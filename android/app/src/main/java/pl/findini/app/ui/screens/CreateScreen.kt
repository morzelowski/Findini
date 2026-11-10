package pl.findini.app.ui.screens

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.CloudUpload
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.HideImage
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.MyLocation
import androidx.compose.material.icons.outlined.PhotoLibrary
import androidx.compose.material.icons.outlined.Public
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.SelectableDates
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import coil3.compose.AsyncImage
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive
import org.maplibre.android.geometry.LatLng
import pl.findini.app.app
import pl.findini.app.data.AiSuggestion
import pl.findini.app.data.AppError
import pl.findini.app.data.DraftStore
import pl.findini.app.data.LocationIn
import pl.findini.app.data.Meta
import pl.findini.app.data.Outcome
import pl.findini.app.data.Report
import pl.findini.app.data.ReportCreate
import pl.findini.app.data.ReportDraft
import pl.findini.app.data.ReportUpdate
import pl.findini.app.data.Repository
import pl.findini.app.ui.components.InfoCard
import pl.findini.app.ui.components.PickerMap
import pl.findini.app.ui.components.PrivacyLine
import pl.findini.app.ui.components.SectionTitle
import pl.findini.app.ui.components.Tone
import pl.findini.app.ui.components.categoryIcon
import pl.findini.app.util.Format
import pl.findini.app.util.Images
import pl.findini.app.util.LocationHelper
import androidx.compose.material.icons.outlined.Search
import java.io.File
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZonedDateTime

enum class UploadState { Uploading, Done, Failed }

data class CreateUi(
    val draft: ReportDraft,
    val uploads: Map<String, UploadState> = emptyMap(),
    val suggestions: Map<String, AiSuggestion> = emptyMap(),
    val suggestionApplied: Boolean = false,
    val aiNote: String? = null,
    val restored: Boolean = false,
    val locating: Boolean = false,
    val gpsNote: String? = null,
    val recenter: LatLng? = null,
    val publishing: Boolean = false,
    val error: AppError? = null,
    val published: Report? = null,
    val photoConfirmed: Boolean = false,
) {
    /** Podpowiedź dotyczy pierwszego (głównego) zdjęcia, które wciąż jest w formularzu. */
    val suggestion: AiSuggestion? get() = draft.photoPaths.firstNotNullOfOrNull { suggestions[it] }
}

class CreateVM(private val repo: Repository, private val drafts: DraftStore) : ViewModel() {
    val ui = MutableStateFlow(CreateUi(ReportDraft()))
    private var saveJob: Job? = null
    private var initialized = false

    fun init(kind: String, editId: String?, fromId: String?, meta: Meta?) {
        if (initialized) return
        initialized = true
        if (editId != null) {
            viewModelScope.launch {
                when (val r = repo.private { report(editId) }) {
                    is Outcome.Ok -> ui.update { it.copy(draft = fromReport(r.value), photoConfirmed = true) }
                    is Outcome.Err -> ui.update { it.copy(error = r.error) }
                }
            }
            return
        }
        val saved = drafts.load()
        if (saved != null && saved.kind == kind && saved.editingReportId == null && fromId == null) {
            ui.update { it.copy(draft = saved, restored = true, uploads = saved.uploadedPhotoIds.mapValues { UploadState.Done }) }
            return
        }
        val now = ZonedDateTime.now(Format.zone)
        var d = ReportDraft(
            kind = kind,
            fromIso = Format.toUtcIso(if (kind == "found") now.minusMinutes(30) else now.minusHours(3)),
            toIso = Format.toUtcIso(now),
        )
        ui.update { it.copy(draft = d) }
        if (fromId != null) viewModelScope.launch {
            // „Znalazłem coś podobnego” do zgłoszenia zguby: podpowiadamy kategorię i kolor (do zmiany).
            (repo.public { report(fromId) } as? Outcome.Ok)?.value?.let { src ->
                d = d.copy(
                    category = src.category,
                    colors = src.colors,
                    attributes = src.attr("subtype")?.let { mapOf("subtype" to it) } ?: emptyMap(),
                )
                ui.update { it.copy(draft = d) }
            }
        }
    }

    private fun fromReport(r: Report): ReportDraft = ReportDraft(
        kind = r.kind,
        uploadedPhotoIds = r.photos.associate { "remote:" + it.id to it.id },
        photoPaths = r.photos.map { "remote:" + it.id },
        noPhoto = r.photos.isEmpty(),
        lat = r.private?.exactLat, lon = r.private?.exactLon, accuracyM = r.private?.accuracyM,
        uncertaintyM = r.private?.uncertaintyM ?: 0, locationSource = r.private?.locationSource,
        areaLabel = r.area.label.orEmpty(), fromIso = r.occurredFrom, toIso = r.occurredTo,
        category = r.category, attributes = r.attributes.associate { it.key to it.text }, colors = r.colors,
        title = r.title, description = r.description, holding = r.holding ?: "with_finder",
        holdingNote = r.holdingNote.orEmpty(), secretDetails = r.private?.secretDetails.orEmpty(),
        claimQuestion = r.private?.claimQuestion.orEmpty(), editingReportId = r.id,
    )

    fun edit(f: (ReportDraft) -> ReportDraft) {
        ui.update { it.copy(draft = f(it.draft), error = null) }
        saveJob?.cancel()
        saveJob = viewModelScope.launch {
            delay(400)
            if (ui.value.draft.editingReportId == null) drafts.save(ui.value.draft)
        }
    }

