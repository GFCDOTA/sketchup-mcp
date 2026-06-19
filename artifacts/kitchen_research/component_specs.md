# Kitchen Component Upgrade Specs — "planejado caro" (SPEC ONLY)

> Papel: COMPONENT BUILDER (spec only). NÃO edita `kitchen_layout.py`, `.skp`, `.rb`.
> Aplicação é SERIAL, feita depois pelo orquestrador.
> Sala r004, cozinha LINEAR na parede OESTE. Pia/parede/porta = FIXAS (PDF).
> Referência manda na LINGUAGEM; PDF manda na POSIÇÃO; gates mandam na segurança.

## Contexto técnico apurado (cadeia kind → material → V-Ray)

Rastreei a cadeia inteira para saber ONDE cada upgrade entra sem mexer em geometria:

1. `kitchen_layout.py::_kmod()` emite sub-peças com `kind = "kc_<papel>"`
   (`kc_tampo`, `kc_backsplash`, `kc_corpo`, `kc_porta`, `kc_porta_sup`, `kc_corpo_sup`,
   `kc_gaveta`, `kc_niche_wood`, `kc_soculo`, `kc_geladeira`, `kc_puxador`, ...).
2. `place_layout_skp.rb:117` materializa CADA box com
   `pl_material(model, "ph_#{b['kind']}", b['rgb'])` →
   o material SU final é **`ph_kc_tampo`, `ph_kc_backsplash`, `ph_kc_corpo`, ...**
   (prefixo `ph_` + o kind inteiro `kc_...`).
3. `vray_export.rb` (linhas 18-50) tem o `tex_map` que casa NOME DE MATERIAL → PNG de textura.
   Hoje as chaves são `ph_corpo`, `ph_porta`, `ph_tampo`, `ph_bancada`... (móveis genéricos
   `ph_*`) **e o gate `VRAY_STONE` casa `ph_bancada` / `ph_bancada_banho`.**

### GAP load-bearing (a raiz do "flat" da cozinha)

