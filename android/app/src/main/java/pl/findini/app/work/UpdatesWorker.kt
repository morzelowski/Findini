package pl.findini.app.work

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import pl.findini.app.FindiniApp
import pl.findini.app.MainActivity
import pl.findini.app.R
import pl.findini.app.app
import pl.findini.app.data.Outcome

/**
 * Okresowe sprawdzenie (bez lokalizacji): nowe dopasowania do moich zgłoszeń i nowe wiadomości.
 * Nie tworzy sesji — jeśli użytkownik nic nie zgłosił, nie ma czego sprawdzać.
 */
class UpdatesWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val repo = applicationContext.app.repo
        if (!repo.hasSession) return Result.success()
        val since = repo.lastUpdatesCheck
        val r = repo.private { updates(since) }
        if (r !is Outcome.Ok) return Result.retry()
        val u = r.value
        repo.lastUpdatesCheck = u.serverTime
        val lines = buildList {
            if (u.newMatches > 0) add("Nowe możliwe dopasowania: ${u.newMatches}")
            if (u.unreadCases > 0) add("Nieprzeczytane sprawy: ${u.unreadCases}")
        }
        if (since != null && lines.isNotEmpty()) notify(lines.joinToString(" · "))
        return Result.success()
    }

    private fun notify(text: String) {
        val ctx = applicationContext
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED &&
            android.os.Build.VERSION.SDK_INT >= 33
        ) return
        val intent = Intent(ctx, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(MainActivity.EXTRA_OPEN, "mine")
        }
        val pi = PendingIntent.getActivity(ctx, 1, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n = NotificationCompat.Builder(ctx, FindiniApp.CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("Findini")
            .setContentText(text)
            .setContentIntent(pi)
            .setAutoCancel(true)
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(42, n) }
    }
}