    fun discardDraft(meta: Meta?) {
        drafts.clear()
        val k = ui.value.draft.kind
        initialized = false
        ui.value = CreateUi(ReportDraft())
        init(k, null, null, meta)
    }

    fun addPhoto(bytes: ByteArray, file: File) {
        val path = file.absolutePath
        edit { it.copy(photoPaths = (it.photoPaths + path).takeLast(4), noPhoto = false) }
        upload(path, bytes)
    }

    fun retryUpload(path: String) {
        viewModelScope.launch {
            val bytes = Images.prepare(File(path)) ?: return@launch
            upload(path, bytes)
        }
    }

    private fun upload(path: String, bytes: ByteArray) {
        ui.update { it.copy(uploads = it.uploads + (path to UploadState.Uploading)) }
        viewModelScope.launch {
            when (val r = repo.uploadPhoto(bytes, "report")) {
                is Outcome.Ok -> {
                    edit { it.copy(uploadedPhotoIds = it.uploadedPhotoIds + (path to r.value.id)) }
                    ui.update { s ->
                        s.copy(
                            uploads = s.uploads + (path to UploadState.Done),
                            suggestions = r.value.suggestion?.let { sg -> s.suggestions + (path to sg) } ?: s.suggestions,
                            aiNote = when (r.value.aiStatus) {
                                "unavailable" -> "Podpowiedzi AI są chwilowo niedostępne — wybierz kategorię ręcznie."
                                "pending" -> "Analiza zdjęcia trwa dłużej — dokończymy ją w tle."
                                else -> s.aiNote
                            },
                        )
                    }
                }
                is Outcome.Err -> ui.update { it.copy(uploads = it.uploads + (path to UploadState.Failed), error = r.error) }
            }
        }
    }

    fun removePhoto(path: String) {
        val id = ui.value.draft.uploadedPhotoIds[path]
        edit { it.copy(photoPaths = it.photoPaths - path, uploadedPhotoIds = it.uploadedPhotoIds - path) }
        ui.update { it.copy(suggestions = it.suggestions - path, suggestionApplied = false) }
        if (id != null && !path.startsWith("remote:")) viewModelScope.launch { repo.private { deletePhoto(id) } }
        if (!path.startsWith("remote:")) runCatching { File(path).delete() }
    }

    fun applySuggestion(s: AiSuggestion) {
        edit {
            it.copy(
                category = s.category,
                attributes = if (s.subtype != null) it.attributes + ("subtype" to s.subtype) else it.attributes,
                colors = s.colors.ifEmpty { it.colors },
            )
        }
        ui.update { it.copy(suggestionApplied = true) }
    }

    fun locate(context: android.content.Context) {
        viewModelScope.launch {
            ui.update { it.copy(locating = true, gpsNote = null) }
            if (!LocationHelper.isEnabled(context)) {
                ui.update { it.copy(locating = false, gpsNote = "Lokalizacja w telefonie jest wyłączona. Wskaż miejsce na mapie.") }
                return@launch
            }
            val fix = LocationHelper.currentFix(context)
            if (fix == null) {
                ui.update { it.copy(locating = false, gpsNote = "Nie udało się ustalić pozycji. Przesuń mapę ręcznie.") }
            } else {
                edit { it.copy(lat = fix.lat, lon = fix.lon, accuracyM = fix.accuracyM, locationSource = "gps") }
                ui.update {
                    it.copy(
                        locating = false,
                        recenter = LatLng(fix.lat, fix.lon),
                        gpsNote = "Pozycja telefonu ±${fix.accuracyM ?: "?"} m. Jeśli rzecz zgubiłeś/znalazłeś gdzie indziej — przesuń mapę.",
                    )
                }
                suggestLabel(fix.lat, fix.lon)
            }
        }
    }

    fun mapMoved(ll: LatLng) {
        val d = ui.value.draft
        if (d.lat != null && d.lon != null && Math.abs(d.lat - ll.latitude) < 1e-6 && Math.abs(d.lon - ll.longitude) < 1e-6) return
        // Ręczne przesunięcie po GPS = korekta; źródłem staje się mapa.
        val manual = d.locationSource == null || (d.lat != null && (Math.abs(d.lat - ll.latitude) > 0.0002 || Math.abs(d.lon!! - ll.longitude) > 0.0002))
        edit { it.copy(lat = ll.latitude, lon = ll.longitude, locationSource = if (manual) "map" else it.locationSource, accuracyM = if (manual) null else it.accuracyM) }
        suggestLabel(ll.latitude, ll.longitude)
    }

    private var labelJob: Job? = null
    private fun suggestLabel(lat: Double, lon: Double) {
        labelJob?.cancel()
        labelJob = viewModelScope.launch {
            delay(600)
            val r = repo.public { placeSuggest(lat, lon) }
            val label = (r as? Outcome.Ok)?.value?.get("label")
            val d = ui.value.draft
            if (label != null && (d.areaLabel.isBlank() || d.areaLabel.startsWith("okolice:"))) edit { it.copy(areaLabel = label) }
        }
    }

