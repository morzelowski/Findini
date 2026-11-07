plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

val debugApiUrl = providers.gradleProperty("findini.apiUrl").getOrElse("http://10.0.2.2:8080/")
val releaseApiUrl = providers.gradleProperty("findini.releaseApiUrl").getOrElse("https://findini.example.org/")

android {
    namespace = "pl.findini.app"
    compileSdk = 37

    defaultConfig {
        applicationId = "pl.findini.app"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        debug {
            buildConfigField("String", "API_URL", "\"$debugApiUrl\"")
            buildConfigField("boolean", "ALLOW_CUSTOM_SERVER", "true")
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            buildConfigField("String", "API_URL", "\"$releaseApiUrl\"")
            buildConfigField("boolean", "ALLOW_CUSTOM_SERVER", "false")
            // Do prezentacji podpisujemy kluczem debug; produkcyjny klucz trzymaj poza repozytorium.
            signingConfig = signingConfigs.getByName("debug")
        }
        // Kod jak w release (R8, bez debugowania), ale z lokalnym serwerem HTTP — do testów i prezentacji
        // w sieci lokalnej. Nie dystrybuować: zezwala na ruch nieszyfrowany.
        create("demoLocal") {
            initWith(getByName("release"))
            matchingFallbacks += listOf("release")
            buildConfigField("String", "API_URL", "\"$debugApiUrl\"")
            buildConfigField("boolean", "ALLOW_CUSTOM_SERVER", "true")
        }
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
    lint {
        abortOnError = true
        warningsAsErrors = false
        // Typos: słownik angielski zgłasza polskie słowa. OldTargetApi: świadomie targetSdk 36 (zachowania API 37 niezweryfikowane).
        disable += setOf("GradleDependency", "NewerVersionAvailable", "AndroidGradlePluginVersion", "Typos", "OldTargetApi", "ObsoleteSdkInt")
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.icons.extended)
    implementation(libs.camera.core)
    implementation(libs.camera.camera2)
    implementation(libs.camera.lifecycle)
    implementation(libs.camera.view)
    implementation(libs.work.runtime)
    implementation(libs.datastore.preferences)
    implementation(libs.exifinterface)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.okhttp)
    implementation(libs.retrofit)
    implementation(libs.retrofit.serialization)
    implementation(libs.coil.compose)
    implementation(libs.coil.network.okhttp)
    implementation(libs.maplibre)
    debugImplementation(libs.compose.ui.tooling)
    testImplementation(libs.junit)
}

// Przypięte, odtwarzalne wersje zależności (gradle.lockfile). Aktualizacja: ./gradlew :app:dependencies --write-locks
dependencyLocking {
    lockAllConfigurations()
}
