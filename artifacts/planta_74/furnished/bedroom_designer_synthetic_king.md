# Quarto KING designer — relatório (synthetic_king, 'SUITE MASTER KING')

área 22.6 m² | resultado **OK**

## Vencedor: cabeceira `wR` — **105 pts**
- clearances: lateral 1.52 m, pé 2.4 m, passagem OK
- score: cama_parede_limpa=30, simetria_criados=20, circulacao=20, guarda_roupa=15, tapete=10, cama_com_cabeceira=5, banco_dresser=5
- móveis:
  - **cama_king** (bed) 2.03×1.93 m @(3.43,2.5) parede `wR` — âncora; cabeceira em parede limpa; centralizada
  - **cabeceira** (headboard) 0.06×1.93 m @(4.48,2.5) parede `wR` — painel fino na parede; a cama encosta (leitura intencional)
  - **tapete** (rug) 3.4×2.8 m @(2.78,2.5) parede `wR` — sob a cama, sai nas laterais e no pé
  - **criado_mudo_dir** (nightstand) 0.4×0.45 m @(4.25,3.74) parede `wR` — flanqueando a cabeceira (simétrico, folga mínima)
  - **criado_mudo_esq** (nightstand) 0.4×0.45 m @(4.25,1.26) parede `wR` — flanqueando a cabeceira (simétrico, folga mínima)
  - **guarda_roupa** (wardrobe) 3.0×0.6 m @(2.3,0.42) parede `wB` — parede limpa, frente livre, 3.00 m (planejado linear)
  - **dresser** (dresser) 1.6×0.4 m @(1.0,4.68) parede `wT` — comoda baixa em parede livre, sem competir com guarda-roupa
- **omitidos** (não couberam com folga / sem espaço): banco, poltrona, mesa lateral

## Candidatos testados (paredes de cabeceira)
- cabeceira `wR` — score 105, valid=True
- cabeceira `wB` — score 105, valid=True
- cabeceira `wT` — score -999, valid=False — bloqueios: [['cama king não coube na parede da cabeceira']]