package pl.findini.app

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AddCircle
import androidx.compose.material.icons.outlined.Inventory2
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import androidx.navigation.navDeepLink
import pl.findini.app.data.Outcome
import pl.findini.app.ui.components.OfflineBanner
import pl.findini.app.ui.screens.CaseScreen
import pl.findini.app.ui.screens.ClaimScreen
import pl.findini.app.ui.screens.CreateScreen
import pl.findini.app.ui.screens.DetailScreen
import pl.findini.app.ui.screens.HomeScreen
import pl.findini.app.ui.screens.MineScreen
import pl.findini.app.ui.screens.MyReportScreen
import pl.findini.app.ui.screens.NewReportSheet
import pl.findini.app.ui.screens.PhotoSearchScreen
import pl.findini.app.ui.screens.RecoveryScreen
import pl.findini.app.ui.screens.SettingsScreen
import pl.findini.app.ui.theme.FindiniTheme
import pl.findini.app.util.Connectivity

class MainActivity : ComponentActivity() {
    private val openTarget = mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        openTarget.value = intent?.getStringExtra(EXTRA_OPEN)
        setContent {
            FindiniTheme {
                FindiniRoot(openTarget.value) { openTarget.value = null }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        openTarget.value = intent.getStringExtra(EXTRA_OPEN) ?: intent.data?.let { "report/" + it.lastPathSegment }
    }

    companion object {
        const val EXTRA_OPEN = "open"
    }
}

private val TOP_LEVEL = setOf("home", "mine")

@Composable
fun FindiniRoot(openTarget: String?, consumed: () -> Unit) {
    val nav = rememberNavController()
    val context = LocalContext.current
    val repo = context.app.repo
    val snackbar = remember { SnackbarHostState() }
    val online by Connectivity.observe(context).collectAsState(initial = true)
    var showNewSheet by remember { mutableStateOf(false) }
    var unread by remember { mutableIntStateOf(0) }
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route

    LaunchedEffect(Unit) {
        repo.loadMeta()
        repo.events.collect { snackbar.showSnackbar(it) }
    }
    LaunchedEffect(route) {
        if (repo.hasSession && route in TOP_LEVEL) {
            (repo.private { me() } as? Outcome.Ok)?.let { unread = it.value.unread }
        }
    }
    LaunchedEffect(online) { if (online && repo.meta.value == null) repo.loadMeta() }
    LaunchedEffect(openTarget) {
        if (openTarget != null) {
            nav.navigate(openTarget) { launchSingleTop = true }
            consumed()
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            if (route in TOP_LEVEL) {
                NavigationBar(containerColor = MaterialTheme.colorScheme.surfaceContainerLow) {
                    val itemColors = NavigationBarItemDefaults.colors(
                        selectedIconColor = MaterialTheme.colorScheme.onSecondaryContainer,
                        selectedTextColor = MaterialTheme.colorScheme.primary,
                        indicatorColor = MaterialTheme.colorScheme.secondaryContainer,
                    )
                    NavigationBarItem(
                        selected = route == "home",
                        onClick = { nav.navigate("home") { popUpTo("home") { inclusive = true }; launchSingleTop = true } },
                        icon = { Icon(Icons.Outlined.Search, null) },
                        label = { Text("Szukaj") },
                        colors = itemColors,
                    )
                    NavigationBarItem(
                        selected = false,
                        onClick = { showNewSheet = true },
                        icon = { Icon(Icons.Outlined.AddCircle, null) },
                        label = { Text("Zgłoś") },
                        colors = itemColors,
                    )
                    NavigationBarItem(
                        selected = route == "mine",
                        onClick = { nav.navigate("mine") { popUpTo("home"); launchSingleTop = true } },
                        icon = {
                            BadgedBox(badge = { if (unread > 0) Badge { Text(unread.toString()) } }) {
                                Icon(Icons.Outlined.Inventory2, null)
                            }
                        },
                        label = { Text("Moje sprawy") },
                        colors = itemColors,
                    )
                }
            }
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(bottom = padding.calculateBottomPadding())) {
            OfflineBanner(!online)
            FindiniNavHost(nav, snackbar)
        }
    }
    if (showNewSheet) {
        NewReportSheet(
            onDismiss = { showNewSheet = false },
            onPick = { kind ->
                showNewSheet = false
                nav.navigate("create?kind=$kind")
            },
        )
    }
}

@Composable
private fun FindiniNavHost(nav: NavHostController, snackbar: SnackbarHostState) {
    NavHost(nav, startDestination = "home", enterTransition = { fadeIn() }, exitTransition = { fadeOut() }) {
        composable("home") { HomeScreen(nav) }
        composable(
            "report/{id}",
            arguments = listOf(navArgument("id") { type = NavType.StringType }),
            deepLinks = listOf(navDeepLink { uriPattern = "findini://report/{id}" }),
        ) { DetailScreen(nav, it.arguments?.getString("id")!!, snackbar) }
        composable(
            "create?kind={kind}&edit={edit}&from={from}",
            arguments = listOf(
                navArgument("kind") { type = NavType.StringType; defaultValue = "found" },
                navArgument("edit") { type = NavType.StringType; nullable = true; defaultValue = null },
                navArgument("from") { type = NavType.StringType; nullable = true; defaultValue = null },
            ),
        ) {
            CreateScreen(
                nav,
                kind = it.arguments?.getString("kind") ?: "found",
                editId = it.arguments?.getString("edit"),
                fromReportId = it.arguments?.getString("from"),
            )
        }
        composable("mine") { MineScreen(nav) }
        composable("myreport/{id}") { MyReportScreen(nav, it.arguments?.getString("id")!!, snackbar) }
        composable("claim/{id}") { ClaimScreen(nav, it.arguments?.getString("id")!!) }
        composable("case/{id}") { CaseScreen(nav, it.arguments?.getString("id")!!, snackbar) }
        composable("photosearch") { PhotoSearchScreen(nav) }
        composable("recovery") { RecoveryScreen(nav) }
        composable("settings") { SettingsScreen(nav, snackbar) }
    }
}