    fun publish() {
        val d = ui.value.draft
        viewModelScope.launch {
            ui.update { it.copy(publishing = true, error = null) }
            // Dosyłanie zdjęć, które nie przeszły (np. brak sieci przy wyborze).
            for (p in d.photoPaths) {
                if (d.uploadedPhotoIds[p] == null && !p.startsWith("remote:")) {
                    val bytes = Images.prepare(File(p))
                    if (bytes == null) continue
                    when (val r = repo.uploadPhoto(bytes, "report")) {
                        is Outcome.Ok -> edit { it.copy(uploadedPhotoIds = it.uploadedPhotoIds + (p to r.value.id)) }
                        is Outcome.Err -> { ui.update { it.copy(publishing = false, error = r.error) }; return@launch }
                    }
                }
            }
            val cur = ui.value.draft
            val photoIds = cur.photoPaths.mapNotNull { cur.uploadedPhotoIds[it] }
            val attrs = cur.attributes.filterValues { it.isNotBlank() }.mapValues { (_, v) -> v.toIntOrNull()?.let { JsonPrimitive(it) } ?: JsonPrimitive(v) }
            val loc = LocationIn(cur.lat!!, cur.lon!!, cur.accuracyM, cur.uncertaintyM, cur.locationSource ?: "map")
            val result = if (cur.editingReportId != null) {
                repo.private {
                    updateReport(
                        cur.editingReportId,
                        ReportUpdate(
                            category = cur.category, title = cur.title.trim(), description = cur.description.trim(), attributes = attrs,
                            colors = cur.colors, occurredFrom = cur.fromIso, occurredTo = cur.toIso, location = loc,
                            areaLabel = cur.areaLabel.trim(), holding = if (cur.kind == "found") cur.holding else null,
                            holdingNote = if (cur.kind == "found") cur.holdingNote.trim() else null,
                            secretDetails = cur.secretDetails.trim(),
                            claimQuestion = if (cur.kind == "found") cur.claimQuestion.trim() else null, photoIds = photoIds,
                        ),
                    )
                }
            } else {
                repo.private {
                    createReport(
                        ReportCreate(
                            kind = cur.kind, category = cur.category!!, title = cur.title.trim(), description = cur.description.trim(),
                            attributes = attrs, colors = cur.colors, occurredFrom = cur.fromIso!!, occurredTo = cur.toIso!!,
                            location = loc, areaLabel = cur.areaLabel.trim().ifBlank { null },
                            holding = if (cur.kind == "found") cur.holding else null,
                            holdingNote = if (cur.kind == "found") cur.holdingNote.trim().ifBlank { null } else null,
                            secretDetails = cur.secretDetails.trim().ifBlank { null },
                            claimQuestion = if (cur.kind == "found") cur.claimQuestion.trim().ifBlank { null } else null,
                            photoIds = photoIds,
                        ),
                    )
                }
            }
            when (result) {
                is Outcome.Ok -> {
                    // Sukces pokazujemy dopiero po potwierdzeniu przez serwer.
                    if (cur.editingReportId == null) {
                        drafts.clear()
                        cur.photoPaths.filterNot { it.startsWith("remote:") }.forEach { runCatching { File(it).delete() } }
                    }
                    ui.update { it.copy(publishing = false, published = result.value) }
                }
                is Outcome.Err -> ui.update { it.copy(publishing = false, error = result.error) }
            }
        }
    }
}

