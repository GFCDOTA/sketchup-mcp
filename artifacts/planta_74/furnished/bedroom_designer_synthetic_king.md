# Quarto KING designer — relatório (synthetic_king, 'SUITE MASTER KING')

área 22.6 m² | resultado **OK**

## Vencedor: cabeceira `wR` — **100 pts**
- clearances: lateral 1.52 m, pé 2.43 m, passagem OK
- score: cama_parede_limpa=30, simetria_criados=20, circulacao=20, guarda_roupa=15, tapete=10, banco_dresser=5
- móveis:
  - **cama_king** (bed) 2.03×1.93 m @(3.46,2.5) parede `wR` — âncora; cabeceira em parede limpa; centralizada
  - **tapete** (rug) 3.4×2.8 m @(2.78,2.5) parede `wR` — sob a cama, sai nas laterais e no pé
  - **criado_mudo_dir** (nightstand) 0.45×0.5 m @(4.25,3.72) parede `wR` — flanqueando a cabeceira (simétrico)
  - **criado_mudo_esq** (nightstand) 0.45×0.5 m @(4.25,1.29) parede `wR` — flanqueando a cabeceira (simétrico)
  - **guarda_roupa** (wardrobe) 2.4×0.6 m @(2.0,0.42) parede `wB` — parede lateral/oposta limpa, com frente livre
  - **dresser** (dresser) 1.6×0.45 m @(0.85,4.65) parede `wT` — comoda baixa em parede livre, sem competir com guarda-roupa
- **omitidos** (não couberam com folga / sem espaço): banco, poltrona, mesa lateral

## Candidatos testados (paredes de cabeceira)
- cabeceira `wR` — score 100, valid=True
- cabeceira `wB` — score 100, valid=True
- cabeceira `wT` — score -999, valid=False — bloqueios: [['cama king não coube na parede da cabeceira']]