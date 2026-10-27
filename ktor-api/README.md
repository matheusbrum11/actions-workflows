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

---

# Ktor API CD — Artifact Registry + Cloud Run

Workflow reutilizável [`ktor-cd.yml`](../.github/workflows/ktor-cd.yml)
(`workflow_call`) que entrega a API Ktor no **Google Cloud Run**: constrói a
imagem Docker, envia ao **Artifact Registry**, faz o deploy e roda um smoke test
em `/v1/health`.

## Índice (CD)

- [Finalidade e modos](#finalidade-e-modos)
- [Variáveis do GitHub por ambiente](#variáveis-do-github-por-ambiente)
- [Inputs](#inputs)
- [Exemplo de `cd.yml` no vanb-api](#exemplo-de-cdyml-no-vanb-api)
- [Permissões e autenticação](#permissões-e-autenticação)
- [Smoke test e rollback](#smoke-test-e-rollback)
- [O que NÃO está coberto](#o-que-não-está-coberto)

## Finalidade e modos

Um workflow, dois modos (input `mode`):

| Modo | Uso | O que faz |
|------|-----|-----------|
| `build-and-deploy` | DEV | Faz checkout do ref, constrói a imagem (`linux/amd64`), marca com o **SHA do commit**, envia ao Artifact Registry e faz o deploy. |
| `promote` | PROD | **Não reconstrói.** Procura no registry a imagem com o SHA do commit da tag e faz o deploy dela. Se a imagem não existe, o job falha com mensagem clara: significa que o DEV nunca construiu esse commit. |

Assim, a **mesma imagem** testada no DEV é a que vai para o PROD. O deploy usa
a imagem pelo **digest** (`repo@sha256:...`), não pela tag, então o que sobe é
exatamente o que foi resolvido naquele momento.

Em ambos os modos: um único job, `concurrency` por repositório + ambiente (dois
deploys não se sobrepõem; o segundo espera, nunca cancela o primeiro), secrets
injetados do Secret Manager com `--set-secrets` (o workflow só conhece os
**nomes**, nunca os valores), e execução do serviço com a service account de
runtime.

## Variáveis do GitHub por ambiente

O job declara `environment: <input environment>`, então lê as **Variables** do
GitHub Environment (`dev` ou `prod`) do repositório que chama. São exatamente as
7 que o `scripts/gcp-setup.sh` do vanb-api imprime; nenhuma é segredo.

| Variable | Input equivalente | Exemplo |
|----------|-------------------|---------|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `workload-identity-provider` | `projects/123/locations/global/workloadIdentityPools/github/providers/github-oidc` |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | `deploy-service-account` | `vanb-deploy@vanb-dev.iam.gserviceaccount.com` |
| `GCP_RUNTIME_SERVICE_ACCOUNT` | `runtime-service-account` | `vanb-api-run@vanb-dev.iam.gserviceaccount.com` |
| `GCP_PROJECT_ID` | `project-id` | `vanb-dev` |
| `GCP_REGION` | `region` | `southamerica-east1` |
| `CLOUD_RUN_SERVICE` | `service` | `vanb-api` |
| `IMAGE_REPOSITORY` | `image-repository` | `southamerica-east1-docker.pkg.dev/vanb-dev/vanb/vanb-api` |

Se o input for informado, ele vence a variável. Por que variáveis e não
`with:` no chamador: um job que usa `uses:` não pode declarar `environment`,
então o chamador não enxerga as variáveis do Environment; só o workflow
chamado, que declara o `environment`, enxerga.

No ambiente **`prod`**, `IMAGE_REPOSITORY` aponta para o registry do **DEV**
(é o que o script de setup imprime). É dali que o `promote` lê a imagem, e por
isso a SA de deploy do PROD precisa de `artifactregistry.reader` no repositório
do DEV (o script já concede). Para exigir aprovação manual em PROD, marque
*Required reviewers* no Environment `prod`.

## Inputs

| Input | Tipo | Padrão | Significado |
|-------|------|--------|-------------|
| `mode` | string | (obrigatório) | `build-and-deploy` ou `promote`. |
| `environment` | string | (obrigatório) | Nome do GitHub Environment (`dev` / `prod`). |
| `project-id` | string | `vars.GCP_PROJECT_ID` | Projeto GCP. |
| `region` | string | `vars.GCP_REGION`, senão `southamerica-east1` | Região do Cloud Run e do Artifact Registry. |
| `service` | string | `vars.CLOUD_RUN_SERVICE` | Nome do serviço Cloud Run. |
| `image-repository` | string | `vars.IMAGE_REPOSITORY` | Caminho da imagem sem tag. |
| `runtime-service-account` | string | `vars.GCP_RUNTIME_SERVICE_ACCOUNT` | SA com a qual o serviço roda. |
| `deploy-service-account` | string | `vars.GCP_DEPLOY_SERVICE_ACCOUNT` | SA assumida via WIF para publicar. |
| `workload-identity-provider` | string | `vars.GCP_WORKLOAD_IDENTITY_PROVIDER` | Provider WIF completo. |
| `secrets-mapping` | string | `SUPABASE_URL=SUPABASE_URL:latest,SUPABASE_ANON_KEY=SUPABASE_ANON_KEY:latest,SUPABASE_JWKS_URL=SUPABASE_JWKS_URL:latest` | Vai para `--set-secrets`: `VAR=SEGREDO:VERSÃO`. Só nomes. |
| `env-vars` | string | `""` | Variáveis **não secretas** para `--set-env-vars` (`K=V,K2=V2`), ex.: `JAVA_TOOL_OPTIONS=...`. |
| `image-sha` | string | `github.sha` | SHA completo usado como tag da imagem. Em push de tag, `github.sha` é o commit da tag. |
| `dockerfile` | string | `Dockerfile` | Dockerfile, relativo ao contexto. |
| `context` | string | `.` | Contexto de build. |
| `platform` | string | `linux/amd64` | Plataforma de build (Cloud Run exige amd64). |
| `use-build-cache` | boolean | `true` | Cache de camadas no GitHub Actions cache. |
| `port` | number | `8080` | Porta do container. |
| `cpu` | string | `"1"` | CPU por instância. |
| `memory` | string | `512Mi` | Memória por instância. |
| `min-instances` | number | `0` | Instâncias mínimas (0 = escala a zero). |
| `max-instances` | number | `3` | Instâncias máximas. |
| `concurrency` | number | `80` | Requisições simultâneas por instância. |
| `allow-unauthenticated` | boolean | `true` | Invocação pública; a API faz a própria autenticação (JWT). |
| `smoke-path` | string | `/v1/health` | Caminho do smoke test. |
| `smoke-timeout-seconds` | number | `120` | Tempo total de tentativas do smoke test. |

Outputs: `service-url`, `revision`, `image` (referência por digest). Também vão
para o resumo do job.

## Exemplo de `cd.yml` no vanb-api

```yaml
# .github/workflows/cd.yml
name: CD
on:
  push:
    branches: ["release/**"]
    tags: ["v*"]
permissions:
  contents: read
  id-token: write
jobs:
  deploy-dev:
    if: github.ref_type == 'branch'
    uses: matheusbrum11/actions-workflows/.github/workflows/ktor-cd.yml@v1
    with:
      mode: build-and-deploy
      environment: dev
  deploy-prod:
    if: github.ref_type == 'tag'
    uses: matheusbrum11/actions-workflows/.github/workflows/ktor-cd.yml@v1
    with:
      mode: promote
      environment: prod
```

O chamador **precisa** conceder `id-token: write` (um workflow chamado nunca
tem mais permissão que o chamador). Fixe `@v1` (tag móvel) ou `@v1.x.y` (fixa),
como nos demais workflows deste repositório.

## Permissões e autenticação

- `permissions` do workflow: `contents: read` e `id-token: write`. Nada mais.
- Autenticação no Google Cloud **somente** por Workload Identity Federation
  (`google-github-actions/auth`). Não existe chave JSON de service account.
- O provider WIF só aceita o repositório `matheusbrum11/vanb-api` e, no DEV,
  ramos `release/*`; no PROD, tags `v*` (definido pelo script de setup).
- As actions de terceiros estão fixadas pelo **SHA completo do commit**, com a
  versão em comentário.

## Smoke test e rollback

Depois do deploy, o job faz `GET <url>/v1/health` com tentativas e espera
crescente (3s até 15s entre tentativas, até `smoke-timeout-seconds`) e falha se
não receber HTTP 200.

Em caso de falha **não há rollback automático**. O job imprime (e grava no
resumo) o nome da revisão anterior e o comando:

```bash
gcloud run services update-traffic <service> --project=<project> --region=<region> --to-revisions=<revisão-anterior>=100
```

Num primeiro deploy não há revisão anterior; o resumo avisa isso. Observação: o
`gcloud run deploy` já direciona 100% do tráfego para a nova revisão, por isso o
rollback é manual e explícito.

## O que NÃO está coberto

- **Migrações do Supabase**: são um job separado no workflow chamador (VB-86),
  com a ordem e a aprovação definidas lá.
- Rollback automático, canary/tráfego gradual e probes de startup/liveness do
  Cloud Run (configure-os no serviço apontando para `/v1/health`).
- Criação da infraestrutura (projetos, SAs, WIF, segredos): é o
  `scripts/gcp-setup.sh` do vanb-api. Os segredos precisam ter ao menos uma
  versão antes do primeiro deploy.
