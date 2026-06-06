# Quarto KING designer — relatório (r000, 'SUITE 01')

área 29.3 m² | resultado **OK**

## Vencedor: cabeceira `m018` — **105 pts**
- clearances: lateral 0.79 m, pé 3.29 m, passagem OK
- score: cama_parede_limpa=30, simetria_criados=20, circulacao=20, guarda_roupa=15, tapete=10, cama_com_cabeceira=5, banco_dresser=5
- móveis:
  - **cama_king** (bed) 2.03×1.93 m @(16.16,20.04) parede `m018` — âncora; cabeceira em parede limpa; centralizada
  - **cabeceira** (headboard) 0.06×1.93 m @(17.21,20.04) parede `m018` — painel fino na parede; a cama encosta (leitura intencional)
  - **tapete** (rug) 3.4×2.8 m @(15.51,20.04) parede `m018` — sob a cama, sai nas laterais e no pé
  - **criado_mudo_dir** (nightstand) 0.4×0.45 m @(16.98,21.28) parede `m018` — flanqueando a cabeceira (simétrico, folga mínima)
  - **criado_mudo_esq** (nightstand) 0.4×0.45 m @(16.98,18.8) parede `m018` — flanqueando a cabeceira (simétrico, folga mínima)
  - **guarda_roupa** (wardrobe) 0.6×1.8 m @(18.96,22.89) parede `m019` — parede limpa, frente livre, 1.80 m (planejado linear)
  - **dresser** (dresser) 0.4×1.6 m @(13.9,19.4) parede `m017` — comoda baixa em parede livre, sem competir com guarda-roupa
- **omitidos** (não couberam com folga / sem espaço): banco, poltrona, mesa lateral

## Candidatos testados (paredes de cabeceira)
- cabeceira `m018` — score 105, valid=True
- cabeceira `m019` — score -999, valid=False — bloqueios: [['cama king não coube na parede da cabeceira']]
- cabeceira `m017` — score -999, valid=False — bloqueios: [['cama king não coube na parede da cabeceira']]