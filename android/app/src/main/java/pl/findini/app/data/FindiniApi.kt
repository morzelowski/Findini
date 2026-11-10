package pl.findini.app.data

import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

interface FindiniApi {
    @GET("v1/places")
    suspend fun places(@Query("q") query: String): PlacesResponse

    @GET("v1/meta")
    suspend fun meta(): Meta

    @POST("v1/sessions")
    suspend fun createSession(): SessionResponse

    @POST("v1/sessions/recover")
    suspend fun recover(@Body body: RecoverIn): SessionResponse

    @GET("v1/me")
    suspend fun me(): MeResponse

    @POST("v1/me/recovery-code")
    suspend fun recoveryCode(): RecoveryCodeResponse

    @DELETE("v1/me")
    suspend fun deleteMe(): Response<Unit>

    @GET("v1/me/reports")
    suspend fun myReports(): ReportsResponse

    @GET("v1/me/cases")
    suspend fun myCases(): CasesResponse

    @GET("v1/me/updates")
    suspend fun updates(@Query("since") since: String?): UpdatesResponse

    @GET("v1/reports")
    suspend fun search(
        @Query("kind") kind: String? = null,
        @Query("category") category: String? = null,
        @Query("subtype") subtype: String? = null,
        @Query("colors") colors: String? = null,
        @Query("brand") brand: String? = null,
        @Query("q") q: String? = null,
        @Query("lat") lat: Double? = null,
        @Query("lon") lon: Double? = null,
        @Query("radius_m") radiusM: Int? = null,
        @Query("date_from") dateFrom: String? = null,
        @Query("date_to") dateTo: String? = null,
        @Query("sort") sort: String? = null,
        @Query("cursor") cursor: String? = null,
        @Query("limit") limit: Int = 20,
    ): SearchResponse

    @GET("v1/reports/areas")
    suspend fun areas(
        @Query("bbox") bbox: String,
        @Query("kind") kind: String? = null,
        @Query("category") category: String? = null,
        @Query("subtype") subtype: String? = null,
        @Query("colors") colors: String? = null,
        @Query("brand") brand: String? = null,
        @Query("q") q: String? = null,
        @Query("lat") lat: Double? = null,
        @Query("lon") lon: Double? = null,
        @Query("radius_m") radiusM: Int? = null,
        @Query("date_from") dateFrom: String? = null,
        @Query("date_to") dateTo: String? = null,
    ): AreasResponse

    @GET("v1/reports/{id}")
    suspend fun report(@Path("id") id: String): Report

    @POST("v1/reports")
    suspend fun createReport(@Body body: ReportCreate): Report

    @PATCH("v1/reports/{id}")
    suspend fun updateReport(@Path("id") id: String, @Body body: ReportUpdate): Report

    @DELETE("v1/reports/{id}")
    suspend fun withdrawReport(@Path("id") id: String): Response<Unit>

    @POST("v1/reports/{id}/resolve")
    suspend fun resolveReport(@Path("id") id: String, @Body body: ResolveIn): Report

    @POST("v1/reports/{id}/renew")
    suspend fun renewReport(@Path("id") id: String): Report

    @GET("v1/reports/{id}/matches")
    suspend fun matches(@Path("id") id: String): MatchesResponse

    @GET("v1/reports/{id}/claims")
    suspend fun reportClaims(@Path("id") id: String): CasesResponse

    @GET("v1/reports/{id}/claim-form")
    suspend fun claimForm(@Path("id") id: String): ClaimForm

    @POST("v1/reports/{id}/claims")
    suspend fun createClaim(@Path("id") id: String, @Body body: ClaimCreate): Case

    @Multipart
    @POST("v1/photos")
    suspend fun uploadPhoto(@Part file: MultipartBody.Part, @Part("purpose") purpose: RequestBody): PhotoUpload

    @DELETE("v1/photos/{id}")
    suspend fun deletePhoto(@Path("id") id: String): Response<Unit>

    @Multipart
    @POST("v1/search/by-photo")
    suspend fun searchByPhoto(
        @Part file: MultipartBody.Part,
        @Part("kind") kind: RequestBody,
    ): PhotoSearchResponse

    @POST("v1/search/parse")
    suspend fun parse(@Body body: ParseIn): ParseResponse

    @GET("v1/places/suggest")
    suspend fun placeSuggest(@Query("lat") lat: Double, @Query("lon") lon: Double): Map<String, String?>

    @GET("v1/claims/{id}")
    suspend fun case(@Path("id") id: String): Case

    @POST("v1/claims/{id}/accept")
    suspend fun accept(@Path("id") id: String, @Body body: NoteIn): Case

    @POST("v1/claims/{id}/reject")
    suspend fun reject(@Path("id") id: String, @Body body: NoteIn): Case

    @POST("v1/claims/{id}/withdraw")
    suspend fun withdraw(@Path("id") id: String): Case

    @POST("v1/claims/{id}/handover")
    suspend fun handover(@Path("id") id: String, @Body body: HandoverIn): Case

    @POST("v1/claims/{id}/confirm-received")
    suspend fun confirmReceived(@Path("id") id: String): Case

    @POST("v1/claims/{id}/thanks")
    suspend fun thanks(@Path("id") id: String): Case

    @POST("v1/claims/{id}/block")
    suspend fun block(@Path("id") id: String): Case

    @GET("v1/claims/{id}/messages")
    suspend fun messages(@Path("id") id: String, @Query("after_id") afterId: Long): MessagesResponse

    @POST("v1/claims/{id}/messages")
    suspend fun sendMessage(@Path("id") id: String, @Body body: MessageIn): ChatMessage

    @POST("v1/claims/{id}/read")
    suspend fun markRead(@Path("id") id: String, @Body body: ReadIn): Response<Unit>

    @POST("v1/abuse-reports")
    suspend fun reportAbuse(@Body body: AbuseIn): AbuseResponse
}
