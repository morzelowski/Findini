package pl.findini.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

// ---------------------------------------------------------------- odpowiedzi

@Serializable
data class PhotoRef(
    val id: String,
    val url: String,
    @SerialName("thumb_url") val thumbUrl: String,
    val width: Int = 0,
    val height: Int = 0,
)

@Serializable
data class AttrValue(val key: String, val label: String, val value: JsonElement) {
    val text: String get() = (value as? JsonPrimitive)?.contentOrNull ?: value.toString()
}

@Serializable
data class Area(
    val lat: Double,
    val lon: Double,
    @SerialName("radius_m") val radiusM: Int,
    val label: String? = null,
)

@Serializable
data class MatchInfo(
    val tier: String? = null,
    val visual: String? = null,
    val reasons: List<String> = emptyList(),
    val warnings: List<String> = emptyList(),
)

@Serializable
data class PrivateInfo(
    @SerialName("exact_lat") val exactLat: Double,
    @SerialName("exact_lon") val exactLon: Double,
    @SerialName("accuracy_m") val accuracyM: Int? = null,
    @SerialName("uncertainty_m") val uncertaintyM: Int = 0,
    @SerialName("location_source") val locationSource: String = "map",
    @SerialName("secret_details") val secretDetails: String? = null,
    @SerialName("claim_question") val claimQuestion: String? = null,
)

@Serializable
data class ClaimCounts(val open: Int = 0, val pending: Int = 0, val total: Int = 0)

@Serializable
data class PhotoStatus(val id: String, @SerialName("embedding_status") val embeddingStatus: String)

@Serializable
data class Report(
    val id: String,
    val kind: String,
    val status: String,
    val category: String,
    @SerialName("category_label") val categoryLabel: String,
    val title: String,
    val description: String = "",
    val attributes: List<AttrValue> = emptyList(),
    val colors: List<String> = emptyList(),
    @SerialName("occurred_from") val occurredFrom: String,
    @SerialName("occurred_to") val occurredTo: String,
    @SerialName("published_at") val publishedAt: String? = null,
    val area: Area,
    val holding: String? = null,
    @SerialName("holding_note") val holdingNote: String? = null,
    val photos: List<PhotoRef> = emptyList(),
    @SerialName("ai_indexed") val aiIndexed: Boolean = false,
    @SerialName("distance_m") val distanceM: Int? = null,
    val match: MatchInfo? = null,
    @SerialName("is_mine") val isMine: Boolean = false,
    // tylko dla właściciela
    val private: PrivateInfo? = null,
    @SerialName("expires_at") val expiresAt: String? = null,
    val hidden: Boolean = false,
    val claims: ClaimCounts? = null,
    @SerialName("photo_status") val photoStatus: List<PhotoStatus>? = null,
) {
    val isFound: Boolean get() = kind == "found"
    fun attr(key: String): String? = attributes.firstOrNull { it.key == key }?.text
}

@Serializable
data class SuggestionAction(val action: String, val label: String)

@Serializable
data class SearchResponse(
    val items: List<Report>,
    @SerialName("next_cursor") val nextCursor: String? = null,
    val sort: String = "newest",
    val suggestions: List<SuggestionAction> = emptyList(),
)

@Serializable
data class AreaCell(
    @SerialName("cell_id") val cellId: String,
    val lat: Double,
    val lon: Double,
    @SerialName("radius_m") val radiusM: Int,
    val count: Int,
    val lost: Int,
    val found: Int,
)

@Serializable
data class AreasResponse(val areas: List<AreaCell>, val note: String? = null)

@Serializable
data class MatchesResponse(
    val strong: List<Report> = emptyList(),
    val possible: List<Report> = emptyList(),
    @SerialName("weak_count") val weakCount: Int = 0,
    val notice: String? = null,
)

@Serializable
data class AttrDef(
    val key: String,
    val label: String,
    val type: String,
    val options: List<String> = emptyList(),
    @SerialName("max_len") val maxLen: Int = 40,
    val hint: String? = null,
)

@Serializable
data class CategoryDef(
    val key: String,
    val label: String,
    val icon: String,
    @SerialName("photo_allowed") val photoAllowed: Boolean = true,
    val tip: String? = null,
    val attributes: List<AttrDef> = emptyList(),
)

@Serializable
data class ColorDef(val key: String, val label: String, val hex: String)

@Serializable
data class LatLon(val lat: Double, val lon: Double)

@Serializable
data class Bounds(
    @SerialName("min_lat") val minLat: Double,
    @SerialName("max_lat") val maxLat: Double,
    @SerialName("min_lon") val minLon: Double,
    @SerialName("max_lon") val maxLon: Double,
)

