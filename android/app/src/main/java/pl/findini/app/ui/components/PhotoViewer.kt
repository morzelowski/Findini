package pl.findini.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import coil3.compose.AsyncImage
import pl.findini.app.data.PhotoRef

@Composable
fun PhotoViewer(photos: List<PhotoRef>, initialPage: Int, imageUrl: (String) -> String, onDismiss: () -> Unit) {
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        val pager = rememberPagerState(initialPage = initialPage, pageCount = { photos.size })
        Box(Modifier.fillMaxSize().background(Color(0xFF0C1118)).systemBarsPadding()) {
            HorizontalPager(pager, modifier = Modifier.fillMaxSize()) { page ->
                var scale by remember { mutableFloatStateOf(1f) }
                var offset by remember { mutableStateOf(Offset.Zero) }
                var imageSize by remember { mutableStateOf(IntSize.Zero) }
                val transform = rememberTransformableState { zoom, pan, _ ->
                    scale = (scale * zoom).coerceIn(1f, 5f)
                    val maxX = imageSize.width * (scale - 1) / 2
                    val maxY = imageSize.height * (scale - 1) / 2
                    offset = Offset((offset.x + pan.x).coerceIn(-maxX, maxX), (offset.y + pan.y).coerceIn(-maxY, maxY))
                }
                LaunchedEffect(pager.currentPage) {
                    if (pager.currentPage != page) { scale = 1f; offset = Offset.Zero }
                }
                AsyncImage(
                    model = imageUrl(photos[page].url), contentDescription = "Zdjęcie ${page + 1} z ${photos.size}. Rozsuń palce, aby powiększyć.",
                    contentScale = ContentScale.Fit,
                    modifier = Modifier.fillMaxSize().onSizeChanged { imageSize = it }
                        .transformable(state = transform, canPan = { scale > 1f })
                        .graphicsLayer(scaleX = scale, scaleY = scale, translationX = offset.x, translationY = offset.y),
                )
            }
            Row(Modifier.align(Alignment.TopCenter).fillMaxWidth().background(Color.Black.copy(alpha = 0.65f)).padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("${pager.currentPage + 1} / ${photos.size}", color = Color.White, modifier = Modifier.weight(1f))
                IconButton(onClick = onDismiss) { Icon(Icons.Outlined.Close, "Zamknij zdjęcie", tint = Color.White) }
            }
            Text("Rozsuń palce, aby powiększyć", style = MaterialTheme.typography.labelMedium, color = Color.White, modifier = Modifier.align(Alignment.BottomCenter).background(Color.Black.copy(alpha = 0.65f)).padding(12.dp))
        }
    }
}
