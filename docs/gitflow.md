# Git flow — actions-workflows

Os workflows reutilizáveis seguem o fluxo dos repositórios VanB (ver `docs/gitflow.md` da vanb-api): ramos `feature/MAT-123-slug` com PR para `main` e commits em Conventional Commits, em inglês.

## Revisão de PR

Não há revisão por IA. O portão é o CI: build, testes, cobertura (Kover), detekt/ktlint, Konsist, gitleaks, squawk e screenshots, conforme o que cada repo roda. Ids de tarefa são do Linear (`MAT-123`) e os ramos seguem `feature/MAT-123-slug`.

| Quando | Revisão |
| --- | --- |
| Label `seguranca` ou `risco-financeiro`, ou PR com migration | o dono revisa antes do merge |
| Todo o resto | sem revisão humana nem de IA; merge se o CI passar |

- O implementador roda build, testes, cobertura e lint localmente e confere o próprio diff contra o checklist da issue antes de abrir o PR.
- Implementação em sessões curtas, uma por issue, com Sonnet por padrão; o contexto de cada sessão é só o `CLAUDE.md`, a issue e os arquivos da seção Contexto.
