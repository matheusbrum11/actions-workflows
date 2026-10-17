# Android CD — Sandbox (Firebase) & Release (Play Store)

Two reusable delivery workflows for Android projects:

| Workflow | Trigger (git flow) | What it does |
|----------|--------------------|--------------|
| **Sandbox** — [`android-cd-sandbox.yml`](../.github/workflows/android-cd-sandbox.yml) | push to `develop` / manual | Builds a signed artifact and uploads it to **Firebase App Distribution** for testers. |
| **Release** — [`android-cd-release.yml`](../.github/workflows/android-cd-release.yml) | **merge to `main`** | Computes the next **semantic version**, builds a signed **AAB**, ships it to **Google Play**, and tags the release. |

Both reuse the same signing secrets. The version logic lives in a small,
dependency-free Python script:
[`scripts/compute_version.py`](scripts/compute_version.py).

---

## Table of contents

- [Versioning model](#versioning-model)
- [The versionCode strategy](#the-versioncode-strategy)
- [Secrets reference](#secrets-reference)
- [Step by step: signing key](#step-by-step-signing-key)
- [Step by step: Firebase App Distribution](#step-by-step-firebase-app-distribution)
- [Step by step: Google Play](#step-by-step-google-play)
- [Wiring versionName / versionCode in Gradle](#wiring-versionname--versioncode-in-gradle)
- [Installing the workflows](#installing-the-workflows)
- [Inputs reference](#inputs-reference)

---

## Versioning model

The release workflow follows **git flow + Conventional Commits**. On each merge
to `main` it reads the latest release tag (e.g. `v1.4.2`) and the commits made
since it, then bumps `MAJOR.MINOR.PATCH`:

| Commit | Example | Bumps | `1.4.2` becomes |
|--------|---------|-------|-----------------|
| Breaking change | `feat!: drop v1 api` or a body line `BREAKING CHANGE: …` | **MAJOR** (major) | `2.0.0` |
| Feature | `feat: add dark mode` | **MINOR** (middle) | `1.5.0` |
| Fix | `fix: npe on launch` | **PATCH** (last) | `1.4.3` |
| Anything else | `chore:`, `docs:`, … | `default-bump` (default **patch**) | `1.4.3` |

The highest-priority bump among the commits wins. The new `versionName` is the
bumped version; a git tag `v<version>` and a GitHub release are created.

> First run with no tags starts from `initial-version` (default `0.0.0`), so a
> first `feat` produces `0.1.0`, a first `fix` produces `0.0.1`.

Commit convention your team should follow: `type(scope)?: subject`, with `!`
and/or a `BREAKING CHANGE:` body line for breaking changes. Squash-merging PRs
with a conventional title keeps history clean and the bump accurate.

---

## The versionCode strategy

Google Play requires a **monotonically increasing integer** `versionCode`. Two
strategies, via the `version-code-strategy` input:

- **`run_number`** (default) — `github.run_number + version-code-offset`. Simple
  and what you asked for. Caveat: `run_number` resets if you delete/recreate the
  workflow file; use `version-code-offset` to jump past any already-published code.
- **`commit_count`** (smarter) — `git rev-list --count HEAD + offset`. Tied to
  history, so it keeps increasing and survives workflow recreation. Requires full
  history in CI (`fetch-depth: 0`, which the workflow already sets).

---

## Secrets reference

Add these under **Repo → Settings → Secrets and variables → Actions → New
repository secret**. Names are exactly what the workflows read.

### Signing (both workflows)

| Secret name | What it holds |
|-------------|---------------|
| `ANDROID_KEYSTORE_BASE64` | The upload keystore (`.jks`/`.keystore`) **base64-encoded** to one line. |
| `ANDROID_KEYSTORE_PASSWORD` | The keystore (store) password. |
| `ANDROID_KEY_ALIAS` | The key alias inside the keystore. |
| `ANDROID_KEY_PASSWORD` | The key (alias) password. |

### Sandbox only

| Secret name | What it holds |
|-------------|---------------|
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Full JSON of a service account with Firebase App Distribution access. |

(The Firebase **App ID** is a workflow *input* — `firebase-app-id` — not a secret.)

### Release only

| Secret name | What it holds |
|-------------|---------------|
| `PLAY_SERVICE_ACCOUNT_JSON` | Full JSON of a Google Play service account with release permissions. |

(The Play **package name** is a workflow *input* — `package-name`.)

---

## Step by step: signing key

1. **Create an upload keystore** (once per app; keep it safe and backed up):

   ```bash
   keytool -genkey -v \
     -keystore upload-keystore.jks \
     -alias upload \
     -keyalg RSA -keysize 2048 -validity 10000
   ```

   Remember the **store password**, the **alias** (`upload` above), and the
   **key password** — these map to the three secrets below.

2. **Base64-encode the keystore** into a single line and copy it:

   ```bash
   base64 -i upload-keystore.jks | tr -d '\n' | pbcopy    # macOS
   # base64 -w0 upload-keystore.jks                        # Linux
   ```

3. **Register the secrets:**
   - `ANDROID_KEYSTORE_BASE64` → the base64 string from step 2
   - `ANDROID_KEYSTORE_PASSWORD` → store password
   - `ANDROID_KEY_ALIAS` → `upload`
   - `ANDROID_KEY_PASSWORD` → key password

The workflow decodes the keystore to a temp file and signs via Gradle *injected
signing* (`-Pandroid.injected.signing.*`), so **no change to your app's signing
config is required**. If you prefer a `keystore.properties` setup, that works too
— just make your release build read it.

> For Play **App Signing** (recommended), this keystore is your *upload* key;
> Google re-signs with the app signing key it manages.

---

## Step by step: Firebase App Distribution

1. In the **Firebase console**, add your Android app and copy its **App ID**
   (looks like `1:1234567890:android:abcdef…`). Put it in the caller's
   `firebase-app-id` input.
2. Create tester **groups** (e.g. `qa`, `internal`) under App Distribution and
   use their aliases in `firebase-groups`.
3. Create a **service account** with App Distribution access:
   - Google Cloud Console → IAM & Admin → Service Accounts → *Create*.
   - Grant the **Firebase App Distribution Admin** role.
   - Create a **JSON key** and download it.
4. Paste the full JSON into the `FIREBASE_SERVICE_ACCOUNT_JSON` secret.

On push to `develop` (or manual dispatch) the sandbox workflow builds, signs,
and uploads the APK to those tester groups.

---

## Step by step: Google Play

1. Your app must exist in the **Play Console** and have had at least one manual
   upload of the first AAB (Play requires the first release by hand).
2. Create a **service account** for automated publishing:
   - Google Cloud Console → create a service account.
   - In **Play Console → Users and permissions**, invite that service account and
     grant **Release** permissions (to the app or account).
   - Create and download its **JSON key**.
3. Paste the full JSON into `PLAY_SERVICE_ACCOUNT_JSON`.
4. Set the caller's `package-name` (e.g. `com.acme.app`) and `track`
   (`internal` → `alpha` → `beta` → `production`). Start with `internal`.

On merge to `main` the release workflow computes the version, builds the signed
AAB, uploads it to the chosen track, and tags the release.

---

## Wiring versionName / versionCode in Gradle

The workflows pass the computed version to Gradle as project properties. Make
your **app module** `build.gradle.kts` read them (falling back to defaults for
local builds):

```kotlin
android {
    defaultConfig {
        versionCode = (project.findProperty("versionCode") as String?)?.toInt() ?: 1
        versionName = (project.findProperty("versionName") as String?) ?: "0.0.1"
    }
}
```

Groovy equivalent:

```groovy
android {
    defaultConfig {
        versionCode (project.findProperty("versionCode") ?: 1).toInteger()
        versionName project.findProperty("versionName") ?: "0.0.1"
    }
}
```

Without this wiring the build still succeeds, but it uses the hardcoded version
in your Gradle file instead of the computed one.

---

## Installing the workflows

1. Copy the signing secrets (and the Firebase/Play ones you need) as above.
2. Copy the example callers into your project:
   - [`examples/cd-sandbox.yml`](examples/cd-sandbox.yml) → `.github/workflows/cd-sandbox.yml`
   - [`examples/cd-release.yml`](examples/cd-release.yml) → `.github/workflows/cd-release.yml`
3. Fill in `firebase-app-id` / `package-name` and adjust tasks for your flavors.
4. Add the Gradle version wiring above.
5. Pin `@main` to a release tag (e.g. `@v1`) for reproducible CD; set the release
   workflow's `gate-ref` to the same tag so the version script matches.

Merge to `main` → a new Play release. Push to `develop` → a new sandbox build.

---

## Inputs reference

### Sandbox (`android-cd-sandbox.yml`)

| Input | Default | Meaning |
|-------|---------|---------|
| `firebase-app-id` | — (required) | Firebase App ID. |
| `firebase-groups` | `testers` | Comma-separated tester groups. |
| `assemble-task` | `assembleRelease` | Gradle task building the APK. |
| `artifact-glob` | `**/build/outputs/apk/**/*.apk` | Where to find the APK. |
| `version-code-offset` | `0` | Added to `github.run_number`. |
| `java-version` / `java-distribution` | `17` / `temurin` | JDK. |
| `runs-on` | `ubuntu-latest` | Runner. |

### Release (`android-cd-release.yml`)

| Input | Default | Meaning |
|-------|---------|---------|
| `package-name` | — (required) | Play package name. |
| `track` | `internal` | Play track. |
| `bundle-task` | `bundleRelease` | Gradle task building the AAB. |
| `aab-glob` | `**/build/outputs/bundle/**/*.aab` | Where to find the AAB. |
| `version-code-strategy` | `run_number` | `run_number` or `commit_count`. |
| `version-code-offset` | `0` | Added to the computed versionCode. |
| `tag-prefix` | `v` | Release tag prefix. |
| `initial-version` | `0.0.0` | Version when no tag exists. |
| `default-bump` | `patch` | Bump when no feat/fix/breaking commit found. |
| `gate-ref` | `main` | Ref providing `compute_version.py`. |
| `java-version` / `java-distribution` | `17` / `temurin` | JDK. |
| `python-version` | `3.12` | Python for the version script. |
| `runs-on` | `ubuntu-latest` | Runner. |

---

See [README.md](README.md) for the PR quality gate (CI) that complements this CD.
