# Análise de referência — ClosetSmart (BIMobject) — CLOSET PLANEJADO MODULAR

> Fonte: `BIMobject-ClosetSmart.zip` (baixado pelo Felipe). `.skp` = "Room 09.skp"
> (closet num quarto-exemplo). Skill `furniture-reference-analyzer`.
> ⚠️ O `furniture_reference_analyzer.py` é calibrado pra SOFÁ → deu "desconhecido" e
> confundiu painéis com encosto. Hipótese CORRETA abaixo (lida do iso/front + dims).

## O que é (confiança ALTA — visual + dims)
**Closet planejado MODULAR ABERTO** (sistema de marcenaria, ferragem **Häfele** real
no .skp). NÃO é guarda-roupa de portas. `single_block=False` (59 definições). É um
**arquétipo NOVO** vs o guarda-roupa-caixa-com-porta atual = "mais variado".

## Dimensões reais (extraídas do .skp, metros)
- **Conjunto (cabinet-1747873): 2.87 L × 1.18 P × 2.35 A** — full-height (chão→teto), planejado.
- **Painéis verticais (divisórias): 0.04 esp × 0.68 P × 2.35 A** — criam as COLUNAS.
- **Prateleiras: 2.87 L × 0.60 P × 0.04 esp** — profundidade padrão de closet = **0.60 m**.
- Módulos de coluna ≈ 0.60–0.90 m.
- Ferragem **Häfele Shoe Rack 0.71 × 0.36 × 2.19** (sapateira deslizante) + gaveteiro.
- Painel de **vidro translúcido cinza** (espelho/porta lateral).

## Anatomia / vocabulário de módulo (o builder deve reproduzir)
Colunas verticais (painel de 4 cm entre elas), cada coluna = pilha de:
- **prateleira de topo** (cestos em cima), **seção de cabide** (vão alto + barra),
- **prateleiras** (0.60 P) e/ou **cestos**, **gaveteiro** (torre de gavetas c/ puxador),
- opcional **painel de espelho/vidro** na ponta.

## Material
No .skp = cores `<auto>` (branco/preto) + vidro. Mas o pacote traz **texturas de madeira
REAIS** em `runs/closetsmart/ClosetSmart/MATERIAL/`: Dark Mahogany, Dark Oak, Golden Oak,
Kings Oak, Mahogany, Granada Maple, Hungary Ash Cognac, Wallis Plum + RAL 9006/9016/9017.
→ biblioteca de acabamento pro render-ready.

## Aprendizado → spec do builder "closet_planejado"
1. **Full-height** (chão→teto ~2.35–2.6 m) = o look "planejado" (vs a caixa baixa solta de hoje).
2. **Profundidade 0.60 m** (prateleira) / 0.68 m (painel) — padrão.
3. Painel 4 cm; prateleira 4 cm.
4. **Composição por COLUNAS** parametrizáveis: cada coluna = stack de {prateleiras | cabide |
   gaveteiro | cestos}. Largura total se adapta à parede.
5. Acabamento por textura de madeira (swap MATERIAL) + ferragem (puxador, barra, sapateira).

## Hard rule (skill)
NÃO importar a geometria do asset pra planta — extrair só dims/anatomia/material; o asset
vira **spec + builder + gate**, não entra no `.skp` da planta.
