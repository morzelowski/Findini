package pl.findini.app.util

import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Daty zapisujemy w UTC (ISO 8601), pokazujemy w strefie Europe/Warsaw. */
object Format {
    val zone: ZoneId = ZoneId.of("Europe/Warsaw")
    private val pl = Locale.forLanguageTag("pl-PL")
    private val dayFmt = DateTimeFormatter.ofPattern("d MMMM", pl)
    private val dayYearFmt = DateTimeFormatter.ofPattern("d MMMM yyyy", pl)
    private val timeFmt = DateTimeFormatter.ofPattern("HH:mm", pl)

    fun parse(iso: String?): ZonedDateTime? =
        iso?.let { runCatching { Instant.parse(it.replace("+00:00", "Z")).atZone(zone) }.getOrNull()
            ?: runCatching { ZonedDateTime.parse(it).withZoneSameInstant(zone) }.getOrNull() }

    fun toUtcIso(z: ZonedDateTime): String = z.toInstant().toString()

    fun day(z: ZonedDateTime): String {
        val today = LocalDate.now(zone)
        return when (z.toLocalDate()) {
            today -> "dziś"
            today.minusDays(1) -> "wczoraj"
            else -> if (z.year == today.year) z.format(dayFmt) else z.format(dayYearFmt)
        }
    }

    fun time(z: ZonedDateTime): String = z.format(timeFmt)

    /** „wczoraj, 14:00–16:30” albo „3–5 listopada”. */
    fun window(fromIso: String, toIso: String): String {
        val a = parse(fromIso) ?: return ""
        val b = parse(toIso) ?: return day(a)
        return if (a.toLocalDate() == b.toLocalDate()) {
            if (Duration.between(a, b).toMinutes() >= 23 * 60) day(a) else "${day(a)}, ${time(a)}–${time(b)}"
        } else {
            "${day(a)} – ${day(b)}"
        }
    }

    fun ago(iso: String?): String {
        val z = parse(iso) ?: return ""
        val d = Duration.between(z.toInstant(), Instant.now())
        return when {
            d.toMinutes() < 1 -> "przed chwilą"
            d.toMinutes() < 60 -> "${d.toMinutes()} min temu"
            d.toHours() < 24 -> "${d.toHours()} godz. temu"
            d.toDays() < 7 -> "${d.toDays()} ${if (d.toDays() == 1L) "dzień" else "dni"} temu"
            else -> day(z)
        }
    }

    fun distance(m: Int?): String? = when {
        m == null -> null
        m < 1000 -> "ok. ${maxOf(m, 100)} m"
        else -> "ok. " + String.format(pl, "%.1f", m / 1000.0) + " km"
    }

    fun radius(m: Int): String = if (m < 1000) "$m m" else String.format(pl, "%.1f km", m / 1000.0)
}
