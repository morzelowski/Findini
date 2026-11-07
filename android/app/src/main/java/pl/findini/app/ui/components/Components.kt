package pl.findini.app.ui.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Backpack
import androidx.compose.material.icons.outlined.Category
import androidx.compose.material.icons.outlined.Checkroom
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material.icons.outlined.Devices
import androidx.compose.material.icons.outlined.Diamond
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.Key
import androidx.compose.material.icons.outlined.Place
import androidx.compose.material.icons.outlined.Schedule
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.VolunteerActivism
import androidx.compose.material.icons.outlined.Wallet
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material.icons.outlined.Umbrella
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import pl.findini.app.data.AppError
import pl.findini.app.data.MatchInfo
import pl.findini.app.data.Meta
import pl.findini.app.data.Report
import pl.findini.app.ui.theme.LocalKindColors
import pl.findini.app.util.Format

fun categoryIcon(key: String?): ImageVector = when (key) {
    "electronics" -> Icons.Outlined.Devices
    "keys" -> Icons.Outlined.Key
    "clothing" -> Icons.Outlined.Checkroom
    "bags" -> Icons.Outlined.Backpack
    "wallets" -> Icons.Outlined.Wallet
    "jewelry" -> Icons.Outlined.Diamond
    "accessories" -> Icons.Outlined.Umbrella
    else -> Icons.Outlined.Category
}

fun parseHex(hex: String): Color = runCatching { Color(android.graphics.Color.parseColor(hex)) }.getOrDefault(Color.Gray)

@Composable
fun KindBadge(kind: String, modifier: Modifier = Modifier) {
    val k = LocalKindColors.current
    val found = kind == "found"
    Row(
        modifier
            .clip(RoundedCornerShape(50))
            .background(if (found) k.found else k.lost)
            .padding(horizontal = 10.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            if (found) Icons.Outlined.VolunteerActivism else Icons.Outlined.Search,
            contentDescription = null,
            tint = if (found) k.onFound else k.onLost,
            modifier = Modifier.size(16.dp),
        )
        Spacer(Modifier.width(4.dp))
        Text(
            if (found) "Znalezione" else "Zgubione",
            style = MaterialTheme.typography.labelMedium,
            color = if (found) k.onFound else k.onLost,
        )
    }
}

@Composable
fun StatusPill(status: String) {
    val (label, color) = when (status) {
        "reserved" -> "W trakcie zwrotu" to MaterialTheme.colorScheme.tertiaryContainer
        "resolved" -> "Zakończone" to MaterialTheme.colorScheme.primaryContainer
        "expired" -> "Wygasłe" to MaterialTheme.colorScheme.surfaceVariant
        "withdrawn" -> "Usunięte" to MaterialTheme.colorScheme.surfaceVariant
        else -> return
    }
    Surface(color = color, shape = RoundedCornerShape(50)) {
        Text(label, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp))
    }
}

