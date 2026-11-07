package pl.findini.app

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import coil3.ImageLoader
import coil3.PlatformContext
import coil3.SingletonImageLoader
import coil3.network.okhttp.OkHttpNetworkFetcherFactory
import coil3.request.crossfade
import org.maplibre.android.MapLibre
import pl.findini.app.data.DraftStore
import pl.findini.app.data.Repository
import pl.findini.app.work.UpdatesWorker
import java.util.concurrent.TimeUnit

class FindiniApp : Application(), SingletonImageLoader.Factory {
    lateinit var repo: Repository
        private set
    lateinit var drafts: DraftStore
        private set

    override fun onCreate() {
        super.onCreate()
        repo = Repository(this)
        drafts = DraftStore(this, repo.json)
        MapLibre.getInstance(this)
        createChannel()
        scheduleUpdates(this)
    }

    override fun newImageLoader(context: PlatformContext): ImageLoader =
        ImageLoader.Builder(context)
            // Ten sam klient co API: prywatne zdjęcia (dowody) wymagają tokenu sesji.
            .components { add(OkHttpNetworkFetcherFactory(callFactory = { repo.http })) }
            .crossfade(true)
            .build()

    private fun createChannel() {
        val nm = getSystemService(NotificationManager::class.java)
        val ch = NotificationChannel(CHANNEL_ID, getString(R.string.notif_channel_matches), NotificationManager.IMPORTANCE_DEFAULT)
        ch.description = getString(R.string.notif_channel_desc)
        nm.createNotificationChannel(ch)
    }

    companion object {
        const val CHANNEL_ID = "matches"

        /** Sprawdzanie nowych dopasowań i wiadomości co ~30 min (bez lokalizacji, tylko przy sieci). */
        fun scheduleUpdates(context: Context) {
            val req = PeriodicWorkRequestBuilder<UpdatesWorker>(30, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork("updates", ExistingPeriodicWorkPolicy.KEEP, req)
        }
    }
}

val Context.app: FindiniApp get() = applicationContext as FindiniApp
