package pl.findini.app.ui.screens

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.Clear
import androidx.compose.material.icons.outlined.Map
import androidx.compose.material.icons.outlined.MyLocation
import androidx.compose.material.icons.outlined.Place
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.SearchOff
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.ViewList
import androidx.compose.material.icons.outlined.VolunteerActivism
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import org.maplibre.android.geometry.LatLng
import pl.findini.app.app
import pl.findini.app.data.AppError
import pl.findini.app.data.AreaCell
import pl.findini.app.data.Outcome
import pl.findini.app.data.Repository
import pl.findini.app.data.Report
import pl.findini.app.data.SuggestionAction
import pl.findini.app.ui.components.Bbox
import pl.findini.app.ui.components.EmptyState
import pl.findini.app.ui.components.ErrorState
import pl.findini.app.ui.components.ExploreMap
import pl.findini.app.ui.components.InfoCard
import pl.findini.app.ui.components.LoadingBox
import pl.findini.app.ui.components.ReportCard
import pl.findini.app.ui.components.Tone
import pl.findini.app.ui.components.categoryIcon
import pl.findini.app.ui.components.parseHex
import pl.findini.app.ui.theme.LocalKindColors
import pl.findini.app.util.Format
import pl.findini.app.util.LocationHelper
import java.time.ZonedDateTime

data class PlaceFilter(val name: String, val lat: Double, val lon: Double, val radiusM: Int)

data class Filters(
    val kind: String? = "found",
    val category: String? = null,
    val subtype: String? = null,
    val colors: List<String> = emptyList(),
    val brand: String? = null,
    val q: String = "",
    val place: PlaceFilter? = null,
    val days: Int? = null,
    val dateFrom: String? = null,
    val dateTo: String? = null,
) {
    val activeCount: Int get() = listOfNotNull(category, colors.firstOrNull(), brand, place, days, dateFrom).size
}

data class HomeState(
    val filters: Filters = Filters(),
    val items: List<Report> = emptyList(),
    val nextCursor: String? = null,
    val loading: Boolean = false,
    val loadingMore: Boolean = false,
    val error: AppError? = null,
    val suggestions: List<SuggestionAction> = emptyList(),
    val understood: List<String> = emptyList(),
    val areas: List<AreaCell> = emptyList(),
    val mapError: String? = null,
)

class HomeVM(private val repo: Repository) : ViewModel() {
    val state = MutableStateFlow(HomeState())
    private var searchJob: Job? = null
    private var areasJob: Job? = null
    private var lastBbox: Bbox? = null

    init { search() }

    fun update(f: (Filters) -> Filters) {
        state.update { it.copy(filters = f(it.filters)) }
        search()
        lastBbox?.let { loadAreas(it) }
    }

    fun search() {
        searchJob?.cancel()
        searchJob = viewModelScope.launch {
            state.update { it.copy(loading = true, error = null) }
            val f = state.value.filters
            val r = fetch(f, null)
            state.update {
                when (r) {
                    is Outcome.Ok -> it.copy(loading = false, items = r.value.items, nextCursor = r.value.nextCursor, suggestions = r.value.suggestions)
                    is Outcome.Err -> it.copy(loading = false, error = r.error)
                }
            }
        }
    }

    fun loadMore() {
        val s = state.value
        val cursor = s.nextCursor ?: return
        if (s.loadingMore) return
        viewModelScope.launch {
            state.update { it.copy(loadingMore = true) }
            val r = fetch(s.filters, cursor)
            state.update {
                when (r) {
                    is Outcome.Ok -> it.copy(loadingMore = false, items = it.items + r.value.items, nextCursor = r.value.nextCursor)
                    is Outcome.Err -> it.copy(loadingMore = false, error = r.error)
                }
            }
        }
    }

    private suspend fun fetch(f: Filters, cursor: String?) = repo.public {
        val from = f.dateFrom ?: f.days?.let { Format.toUtcIso(ZonedDateTime.now(Format.zone).minusDays(it.toLong())) }
        search(
            kind = f.kind, category = f.category, subtype = f.subtype,
            colors = f.colors.joinToString(",").ifBlank { null }, brand = f.brand, q = f.q.ifBlank { null },
            lat = f.place?.lat, lon = f.place?.lon, radiusM = f.place?.radiusM,
            dateFrom = from, dateTo = f.dateTo, sort = if (f.q.isNotBlank()) "relevance" else if (f.place != null) "nearest" else "newest",
            cursor = cursor,
        )
    }

