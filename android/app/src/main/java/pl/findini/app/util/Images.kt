package pl.findini.app.util

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.InputStream

/**
 * Przygotowanie zdjęcia na telefonie: obrót wg EXIF, zmniejszenie do 2048 px, ponowne
 * zakodowanie do JPEG — nowy plik NIE zawiera metadanych (GPS, model aparatu).
 * Serwer i tak usuwa metadane drugi raz.
 */
object Images {
    private const val MAX_SIDE = 2048

    suspend fun prepare(context: Context, uri: Uri): ByteArray? = withContext(Dispatchers.IO) {
        runCatching {
            val rotation = context.contentResolver.openInputStream(uri)?.use { readRotation(it) } ?: 0
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
            if (bounds.outWidth <= 0) return@runCatching null
            var sample = 1
            while (bounds.outWidth / (sample * 2) >= MAX_SIDE || bounds.outHeight / (sample * 2) >= MAX_SIDE) sample *= 2
            val opts = BitmapFactory.Options().apply { inSampleSize = sample }
            val bmp = context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, opts) }
                ?: return@runCatching null
            encode(scaleAndRotate(bmp, rotation))
        }.getOrNull()
    }

    suspend fun prepare(file: File): ByteArray? = withContext(Dispatchers.IO) {
        runCatching {
            val rotation = file.inputStream().use { readRotation(it) }
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(file.absolutePath, bounds)
            var sample = 1
            while (bounds.outWidth / (sample * 2) >= MAX_SIDE || bounds.outHeight / (sample * 2) >= MAX_SIDE) sample *= 2
            val bmp = BitmapFactory.decodeFile(file.absolutePath, BitmapFactory.Options().apply { inSampleSize = sample })
                ?: return@runCatching null
            encode(scaleAndRotate(bmp, rotation))
        }.getOrNull()
    }

    private fun readRotation(input: InputStream): Int = when (
        ExifInterface(input).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
    ) {
        ExifInterface.ORIENTATION_ROTATE_90 -> 90
        ExifInterface.ORIENTATION_ROTATE_180 -> 180
        ExifInterface.ORIENTATION_ROTATE_270 -> 270
        else -> 0
    }

    private fun scaleAndRotate(src: Bitmap, rotation: Int): Bitmap {
        val scale = minOf(1f, MAX_SIDE.toFloat() / maxOf(src.width, src.height))
        if (scale == 1f && rotation == 0) return src
        val m = Matrix().apply {
            postScale(scale, scale)
            postRotate(rotation.toFloat())
        }
        return Bitmap.createBitmap(src, 0, 0, src.width, src.height, m, true)
    }

    private fun encode(bmp: Bitmap): ByteArray = ByteArrayOutputStream().use { out ->
        bmp.compress(Bitmap.CompressFormat.JPEG, 85, out)
        out.toByteArray()
    }

    /** Zapis do prywatnego katalogu aplikacji (szkic formularza przetrwa zamknięcie aplikacji). */
    suspend fun saveDraftPhoto(context: Context, bytes: ByteArray): File = withContext(Dispatchers.IO) {
        val dir = File(context.filesDir, "drafts").apply { mkdirs() }
        File(dir, "photo_${System.currentTimeMillis()}.jpg").apply { writeBytes(bytes) }
    }
}
