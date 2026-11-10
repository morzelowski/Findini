package pl.findini.app.ui.screens

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Flag
import androidx.compose.material.icons.outlined.Inventory
import androidx.compose.material.icons.outlined.Place
import androidx.compose.material.icons.outlined.Schedule
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material.icons.outlined.Shield
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
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
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import coil3.compose.AsyncImage
import kotlinx.coroutines.launch
import pl.findini.app.app
import pl.findini.app.data.AbuseIn
import pl.findini.app.data.AppError
import pl.findini.app.data.Outcome
import pl.findini.app.data.Report
import pl.findini.app.ui.components.AreaMap
import pl.findini.app.ui.components.ColorDots
import pl.findini.app.ui.components.ErrorState
import pl.findini.app.ui.components.InfoCard
import pl.findini.app.ui.components.KeyValue
import pl.findini.app.ui.components.KindBadge
import pl.findini.app.ui.components.LoadingBox
import pl.findini.app.ui.components.MetaLine
import pl.findini.app.ui.components.PhotoOrIcon
import pl.findini.app.ui.components.SectionTitle
import pl.findini.app.ui.components.StatusPill
import pl.findini.app.ui.components.Tone
import pl.findini.app.util.Format
import androidx.compose.foundation.clickable

fun holdingLabel(h: String?): String? = when (h) {
    "with_finder" -> "U znalazcy"
    "at_place" -> "Zostawiony w miejscu znalezienia (np. u obsługi, w portierni)"
    "office" -> "Oddany do biura rzeczy znalezionych / na policję"
    else -> null
}

fun shareReport(context: android.content.Context, baseUrl: String, r: Report) {
    val kind = if (r.isFound) "Znaleziono" else "Zgubiono"
    val text = "$kind: ${r.title} (${r.area.label ?: "Polska"}). Szczegóły i prywatny kontakt w Findini: " +
        baseUrl.trimEnd('/') + "/r/${r.id}"
    val send = Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"
        putExtra(Intent.EXTRA_TEXT, text)
    }
    context.startActivity(Intent.createChooser(send, "Udostępnij zgłoszenie"))
}

