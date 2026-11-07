package pl.findini.app.data

import android.content.Context
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.RequestBody.Companion.toRequestBody
import pl.findini.app.BuildConfig
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.io.IOException
import java.net.SocketTimeoutException
import java.util.concurrent.TimeUnit

sealed interface Outcome<out T> {
    data class Ok<T>(val value: T) : Outcome<T>
    data class Err(val error: AppError) : Outcome<Nothing>
}

data class AppError(val kind: Kind, val message: String, val code: String? = null, val attemptsLeft: Int? = null) {
    enum class Kind { Offline, Timeout, Server, Client, NotFound, RateLimited, AiUnavailable, Session }
}

inline fun <T> Outcome<T>.onOk(f: (T) -> Unit): Outcome<T> { if (this is Outcome.Ok) f(value); return this }
inline fun <T> Outcome<T>.onErr(f: (AppError) -> Unit): Outcome<T> { if (this is Outcome.Err) f(error); return this }
fun <T> Outcome<T>.valueOrNull(): T? = (this as? Outcome.Ok)?.value

class Repository(context: Context) {
    private val secure = SecureStore(context)
    private val prefs = context.getSharedPreferences("findini_prefs", Context.MODE_PRIVATE)
    val json = Json { ignoreUnknownKeys = true; explicitNulls = false; coerceInputValues = true }

    @Volatile private var token: String? = secure.get(KEY_TOKEN)
    private val sessionMutex = Mutex()

    private val _events = MutableSharedFlow<String>(extraBufferCapacity = 4)
    /** Komunikaty dla użytkownika (np. utrata sesji). */
    val events: SharedFlow<String> = _events

    private val _meta = MutableStateFlow<Meta?>(null)
    val meta: StateFlow<Meta?> = _meta

    val baseUrl: String
        get() = (if (BuildConfig.ALLOW_CUSTOM_SERVER) prefs.getString(KEY_SERVER, null) else null)
            ?.takeIf { it.isNotBlank() } ?: BuildConfig.API_URL

    private val authInterceptor = Interceptor { chain ->
        val req = chain.request()
        val t = token
        // Token wysyłamy wyłącznie do własnego serwera API (nigdy do serwerów kafelków map itp.).
        val sameHost = req.url.host.equals(hostOf(baseUrl), ignoreCase = true)
        val out = if (t != null && sameHost) req.newBuilder().header("Authorization", "Bearer $t").build() else req
        chain.proceed(out.newBuilder().header("Accept-Language", "pl").build())
    }

    val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .addInterceptor(authInterceptor)
        .build()

    @Volatile private var apiCache: Pair<String, FindiniApi>? = null
    private val api: FindiniApi
        get() {
            val url = baseUrl
            apiCache?.let { if (it.first == url) return it.second }
            val created = Retrofit.Builder()
                .baseUrl(url)
                .client(http)
                .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
                .build()
                .create(FindiniApi::class.java)
            apiCache = url to created
            return created
        }

    fun absolute(path: String): String = if (path.startsWith("http")) path else baseUrl.trimEnd('/') + path

    val hasSession: Boolean get() = token != null

    fun setServerUrl(url: String?) {
        prefs.edit().putString(KEY_SERVER, url?.trim()).apply()
        apiCache = null
    }

    // ------------------------------------------------------------ wywołania

    suspend fun <T> public(block: suspend FindiniApi.() -> T): Outcome<T> = runCatchingApi { api.block() }

    /** Operacje prywatne: w razie potrzeby w tle tworzy techniczną sesję gościa (bez rejestracji). */
    suspend fun <T> private(block: suspend FindiniApi.() -> T): Outcome<T> {
        val s = ensureSession()
        if (s is Outcome.Err) return s
        val first = runCatchingApi { api.block() }
        if (first is Outcome.Err && first.error.kind == AppError.Kind.Session) {
            // Sesja unieważniona (np. odzyskana na innym telefonie lub usunięta) — uczciwie informujemy.
            sessionMutex.withLock {
                token = null
                secure.put(KEY_TOKEN, null)
            }
            _events.tryEmit(
                "Twoja poprzednia sesja wygasła. Utworzono nową — wcześniejsze zgłoszenia możesz odzyskać kodem odzyskiwania.",
            )
            val again = ensureSession()
            if (again is Outcome.Err) return again
            return runCatchingApi { api.block() }
        }
        return first
    }

    suspend fun ensureSession(): Outcome<Unit> = sessionMutex.withLock {
        if (token != null) return@withLock Outcome.Ok(Unit)
        when (val r = runCatchingApi { api.createSession() }) {
            is Outcome.Ok -> {
                token = r.value.token
                secure.put(KEY_TOKEN, r.value.token)
                Outcome.Ok(Unit)
            }
            is Outcome.Err -> r
        }
    }

