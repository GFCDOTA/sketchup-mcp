---
paths:
  - "docs/specs/**"
  - ".claude/specs/**"
---

# Ownership de SPECs e skills

O contrato `Plan2Space/claude-engineering-skills/contracts/ownership.v1.md`
mantém skills reutilizáveis e contratos compartilhados no hub. SPECs de produto,
código, testes e evidências SketchUp são mantidos neste repositório.

- **Nova SPEC de produto:** escreva em `docs/specs/` ou `.claude/specs/` conforme a convenção local, com owner, aceite, testes, rollback e referências externas por commit imutável.
- **Contrato compartilhado:** altere no hub, cite versão e SHA aqui; não copie texto normativo.
- **Skill:** consulte `catalog/skills.json` do hub na versão fixada em `.claude/CLAUDE.md` e verifique a carga. O mecanismo automático é a issue central #29.
- **Estado:** Issues e Project Board guardam prioridade e progresso; a SPEC local preserva decisões e evidências datadas.
