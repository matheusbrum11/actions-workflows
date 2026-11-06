# actions-workflows

Reusable GitHub Actions workflows for the VanB projects, grouped into three
families: **Android**, **Ktor API**, and **KMP**. Each family ships one or more
reusable workflows (`workflow_call`) that a consumer repo calls from its own
`ci.yml`, plus a folder with a focused README covering its configuration.

This root document explains what each workflow does, how consumers pin a
version, how to wire the triggers, and the one-time manual steps the repo owner
has to do on GitHub.

---

## Table of contents

- [Workflows by family](#workflows-by-family)
- [Versioning by tag](#versioning-by-tag)
- [Consumer `ci.yml` examples](#consumer-ciyml-examples)
- [Manual GitHub actions](#manual-github-actions)
- [Next steps (CD)](#next-steps-cd)

---

## Workflows by family

### Android

Folder: [`android/`](android/README.md) — see that README for the quality-gate
configuration, coding standard, and how to extend the rules.

| Workflow | What it does |
|----------|--------------|
| `.github/workflows/android-pr-gate.yml` | PR CI: build, unit tests, coverage, and the Python quality gate; blocking findings fail the PR. |
| `.github/workflows/android-cd-sandbox.yml` | Sandbox delivery to Firebase App Distribution. |
| `.github/workflows/android-cd-release.yml` | Release delivery to Google Play. |

### Ktor API

Folder: [`ktor-api/`](ktor-api/README.md) — see that README for the Kover
configuration and coverage exclusions.

| Workflow | What it does |
|----------|--------------|
| `.github/workflows/ktor-ci.yml` | Reusable CI (`workflow_call`): runs `./gradlew build koverXmlReport koverHtmlReport` plus a `koverVerify` coverage gate, posts a coverage summary and a PR comment, and uploads the Kover HTML report as an artifact. |

Jobs: `secrets` (gitleaks, full history), `migrations` (squawk, only the changed
`supabase/migrations/*.sql`, skipped when none changed) and `ktor-ci` (build and coverage).

Inputs (all optional): `java-version` (default `"21"`), `coverage-min` (default `90`),
`working-directory` (default `"."`), `gradle-tasks-extra` (default `""`),
`mode` (`full` | `deploy`, default `full`), `migrations-path` (default
`supabase/migrations`), `pg-version` (default `"17"`). Details, allowlists and
exclusions in [`ktor-api/README.md`](ktor-api/README.md#jobs-de-segurança-e-migrations-v120).

Also: `.github/workflows/ktor-cd.yml` — reusable CD (`workflow_call`): builds the image, pushes it to Artifact Registry and deploys to Cloud Run through Workload Identity Federation, then smoke-tests `/v1/health`. Modes: `build-and-deploy` (DEV) and `promote` (PROD, deploys the image already built for the commit). Details in [`ktor-api/README.md`](ktor-api/README.md#ktor-api-cd--artifact-registry--cloud-run).

### KMP

Folder: [`kmp/`](kmp/README.md) — see that README for the coverage exclusions
(note: `iosMain` is not measured by Kover).

| Workflow | What it does |
|----------|--------------|
| `.github/workflows/kmp-ci.yml` | Reusable CI (`workflow_call`, Linux): Android build/lint plus detekt and ktlint, `commonTest`/JVM/Android unit tests, Konsist checks, desktop build, and an aggregated Kover report with a coverage gate. |
| `.github/workflows/kmp-ios.yml` | Separate **optional** iOS job on macOS, run **only by `workflow_dispatch`** (manually, before each release) — no schedule and not on PRs, to save macOS minutes (see [cost note](#manual-github-actions)). |

`kmp-ci.yml` jobs: `secrets` (gitleaks) and `kmp-ci`. Inputs (all optional):
`java-version` (default `"21"`), `coverage-min` (default `90`),
`working-directory` (default `"."`), `mode` (`full` | `deploy`, default `full`).

> **Docs-only PRs pass without Gradle.** All reusable CIs detect docs-only
> changes (`*.md`, `docs/**`, `.claude/**`) inside the job and skip the Gradle
> build, so the required check reports success instead of staying pending. This
> is in-job detection, not `paths-ignore`, so the required status check is still
> reported.

---

## Versioning by tag

Consumers must **not** call these workflows on a branch (for example `@main`),
because a change on `main` would silently change everyone's CI. Instead they pin
a version tag:

```yaml
uses: matheusbrum11/actions-workflows/.github/workflows/ktor-ci.yml@v1
```

Two kinds of tags are published:

- **`v1.0.0` — fixed tag.** It points at one exact commit and never moves. Use
  it when you need a fully reproducible pipeline.
- **`v1` — moving tag.** It is re-pointed to the latest `v1.x.y` release
  whenever a backward-compatible fix or feature ships. Consumers that pin `@v1`
  automatically get those updates without editing their `ci.yml`, while a
  breaking change would be published as `v2` (and a new `v2` moving tag).

The features documented here (`secrets`/`migrations` jobs, `mode`,
`migrations-path`, `pg-version`, iOS dispatch-only guard, concurrency) ship in
**`v1.2.0`**: consumers should pin `@v1.2.0` (or `@v1` once it is moved to it).
Consumers still pinned to `v1.0.x`/`v1.1.0` are unaffected.

Recommended default is `@v1`: bug fixes and compatible improvements arrive
automatically, and breaking changes never land without an explicit bump to
`@v2`.

---

## Consumer `ci.yml` examples

The triggers below run the full gate **before** merge (on the pull request) and
a **light run after** merge (push to `main` or a `release/**` branch). The
pre-merge run is what blocks a bad PR; the post-merge run uses `mode: deploy`
(secrets scan + assemble only), so tests and coverage are not repeated: they
already passed on the PR. The expression
`mode: ${{ github.event_name == 'pull_request' && 'full' || 'deploy' }}` picks
the mode from the trigger. New pushes to the same PR cancel the previous run
(`concurrency` with `cancel-in-progress`); CD workflows are never cancelled.

### Ktor consumer

```yaml
# .github/workflows/ci.yml
name: CI
on:
  pull_request:
  push:
    branches:
      - main
      - "release/**"
permissions:
  contents: read
  pull-requests: write   # required for the coverage PR comment
jobs:
  ci:
    uses: matheusbrum11/actions-workflows/.github/workflows/ktor-ci.yml@v1.2.0
    with:
      mode: ${{ github.event_name == 'pull_request' && 'full' || 'deploy' }}
      java-version: "21"
      coverage-min: 90
      working-directory: "."
      pg-version: "17"                       # Postgres major of the Supabase project
      # migrations-path: supabase/migrations
      # gradle-tasks-extra: ""   # extra Gradle tasks if needed
```

### KMP consumer

```yaml
# .github/workflows/ci.yml
name: CI
on:
  pull_request:
  push:
    branches:
      - main
      - "release/**"
permissions:
  contents: read
  pull-requests: write   # required for the coverage PR comment
jobs:
  ci:
    uses: matheusbrum11/actions-workflows/.github/workflows/kmp-ci.yml@v1.2.0
    with:
      mode: ${{ github.event_name == 'pull_request' && 'full' || 'deploy' }}
      java-version: "21"
      coverage-min: 90
      working-directory: "."
```

The optional iOS workflow (`kmp-ios.yml`) is wired separately and runs **only by
`workflow_dispatch`**, with no `schedule`. Dispatch it manually before each
release (**Actions → iOS → Run workflow**, or `gh workflow run ios.yml --ref
release/x.y.z`):

```yaml
# .github/workflows/ios.yml
name: iOS
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  ios:
    uses: matheusbrum11/actions-workflows/.github/workflows/kmp-ios.yml@v1.2.0
```

---

## Manual GitHub actions

These are one-time steps the repo owner does in the GitHub web UI. No DevOps
experience required — follow them in order.

### 1. Let other repos use these workflows

1. Open this repo on GitHub.
2. Go to **Settings → Actions → General**.
3. Scroll to **Access**.
4. Choose the option that allows other repositories **in your account** to use
   this repo's workflows (accessible from repositories owned by the account).
5. Click **Save**.

Without this, a consumer repo calling `...@v1` fails with an access error.

### 2. Protect `main` and `release/**`

For each of `main` and `release/**`, add a branch protection rule so nothing is
merged without passing CI:

1. Go to **Settings → Branches**.
2. Click **Add branch ruleset** (or **Add rule**).
3. Set the branch name pattern (`main`, then repeat for `release/**`).
4. Enable **Require a pull request before merging** (no direct pushes).
5. Enable **Require status checks to pass before merging** and select the CI
   check (the job from the consumer's `ci.yml`).
6. Save.

> **Heads up — this needs a paid plan or a public repo.** On a **private
> repository owned by a personal account**, branch protection rules require
> **GitHub Pro**. The alternative is to make the repo **public**, where branch
> protection is free. Pick one before relying on the required-check rule.

### 3. Watch your Actions minutes (cost)

GitHub bills Actions minutes per runner type, and they are **not** equal:

- Linux runners are the cheapest (baseline).
- **macOS runners cost about 10x** a Linux minute.

This is exactly why the iOS build lives in a **separate, optional** workflow
(`kmp-ios.yml`) that runs only on manual dispatch (before each release), instead
of on every PR or on a schedule. Keeping macOS off the per-PR path keeps routine
CI on cheap Linux minutes.

Other cost levers already in place: `concurrency` cancels superseded runs of the
same PR, `mode: deploy` skips repeated tests/coverage on pushes, docs-only
changes skip Gradle, and `setup-gradle` caches dependencies (written only on the
default branch, read-only elsewhere).

**Where to see consumption:** on the account/organization page open
**Settings → Billing and licensing → Usage** (older UI: **Settings → Billing &
plans**), filter by product *Actions* and by repository to see minutes per runner
type. Each repo's **Actions** tab also lists the duration of every run.

**Budget (if a card is registered):** in the same billing area open **Budgets
and alerts → New budget**, choose product *Actions* (or the whole account), set
a monthly amount (for example US$ 5) and enable **Stop usage when budget limit is
reached** if you want a hard stop instead of only e-mail alerts. Without a
payment method, usage is capped by the free quota and nothing is charged.

---

## Next steps (CD)

Continuous delivery for the KMP family is **not** covered yet (Ktor CD lives in `ktor-cd.yml`, see above). This
section is a placeholder: deployment/release workflows for those families will
be documented here once defined. (The Android CD workflows already exist — see
[`android/CD.md`](android/CD.md).)
