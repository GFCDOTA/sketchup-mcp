# Spike técnica — Render & Asset Providers (Fase 5)

> Investigação HONESTA do que é automatizável NESTE ambiente. Sem inventar API.
> Evidência empírica (instalações reais) + capacidade documentada. NÃO é integração —
> é decisão de caminho. Data: 2026-06.

## Evidência empírica (o que está instalado)

| Achado | Caminho / prova |
|---|---|
| Enscape instalado | `C:\Program Files\Enscape` — plugin **.NET** `Enscape.Sketchup.Plugin.Host-net10.0`; `tools/` só `setvrlservice.exe`; **sem .rb / sem CLI de render** |
| V-Ray (Chaos) instalado | `C:\Program Files\Chaos\V-Ray\V-Ray for SketchUp\extension` — **`vray4sketchup2026.so`** (suporta SU 2026!) + pasta `ruby/` (`module VRay` em `init.rb`, carrega `sketchup2vray`, `scene`, `vray`) + **`vray.exe` standalone** (headless) + pasta `scene/` (.vrscene) |
| V-Ray licença | `init.rb` checa `VRay::SketchupEntitlements.active_entitlement` (EULA/entitlement) + módulos `require_crypt` (obfuscados) |
| V-Ray NÃO carregado no nosso SU 2026 | ausente de `…\SketchUp 2026\SketchUp\Plugins` (só habitat/su_*/tc_visualizer + autorun_*) |
| Trimble Connect | `tc_visualizer` carregado no SU; 3D Warehouse sem CLI |
| RenderProvider básico | `interior/renderers/sketchup_basic_provider.py` — **FUNCIONAL e provado** (render via SU + PowerShell Start-Process, base intacta) |

## Matriz de decisão

| Ferramenta | Capacidade | Método de automação | Riscos | Recomendação | Precisa MCP? |
|---|---|---|---|---|---|
| **SketchUp básico** | top/iso/front/closeup (linha, sem luz) | ✅ Ruby (place_layout/build_furniture) + Start-Process (FEITO, Fase 4) | desktop interativo p/ write_image | **JÁ É O PROVIDER PADRÃO** | Não (adapter interno) |
| **Enscape** | PREVIEW realtime (layout/escala/luz básica) | ❌ GUI-only: plugin .NET roda DENTRO do SU, render pela UI. Sem Ruby/CLI/headless achados | sem API de script; UI-bound; automação só por computer-use (frágil) | **PREVIEW MANUAL** — não automatizar agora (ROI baixo vs fragilidade). Reavaliar se a UI tiver atalho/handoff | Não (seria computer-use se um dia) |
| **V-Ray** | FINAL/premium (tecido/madeira/luz indireta) | ✅ **VIÁVEL — CONFIRMADO EMPIRICAMENTE** (probe_vray*.rb em SU 2026): extensão CARREGA (loaded=true), `module VRay` 100% alcançável de -RubyStartup, fluxo render→save MAPEADO (`RenderSessionProduction/Export.new(context:).start`, `VRayImage#save`, `ModelExporter#update_camera`, `vray.exe` headless do `.vrscene`) | (a) **precisa LICENÇA** ativa (entitlement — já instalada); (b) `context`/args de `start_render` no source CRYPT (mapear por tentativa, não inventar); (c) render lento (min) + possível VFB window | **MELHOR candidato → `VRayFinalProvider`** (adapter interno). Caminho: `RenderSessionExport`→`.vrscene`→`vray.exe` headless (desacopla do GUI). **Fase 8** focada. available()=True | Não (adapter interno) |
| **Trimble / 3D Warehouse** | biblioteca de assets/referência | ❌ sem CLI de download; API web existe mas com auth; download é browser/UI | licença per-asset (maioria "combined work only"); ToS; bloat | **Chrome MCP (já existe)** + permissão do Felipe por asset + manifest de provenance + cache gitignored (`assets/third_party_cache/`); NUNCA redistribuir geometria (alinha com Fase 7) | Usa o **Chrome MCP existente** — sem MCP novo |

## MCP separado — avaliação

- Adapter interno **basta** p/ SU básico (provado) e p/ V-Ray (Ruby + vray.exe = adapter interno).
- Enscape (GUI) = computer-use se algum dia; 3DW = Chrome MCP existente.
- Fila de render stateful / daemon long-lived = **não é necessário agora** (renders são one-shot).
- **Veredito: NÃO criar MCP separado.** Adapters internos (RenderProvider) + MCPs existentes (Chrome, computer-use) cobrem tudo. Reavaliar só se surgir necessidade real de daemon/fila/sessão longa.

## Recomendação explícita (gate da Fase 5)

1. **Enscape**: `manual-only` (preview manual; não automatizar — GUI-only).
2. **V-Ray**: `adapter interno` — **VIÁVEL (confirmado)**. Fase 8 nail o `context`/`start_render` (empírico,
   tentativa cuidadosa) → `RenderSessionExport`→`.vrscene`→`vray.exe` headless. Pré-req: licença ativa (já há).
   **NÃO é blocked** — é trabalho focado de orquestração. Felipe pode acelerar com um snippet do AppSDK.
3. **3D Warehouse**: `Chrome MCP existente` + manifest + gitignore (Fase 7).
4. **MCP separado**: `não` (adapters internos bastam).

### Correção pós-probe (Felipe apontou: "tem todas extensões no SketchUp")
A 1a leitura (ext ausente dos Plugins) estava ERRADA: as extensões registram fora da pasta Plugins
(Enscape + V-Ray = `loaded=true` no SU). A `probe_vray*.rb` provou a API. V-Ray saiu de "blocked" → "VIÁVEL".

→ **Gate Fase 5 GREEN**: spike honesta concluída, sem inventar API, recomendação explícita por ferramenta.
Próximo no plano: Fase 6 (Enscape preview) fica **manual/blocked** pela spike → pular sem forçar;
o caminho de render premium real é V-Ray (Fase 8) com a pré-condição de licença+setup. O core
(placement + anatomia + provider básico) NÃO depende disso.
