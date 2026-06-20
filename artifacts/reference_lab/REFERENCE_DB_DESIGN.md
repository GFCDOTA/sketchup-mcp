# Reference DB — design concreto (banco de referências indexado, consultável por tema)

> **Pedido do Felipe (transcrito):** *"um banco de dados rodando em Docker com as
> imagens de referência + tudo que preciso quando vou VALIDAR; não deixar imagem
> em pasta solta (custoso varrer todas); SEPARAR POR TEMA (industrial/clean/etc.);
> uma TABELA com COLUNAS indicando o tipo (tema, estilo, cômodo...) — porque ler a
> tabela é mais barato que abrir cada imagem; deixar o sistema mais inteligente."*
>
> **Objetivo deste doc:** dar o esquema da tabela + a stack recomendada + o fluxo de
> ingestão/consulta + o plano de microtarefas. **Não duplica** o que já existe em
> `reference_lab/` (cards, tokens, themes, gates) — **indexa** isso numa tabela única
> consultável, e formaliza onde a imagem curada de verdade vive.

---

## 0. O que JÁ existe (auditado, não reinventar)

| artefato existente | o que é | papel no DB |
|---|---|---|
| `kitchen/cards/*.json` (17 cards) + `card_schema.json` | regra procedural (FORMA×PELE), campo `category` enum | **vira linha** (kind=`card`) |
| `references/tokens/*.json` (9 tokens canônicos) | parâmetro reusável (rgb/dims/brdf) | **vira linha** (kind=`token`) |
| `themes/*.json` (4 presets) + `kitchen*/THEME_*.json` | preset material+luz, c/ veredito por gate | **vira linha** (kind=`theme_preset`) |
| `analyzed/*.analysis.md` (3 sidecars) | as 10 saídas + tabela 4 gates de UMA referência curada | **vira linha** (kind=`reference_image`), o `.md` é o sidecar |
| `kitchen_angles/*.png` (~50 PNGs gerados) | renders A/B/C, heros, montagens | **vira linha** (kind=`render`) — É AQUI a "pasta solta" real |
| `assets/textures/procedural/candidates/*.png` | candidatos de pedra/piso/textura | **vira linha** (kind=`texture_candidate`) |

> ⚠️ **Achado de auditoria:** `inbox/` e `analyzed/` **não têm imagem física** hoje —
> só os sidecars `.md` que descrevem prints que o Felipe curou e descartou. A "pasta
> solta" que dói de verdade é `kitchen_angles/` (50+ PNGs sem metadado: impossível
> saber qual é tema B vs hero final vs montagem sem abrir cada um). O DB resolve
> exatamente isso: a tabela responde "me dá o hero PASS do black_wood_gold" sem abrir 50 imagens.

**Regra de não-duplicação:** o DB guarda **metadado + ponteiro de caminho**, nunca o
conteúdo. O `.json`/`.png`/`.md` continua sendo a fonte; a linha é o índice. Reingestão
é idempotente por `sha256`.

---

## 1. Esquema da TABELA (uma tabela `reference` + tags)

Tabela única `reference` (linha = qualquer artefato consultável: imagem curada, render,
card, token, theme, textura). Colunas escolhidas para o caso REAL (validar cozinha,
separar por tema, ler tabela em vez de abrir imagem):

