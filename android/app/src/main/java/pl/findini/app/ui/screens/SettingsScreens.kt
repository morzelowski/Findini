package pl.findini.app.ui.screens

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.DeleteForever
import androidx.compose.material.icons.outlined.Dns
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Key
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.PhonelinkSetup
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import kotlinx.coroutines.launch
import pl.findini.app.BuildConfig
import pl.findini.app.app
import pl.findini.app.data.Outcome
import pl.findini.app.ui.components.ClickableRow
import pl.findini.app.ui.components.InfoCard
import pl.findini.app.ui.components.SectionTitle
import pl.findini.app.ui.components.Tone
import pl.findini.app.ui.theme.Mono

@Composable
fun SettingsScreen(nav: NavController, snackbar: SnackbarHostState) {
    val context = LocalContext.current
    val repo = context.app.repo
    val meta by repo.meta.collectAsState()
    val scope = rememberCoroutineScope()
    var code by remember { mutableStateOf<String?>(null) }
    var confirmDelete by remember { mutableStateOf(false) }
    var server by remember { mutableStateOf(repo.baseUrl) }
    var askNotif by remember { mutableStateOf(false) }
    NotificationPermissionAsk(askNotif) { askNotif = false; repo.notificationsAsked = true }

    ScreenScaffold(title = "Prywatność i ustawienia", onBack = { nav.popBackStack() }) { mod ->
        Column(mod.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            InfoCard(
                "Bez konta, ale nie bez zabezpieczeń",
                "Przy pierwszym zgłoszeniu telefon dostaje losowy, tajny token sesji (zaszyfrowany w Android Keystore). Nie podajesz imienia, e-maila ani telefonu. " +
                    "Jeśli usuniesz aplikację lub zgubisz telefon bez kodu odzyskiwania — dostęp do zgłoszeń przepadnie. Nie mamy innego sposobu, by potwierdzić, że to Ty.",
                Tone.Privacy,
            )
            SectionTitle("Dostęp")
            ClickableRow(Icons.Outlined.Key, "Utwórz kod odzyskiwania", "Pozwala przenieść zgłoszenia na nowy telefon. Nowy kod unieważnia poprzedni.") {
                scope.launch {
                    when (val r = repo.private { recoveryCode() }) {
                        is Outcome.Ok -> code = r.value.code
                        is Outcome.Err -> snackbar.showSnackbar(r.error.message)
                    }
                }
            }
            ClickableRow(Icons.Outlined.PhonelinkSetup, "Przywróć dostęp kodem", "Masz kod z poprzedniego telefonu?") { nav.navigate("recovery") }
            ClickableRow(Icons.Outlined.Notifications, "Powiadomienia o dopasowaniach", "Sprawdzanie co ok. 30 min, bez lokalizacji") {
                if (android.os.Build.VERSION.SDK_INT >= 33) askNotif = true
                else scope.launch { snackbar.showSnackbar("Powiadomienia są włączone") }
            }
            HorizontalDivider()
            SectionTitle("Twoje dane")
            Text(
                "Zgłoszenia są aktywne ${meta?.retention?.activeDays ?: 60} dni, potem wygasają. Zakończone, usunięte i wygasłe sprawy " +
                    "(z rozmowami i dowodami) kasujemy po ${meta?.retention?.purgeAfterDays ?: 180} dniach. Niewykorzystane zdjęcia — po 24 h. " +
                    "Publicznie pokazujemy tylko obszar ok. 500 m. Dokładne miejsce, ukryty szczegół, dowody i rozmowy widzą wyłącznie uprawnione strony sprawy.",
                style = MaterialTheme.typography.bodyMedium,
            )
            ClickableRow(Icons.Outlined.DeleteForever, "Usuń wszystkie moje dane", "Zgłoszenia, zdjęcia, roszczenia, rozmowy i sesja — nieodwracalnie") { confirmDelete = true }
            HorizontalDivider()
            SectionTitle("O aplikacji")
            ClickableRow(Icons.Outlined.Info, "Findini ${BuildConfig.VERSION_NAME} · pilotaż: ${meta?.pilot?.name ?: "Kraków"}", "Projekt studencki: K. Czaplicki, A. Łabęda, M. Orzełowski") {}
            Text(
                "Mapa: MapLibre, kafelki OpenFreeMap, dane © współtwórcy OpenStreetMap. Analiza zdjęć: lokalny model CLIP ViT-B/32 (licencja MIT) na serwerze Findini — " +
                    "zdjęcia nie trafiają do zewnętrznych usług. Asystent wyszukiwania działa na regułach, bez AI. Krój pisma: Plus Jakarta Sans (SIL OFL 1.1). " +
                    "Status AI: ${meta?.ai?.status ?: "nieznany"}.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (BuildConfig.ALLOW_CUSTOM_SERVER) {
                HorizontalDivider()
                SectionTitle("Serwer (wersja deweloperska)")
                OutlinedTextField(server, { server = it.trim() }, label = { Text("Adres API") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Text("Emulator: http://10.0.2.2:8080/ · telefon w tej samej sieci Wi-Fi: http://IP-komputera:8080/ · USB: adb reverse + http://localhost:8080/", style = MaterialTheme.typography.bodySmall)
                Button(onClick = {
                    repo.setServerUrl(if (server.endsWith("/")) server else "$server/")
                    scope.launch { repo.forgetSession(); repo.loadMeta(force = true); snackbar.showSnackbar("Zapisano adres serwera") }
                }) { Text("Zapisz") }
            }
            Spacer(Modifier.height(24.dp))
        }
    }

    code?.let { c ->
        AlertDialog(
            onDismissRequest = { code = null },
            title = { Text("Twój kod odzyskiwania") },
            text = {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Surface(color = MaterialTheme.colorScheme.surfaceContainerHigh, shape = MaterialTheme.shapes.medium) {
                        Text(c, style = Mono.copy(fontSize = MaterialTheme.typography.titleMedium.fontSize), modifier = Modifier.padding(12.dp))
                    }
                    Spacer(Modifier.height(8.dp))
                    Text("Zapisz go w bezpiecznym miejscu (np. menedżer haseł). Pokazujemy go tylko teraz — serwer przechowuje jedynie jego skrót. Nie udostępniaj go nikomu.", style = MaterialTheme.typography.bodySmall)
                }
            },
            confirmButton = {
                Button(onClick = {
                    val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                    cm.setPrimaryClip(ClipData.newPlainText("Kod Findini", c))
                    code = null
                }) { Text("Kopiuj i zamknij") }
            },
            dismissButton = { TextButton(onClick = { code = null }) { Text("Zapisałem") } },
        )
    }
    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text("Usunąć wszystkie dane?") },
            text = { Text("Usuniemy z serwera Twoje zgłoszenia, zdjęcia, roszczenia i rozmowy oraz zakończymy sesję. Osoby, z którymi rozmawiałeś, stracą dostęp do tych spraw. Tego nie da się cofnąć.") },
            confirmButton = {
                Button(onClick = {
                    confirmDelete = false
                    scope.launch {
                        when (val r = repo.private { deleteMe() }) {
                            is Outcome.Ok -> {
                                if (r.value.isSuccessful) {
                                    repo.forgetSession()
                                    context.app.drafts.clear()
                                    snackbar.showSnackbar("Dane usunięte z serwera")
                                    nav.navigate("home") { popUpTo(0) }
                                } else snackbar.showSnackbar("Nie udało się usunąć danych (${r.value.code()})")
                            }
                            is Outcome.Err -> snackbar.showSnackbar(r.error.message)
                        }
                    }
                }) { Text("Usuń na zawsze") }
            },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("Anuluj") } },
        )
    }
}