@Composable
fun ColorDots(colors: List<String>, meta: Meta?, modifier: Modifier = Modifier) {
    if (colors.isEmpty() || meta == null) return
    val labels = colors.mapNotNull { meta.color(it)?.label }
    Row(
        modifier.semantics(mergeDescendants = true) { contentDescription = "Kolor: " + labels.joinToString() },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        colors.forEach { c ->
            val def = meta.color(c) ?: return@forEach
            Box(
                Modifier
                    .padding(end = 4.dp)
                    .size(14.dp)
                    .clip(CircleShape)
                    .background(parseHex(def.hex))
                    .border(1.dp, MaterialTheme.colorScheme.outlineVariant, CircleShape),
            )
        }
        Text(labels.joinToString(), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun PhotoOrIcon(report: Report, imageUrl: (String) -> String, modifier: Modifier = Modifier) {
    val photo = report.photos.firstOrNull()
    Box(
        modifier.clip(MaterialTheme.shapes.medium).background(MaterialTheme.colorScheme.surfaceContainerHigh),
        contentAlignment = Alignment.Center,
    ) {
        if (photo != null) {
            AsyncImage(
                model = imageUrl(photo.thumbUrl),
                contentDescription = "Zdjęcie: ${report.title}",
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        } else {
            Icon(
                categoryIcon(report.category),
                contentDescription = "Bez zdjęcia — ${report.categoryLabel}",
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(36.dp),
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ReasonChips(match: MatchInfo?, max: Int = 4) {
    if (match == null || (match.reasons.isEmpty() && match.warnings.isEmpty())) return
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        match.reasons.take(max).forEach { r ->
            Row(
                Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .background(MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.6f))
                    .padding(horizontal = 8.dp, vertical = 3.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Outlined.CheckCircle, null, Modifier.size(14.dp), tint = MaterialTheme.colorScheme.onPrimaryContainer)
                Spacer(Modifier.width(4.dp))
                Text(r, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onPrimaryContainer)
            }
        }
        match.warnings.forEach { w ->
            Row(
                Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .background(MaterialTheme.colorScheme.errorContainer)
                    .padding(horizontal = 8.dp, vertical = 3.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Outlined.WarningAmber, "Uwaga", Modifier.size(14.dp), tint = MaterialTheme.colorScheme.onErrorContainer)
                Spacer(Modifier.width(4.dp))
                Text(w, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onErrorContainer)
            }
        }
    }
}

@Composable
fun ReportCard(report: Report, meta: Meta?, imageUrl: (String) -> String, onClick: () -> Unit, showReasons: Boolean = true) {
    Card(
        onClick = onClick,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(Modifier.padding(12.dp)) {
            PhotoOrIcon(report, imageUrl, Modifier.size(92.dp))
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    KindBadge(report.kind)
                    Spacer(Modifier.width(6.dp))
                    StatusPill(report.status)
                }
                Spacer(Modifier.height(6.dp))
                Text(report.title, style = MaterialTheme.typography.titleMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(2.dp))
                MetaLine(Icons.Outlined.Place, listOfNotNull(report.area.label?.removePrefix("okolice: "), Format.distance(report.distanceM)).joinToString(" · ").ifBlank { "Kraków" })
                MetaLine(Icons.Outlined.Schedule, Format.window(report.occurredFrom, report.occurredTo))
                ColorDots(report.colors, meta, Modifier.padding(top = 2.dp))
                if (showReasons && report.match != null) {
                    Spacer(Modifier.height(6.dp))
                    ReasonChips(report.match, max = 3)
                }
            }
        }
    }
}

@Composable
fun MetaLine(icon: ImageVector, text: String) {
    if (text.isBlank()) return
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 1.dp)) {
        Icon(icon, null, Modifier.size(14.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.width(4.dp))
        Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(
        text,
        style = MaterialTheme.typography.titleMedium,
        modifier = modifier.semantics { heading() }.padding(vertical = 8.dp),
    )
}

enum class Tone { Info, Privacy, Warning, Success }

@Composable
fun InfoCard(title: String?, body: String, tone: Tone = Tone.Info, icon: ImageVector? = null, modifier: Modifier = Modifier, action: (@Composable () -> Unit)? = null) {
    val cs = MaterialTheme.colorScheme
    val k = LocalKindColors.current
    val (bg, fg) = when (tone) {
        Tone.Info -> cs.tertiaryContainer to cs.onTertiaryContainer
        Tone.Privacy -> cs.primaryContainer to cs.onPrimaryContainer
        Tone.Warning -> k.lost to k.onLost
        Tone.Success -> cs.primaryContainer to cs.onPrimaryContainer
    }
    val ic = icon ?: when (tone) {
        Tone.Privacy -> Icons.Outlined.Lock
        Tone.Warning -> Icons.Outlined.WarningAmber
        Tone.Success -> Icons.Outlined.CheckCircle
        Tone.Info -> Icons.Outlined.Info
    }
    Surface(color = bg, contentColor = fg, shape = MaterialTheme.shapes.medium, modifier = modifier.fillMaxWidth()) {
        Row(Modifier.padding(14.dp)) {
            Icon(ic, null, Modifier.size(22.dp))
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                if (title != null) Text(title, style = MaterialTheme.typography.titleSmall)
                Text(body, style = MaterialTheme.typography.bodyMedium)
                if (action != null) action()
            }
        }
    }
}

@Composable
fun LoadingBox(text: String = "Wczytywanie…", modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxWidth().padding(32.dp).semantics(mergeDescendants = true) {},
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        CircularProgressIndicator()
        Spacer(Modifier.height(12.dp))
        Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun ErrorState(error: AppError, onRetry: (() -> Unit)?, modifier: Modifier = Modifier) {
    val offline = error.kind == AppError.Kind.Offline || error.kind == AppError.Kind.Timeout
    Column(modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(
            if (offline) Icons.Outlined.CloudOff else Icons.Outlined.ErrorOutline,
            null,
            Modifier.size(48.dp),
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(12.dp))
        Text(if (offline) "Brak połączenia" else "Coś poszło nie tak", style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(4.dp))
        Text(error.message, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (onRetry != null) {
            Spacer(Modifier.height(12.dp))
            Button(onClick = onRetry) { Text("Spróbuj ponownie") }
        }
    }
}

@Composable
fun EmptyState(icon: ImageVector, title: String, body: String, modifier: Modifier = Modifier, actions: @Composable () -> Unit = {}) {
    Column(modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Box(
            Modifier.size(72.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primaryContainer),
            contentAlignment = Alignment.Center,
        ) { Icon(icon, null, Modifier.size(36.dp), tint = MaterialTheme.colorScheme.onPrimaryContainer) }
        Spacer(Modifier.height(12.dp))
        Text(title, style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(4.dp))
        Text(body, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(12.dp))
        actions()
    }
}

@Composable
fun OfflineBanner(visible: Boolean) {
    AnimatedVisibility(visible) {
        Surface(color = MaterialTheme.colorScheme.inverseSurface, contentColor = MaterialTheme.colorScheme.inverseOnSurface) {
            Row(
                Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Outlined.CloudOff, null, Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text("Jesteś offline. Szkice zapisujemy na telefonie.", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
fun PrivacyLine(text: String) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 2.dp)) {
        Icon(Icons.Outlined.Lock, "Prywatne", Modifier.size(16.dp), tint = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.width(6.dp))
        Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun TextLink(text: String, onClick: () -> Unit) {
    TextButton(onClick = onClick) { Text(text, fontWeight = FontWeight.SemiBold) }
}

@Composable
fun SecondaryAction(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    OutlinedButton(onClick = onClick, modifier = modifier) { Text(text) }
}

@Composable
fun KeyValue(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp).semantics(mergeDescendants = true) {}) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.width(130.dp))
        Text(value, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
    }
}

@Composable
fun ClickableRow(icon: ImageVector, title: String, subtitle: String? = null, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 4.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, null, tint = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyLarge)
            if (subtitle != null) Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
