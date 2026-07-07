"""Vocabulario do VEREDITO HUMANO (negative_dogfood) — fonte unica.

So o Felipe fala IMPROVED/SAME/WORSE, e SO via clique na tela de curadoria
do :8782 (KICKOFF_CURADORIA), que grava human_verdicts.jsonl ao lado do
corpus. Modulos-MAQUINA (variant_sweep, vision adapter, corpus_to_rag) sao
proibidos de conter esses literais no fonte — e' o que
test_machine_never_writes_human_verdict pina. Consumidor que precisa VALIDAR
a leitura importa DAQUI: conhecer o vocabulario para validar nao e' o mesmo
que poder emiti-lo (membership test nao fabrica veredito).
"""
HUMAN_VERDICTS = ("IMPROVED", "SAME", "WORSE")