**NENHUMA chave do `tex_map` casa os materiais `ph_kc_*` da cozinha planejada.**
`ph_bancada` ≠ `ph_kc_tampo`. Logo, mesmo com `VRAY_STONE=1`, o tampo/backsplash de PEDRA,
a madeira do corpo inferior e o nicho de madeira do aéreo **recebem zero textura no V-Ray** —
saem com a cor RGB chapada. É exatamente o sintoma do briefing ("veios de pedra... NÃO aparecem
no flat"): não é só falta de V-Ray, é que a cozinha não está cadastrada no mapa de texturas.
Já existe `stone_counter.png` gerado (`gen_textures.py:172`) e `wood_medium.png`/`wood_dark.png` —
os PNGs existem, só não estão wired para os kinds `kc_*`.

Os 3 upgrades abaixo são priorizados por ROI visual / risco. **Upgrade 1 é o de maior impacto
e menor risco** — destrava material que já existe para geometria que já existe.

---

## Upgrade 1 — Veio de PEDRA no tampo + backsplash (e madeira no corpo) via V-Ray tex_map

**Elemento:** `kc_tampo` (→ `ph_kc_tampo`), `kc_backsplash` (→ `ph_kc_backsplash`),
e por tabela: corpo inferior `kc_corpo`/`kc_porta`/`kc_gaveta` (madeira) e `kc_niche_wood` do aéreo.

**Arquivo:** `tools/vray_export.rb` (e, se preciso, uma textura nova em `tools/gen_textures.py`).
NÃO toca `kitchen_layout.py`.

**Mudança mínima:** estender o bloco `if ENV['VRAY_STONE'] == '1'` (linhas 47-50) — ou criar um
bloco `VRAY_KITCHEN == '1'` análogo — adicionando as chaves dos materiais REAIS da cozinha:

```ruby
# dentro do guard existente de pedra/cozinha:
tex_map = tex_map.merge({
  'ph_kc_tampo'      => 'stone_counter.png',   # PEDRA: veio fino sal-e-pimenta (já gerado)
  'ph_kc_backsplash' => 'stone_counter.png',   # backsplash = tampo subindo (mesma pedra)
  'ph_kc_corpo'      => 'wood_medium.png',      # carcaça inferior carvalho/freijó
  'ph_kc_porta'      => 'wood_medium.png',      # portas do gabinete (veio contínuo)
  'ph_kc_gaveta'     => 'wood_medium.png',      # gaveteiro
  'ph_kc_niche_wood' => 'wood_dark.png',        # nicho de assinatura do aéreo (madeira mais escura = contraste)
})
# tile menor no tampo p/ o veio ler na escala da bancada (a pedra atual usa size [40,40] genérico):
sm = model.materials['ph_kc_tampo']; sm.texture.size = [55, 55] if sm && sm.texture
```

Reaproveita o loop `tex_map.each` que já existe (linhas 52-64): ele só aplica `m.texture = path`
em materiais que EXISTEM no modelo, então chaves a mais são inofensivas (o `next unless m` protege).

**Risco:** BAIXO.
- Render-only: line renders (matplotlib/flat) continuam chapados; só o V-Ray muda.
- `stone_counter.png`/`wood_medium.png`/`wood_dark.png` já existem (`gen_textures.py` TEXTURES dict),
  não precisa gerar nada novo no caminho mínimo.
- Geometria intacta: só `material.texture` (mesmo padrão já provado para piso `floor_*` e `ph_bancada`).
- Único cuidado: confirmar o nome EXATO do material no .skp gerado (`ph_kc_tampo`) — derivado de
  `"ph_#{b['kind']}"` com `kind="kc_tampo"`. Se o orquestrador renomear kinds, atualizar as chaves.
- Não regride sofá/parede/quarto (materiais `ph_kc_*` são exclusivos da cozinha; default sem
  o guard continua byte-estável).

**Validação sugerida (orquestrador):** render V-Ray da cozinha com guard ligado → contar
`texturas aplicadas: N` no `vray_export_log.txt` (deve subir ≥ 4) → veredito visual GPT (gate de aparência).

---

## Upgrade 2 — Veio DIRECIONAL na pedra (book-match horizontal), não ruído isotrópico

**Elemento:** a TEXTURA de pedra em si (`stone_counter.png`), que hoje é grão isotrópico +
"veias suaves" de `_value_noise` sem direção (`gen_textures.py:130-138`). Pedra de bancada cara
lê como tendo VEIO CORRENTE (mármore/quartzo veiado), não granito-pontilhado.

**Arquivo:** `tools/gen_textures.py` — função nova `stone_veined(...)` + uma entrada no dict `TEXTURES`.
NÃO toca `kitchen_layout.py` nem `vray_export.rb` (além de apontar a chave do Upgrade 1 para o PNG novo).

**Mudança mínima:** adicionar uma textura com veio direcional (segue o padrão já usado em `wood()`,
que faz `sin((x*rings + warp))` para veio corrido — só que com veias finas, esparsas e de baixo
contraste, em cima da base de pedra existente):

```python
def stone_veined(c_base, seed, veins=2.2):
    """Quartzo/marmore VEIADO: base + grao fino + veias finas CORRENTES (direcao) low-contrast.
    Le como pedra cara (veio book-match), nao granito pontilhado."""
    rng = np.random.default_rng(seed)
    speck = rng.random((SZ, SZ)) - 0.5
    warp = _value_noise(SZ, SZ, 40, rng) * 4.0 + _value_noise(SZ, SZ, 10, rng) * 1.2
    x = np.linspace(0, 1, SZ)[None, :].repeat(SZ, 0)          # veio corre na horizontal (book-match)
    streak = np.sin((x * veins + warp) * np.pi)
    vein = np.clip(np.abs(streak) ** 6, 0, 1)                 # poucas linhas finas (expoente alto = esparso)
    t = speck * 0.06 - vein * 0.16                            # veia ESCURECE de leve (sutil, premium)
    out = np.stack([np.clip(c_base[i] + t * 42, 0, 255) for i in range(3)], -1)
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"))

# em TEXTURES:
"stone_veined.png": lambda: stone_veined((188, 185, 179), 107),  # pedra clara quente veiada
```

Depois, no Upgrade 1, apontar `'ph_kc_tampo' => 'stone_veined.png'` e
`'ph_kc_backsplash' => 'stone_veined.png'` (em vez de `stone_counter.png`).

**Risco:** MÉDIO-BAIXO.
- É textura nova: NÃO substitui `stone_counter.png` (a bancada genérica `ph_bancada`/banho continua
  na pedra antiga → não regride banho). Aditivo.
- Determinístico (seed fixo 107) — `gen_textures.py` roda 2× = mesmo PNG (regra de idempotência).
- Cuidado de TILE: veia direcional exige orientação coerente com a UV do tampo no SU; se o veio
  sair vertical no render, é só transpor o `np.linspace` (eixo `[:, None]` vs `[None, :]`) — ajuste
  de 1 caractere, mas precisa do render para confirmar a direção.
- Custo: precisa rodar `gen_textures.py` para materializar o PNG antes do render (passo do orquestrador).

---

## Upgrade 3 — Assimetria de ASSINATURA no aéreo: nicho aberto + porta-vidro ripada (1 bay)

**Elemento:** `aereo` / `kc_porta_sup` / `kc_niche_wood`. Hoje o aéreo já tem 1 bay de nicho aberto
de madeira (`kitchen_layout.py:183-189`: `niche = (nmod-1)` quando `nmod>=3`). O resto são portas
off-white iguais (`kc_porta_sup`). "Planejado caro" raramente é uma fileira simétrica de portas
idênticas — costuma ter UM volume diferente (vidro canelado, ou painel ripado, ou prateleira aberta)
para quebrar a repetição. O nicho atual já faz parte disso; o upgrade é dar a ESSE bay um material
distinto que o leia como peça de assinatura (vidro/ripado), não só "buraco com fundo de madeira".

**Arquivo:** principal = `tools/vray_export.rb` (material). A geometria do nicho/porta JÁ EXISTE;
só falta diferenciá-lo no mapa de textura. (Opção mais profunda mexeria em `kitchen_layout.py`
para emitir um `kc_porta_vidro` no bay de assinatura — mas isso é EDITAR o brain, **fora do meu
mandato** → fica como nota para o orquestrador decidir, não como minha mudança.)

**Mudança mínima (dentro do meu mandato — só material):** no Upgrade 1, dar ao `kc_niche_wood`
uma madeira escura distinta (`wood_dark.png`) e, se o orquestrador quiser, mapear um leve
metal/vidro no puxador/gola para o bay ler como vitrine:

```ruby
'ph_kc_niche_wood' => 'wood_dark.png',   # nicho = madeira escura (contraste com off-white) -> peça-foco
# (opcional, se quiser leitura de vitrine no bay:)
# 'ph_kc_gola'     => 'metal_black_matte.png',  # gola/sombra fina vira reveal metálico fino
```

**Nota para o orquestrador (fora do meu mandato, NÃO aplico):** o salto real de "assinatura"
seria `_kmod` emitir um `kc_porta_vidro` (porta-vidro canelado/ripada) em UM bay do aéreo —
mudança de geometria/kind no brain, com gate `kitchen_ergonomics`/`furniture_overlap` re-rodado.
Deixo isto sinalizado, não codificado: respeita "NÃO virar U/L" e "layout linear" (é só material/face
de UM módulo já existente, não muda footprint nem posição da pia).

**Risco:** BAIXO (na versão só-material).
- Não muda footprint, posição, nem contagem de módulos → `furniture_overlap_gate`,
  `kitchen_validation`, `geometry_sanity`, `kitchen_ergonomics` continuam PASS (nenhuma medida muda).
- Só recolore 1 papel já existente. Se o bay de nicho não existir (cozinha curta, `nmod<3`),
  a chave `ph_kc_niche_wood` simplesmente não casa material (`next unless m`) — inofensivo.
- A variante geometria (porta-vidro real) é MÉDIO risco e fica explicitamente FORA desta entrega.

---

## Resumo de prioridade (ROI ↓, risco ↑)

| # | Upgrade | Arquivo | Risco | Por quê primeiro |
|---|---------|---------|-------|------------------|
| 1 | Pedra+madeira no tex_map (`ph_kc_*`) | `vray_export.rb` | BAIXO | Destrava material EXISTENTE p/ geometria EXISTENTE; é a raiz do flat |
| 2 | Pedra VEIADA direcional | `gen_textures.py` (+chave no 1) | MÉDIO-BAIXO | Eleva de "granito pontilhado" p/ "quartzo veiado caro"; aditivo |
| 3 | Assinatura no aéreo (nicho madeira escura) | `vray_export.rb` | BAIXO | Quebra a fileira simétrica; só material em bay existente |

**Sequência recomendada para o orquestrador:** aplicar 1 → render V-Ray → veredito GPT.
Se PASS mas "pedra ainda pontilhada", aplicar 2 (gerar PNG + re-apontar chave) → render → GPT.
3 entra junto com 1 (mesmo arquivo, mesmo render). NÃO empilhar os três antes do primeiro veredito
(um de cada vez = sinal limpo de qual upgrade moveu a agulha).

## Garantias de segurança (todas as 3 entregas)

- ZERO edição em `kitchen_layout.py`, `.skp`, `.rb` de geometria. Mudança vive em
  `vray_export.rb` (mapa de material) e `gen_textures.py` (PNG novo aditivo).
- Pia/parede OESTE/porta/medidas: INTOCADAS (nenhuma constante de layout muda).
- Gates não regridem: nenhuma mudança altera footprint/Z/posição → `furniture_overlap_gate`,
  `kitchen_validation`, `geometry_sanity`, `kitchen_ergonomics` ficam PASS por construção.
- Default byte-estável: tudo atrás de guard (`VRAY_STONE`/`VRAY_KITCHEN`); sem o env, render igual.
