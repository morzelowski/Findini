package pl.findini.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.findini.app.R

// Spokojna paleta katalogu: granat, neutralne powierzchnie i oszczędne akcenty.
private val Sea = Color(0xFF234E70)
private val SeaLight = Color(0xFFA5C9EB)
private val Apricot = Color(0xFFB96332)
private val Paper = Color(0xFFF6F7F9)
private val Ink = Color(0xFF1B2936)

private val LightColors = lightColorScheme(
    primary = Sea,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFE0ECF7),
    onPrimaryContainer = Color(0xFF102B43),
    secondary = Color(0xFFA2492A),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFE7ECF2),
    onSecondaryContainer = Color(0xFF273E52),
    tertiary = Color(0xFF4F5D9A),
    onTertiary = Color.White,
    tertiaryContainer = Color(0xFFDEE1FF),
    onTertiaryContainer = Color(0xFF0A1752),
    background = Paper,
    onBackground = Ink,
    surface = Paper,
    onSurface = Ink,
    surfaceVariant = Color(0xFFE8EDF2),
    onSurfaceVariant = Color(0xFF566573),
    surfaceContainerLowest = Color.White,
    surfaceContainerLow = Color(0xFFF1F4F7),
    surfaceContainer = Color(0xFFEBEFF4),
    surfaceContainerHigh = Color(0xFFE5EAF0),
    surfaceContainerHighest = Color(0xFFDEE5ED),
    outline = Color(0xFF75818D),
    outlineVariant = Color(0xFFCFD8E1),
    error = Color(0xFFB3261E),
    onError = Color.White,
    errorContainer = Color(0xFFF9DEDC),
    onErrorContainer = Color(0xFF410E0B),
)

private val DarkColors = darkColorScheme(
    primary = SeaLight,
    onPrimary = Color(0xFF103348),
    primaryContainer = Color(0xFF244862),
    onPrimaryContainer = Color(0xFFE0ECF7),
    secondary = Color(0xFFFFB596),
    onSecondary = Color(0xFF5A1C03),
    secondaryContainer = Color(0xFF2C4A46),
    onSecondaryContainer = Color(0xFFE7ECF2),
    tertiary = Color(0xFFBAC3FF),
    onTertiary = Color(0xFF212F6A),
    tertiaryContainer = Color(0xFF384582),
    onTertiaryContainer = Color(0xFFDEE1FF),
    background = Color(0xFF111820),
    onBackground = Color(0xFFDDE4E2),
    surface = Color(0xFF111820),
    onSurface = Color(0xFFDDE4E2),
    surfaceVariant = Color(0xFF3F4947),
    onSurfaceVariant = Color(0xFFBEC9C6),
    surfaceContainerLowest = Color(0xFF0A0F0E),
    surfaceContainerLow = Color(0xFF18212B),
    surfaceContainer = Color(0xFF1E2935),
    surfaceContainerHigh = Color(0xFF263340),
    surfaceContainerHighest = Color(0xFF303F4E),
    outline = Color(0xFF899391),
    outlineVariant = Color(0xFF3F4947),
)

/** Kolory semantyczne rodzajów zgłoszeń (zawsze używane razem z ikoną i tekstem). */
@Immutable
data class KindColors(val found: Color, val onFound: Color, val lost: Color, val onLost: Color, val foundStrong: Color, val lostStrong: Color)

val LocalKindColors = staticCompositionLocalOf {
    KindColors(Color(0xFFD8F0E6), Color(0xFF0B4D3F), Color(0xFFFCE3D3), Color(0xFF7A3313), Color(0xFF168067), Color(0xFFD0652F))
}

private val LightKind = KindColors(Color(0xFFD8F0E6), Color(0xFF0B4D3F), Color(0xFFFCE3D3), Color(0xFF7A3313), Color(0xFF168067), Color(0xFFD0652F))
private val DarkKind = KindColors(Color(0xFF15463B), Color(0xFFC6F0E2), Color(0xFF5C2A12), Color(0xFFFFDCCB), Color(0xFF52C7A6), Color(0xFFF29A6C))

private fun jakarta(weight: Int) = Font(
    R.font.plus_jakarta_sans,
    weight = FontWeight(weight),
    variationSettings = FontVariation.Settings(FontVariation.weight(weight)),
)

private val Jakarta = FontFamily(jakarta(400), jakarta(500), jakarta(600), jakarta(700), jakarta(800))

private val AppTypography = Typography().run {
    copy(
        displaySmall = displaySmall.copy(fontFamily = Jakarta, fontWeight = FontWeight.Bold, letterSpacing = (-0.5).sp),
        headlineLarge = headlineLarge.copy(fontFamily = Jakarta, fontWeight = FontWeight.Bold, letterSpacing = (-0.5).sp),
        headlineMedium = headlineMedium.copy(fontFamily = Jakarta, fontWeight = FontWeight.Bold, letterSpacing = (-0.25).sp),
        headlineSmall = headlineSmall.copy(fontFamily = Jakarta, fontWeight = FontWeight.Bold),
        titleLarge = titleLarge.copy(fontFamily = Jakarta, fontWeight = FontWeight.Bold),
        titleMedium = titleMedium.copy(fontFamily = Jakarta, fontWeight = FontWeight.SemiBold),
        titleSmall = titleSmall.copy(fontFamily = Jakarta, fontWeight = FontWeight.SemiBold),
        bodyLarge = bodyLarge.copy(fontFamily = Jakarta, lineHeight = 24.sp),
        bodyMedium = bodyMedium.copy(fontFamily = Jakarta, lineHeight = 21.sp),
        bodySmall = bodySmall.copy(fontFamily = Jakarta),
        labelLarge = labelLarge.copy(fontFamily = Jakarta, fontWeight = FontWeight.SemiBold),
        labelMedium = labelMedium.copy(fontFamily = Jakarta, fontWeight = FontWeight.SemiBold),
        labelSmall = labelSmall.copy(fontFamily = Jakarta, fontWeight = FontWeight.SemiBold),
    )
}

private val AppShapes = Shapes(
    extraSmall = RoundedCornerShape(4.dp),
    small = RoundedCornerShape(8.dp),
    medium = RoundedCornerShape(12.dp),
    large = RoundedCornerShape(16.dp),
    extraLarge = RoundedCornerShape(20.dp),
)

val Mono = TextStyle(fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold, fontSize = 30.sp, letterSpacing = 6.sp)

@Composable
fun FindiniTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    androidx.compose.runtime.CompositionLocalProvider(LocalKindColors provides if (dark) DarkKind else LightKind) {
        MaterialTheme(
            colorScheme = if (dark) DarkColors else LightColors,
            typography = AppTypography,
            shapes = AppShapes,
            content = content,
        )
    }
}
