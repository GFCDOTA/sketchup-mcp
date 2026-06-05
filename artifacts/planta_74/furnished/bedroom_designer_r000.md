# Quarto KING designer — relatório (r000, 'SUITE 01')

área 29.3 m² | resultado **OK**

## Vencedor: cabeceira `m018` — **90 pts**
- clearances: lateral 0.79 m, pé 3.32 m, passagem OK
- score: cama_parede_limpa=30, simetria_criados=20, circulacao=20, tapete=10, banco_dresser=10
- downgrades: guarda-roupa não coube com frente livre
- móveis:
  - **cama_king** (bed) 2.03×1.93 m @(16.19,20.04) parede `m018` — âncora; cabeceira em parede limpa; centralizada
  - **tapete** (rug) 3.4×2.8 m @(15.51,20.04) parede `m018` — sob a cama, sai nas laterais e no pé
  - **criado_mudo_dir** (nightstand) 0.45×0.5 m @(16.98,21.26) parede `m018` — flanqueando a cabeceira (simétrico)
  - **criado_mudo_esq** (nightstand) 0.45×0.5 m @(16.98,18.83) parede `m018` — flanqueando a cabeceira (simétrico)
  - **banco** (bench) 0.45×1.4 m @(14.9,20.04) parede `None` — aos pés da cama, centralizado
  - **dresser** (dresser) 0.45×1.6 m @(19.03,22.69) parede `m019` — parede livre, baixa, sem competir com guarda-roupa
  - **poltrona** (armchair) 0.8×0.8 m @(12.25,23.32) parede `None` — canto livre perto da janela (leitura)
  - **mesa_lateral** (side_table) 0.4×0.4 m @(12.9,23.12) parede `None` — ao lado da poltrona
- **omitidos** (não couberam com folga / sem espaço): guarda-roupa

## Candidatos testados (paredes de cabeceira)
- cabeceira `m018` — score 90, valid=True
- cabeceira `m019` — score -999, valid=False — bloqueios: [['cama king não coube na parede da cabeceira']]
- cabeceira `m017` — score -999, valid=False — bloqueios: [['cama king não coube na parede da cabeceira']]