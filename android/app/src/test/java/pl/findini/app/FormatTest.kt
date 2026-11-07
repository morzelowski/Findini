package pl.findini.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import pl.findini.app.util.Format

class FormatTest {
    @Test
    fun distancesAreCoarseAndPolish() {
        assertEquals("ok. 100 m", Format.distance(40))
        assertEquals("ok. 400 m", Format.distance(400))
        assertEquals("ok. 1,5 km", Format.distance(1500))
    }

    @Test
    fun utcIsoIsShownInWarsawTime() {
        // 12:00 UTC w lipcu = 14:00 w Polsce (czas letni)
        val z = Format.parse("2026-07-01T12:00:00Z")!!
        assertEquals(14, z.hour)
        val w = Format.window("2026-07-01T10:00:00Z", "2026-07-01T12:30:00Z")
        assertTrue(w, w.endsWith("12:00–14:30"))
    }
}
