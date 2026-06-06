# Quarto KING designer — relatório (r003, 'SUITE 02')

área 14.7 m² | resultado **OK**

## Vencedor: cabeceira `m014` — **105 pts**
- clearances: lateral 1.38 m, pé 1.28 m, passagem OK
- score: cama_parede_limpa=30, simetria_criados=20, circulacao=20, guarda_roupa=15, tapete=10, cama_com_cabeceira=5, banco_dresser=5
- móveis:
  - **cama_queen** (bed) 2.03×1.58 m @(9.42,18.37) parede `m014` — âncora; cabeceira em parede limpa; centralizada
  - **cabeceira** (headboard) 0.06×1.58 m @(8.37,18.37) parede `m014` — painel fino na parede; a cama encosta (leitura intencional)
  - **tapete** (rug) 3.4×2.8 m @(10.07,18.37) parede `m014` — sob a cama, sai nas laterais e no pé
  - **criado_mudo_dir** (nightstand) 0.4×0.45 m @(8.6,19.43) parede `m014` — flanqueando a cabeceira (simétrico, folga mínima)
  - **criado_mudo_esq** (nightstand) 0.4×0.45 m @(8.6,17.3) parede `m014` — flanqueando a cabeceira (simétrico, folga mínima)
  - **guarda_roupa** (wardrobe) 1.5×0.6 m @(9.71,20.23) parede `m007` — parede limpa, frente livre, 1.50 m (planejado linear)
  - **dresser** (dresser) 0.4×1.6 m @(11.41,18.71) parede `m016` — comoda baixa em parede livre, sem competir com guarda-roupa
- **omitidos** (não couberam com folga / sem espaço): banco, poltrona, mesa lateral

## Candidatos testados (paredes de cabeceira)
- cabeceira `m014` — score 105, valid=True
- cabeceira `m002` — score -999, valid=False — bloqueios: [['cama king não coube na parede da cabeceira']]
- cabeceira `m003` — score -999, valid=False — bloqueios: [['cama king não coube na parede da cabeceira']]