@Serializable
data class Pilot(
    val name: String,
    val center: LatLon,
    val bounds: Bounds,
    @SerialName("grid_cell_m") val gridCellM: Int = 500,
)

@Serializable
data class Landmark(
    val key: String, val name: String, val lat: Double, val lon: Double,
    val region: String = "", val county: String = "",
) {
    val context: String get() = listOf(region, county).filter { it.isNotBlank() }.joinToString(" · ")
}

@Serializable
data class PlacesResponse(val items: List<Landmark> = emptyList())

@Serializable
data class AiStatus(val status: String)

@Serializable
data class Retention(
    @SerialName("active_days") val activeDays: Int = 60,
    @SerialName("purge_after_days") val purgeAfterDays: Int = 180,
)

@Serializable
data class Meta(
    val categories: List<CategoryDef>,
    val colors: List<ColorDef>,
    val pilot: Pilot,
    val landmarks: List<Landmark> = emptyList(),
    val ai: AiStatus = AiStatus("unknown"),
    @SerialName("safety_tips") val safetyTips: List<String> = emptyList(),
    val retention: Retention = Retention(),
) {
    fun category(key: String?): CategoryDef? = categories.firstOrNull { it.key == key }
    fun color(key: String): ColorDef? = colors.firstOrNull { it.key == key }
}

@Serializable
data class GuestInfo(val id: String, val alias: String, @SerialName("created_at") val createdAt: String? = null)

@Serializable
data class SessionResponse(
    val token: String,
    val guest: GuestInfo,
    val notice: String? = null,
    @SerialName("new_recovery_code") val newRecoveryCode: String? = null,
)

@Serializable
data class MeStats(
    @SerialName("active_reports") val activeReports: Int = 0,
    @SerialName("hearts_received") val heartsReceived: Int = 0,
    @SerialName("items_returned") val itemsReturned: Int = 0,
)

@Serializable
data class MeResponse(
    val guest: GuestInfo,
    @SerialName("has_recovery_code") val hasRecoveryCode: Boolean,
    val stats: MeStats = MeStats(),
    val unread: Int = 0,
    val notice: String? = null,
)

@Serializable
data class RecoveryCodeResponse(val code: String, val notice: String)

@Serializable
data class AiSuggestionAlt(val category: String, val subtype: String? = null)

@Serializable
data class AiSuggestion(
    val category: String,
    val subtype: String? = null,
    val alternative: AiSuggestionAlt? = null,
    val confidence: String = "uncertain",
    val colors: List<String> = emptyList(),
    @SerialName("colors_pl") val colorsPl: List<String> = emptyList(),
)

@Serializable
data class PhotoUpload(
    val id: String,
    val url: String,
    @SerialName("thumb_url") val thumbUrl: String,
    @SerialName("ai_status") val aiStatus: String,
    val suggestion: AiSuggestion? = null,
    val notice: String? = null,
)

@Serializable
data class PhotoSearchResponse(
    val items: List<Report>,
    @SerialName("no_convincing_match") val noConvincingMatch: Boolean,
    @SerialName("query_suggestion") val querySuggestion: AiSuggestion? = null,
    val notice: String,
)

@Serializable
data class ParsedPlace(val key: String, val name: String, val lat: Double, val lon: Double, @SerialName("radius_m") val radiusM: Int)

@Serializable
data class ParseResponse(
    val kind: String? = null,
    val category: String? = null,
    val subtype: String? = null,
    val colors: List<String> = emptyList(),
    val brand: String? = null,
    @SerialName("date_from") val dateFrom: String? = null,
    @SerialName("date_to") val dateTo: String? = null,
    val place: ParsedPlace? = null,
    val text: String? = null,
    val understood: List<String> = emptyList(),
)

@Serializable
data class ClaimForm(
    val question: String,
    @SerialName("custom_question") val customQuestion: Boolean,
    @SerialName("can_claim") val canClaim: Boolean,
    val reason: String? = null,
    @SerialName("existing_claim_id") val existingClaimId: String? = null,
    val notice: String,
)