    /** Asystent: zamienia zdanie na filtry (reguły po stronie serwera, bez AI). Wynik jest edytowalny. */
    fun submitQuery(text: String) {
        if (text.isBlank()) {
            update { it.copy(q = "") }
            state.update { it.copy(understood = emptyList()) }
            return
        }
        viewModelScope.launch {
            when (val r = repo.public { parse(pl.findini.app.data.ParseIn(text)) }) {
                is Outcome.Ok -> {
                    val p = r.value
                    val recognized = p.category != null || p.colors.isNotEmpty() || p.place != null || p.dateFrom != null || p.kind != null
                    state.update { it.copy(understood = if (recognized) p.understood else emptyList()) }
                    update { f ->
                        if (!recognized) f.copy(q = text) else f.copy(
                            kind = p.kind ?: f.kind,
                            category = p.category ?: f.category,
                            subtype = p.subtype,
                            colors = p.colors.ifEmpty { f.colors },
                            brand = p.brand,
                            dateFrom = p.dateFrom,
                            dateTo = p.dateTo,
                            days = if (p.dateFrom != null) null else f.days,
                            place = p.place?.let { pl -> PlaceFilter(pl.name, pl.lat, pl.lon, pl.radiusM) } ?: f.place,
                            q = p.text.orEmpty(),
                        )
                    }
                }
                is Outcome.Err -> update { it.copy(q = text) }
            }
        }
    }

    fun clearAll() {
        state.update { it.copy(understood = emptyList()) }
        update { Filters(kind = it.kind) }
    }

    fun loadAreas(b: Bbox) {
        lastBbox = b
        areasJob?.cancel()
        areasJob = viewModelScope.launch {
            delay(250)
            val f = state.value.filters
            when (val r = repo.public { areas(b.toString(), f.kind, f.category) }) {
                is Outcome.Ok -> state.update { it.copy(areas = r.value.areas, mapError = null) }
                is Outcome.Err -> state.update { it.copy(mapError = r.error.message) }
            }
        }
    }

