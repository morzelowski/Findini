package pl.findini.app

import org.junit.Assert.assertEquals
import org.junit.Test
import pl.findini.app.ui.screens.agree

class TitleAgreementTest {
    @Test
    fun adjectiveAgreesWithNounGender() {
        assertEquals("biała", agree("biały", "czapka"))
        assertEquals("niebieska", agree("niebieski", "bluza / sweter"))
        assertEquals("czarne", agree("czarny", "słuchawki"))
        assertEquals("niebieskie", agree("niebieski", "okulary"))
        assertEquals("czarne", agree("czarny", "etui na karty"))
        assertEquals("granatowy", agree("granatowy", "plecak"))
        assertEquals("srebrny", agree("srebrny", "pierścionek"))
    }
}
