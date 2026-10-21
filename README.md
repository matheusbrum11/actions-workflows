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

Inputs: `java-version` (default `"21"`), `coverage-min` (default `90`),
`working-directory` (default `"."`), `gradle-tasks-extra` (default `""`).

### KMP

Folder: [`kmp/`](kmp/README.md) — see that README for the coverage exclusions
(note: `iosMain` is not measured by Kover).

| Workflow | What it does |
|----------|--------------|
| `.github/workflows/kmp-ci.yml` | Reusable CI (`workflow_call`, Linux): Android build/lint plus detekt and ktlint, `commonTest`/JVM/Android unit tests, Konsist checks, desktop build, and an aggregated Kover report with a coverage gate. |
| `.github/workflows/kmp-ios.yml` | Separate **optional** iOS job on macOS, run on a schedule or manually — **not** on every PR, to save macOS minutes (see [cost note](#manual-github-actions)). |

`kmp-ci.yml` inputs: `java-version` (default `"21"`), `coverage-min`
(default `90`), `working-directory` (default `"."`).

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

Recommended default is `@v1`: bug fixes and compatible improvements arrive
automatically, and breaking changes never land without an explicit bump to
`@v2`.

---

## Consumer `ci.yml` examples

The triggers below run the gate **before** merge (on the pull request) and
**again after** merge (on the push to `main` or a `release/**` branch). The
pre-merge run is what blocks a bad PR; the post-merge run confirms the merged
state of the protected branch is still green.

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
    uses: matheusbrum11/actions-workflows/.github/workflows/ktor-ci.yml@v1
    with:
      java-version: "21"
      coverage-min: 90
      working-directory: "."
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
    uses: matheusbrum11/actions-workflows/.github/workflows/kmp-ci.yml@v1
    with:
      java-version: "21"
      coverage-min: 90
      working-directory: "."
```

The optional iOS workflow (`kmp-ios.yml`) is wired separately — on a schedule or
`workflow_dispatch` — and is intentionally kept off the per-PR path.

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
(`kmp-ios.yml`) that runs on a schedule or on demand, instead of on every PR.
Keeping macOS off the per-PR path keeps routine CI on cheap Linux minutes.

---

## Next steps (CD)

Continuous delivery for the Ktor and KMP families is **not** covered yet. This
section is a placeholder: deployment/release workflows for those families will
be documented here once defined. (The Android CD workflows already exist — see
[`android/CD.md`](android/CD.md).)