@Serializable
data class Case(
    val id: String,
    val role: String,
    val status: String,
    @SerialName("status_label") val statusLabel: String,
    @SerialName("close_reason") val closeReason: String? = null,
    val report: Report,
    val answer: String,
    @SerialName("proof_details") val proofDetails: String = "",
    @SerialName("evidence_photos") val evidencePhotos: List<PhotoRef> = emptyList(),
    @SerialName("finder_note") val finderNote: String? = null,
    @SerialName("finder_confirmed") val finderConfirmed: Boolean = false,
    @SerialName("owner_confirmed") val ownerConfirmed: Boolean = false,
    @SerialName("created_at") val createdAt: String? = null,
    val thanked: Boolean = false,
    val blocked: Boolean = false,
    val unread: Int = 0,
    @SerialName("last_message_id") val lastMessageId: Long = 0,
    @SerialName("safety_tips") val safetyTips: List<String> = emptyList(),
    @SerialName("can_message") val canMessage: Boolean = false,
    val question: String? = null,
    @SerialName("secret_details") val secretDetails: String? = null,
    @SerialName("handover_attempts_left") val handoverAttemptsLeft: Int? = null,
    @SerialName("handover_code") val handoverCode: String? = null,
    @SerialName("handover_code_length") val handoverCodeLength: Int = 6,
) {
    val isFinder: Boolean get() = role == "finder"
}

@Serializable
data class CasesResponse(val items: List<Case>)

@Serializable
data class ReportsResponse(val items: List<Report>)

@Serializable
data class ChatMessage(
    val id: Long,
    val kind: String,
    val mine: Boolean,
    val body: String,
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class MessagesResponse(val items: List<ChatMessage>, val status: String)

@Serializable
data class UpdatesResponse(
    @SerialName("unread_cases") val unreadCases: Int = 0,
    @SerialName("new_matches") val newMatches: Int = 0,
    @SerialName("changed_cases") val changedCases: Int = 0,
    @SerialName("server_time") val serverTime: String? = null,
)

@Serializable
data class AbuseResponse(val message: String, @SerialName("auto_hidden") val autoHidden: Boolean = false)

@Serializable
data class ErrorBody(val error: ErrorDetail)

@Serializable
data class ErrorDetail(
    val code: String,
    val message: String,
    @SerialName("attempts_left") val attemptsLeft: Int? = null,
    val fields: List<FieldError> = emptyList(),
)

@Serializable
data class FieldError(val field: String, val problem: String)

// ---------------------------------------------------------------- żądania

@Serializable
data class LocationIn(
    val lat: Double,
    val lon: Double,
    @SerialName("accuracy_m") val accuracyM: Int? = null,
    @SerialName("uncertainty_m") val uncertaintyM: Int = 0,
    val source: String,
)

@Serializable
data class ReportCreate(
    val kind: String,
    val category: String,
    val title: String,
    val description: String,
    val attributes: Map<String, JsonElement>,
    val colors: List<String>,
    @SerialName("occurred_from") val occurredFrom: String,
    @SerialName("occurred_to") val occurredTo: String,
    val location: LocationIn,
    @SerialName("area_label") val areaLabel: String? = null,
    val holding: String? = null,
    @SerialName("holding_note") val holdingNote: String? = null,
    @SerialName("secret_details") val secretDetails: String? = null,
    @SerialName("claim_question") val claimQuestion: String? = null,
    @SerialName("photo_ids") val photoIds: List<String> = emptyList(),
)

@Serializable
data class ReportUpdate(
    val category: String? = null,
    val title: String? = null,
    val description: String? = null,
    val attributes: Map<String, JsonElement>? = null,
    val colors: List<String>? = null,
    @SerialName("occurred_from") val occurredFrom: String? = null,
    @SerialName("occurred_to") val occurredTo: String? = null,
    val location: LocationIn? = null,
    @SerialName("area_label") val areaLabel: String? = null,
    val holding: String? = null,
    @SerialName("holding_note") val holdingNote: String? = null,
    @SerialName("secret_details") val secretDetails: String? = null,
    @SerialName("claim_question") val claimQuestion: String? = null,
    @SerialName("photo_ids") val photoIds: List<String>? = null,
)

@Serializable
data class ClaimCreate(
    val answer: String,
    @SerialName("proof_details") val proofDetails: String = "",
    @SerialName("evidence_photo_ids") val evidencePhotoIds: List<String> = emptyList(),
    @SerialName("lost_report_id") val lostReportId: String? = null,
)

@Serializable
data class NoteIn(val note: String? = null)

@Serializable
data class HandoverIn(val code: String? = null)

@Serializable
data class MessageIn(val body: String)

@Serializable
data class ReadIn(@SerialName("last_read_id") val lastReadId: Long)

@Serializable
data class RecoverIn(val code: String)

@Serializable
data class ParseIn(val text: String)

@Serializable
data class ResolveIn(val note: String)

@Serializable
data class AbuseIn(
    @SerialName("target_type") val targetType: String,
    @SerialName("target_id") val targetId: String,
    val reason: String,
    val details: String = "",
)

fun JsonElement.asText(): String = runCatching { jsonPrimitive.content }.getOrDefault(toString())
