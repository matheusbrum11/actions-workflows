# Android PR CI + Quality Gate

A reusable CI pipeline for Android (Kotlin / Gradle) pull requests, built around
an **extensible Python quality gate**. It builds the app, runs unit tests,
measures coverage, and runs a plugin-based set of code-quality rules. Any
**blocking** finding fails the PR; everything (blocking + warnings) is written to
the GitHub Step Summary.

The gate is designed to grow: adding your own rules is a drop-in operation and
the coding standard it enforces can be repointed at your own document.

> **Looking for delivery (CD)?** The sandbox (Firebase App Distribution) and
> release (Google Play) workflows are documented in [CD.md](CD.md).

---

## Table of contents

- [What the pipeline does](#what-the-pipeline-does)
- [Plugging it into a new Android project](#plugging-it-into-a-new-android-project)
- [What the consumer project must have](#what-the-consumer-project-must-have)
- [The coding standard used as the baseline](#the-coding-standard-used-as-the-baseline)
- [Pointing the gate at your own standard](#pointing-the-gate-at-your-own-standard)
- [Adding a new rule](#adding-a-new-rule)
- [Configuration reference](#configuration-reference)
- [Contributing](#contributing)

---

## What the pipeline does

The reusable workflow runs these steps, in order:

| # | Step | Tool | Fails the PR when… |
|---|------|------|--------------------|
| 1 | Checkout (full history) | `actions/checkout` | — |
| 2 | Build debug | `./gradlew assembleDebug` | compilation fails |
| 3 | Unit tests | `./gradlew testDebugUnitTest` | any test fails |
| 4 | Coverage | `./gradlew jacocoTestReport` | — (produces the report) |
| 5 | Quality gate | `python -m quality_gate` | any **blocking** finding |
| 6 | Summary | gate → `$GITHUB_STEP_SUMMARY` | — |

The quality gate ships with three rules out of the box:

1. **`no-comments`** — Kotlin sources must not carry implementation comments
   (`//`, `/* */`). The license header and `/** KDoc */` on **public**
   declarations are exempt by default (both configurable). Blocking.
2. **`coverage`** — aggregated JaCoCo coverage must be **≥ 90%** (configurable).
   Blocking.
3. **`layering`** — enforces the layer dependency direction `ui → domain → data`
   (see [the standard](#the-coding-standard-used-as-the-baseline)). Blocking.

Everything else is left as a documented template for you to extend.

---

## Plugging it into a new Android project

There are two ways to consume this, both reusing the same bundled gate.

### Option A — reusable workflow (simplest)

Copy [`examples/pr-gate.yml`](examples/pr-gate.yml) into your project at
`.github/workflows/pr-gate.yml`:

```yaml
name: PR Gate
on:
  pull_request:
permissions:
  contents: read
jobs:
  quality:
    uses: matheusbrum11/actions-workflows/.github/workflows/android-pr-gate.yml@main
    with:
      java-version: "17"
      # assemble-task: "assembleDemoDebug"     # override if you use flavors
      # test-task: "testDemoDebugUnitTest"
      # coverage-task: "createDebugCombinedCoverageReport"
      # config-path: "android/quality-gate.yml"
```

### Option B — composite action (own your build steps)

Use this when you want full control over build/test/coverage (matrix, caching,
flavors) and only delegate the gate. See
[`examples/pr-gate-composite-action.yml`](examples/pr-gate-composite-action.yml):

```yaml
- name: Quality gate
  uses: matheusbrum11/actions-workflows/android@main
  with:
    project-root: "."
    config-path: "android/quality-gate.yml"
    base-ref: "origin/${{ github.base_ref }}"
```

> **Pinning:** `@main` tracks the latest gate. For reproducible CI, pin to a tag
> (e.g. `@v1`). When using the reusable workflow, also set the `gate-ref` input
> to the same tag so the workflow and the gate script stay in lockstep.

### Add the config file

Copy [`quality-gate.yml`](quality-gate.yml) into your project at
`android/quality-gate.yml` and adjust `scan_paths`, the coverage threshold, and
rule options for your project. No secrets are required — the gate only reads the
checkout and the JaCoCo report.

---

## What the consumer project must have

For the pipeline to work, the Android project you point it at needs:

1. **A Gradle wrapper** (`./gradlew`) and the tasks referenced by the workflow
   inputs (`assembleDebug`, `testDebugUnitTest`, and a coverage task). Override
   the input names if yours differ.
2. **JaCoCo configured** so the coverage task emits an **XML** report. The
   `report_paths` glob in the config must match where it lands (default
   `**/build/reports/jacoco/**/*.xml`). Minimal setup for a single module:

   ```kotlin
   // build.gradle.kts
   plugins { jacoco }

   tasks.withType<Test> { finalizedBy("jacocoTestReport") }

   tasks.register<JacocoReport>("jacocoTestReport") {
       dependsOn("testDebugUnitTest")
       reports { xml.required.set(true) }   // XML is what the gate reads
       // classDirectories/sourceDirectories per your module layout
   }
   ```

   Now in Android generates a combined report via
   `create{Variant}CombinedCoverageReport` — if you follow that, set
   `coverage-task` and `report_paths` accordingly.
3. **`android/quality-gate.yml`** present (or pass `--config`/`config-path`).
4. **Full git history in CI** (`fetch-depth: 0`) so the gate can diff against the
   PR base ref for `scope: changed`. The reusable workflow sets this for you.

---

## The coding standard used as the baseline

The default rules encode the **Now in Android** architecture and conventions,
adapted to a **single module** (the same layer separation NiA keeps across Gradle
modules, expressed as **packages** inside one module — "multi-module without the
multi-module").

### Layers (as packages)

```
com.yourapp
├── data          # offline-first data layer
│   ├── repository    # interfaces + impls (OfflineFirst*/Default*)
│   ├── model         # data-layer models / DTOs
│   ├── local         # Room, DataStore
│   ├── remote        # Retrofit / network
│   └── di
├── domain         # business logic
│   ├── usecase       # *UseCase classes, operator fun invoke(), return Flow
│   └── model         # domain models (immutable)
└── ui             # presentation
    ├── <feature>     # ViewModel + Screen + UiState per feature
    └── designsystem  # shared Compose components
```

### Dependency direction (enforced by `layering`)

```
ui  ──▶  domain  ──▶  data
```

- `ui` may depend on `domain` and `data` (NiA ViewModels inject repositories
  directly, so `ui → data` is allowed).
- `domain` may depend on `data` only.
- `data` must **not** import `domain` or `ui`; `domain` must **not** import `ui`.

### Conventions adopted (from NiA)

- **License header** on every Kotlin file (the leading block comment; exempt from
  `no-comments`).
- **UDF + Jetpack Compose**: `@HiltViewModel` exposes `StateFlow<UiState>`;
  `UiState` is a `sealed interface` (`data object Loading` / `data class …` /
  `data object Empty`); UI state is immutable.
- **Repository pattern**: an interface plus an `OfflineFirst*`/`Default*` impl.
- **Use cases**: `class XUseCase @Inject constructor(...)` with
  `operator fun invoke()` returning a `Flow`.
- **Hilt** for DI; **ktlint/Spotless** formatting.

> **Deliberate divergence:** NiA itself uses inline comments and `// TODO`s. This
> gate is stricter — it forbids implementation comments (keeping public-API KDoc).
> That is the `no-comments` rule's purpose and is fully configurable.

---

## Pointing the gate at your own standard

If you prefer a different standard than the NiA-single-module baseline, you do
**not** fork the script. Two levers:

### 1. Declare your standard in the config

```yaml
# android/quality-gate.yml
coding_standard:
  name: "ACME Android Guidelines v2"
  document: docs/android-standard.md   # your own standard document
```

`name` is shown in the PR summary header; `document` points humans (and your
future rules) at the authoritative description. Put your standard document
anywhere in your repo and reference it here.

### 2. Make the rules match that standard

The rules are config-driven, so most changes are just config:

- **Different layering** — redefine the layer→package map and the forbidden
  directions under `rules.layering` (add layers, rename segments, change the
  allowed flow).
- **Different comment policy** — toggle `allow_kdoc_on_public_api`,
  `allow_license_header`, `flag_line_comments`, `flag_block_comments` under
  `rules.no-comments`.
- **Different coverage bar** — change `coverage.min_percentage` / `metric`.
- **Disable a baseline rule** — set `enabled: false` on it.
- **New conventions your standard adds** — write a rule for each (next section).
  A natural pattern is to have each new rule read its parameters from the config
  so your `document` stays the single source of truth and the rules enforce it.

---

## Adding a new rule

A rule is a small, isolated class. The framework discovers, configures, runs, and
renders it — you never touch the registry, CLI, or report.

1. **Copy the template:**
   `scripts/quality_gate/rules/_template.py` → `rules/my_rule.py`.
2. **Implement it:**

   ```python
   from typing import Iterable
   from ..context import GateContext
   from ..finding import Finding, Severity
   from ..registry import Rule, register

   @register
   class NoHardcodedStringsRule(Rule):
       id = "no-hardcoded-strings"
       description = "Compose text must come from string resources."
       default_severity = Severity.WARNING

       def check(self, context: GateContext) -> Iterable[Finding]:
           for path in context.kotlin_files_to_check():
               source = context.read_text(path)
               for line_no, line in enumerate(source.splitlines(), start=1):
                   if 'Text("' in line:
                       yield self.finding(
                           "Use stringResource(...) instead of a literal.",
                           file=path, line=line_no,
                       )
   ```

   Classify severity by either setting `default_severity`, passing
   `severity=Severity.WARNING` to `self.finding(...)`, or letting the consumer
   set `severity:` in config.

3. **Register it** — add one line to `rules/__init__.py`:

   ```python
   from . import my_rule  # noqa: F401
   ```

4. **Enable it** in `android/quality-gate.yml`:

   ```yaml
   rules:
     no-hardcoded-strings:
       enabled: true
       severity: warning
   ```

The `GateContext` gives rules `project_root`, `changed_files`, `diff`,
`kotlin_files_to_check()`, `all_kotlin_files()`, `read_text(path)`, and the
parsed `config`. Per-rule options arrive as `self.options`.

---

## Configuration reference

`android/quality-gate.yml` keys:

| Key | Meaning | Default |
|-----|---------|---------|
| `scan_paths` | Dirs scanned for `.kt` sources | `[app/src/main]` |
| `exempt_paths` | Globs excluded from all file rules | build/generated |
| `scope` | `changed` (PR diff) or `all` | `changed` |
| `coding_standard.name` | Shown in the summary | NiA single-module |
| `coding_standard.document` | Pointer to the standard doc | `android/README.md` |
| `coverage.min_percentage` | Global coverage threshold | `90` |
| `rules.<id>.enabled` | Whether the rule runs | `false` if absent |
| `rules.<id>.severity` | `blocking` or `warning` | rule default |
| `rules.no-comments.allow_license_header` | Keep leading license block | `true` |
| `rules.no-comments.allow_kdoc_on_public_api` | Allow KDoc on public decls | `true` |
| `rules.no-comments.flag_line_comments` | Flag `//` | `true` |
| `rules.no-comments.flag_block_comments` | Flag `/* */` | `true` |
| `rules.coverage.metric` | `LINE`/`INSTRUCTION`/`BRANCH` | `LINE` |
| `rules.coverage.report_paths` | JaCoCo XML globs | `**/build/reports/jacoco/**/*.xml` |
| `rules.layering.layers` | layer → package segment | `data/domain/ui` |
| `rules.layering.forbidden` | layer → layers it may not import | `data:[domain,ui], domain:[ui]` |

---

## Contributing

This repo is open source — contributions welcome.

### Project structure

```
.github/workflows/android-pr-gate.yml   reusable workflow (workflow_call)
android/
├── action.yml                          composite action (bundles the gate)
├── quality-gate.yml                    default gate config
├── examples/                           caller workflows to copy
├── README.md                           this file
└── scripts/
    ├── requirements.txt                PyYAML only
    └── quality_gate/
        ├── cli.py / __main__.py        orchestrator + entrypoint
        ├── registry.py                 @register + rule discovery
        ├── context.py                  GateContext
        ├── config.py                   YAML config loader
        ├── finding.py                  Finding + Severity
        ├── report.py                   Markdown summary
        └── rules/
            ├── no_comments.py
            ├── coverage.py
            ├── layering.py
            └── _template.py            copy-paste starting point
```

### Run the gate locally

```bash
cd android/scripts
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Scan a local Android project (full scan):
python -m quality_gate --project-root /path/to/android-app \
    --config /path/to/android-app/android/quality-gate.yml

# Changed-files scope, diffing against a base ref:
python -m quality_gate --project-root /path/to/android-app \
    --base-ref origin/main
```

Exit code is `0` when clean and `1` when a blocking finding exists. With no
`$GITHUB_STEP_SUMMARY` set, the Markdown report is printed to stdout.

### Testing a new rule

Point the gate at a small fixture project that deliberately violates your rule
and confirm it is reported (and that a clean fixture passes). A fixture is just a
directory with a few `.kt` files under `scan_paths` and, for coverage, a JaCoCo
XML under `report_paths`:

```
fixture/
├── quality-gate.yml
└── app/
    ├── src/main/kotlin/com/example/app/...   # .kt sources
    └── build/reports/jacoco/test/jacocoTestReport.xml
```

Run `python -m quality_gate --project-root fixture` and assert the exit code and
the findings. Keep rules dependency-free (stdlib + PyYAML) and documented with a
docstring explaining the convention they enforce.