    suspend fun recover(code: String): Outcome<SessionResponse> {
        val r = runCatchingApi { api.recover(RecoverIn(code)) }
        if (r is Outcome.Ok) sessionMutex.withLock {
            token = r.value.token
            secure.put(KEY_TOKEN, r.value.token)
        }
        return r
    }

    suspend fun forgetSession() = sessionMutex.withLock {
        token = null
        secure.put(KEY_TOKEN, null)
    }

    suspend fun loadMeta(force: Boolean = false): Outcome<Meta> {
        _meta.value?.let { if (!force) return Outcome.Ok(it) }
        val r = public { meta() }
        r.onOk { _meta.value = it }
        return r
    }

    suspend fun uploadPhoto(jpeg: ByteArray, purpose: String): Outcome<PhotoUpload> = private {
        val part = MultipartBody.Part.createFormData("file", "photo.jpg", jpeg.toRequestBody("image/jpeg".toMediaType()))
        uploadPhoto(part, purpose.toRequestBody("text/plain".toMediaType()))
    }

    suspend fun searchByPhoto(jpeg: ByteArray, kind: String): Outcome<PhotoSearchResponse> = private {
        val part = MultipartBody.Part.createFormData("file", "query.jpg", jpeg.toRequestBody("image/jpeg".toMediaType()))
        searchByPhoto(part, kind.toRequestBody("text/plain".toMediaType()))
    }

    var lastUpdatesCheck: String?
        get() = prefs.getString(KEY_LAST_CHECK, null)
        set(v) = prefs.edit().putString(KEY_LAST_CHECK, v).apply()

    var notificationsAsked: Boolean
        get() = prefs.getBoolean(KEY_NOTIF_ASKED, false)
        set(v) = prefs.edit().putBoolean(KEY_NOTIF_ASKED, v).apply()

    var hintDismissed: Boolean
        get() = prefs.getBoolean(KEY_HINT, false)
        set(v) = prefs.edit().putBoolean(KEY_HINT, v).apply()

    private suspend fun <T> runCatchingApi(call: suspend () -> T): Outcome<T> = try {
        Outcome.Ok(call())
    } catch (e: HttpException) {
        Outcome.Err(mapHttp(e))
    } catch (e: SocketTimeoutException) {
        Outcome.Err(AppError(AppError.Kind.Timeout, "Serwer nie odpowiada. Spróbuj ponownie za chwilę."))
    } catch (e: IOException) {
        Outcome.Err(AppError(AppError.Kind.Offline, "Brak połączenia z serwerem Findini. Sprawdź internet i spróbuj ponownie."))
    } catch (e: kotlinx.serialization.SerializationException) {
        Outcome.Err(AppError(AppError.Kind.Server, "Nieoczekiwana odpowiedź serwera. Zaktualizuj aplikację lub spróbuj później."))
    }

    private fun mapHttp(e: HttpException): AppError {
        val body = runCatching { e.response()?.errorBody()?.string() }.getOrNull()
        val detail = body?.let { runCatching { json.decodeFromString(ErrorBody.serializer(), it).error }.getOrNull() }
        val msg = detail?.let { d ->
            if (d.fields.isNotEmpty()) d.message + " (" + d.fields.joinToString { it.field } + ")" else d.message
        }
        val kind = when {
            e.code() == 401 -> AppError.Kind.Session
            e.code() == 404 -> AppError.Kind.NotFound
            e.code() == 429 -> AppError.Kind.RateLimited
            detail?.code == "ai_unavailable" -> AppError.Kind.AiUnavailable
            e.code() >= 500 -> AppError.Kind.Server
            else -> AppError.Kind.Client
        }
        val fallback = when (kind) {
            AppError.Kind.Server -> "Błąd serwera. Twoje dane nie zostały utracone — spróbuj ponownie."
            AppError.Kind.NotFound -> "Nie znaleziono — zgłoszenie mogło zostać zamknięte."
            else -> "Nie udało się wykonać operacji (${e.code()})."
        }
        return AppError(kind, msg ?: fallback, detail?.code, detail?.attemptsLeft)
    }

    private fun hostOf(url: String): String = runCatching { java.net.URI(url).host }.getOrNull() ?: "localhost"

    companion object {
        private const val KEY_TOKEN = "session_token"
        private const val KEY_SERVER = "server_url"
        private const val KEY_LAST_CHECK = "last_updates_check"
        private const val KEY_NOTIF_ASKED = "notif_asked"
        private const val KEY_HINT = "hint_dismissed"
    }
}
