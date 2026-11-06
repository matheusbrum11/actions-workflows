# Git flow — actions-workflows

Os workflows reutilizáveis seguem o fluxo dos repositórios VanB (ver `docs/gitflow.md` da vanb-api): ramos `feature/MAT-123-slug` com PR para `main` e commits em Conventional Commits, em inglês.

## Revisão de PR

O revisor é o sub-agent `pr-reviewer`, mantido no repositório `claude-agents` (instalado em `~/.claude/agents`, fora dos repositórios de produto). Ids de tarefa são do Linear (`MAT-123`) e os ramos seguem `feature/MAT-123-slug`.

| Nível | Quando | Revisão |
| --- | --- | --- |
| Só CI | PR só de docs (`*.md`, `docs/**`), só de testes ou de config sem lógica | sem revisão de IA; merge se o CI passar |
| LIGHT | todo o resto | `pr-reviewer` tier LIGHT, só o diff |
| FULL | labels `seguranca` / `risco-financeiro`, qualquer migration, auth/sessão/tokens | `pr-reviewer` tier FULL |

- O revisor recebe só o número do PR, o repo, o id da tarefa com o checklist e o nível.
- Re-revisão com `since_sha` (só as correções); no máximo 2 rodadas, depois escala para o dono.
- O orquestrador não relê o diff depois do revisor.
- O implementador roda build, testes, Kover e lint e confere o próprio diff contra o checklist da issue antes de abrir o PR.
- O que o CI já garante (build, testes, cobertura, lint/detekt/ktlint, Konsist, gitleaks, squawk) fica fora do checklist do revisor.
