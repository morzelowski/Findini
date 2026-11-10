package pl.findini.app.ui.components

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.MyLocation
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import pl.findini.app.app
import pl.findini.app.data.Landmark
import pl.findini.app.data.Outcome
import pl.findini.app.util.Format
import pl.findini.app.util.LocationHelper
import kotlin.math.roundToInt

data class SelectedPlace(val name: String, val lat: Double, val lon: Double, val radiusM: Int)

/** Stała wysokość, przewijane wyniki i jawne zatwierdzanie: suwak nie uruchamia wyszukiwania. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlaceSearchSheet(
    current: SelectedPlace?,
    searchArea: Boolean = true,
    onDismiss: () -> Unit,
    onPick: (SelectedPlace?) -> Unit,
) {
    val context = LocalContext.current
    val repo = context.app.repo
    val meta by repo.meta.collectAsState()
    val scope = rememberCoroutineScope()
    var query by rememberSaveable { mutableStateOf("") }
    var selected by remember { mutableStateOf(current) }
    var radius by rememberSaveable { mutableFloatStateOf((current?.radiusM ?: 5000).toFloat().coerceIn(500f, 25000f)) }
    var results by remember { mutableStateOf<List<Landmark>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }
    var locating by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var retry by remember { mutableIntStateOf(0) }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val appliedRadius = ((radius / 500).roundToInt() * 500).coerceIn(500, 25000)

    fun locate() {
        scope.launch {
            locating = true
            error = null
            val fix = LocationHelper.currentFix(context)
            locating = false
            if (fix != null) selected = SelectedPlace("Moja okolica", fix.lat, fix.lon, radius.toInt())
            else error = "Nie udało się ustalić pozycji. Wyszukaj miejscowość lub wskaż punkt na mapie."
        }
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        if (grants.values.any { it }) locate()
        else error = "Brak dostępu do lokalizacji. Możesz wyszukać miejscowość po nazwie."
    }

    LaunchedEffect(query, retry) {
        error = null
        if (query.trim().length < 2) {
            results = emptyList()
            loading = false
            return@LaunchedEffect
        }
        loading = true
        results = emptyList()
        delay(300)
        when (val r = repo.public { places(query.trim()) }) {
            is Outcome.Ok -> results = r.value.items
            is Outcome.Err -> error = r.error.message
        }
        loading = false
    }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(Modifier.fillMaxWidth().fillMaxHeight(0.9f).imePadding().padding(horizontal = 20.dp)) {
            Text(if (searchArea) "Obszar wyszukiwania" else "Wybierz miejscowość", style = MaterialTheme.typography.titleLarge)
            Text("Cała Polska · miasta i mniejsze miejscowości", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = query, onValueChange = { query = it.take(80) },
                label = { Text("Miejscowość") },
                placeholder = { Text("Możesz dodać województwo lub powiat") },
                leadingIcon = { Icon(Icons.Outlined.Search, null) },
                singleLine = true, modifier = Modifier.fillMaxWidth(),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            )
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                TextButton(onClick = {
                    if (LocationHelper.hasPermission(context)) locate()
                    else permission.launch(arrayOf(Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.ACCESS_FINE_LOCATION))
                }, enabled = !locating) {
                    Icon(Icons.Outlined.MyLocation, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(if (locating) "Ustalam pozycję…" else "Użyj lokalizacji")
                }
                if (searchArea) TextButton(onClick = { selected = null }) { Text("Cała Polska") }
            }
            HorizontalDivider()
            LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(vertical = 8.dp)) {
                if (loading) item { LoadingBox("Szukam miejscowości…") }
                if (error != null) item {
                    Text(error!!, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
                    TextButton(onClick = { retry++ }) { Text("Spróbuj ponownie") }
                }
                if (!loading && error == null && query.trim().length >= 2 && results.isEmpty()) item {
                    Text("Brak miejscowości. Spróbuj krótszej nazwy lub dodaj województwo. Dokładne miejsce możesz wskazać na mapie.", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(vertical = 12.dp))
                }
                if (query.trim().length < 2) item {
                    Text("Popularne miejscowości", style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(vertical = 8.dp))
                }
                items(if (query.trim().length < 2) meta?.landmarks.orEmpty() else results, key = { it.key }) { place ->
                    val checked = selected?.lat == place.lat && selected?.lon == place.lon
                    Row(
                        Modifier.fillMaxWidth().clickable { selected = SelectedPlace(place.name, place.lat, place.lon, radius.toInt()) }.padding(vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(place.name, style = MaterialTheme.typography.bodyLarge)
                            if (place.context.isNotBlank()) Text(place.context, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        if (checked) Icon(Icons.Outlined.Check, "Wybrane", tint = MaterialTheme.colorScheme.primary)
                    }
                }
            }
            HorizontalDivider()
            Text(selected?.name ?: if (searchArea) "Cała Polska" else "Wybierz miejscowość z listy", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 12.dp))
            if (searchArea && selected != null) {
                Text("Promień: ${Format.radius(appliedRadius)}", style = MaterialTheme.typography.bodySmall)
                Slider(value = radius, onValueChange = { radius = it }, onValueChangeFinished = { radius = appliedRadius.toFloat() }, valueRange = 500f..25000f)
            } else {
                Text(if (searchArea) "Wyszukiwanie bez ograniczenia odległości." else "Następnie doprecyzuj punkt na mapie.", style = MaterialTheme.typography.bodySmall)
            }
            Button(shape = MaterialTheme.shapes.small,
                onClick = { onPick(selected?.copy(radiusM = appliedRadius)) },
                enabled = searchArea || selected != null,
                modifier = Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 16.dp).heightIn(min = 48.dp),
            ) { Text(if (searchArea) "Zastosuj obszar" else "Pokaż na mapie") }
            Text("Miejscowości: © GeoNames · CC BY 4.0", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(bottom = 8.dp))
        }
    }
}
