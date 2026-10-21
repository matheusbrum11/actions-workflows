# Ktor API CI + Coverage Gate

A reusable CI pipeline for Ktor (Kotlin / Gradle) backends. It builds the
project (which runs tests plus **detekt/ktlint** through the `build` task),
produces **Kover** coverage reports, and fails the check when coverage drops
below a configurable minimum (default **90%**). The coverage result is written
to the GitHub Step Summary and posted as a PR comment, and the Kover HTML report
is uploaded as a build artifact.

Docs-only changes pass the check **without** running Gradle, so a required
status check never blocks a pure documentation PR and never stays pending.

---

## Table of contents

- [What the pipeline does](#what-the-pipeline-does)
- [Plugging it into a Ktor project](#plugging-it-into-a-ktor-project)
- [What the consumer project must have](#what-the-consumer-project-must-have)
- [Kover configuration example](#kover-configuration-example)
- [Default coverage exclusions](#default-coverage-exclusions)
- [Docs-only skip](#docs-only-skip)
- [Inputs reference](#inputs-reference)

---

## What the pipeline does

The reusable workflow runs these steps, in order:

| # | Step | Tool | Fails the check when… |
|---|------|------|-----------------------|
| 1 | Checkout (full history) | `actions/checkout` | — |
| 2 | Detect docs-only changes | `git diff` vs base | — (decides whether to skip) |
| 3 | Build + tests + detekt/ktlint | `./gradlew build` | compilation, a test, or lint fails |
| 4 | Coverage reports | `./gradlew koverXmlReport koverHtmlReport` | — (produces the reports) |
| 5 | Coverage summary + PR comment | `$GITHUB_STEP_SUMMARY` + `gh pr comment` | — |
| 6 | Upload HTML report | `actions/upload-artifact` | — |
| 7 | Coverage gate | `./gradlew koverVerify` | coverage `< coverage-min` |

The gate runs with `GITHUB_TOKEN` only and minimal permissions
(`contents: read`, `pull-requests: write`).

---

## Plugging it into a Ktor project

Copy the example below into your project at `.github/workflows/ci.yml`:

```yaml
name: CI
on:
  pull_request:
  push:
    branches:
      - main
      - "release/**"

permissions:
  contents: read
  pull-requests: write

jobs:
  ci:
    uses: matheusbrum11/actions-workflows/.github/workflows/ktor-ci.yml@v1
    with:
      java-version: "21"
      coverage-min: 90
      # working-directory: "."          # set to a subfolder for a monorepo
      # gradle-tasks-extra: "detektMain" # extra tasks/flags if needed
```

> **Pinning:** `@v1` tracks the `v1` tag of this repo. Prefer a tag over `@main`
> for reproducible CI.

The caller triggers on `pull_request` and on `push` to `main` and `release/**`.
On a pull request the coverage result is posted as a PR comment; on a push it is
written to the job summary only (there is no PR to comment on).

---

## What the consumer project must have

1. **A Gradle wrapper** (`./gradlew`) at the `working-directory`.
2. **detekt and/or ktlint wired into `build`** (or `check`, which `build`
   depends on) so static analysis runs and fails the build on violations.
3. **The Kover Gradle plugin applied.** Reference it by its standard id —
   `org.jetbrains.kotlinx.kover` — in the consumer's build. The **version is
   pinned by the consumer project**, not by this workflow, so the project stays
   in control of its own toolchain.
4. **A `koverVerify` rule** that enforces the minimum. The workflow passes the
   `coverage-min` input to Gradle as the `koverMinCoverage` project property, so
   wire the rule to read it (see below).

---

## Kover configuration example

Apply the plugin (pin the version in the consumer project) and configure the
XML/HTML reports plus the verification rule so it reads the `koverMinCoverage`
property passed by the workflow, falling back to 90 locally:

```kotlin
// build.gradle.kts
plugins {
    kotlin("jvm") version "<pinned>"
    id("org.jetbrains.kotlinx.kover") version "<pinned>"
}

kover {
    reports {
        total {
            xml { onCheck.set(false) }   // produced on demand by koverXmlReport
            html { onCheck.set(false) }  // produced on demand by koverHtmlReport

            verify {
                rule {
                    minBound(
                        providers.gradleProperty("koverMinCoverage")
                            .map(String::toInt)
                            .getOrElse(90),
                    )
                }
            }

            filters {
                excludes {
                    // See "Default coverage exclusions" below.
                    classes(
                        "*ApplicationKt",          // Ktor entrypoint (Application.main)
                        "*.di.*", "*KoinModuleKt", // DI (Koin) modules
                    )
                    annotatedBy("*Generated*")     // generated code
                }
            }
        }
    }
}
```

> The workflow invokes `./gradlew koverVerify -PkoverMinCoverage=<coverage-min>`,
> so overriding `coverage-min` in the caller changes the enforced bar without
> touching the project build.

---

## Default coverage exclusions

The coverage measurement is meant to reflect **testable application logic**, so
the recommended Kover filter excludes:

- **Generated code** — anything marked with a `*Generated*` annotation (for
  example `javax.annotation.Generated` / `jakarta.annotation.Generated`).
- **`Application.main`** — the Ktor entrypoint (`*ApplicationKt`), i.e. the
  `fun main()` / `Application.module()` wiring that boots the server.
- **DI (Koin) modules** — dependency-injection declarations
  (`*.di.*`, `*KoinModuleKt`), which are wiring, not logic.

Keep these exclusions in the consumer's Kover `filters` block (shown above) so
the gate verifies real logic rather than boilerplate. Adjust the globs to match
your package layout.

---

## Docs-only skip

A required status check must always report a conclusion, so this workflow does
**not** use `paths-ignore` on the trigger (that would leave the required check
pending forever on a docs-only PR). Instead the job itself inspects the diff
against the base ref and classifies the change:

- If **every** changed file matches `*.md`, `docs/**`, or `.claude/**`, the
  Gradle build and coverage gate are **skipped** and the check **passes** with a
  note in the job summary.
- Otherwise the full build + coverage pipeline runs.

On a pull request the diff is taken against `origin/<base ref>`; on a push it is
taken against the previous commit. Full history (`fetch-depth: 0`) is fetched so
the diff is accurate.

---

## Inputs reference

| Input | Type | Default | Meaning |
|-------|------|---------|---------|
| `java-version` | string | `"21"` | Temurin JDK version. |
| `coverage-min` | number | `90` | Minimum coverage; passed to `koverVerify` as `-PkoverMinCoverage`. |
| `working-directory` | string | `"."` | Directory the Gradle build runs from. |
| `gradle-tasks-extra` | string | `""` | Extra Gradle tasks/flags appended to the build invocation. |
