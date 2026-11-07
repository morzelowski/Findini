package pl.findini.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.outlined.Block
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.ExpandLess
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material.icons.outlined.Flag
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.MoreVert
import androidx.compose.material.icons.outlined.Shield
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import coil3.compose.AsyncImage
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import pl.findini.app.app
import pl.findini.app.data.AbuseIn
import pl.findini.app.data.AppError
import pl.findini.app.data.Case
import pl.findini.app.data.ChatMessage
import pl.findini.app.data.HandoverIn
import pl.findini.app.data.MessageIn
import pl.findini.app.data.NoteIn
import pl.findini.app.data.Outcome
import pl.findini.app.data.ReadIn
import pl.findini.app.ui.components.ErrorState
import pl.findini.app.ui.components.InfoCard
import pl.findini.app.ui.components.KeyValue
import pl.findini.app.ui.components.LoadingBox
import pl.findini.app.ui.components.PhotoOrIcon
import pl.findini.app.ui.components.Tone
import pl.findini.app.ui.theme.Mono
import pl.findini.app.util.Format

@Composable
fun CaseScreen(nav: NavController, id: String, snackbar: SnackbarHostState) {
    val context = LocalContext.current
    val repo = context.app.repo
    val scope = rememberCoroutineScope()
    var case by remember { mutableStateOf<Case?>(null) }
    var error by remember { mutableStateOf<AppError?>(null) }
    var messages by remember { mutableStateOf<List<ChatMessage>>(emptyList()) }
    var input by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var reload by remember { mutableIntStateOf(0) }
    var menu by remember { mutableStateOf(false) }
    var dialog by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val listState = rememberLazyListState()

    suspend fun refreshCase() {
        when (val r = repo.private { case(id) }) {
            is Outcome.Ok -> { case = r.value; error = null }
            is Outcome.Err -> if (case == null) error = r.error
        }
    }

    LaunchedEffect(id, reload) { refreshCase() }
    // Odpytywanie co 4 s, gdy ekran jest otwarty (bez stałego połączenia w tle).
    LaunchedEffect(id) {
        var tick = 0
        while (isActive) {
            val after = messages.lastOrNull()?.id ?: 0
            (repo.private { messages(id, after) } as? Outcome.Ok)?.let { res ->
                if (res.value.items.isNotEmpty()) {
                    messages = (messages + res.value.items).distinctBy { it.id }
                    repo.private { markRead(id, ReadIn(messages.last().id)) }
                    if (res.value.items.any { it.kind == "system" }) refreshCase()
                }
                if (case != null && res.value.status != case!!.status) refreshCase()
            }
            tick++
            delay(4000)
        }
    }
    LaunchedEffect(messages.size) { if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size + 1) }

    fun act(block: suspend () -> Outcome<Case>, ok: String? = null) {
        if (busy) return
        busy = true
        scope.launch {
            when (val r = block()) {
                is Outcome.Ok -> { case = r.value; ok?.let { snackbar.showSnackbar(it) } }
                is Outcome.Err -> snackbar.showSnackbar(r.error.message)
            }
            busy = false
        }
    }

    ScreenScaffold(
        title = case?.let { if (it.isFinder) "Ocena roszczenia" else "Twoje roszczenie" } ?: "Sprawa",
        onBack = { nav.popBackStack() },
        actions = {
            IconButton(onClick = { menu = true }) { Icon(Icons.Outlined.MoreVert, "Więcej opcji") }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                DropdownMenuItem(text = { Text("Zablokuj kontakt") }, leadingIcon = { Icon(Icons.Outlined.Block, null) }, onClick = { menu = false; dialog = "block" })
                DropdownMenuItem(text = { Text("Zgłoś nadużycie") }, leadingIcon = { Icon(Icons.Outlined.Flag, null) }, onClick = { menu = false; dialog = "abuse" })
            }
        },
    ) { mod ->
        when {
            error != null -> ErrorState(error!!, onRetry = { reload++ }, modifier = mod)
            case == null -> LoadingBox(modifier = mod)
            else -> {
                val c = case!!
                Column(mod.fillMaxSize().imePadding()) {
                    LazyColumn(
                        state = listState,
                        modifier = Modifier.weight(1f),
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        item { CaseHeader(c, repo::absolute) { nav.navigate(if (c.isFinder) "myreport/${c.report.id}" else "report/${c.report.id}") } }
                        item { CasePanel(c, busy, repo::absolute, ::act, repo) }
                        items(messages, key = { it.id }) { m -> Bubble(m) }
                    }
                    if (c.canMessage) {
                        HorizontalDivider()
                        Row(Modifier.fillMaxWidth().navigationBarsPadding().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            OutlinedTextField(
                                value = input,
                                onValueChange = { input = it.take(1000) },
                                placeholder = { Text("Napisz wiadomość…") },
                                modifier = Modifier.weight(1f),
                                maxLines = 4,
                                shape = MaterialTheme.shapes.extraLarge,
                            )
                            Spacer(Modifier.width(8.dp))
                            FilledIconButton(
                                onClick = {
                                    val text = input.trim()
                                    if (text.isEmpty() || sending) return@FilledIconButton
                                    sending = true
                                    scope.launch {
                                        when (val r = repo.private { sendMessage(id, MessageIn(text)) }) {
                                            is Outcome.Ok -> { input = ""; messages = (messages + r.value).distinctBy { it.id } }
                                            is Outcome.Err -> snackbar.showSnackbar(r.error.message) // treść zostaje w polu
                                        }
                                        sending = false
                                    }
                                },
                                enabled = input.isNotBlank() && !sending,
                            ) { Icon(Icons.AutoMirrored.Filled.Send, "Wyślij") }
                        }
                    }
                }
            }
        }
    }

    when (dialog) {
        "block" -> AlertDialog(
            onDismissRequest = { dialog = null },
            title = { Text("Zablokować kontakt?") },
            text = { Text("Rozmowa zostanie zamknięta, a ta osoba nie złoży więcej roszczeń do Twoich zgłoszeń. Jeśli coś było niepokojące — zgłoś też nadużycie.") },
            confirmButton = { Button(onClick = { dialog = null; act({ repo.private { block(id) } }, "Kontakt zablokowany") }) { Text("Zablokuj") } },
            dismissButton = { TextButton(onClick = { dialog = null }) { Text("Anuluj") } },
        )
        "abuse" -> AbuseDialog(onDismiss = { dialog = null }) { reason, details ->
            dialog = null
            scope.launch {
                when (val r = repo.private { reportAbuse(AbuseIn("claim", id, reason, details)) }) {
                    is Outcome.Ok -> snackbar.showSnackbar(r.value.message)
                    is Outcome.Err -> snackbar.showSnackbar(r.error.message)
                }
            }
        }
    }
}