    fun applySuggestion(a: SuggestionAction) {
        when (a.action) {
            "expand_radius" -> update { f -> f.copy(place = f.place?.let { it.copy(radiusM = minOf(it.radiusM * 3, 15000)) }) }
            "expand_dates" -> update { it.copy(days = null, dateFrom = null, dateTo = null) }
            "clear_filters" -> update { it.copy(colors = emptyList(), brand = null, subtype = null) }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun HomeScreen(nav: NavController) {
    val context = LocalContext.current
    val repo = context.app.repo
    val vm: HomeVM = viewModel { HomeVM(repo) }
    val s by vm.state.collectAsState()
    val meta by repo.meta.collectAsState()
    val focus = LocalFocusManager.current
    var query by remember { mutableStateOf("") }
    var mapMode by remember { mutableStateOf(false) }
    var sheet by remember { mutableStateOf<String?>(null) }
    var cellSheet by remember { mutableStateOf<AreaCell?>(null) }
    val scope = rememberCoroutineScope()
    val listState = rememberLazyListState()
    val f = s.filters

    LaunchedEffect(listState) {
        snapshotFlow { listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }
            .collect { last -> if (last >= listState.layoutInfo.totalItemsCount - 3) vm.loadMore() }
    }

    val locationPerm = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { granted ->
        if (granted.values.any { it }) scope.launch {
            LocationHelper.currentFix(context)?.let { fix ->
                vm.update { it.copy(place = PlaceFilter("Moja okolica", fix.lat, fix.lon, it.place?.radiusM ?: 2000)) }
            }
        }
    }

    Column(Modifier.fillMaxSize().statusBarsPadding()) {
        // Nagłówek
        Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Findini", style = MaterialTheme.typography.headlineMedium, color = MaterialTheme.colorScheme.primary)
                Text(
                    "${meta?.pilot?.name ?: "Kraków"} · szukaj bez zakładania konta",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            IconButton(onClick = { nav.navigate("settings") }) { Icon(Icons.Outlined.Settings, "Ustawienia i prywatność") }
        }
        // Wyszukiwarka
        OutlinedTextField(
            value = query,
            onValueChange = { query = it },
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            placeholder = { Text("np. czarna czapka zgubiona wczoraj przy AGH") },
            leadingIcon = { Icon(Icons.Outlined.Search, null) },
            trailingIcon = {
                Row {
                    if (query.isNotEmpty()) IconButton(onClick = { query = ""; vm.submitQuery("") }) { Icon(Icons.Outlined.Clear, "Wyczyść") }
                    IconButton(onClick = { nav.navigate("photosearch") }) { Icon(Icons.Outlined.CameraAlt, "Szukaj zdjęciem") }
                }
            },
            singleLine = true,
            shape = MaterialTheme.shapes.extraLarge,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { focus.clearFocus(); vm.submitQuery(query) }),
        )
        if (s.understood.isNotEmpty()) {
            Surface(
                color = MaterialTheme.colorScheme.tertiaryContainer,
                shape = MaterialTheme.shapes.medium,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            ) {
                Column(Modifier.padding(12.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.AutoAwesome, null, Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Zrozumiałem tak — możesz to zmienić filtrami:", style = MaterialTheme.typography.labelLarge, modifier = Modifier.weight(1f))
                        TextButton(onClick = { vm.clearAll(); query = "" }) { Text("Wyczyść") }
                    }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        s.understood.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall) }
                    }
                }
            }
        }
        // Filtry
        Row(
            Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            listOf("found" to "Znalezione", "lost" to "Zgubione", null to "Wszystkie").forEach { (k, label) ->
                FilterChip(selected = f.kind == k, onClick = { vm.update { it.copy(kind = k) } }, label = { Text(label) })
            }
            FilterChip(
                selected = f.category != null,
                onClick = { sheet = "category" },
                label = { Text(meta?.category(f.category)?.label?.let { l -> f.subtype?.let { "$l: $it" } ?: l } ?: "Kategoria") },
                leadingIcon = { Icon(categoryIcon(f.category), null, Modifier.size(18.dp)) },
            )
            FilterChip(
                selected = f.colors.isNotEmpty(),
                onClick = { sheet = "color" },
                label = { Text(if (f.colors.isEmpty()) "Kolor" else f.colors.mapNotNull { meta?.color(it)?.label }.joinToString()) },
            )
            FilterChip(
                selected = f.days != null || f.dateFrom != null,
                onClick = { sheet = "time" },
                label = { Text(timeLabel(f)) },
            )
            FilterChip(
                selected = f.place != null,
                onClick = { sheet = "place" },
                label = { Text(f.place?.let { "${it.name} · ${Format.radius(it.radiusM)}" } ?: "Cały obszar") },
                leadingIcon = { Icon(Icons.Outlined.Place, null, Modifier.size(18.dp)) },
            )
            if (f.brand != null) FilterChip(selected = true, onClick = { vm.update { it.copy(brand = null) } }, label = { Text("Marka: ${f.brand} ✕") })
        }
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(
                when {
                    s.loading -> "Szukam…"
                    s.items.isEmpty() -> "Brak wyników"
                    else -> "Wyniki: ${s.items.size}${if (s.nextCursor != null) "+" else ""}"
                },
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.weight(1f),
            )
            SingleChoiceSegmentedButtonRow {
                SegmentedButton(
                    selected = !mapMode,
                    onClick = { mapMode = false },
                    shape = SegmentedButtonDefaults.itemShape(0, 2),
                    icon = { Icon(Icons.Outlined.ViewList, null, Modifier.size(18.dp)) },
                ) { Text("Lista") }
                SegmentedButton(
                    selected = mapMode,
                    onClick = { mapMode = true },
                    shape = SegmentedButtonDefaults.itemShape(1, 2),
                    icon = { Icon(Icons.Outlined.Map, null, Modifier.size(18.dp)) },
                ) { Text("Mapa") }
            }
        }

        Box(Modifier.weight(1f).fillMaxWidth()) {
            if (mapMode) {
                val c = f.place?.let { LatLng(it.lat, it.lon) } ?: meta?.pilot?.center?.let { LatLng(it.lat, it.lon) } ?: LatLng(50.0614, 19.9366)
                ExploreMap(
                    modifier = Modifier.fillMaxSize(),
                    center = c,
                    areas = s.areas,
                    onBboxChanged = { b, _ -> vm.loadAreas(b) },
                    onAreaClick = { cellSheet = it },
                )
                Surface(
                    color = MaterialTheme.colorScheme.surface.copy(alpha = 0.92f),
                    shape = MaterialTheme.shapes.small,
                    modifier = Modifier.align(Alignment.TopCenter).padding(8.dp),
                ) {
                    Text(
                        s.mapError ?: "Kółka to przybliżone obszary (ok. 500 m), nie dokładne miejsca.",
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                    )
                }
                MapLegend(Modifier.align(Alignment.BottomEnd).padding(10.dp))
            } else {
                LazyColumn(
                    state = listState,
                    contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 24.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    if (f == Filters() && !repo.hintDismissed) {
                        item {
                            QuickStart(
                                onLost = { vm.update { it.copy(kind = "found") }; nav.navigate("create?kind=lost") },
                                onFound = { nav.navigate("create?kind=found") },
                            )
                        }
                    }
                    when {
                        s.loading && s.items.isEmpty() -> item { LoadingBox("Szukam zgłoszeń…") }
                        s.error != null && s.items.isEmpty() -> item { ErrorState(s.error!!, onRetry = vm::search) }
                        s.items.isEmpty() -> item {
                            EmptyState(
                                Icons.Outlined.SearchOff,
                                "Nic tu jeszcze nie pasuje",
                                if (f.kind == "found") "Twoja rzecz mogła jeszcze nie zostać zgłoszona. Dodaj zgłoszenie zguby — sprawdzimy nowe znaleziska i damy Ci znać."
                                else "Spróbuj poszerzyć wyszukiwanie.",
                            ) {
                                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                    s.suggestions.forEach { a ->
                                        when (a.action) {
                                            "create_lost" -> Button(onClick = { nav.navigate("create?kind=lost") }) { Text(a.label) }
                                            "share" -> Unit
                                            else -> OutlinedButton(onClick = { vm.applySuggestion(a) }) { Text(a.label) }
                                        }
                                    }
                                    if (s.suggestions.isEmpty()) Button(onClick = { nav.navigate("create?kind=lost") }) { Text("Dodaj zgłoszenie zguby") }
                                }
                            }
                        }
                        else -> {
                            items(s.items, key = { it.id }) { r ->
                                ReportCard(r, meta, repo::absolute, onClick = {
                                    nav.navigate(if (r.isMine) "myreport/${r.id}" else "report/${r.id}")
                                })
                            }
                            if (s.loadingMore) item { LoadingBox("Wczytuję więcej…") }
                            if (s.error != null) item { ErrorState(s.error!!, onRetry = vm::loadMore) }
                        }
                    }
                }
            }
        }
    }

    when (sheet) {
        "category" -> CategorySheet(meta, f.category, f.subtype, onDismiss = { sheet = null }) { cat, sub ->
            vm.update { it.copy(category = cat, subtype = sub) }; sheet = null
        }
        "color" -> ColorSheet(meta, f.colors, onDismiss = { sheet = null }) { cols -> vm.update { it.copy(colors = cols) }; sheet = null }
        "time" -> TimeSheet(f.days, onDismiss = { sheet = null }) { d -> vm.update { it.copy(days = d, dateFrom = null, dateTo = null) }; sheet = null }
        "place" -> PlaceSheet(
            meta = meta,
            current = f.place,
            onDismiss = { sheet = null },
            onMyLocation = {
                sheet = null
                if (LocationHelper.hasPermission(context)) scope.launch {
                    val fix = LocationHelper.currentFix(context)
                    if (fix != null) vm.update { it.copy(place = PlaceFilter("Moja okolica", fix.lat, fix.lon, it.place?.radiusM ?: 2000)) }
                } else {
                    locationPerm.launch(arrayOf(Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.ACCESS_FINE_LOCATION))
                }
            },
        ) { p -> vm.update { it.copy(place = p) }; sheet = null }
    }
    cellSheet?.let { cell ->
        CellSheet(cell, vm, nav, onDismiss = { cellSheet = null })
    }
}

