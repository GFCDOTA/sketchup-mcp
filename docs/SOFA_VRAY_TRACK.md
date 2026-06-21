# SOFA — track de realismo V-Ray (último track)

> Geometria ✅ (PASS, 14 ciclos GPT) e albedo-preview ✅ (PASS, 2 ciclos). O GPT (diretor)
> liberou o track final: **V-Ray** — usar os MESMOS maps (albedo/bump tileáveis) e ajustar
> **roughness / bump / sheen / fuzz / fresnel**. Em tecido escuro é AQUI que o realismo aparece
> (a preview flat do SketchUp não mostra sheen/bump fino — comprovado nos ciclos de material).

## Spec (pronto, por código)

`configs/sofa_vray_material_spec.json` — **SofaVRayMaterialSpec**, de CLASSE por `material_style`,
com os valores de partida do GPT (dark: roughness 0.85, reflection 0.20, bump 0.045, sheen 0.35,
fuzz 0.25, fresnel on) referenciando os maps de `sofa_fabric_material.py`. Render-engine-agnóstico:
um applier consome isto e cria o `VRayBRDF`.

## ⚠️ Bloqueio de AMBIENTE (achado 2026-06-10)

- **V-Ray for SketchUp ESTÁ instalado**: `C:\Program Files\Chaos\V-Ray\V-Ray for SketchUp\`
  (extensão Ruby `extension/vray/vray.rb`, `sketchup2vray.rb`; engine em `Chaos\Cosmos\tools\vray`).
  Chaos Cosmos + V-Ray Swarm 2 (render farm) também presentes.
- **MAS não está carregado no SketchUp 2026**: nenhum loader V-Ray na pasta `Plugins` do SU 2026,
  e nenhum registro Chaos→SU 2026 (HKLM/HKCU). Só o SU 2026 existe na máquina (sem 2023-2025).
  → O SU 2026 é novíssimo; o V-Ray foi instalado/registrado p/ uma versão anterior (ou o hookup
  do SU 2026 não foi feito). **Render V-Ray scriptado/headless no SU 2026 que usamos = bloqueado**
  até o V-Ray ser hookado no SU 2026 (repair/reinstall do V-Ray apontando p/ SU 2026, se a versão
  suportar SU 2026) — é mudança de instalação/sistema, decisão do Felipe.

## Caminhos possíveis (decisão macro do Felipe)

1. **Hookar V-Ray no SU 2026** (repair/reinstall apontando p/ 2026, se suportado) → aí dá p/
   scriptar o applier do spec + render headless e rodar o loop GPT no render real.
2. **Setup V-Ray interativo**: Felipe abre o `.skp` no SU+V-Ray (versão suportada), eu entrego o
   applier do spec (Ruby V-Ray API) + ele roda o render; GPT julga via Chrome.
3. **Render farm / cockpit**: usar Swarm/cockpit p/ o render canônico (memória: `:8765` cockpit,
   Swarm render-ready).
4. **Adiar V-Ray**: geometria + albedo já entregam um sofá de CLASSE coerente; V-Ray quando o
   ambiente estiver pronto.

## Regra mantida

Render/aparência **nunca** é auto-julgado (visual-review-chrome-only). O loop GPT roda no render
real (V-Ray), não na preview. Cada ajuste de roughness/bump/sheen entra no **spec de CLASSE**,
não num exemplar.
