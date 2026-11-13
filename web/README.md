# Web CI + CD (Vite / React / TypeScript)

Reusable workflows for static web projects built with Vite, tested with Vitest
and deployed to **Cloudflare Workers (static assets)** with `wrangler deploy`.

| Workflow | Purpose |
| --- | --- |
| `.github/workflows/web-ci.yml` | lint, typecheck, Vitest with a coverage gate (default 90%), build |
| `.github/workflows/web-cd.yml` | build and `wrangler deploy`: DEV on release push, PROD on a tag |

## What the consumer project must have

- `package.json` + `package-lock.json` (CI uses `npm ci --ignore-scripts`).
- npm scripts `lint`, `typecheck`, `test:coverage` (Vitest with `--coverage`,
  `@vitest/coverage-v8`) and `build`. Names are overridable through inputs.
- For CD: a `wrangler.jsonc` serving the build output as assets, with an `env.dev`
  entry (Worker `<name>-dev`). Security headers go in a `public/_headers` file, which
  Vite copies to `dist/` and Workers serves natively.

## CI

```yaml
name: CI
on:
  pull_request:
  push:
    branches: [main, "release/**"]
jobs:
  web:
    uses: matheusbrum11/actions-workflows/.github/workflows/web-ci.yml@v1
```

The coverage minimum is passed to Vitest as `--coverage.thresholds.*`
(lines, statements, functions, branches), so it applies even if the repo config is
looser. A summary goes to the job summary and the `coverage/` folder is uploaded
as the `web-coverage` artifact.

| Input | Default | Meaning |
| --- | --- | --- |
| `node-version` | `22` | Node.js version |
| `coverage-min` | `90` | minimum coverage percentage |
| `working-directory` | `.` | folder with `package.json` |
| `lint-script` / `typecheck-script` / `test-script` | `lint` / `typecheck` / `test:coverage` | npm script names |
| `build-script` | `build` | npm script name; empty skips the build |

## CD

```yaml
name: CD
on:
  push:
    branches: ["release/**"]
    tags: ["v*.*.*"]
jobs:
  dev:
    if: github.ref_type == 'branch'
    uses: matheusbrum11/actions-workflows/.github/workflows/web-cd.yml@v1
    with: { environment: dev }
    secrets: inherit
  prod:
    if: github.ref_type == 'tag'
    uses: matheusbrum11/actions-workflows/.github/workflows/web-cd.yml@v1
    with: { environment: prod }
    secrets: inherit
```

- `environment: dev` runs `wrangler deploy --env dev`; `environment: prod` runs the
  default environment and only accepts a `vX.Y.Z` tag.
- Deploys are serialized per environment and never cancelled mid-run.
- Optional smoke test: set the `WEB_SMOKE_URL` variable (or `smoke-url`); it must
  return HTTP 200.

### Credentials (owner setup, names only)

Create two GitHub Environments in the consumer repo, `dev` and `prod` (add
required reviewers on `prod`), each with:

| Kind | Name | Notes |
| --- | --- | --- |
| secret | `CLOUDFLARE_API_TOKEN` | token scoped to Workers deploy for that environment |
| secret | `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account id |
| variable (optional) | `WEB_SMOKE_URL` | public URL checked after deploy |

The workflow fails fast, naming the missing secret. No credential is ever printed or
stored in the repo.

## Inputs reference (CD)

| Input | Default | Meaning |
| --- | --- | --- |
| `environment` | required | `dev` or `prod` (GitHub Environment) |
| `wrangler-env` | `dev` for dev, none for prod | wrangler `--env` override |
| `node-version`, `working-directory`, `build-script` | `22`, `.`, `build` | as in CI |
| `smoke-url` | `vars.WEB_SMOKE_URL` | URL expected to return 200 |
| `smoke-timeout-seconds` | `60` | retry window of the smoke test |
