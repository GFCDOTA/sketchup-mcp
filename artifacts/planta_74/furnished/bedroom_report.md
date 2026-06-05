# Relatorio auto-mobiliado — quartos (planta_74)

8 comodos | 2 quartos | 2 mobiliados OK

## `r000` — SUITE 01  (BEDROOM, via name_regex)
- area **29.3 m2** | cama **king** (alvo king)
- **vencedor**: cabeceira `m018` — **110.0 pts**
  - moveis: bed, nightstand, nightstand, wardrobe
  - score: folga_lateral=20.0, folga_pe=15.0, centralizada=15.0, criados=15.0, guarda_roupa=20.0, cabeceira_sem_janela=25.0
  - prós: folga lateral 0.79m (+20); folga pe 3.32m (+15); 2 criados-mudos (+15); guarda-roupa com frente livre (+20)
  - rejeitado `m019` (valid=False, 0.0 pts): dentro_do_comodo, nao_bloqueia_circulacao, nao_bloqueia_porta, nao_invade_abertura, nao_in
  - rejeitado `m017` (valid=True, 95.6 pts): cama descentralizada 1.2m

## `r001` — A.S. | TERRACO SOCIAL | TERRACO TECNICO  (SERVICE, via name_regex)
- **PULADO**: tipo SERVICE: brain de quarto so mobilia BEDROOM

## `r002` — SALA DE JANTAR | SALA DE ESTAR  (LIVING, via name_regex)
- **PULADO**: tipo LIVING: brain de quarto so mobilia BEDROOM

## `r003` — SUITE 02  (BEDROOM, via name_regex)
- area **14.7 m2** | cama **queen** (alvo queen)
- **vencedor**: cabeceira `m014` — **90.0 pts**
  - moveis: bed, nightstand, nightstand
  - score: folga_lateral=20.0, folga_pe=15.0, centralizada=15.0, criados=15.0, guarda_roupa=0.0, cabeceira_sem_janela=25.0
  - prós: folga lateral 1.38m (+20); folga pe 1.36m (+15); 2 criados-mudos (+15)
  - rejeitado `m002` (valid=True, 74.3 pts): folga lateral 0.53m < 0.6m, cama descentralizada 0.4m, cabeceira sob/na parede da janela (
  - rejeitado `m003` (valid=False, 0.0 pts): dentro_do_comodo

## `r004` — COZINHA  (KITCHEN, via name_regex)
- **PULADO**: tipo KITCHEN: brain de quarto so mobilia BEDROOM

## `r005` — BANHO 01  (BATHROOM, via name_regex)
- **PULADO**: tipo BATHROOM: brain de quarto so mobilia BEDROOM

## `r006` — BANHO 02  (BATHROOM, via name_regex)
- **PULADO**: tipo BATHROOM: brain de quarto so mobilia BEDROOM

## `r007` — LAVABO  (BATHROOM, via name_regex)
- **PULADO**: tipo BATHROOM: brain de quarto so mobilia BEDROOM
