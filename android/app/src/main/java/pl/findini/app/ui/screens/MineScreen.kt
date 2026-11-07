package pl.findini.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material.icons.outlined.Forum
import androidx.compose.material.icons.outlined.Inventory2
import androidx.compose.material.icons.outlined.Key
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.Badge
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.PrimaryTabRow
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import pl.findini.app.app
import pl.findini.app.data.AppError
import pl.findini.app.data.Case
import pl.findini.app.data.MeResponse
import pl.findini.app.data.Outcome
import pl.findini.app.data.Report
import pl.findini.app.ui.components.EmptyState
import pl.findini.app.ui.components.ErrorState
import pl.findini.app.ui.components.InfoCard
import pl.findini.app.ui.components.KindBadge
import pl.findini.app.ui.components.LoadingBox
import pl.findini.app.ui.components.ReportCard
import pl.findini.app.ui.components.Tone
import pl.findini.app.util.Format

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MineScreen(nav: NavController) {
    val context = LocalContext.current
    val repo = context.app.repo
    val meta by repo.meta.collectAsState()
    var tab by remember { mutableIntStateOf(0) }
    var me by remember { mutableStateOf<MeResponse?>(null) }
    var reports by remember { mutableStateOf<List<Report>?>(null) }
    var cases by remember { mutableStateOf<List<Case>?>(null) }
    var error by remember { mutableStateOf<AppError?>(null) }
    var refreshing by remember { mutableStateOf(false) }
    var reload by remember { mutableIntStateOf(0) }

    LaunchedEffect(reload) {
        if (!repo.hasSession) {
            reports = emptyList(); cases = emptyList(); refreshing = false
            return@LaunchedEffect
        }
        error = null
        coroutineScope {
            val a = async { repo.private { me() } }
            val b = async { repo.private { myReports() } }
            val c = async { repo.private { myCases() } }
            when (val r = a.await()) { is Outcome.Ok -> me = r.value; is Outcome.Err -> error = r.error }
            when (val r = b.await()) { is Outcome.Ok -> reports = r.value.items; is Outcome.Err -> error = r.error }
            when (val r = c.await()) { is Outcome.Ok -> cases = r.value.items; is Outcome.Err -> error = r.error }
        }
        refreshing = false
    }

    Column(Modifier.fillMaxSize().statusBarsPadding()) {
        Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Moje sprawy", style = MaterialTheme.typography.headlineMedium)
                me?.let {
                    Text("Działasz jako „${it.guest.alias}” — pseudonim widoczny tylko dla Ciebie", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            IconButton(onClick = { nav.navigate("settings") }) { Icon(Icons.Outlined.Settings, "Ustawienia, kod odzyskiwania, usuwanie danych") }
        }
        me?.let { m ->
            Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Stat(Icons.Outlined.Favorite, m.stats.heartsReceived.toString(), "podziękowań", Modifier.weight(1f))
                Stat(Icons.Outlined.Inventory2, m.stats.itemsReturned.toString(), "zwróconych", Modifier.weight(1f))
                Stat(Icons.Outlined.Forum, m.unread.toString(), "nieprzeczytanych", Modifier.weight(1f))
            }
            if (!m.hasRecoveryCode) {
                InfoCard(
                    "Zabezpiecz dostęp",
                    "Bez konta Twoje zgłoszenia są na tym telefonie. Zapisz kod odzyskiwania, aby nie stracić ich po zmianie telefonu.",
                    Tone.Warning,
                    Icons.Outlined.Key,
                    modifier = Modifier.padding(horizontal = 16.dp),
                ) { TextButton(onClick = { nav.navigate("settings") }) { Text("Utwórz kod odzyskiwania") } }
            }
        }
        PrimaryTabRow(selectedTabIndex = tab, containerColor = MaterialTheme.colorScheme.background) {
            Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Zgłoszenia (${reports?.size ?: 0})") })
            Tab(
                selected = tab == 1,
                onClick = { tab = 1 },
                text = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Roszczenia i rozmowy")
                        val unread = cases?.count { it.unread > 0 } ?: 0
                        if (unread > 0) { Spacer(Modifier.width(6.dp)); Badge { Text("$unread") } }
                    }
                },
            )
        }
        PullToRefreshBox(isRefreshing = refreshing, onRefresh = { refreshing = true; reload++ }, modifier = Modifier.weight(1f)) {
            LazyColumn(
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.fillMaxSize(),
            ) {
                when {
                    error != null && reports == null -> item { ErrorState(error!!, onRetry = { reload++ }) }
                    tab == 0 && reports == null -> item { LoadingBox() }
                    tab == 0 && reports!!.isEmpty() -> item {
                        EmptyState(Icons.Outlined.Inventory2, "Nie masz jeszcze zgłoszeń", "Zgubiłeś lub znalazłeś coś? Zgłoszenie zajmuje około minuty i nie wymaga konta.") {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button(onClick = { nav.navigate("create?kind=found") }) { Text("Znalazłem") }
                                OutlinedButton(onClick = { nav.navigate("create?kind=lost") }) { Text("Zgubiłem") }
                            }
                            TextButton(onClick = { nav.navigate("recovery") }) { Text("Mam kod odzyskiwania z innego telefonu") }
                        }
                    }
                    tab == 0 -> items(reports!!, key = { it.id }) { r ->
                        Column {
                            ReportCard(r, meta, repo::absolute, onClick = { nav.navigate("myreport/${r.id}") }, showReasons = false)
                            r.claims?.let { c ->
                                if (c.pending > 0) Text(
                                    "Nowe roszczenia czekają na decyzję: ${c.pending}",
                                    style = MaterialTheme.typography.labelLarge,
                                    color = MaterialTheme.colorScheme.secondary,
                                    modifier = Modifier.padding(start = 8.dp, top = 4.dp),
                                )
                            }
                        }
                    }
                    cases == null -> item { LoadingBox() }
                    cases!!.isEmpty() -> item {
                        EmptyState(Icons.Outlined.Forum, "Brak spraw", "Tu pojawią się roszczenia do Twoich znalezisk i Twoje roszczenia do cudzych — razem z prywatną rozmową.")
                    }
                    else -> items(cases!!, key = { it.id }) { c -> CaseRow(c) { nav.navigate("case/${c.id}") } }
                }
            }
        }
    }
}

@Composable
private fun Stat(icon: androidx.compose.ui.graphics.vector.ImageVector, value: String, label: String, modifier: Modifier) {
    Surface(color = MaterialTheme.colorScheme.surfaceContainer, shape = MaterialTheme.shapes.medium, modifier = modifier.semantics(mergeDescendants = true) { contentDescription = "$value $label" }) {
        Column(Modifier.padding(12.dp)) {
            Icon(icon, null, tint = MaterialTheme.colorScheme.secondary, modifier = Modifier.size(20.dp))
            Text(value, style = MaterialTheme.typography.titleLarge)
            Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
fun CaseRow(c: Case, onClick: () -> Unit) {
    Card(onClick = onClick, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                KindBadge(c.report.kind)
                Spacer(Modifier.width(8.dp))
                Text(if (c.isFinder) "Jesteś znalazcą" else "Odbierasz", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(1f))
                if (c.unread > 0) Badge { Text("${c.unread}") }
            }
            Spacer(Modifier.height(6.dp))
            Text(c.report.title, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(c.statusLabel, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary)
            c.createdAt?.let { Text("Złożone " + Format.ago(it), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}
