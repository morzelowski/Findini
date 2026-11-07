package pl.findini.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material.icons.outlined.TravelExplore
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import kotlinx.coroutines.launch
import pl.findini.app.app
import pl.findini.app.data.AppError
import pl.findini.app.data.Case
import pl.findini.app.data.MatchesResponse
import pl.findini.app.data.Outcome
import pl.findini.app.data.Report
import pl.findini.app.data.ResolveIn
import pl.findini.app.ui.components.EmptyState
import pl.findini.app.ui.components.ErrorState
import pl.findini.app.ui.components.InfoCard
import pl.findini.app.ui.components.KeyValue
import pl.findini.app.ui.components.LoadingBox
import pl.findini.app.ui.components.ReportCard
import pl.findini.app.ui.components.SectionTitle
import pl.findini.app.ui.components.Tone
import pl.findini.app.util.Format

@Composable
fun MyReportScreen(nav: NavController, id: String, snackbar: SnackbarHostState) {
    val context = LocalContext.current
    val repo = context.app.repo
    val meta by repo.meta.collectAsState()
    val scope = rememberCoroutineScope()
    var report by remember { mutableStateOf<Report?>(null) }
    var matches by remember { mutableStateOf<MatchesResponse?>(null) }
    var claims by remember { mutableStateOf<List<Case>?>(null) }
    var error by remember { mutableStateOf<AppError?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    var confirm by remember { mutableStateOf<String?>(null) }
    var askNotif by remember { mutableStateOf(false) }

    LaunchedEffect(id, reload) {
        error = null
        when (val r = repo.private { report(id) }) {
            is Outcome.Ok -> {
                report = r.value
                if (r.value.private == null) { error = AppError(AppError.Kind.NotFound, "To nie jest Twoje zgłoszenie."); return@LaunchedEffect }
                (repo.private { matches(id) } as? Outcome.Ok)?.let { matches = it.value }
                if (r.value.isFound) (repo.private { reportClaims(id) } as? Outcome.Ok)?.let { claims = it.value.items }
                if (!repo.notificationsAsked && android.os.Build.VERSION.SDK_INT >= 33) askNotif = true
            }
            is Outcome.Err -> error = r.error
        }
    }
    NotificationPermissionAsk(askNotif) { askNotif = false; repo.notificationsAsked = true }

    fun act(block: suspend () -> Outcome<*>, ok: String) {
        scope.launch {
            when (val r = block()) {
                is Outcome.Ok -> { snackbar.showSnackbar(ok); reload++ }
                is Outcome.Err -> snackbar.showSnackbar(r.error.message)
            }
        }
    }

    ScreenScaffold(
        title = "Twoje zgłoszenie",
        onBack = { if (!nav.popBackStack()) nav.navigate("mine") },
        actions = {
            report?.let { r ->
                IconButton(onClick = { shareReport(context, repo.baseUrl, r) }) { Icon(Icons.Outlined.Share, "Udostępnij link") }
                if (r.status == "active" || r.status == "reserved") {
                    IconButton(onClick = { nav.navigate("create?kind=${r.kind}&edit=${r.id}") }) { Icon(Icons.Outlined.Edit, "Edytuj") }
                }
            }
        },
    ) { mod ->
        when {
            error != null -> ErrorState(error!!, onRetry = { reload++ }, modifier = mod)
            report == null -> LoadingBox(modifier = mod)
            else -> {
                val r = report!!
                ReportBody(r, meta, repo::absolute, mod) {
                    OwnerPanel(r, matches, claims, nav, onAction = { confirm = it })
                }
            }
        }
    }

    confirm?.let { action ->
        val r = report ?: return@let
        val (title, body, label) = when (action) {
            "withdraw" -> Triple("Usunąć zgłoszenie?", "Zgłoszenie zniknie z wyszukiwania, zdjęcia zostaną usunięte, a otwarte roszczenia zamknięte. Tego nie da się cofnąć.", "Usuń")
            "resolve_lost" -> Triple("Odnalazłeś swoją rzecz?", "Zamkniemy zgłoszenie i przestaniemy szukać dopasowań. Super!", "Tak, odnalazłem")
            "resolve_found" -> Triple("Zamknąć bez roszczenia?", "Np. oddałeś rzecz do biura rzeczy znalezionych albo właściciel odebrał ją poza aplikacją. Otwarte roszczenia zostaną zamknięte.", "Zamknij")
            else -> Triple("Odnowić zgłoszenie?", "Zgłoszenie znowu będzie aktywne przez ${meta?.retention?.activeDays ?: 60} dni.", "Odnów")
        }
        AlertDialog(
            onDismissRequest = { confirm = null },
            title = { Text(title) },
            text = { Text(body) },
            confirmButton = {
                Button(onClick = {
                    confirm = null
                    when (action) {
                        "withdraw" -> scope.launch {
                            when (val res = repo.private { withdrawReport(r.id) }) {
                                is Outcome.Ok -> { snackbar.showSnackbar("Zgłoszenie usunięte"); nav.popBackStack() }
                                is Outcome.Err -> snackbar.showSnackbar(res.error.message)
                            }
                        }
                        "resolve_lost" -> act({ repo.private { resolveReport(r.id, ResolveIn("owner_found")) } }, "Zamknięto — cieszymy się razem z Tobą!")
                        "resolve_found" -> act({ repo.private { resolveReport(r.id, ResolveIn("returned_outside_app")) } }, "Zgłoszenie zamknięte")
                        else -> act({ repo.private { renewReport(r.id) } }, "Zgłoszenie odnowione")
                    }
                }) { Text(label) }
            },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text("Anuluj") } },
        )
    }
}

