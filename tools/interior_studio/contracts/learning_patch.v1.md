# LEARNING_PATCH v1

> O ÚNICO artefato que pode atualizar a memória do Arquiteto. A resposta do Consult GPT NUNCA é
> ingerida direto: vira um patch `status=draft`, o Felipe vê o **diff** e aprova/rejeita; só após
> aprovação ele altera `felipe_style_dna.md` + anti-patterns do juiz + learning log.
> Geração AUTOMÁTICA (a partir do ARCHITECT_ANSWER) · aplicação MANUAL (Felipe).

## Fluxo
```
ARCHITECT_ANSWER → from_answer() → LEARNING_PATCH (draft) → dashboard mostra DIFF
   → Felipe aprova → approve() aplica (dedupe) no DNA/juiz + atualiza o ciclo
   → Felipe rejeita → reject() (não toca memória)
```

## Campos (rastreabilidade obrigatória)
```json
{
  "patch_id": "LP-SOFA-001",
  "created_at": "<iso>",
  "status": "draft | applied | rejected",
  "source": "Consult GPT | Felipe | Claude | Scout",
  "source_question_id": "<id da pergunta>",
  "source_answer_id": null,
  "cycle_id": "CYCLE-003",
  "project": "planta_74", "room": "living", "asset": "sofa",
  "theme": "BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE",
  "branch": "<git>", "commit_sha": "<git>",
  "applies_to": ["felipe_style_dna", "anti_patterns", "learning_log"],
  "confidence": "low | medium | high",
  "requires_felipe_confirmation": true,
  "verdict": "PASS | WARN | FAIL",
  "evidence": {"reference_ids": [], "render_paths": [], "source_urls": [],
               "raw_question_path": "", "raw_answer_path": ""},
  "proposed_changes": {
    "new_rules": [], "anti_patterns": [], "visual_tokens": [],
    "material_lessons": [], "maintenance_lessons": [], "forbidden_patterns": [],
    "build_spec_constraints": [], "golden_sample_candidates": []
  },
  "next_microtask": {"id": "MT-SOFA-003", "title": "Gerar SOFA_BUILD_SPEC", "description": "..."},
  "review": {"approved_by": null, "approved_at": null, "rejected_reason": null},
  "applied": {"applied_at": null, "files_changed": []}
}
```

## Regras
- Aplicar é **idempotente** (reusa o dedupe do `ingest`): aprovar 2× não duplica regra/anti-pattern.
- `compute_diff()` mostra só o que de fato muda (separa `add` de `dup`).
- Nada vira memória sem `review.approved_at`.
- Storage: `.ai_bridge/learning_patches/LP-*.json`.
