# BED-CLASS — cycle 001 (3a classe; criado-mudo como SATELITE)

- **Data:** 2026-06-12
- **Juiz:** ChatGPT (web, GPT-5 thinking "Alto"), matriz @9847836 via browsing.
  Chat: https://chatgpt.com/c/6a2b600b-3800-83e9-bfe9-dbea5da1596e
- **Gates previos:** 12/12 derivados, 6/6 sabotagens + satelite provado, matriz
  9/9 PASS, suite 670 ✓.

## VEREDITO_CLASSE: WARN — "otimo nascimento de classe"

- **IDENTIDADE:** "sim, leem como CAMAS reais. Ja nasceu bem... a dominancia do
  colchao esta funcionando, a relacao base/colchao e' crivel."
- **ARQUETIPOS:** 3 linguagens, com sobreposicao — "a linguagem do arquetipo ainda
  depende mais da ETIQUETA do builder do que de um gesto formal muito forte."
- **ESCALA:** "casal->queen->king escala certo. Ponto forte... progressao limpa."
- **PIOR_CELULA:** queen-box-legs-med — "box+legs reduz a massa inferior justamente
  onde o BOX deveria afirmar presenca; nem leve como platform, nem robusta como box."

## TOP3_FIXES_DE_CLASSE (cycle 002 da cama)

1. **Coerencia BASE<->ARQUETIPO (regra rigida):** platform enfatiza leveza/reveal/
   flutuacao; upholstered aceita pes subordinados a cabeceira/maciez; box COM pes
   so se os pes SUSTENTAM a leitura box (nao esvaziam a massa).
2. **Assinatura da CABECEIRA por arquetipo:** platform fina/arquitetonica; uphol
   acolhedora com leitura de volume; box contida/subordinada — legivel a distancia.
3. **Gramatica de frente/lateral da base** anti "caixote limpo demais": reveal/
   saia/recuo desenhados — "base parecer desenhada, nao so extrudada".

**OVERFIT_CHECK:** "fix proibido = arrumar so a queen-box-legs-med. O certo e'
subir uma REGRA DE COERENCIA base<->arquetipo para toda a classe."

## 🏛️ SATELITE = PADRAO OFICIAL DO PROGRAMA (decisao do juiz)

> "Sim, faz muito sentido. Essa regra do criado derivado da cama e' boa pra
> caralho como primeira constraint entre classes, porque NASCE DE USO REAL e nao
> de gosto. Ela impede o erro sistemico classico — criado padrao unico servindo
> para qualquer cama. Eu manteria como PADRAO OFICIAL DO PROGRAMA:
> **classe principal deriva a regua; classe satelite se adapta.**"

(Implementado: nightstand_satellite_gate — alvo derivado: platform 0.38 /
uphol 0.57 / box 0.62; criado padrao 0.55 FALHA em cama platform.)

## FASE 0 — diagnostico do bed_builder

Anatomia boa; sem teoria (validate raso, hardcodes, sempre plinto, mattress_inset
morto). Upgrades subiram pra spec/builder com defaults neutros.