@Composable
fun RecoveryScreen(nav: NavController) {
    val context = LocalContext.current
    val repo = context.app.repo
    val scope = rememberCoroutineScope()
    var code by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var newCode by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    ScreenScaffold(title = "Przywróć dostęp", onBack = { nav.popBackStack() }) { mod ->
        Column(mod.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Wpisz kod odzyskiwania z poprzedniego telefonu.", style = MaterialTheme.typography.bodyLarge)
            InfoCard(
                null,
                "Po przywróceniu: stara sesja (np. na zgubionym telefonie) zostanie wylogowana, a kod — wymieniony na nowy. Zgłoszenia utworzone na tym telefonie przed przywróceniem pozostaną w poprzedniej sesji.",
                Tone.Info,
            )
            OutlinedTextField(code, { code = it.uppercase().take(29) }, label = { Text("Kod, np. 7K2M-QX9D-…") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            Button(onClick = {
                busy = true
                scope.launch {
                    when (val r = repo.recover(code)) {
                        is Outcome.Ok -> newCode = r.value.newRecoveryCode
                        is Outcome.Err -> error = r.error.message
                    }
                    busy = false
                }
            }, enabled = code.length >= 10 && !busy) { Text("Przywróć") }
        }
    }
    newCode?.let { c ->
        AlertDialog(
            onDismissRequest = {},
            title = { Text("Dostęp przywrócony") },
            text = {
                Column {
                    Text("Stary kod przestał działać. Zapisz nowy:")
                    Spacer(Modifier.height(8.dp))
                    Text(c, style = Mono.copy(fontSize = MaterialTheme.typography.titleMedium.fontSize))
                }
            },
            confirmButton = {
                Button(onClick = {
                    val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                    cm.setPrimaryClip(ClipData.newPlainText("Kod Findini", c))
                    newCode = null
                    nav.navigate("mine") { popUpTo("home") }
                }) { Text("Kopiuj i przejdź do moich spraw") }
            },
        )
    }
}
