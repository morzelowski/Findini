package pl.findini.app.ui.screens

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AddPhotoAlternate
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.HelpOutline
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
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
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import coil3.compose.AsyncImage
import kotlinx.coroutines.launch
import pl.findini.app.app
import pl.findini.app.data.AppError
import pl.findini.app.data.ClaimCreate
import pl.findini.app.data.ClaimForm
import pl.findini.app.data.Outcome
import pl.findini.app.data.Report
import pl.findini.app.ui.components.ErrorState
import pl.findini.app.ui.components.InfoCard
import pl.findini.app.ui.components.LoadingBox
import pl.findini.app.ui.components.PhotoOrIcon
import pl.findini.app.ui.components.Tone
import pl.findini.app.util.Images

@Composable
fun ClaimScreen(nav: NavController, reportId: String) {
    val context = LocalContext.current
    val repo = context.app.repo
    val scope = rememberCoroutineScope()
    var form by remember { mutableStateOf<ClaimForm?>(null) }
    var report by remember { mutableStateOf<Report?>(null) }
    var myLost by remember { mutableStateOf<List<Report>>(emptyList()) }
    var error by remember { mutableStateOf<AppError?>(null) }
    var answer by remember { mutableStateOf("") }
    var proof by remember { mutableStateOf("") }
    var lostId by remember { mutableStateOf<String?>(null) }
    var evidence by remember { mutableStateOf<Pair<Uri, String?>?>(null) } // (podgląd, id na serwerze)
    var uploading by remember { mutableStateOf(false) }
    var sending by remember { mutableStateOf(false) }
    var reload by remember { mutableIntStateOf(0) }

    LaunchedEffect(reload) {
        error = null
        (repo.public { report(reportId) } as? Outcome.Ok)?.let { report = it.value }
        when (val r = repo.private { claimForm(reportId) }) {
            is Outcome.Ok -> form = r.value
            is Outcome.Err -> error = r.error
        }
        (repo.private { myReports() } as? Outcome.Ok)?.let { res ->
            myLost = res.value.items.filter { it.kind == "lost" && it.status == "active" }
            if (myLost.size == 1) lostId = myLost.first().id
        }
    }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) scope.launch {
            uploading = true
            val bytes = Images.prepare(context, uri)
            if (bytes != null) {
                when (val r = repo.uploadPhoto(bytes, "evidence")) {
                    is Outcome.Ok -> evidence = uri to r.value.id
                    is Outcome.Err -> error = r.error
                }
            }
            uploading = false
        }
    }

    ScreenScaffold(
        title = "To moja rzecz",
        onBack = { nav.popBackStack() },
        bottomBar = {
            form?.let { f ->
                BottomActions {
                    if (f.canClaim) {
                        Button(shape = MaterialTheme.shapes.small,
                            onClick = {
                                sending = true
                                scope.launch {
                                    val body = ClaimCreate(answer.trim(), proof.trim(), listOfNotNull(evidence?.second), lostId)
                                    when (val r = repo.private { createClaim(reportId, body) }) {
                                        is Outcome.Ok -> nav.navigate("case/${r.value.id}") { popUpTo("claim/$reportId") { inclusive = true } }
                                        is Outcome.Err -> error = r.error
                                    }
                                    sending = false
                                }
                            },
                            enabled = answer.trim().length >= 3 && !sending && !uploading,
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            if (sending) { CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp); Spacer(Modifier.width(8.dp)) }
                            Text("Wyślij prywatnie do znalazcy")
                        }
                    } else if (f.existingClaimId != null) {
                        Button(shape = MaterialTheme.shapes.small, onClick = { nav.navigate("case/${f.existingClaimId}") }, modifier = Modifier.fillMaxWidth()) { Text("Przejdź do swojej sprawy") }
                    }
                }
            }
        },
    ) { mod ->
        when {
            form == null && error != null -> ErrorState(error!!, onRetry = { reload++ }, modifier = mod)
            form == null -> LoadingBox(modifier = mod)
            else -> Column(
                mod.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                val f = form!!
                report?.let { r ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        PhotoOrIcon(r, repo::absolute, Modifier.size(64.dp))
                        Spacer(Modifier.width(12.dp))
                        Column {
                            Text(r.title, style = MaterialTheme.typography.titleMedium)
                            Text(r.area.label ?: "Polska", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
                if (!f.canClaim) {
                    InfoCard(null, f.reason ?: "Nie możesz złożyć roszczenia.", Tone.Warning)
                    return@Column
                }
                Surface(color = MaterialTheme.colorScheme.secondaryContainer, shape = MaterialTheme.shapes.medium) {
                    Row(Modifier.padding(14.dp)) {
                        Icon(Icons.Outlined.HelpOutline, null)
                        Spacer(Modifier.width(10.dp))
                        Column {
                            Text(if (f.customQuestion) "Pytanie od znalazcy" else "Opisz ukryty szczegół", style = MaterialTheme.typography.labelLarge)
                            Text(f.question, style = MaterialTheme.typography.titleMedium)
                        }
                    }
                }
                OutlinedTextField(
                    value = answer,
                    onValueChange = { answer = it.take(500) },
                    label = { Text("Twoja odpowiedź") },
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = proof,
                    onValueChange = { proof = it.take(1000) },
                    label = { Text("Dodatkowe szczegóły (opcjonalnie)") },
                    supportingText = { Text("Np. gdzie i kiedy zgubiłeś, co było w środku, charakterystyczne ślady.") },
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text("Zdjęcie jako dowód (opcjonalnie, prywatne)", style = MaterialTheme.typography.titleSmall)
                Text(
                    "Np. Twoje starsze zdjęcie z tą rzeczą lub paragon. Zobaczy je tylko znalazca — nie trafia do wyszukiwarki ani analizy AI. Zakryj dane osobowe.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (evidence != null) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        AsyncImage(evidence!!.first, "Zdjęcie dowodu", contentScale = ContentScale.Fit, modifier = Modifier.size(88.dp).clip(MaterialTheme.shapes.medium))
                        IconButton(onClick = {
                            val id = evidence?.second
                            evidence = null
                            if (id != null) scope.launch { repo.private { deletePhoto(id) } }
                        }) { Icon(Icons.Outlined.Delete, "Usuń zdjęcie dowodu") }
                    }
                } else {
                    OutlinedButton(shape = MaterialTheme.shapes.small, onClick = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }, enabled = !uploading) {
                        if (uploading) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp) else Icon(Icons.Outlined.AddPhotoAlternate, null)
                        Spacer(Modifier.width(6.dp)); Text("Dodaj zdjęcie z galerii")
                    }
                }
                if (myLost.isNotEmpty()) {
                    Text("Powiąż ze swoim zgłoszeniem zguby (zamkniemy je po odbiorze)", style = MaterialTheme.typography.titleSmall)
                    myLost.forEach { l ->
                        FilterChip(selected = lostId == l.id, onClick = { lostId = if (lostId == l.id) null else l.id }, label = { Text(l.title) })
                    }
                }
                InfoCard(null, f.notice, Tone.Privacy)
                error?.let { Text(it.message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium) }
                Spacer(Modifier.height(16.dp))
            }
        }
    }
}
