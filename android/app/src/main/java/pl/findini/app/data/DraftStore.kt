package pl.findini.app.data

import android.content.Context
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/** Szkic zgłoszenia — zapisywany lokalnie po każdej zmianie, aby błąd sieci/zapisu nie kasował pracy. */
@Serializable
data class ReportDraft(
    val kind: String = "found",
    val photoPaths: List<String> = emptyList(),
    val uploadedPhotoIds: Map<String, String> = emptyMap(), // ścieżka lokalna -> id na serwerze
    val noPhoto: Boolean = false,
    val lat: Double? = null,
    val lon: Double? = null,
    val accuracyM: Int? = null,
    val uncertaintyM: Int = 0,
    val locationSource: String? = null,
    val areaLabel: String = "",
    val fromIso: String? = null,
    val toIso: String? = null,
    val category: String? = null,
    val attributes: Map<String, String> = emptyMap(),
    val colors: List<String> = emptyList(),
    val title: String = "",
    val description: String = "",
    val holding: String = "with_finder",
    val holdingNote: String = "",
    val secretDetails: String = "",
    val claimQuestion: String = "",
    val step: Int = 0,
    val editingReportId: String? = null,
)

class DraftStore(context: Context, private val json: Json) {
    private val prefs = context.getSharedPreferences("findini_drafts", Context.MODE_PRIVATE)

    fun load(): ReportDraft? = prefs.getString(KEY, null)?.let {
        runCatching { json.decodeFromString(ReportDraft.serializer(), it) }.getOrNull()
    }

    fun save(d: ReportDraft) {
        prefs.edit().putString(KEY, json.encodeToString(ReportDraft.serializer(), d)).apply()
    }

    fun clear() {
        prefs.edit().remove(KEY).apply()
    }

    companion object {
        private const val KEY = "report_draft"
    }
}