private fun timeLabel(f: Filters): String = when {
    f.dateFrom != null -> Format.parse(f.dateFrom)?.let { "Od " + Format.day(it) } ?: "Wybrany czas"
    f.days == 1 -> "Ostatnie 24 h"
    f.days != null -> "Ostatnie ${f.days} dni"
    else -> "Kiedy: dowolnie"
}

@Composable
private fun QuickStart(onLost: () -> Unit, onFound: () -> Unit) {
    val k = LocalKindColors.current
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Co się stało?", style = MaterialTheme.typography.titleLarge)
        Row(Modifier.height(androidx.compose.foundation.layout.IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.weight(1f).fillMaxHeight()) {
                BigChoiceCompact(Icons.Outlined.Search, "Zgubiłem", "Opisz rzecz — damy znać o dopasowaniach", k.lost, k.onLost, onLost)
            }
            Box(Modifier.weight(1f).fillMaxHeight()) {
                BigChoiceCompact(Icons.Outlined.VolunteerActivism, "Znalazłem", "Zdjęcie i miejsce, kontakt prywatny", k.found, k.onFound, onFound)
            }
        }
        Text(
            "Poniżej znalezione rzeczy w okolicy. Przeglądanie nie wymaga konta.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        HorizontalDivider()
    }
}

