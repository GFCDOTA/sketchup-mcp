# FP-042 / P1 — fronteiras de domínio e dependências

Baseline `develop` após merge #256: `a915ddc3e8e95a5dd3946cb94bd74d92ec8479fe`.

**Problema:** centralização legada em `tools/furnish_apartment.py`; novos pacotes de
cômodo ainda são majoritariamente declarativos. `tools.rooms.shared.geometry`
e `tools.rooms.shared.project_paths` já são reutilizados.

**Regra desta etapa:** nenhum pacote de cômodo `tools.rooms.X` deve importar
`tools.rooms.Y` onde X != Y; `shared` não deve importar implementações
legadas específicas de cômodos. Isso é verificado via AST pelo
`python -m tools.rooms.ownership_audit`.

**Limitação intencional:** o gate tem escopo EXCLUSIVO aos novos pacotes. Ainda
não certifica a migração de `tools/furnish_apartment.py`, `tools/kitchen_layout.py`,
`tools/bathroom_layout.py`, `tools/bedroom_designer.py`, `tools/service_layout.py`
ou scripts Ruby. Para cada uma dessas dependências, criar microfatia com adapters
e golden comparison; não alterar inadvertidamente a geometria.

**Migrações seguintes:** orquestrador de boxes, depois owners de cozinha/banho,
quartos/sala, serviços/varanda; posteriormente marcenaria e materiais comuns.
O inventário FP-042 deve ser atualizado para toda adição/mudança de ownership.