@Composable
private fun CaseHeader(c: Case, imageUrl: (String) -> String, onOpen: () -> Unit) {
    val steps = listOf("Złożone", "Zaakceptowane", "Przekazane", "Zakończone")
    val idx = when (c.status) {
        "pending" -> 0
        "accepted" -> if (c.finderConfirmed || c.ownerConfirmed) 2 else 1
        "returned" -> 3
        else -> -1
    }
    Surface(color = MaterialTheme.colorScheme.surfaceContainerLowest, shape = MaterialTheme.shapes.large, onClick = onOpen) {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                PhotoOrIcon(c.report, imageUrl, Modifier.size(56.dp))
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(c.report.title, style = MaterialTheme.typography.titleMedium)
                    Text(
                        c.statusLabel,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }
            }
            if (idx >= 0) {
                Spacer(Modifier.height(12.dp))
                Row(Modifier.fillMaxWidth().semantics(mergeDescendants = true) { contentDescription = "Etap: ${steps[idx]}, ${idx + 1} z 4" }) {
                    steps.forEachIndexed { i, s ->
                        Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                            Box(
                                Modifier.size(24.dp).clip(CircleShape)
                                    .background(if (i <= idx) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant),
                                contentAlignment = Alignment.Center,
                            ) {
                                if (i <= idx) Icon(Icons.Outlined.Check, null, Modifier.size(16.dp), tint = MaterialTheme.colorScheme.onPrimary)
                                else Text("${i + 1}", style = MaterialTheme.typography.labelSmall)
                            }
                            Text(s, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
            c.closeReason?.let { Text(it, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 8.dp)) }
        }
    }
}

@Composable
private fun CasePanel(c: Case, busy: Boolean, imageUrl: (String) -> String, act: (suspend () -> Outcome<Case>, String?) -> Unit, repo: pl.findini.app.data.Repository) {
    var code by remember { mutableStateOf("") }
    var tipsOpen by remember { mutableStateOf(c.status == "accepted") }
    var rejectNote by remember { mutableStateOf<String?>(null) }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        // Odpowiedź i dowody (znalazca ocenia; osoba odbierająca widzi, co wysłała).
        Surface(color = MaterialTheme.colorScheme.surfaceContainer, shape = MaterialTheme.shapes.medium) {
            Column(Modifier.padding(14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.Lock, null, Modifier.size(16.dp), tint = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.width(6.dp))
                    Text("Prywatne — widzicie tylko wy dwoje", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                c.question?.let { KeyValue("Pytanie", it) }
                KeyValue(if (c.isFinder) "Odpowiedź" else "Twoja odpowiedź", c.answer)
                if (c.proofDetails.isNotBlank()) KeyValue("Szczegóły", c.proofDetails)
                if (c.isFinder) KeyValue("Twój ukryty szczegół", c.secretDetails ?: "— (nie podano)")
                c.evidencePhotos.forEach { p ->
                    AsyncImage(imageUrl(p.url), "Zdjęcie dowodu", contentScale = ContentScale.Crop, modifier = Modifier.padding(top = 6.dp).fillMaxWidth().height(180.dp).clip(MaterialTheme.shapes.medium))
                }
                c.finderNote?.let { KeyValue("Notatka znalazcy", it) }
            }
        }
        when {
            c.isFinder && c.status == "pending" -> {
                InfoCard(
                    "Twoja decyzja",
                    "Porównaj odpowiedź ze swoim ukrytym szczegółem. Możesz dopytać w rozmowie. Odpowiedź nie jest dowodem tożsamości — jeśli masz wątpliwości, nie wydawaj przedmiotu.",
                    Tone.Info,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { act({ repo.private { accept(c.id, NoteIn(null)) } }, "Zaakceptowano — umówcie przekazanie") }, enabled = !busy, modifier = Modifier.weight(1f)) { Text("Akceptuj") }
                    OutlinedButton(onClick = { rejectNote = "" }, enabled = !busy, modifier = Modifier.weight(1f)) { Text("Odrzuć") }
                }
            }
            c.isFinder && c.status == "accepted" -> {
                Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = MaterialTheme.shapes.medium) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Przy spotkaniu poproś o kod przekazania", style = MaterialTheme.typography.titleSmall)
                        Text("Kod ma tylko osoba, której roszczenie zaakceptowałeś. Potwierdza spotkanie z właściwą osobą z aplikacji — nie dowodzi własności.", style = MaterialTheme.typography.bodySmall)
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            OutlinedTextField(
                                value = code,
                                onValueChange = { v -> code = v.filter { it.isDigit() }.take(6) },
                                label = { Text("Kod (6 cyfr)") },
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                                singleLine = true,
                                modifier = Modifier.weight(1f),
                            )
                            Spacer(Modifier.width(8.dp))
                            Button(onClick = { act({ repo.private { handover(c.id, HandoverIn(code)) } }, null) }, enabled = code.length == 6 && !busy) { Text("Wydaję") }
                        }
                        c.handoverAttemptsLeft?.let { Text("Pozostałe próby: $it", style = MaterialTheme.typography.labelSmall) }
                        if (c.finderConfirmed) Text("Potwierdziłeś wydanie. Czekamy na potwierdzenie odbioru przez drugą stronę.", style = MaterialTheme.typography.bodySmall)
                        else TextButton(onClick = { act({ repo.private { handover(c.id, HandoverIn(null)) } }, "Zapisano — czekamy na potwierdzenie odbioru") }) {
                            Text("Wydałem bez kodu (odbiorca potwierdzi w aplikacji)")
                        }
                        TextButton(onClick = { rejectNote = "" }) { Text("Cofnij akceptację (np. brak kontaktu)") }
                    }
                }
            }
            !c.isFinder && c.status == "pending" -> {
                InfoCard("Czekasz na decyzję znalazcy", "Znalazca porówna Twoją odpowiedź ze szczegółem, który zna tylko on. Możesz napisać wiadomość poniżej.", Tone.Info)
                TextButton(onClick = { act({ repo.private { withdraw(c.id) } }, "Roszczenie wycofane") }) { Text("Wycofaj roszczenie") }
            }
            !c.isFinder && c.status == "accepted" -> {
                Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = MaterialTheme.shapes.medium) {
                    Column(Modifier.padding(16.dp).fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("Twój kod przekazania", style = MaterialTheme.typography.titleSmall)
                        Text(
                            c.handoverCode?.chunked(3)?.joinToString(" ") ?: "—",
                            style = Mono,
                            modifier = Modifier.semantics { contentDescription = "Kod przekazania: " + (c.handoverCode?.toList()?.joinToString(" ") ?: "") },
                        )
                        Text("Pokaż go znalazcy dopiero przy spotkaniu, gdy zobaczysz swoją rzecz.", style = MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.height(8.dp))
                        Button(onClick = { act({ repo.private { confirmReceived(c.id) } }, "Dziękujemy za potwierdzenie") }, enabled = !busy && !c.ownerConfirmed) {
                            Text(if (c.ownerConfirmed) "Potwierdziłeś odbiór" else "Odebrałem przedmiot")
                        }
                        TextButton(onClick = { act({ repo.private { withdraw(c.id) } }, "Roszczenie wycofane") }) { Text("Wycofaj roszczenie") }
                    }
                }
            }
            c.status == "returned" -> {
                InfoCard("Przedmiot wrócił do właściciela", "Sprawa zamknięta. Dziękujemy za życzliwość!", Tone.Success)
                if (!c.isFinder) {
                    if (c.thanked) Text("❤ Podziękowanie wysłane", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.secondary)
                    else Button(onClick = { act({ repo.private { thanks(c.id) } }, "Wysłano podziękowanie ❤") }, enabled = !busy) {
                        Icon(Icons.Outlined.Favorite, null); Spacer(Modifier.width(6.dp)); Text("Podziękuj znalazcy")
                    }
                    Text("Serduszko to gest wdzięczności, nie ocena uczciwości.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            else -> InfoCard(null, c.closeReason ?: c.statusLabel, Tone.Info)
        }
        Surface(color = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.6f), shape = MaterialTheme.shapes.medium, onClick = { tipsOpen = !tipsOpen }) {
            Column(Modifier.padding(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.Shield, null)
                    Spacer(Modifier.width(8.dp))
                    Text("Bezpieczne przekazanie", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                    Icon(if (tipsOpen) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore, if (tipsOpen) "Zwiń" else "Rozwiń")
                }
                if (tipsOpen) c.safetyTips.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 4.dp)) }
            }
        }
        if (c.blocked) InfoCard(null, "Kontakt w tej sprawie jest zablokowany.", Tone.Warning)
        Text("Rozmowa", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 4.dp))
    }
    rejectNote?.let { note ->
        AlertDialog(
            onDismissRequest = { rejectNote = null },
            title = { Text(if (c.status == "accepted") "Cofnąć akceptację?" else "Odrzucić roszczenie?") },
            text = {
                OutlinedTextField(note, { rejectNote = it.take(300) }, label = { Text("Krótka informacja dla tej osoby (opcjonalnie)") })
            },
            confirmButton = {
                Button(onClick = {
                    val n = rejectNote
                    rejectNote = null
                    act({ repo.private { reject(c.id, NoteIn(n?.ifBlank { null })) } }, "Zapisano decyzję")
                }) { Text("Potwierdź") }
            },
            dismissButton = { TextButton(onClick = { rejectNote = null }) { Text("Anuluj") } },
        )
    }
}

@Composable
private fun Bubble(m: ChatMessage) {
    if (m.kind == "system") {
        Text(
            m.body,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 4.dp),
        )
        return
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (m.mine) Arrangement.End else Arrangement.Start) {
        Surface(
            color = if (m.mine) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceContainerHigh,
            contentColor = if (m.mine) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
            shape = RoundedCornerShape(18.dp, 18.dp, if (m.mine) 4.dp else 18.dp, if (m.mine) 18.dp else 4.dp),
            modifier = Modifier.widthIn(max = 300.dp).semantics(mergeDescendants = true) {
                contentDescription = (if (m.mine) "Ty: " else "Druga strona: ") + m.body
            },
        ) {
            Column(Modifier.padding(horizontal = 14.dp, vertical = 8.dp)) {
                Text(m.body, style = MaterialTheme.typography.bodyMedium)
                Format.parse(m.createdAt)?.let { Text(Format.time(it), style = MaterialTheme.typography.labelSmall) }
            }
        }
    }
}
