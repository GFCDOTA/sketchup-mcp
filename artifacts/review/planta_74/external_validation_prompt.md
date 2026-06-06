# Prompt — revisão externa de fidelidade da planta_74 (mandar pra outras IAs)

> Anexar SEMPRE: `planta_74.pdf` (verdade) + `planta_74_top.png` +
> `planta_74_iso.png` + `side_by_side_pdf_vs_skp.png`.
> Sem o PDF anexado, a revisão é INVÁLIDA (peça o PDF antes).

---

## CONTEXTO
Você é um revisor especialista em arquitetura + visão computacional avaliando a
**fidelidade de um modelo 3D (SketchUp)** gerado automaticamente a partir de uma
**planta baixa em PDF**.

- Unidade: apartamento de **74 m²**, **8 ambientes**: SUÍTE 01, SUÍTE 02,
  SALA DE ESTAR/JANTAR, COZINHA, ÁREA DE SERVIÇO/TERRAÇO, BANHO 01, BANHO 02,
  LAVABO.
- Pipeline: PDF → extração vetorial → `consensus.json` (**19 paredes, 12
  aberturas = 7 portas + 5 janelas, 8 cômodos**) → modelo `.skp` + renders
  (topo + isométrico).

## VERDADE DE REFERÊNCIA (regra dura)
O **PDF da planta é a ÚNICA fonte geométrica autoritativa.** Os renders do `.skp`
são artefatos **derivados** — podem estar errados. **NÃO** trate um render bonito
como prova de correção. Toda validação é **contra o PDF**. Não invente geometria
(porta, parede, janela, cômodo, peitoril) que não esteja visível no PDF.

## O QUE JÁ FOI FEITO / CORRIGIDO (não re-levantar como novo)
- Escala ancorada nas **cotas do PDF** (não no default 1/72").
- **Janelas** = vãos vazados com vidro (não blocos sólidos).
- **Portas** = vãos full-height.
- Correção recente: vidro do **BANHO 2** que faltava.
- Gates determinísticos **verdes**: todas as paredes do consensus presentes no
  render; cada abertura hospedada na parede certa; sem paredes duplicadas.

## O QUE EU PRECISO DE VOCÊ
Compare o modelo (renders) **contra o PDF** e me dê achados **acionáveis**,
**priorizados** por severidade — **CRÍTICO / IMPORTANTE / POLIMENTO** — em duas
frentes:

### A) VALIDAR — o que pode estar ERRADO vs o PDF
- **Paredes**: faltando, sobrando, posição/espessura errada, invadindo cômodo?
- **Portas**: local, parede certa, largura, **sentido de abertura (swing)**?
  Alguma porta virou parede fechada, ou parede virou vão?
- **Janelas**: posição, largura, peitoril; alguma inventada ou faltando?
- **Cômodos**: ambiente faltando, falso, fundido, polígono/sliver errado?
- **Escala / rotação / alinhamento** global vs as cotas do PDF.
- **Alucinação**: algo no modelo que NÃO existe no PDF (ou o inverso).

### B) MELHORAR — fidelidade, legibilidade e como travar cada erro
- O que tornaria o modelo mais **fiel e legível** vs a planta?
- Para cada classe de erro acima, **que checagem DETERMINÍSTICA** (mensurável,
  sem olho humano) você criaria pra travá-la? Ex.: "para cada abertura, projetar
  o centro no render de topo e verificar X". (Isto é ouro pra nós — viramos seu
  achado em gate automático.)
- Top 3 prioridades pro próximo ciclo.

## FORMATO DA RESPOSTA (por achado)
- **[SEVERIDADE]** ambiente/elemento + localização (ex.: "porta do BANHO 02,
  parede norte")
- **PDF mostra** X **vs modelo mostra** Y
- **Evidência**: qual região da imagem olhar
- **Correção proposta** + **como validar** que foi corrigido (de preferência um
  teste determinístico)

Seja **específico e cético**. Se parece certo mas você não consegue confirmar
contra o PDF, marque **"INCONCLUSIVO — precisa de [o quê]"**. Prefira **5
problemas reais e verificáveis** a 20 genéricos. Não rebaixe a régua pra dar
"parece ok".
