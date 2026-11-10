package pl.findini.app.ui.components

import android.graphics.PointF
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.background
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.outlined.MapsUgc
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngBounds
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression
import org.maplibre.android.style.layers.FillLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.layers.SymbolLayer
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import org.maplibre.geojson.Point
import org.maplibre.geojson.Polygon
import pl.findini.app.data.AreaCell
import pl.findini.app.ui.theme.LocalKindColors
import kotlin.math.cos
import kotlin.math.sin

/**
 * Mapa: MapLibre + kafelki OpenFreeMap (bez klucza API, dane © OpenStreetMap — atrybucja
 * pokazywana w przycisku „i” na mapie). Adres stylu można zmienić w jednym miejscu.
 */
const val MAP_STYLE_URL = "https://tiles.openfreemap.org/styles/positron"

data class Bbox(val minLon: Double, val minLat: Double, val maxLon: Double, val maxLat: Double) {
    override fun toString() = "%.5f,%.5f,%.5f,%.5f".format(java.util.Locale.US, minLon, minLat, maxLon, maxLat)
}

fun circlePolygon(lat: Double, lon: Double, radiusM: Double, steps: Int = 48): Polygon {
    val pts = (0..steps).map { i ->
        val a = 2 * Math.PI * i / steps
        val dLat = radiusM * cos(a) / 111_320.0
        val dLon = radiusM * sin(a) / (111_320.0 * cos(Math.toRadians(lat)))
        Point.fromLngLat(lon + dLon, lat + dLat)
    }
    return Polygon.fromLngLats(listOf(pts))
}

