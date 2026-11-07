package pl.findini.app.util

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import androidx.core.content.ContextCompat
import androidx.core.location.LocationManagerCompat
import androidx.core.os.CancellationSignal
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import java.util.concurrent.Executors
import kotlin.coroutines.resume

data class Fix(val lat: Double, val lon: Double, val accuracyM: Int?)

/**
 * Jednorazowe pobranie pozycji (bez śledzenia w tle, bez Google Play Services).
 * Pozycja telefonu służy wyłącznie jako punkt startowy — użytkownik potwierdza lub
 * przesuwa miejsce zdarzenia na mapie.
 */
object LocationHelper {
    fun hasPermission(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    fun isEnabled(context: Context): Boolean {
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        return LocationManagerCompat.isLocationEnabled(lm)
    }

    @SuppressLint("MissingPermission")
    suspend fun currentFix(context: Context, timeoutMs: Long = 12_000): Fix? {
        if (!hasPermission(context)) return null
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER, "fused")
            .filter { runCatching { lm.isProviderEnabled(it) }.getOrDefault(false) }
        // Świeża ostatnia pozycja (do 2 min) wystarczy jako punkt startowy.
        val recent = providers.mapNotNull { runCatching { lm.getLastKnownLocation(it) }.getOrNull() }
            .filter { System.currentTimeMillis() - it.time < 120_000 }
            .minByOrNull { it.accuracy }
        if (recent != null) return recent.toFix()
        val provider = providers.firstOrNull() ?: return null
        return withTimeoutOrNull(timeoutMs) {
            suspendCancellableCoroutine { cont ->
                val signal = CancellationSignal()
                cont.invokeOnCancellation { signal.cancel() }
                LocationManagerCompat.getCurrentLocation(lm, provider, signal, Executors.newSingleThreadExecutor()) { loc: Location? ->
                    if (cont.isActive) cont.resume(loc?.toFix())
                }
            }
        }
    }

    private fun Location.toFix() = Fix(latitude, longitude, if (hasAccuracy()) accuracy.toInt() else null)
}
