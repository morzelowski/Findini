package pl.findini.app.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.ImageSearch
import androidx.compose.material.icons.outlined.PhotoLibrary
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.navigation.NavController
import coil3.compose.AsyncImage
import kotlinx.coroutines.launch
import pl.findini.app.app
import pl.findini.app.data.AppError
import pl.findini.app.data.Outcome
import pl.findini.app.data.PhotoSearchResponse
import pl.findini.app.ui.components.EmptyState
import pl.findini.app.ui.components.ErrorState
import pl.findini.app.ui.components.InfoCard
import pl.findini.app.ui.components.LoadingBox
import pl.findini.app.ui.components.ReportCard
import pl.findini.app.ui.components.Tone

@Composable
fun PhotoSearchScreen(nav: NavController) {
    val context = LocalContext.current
    val repo = context.app.repo
    val meta by repo.meta.collectAsState()
    val scope = rememberCoroutineScope()
    var kind by remember { mutableStateOf("found") }
    var preview by remember { mutableStateOf<Any?>(null) }
    var bytes by remember { mutableStateOf<ByteArray?>(null) }
    var result by remember { mutableStateOf<PhotoSearchResponse?>(null) }
    var error by remember { mutableStateOf<AppError?>(null) }
    var loading by remember { mutableStateOf(false) }
    var camera by remember { mutableStateOf(false) }

    fun run(b: ByteArray) {
        loading = true; error = null; result = null
        scope.launch {
            when (val r = repo.searchByPhoto(b, kind)) {
                is Outcome.Ok -> result = r.value
                is Outcome.Err -> error = r.error
            }
            loading = false
        }
    }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) scope.launch {
            val b = pl.findini.app.util.Images.prepare(context, uri)
            if (b != null) { preview = uri; bytes = b; run(b) }
        }
    }
    val camPerm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (ok) camera = true }

    if (camera) {
        BackHandler { camera = false }
        CameraCapture(onCaptured = { f ->
            camera = false
            scope.launch {
                val b = pl.findini.app.util.Images.prepare(f)
                f.delete() // zdjęcie zapytania nie zostaje na telefonie
                if (b != null) { preview = b; bytes = b; run(b) }
            }
        }, onClose = { camera = false })
        return
    }

    ScreenScaffold(title = "Szukaj zdjęciem", onBack = { nav.popBackStack() }) { mod ->
        LazyColumn(mod.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                InfoCard(
                    "Jak to działa",
                    "Lokalny model analizy obrazu porównuje Twoje zdjęcie ze zdjęciami zgłoszeń w Findini (nie w całym internecie). Wiele rzeczy wygląda podobnie — wynik to podpowiedź, a nie potwierdzenie. Zdjęcie zapytania nie jest zapisywane.",
                    Tone.Info,
                    Icons.Outlined.AutoAwesome,
                )
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(selected = kind == "found", onClick = { kind = "found"; bytes?.let { run(it) } }, label = { Text("Wśród znalezionych") })
                    FilterChip(selected = kind == "lost", onClick = { kind = "lost"; bytes?.let { run(it) } }, label = { Text("Wśród zgubionych") })
                }
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = {
                        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) camera = true
                        else camPerm.launch(Manifest.permission.CAMERA)
                    }, modifier = Modifier.weight(1f)) { Icon(Icons.Outlined.CameraAlt, null); Spacer(Modifier.width(6.dp)); Text("Aparat") }
                    OutlinedButton(onClick = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }, modifier = Modifier.weight(1f)) {
                        Icon(Icons.Outlined.PhotoLibrary, null); Spacer(Modifier.width(6.dp)); Text("Galeria")
                    }
                }
            }
            preview?.let { p ->
                item { AsyncImage(p, "Zdjęcie zapytania", contentScale = ContentScale.Crop, modifier = Modifier.fillMaxWidth().height(180.dp).clip(MaterialTheme.shapes.large)) }
            }
            when {
                loading -> item { LoadingBox("Porównuję zdjęcia…") }
                error != null -> item {
                    if (error!!.kind == AppError.Kind.AiUnavailable) {
                        EmptyState(Icons.Outlined.ImageSearch, "Analiza zdjęć chwilowo niedostępna", error!!.message) {
                            Button(onClick = { nav.popBackStack() }) { Text("Szukaj filtrami") }
                        }
                    } else ErrorState(error!!, onRetry = bytes?.let { b -> { run(b) } })
                }
                result != null -> {
                    val r = result!!
                    item {
                        InfoCard(
                            if (r.noConvincingMatch) "Brak wyraźnego dopasowania" else "Sprawdź pierwszy wynik",
                            r.notice,
                            if (r.noConvincingMatch) Tone.Warning else Tone.Success,
                        )
                    }
                    r.querySuggestion?.let { s ->
                        item {
                            Text(
                                "Na Twoim zdjęciu model widzi: " + listOfNotNull(meta?.category(s.category)?.label, s.subtype).joinToString(" › ") +
                                    (if (s.colorsPl.isNotEmpty()) " · " + s.colorsPl.joinToString() else ""),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    if (r.items.isEmpty()) item {
                        EmptyState(Icons.Outlined.ImageSearch, "Nic podobnego", "Dodaj zgłoszenie zguby ze zdjęciem — porównamy je z nowymi znaleziskami.") {
                            Button(onClick = { nav.navigate("create?kind=lost") }) { Text("Dodaj zgłoszenie zguby") }
                        }
                    }
                    items(r.items, key = { it.id }) { rep ->
                        val label = when (rep.match?.visual) {
                            "distinct" -> "Wyróżnia się podobieństwem"
                            "similar" -> "Podobne wizualnie"
                            else -> "Zbliżone"
                        }
                        Text(label, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(top = 4.dp))
                        ReportCard(rep, meta, repo::absolute, onClick = { nav.navigate(if (rep.isMine) "myreport/${rep.id}" else "report/${rep.id}") })
                    }
                }
                else -> item {
                    EmptyState(Icons.Outlined.ImageSearch, "Dodaj zdjęcie", "Najlepiej zdjęcie Twojej rzeczy z bliska, na prostym tle. Może być starsze zdjęcie z galerii.")
                }
            }
            item { Spacer(Modifier.size(16.dp)) }
        }
    }
}
