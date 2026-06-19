# Room Furnishing Method — "o método" (golden-sample, 2026-06-19)

> Descoberto mobiliando a COZINHA da planta_74 (Minecraft → marcenaria técnica →
> cozinha planejada moderna). A **ordem** é o método. Inverter (começar por "deixa
> bonito") = "porra aleatória bonita no lugar errado". Este é o template de TODO cômodo.

## A ordem (não pular, não inverter)

1. **PDF-anchor** — respeitar a planta PRIMEIRO: pontos fixos (hidráulica/pia, porta,
   parede, janela), circulação. O que é fixo no PDF é fixo no modelo. Ex.: a pia da
   cozinha é ponto hidráulico da parede oeste — `tools/kitchen_validation.py` ABORTA o
   build se ela migrar. (Consensus pode não ter o símbolo → ancorar na borda do polígono.)
2. **Componentização** — cada móvel/módulo = grupo top-level SEPARADO, nomeado, editável,
   validável. Clique único seleciona só aquela peça. 0 geometria solta no root; shell
   (paredes/piso/portas) locked. Prova: `tools/skp_editability_report.rb`.
3. **Forma técnica** — módulos com proporção REAL (não cubo): espessura de chapa/tampo,
   sóculo recuado, portas/gavetas separadas com reveals, embutidos (cooktop/cuba),
   respiro/folga. Critério: lê como planejado MESMO em massa cinza.
4. **Linguagem de design** — SÓ AQUI entra beleza: paleta (madeira/off-white/pedra/inox/
   grafite), fillers, painéis de acabamento, cava/puxador slim, alinhamento de topo,
   coifa slim integrada. Cores entram por PAPEL (kind próprio `kc_*`), senão o cache de
   material por kind pinta o módulo todo com a 1ª peça.
5. **Render/V-Ray** — só depois que forma E design estão certos. Hero render por último.

## Regras de ouro

- **Golden sample:** a cozinha final é a régua de qualidade. Cômodo novo tem que
  ACOMPANHAR esse nível antes de avançar.
- **Subir o apê inteiro ANTES do V-Ray hero.** Render bonito em 1 cômodo com o resto cru
  = sensação de demo quebrada. Primeiro nivela tudo, depois V-Ray.
- **Validar visual com gate + GPT** (massa cinza isolada por cômodo, ângulos múltiplos;
  `render_kitchen_angles.rb` esconde o resto → zero oclusão). Veredito visual nunca é
  auto — é o Felipe / GPT via Chrome (URL raw do PNG pushado).
- **Compacto:** apê de 74m² → móveis compactos, circulação livre, sem bloco genérico.

## Aplicação por cômodo (checklist)
PDF-anchor ✓ → circulação ✓ → componentes nomeados ✓ → forma real ✓ → paleta/linguagem ✓
→ gates (geometry_sanity + overlap + cômodo-validation) ✓ → ângulos cinza ✓ → veredito ✓
→ (apê todo no nível) → V-Ray hero.