private val STEPS = listOf("Zdjęcie", "Gdzie i kiedy", "Opis", "Sprawdź")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CreateScreen(nav: NavController, kind: String, editId: String?, fromReportId: String?) {
    val context = LocalContext.current
    val app = context.app
    val vm: CreateVM = viewModel { CreateVM(app.repo, app.drafts) }
    val meta by app.repo.meta.collectAsState()
    val ui by vm.ui.collectAsState()
    val d = ui.draft
    var camera by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(meta) { vm.init(kind, editId, fromReportId, meta) }
    LaunchedEffect(ui.published) {
        ui.published?.let { r ->
            nav.navigate("myreport/${r.id}?fresh=1".substringBefore("?")) {
                popUpTo("create?kind={kind}&edit={edit}&from={from}") { inclusive = true }
            }
        }
    }

    if (camera) {
        BackHandler { camera = false }
        CameraCapture(
            onCaptured = { file ->
                camera = false
                scope.launch {
                    val bytes = Images.prepare(file)
                    if (bytes != null) {
                        file.writeBytes(bytes) // nadpisujemy wersją bez metadanych
                        vm.addPhoto(bytes, file)
                    }
                }
            },
            onClose = { camera = false },
        )
        return
    }

    val step = d.step
    val title = when {
        d.editingReportId != null -> "Edytuj zgłoszenie"
        d.kind == "found" -> "Znalazłem coś"
        else -> "Zgubiłem coś"
    }
    BackHandler(enabled = step > 0) { vm.edit { it.copy(step = step - 1) } }

    ScreenScaffold(
        title = title,
        onBack = { if (step > 0) vm.edit { it.copy(step = step - 1) } else nav.popBackStack() },
        bottomBar = {
            BottomActions {
                ui.error?.let { e ->
                    Text(e.message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
                val canNext = when (step) {
                    0 -> d.photoPaths.isNotEmpty() || d.noPhoto
                    1 -> d.lat != null && d.fromIso != null && d.toIso != null
                    2 -> d.category != null && (d.title.isBlank() || d.title.trim().length >= 3)
                    else -> !ui.publishing && (d.photoPaths.isEmpty() || ui.photoConfirmed)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (step > 0) OutlinedButton(shape = MaterialTheme.shapes.small, onClick = { vm.edit { it.copy(step = step - 1) } }) { Text("Wstecz") }
                    Button(shape = MaterialTheme.shapes.small,
                        onClick = {
                            if (step < 3) {
                                if (step == 2 && d.title.isBlank()) vm.edit { it.copy(title = suggestTitle(it, meta)) }
                                vm.edit { it.copy(step = step + 1) }
                            } else vm.publish()
                        },
                        enabled = canNext,
                        modifier = Modifier.weight(1f),
                    ) {
                        if (ui.publishing) {
                            CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                            Spacer(Modifier.width(8.dp))
                            Text("Zapisuję na serwerze…")
                        } else Text(if (step < 3) "Dalej" else if (d.editingReportId != null) "Zapisz zmiany" else "Opublikuj")
                    }
                }
            }
        },
    ) { mod ->
        Column(mod.fillMaxSize()) {
            LinearProgressIndicator(progress = { (step + 1) / 4f }, modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp))
            Text(
                "Krok ${step + 1} z 4 · ${STEPS[step]}",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
            )
            if (ui.restored && step == 0) {
                InfoCard("Przywrócono szkic", "Wróciłeś do niedokończonego zgłoszenia.", Tone.Info, modifier = Modifier.padding(horizontal = 16.dp)) {
                    TextButton(onClick = { vm.discardDraft(meta) }) { Text("Zacznij od nowa") }
                }
            }
            AnimatedContent(targetState = step, label = "step") { s ->
                when (s) {
                    0 -> PhotoStep(vm, ui, meta, onCamera = { camera = true })
                    1 -> PlaceTimeStep(vm, ui, meta)
                    2 -> DetailsStep(vm, ui, meta)
                    else -> ReviewStep(vm, ui, meta)
                }
            }
        }
    }
}

fun suggestTitle(d: ReportDraft, meta: Meta?): String {
    val rawSub = d.attributes["subtype"]?.takeIf { it.isNotBlank() && it != "inne" }
    val noun = rawSub ?: meta?.category(d.category)?.takeIf { it.key in setOf("keys", "electronics", "clothing") }?.label?.lowercase() ?: "przedmiot"
    val color = d.colors.firstOrNull { it != "multi" }?.let { meta?.color(it)?.label }
    val t = if (color != null) "${agree(color, noun)} $noun" else noun
    return t.replaceFirstChar { it.uppercase() }
}

/**
 * Zgodność przymiotnika koloru z rodzajem rzeczownika (uproszczona, dla słownika kategorii):
 * „czapka” → „biała czapka”, „słuchawki”/„etui” → „białe…”, „plecak” → „biały plecak”.
 */
fun agree(adjMasc: String, noun: String): String {
    val head = noun.substringBefore(" ").substringBefore("/").trim().lowercase()
    return when {
        head.endsWith("a") -> adjMasc.dropLast(1) + "a"
        head.endsWith("i") || head.endsWith("y") || head.endsWith("e") ->
            if (adjMasc.endsWith("i")) adjMasc + "e" else adjMasc.dropLast(1) + "e"
        else -> adjMasc
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PhotoStep(vm: CreateVM, ui: CreateUi, meta: Meta?, onCamera: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val d = ui.draft
    var cameraDenied by remember { mutableStateOf(false) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(4)) { uris: List<Uri> ->
        scope.launch {
            uris.forEach { uri ->
                val bytes = Images.prepare(context, uri)
                if (bytes != null) vm.addPhoto(bytes, Images.saveDraftPhoto(context, bytes))
            }
        }
    }
    val camPerm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        if (ok) onCamera() else cameraDenied = true
    }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            if (d.kind == "found") "Zrób zdjęcie znalezionej rzeczy" else "Masz zdjęcie zgubionej rzeczy?",
            style = MaterialTheme.typography.headlineSmall,
        )
        Text(
            if (d.kind == "found") "Zdjęcie bardzo pomaga właścicielowi. Nie fotografuj dokumentów, twarzy ani adresów."
            else "Twoje stare zdjęcie (lub zdjęcie takiego samego modelu) pozwoli wyszukiwać zdjęciem. Możesz też pominąć ten krok.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(shape = MaterialTheme.shapes.small, onClick = {
                if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) onCamera()
                else camPerm.launch(Manifest.permission.CAMERA)
            }, modifier = Modifier.weight(1f)) {
                Icon(Icons.Outlined.CameraAlt, null); Spacer(Modifier.width(6.dp)); Text("Aparat")
            }
            OutlinedButton(shape = MaterialTheme.shapes.small, onClick = {
                picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
            }, modifier = Modifier.weight(1f)) {
                Icon(Icons.Outlined.PhotoLibrary, null); Spacer(Modifier.width(6.dp)); Text("Galeria")
            }
        }
        if (cameraDenied) {
            InfoCard(
                "Brak dostępu do aparatu",
                "Możesz wybrać zdjęcie z galerii albo kontynuować bez zdjęcia. Dostęp możesz włączyć w ustawieniach.",
                Tone.Warning,
            ) {
                TextButton(onClick = {
                    context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null)))
                }) { Text("Otwórz ustawienia") }
            }
        }
        if (d.photoPaths.isNotEmpty()) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                d.photoPaths.forEach { p -> PhotoTile(p, ui.uploads[p], vm) }
            }
            ui.suggestion?.let { s ->
                if (!ui.suggestionApplied) SuggestionCard(s, meta, onApply = { vm.applySuggestion(s) })
            }
            ui.aiNote?.let { InfoCard(null, it, Tone.Info, Icons.Outlined.AutoAwesome) }
            InfoCard(
                "Sprawdź zdjęcie przed publikacją",
                "Usunęliśmy metadane (GPS, model telefonu). Upewnij się, że nie widać na nim dokumentów, adresów, twarzy, numerów telefonów ani tablic rejestracyjnych.",
                Tone.Privacy,
            )
        }
        Row(
            Modifier.fillMaxWidth().clip(MaterialTheme.shapes.small)
                .selectable(d.noPhoto, role = Role.Checkbox) { vm.edit { it.copy(noPhoto = !it.noPhoto) } }
                .padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Checkbox(checked = d.noPhoto && d.photoPaths.isEmpty(), onCheckedChange = null, enabled = d.photoPaths.isEmpty())
            Spacer(Modifier.width(8.dp))
            Icon(Icons.Outlined.HideImage, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.width(8.dp))
            Text("Kontynuuj bez zdjęcia", style = MaterialTheme.typography.bodyLarge)
        }
        meta?.category(d.category)?.tip?.let { InfoCard(null, it, Tone.Warning) }
        Spacer(Modifier.height(16.dp))
    }
}

