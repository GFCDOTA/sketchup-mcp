"""Vocabulario do VEREDITO HUMANO (negative_dogfood) — fonte unica.

So o Felipe fala IMPROVED/SAME/WORSE, e SO via clique na tela de curadoria
do :8782 (KICKOFF_CURADORIA), que grava human_verdicts.jsonl ao lado do
corpus. Modulos-MAQUINA (variant_sweep, vision adapter, corpus_to_rag) sao
proibidos de conter esses literais no fonte — e' o que
test_machine_never_writes_human_verdict pina. Consumidor que precisa VALIDAR
a leitura importa DAQUI: conhecer o vocabulario para validar nao e' o mesmo
que poder emiti-lo (membership test nao fabrica veredito).

Alem do veredito de regressao, a curadoria carrega mais dois campos de GOSTO,
ambos igualmente EXCLUSIVOS do humano (a maquina nunca escreve nenhum):
  - `liked`  (bool | null): thumbs do Felipe, ORTOGONAL a IMPROVED/SAME/WORSE —
    ele pode gostar de um SAME ou desgostar de um IMPROVED. null = nao sinalizado.
  - `tags`   (list[str]): rotulos livres da curadoria ("industrial", "escuro
    demais", "gostei da luz"). Territorio humano.
Shape completo em schemas/curadoria_verdict.schema.json.
"""
HUMAN_VERDICTS = ("IMPROVED", "SAME", "WORSE")

# `liked` — sinal de GOSTO, ORTOGONAL ao veredito de regressao. bool | null.
# null = nao sinalizado. (Tupla so documental: NAO usar `x in LIKED_VALUES`
# para validar — `1 in (True, False, None)` e' True; use is_liked().)
LIKED_VALUES = (True, False, None)

# Campos que SO o humano preenche num veredito de curadoria. A maquina grava
# sempre null/ausente nos tres (o rail test_machine_never_writes_human_verdict
# guarda os modulos-maquina contra os literais de veredito; liked/tags seguem a
# mesma regra por construcao — nenhum emitter da maquina os escreve).
HUMAN_ONLY_FIELDS = ("human_verdict", "liked", "tags")


def is_human_verdict(value) -> bool:
    """True se `value` e' um veredito de regressao valido (IMPROVED/SAME/WORSE).
    Membership test para VALIDAR a leitura — nao fabrica veredito."""
    return value in HUMAN_VERDICTS


def is_liked(value) -> bool:
    """True se `value` e' um `liked` valido: True, False ou None (bool|null).
    Identidade estrita de proposito — 1/0/'true' NAO sao `liked` (ortogonal e
    tipado; `1 == True` em Python nao pode contaminar o vocabulario)."""
    return value is True or value is False or value is None


def normalize_tags(tags) -> list[str]:
    """Normaliza `tags` do humano numa lista de strings limpa: apara espacos,
    remove vazias e duplicatas, PRESERVA a ordem de primeira ocorrencia.
    Entrada None / nao-lista -> []. Puro e deterministico (sem clock/random)."""
    if not isinstance(tags, (list, tuple)):
        return []
    seen: set = set()
    out: list[str] = []
    for t in tags:
        if not isinstance(t, str):
            continue
        s = t.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out