@Composable
fun DetailScreen(nav: NavController, id: String, snackbar: SnackbarHostState) {
    val context = LocalContext.current
    val repo = context.app.repo
    var report by remember { mutableStateOf<Report?>(null) }
    var error by remember { mutableStateOf<AppError?>(null) }
    var showAbuse by remember { mutableStateOf(false) }
    var reload by remember { mutableIntStateOf(0) }
    val meta by repo.meta.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(id, reload) {
        error = null
        when (val r = repo.public { report(id) }) {
            is Outcome.Ok -> {
                if (r.value.isMine) {
                    nav.navigate("myreport/$id") { popUpTo("report/$id") { inclusive = true } }
                } else report = r.value
            }
            is Outcome.Err -> error = r.error
        }
    }

    ScreenScaffold(
        title = report?.let { if (it.isFound) "Znaleziona rzecz" else "Zgubiona rzecz" } ?: "Zgłoszenie",
        onBack = { nav.popBackStack() },
        actions = {
            report?.let { r ->
                IconButton(onClick = { shareReport(context, repo.baseUrl, r) }) { Icon(Icons.Outlined.Share, "Udostępnij") }
                IconButton(onClick = { showAbuse = true }) { Icon(Icons.Outlined.Flag, "Zgłoś nadużycie") }
            }
        },
        bottomBar = {
            report?.let { r ->
                BottomActions {
                    if (r.isFound) {
                        Button(shape = MaterialTheme.shapes.small, onClick = { nav.navigate("claim/${r.id}") }, modifier = Modifier.fillMaxWidth()) {
                            Text("To moje — złóż prywatne roszczenie")
                        }
                        Text(
                            "Znalazca zobaczy Twoją odpowiedź na pytanie o ukryty szczegół i zdecyduje o wydaniu.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    } else {
                        Button(shape = MaterialTheme.shapes.small, onClick = { nav.navigate("create?kind=found&from=${r.id}") }, modifier = Modifier.fillMaxWidth()) {
                            Text("Znalazłem coś podobnego")
                        }
                        Text(
                            "Dodasz zgłoszenie znalezienia — właściciel zobaczy je w dopasowaniach i złoży prywatne roszczenie.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        },
    ) { mod ->
        when {
            error != null -> ErrorState(error!!, onRetry = { reload++ }, modifier = mod)
            report == null -> LoadingBox(modifier = mod)
            else -> ReportBody(report!!, meta, repo::absolute, mod)
        }
    }

    if (showAbuse && report != null) {
        AbuseDialog(
            onDismiss = { showAbuse = false },
            onSend = { reason, details ->
                showAbuse = false
                scope.launch {
                    when (val r = repo.private { reportAbuse(AbuseIn("report", report!!.id, reason, details)) }) {
                        is Outcome.Ok -> snackbar.showSnackbar(r.value.message)
                        is Outcome.Err -> snackbar.showSnackbar(r.error.message)
                    }
                }
            },
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ReportBody(r: Report, meta: pl.findini.app.data.Meta?, imageUrl: (String) -> String, modifier: Modifier, ownerExtras: @Composable () -> Unit = {}) {
    var photoPage by remember { mutableStateOf<Int?>(null) }
    photoPage?.let { page ->
        pl.findini.app.ui.components.PhotoViewer(r.photos, page, imageUrl) { photoPage = null }
    }
    Column(modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        if (r.photos.isNotEmpty()) {
            val pager = rememberPagerState(pageCount = { r.photos.size })
            Box {
                HorizontalPager(pager, modifier = Modifier.fillMaxWidth().aspectRatio(4f / 3f)) { i ->
                    AsyncImage(
                        model = imageUrl(r.photos[i].url),
                        contentDescription = "Zdjęcie ${i + 1} z ${r.photos.size}: ${r.title}",
                        contentScale = ContentScale.Fit,
                        modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surfaceContainerLow).clickable { photoPage = i },
                    )
                }
                if (r.photos.size > 1) {
                    Row(Modifier.align(Alignment.BottomCenter).padding(8.dp)) {
                        repeat(r.photos.size) { i ->
                            Box(
                                Modifier.padding(3.dp).size(8.dp).clip(CircleShape)
                                    .background(if (pager.currentPage == i) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surface),
                            )
                        }
                    }
                }
            }
            TextButton(onClick = { photoPage = pager.currentPage }, modifier = Modifier.align(Alignment.End)) { Text("Powiększ zdjęcie") }
        } else {
            PhotoOrIcon(r, imageUrl, Modifier.fillMaxWidth().height(140.dp).padding(16.dp))
        }
        Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                KindBadge(r.kind)
                StatusPill(r.status)
                Text(r.categoryLabel, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Text(r.title, style = MaterialTheme.typography.headlineSmall)
            MetaLine(Icons.Outlined.Schedule, (if (r.isFound) "Znaleziono: " else "Zgubiono: ") + Format.window(r.occurredFrom, r.occurredTo))
            MetaLine(Icons.Outlined.Place, (r.area.label ?: "Polska") + " · obszar ok. " + Format.radius(r.area.radiusM))
            r.publishedAt?.let { Text("Dodano " + Format.ago(it), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            ColorDots(r.colors, meta)
            if (r.description.isNotBlank()) {
                Spacer(Modifier.height(4.dp))
                Text(r.description, style = MaterialTheme.typography.bodyLarge)
            }
            if (r.attributes.isNotEmpty()) {
                SectionTitle("Cechy")
                r.attributes.forEach { KeyValue(it.label, it.text) }
            }
            if (r.isFound) {
                holdingLabel(r.holding)?.let { h ->
                    SectionTitle("Gdzie jest teraz przedmiot")
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.Inventory, null, tint = MaterialTheme.colorScheme.primary)
                        Spacer(Modifier.size(8.dp))
                        Text(h + (r.holdingNote?.let { " — $it" } ?: ""), style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
            ownerExtras()
            SectionTitle("Przybliżony obszar")
            AreaMap(Modifier.fillMaxWidth().height(200.dp).clip(MaterialTheme.shapes.medium), r.area.lat, r.area.lon, r.area.radiusM, r.kind)
            InfoCard(
                null,
                "Pokazujemy obszar ok. ${Format.radius(r.area.radiusM)}, nie dokładne miejsce. " +
                    if (r.isFound) "Szczegóły odbioru ustalicie w prywatnej rozmowie." else "Dokładne miejsce zna tylko osoba zgłaszająca.",
                Tone.Privacy,
            )
            InfoCard(
                "Bezpiecznie",
                "Findini nigdy nie wymaga opłat, przelewów ani kodów BLIK za zwrot. Nie podawaj adresu domowego — umawiajcie się w miejscu publicznym.",
                Tone.Warning,
                Icons.Outlined.Shield,
            )
            Spacer(Modifier.height(12.dp))
        }
    }
}

@Composable
fun AbuseDialog(onDismiss: () -> Unit, onSend: (String, String) -> Unit) {
    val reasons = listOf(
        "scam" to "Próba oszustwa / żądanie opłaty",
        "bait" to "Fałszywe ogłoszenie (przynęta)",
        "personal_data" to "Publikuje cudze dane osobowe",
        "stolen" to "Podejrzenie kradzieży",
        "offensive" to "Treści obraźliwe",
        "spam" to "Spam",
        "other" to "Inny powód",
    )
    var sel by remember { mutableStateOf("scam") }
    var details by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Zgłoś nadużycie") },
        text = {
            Column {
                reasons.forEach { (k, label) ->
                    Row(
                        Modifier.fillMaxWidth().selectable(sel == k, role = Role.RadioButton) { sel = k }.padding(vertical = 2.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        RadioButton(selected = sel == k, onClick = null)
                        Spacer(Modifier.size(8.dp))
                        Text(label, style = MaterialTheme.typography.bodyMedium)
                    }
                }
                OutlinedTextField(details, { details = it.take(500) }, label = { Text("Szczegóły (opcjonalnie)") }, minLines = 2)
                Text("Zgłoszenie trafi do moderatora. Po kilku zgłoszeniach ogłoszenie jest automatycznie ukrywane.", style = MaterialTheme.typography.bodySmall)
            }
        },
        confirmButton = { Button(shape = MaterialTheme.shapes.small, onClick = { onSend(sel, details) }) { Text("Wyślij") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Anuluj") } },
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun Chips(items: List<String>) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) { items.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall) } }
}

