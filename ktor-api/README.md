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
| `mode` | string | `"full"` | `full` (PR gate) or `deploy` (push to `main`/`release/**`: only `./gradlew assemble`, no tests/coverage/migrations lint). |
| `migrations-path` | string | `"supabase/migrations"` | Pasta (a partir da raiz do repo) com as migrations SQL que o squawk analisa. |
| `pg-version` | string | `"17"` | Versão major do Postgres do Supabase, usada pelo squawk. |

Todos os inputs são opcionais; consumidores antigos continuam funcionando sem mudança.

---

## Jobs de segurança e migrations (v1.2.0+)

O `ktor-ci.yml` agora tem três jobs independentes: `secrets`, `migrations` e
`ktor-ci` (build/cobertura, como antes). Para quem exige status checks, os nomes
aparecem como `<job do consumidor> / secrets`, `/ migrations` e `/ ktor-ci`.

### `secrets` — gitleaks

- Roda sempre (inclusive em `mode: deploy`), com `fetch-depth: 0`, e varre **todo o
  histórico git**. O binário do gitleaks `8.30.1` é baixado do release oficial e
  validado por SHA-256 fixo no workflow.
- Falha o CI se houver achados. O gitleaks roda com `--redact` e grava um relatório
  JSON; o log imprime uma linha por achado com apenas `RuleID`, `File`, `Line`,
  `Commit` e `Fingerprint` (nunca `Match`, `Secret` ou `Description`), mais um aviso
  apontando para esta seção. Exemplo:
  `RuleID=generic-api-key File=app/Config.kt Line=12 Commit=abc1234 Fingerprint=abc1234:app/Config.kt:generic-api-key:12`.
  A `Fingerprint` é o valor usado no `.gitleaksignore`.
- Se existir `.gitleaks.toml` na raiz do consumidor, ele é usado (estende as regras
  padrão). Um achado que já vazou deve ser **rotacionado**; só depois liberado.

Como criar uma allowlist (falso positivo, ex.: chave de teste pública):

```toml
# .gitleaks.toml
[extend]
useDefault = true

[[allowlists]]
description = "Public test key used in fixtures"
paths = ['''src/test/resources/fixtures/.*''']
regexes = ['''pk_test_[A-Za-z0-9]+''']
```

Alternativa por achado: adicionar a *fingerprint* impressa pelo gitleaks em um
arquivo `.gitleaksignore` na raiz (uma por linha).

### `migrations` — squawk

- Só roda em `mode: full`. Analisa **apenas** os `*.sql` adicionados/modificados em
  `migrations-path` no PR (`git diff` contra a base). Se nenhum mudou, o job termina
  com sucesso e registra isso no summary, sem instalar nada.
- Se a base do PR não puder ser obtida ou o `git diff` falhar, o job **falha** (não passa em silêncio).
- Em `push` o intervalo é `before..HEAD`; sem `before` válido, cai para o último commit
  (`HEAD~1..HEAD`). O squawk é um gate de PR: em push é só best-effort.
- Instala `squawk-cli==2.71.0` (`pip --require-hashes`, em venv, hashes SHA-256 das wheels
  Linux x86_64/aarch64 vindos do PyPI) e executa
  `squawk --pg-version=<pg-version> <arquivos>`. Qualquer achado falha o job.
- `pg-version` deve ser a versão major do projeto Supabase (o vanb-api usa `17`).
  O input vence o `pg_version` de um eventual `.squawk.toml`.
- Se existir `.squawk.toml` na raiz do consumidor, ele é respeitado.

Como excluir uma regra do squawk:

```toml
# .squawk.toml (raiz do repositório)
excluded_rules = ["prefer-robust-stmts", "require-lock-timeout"]
```

Ou pontualmente, no próprio arquivo SQL, acima do statement:

```sql
-- squawk-ignore prefer-robust-stmts
create table public.example (id bigint primary key);
```

Atenção: consulte `squawk --help`/a [doc de regras](https://squawkhq.com/docs/rules)
para os nomes exatos das regras na versão fixada.

### `mode: full` x `mode: deploy`

| Trigger do consumidor | `mode` | O que roda |
|-----------------------|--------|-----------|
| `pull_request` | `full` (padrão) | secrets + migrations + build, testes, detekt/ktlint e gate de cobertura. |
| `push` em `main` / `release/**` | `deploy` | secrets + `./gradlew assemble`. Sem testes/cobertura repetidos (já passaram no PR). |

Como o `mode` depende do evento, o consumidor define o valor na chamada:

```yaml
on:
  pull_request:
  push:
    branches: [main, "release/**"]
jobs:
  ci:
    uses: matheusbrum11/actions-workflows/.github/workflows/ktor-ci.yml@v1.2.0
    with:
      mode: ${{ github.event_name == 'pull_request' && 'full' || 'deploy' }}
      pg-version: "17"
```

Observação sobre cache: o `setup-gradle` grava o cache só na branch padrão. Em
`deploy`, o `main` aquece apenas as dependências de `assemble`; dependências de
teste são baixadas de novo nos PRs. Se isso incomodar, use `mode: full` apenas nos
pushes para `main`.

### Concorrência

Cada job usa `concurrency` com `cancel-in-progress: true`, agrupado por workflow do
consumidor + número do PR (ou ref, em pushes). Um novo push na mesma PR cancela a
execução anterior. Isso vale também para pushes em `main`/`release/**`: um push novo
cancela o CI do anterior. CD/deploy nunca é cancelado (ver `ktor-cd.yml`), mas um CD do
consumidor que espere o CI via `workflow_run` ou `needs` ficaria bloqueado por um CI
cancelado; nesse caso o CD deve rodar a partir do push mais recente.

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