@Composable
private fun BigChoiceCompact(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, body: String, bg: androidx.compose.ui.graphics.Color, fg: androidx.compose.ui.graphics.Color, onClick: () -> Unit) {
    androidx.compose.material3.Card(
        onClick = onClick,
        colors = androidx.compose.material3.CardDefaults.cardColors(containerColor = bg, contentColor = fg),
        modifier = Modifier.fillMaxWidth().fillMaxHeight(),
    ) {
        Column(Modifier.padding(14.dp)) {
            Icon(icon, null, Modifier.size(28.dp))
            Spacer(Modifier.height(8.dp))
            Text(title, style = MaterialTheme.typography.titleLarge)
            Text(body, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun MapLegend(modifier: Modifier) {
    val k = LocalKindColors.current
    Surface(color = MaterialTheme.colorScheme.surface.copy(alpha = 0.92f), shape = MaterialTheme.shapes.small, modifier = modifier) {
        Column(Modifier.padding(8.dp)) {
            LegendRow(k.foundStrong, "Znalezione")
            LegendRow(k.lostStrong, "Zgubione")
            LegendRow(MaterialTheme.colorScheme.tertiary, "Oba rodzaje")
        }
    }
}

@Composable
private fun LegendRow(color: androidx.compose.ui.graphics.Color, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(12.dp).padding(1.dp)) { Surface(color = color, shape = androidx.compose.foundation.shape.CircleShape, modifier = Modifier.fillMaxSize()) {} }
        Spacer(Modifier.width(6.dp))
        Text(label, style = MaterialTheme.typography.labelSmall)
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun CategorySheet(meta: pl.findini.app.data.Meta?, current: String?, currentSub: String?, onDismiss: () -> Unit, onPick: (String?, String?) -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 28.dp)) {
            Text("Kategoria", style = MaterialTheme.typography.titleLarge)
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = current == null, onClick = { onPick(null, null) }, label = { Text("Wszystkie") })
                meta?.categories?.forEach { c ->
                    FilterChip(
                        selected = current == c.key && currentSub == null,
                        onClick = { onPick(c.key, null) },
                        label = { Text(c.label) },
                        leadingIcon = { Icon(categoryIcon(c.key), null, Modifier.size(18.dp)) },
                    )
                }
            }
            val cat = meta?.category(current)
            val sub = cat?.attributes?.firstOrNull { it.key == "subtype" && it.type == "select" }
            if (sub != null) {
                Spacer(Modifier.height(12.dp))
                Text("Rodzaj (${cat.label})", style = MaterialTheme.typography.titleSmall)
                Spacer(Modifier.height(6.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    sub.options.forEach { o -> FilterChip(selected = currentSub == o, onClick = { onPick(cat.key, o) }, label = { Text(o) }) }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun ColorSheet(meta: pl.findini.app.data.Meta?, current: List<String>, onDismiss: () -> Unit, onPick: (List<String>) -> Unit) {
    var sel by remember { mutableStateOf(current) }
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 28.dp)) {
            Text("Kolor", style = MaterialTheme.typography.titleLarge)
            Text("Uwzględniamy też kolory podobne (np. granatowy ≈ czarny).", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(8.dp))
            ColorPicker(meta, sel) { sel = it }
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { onPick(emptyList()) }) { Text("Dowolny") }
                Button(onClick = { onPick(sel) }) { Text("Zastosuj") }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ColorPicker(meta: pl.findini.app.data.Meta?, selected: List<String>, max: Int = 3, onChange: (List<String>) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        meta?.colors?.forEach { c ->
            val on = c.key in selected
            FilterChip(
                selected = on,
                onClick = { onChange(if (on) selected - c.key else (selected + c.key).takeLast(max)) },
                label = { Text(c.label) },
                leadingIcon = {
                    Box(Modifier.size(16.dp)) {
                        Surface(color = parseHex(c.hex), shape = androidx.compose.foundation.shape.CircleShape, border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outline), modifier = Modifier.fillMaxSize()) {}
                    }
                },
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun TimeSheet(current: Int?, onDismiss: () -> Unit, onPick: (Int?) -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 28.dp)) {
            Text("Kiedy zdarzenie?", style = MaterialTheme.typography.titleLarge)
            Text("Liczy się czas zgubienia / znalezienia, nie publikacji.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(null to "Dowolnie", 1 to "Ostatnie 24 h", 3 to "3 dni", 7 to "Tydzień", 30 to "30 dni").forEach { (d, label) ->
                    FilterChip(selected = current == d, onClick = { onPick(d) }, label = { Text(label) })
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun PlaceSheet(meta: pl.findini.app.data.Meta?, current: PlaceFilter?, onDismiss: () -> Unit, onMyLocation: () -> Unit, onPick: (PlaceFilter?) -> Unit) {
    var radius by remember { mutableFloatStateOf((current?.radiusM ?: 2000).toFloat()) }
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 28.dp)) {
            Text("Obszar wyszukiwania", style = MaterialTheme.typography.titleLarge)
            Spacer(Modifier.height(8.dp))
            Text("Promień: ${Format.radius(radius.toInt())}", style = MaterialTheme.typography.labelLarge)
            Slider(value = radius, onValueChange = { radius = it }, valueRange = 500f..10000f, steps = 18)
            AssistChip(onClick = onMyLocation, label = { Text("Moja okolica (jednorazowo GPS)") }, leadingIcon = { Icon(Icons.Outlined.MyLocation, null) })
            Spacer(Modifier.height(8.dp))
            Text("Znane miejsca", style = MaterialTheme.typography.titleSmall)
            Spacer(Modifier.height(6.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = current == null, onClick = { onPick(null) }, label = { Text("Cały obszar pilotażu") })
                meta?.landmarks?.forEach { lm ->
                    FilterChip(
                        selected = current?.name == lm.name,
                        onClick = { onPick(PlaceFilter(lm.name, lm.lat, lm.lon, radius.toInt())) },
                        label = { Text(lm.name) },
                    )
                }
            }
            if (current != null) {
                Spacer(Modifier.height(10.dp))
                Button(onClick = { onPick(current.copy(radiusM = radius.toInt())) }) { Text("Zastosuj promień") }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CellSheet(cell: AreaCell, vm: HomeVM, nav: NavController, onDismiss: () -> Unit) {
    val repo = LocalContext.current.app.repo
    val meta by repo.meta.collectAsState()
    var items by remember { mutableStateOf<List<Report>?>(null) }
    var err by remember { mutableStateOf<AppError?>(null) }
    LaunchedEffect(cell.cellId) {
        val f = vm.state.value.filters
        // Promień 300 m < rozmiar komórki: dostajemy dokładnie zgłoszenia z tego obszaru.
        when (val r = repo.public { search(kind = f.kind, category = f.category, lat = cell.lat, lon = cell.lon, radiusM = 300, limit = 30) }) {
            is Outcome.Ok -> items = r.value.items
            is Outcome.Err -> err = r.error
        }
    }
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.padding(horizontal = 16.dp).padding(bottom = 24.dp)) {
            Text("W tym obszarze: ${cell.count}", style = MaterialTheme.typography.titleLarge)
            InfoCard(null, "Obszar ma ok. ${Format.radius(cell.radiusM)} promienia. Dokładne miejsce zna tylko osoba zgłaszająca.", Tone.Privacy, modifier = Modifier.padding(vertical = 8.dp))
            when {
                err != null -> ErrorState(err!!, null)
                items == null -> LoadingBox()
                else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.height(420.dp)) {
                    items(items!!, key = { it.id }) { r ->
                        ReportCard(r, meta, repo::absolute, onClick = { onDismiss(); nav.navigate(if (r.isMine) "myreport/${r.id}" else "report/${r.id}") }, showReasons = false)
                    }
                }
            }
        }
    }
}