| coluna | tipo | obrigatória | exemplo | por quê |
|---|---|---|---|---|
| `id` | INTEGER PK | sim | `42` | chave estável |
| `slug` | TEXT UNIQUE | sim | `cozinha_skp_blackgold_hero_final` | nome legível, casável com filename |
| `kind` | TEXT (enum) | sim | `render` | `reference_image`/`render`/`card`/`token`/`theme_preset`/`texture_candidate` |
| `path` | TEXT | sim | `artifacts/.../kitchen_angles/cozinha_skp_blackgold_hero_final.png` | **relativo à raiz do repo** (portável entre máquinas) |
| `room` | TEXT (enum) | sim | `kitchen` | `kitchen`/`living_room`/`bedroom`/`bathroom`/`service`/`whole_apt` |
| `theme` | TEXT (enum, nullable) | não | `black_wood_gold` | **a coluna de SEPARAÇÃO pedida** — `industrial_boutique`/`warm_compact`/`dark_walnut`/`hotel_boutique`/`black_wood_gold`/`clean`/`null` |
| `style` | TEXT (nullable) | não | `industrial_boutique_premium` | estilo de alto nível (free-text controlado); `theme` é o preset concreto, `style` é a família |
| `sub_element` | TEXT (enum, nullable) | não | `hero_render` | **o que a imagem mostra**: `backsplash`/`floor`/`sink`/`countertop`/`fridge_tower`/`hood`/`upper_cabinet`/`base_cabinet`/`lighting`/`hero_render`/`elevation`/`montage`/`detail`/`full_room` |
| `category` | TEXT (enum, nullable) | não | `material_token` | **a trava FORMA×PELE** já existente nos cards: `joinery_form_token`/`material_token`/`lighting_token`/`camera_token`/`safety_gate` |
| `intent` | TEXT | sim | `"hero final aprovado: preto fosco + pedra dark-gold sutil + madeira quente"` | **"o que esta imagem ENSINA"** — o campo que substitui abrir a imagem |
| `tags` | (tabela N:N) | não | `["dark","gold_vein","matte_black","led_2700k"]` | busca livre multi-valor (ver §1.1) |
| `source` | TEXT (nullable) | não | `golden_sample` / `felipe_curated` / `generated_vray` / `pinterest` | proveniência |
| `source_url` | TEXT (nullable) | não | `https://...` | URL original quando curada de Pinterest (sidecar) |
| `sha256` | TEXT (nullable) | não | `9f2c...` | dedup/idempotência de ingestão (null p/ card/token = usa `path`) |
| `curation_status` | TEXT (enum) | sim | `golden` | `inbox`/`analyzed`/`candidate`/`approved`/`golden`/`rejected`/`superseded` |
| `gate_verdicts` | TEXT (JSON, nullable) | não | `{"theme_fit":"PASS","maintenance":"WARN"}` | veredito dos 4 gates (copiado do theme/analysis p/ filtrar "só PASS") |
| `linked_skp` | TEXT (nullable) | não | `artifacts/.../planta_74_furnished_black_wood_gold.skp` | render→.skp de origem |
| `sidecar` | TEXT (nullable) | não | `analyzed/pinterest_001_dark_walnut.analysis.md` | o `.md`/`.json` que detalha (10 saídas, real_values) |
| `notes` | TEXT (nullable) | não | livre | observação humana |
| `created_at` | TEXT (ISO) | sim | `2026-06-20` | ordenação temporal |

### 1.1 Tabela de tags (N:N — busca livre sem explodir colunas)
```
tag(id PK, name TEXT UNIQUE)
reference_tag(reference_id FK, tag_id FK, PRIMARY KEY(reference_id, tag_id))
```
Tags são o escape-hatch: vocabulário aberto, mas **controlado por uma lista-semente**
(`dark`, `warm`, `matte_black`, `gold_vein`, `wood_accent`, `led_2700k`, `inox_dark`,
`black_sink`, `compact`, `cave_risk`, `daylight_reflection`…) pra não virar lixo. Coluna
estruturada (`theme`/`room`/`sub_element`/`category`) é a busca barata; tag é o refinamento.

> **Por que UMA tabela e não cinco:** 1 usuário, validação local, volume baixo
> (centenas de linhas, não milhões). Uma tabela `reference` + `kind` discriminador =
> uma query responde tudo. Normalizar em tabelas por tipo (over-engineering) só
> adicionaria JOINs sem ganho. KISS.

---

## 2. Stack: **SQLite** (recomendado), NÃO Postgres-em-Docker

| critério | SQLite | Postgres em Docker |
|---|---|---|
| nº de usuários | 1 (Felipe) ✅ | feito p/ N conexões — desperdício |
| processo extra | nenhum (arquivo `.db`) ✅ | precisa `docker compose up`, daemon vivo |
| versionável no git | sim — `reference.db` (binário pequeno) ou dump `.sql` ✅ | não (volume Docker fora do git) |
| portabilidade | abre em qualquer máquina/Python stdlib ✅ | depende de Docker instalado + container subido |
| reconstruir do zero | `python tools/reference_db.py rebuild` varre `reference_lab/` ✅ | idem, mas com infra acima |
| consulta pelo agente | `sqlite3` na stdlib do Python — zero deps ✅ | precisa driver `psycopg`, conexão TCP |
| custo de manutenção | ~zero ✅ | cuidar de container, porta, volume, backup |

**Recomendação: SQLite, 1 arquivo `reference.db` em `artifacts/reference_lab/`.**
O caso é exatamente o sweet-spot do SQLite (single-writer, leitura local, embarcado).
Postgres-em-Docker só se justificaria com múltiplos escritores concorrentes ou acesso
em rede — não é o caso e seria a `false-economy` invertida (cerimônia de infra sem ROI).
Ver Hard Rules de right-sizing na MEMORY.

> **Verdade de fonte:** a fonte continua sendo os arquivos `reference_lab/` (cards/
> tokens/themes/analyzed) + os PNGs. O `.db` é um **índice derivado e reconstruível** —
> se corromper, `rebuild` regenera. Por isso pode-se até NÃO commitar o `.db` e commitar
> só um dump `.sql` legível no diff (decisão de microtarefa M6).