@Composable
private fun OwnerPanel(r: Report, matches: MatchesResponse?, claims: List<Case>?, nav: NavController, onAction: (String) -> Unit) {
    val repo = LocalContext.current.app.repo
    val meta by repo.meta.collectAsState()
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (r.hidden) InfoCard("Zgłoszenie ukryte przez moderację", "Nie jest widoczne publicznie. Jeśli to pomyłka — usuń je i dodaj ponownie bez spornych treści.", Tone.Warning)
        if (r.status == "resolved") InfoCard("Sprawa zakończona", "Dziękujemy, że korzystasz z Findini.", Tone.Success)
        if (r.status == "expired") InfoCard("Zgłoszenie wygasło", "Nie jest już widoczne w wyszukiwaniu.", Tone.Info) { TextButton(onClick = { onAction("renew") }) { Text("Odnów") } }

        r.private?.let { p ->
            Surface(color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.5f), shape = MaterialTheme.shapes.medium) {
                Column(Modifier.padding(12.dp)) {
                    SectionTitle("Widoczne tylko dla Ciebie")
                    KeyValue("Dokładne miejsce", "%.5f, %.5f".format(java.util.Locale.US, p.exactLat, p.exactLon) + (p.accuracyM?.let { " (±$it m, GPS)" } ?: if (p.locationSource == "map") " (wskazane ręcznie)" else ""))
                    if (p.uncertaintyM > 0) KeyValue("Niepewność", Format.radius(p.uncertaintyM))
                    p.secretDetails?.let { KeyValue(if (r.isFound) "Ukryty szczegół" else "Notatka", it) }
                    p.claimQuestion?.let { KeyValue("Pytanie", it) }
                    r.expiresAt?.let { e -> Format.parse(e)?.let { KeyValue("Aktywne do", Format.day(it)) } }
                }
            }
        }
        val indexed = r.photoStatus.orEmpty()
        if (indexed.isNotEmpty()) {
            val ready = indexed.count { it.embeddingStatus == "ready" }
            InfoCard(
                null,
                if (ready == indexed.size) "Zdjęcia przeanalizowane — zgłoszenie bierze udział w wyszukiwaniu zdjęciem."
                else if (indexed.any { it.embeddingStatus == "failed" }) "Nie udało się przeanalizować zdjęcia. Wyszukiwanie tekstem i filtrami działa normalnie."
                else "Analiza zdjęć trwa (kolejka w tle). Wyszukiwanie filtrami działa już teraz.",
                Tone.Info,
                Icons.Outlined.AutoAwesome,
            )
        }

        if (r.isFound) {
            SectionTitle("Roszczenia (${claims?.size ?: 0})")
            when {
                claims == null -> LoadingBox()
                claims.isEmpty() -> Text(
                    "Nikt jeszcze nie zgłosił, że to jego rzecz. Udostępnij link w lokalnej grupie, na uczelni lub w budynku, gdzie znalazłeś przedmiot.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                else -> claims.forEach { c -> CaseRow(c) { nav.navigate("case/${c.id}") } }
            }
        }

        SectionTitle(if (r.isFound) "Pasujące zgłoszenia zgub" else "Możliwe dopasowania wśród znalezionych")
        when {
            matches == null -> LoadingBox("Szukam dopasowań…")
            matches.strong.isEmpty() && matches.possible.isEmpty() -> EmptyState(
                Icons.Outlined.TravelExplore,
                "Brak przekonujących dopasowań",
                (matches.notice ?: "") + if (matches.weakCount > 0) " Pominięto ${matches.weakCount} słabo pasujących." else "",
            )
            else -> {
                if (matches.strong.isNotEmpty()) {
                    Text("Mocne dopasowania — wiele sygnałów się zgadza", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                    matches.strong.forEach { m -> ReportCard(m, meta, repo::absolute, onClick = { nav.navigate("report/${m.id}") }) }
                }
                if (matches.possible.isNotEmpty()) {
                    Text("Możliwe — sprawdź szczegóły", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    matches.possible.forEach { m -> ReportCard(m, meta, repo::absolute, onClick = { nav.navigate("report/${m.id}") }) }
                }
                Text(
                    "Dopasowanie to podpowiedź, nie dowód. Podobne rzeczy bywają różne — " +
                        if (r.isFound) "właściciel musi złożyć roszczenie." else "otwórz zgłoszenie i złóż roszczenie, a znalazca zdecyduje.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        HorizontalDivider()
        if (r.status == "active") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedButton(onClick = { onAction(if (r.isFound) "resolve_found" else "resolve_lost") }, modifier = Modifier.weight(1f)) {
                    Text(if (r.isFound) "Zamknij sprawę" else "Odnalazłem!")
                }
                OutlinedButton(onClick = { onAction("withdraw") }, modifier = Modifier.weight(1f)) { Text("Usuń") }
            }
        } else if (r.status != "reserved") {
            OutlinedButton(onClick = { onAction("withdraw") }, modifier = Modifier.fillMaxWidth()) { Text("Usuń zgłoszenie i zdjęcia") }
        }
    }
}

@Composable
fun NotificationPermissionAsk(show: Boolean, done: () -> Unit) {
    if (!show || android.os.Build.VERSION.SDK_INT < 33) return
    val launcher = androidx.activity.compose.rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.RequestPermission(),
    ) { done() }
    AlertDialog(
        onDismissRequest = done,
        title = { Text("Powiadomić Cię o dopasowaniach?") },
        text = { Text("Co ok. 30 minut sprawdzimy nowe zgłoszenia pasujące do Twojego i wiadomości w sprawach. Bez śledzenia lokalizacji.") },
        confirmButton = { Button(onClick = { launcher.launch(android.Manifest.permission.POST_NOTIFICATIONS) }) { Text("Tak, powiadamiaj") } },
        dismissButton = { TextButton(onClick = done) { Text("Nie teraz") } },
    )
}
