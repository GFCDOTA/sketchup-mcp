# Matterport Photo Inventory — Living Grand Wish Jardim 74m²

> Mapping of the 36 photos / video / dollhouse renders observed in the
> public Matterport tour, what each one shows, and which residual SKP
> defect (V1, V2, V4, V5) it helps validate.
>
> **Source:** https://discover.matterport.com/space/rLoqyVDHfzC,
> "Photos and Video" gallery + the dollhouse/FPV scan positions visited
> via Chrome MCP. Photo numbering matches the modal counter (`3 / 36`,
> `5 / 36`, etc.) the viewer shows when a thumbnail is opened.
>
> **Persistence status:** only photo #1 (Living Room) is currently
> committed at `references/matterport_74m2/01_living_room_official.jpg`.
> The rest are described from observation; see
> `docs/tour/matterport_capture_failure_74m2.md` for why and how to
> recover the others.

## Persisted assets

| File | Source | What it shows | Helps validate |
|---|---|---|---|
| `references/matterport_74m2/01_living_room_official.jpg` | CDN file `GFhsm6jpyHB-Living_Room.jpg`, 640×360 JPEG | SALA DE ESTAR — sofá branco em L, painel de mármore com TV ao centro, estante iluminada à direita, porta-balcão envidraçada visível na borda direita, corredor → suíte ao fundo esquerdo. Walls all orthogonal. | **V1 strong** (sala retangular contradiz mordida diagonal do SKP) |

## Observed but not persisted

Numbered by the modal counter when viewed in the browser. Filenames
listed are the CDN basename (matterport CDN paths under
`/apifs/models/rLoqyVDHfzC/images/<scanId>/<filename>`).

| # | CDN basename | Ambient | What it shows | Validates |
|---|---|---|---|---|
| 1 | `GFhsm6jpyHB-Living_Room.jpg` | Living | Curated hero shot of the SALA DE ESTAR (persisted). | V1 |
| 2 | `UdHzUwjCQ6K-Dollhouse_View.jpg` | Whole apartment | Hero dollhouse render: full apartment in 3D with all 27 scan points. Wood-deck terraço visible bottom-left. | V1 + V2 + V4 (overall layout) |
| 3 (video) | `animation-0001-480.jpg` (poster), full clip on viewer | Living + cozinha | 12-second video panning from sofá toward kitchen island. Confirms cozinha is open to living, no door. | V5 (open passages) |
| 4 | `08.23.2023_10.41.03.jpg` | Sala de jantar / terraço | Mesa de jantar formal de 6 cadeiras amarelas, pendentes douradas, **porta-balcão envidraçada com cortina translúcida ao fundo**. Bancada de mármore secundária à direita. | V2 (terraço is glassed, not walled — supports rectangular shape) |
| 5 | `08.23.2023_11.04.56.jpg` | Suíte 02 (infantil) | Cama de criança com almofadas coloridas + papel de parede com plantas/animais. Closet de vidro à esquerda. | (none of V1-V5) |
| 6 | `08.23.2023_10.14.26.jpg` | Suíte 02 — closet | Closet de vidro fumê com araras + acessórios + cadeira de penteadeira. | (none) |
| 7 | `08.23.2023_10.34.12.jpg` | Banheiro 01 | Box de mármore Calacatta + janela alta + cuba e espelho retangular. | (none) |
| 8 | `08.23.2023_11.03.11.jpg` | Suíte 01 | Cama king + papel parede + criados-mudos. | (none) |
| 9 | `08.23.2023_10.08.08.jpg` | Living → cozinha | Vista do sofá com a cozinha (geladeira inox, bancada de madeira) atrás. **Confirma vão aberto sem porta entre living e cozinha.** | **V5** |
| 10 | `08.23.2023_10.31.23.jpg` | Corredor → suítes | Corredor estreito olhando para suíte de casal com cama king ao fundo. | (none) |
| 11 | `08.23.2023_10.35.08.jpg` | Banho 02 | Box + pia da Suíte 02. | (none) |
| 12 | `08.23.2023_10.06.56.jpg` | Hall / entrada | Vista da porta de entrada para o living. | (none) |
| 13 | `08.23.2023_10.10.19.jpg` | Cozinha | Bancada com fogão de 6 bocas, marmoraria, geladeira inox. | (none) |
| 14 | `08.23.2023_10.34.43.jpg` | Suíte 01 | Vista lateral da cama com closet de vidro à direita. | (none) |
| 15-36 | (mix) | 360° pano captures | Walking-mode panoramas at each of the 27 scan positions. Names are timestamps `08.23.2023_<HH.MM.SS>.jpg`. The renderer composites these on demand. | reserve for V2/V5 follow-up |

## Dollhouse / top-down captures observed via Chrome MCP

These came from the tour's interactive view, not the static gallery,
so they don't have a CDN basename.

| Capture | What it shows | Validates |
|---|---|---|
| Dollhouse iso | Apartment in 3D from upper-left isometric. Wood-deck terraço along bottom-left edge with formal dining set on it. | V2 (terraço position + shape) |
| Top-down floorplan (post-Ctrl+drag tilt) | Full apartment from straight above. Rooms recognizable: cozinha (fogão de 6 bocas + bancada), A.S. (faixa estreita à esquerda), living + dining + suítes + banhos. **All walls orthogonal.** | **V1 strong** + **V4 confirmed** |
| FPV at scan ~0 (initial) | Sofá com almofadas (azuis + laranja), painel TV, vista parcial da varanda à direita. | V1 |
| FPV from A.S. corridor | A.S. faixa vertical estreita à esquerda (com tanque + máquinas), cozinha ao centro (geladeira), sala de jantar à direita (cadeiras amarelas), vidros ao fundo. | **V4 confirmed** + V5 (open passages) |
| FPV with "Lavabo" mattertag | Sofá orgânico curvo + estante de mármore + porta-balcão à esquerda com luz natural. | V5 (porta-balcão evidence) |

## Priority viewpoints for next-session capture

In order of evidence value for the remaining open questions:

```
P1 (V2 definitive):    top-down crop apenas no terraço (wood-deck)
P2 (V2 definitive):    FPV de dentro do terraço olhando para o building interior
P3 (V5 enrichment):    FPV do living mostrando porta-balcão aberta para terraço
P4 (V5 enrichment):    FPV da cozinha mostrando vão aberto para living
P5 (background):       FPV do corredor mostrando portas reais das suítes
```

P1 + P2 alone are enough to upgrade V2 from "likely contradicted" to
"definitively contradicted" and unblock the V1+V2 shared fix in
`tools/rooms_from_seeds.py`.