### 2.1 Se o Felipe insistir em Docker (opção B, documentada mas não recomendada)
`docker-compose.yml` mínimo (Postgres 16) + script de ingestão idêntico trocando o
driver. Guardado em apêndice (§7) pra não bloquear, mas **default = SQLite**.

---

## 3. Fluxo de INGESTÃO (Felipe cura → entra na tabela)

```
1. Felipe larga print curado em  reference_lab/inbox/<slug>.png   (+ opcional <slug>.url.txt)
2. Agente analisa → analyzed/<slug>.analysis.md  (10 saídas + 4 gates) — pipeline JÁ existe
3. `python tools/reference_db.py ingest`  varre reference_lab/ + assets/textures + kitchen_angles
   → para cada arquivo novo/alterado (sha256), cria/atualiza UMA linha:
     - .analysis.md  → kind=reference_image, lê front-matter (theme/sub_element/tags/intent)
     - cards/*.json  → kind=card,  copia category/applies_to/problem→intent
     - tokens/*.json → kind=token, copia params→intent
     - themes/*.json → kind=theme_preset, copia gates→gate_verdicts, status→curation_status
     - kitchen_angles/*.png → kind=render, infere theme/sub_element do filename (regras §3.1)
     - assets/textures/.../candidates/*.png → kind=texture_candidate
4. Idempotente: mesmo sha256 = update, não duplica. Arquivo sumiu = marca curation_status='superseded'.
```

### 3.1 Metadado da imagem — front-matter YAML no sidecar (fonte do `intent`/`theme`/`tags`)
A imagem PNG não carrega metadado. A verdade vive num **sidecar**: para referência curada
é o `analyzed/<slug>.analysis.md` (ganha um bloco front-matter YAML no topo); para render
gerado, o ingestor infere do filename + um `kitchen_angles/INDEX.yml` opcional editável.
Bloco mínimo a adicionar no topo dos `.analysis.md`:
```yaml
---
slug: pinterest_001_dark_walnut
kind: reference_image
room: kitchen
theme: dark_walnut
style: dark_moody_premium
sub_element: full_room
tags: [dark, walnut, matte_black, led_moody]
intent: "nogueira contínua + preto fosco; ensina materialidade quente escura sem virar caverna"
source: pinterest
source_url: ""
curation_status: analyzed
---
```
> Isto é a peça que torna "ler a tabela mais barato que abrir a imagem" — o `intent` +
> `theme` + `sub_element` respondem 90% das consultas sem decodificar 1 pixel.

---

## 4. Fluxo de CONSULTA (eu, ao validar, leio metadado + 1-2 imagens)

A skill de validação (`reference-to-joinery-translator` / `gpt-review-gate`) deixa de
varrer `kitchen_angles/` e passa a consultar a tabela. CLI helper:

```bash
# "o que tenho de referência de backsplash escuro pra cozinha, só o que passou nos gates"
python tools/reference_db.py query --room kitchen --sub-element backsplash \
    --theme black_wood_gold --gate-pass theme_fit
# → devolve LINHAS (slug, path, intent, gate_verdicts) — 2 linhas, não 50 imagens

# "me dá o hero golden aprovado do tema escolhido"
python tools/reference_db.py query --kind render --curation golden --theme black_wood_gold
# → 1 path. Aí (e só aí) eu abro essa 1 imagem.

# busca por tag
python tools/reference_db.py query --tag gold_vein --tag compact
```
Saída default = **tabela texto** (slug | kind | theme | sub_element | intent | path | gates).
Flag `--json` p/ consumo por agente; `--paths` p/ só os caminhos (alimenta o Read tool).

**Ganho concreto de token:** hoje validar "qual o melhor backsplash dark" = abrir N PNGs
(custo de visão alto). Com o DB = 1 query → leio 2 linhas de `intent` → abro no máximo a
1 imagem que importa. É exatamente o "ler a tabela é mais barato" do Felipe.

---

## 5. Como plugga no loop atual

```
   Felipe cura imagem ─┐
                       ▼
   inbox/<slug>.png ─► [translator skill] ─► analyzed/<slug>.analysis.md (front-matter)
                                                     │
   cards/ tokens/ themes/ (já existem) ──────────────┤
   kitchen_angles/*.png (renders gerados) ───────────┤
   assets/textures/candidates/*.png ─────────────────┤
                                                     ▼
                                   `reference_db.py ingest`  →  reference.db (índice)
                                                     ▲                    │
                          agente de validação ───────┘  query  ◄─────────┘
                          (gpt-review-gate / reference-to-joinery-translator)
```
- **Ponto de plug 1 (ingestão):** o passo 3 do ciclo de 6 (COMPILAR) ganha um sub-passo
  "ingest" — quando um card/token/theme é criado, roda `ingest` (ou hook). Zero trabalho
  manual: é varredura.
