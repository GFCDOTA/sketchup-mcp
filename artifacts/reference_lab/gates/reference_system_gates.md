# Reference System Gates — 4 gates de inteligência de uso

> Além dos gates de fidelidade (kitchen_validation, furniture_overlap, geometry_sanity). Estes
> respondem: a referência bonita vira uma cozinha que FUNCIONA na planta_74 compacta? Cada
> análise de referência e cada theme preset declara um veredito por gate (PASS/WARN/FAIL).

## 1. theme_fit_gate — o tema combina com a planta compacta?
**Pergunta:** a linguagem visual faz sentido numa cozinha COMPACTA linear (planta_74), ou só
funciona em mansão/loft amplo?
- FAIL: exige ilha, bancada em L, pé-direito alto, parede de coifa industrial gigante.
- WARN: escurece/aperta o compacto, mas dá pra compensar (luz, madeira, espelho).
- PASS: a vibe transfere pro compacto sem precisar da estrutura da foto.
- Evidência: render na planta_74 + veredito GPT/Felipe.

## 2. ergonomics_gate — altura/alcance/uso/circulação/bancada
**Pergunta:** as medidas e proporções fazem sentido pro uso diário?
- Ferramenta: `tools/kitchen_ergonomics.py` (12 medidas: bancada 88-92, sóculo 10-15, base
  50-60, aéreo 30-35, clearance 50-60, coifa 45-65, torre 60-75, etc.). FAIL fora de faixa.
- Checagens extras: área de apoio na bancada? circulação ≥ folga mínima? alcance do aéreo?
- Medida da referência entra como HIPÓTESE; o gate valida contra a faixa + o PDF.

## 3. maintenance_gate — poeira / limpeza / mancha / vão inútil
**Pergunta:** vai ser ruim de manter na vida real?
- FAIL: vão aberto que só pega poeira; pedra/madeira que mancha na zona molhada sem proteção;
  rejunte demais; nicho fundo sem acesso; ripado que junta gordura na cozinha.
- WARN: superfície que marca digital (preto fosco/ultra-gloss); canto vivo difícil de limpar.
- PASS: superfícies laváveis, sem vão inútil, zona molhada/quente protegida.
- Ver `wood_wetzone_gate` (madeira na pia/cooktop) e os anti-padrões da KB.

## 4. buildability_gate — marcenaria executa ou é só foto?
**Pergunta:** um marceneiro real consegue construir, ou é truque de render/Pinterest?
- FAIL: balanços impossíveis sem estrutura; junções que não fecham; eletro que não cabe no
  nicho; "flutua" sem suporte; medida que ignora espessura de chapa/eletro/norma.
- WARN: exige ferragem/material caro ou execução difícil (viável, mas custa).
- PASS: módulos padrão, ferragem comum, tolerâncias reais.

## Regra de ouro (todos os gates)
```
Medida de Pinterest = HIPÓTESE.
PDF + ergonomia + gate = VERDADE.
```
Se a referência diz "aéreo 60cm / bancada 90 / armário até o teto", isso depende de pé-direito,
eletros, coifa, pessoa, norma, marcenaria e espaço REAL — valida, não copia.

---

# Gates BLACK_WOOD_GOLD / temas escuros premium (DECISION 003)

Obrigatórios pra temas escuros/premium na planta_74 compacta. Cada variação declara veredito.

1. **cave_check** — ficou escura/pesada demais? Se sim → +LED, reflecta pontual, clarear piso,
   ou trocar um volume pra grafite/champagne. (já validado no dark_walnut.)
2. **daylight_reflection_check** — DE DIA, existe superfície que devolve luz? (geladeira satin/
   reflexiva, vidro reflecta pontual, pedra satin/polida, champagne discreto, parede clara
   controlada). Sem nenhuma → WARN (vira buraco escuro de dia).
3. **maintenance_check** — piso/cuba/pedra/vidro/metais vão ser chatos de limpar/manter? WARN
   quando muita superfície preta, vidro demais, ou pedra muito brilhante. (cuba/torneira preta
   marca água; preto fosco marca dedo.)
4. **appliance_workflow_check** — forno/micro/cooktop/pia/bancada fazem sentido no uso diário?
   NÃO priorizar estética se o fluxo ficar burro (forno longe do preparo, micro inacessível).
5. **reflecta_control_gate** — vidro reflecta/smoked SÓ como detalhe: 1–2 módulos no máx,
   de preferência com LED interno ou módulo superior. Nunca fachada inteira.
6. **black_floor_gate** — piso preto SÓ como teste; default = grafite médio / cimento queimado
   quente / porcelanato escuro moderado. Preto com veio dourado = variante autoral, não default.
7. **fake_luxury_check** — bronze/dourado e veios dourados SUTIS. Se parecer ostentação fake,
   reduzir. (veião dourado gigante = "mansão fake Pinterest".)
8. **buildability_check** — executável por marcenaria/pedreiro real? Material caro / execução
   crítica / manutenção difícil → marcar risco. (cuba esculpida = cuidado com emenda/caimento.)

**Critério de sucesso do tema escuro:** causar impacto MAS continuar usável, limpável, clara o
suficiente de dia, e coerente com metragem compacta.
