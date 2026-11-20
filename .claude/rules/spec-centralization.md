---
paths:
  - "docs/specs/**"
  - ".claude/specs/**"
---

# Centralização de SPECs e skills

Todas as SPECs e skills do ecossistema Plan2Space são mantidas exclusivamente em
`Plan2Space/claude-engineering-skills`. Nenhuma SPEC nova pode ser criada fora desse repositório.
Toda alteração de SPEC é feita na fonte central e referenciada por este repositório.

- **Nova SPEC:** não crie arquivo novo em `docs/specs/` nem em `.claude/specs/`. Abra a proposta na fonte central.
- **SPEC existente:** não a reescreva aqui. Mudança de conteúdo autoritativo segue o plano de migração da fonte central.
- **Skill:** consumida por referência versionada (`skills.manifest.json`, pino por SHA ou tag), nunca copiada como fonte.
- **Exceção temporária:** só existe quando registrada na fonte central para a migração. Sem registro, a violação é bloqueante.
- **Governança:** `specs/governance/SPEC-001-centralized-engineering-governance.md` no repositório central.