- **Ponto de plug 2 (consulta):** a skill de validação, antes de pedir veredito visual,
  faz `query` por `room`+`sub_element`+`theme` e injeta os `intent` + 1-2 paths no
  contexto. O HOW_TO_USE §"OUTPUT PADRÃO" passa a citar a query, não a pasta.
- **Não muda a hierarquia:** `PDF=posição · gates=segurança · referência=linguagem ·
  Felipe=PASS` continua intacta. O DB só torna a camada "referência" consultável.

---

## 6. Plano de implementação em MICROTAREFAS

Cada uma é pequena, uma intenção, acionável. M1 é o esqueleto mínimo útil (entrega valor
sozinha: já responde queries sobre o que existe hoje).

| # | microtarefa | entrega | toca geometria? |
|---|---|---|---|
| **M1** | **Esqueleto mínimo:** `tools/reference_db.py` com `init` (cria schema §1) + `ingest` SÓ de `cards/` e `tokens/` e `themes/` (JSON já estruturado, sem inferência) + `query` texto. Roda e responde "me lista os theme_preset golden". | `reference.db` + CLI que já consulta os 30 artefatos JSON existentes | não |
| **M2** | Ingestão de `analyzed/*.analysis.md`: adicionar front-matter YAML §3.1 nos 3 sidecars existentes + parser. | referências curadas viram linha | não |
| **M3** | Ingestão de `kitchen_angles/*.png` (kind=render) + `assets/textures/candidates/*.png` (texture_candidate): regras de inferência §3.1 (filename→theme/sub_element) + `kitchen_angles/INDEX.yml` editável p/ overrides. Mata a "pasta solta". | 50+ PNGs indexados, consultáveis por tema | não |
| **M4** | Tabela `tag` + `reference_tag` + flags `--tag`. Semear vocabulário de tags da lista §1.1. | busca livre multi-valor | não |
| **M5** | `--gate-pass`/`--gate` (filtra por `gate_verdicts`) + `--json`/`--paths`. Plugar no `gpt-review-gate` (consulta antes do veredito). | consulta filtra por PASS; agente consome | não |
| **M6** | Decisão de versionamento: `rebuild` determinístico + dump `.sql` legível em `reference_lab/reference.db.sql` (commitável, diffável) OU `.db` no `.gitignore`. Doc no README. | reprodutível + revisável no git | não |
| **M7** | (opcional) `validate`: checa linhas órfãs (path inexistente), sidecar sem front-matter, theme fora do enum. Gate de higiene do índice. | índice consistente | não |

> **Nenhuma microtarefa toca a geometria congelada** (GOLDEN_SAMPLE_004 / DECISION 004) —
> é puramente índice/metadado. `touches_frozen_geometry=false` em todas.

### Sequência recomendada
M1 (esqueleto, valor imediato) → M3 (mata a pasta solta, maior dor) → M5 (plug no loop) →
M2/M4 (enriquece) → M6/M7 (higiene). M1+M3+M5 já entregam o pedido central do Felipe.

---

## 7. Apêndice — opção Docker/Postgres (NÃO default, só se exigido)

`reference_lab/docker-compose.yml`:
```yaml
services:
  refdb:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: reference
      POSTGRES_USER: ref
      POSTGRES_PASSWORD: ref_local_only   # local-only, NÃO é segredo de produção
    ports: ["55432:5432"]
    volumes: ["./_pgdata:/var/lib/postgresql/data"]   # _pgdata no .gitignore
```
Popular: `docker compose up -d` → `python tools/reference_db.py --backend postgres ingest`.
Mesmo schema (§1), mesmo CLI; troca só a connection string. **Tradeoff:** ganha nada para
1 usuário local e adiciona um daemon a manter vivo. Documentado pra não travar, mas a
recomendação técnica é SQLite.

---

## 8. Pontas soltas honestas (o que este design NÃO resolve)
- **`intent`/`tags` de render gerado dependem de inferência por filename** — frágil se os
  nomes forem inconsistentes (`cozinha_skp_blackgold_hero_final` vs `cozinha_vray_hero`).
  Mitigação: `INDEX.yml` de override (M3). Não é automático-perfeito.
- **Imagem curada de Pinterest hoje não tem arquivo físico** (só sidecar `.md`) — o DB
  vai indexar o sidecar, mas se o Felipe quiser a imagem-fonte no banco, precisa SALVAR o
  PNG em `inbox/` (mudança de hábito, não de código).
- **O `.db` binário versionado polui o diff** — por isso M6 oferece dump `.sql`. Decisão
  do Felipe.
- Isto é um **índice de referência**, não um motor de busca por similaridade visual (sem
  embeddings/CLIP). Se um dia quiser "ache imagens parecidas com esta", é outra fase — não
  pré-construir (regra event-driven da MEMORY).