@Composable
fun MapBox(
    modifier: Modifier,
    initial: LatLng,
    zoom: Double,
    description: String,
    interactive: Boolean = true,
    onReady: (MapLibreMap, Style) -> Unit,
) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var failed by remember { mutableStateOf(false) }
    val ready by rememberUpdatedState(onReady)
    val mapView = remember {
        MapView(context).apply {
            onCreate(null)
            addOnDidFailLoadingMapListener { failed = true }
            getMapAsync { map ->
                map.uiSettings.isAttributionEnabled = true
                map.uiSettings.isLogoEnabled = false
                map.uiSettings.isRotateGesturesEnabled = false
                map.uiSettings.isTiltGesturesEnabled = false
                if (!interactive) map.uiSettings.setAllGesturesEnabled(false)
                map.cameraPosition = CameraPosition.Builder().target(initial).zoom(zoom).build()
                map.setStyle(Style.Builder().fromUri(MAP_STYLE_URL)) { style -> ready(map, style) }
            }
        }
    }
    DisposableEffect(lifecycle) {
        val obs = LifecycleEventObserver { _, e ->
            when (e) {
                Lifecycle.Event.ON_START -> mapView.onStart()
                Lifecycle.Event.ON_RESUME -> mapView.onResume()
                Lifecycle.Event.ON_PAUSE -> mapView.onPause()
                Lifecycle.Event.ON_STOP -> mapView.onStop()
                else -> Unit
            }
        }
        lifecycle.addObserver(obs)
        onDispose {
            lifecycle.removeObserver(obs)
            mapView.onPause()
            mapView.onStop()
            mapView.onDestroy()
        }
    }
    Box(modifier.semantics { contentDescription = description }) {
        AndroidView(factory = { mapView }, modifier = Modifier.fillMaxSize())
        if (failed) {
            Column(
                Modifier.align(Alignment.Center).padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Icon(Icons.Outlined.MapsUgc, null, Modifier.size(40.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(
                    "Mapa jest niedostępna. Możesz korzystać z listy i wyszukać miejscowość po nazwie.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/** Mapa eksploracji: kółka = przybliżone obszary (komórki ~500 m) z liczbą zgłoszeń. */
@Composable
fun ExploreMap(
    modifier: Modifier,
    center: LatLng,
    areas: List<AreaCell>,
    zoom: Double = 5.2,
    onBboxChanged: (Bbox, Double) -> Unit,
    onAreaClick: (AreaCell) -> Unit,
) {
    val kind = LocalKindColors.current
    val foundColor = kind.foundStrong.toArgb()
    val lostColor = kind.lostStrong.toArgb()
    val mixed = MaterialTheme.colorScheme.tertiary.toArgb()
    var styleRef by remember { mutableStateOf<Style?>(null) }
    var mapRef by remember { mutableStateOf<MapLibreMap?>(null) }
    val areasState by rememberUpdatedState(areas)
    val clickState by rememberUpdatedState(onAreaClick)
    val bboxState by rememberUpdatedState(onBboxChanged)
    MapBox(modifier, center, zoom, "Mapa z przybliżonymi obszarami zgłoszeń") { map, style ->
        mapRef = map
        style.addSource(GeoJsonSource("areas"))
        style.addSource(GeoJsonSource("labels"))
        style.addLayer(
            FillLayer("areas-fill", "areas").withProperties(
                PropertyFactory.fillColor(Expression.toColor(Expression.get("color"))),
                PropertyFactory.fillOpacity(0.22f),
            ),
        )
        style.addLayer(
            LineLayer("areas-line", "areas").withProperties(
                PropertyFactory.lineColor(Expression.toColor(Expression.get("color"))),
                PropertyFactory.lineWidth(1.5f),
            ),
        )
        style.addLayer(
            SymbolLayer("areas-count", "labels").withProperties(
                PropertyFactory.textField(Expression.get("count")),
                PropertyFactory.textFont(arrayOf("Noto Sans Bold")),
                PropertyFactory.textSize(14f),
                PropertyFactory.textColor("#14302E"),
                PropertyFactory.textHaloColor("#FFFFFF"),
                PropertyFactory.textHaloWidth(2f),
                PropertyFactory.textAllowOverlap(true),
            ),
        )
        styleRef = style
        map.addOnCameraIdleListener {
            val b = map.projection.visibleRegion.latLngBounds
            bboxState(Bbox(b.longitudeWest, b.latitudeSouth, b.longitudeEast, b.latitudeNorth), map.cameraPosition.zoom)
        }
        map.addOnMapClickListener { ll ->
            val p: PointF = map.projection.toScreenLocation(ll)
            val f = map.queryRenderedFeatures(p, "areas-fill").firstOrNull()
            val id = f?.getStringProperty("cell")
            val cell = areasState.firstOrNull { it.cellId == id }
            if (cell != null) {
                if (cell.cellId.startsWith("cluster:")) {
                    map.animateCamera(CameraUpdateFactory.newLatLngZoom(LatLng(cell.lat, cell.lon), map.cameraPosition.zoom + 2.0))
                } else clickState(cell)
            }
            cell != null
        }
        val b = map.projection.visibleRegion.latLngBounds
        bboxState(Bbox(b.longitudeWest, b.latitudeSouth, b.longitudeEast, b.latitudeNorth), map.cameraPosition.zoom)
    }
    LaunchedEffect(mapRef, center.latitude, center.longitude, zoom) {
        mapRef?.animateCamera(CameraUpdateFactory.newLatLngZoom(center, zoom))
    }
    LaunchedEffect(styleRef, areas) {
        val style = styleRef ?: return@LaunchedEffect
        val polys = areas.map { a ->
            val color = when {
                a.found > 0 && a.lost > 0 -> mixed
                a.found > 0 -> foundColor
                else -> lostColor
            }
            Feature.fromGeometry(circlePolygon(a.lat, a.lon, a.radiusM.toDouble())).apply {
                addStringProperty("cell", a.cellId)
                addStringProperty("color", String.format("#%06X", 0xFFFFFF and color))
            }
        }
        val labels = areas.map { a ->
            Feature.fromGeometry(Point.fromLngLat(a.lon, a.lat)).apply { addStringProperty("count", a.count.toString()) }
        }
        (style.getSource("areas") as? GeoJsonSource)?.setGeoJson(FeatureCollection.fromFeatures(polys))
        (style.getSource("labels") as? GeoJsonSource)?.setGeoJson(FeatureCollection.fromFeatures(labels))
    }
}

/** Mapa z jednym przybliżonym obszarem (szczegóły zgłoszenia). */
@Composable
fun AreaMap(modifier: Modifier, lat: Double, lon: Double, radiusM: Int, kind: String) {
    val k = LocalKindColors.current
    val color = String.format("#%06X", 0xFFFFFF and (if (kind == "found") k.foundStrong else k.lostStrong).toArgb())
    MapBox(modifier, LatLng(lat, lon), if (radiusM > 800) 12.6 else 13.5, "Mapa przybliżonego obszaru zgłoszenia", interactive = false) { _, style ->
        style.addSource(GeoJsonSource("area", Feature.fromGeometry(circlePolygon(lat, lon, radiusM.toDouble()))))
        style.addLayer(FillLayer("area-fill", "area").withProperties(PropertyFactory.fillColor(color), PropertyFactory.fillOpacity(0.25f)))
        style.addLayer(LineLayer("area-line", "area").withProperties(PropertyFactory.lineColor(color), PropertyFactory.lineWidth(2f)))
    }
}

/**
 * Wybór miejsca: pinezka na środku mapy; użytkownik przesuwa mapę. Kółko pokazuje
 * niepewność (dokładność GPS lub zadeklarowany promień).
 */
@Composable
fun PickerMap(
    modifier: Modifier,
    initial: LatLng,
    uncertaintyM: Int,
    recenter: LatLng?,
    hasLocation: Boolean = true,
    onCenter: (LatLng) -> Unit,
) {
    var mapRef by remember { mutableStateOf<MapLibreMap?>(null) }
    var styleRef by remember { mutableStateOf<Style?>(null) }
    var center by remember { mutableStateOf(initial) }
    val onCenterState by rememberUpdatedState(onCenter)
    val primary = String.format("#%06X", 0xFFFFFF and MaterialTheme.colorScheme.primary.toArgb())
    Box(modifier) {
        MapBox(Modifier.fillMaxSize(), initial, if (hasLocation) 14.0 else 5.2, "Mapa wyboru miejsca. Przesuń mapę, aby ustawić pinezkę.") { map, style ->
            style.addSource(GeoJsonSource("unc"))
            style.addLayer(FillLayer("unc-fill", "unc").withProperties(PropertyFactory.fillColor(primary), PropertyFactory.fillOpacity(0.15f)))
            style.addLayer(LineLayer("unc-line", "unc").withProperties(PropertyFactory.lineColor(primary), PropertyFactory.lineWidth(1.5f)))
            var userMoved = false
            map.addOnCameraMoveStartedListener { reason ->
                if (reason == MapLibreMap.OnCameraMoveStartedListener.REASON_API_GESTURE) userMoved = true
            }
            map.addOnCameraIdleListener {
                val t = map.cameraPosition.target ?: return@addOnCameraIdleListener
                center = t
                if (userMoved) {
                    onCenterState(t)
                    userMoved = false
                }
            }
            mapRef = map
            styleRef = style
        }
        Icon(
            Icons.Filled.Place,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.secondary,
            modifier = Modifier.align(Alignment.Center).padding(bottom = 36.dp).size(44.dp),
        )
    }
    LaunchedEffect(recenter, mapRef) {
        val m = mapRef ?: return@LaunchedEffect
        if (recenter != null) m.animateCamera(CameraUpdateFactory.newLatLngZoom(recenter, 16.0))
    }
    LaunchedEffect(styleRef, center, uncertaintyM) {
        val s = styleRef ?: return@LaunchedEffect
        val r = maxOf(uncertaintyM, 25).toDouble()
        (s.getSource("unc") as? GeoJsonSource)?.setGeoJson(Feature.fromGeometry(circlePolygon(center.latitude, center.longitude, r)))
    }
}
