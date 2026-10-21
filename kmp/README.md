# KMP CI + Coverage Gate

A reusable CI pipeline for **Kotlin Multiplatform** (KMP) pull requests. It
builds the Android and desktop/JVM targets, runs the shared `commonTest` suite,
static analysis and architecture checks, and enforces an **aggregated Kover
coverage gate** (90% by default). Anything below the threshold fails the PR; the
coverage result is written to the GitHub Step Summary and posted as a PR comment.

The iOS targets need a macOS runner, so they live in a **separate, optional**
workflow ([`kmp-ios.yml`](#optional-ios-workflow)) meant to run on a schedule or
on demand rather than on every PR.

---

## Table of contents

- [Why a new workflow instead of reusing the Android gate](#why-a-new-workflow-instead-of-reusing-the-android-gate)
- [What the pipeline does](#what-the-pipeline-does)
- [Consuming `kmp-ci.yml`](#consuming-kmp-ciyml)
- [Optional iOS workflow](#optional-ios-workflow)
- [What the consumer project must have](#what-the-consumer-project-must-have)
- [Default Kover exclusions](#default-kover-exclusions)
- [Docs-only pull requests](#docs-only-pull-requests)

---

## Why a new workflow instead of reusing the Android gate

**Decision: create a new `kmp-ci.yml` rather than reuse `android-pr-gate.yml`.**

The Android PR gate measures coverage with **JaCoCo** and feeds the XML into an
Android-specific **Python quality gate** (`python -m quality_gate`) that also
enforces single-module layering and comment rules. That pipeline is tied to a
single Android variant (`assembleDebug` / `testDebugUnitTest` / `jacocoTestReport`)
and to the JaCoCo report layout.

A KMP project is multi-target by nature: the same `commonMain` is compiled for
Android, JVM/desktop and iOS. JaCoCo only sees the JVM/Android side, so it cannot
express whole-project coverage. **Kover** is the KMP-native tool — it aggregates
every measurable target into one report and ships its own `koverVerify` gate.
KMP also needs steps the Android gate does not run (desktop build, **Konsist**
architecture tests, a macOS iOS job). Reusing the Android workflow would mean
bending it far out of shape, so a purpose-built KMP workflow is cleaner and
honest about what it measures.

---

## What the pipeline does

`kmp-ci.yml` runs on **ubuntu-latest**, in order:

| # | Step | Command | Fails the PR when… |
|---|------|---------|--------------------|
| 1 | Checkout (full history) | `actions/checkout` | — |
| 2 | Detect code changes | in-job git diff | — (decides docs-only skip) |
| 3 | Android build | `./gradlew assembleDebug` | compilation fails |
| 4 | Android lint | `./gradlew lintDebug` | lint errors |
| 5 | Static analysis | `./gradlew detekt ktlintCheck` | detekt/ktlint findings |
| 6 | Unit tests | `./gradlew desktopTest testDebugUnitTest` | any test fails |
| 7 | Konsist tests | `./gradlew konsistTest` | architecture rule broken |
| 8 | Desktop build | `./gradlew desktopJar` | compilation fails |
| 9 | Coverage report | `./gradlew koverXmlReport koverHtmlReport` | — (produces the report) |
| 10 | Coverage gate | `./gradlew koverVerify` | aggregated coverage < minimum |
| 11 | Summary + PR comment | Step Summary + `gh pr comment` | — |
| 12 | Kover HTML artifact | `actions/upload-artifact` | — |

`commonTest` runs as part of the JVM/desktop and Android unit test tasks.

---

## Consuming `kmp-ci.yml`

Add a caller workflow to your project at `.github/workflows/pr-ci.yml`:

```yaml
name: PR CI
on:
  pull_request:
permissions:
  contents: read
  pull-requests: write
jobs:
  ci:
    uses: matheusbrum11/actions-workflows/.github/workflows/kmp-ci.yml@v1
    with:
      java-version: "21"
      coverage-min: 90
      working-directory: "."
```

### Inputs

| Input | Meaning | Default |
|-------|---------|---------|
| `java-version` | JDK version for setup-java | `"21"` |
| `coverage-min` | Minimum aggregated coverage percentage | `90` |
| `working-directory` | Directory that holds the Gradle build | `"."` |

The gate uses the built-in `GITHUB_TOKEN` (the caller grants
`pull-requests: write`) to post the coverage comment. No other secrets are
required.

> **Pinning:** `@v1` tracks the first stable major. Pin to a specific tag for
> fully reproducible CI.

---

## Optional iOS workflow

`kmp-ios.yml` builds and tests the iOS targets on **macOS**. macOS runners cost
roughly **10x** a Linux runner, so do not run it on every PR — call it from a
**scheduled** or **manually dispatched** workflow:

```yaml
name: iOS nightly
on:
  schedule:
    - cron: "0 3 * * *"   # nightly
  workflow_dispatch:
permissions:
  contents: read
jobs:
  ios:
    uses: matheusbrum11/actions-workflows/.github/workflows/kmp-ios.yml@v1
    with:
      java-version: "21"
      working-directory: "."
```

It runs `compileKotlinIosSimulatorArm64` and `iosSimulatorArm64Test`. There is no
coverage gate here (see below).

---

## What the consumer project must have

1. **A Gradle wrapper** (`./gradlew`) and the tasks the workflows call:
   `assembleDebug`, `lintDebug`, `detekt`, `ktlintCheck`, `desktopTest`,
   `testDebugUnitTest`, `konsistTest`, `desktopJar`, the Kover tasks
   (`koverXmlReport`, `koverHtmlReport`, `koverVerify`) and, for iOS,
   `compileKotlinIosSimulatorArm64` / `iosSimulatorArm64Test`.
2. **The Kover Gradle plugin** applied (referenced by its standard plugin id;
   **the version is pinned by the consumer project**). Configure the aggregated
   report and a `koverVerify` rule. The rule should read the minimum from the
   `kover.coverageThreshold` Gradle property so the workflow's `coverage-min`
   input drives the gate:

   ```kotlin
   // build.gradle.kts
   kover {
       reports {
           verify {
               rule {
                   minBound(
                       (project.findProperty("kover.coverageThreshold") as String?)
                           ?.toInt() ?: 90
                   )
               }
           }
       }
   }
   ```

3. A **Konsist** test source set exposing a `konsistTest` task.
4. **Full git history in CI** (`fetch-depth: 0`) so the docs-only detection can
   diff against the PR base ref. The reusable workflow sets this for you.

---

## Default Kover exclusions

Kover measures only code that is meaningful to test. Exclude the following from
the aggregated report so the percentage reflects real logic, not scaffolding or
generated code:

- **Application entry-point modules** — `androidApp`, `desktopApp`, `iosApp`.
- **Generated code** — Room-generated classes, the `Res` / resource accessors,
  and `BuildConfig`.
- **Koin modules** — DI wiring (`*Module` / `di` packages).
- **Compose UI** — `@Composable` functions and `@Preview` previews.

A matching Kover configuration in the consumer project:

```kotlin
kover {
    currentProject {
        sources {
            excludedSourceSets.addAll("androidApp", "desktopApp", "iosApp")
        }
    }
    reports {
        filters {
            excludes {
                classes(
                    "*.BuildConfig",
                    "*.Res", "*.Res\$*",          // generated resources
                    "*_Impl",                      // Room-generated
                    "*.di.*", "*Module",           // Koin modules
                )
                annotatedBy(
                    "androidx.compose.runtime.Composable",
                    "androidx.compose.ui.tooling.preview.Preview",
                )
            }
        }
    }
}
```

> **iosMain is not measured.** Kover instruments the JVM/Android bytecode; it
> cannot measure Kotlin/Native output, so `iosMain` coverage never appears in the
> aggregated report. iOS code is exercised by the optional `kmp-ios.yml` tests
> instead.

---

## Docs-only pull requests

Instead of `paths-ignore` (which would make the required check never report on a
docs-only PR), the workflow detects docs-only changes **inside the job**: it
diffs the PR against its base ref and, when every changed file matches `*.md`,
`docs/**` or `.claude/**`, it **skips the Gradle steps and still succeeds**. Any
non-docs file in the diff runs the full pipeline.