@Composable
private fun PhotoTile(path: String, state: UploadState?, vm: CreateVM) {
    val repo = LocalContext.current.app.repo
    val model: Any = if (path.startsWith("remote:")) repo.absolute("/v1/photos/${path.removePrefix("remote:")}?size=thumb") else File(path)
    Box(Modifier.size(104.dp).clip(MaterialTheme.shapes.medium)) {
        AsyncImage(model = model, contentDescription = "Dodane zdjęcie", contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize())
        Surface(color = MaterialTheme.colorScheme.surface.copy(alpha = 0.85f), shape = MaterialTheme.shapes.small, modifier = Modifier.align(Alignment.BottomStart).padding(4.dp)) {
            Row(Modifier.padding(horizontal = 6.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                when (state) {
                    UploadState.Uploading -> { CircularProgressIndicator(Modifier.size(12.dp), strokeWidth = 2.dp); Spacer(Modifier.width(4.dp)); Text("Wysyłam", style = MaterialTheme.typography.labelSmall) }
                    UploadState.Failed -> TextButton(onClick = { vm.retryUpload(path) }, modifier = Modifier.height(28.dp)) {
                        Icon(Icons.Outlined.ErrorOutline, null, Modifier.size(14.dp)); Text("Ponów", style = MaterialTheme.typography.labelSmall)
                    }
                    UploadState.Done -> { Icon(Icons.Outlined.CheckCircle, "Wysłane", Modifier.size(14.dp), tint = MaterialTheme.colorScheme.primary) }
                    null -> { Icon(Icons.Outlined.CloudUpload, "Czeka na wysłanie", Modifier.size(14.dp)) }
                }
            }
        }
        IconButton(onClick = { vm.removePhoto(path) }, modifier = Modifier.align(Alignment.TopEnd)) {
            Surface(color = MaterialTheme.colorScheme.surface.copy(alpha = 0.85f), shape = MaterialTheme.shapes.small) {
                Icon(Icons.Outlined.Delete, "Usuń zdjęcie", Modifier.padding(4.dp).size(18.dp))
            }
        }
    }
}

@Composable
private fun SuggestionCard(s: AiSuggestion, meta: Meta?, onApply: () -> Unit) {
    val cat = meta?.category(s.category)?.label ?: s.category
    val text = buildString {
        append(cat)
        s.subtype?.let { append(" › $it") }
        if (s.colorsPl.isNotEmpty()) append(" · kolor: " + s.colorsPl.joinToString())
    }
    InfoCard(
        if (s.confidence == "clear") "Podpowiedź z analizy zdjęcia" else "Niepewna podpowiedź z analizy zdjęcia",
        "$text\nTo tylko sugestia lokalnego modelu — zatwierdź lub wybierz sam w kroku „Opis”.",
        Tone.Info,
        Icons.Outlined.AutoAwesome,
    ) {
        Row {
            TextButton(onClick = onApply) { Text("Zastosuj") }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun PlaceTimeStep(vm: CreateVM, ui: CreateUi, meta: Meta?) {
    val context = LocalContext.current
    val d = ui.draft
    var locDenied by remember { mutableStateOf(false) }
    var showDate by remember { mutableStateOf(false) }
    var timePick by remember { mutableStateOf<String?>(null) }
    var placeSearch by remember { mutableStateOf(false) }
    val perm = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { res ->
        if (res.values.any { it }) vm.locate(context) else locDenied = true
    }
    val from = Format.parse(d.fromIso) ?: ZonedDateTime.now(Format.zone)
    val to = Format.parse(d.toIso) ?: ZonedDateTime.now(Format.zone)
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(if (d.kind == "found") "Gdzie znalazłeś przedmiot?" else "Gdzie mogłeś go zgubić?", style = MaterialTheme.typography.headlineSmall)
        Text(
            "Chodzi o miejsce zdarzenia, a nie o to, gdzie jesteś teraz. Pinezkę możesz przesunąć. Publicznie pokażemy tylko obszar ok. 500 m.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        OutlinedButton(shape = MaterialTheme.shapes.small, onClick = { placeSearch = true }, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Outlined.Search, null)
            Spacer(Modifier.width(8.dp))
            Text("Wyszukaj miejscowość w Polsce")
        }
        val start = if (d.lat != null && d.lon != null) LatLng(d.lat, d.lon) else LatLng(meta?.pilot?.center?.lat ?: 52.0, meta?.pilot?.center?.lon ?: 19.0)
        PickerMap(
            modifier = Modifier.fillMaxWidth().height(280.dp).clip(MaterialTheme.shapes.large),
            initial = start,
            uncertaintyM = maxOf(d.uncertaintyM, d.accuracyM ?: 0),
            recenter = ui.recenter,
            hasLocation = d.lat != null && d.lon != null,
            onCenter = vm::mapMoved,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedButton(shape = MaterialTheme.shapes.small, onClick = {
                if (LocationHelper.hasPermission(context)) vm.locate(context)
                else perm.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
            }) {
                if (ui.locating) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp) else Icon(Icons.Outlined.MyLocation, null)
                Spacer(Modifier.width(6.dp)); Text("Jestem na miejscu (GPS)")
            }
            Text(
                when (d.locationSource) { "gps" -> "Źródło: GPS"; "map" -> "Źródło: ręcznie"; else -> "" },
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        ui.gpsNote?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        if (locDenied) {
            InfoCard("Bez dostępu do lokalizacji", "Nic nie szkodzi — przesuń mapę lub wybierz znane miejsce poniżej.", Tone.Info)
        }
        if (d.lat == null) Text("Wybierz miejscowość, użyj GPS lub przesuń mapę, aby wskazać miejsce zdarzenia.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
        Text("Nie jestem pewien dokładnego miejsca: ${if (d.uncertaintyM == 0) "znam miejsce" else "promień " + Format.radius(d.uncertaintyM)}", style = MaterialTheme.typography.labelLarge)
        Slider(value = d.uncertaintyM.toFloat(), onValueChange = { v -> vm.edit { it.copy(uncertaintyM = (v / 50).toInt() * 50) } }, valueRange = 0f..3000f)
        OutlinedTextField(
            value = d.areaLabel,
            onValueChange = { v -> vm.edit { it.copy(areaLabel = v.take(80)) } },
            label = { Text("Opis okolicy (publiczny)") },
            supportingText = { Text("Np. „okolice dworca, przystanek”. Bez adresu domowego.") },
            leadingIcon = { Icon(Icons.Outlined.Public, "Publiczne") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )

        SectionTitle(if (d.kind == "found") "Kiedy znalazłeś?" else "Kiedy mogłeś zgubić?")
        val today = LocalDate.now(Format.zone)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            val now = ZonedDateTime.now(Format.zone)
            FilterChip(selected = false, onClick = { setRange(vm, now.minusMinutes(30), now) }, label = { Text("Przed chwilą") })
            FilterChip(selected = false, onClick = { setRange(vm, now.minusHours(3), now) }, label = { Text("Ostatnie 3 h") })
            FilterChip(selected = false, onClick = { setRange(vm, today.atStartOfDay(Format.zone), now) }, label = { Text("Dziś") })
            FilterChip(selected = false, onClick = {
                val y = today.minusDays(1)
                setRange(vm, y.atStartOfDay(Format.zone), y.atTime(LocalTime.of(23, 59)).atZone(Format.zone))
            }, label = { Text("Wczoraj") })
            FilterChip(selected = false, onClick = { showDate = true }, label = { Text("Inny dzień…") })
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(shape = MaterialTheme.shapes.small, onClick = { timePick = "from" }, modifier = Modifier.weight(1f)) { Text("Od: ${Format.day(from)} ${Format.time(from)}") }
            OutlinedButton(shape = MaterialTheme.shapes.small, onClick = { timePick = "to" }, modifier = Modifier.weight(1f)) { Text("Do: ${Format.day(to)} ${Format.time(to)}") }
        }
        Text("Podaj przedział, jeśli nie wiesz dokładnie — to pomaga w dopasowaniach.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)

        if (d.kind == "found") {
            SectionTitle("Gdzie jest teraz przedmiot?")
            listOf("with_finder" to "Mam go przy sobie", "at_place" to "Zostawiłem u obsługi / w portierni", "office" to "Oddałem do biura rzeczy znalezionych lub na policję").forEach { (k, label) ->
                Row(
                    Modifier.fillMaxWidth().selectable(d.holding == k, role = Role.RadioButton) { vm.edit { it.copy(holding = k) } }.padding(vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    RadioButton(selected = d.holding == k, onClick = null)
                    Spacer(Modifier.width(8.dp))
                    Text(label, style = MaterialTheme.typography.bodyLarge)
                }
            }
            if (d.holding != "with_finder") {
                OutlinedTextField(
                    value = d.holdingNote,
                    onValueChange = { v -> vm.edit { it.copy(holdingNote = v.take(120)) } },
                    label = { Text("Gdzie dokładnie? (publiczne)") },
                    supportingText = { Text("Np. „portiernia budynku A-0”. Bez danych osobowych.") },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
        Spacer(Modifier.height(16.dp))
    }

    if (placeSearch) {
        pl.findini.app.ui.components.PlaceSearchSheet(
            current = null, searchArea = false, onDismiss = { placeSearch = false },
        ) { place ->
            if (place != null) {
                val ll = LatLng(place.lat, place.lon)
                vm.mapMoved(ll)
                vm.edit { it.copy(areaLabel = "okolice: ${place.name}", locationSource = "map", uncertaintyM = 500) }
                vm.ui.update { it.copy(recenter = ll) }
            }
            placeSearch = false
        }
    }
    if (showDate) {
        val state = rememberDatePickerState(
            initialSelectedDateMillis = from.toLocalDate().atStartOfDay(java.time.ZoneOffset.UTC).toInstant().toEpochMilli(),
            selectableDates = object : SelectableDates {
                override fun isSelectableDate(utcTimeMillis: Long) = utcTimeMillis <= System.currentTimeMillis()
            },
        )
        DatePickerDialog(
            onDismissRequest = { showDate = false },
            confirmButton = {
                TextButton(onClick = {
                    state.selectedDateMillis?.let { ms ->
                        val day = java.time.Instant.ofEpochMilli(ms).atZone(java.time.ZoneOffset.UTC).toLocalDate()
                        val end = if (day == LocalDate.now(Format.zone)) ZonedDateTime.now(Format.zone) else day.atTime(23, 59).atZone(Format.zone)
                        setRange(vm, day.atStartOfDay(Format.zone), end)
                    }
                    showDate = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { showDate = false }) { Text("Anuluj") } },
        ) { DatePicker(state) }
    }
    timePick?.let { which ->
        val base = if (which == "from") from else to
        val state = rememberTimePickerState(base.hour, base.minute, is24Hour = true)
        AlertDialog(
            onDismissRequest = { timePick = null },
            title = { Text(if (which == "from") "Od której?" else "Do której?") },
            text = { TimePicker(state) },
            confirmButton = {
                TextButton(onClick = {
                    var t = base.withHour(state.hour).withMinute(state.minute)
                    val now = ZonedDateTime.now(Format.zone)
                    if (t.isAfter(now)) t = now
                    if (which == "from") setRange(vm, t, if (to.isBefore(t)) t else to) else setRange(vm, if (from.isAfter(t)) t else from, t)
                    timePick = null
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { timePick = null }) { Text("Anuluj") } },
        )
    }
}

private fun setRange(vm: CreateVM, a: ZonedDateTime, b: ZonedDateTime) {
    vm.edit { it.copy(fromIso = Format.toUtcIso(a), toIso = Format.toUtcIso(b)) }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DetailsStep(vm: CreateVM, ui: CreateUi, meta: Meta?) {
    val d = ui.draft
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("Co to jest?", style = MaterialTheme.typography.headlineSmall)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            meta?.categories?.forEach { c ->
                FilterChip(
                    selected = d.category == c.key,
                    onClick = { vm.edit { it.copy(category = c.key, attributes = if (it.category == c.key) it.attributes else emptyMap()) } },
                    label = { Text(c.label) },
                    leadingIcon = { Icon(categoryIcon(c.key), null, Modifier.size(18.dp)) },
                )
            }
        }
        val cat = meta?.category(d.category)
        cat?.tip?.let { InfoCard(null, it, Tone.Warning) }
        cat?.attributes?.forEach { a ->
            when (a.type) {
                "select" -> {
                    Text(a.label, style = MaterialTheme.typography.titleSmall)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        a.options.forEach { o ->
                            FilterChip(
                                selected = d.attributes[a.key] == o,
                                onClick = { vm.edit { it.copy(attributes = if (it.attributes[a.key] == o) it.attributes - a.key else it.attributes + (a.key to o)) } },
                                label = { Text(o) },
                            )
                        }
                    }
                }
                else -> OutlinedTextField(
                    value = d.attributes[a.key].orEmpty(),
                    onValueChange = { v -> vm.edit { it.copy(attributes = it.attributes + (a.key to v.take(a.maxLen))) } },
                    label = { Text(a.label) },
                    supportingText = a.hint?.let { h -> { Text(h) } },
                    keyboardOptions = if (a.type == "number") KeyboardOptions(keyboardType = KeyboardType.Number) else KeyboardOptions.Default,
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
        Text("Kolor (maks. 3)", style = MaterialTheme.typography.titleSmall)
        ColorPicker(meta, d.colors) { cols -> vm.edit { it.copy(colors = cols) } }
        OutlinedTextField(
            value = d.title,
            onValueChange = { v -> vm.edit { it.copy(title = v.take(80)) } },
            label = { Text("Tytuł (publiczny)") },
            placeholder = { Text(suggestTitle(d, meta)) },
            trailingIcon = {
                if (d.title.isBlank() && d.category != null) TextButton(onClick = { vm.edit { it.copy(title = suggestTitle(it, meta)) } }) { Text("Użyj") }
            },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = d.description,
            onValueChange = { v -> vm.edit { it.copy(description = v.take(1000)) } },
            label = { Text("Opis (publiczny)") },
            supportingText = { Text("Bez telefonu, e-maila i adresu — kontakt jest prywatny w aplikacji. ${d.description.length}/1000") },
            minLines = 3,
            modifier = Modifier.fillMaxWidth(),
        )
        Surface(color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.5f), shape = MaterialTheme.shapes.medium) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.Lock, null, tint = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.width(8.dp))
                    Text("Tylko dla Ciebie — nigdy nie publikujemy", style = MaterialTheme.typography.titleSmall)
                }
                if (d.kind == "found") {
                    OutlinedTextField(
                        value = d.secretDetails,
                        onValueChange = { v -> vm.edit { it.copy(secretDetails = v.take(500)) } },
                        label = { Text("Ukryty szczegół do weryfikacji") },
                        supportingText = { Text("Coś, co zna tylko właściciel: zawartość kieszeni, uszkodzenie, naklejka, grawer. Porównasz to z odpowiedzią.") },
                        minLines = 2,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        value = d.claimQuestion,
                        onValueChange = { v -> vm.edit { it.copy(claimQuestion = v.take(200)) } },
                        label = { Text("Pytanie do osoby zgłaszającej roszczenie (opcjonalne)") },
                        placeholder = { Text("Np. Co jest przyczepione do kluczy?") },
                        supportingText = { Text("Pytanie zobaczy tylko osoba składająca roszczenie. Nie zdradzaj w nim odpowiedzi.") },
                        modifier = Modifier.fillMaxWidth(),
                    )
                } else {
                    OutlinedTextField(
                        value = d.secretDetails,
                        onValueChange = { v -> vm.edit { it.copy(secretDetails = v.take(500)) } },
                        label = { Text("Prywatna notatka (np. numer seryjny, zawartość)") },
                        supportingText = { Text("Przyda się, gdy będziesz odpowiadać znalazcy na pytanie weryfikacyjne.") },
                        minLines = 2,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }
        Spacer(Modifier.height(16.dp))
    }
}

@Composable
private fun ReviewStep(vm: CreateVM, ui: CreateUi, meta: Meta?) {
    val d = ui.draft
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("Sprawdź, co zobaczą inni", style = MaterialTheme.typography.headlineSmall)
        Surface(color = MaterialTheme.colorScheme.surfaceContainerLowest, shape = MaterialTheme.shapes.medium) {
            Column(Modifier.padding(14.dp).semantics(mergeDescendants = true) { contentDescription = "Dane publiczne" }) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.Public, null, tint = MaterialTheme.colorScheme.tertiary)
                    Spacer(Modifier.width(8.dp))
                    Text("Publiczne", style = MaterialTheme.typography.titleSmall)
                }
                Spacer(Modifier.height(6.dp))
                Text(d.title.ifBlank { suggestTitle(d, meta) }, style = MaterialTheme.typography.titleMedium)
                Text(listOfNotNull(meta?.category(d.category)?.label, d.attributes["subtype"]).joinToString(" › "), style = MaterialTheme.typography.bodyMedium)
                if (d.colors.isNotEmpty()) Text("Kolor: " + d.colors.mapNotNull { meta?.color(it)?.label }.joinToString(), style = MaterialTheme.typography.bodyMedium)
                if (d.description.isNotBlank()) Text(d.description, style = MaterialTheme.typography.bodyMedium)
                Text("Zdjęcia: ${d.photoPaths.size}", style = MaterialTheme.typography.bodyMedium)
                Text("Obszar: ${d.areaLabel.ifBlank { "Polska" }} (ok. 500 m, bez dokładnego punktu)", style = MaterialTheme.typography.bodyMedium)
                Text("Czas: " + Format.window(d.fromIso ?: "", d.toIso ?: ""), style = MaterialTheme.typography.bodyMedium)
                if (d.kind == "found") holdingLabel(d.holding)?.let { Text("Przedmiot: $it" + (if (d.holdingNote.isNotBlank()) " — ${d.holdingNote}" else ""), style = MaterialTheme.typography.bodyMedium) }
            }
        }
        Surface(color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.5f), shape = MaterialTheme.shapes.medium) {
            Column(Modifier.padding(14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.Lock, null, tint = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.width(8.dp))
                    Text("Prywatne (tylko Ty)", style = MaterialTheme.typography.titleSmall)
                }
                PrivacyLine("Dokładne miejsce na mapie" + (if (d.locationSource == "gps") " (z GPS)" else " (wskazane ręcznie)"))
                if (d.secretDetails.isNotBlank()) PrivacyLine(if (d.kind == "found") "Ukryty szczegół: ${d.secretDetails}" else "Notatka: ${d.secretDetails}")
                if (d.claimQuestion.isNotBlank()) PrivacyLine("Pytanie (widzi tylko osoba składająca roszczenie): ${d.claimQuestion}")
                PrivacyLine("Twoja tożsamość — kontakt odbywa się w aplikacji")
            }
        }
        if (d.kind == "found" && d.secretDetails.isBlank()) {
            InfoCard("Dodaj ukryty szczegół", "Bez niego trudniej będzie odróżnić właściciela od osoby zgadującej. Wróć do kroku „Opis”.", Tone.Warning)
        }
        if (d.photoPaths.isNotEmpty()) {
            Row(
                Modifier.fillMaxWidth().selectable(ui.photoConfirmed, role = Role.Checkbox) { vm.ui.update { it.copy(photoConfirmed = !it.photoConfirmed) } },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Checkbox(checked = ui.photoConfirmed, onCheckedChange = null)
                Spacer(Modifier.width(8.dp))
                Text("Sprawdziłem zdjęcia — nie widać na nich dokumentów, adresów ani twarzy.", style = MaterialTheme.typography.bodyMedium)
            }
        }
        InfoCard(
            null,
            "Zgłoszenie będzie aktywne ${meta?.retention?.activeDays ?: 60} dni (możesz je przedłużyć, edytować lub usunąć w „Moje sprawy”).",
            Tone.Info,
        )
        Spacer(Modifier.height(16.dp))
    }
}
