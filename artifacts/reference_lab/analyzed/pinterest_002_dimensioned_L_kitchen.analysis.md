# Reference Analysis — pinterest_002_dimensioned_L_kitchen

> Referência de **DIMENSÃO/ERGONOMIA** (não tema/estética): cozinha em L cotada. Caso-modelo
> da regra de ouro: **medida de Pinterest = HIPÓTESE; PDF + ergonomia + gate validam.**
>
> ⚠️ **LEITURA CORRETA (Felipe):** estas cotas são **boas práticas de ergonomia pra QUALQUER
> cozinha** (guia de melhorias) — **NÃO** são as dimensões da planta_74 e **NÃO** se importam.
> As dimensões/posições da nossa cozinha vêm **SÓ do PDF**. Esta referência serve apenas como
> **conjunto de REGRAS de conferência** (folgas/alturas padrão) — e elas confirmam o nosso
> `kitchen_ergonomics.py`. Nada de medida desta foto vira medida nossa.

## Sidecar
- **Fonte:** print cotado curado pelo Felipe (cozinha em L genérica, madeira clara + tampo escuro)
- **Ambiente:** cozinha em L com torre da geladeira
- **O que é:** uma **planilha de medidas**, não uma paleta — alimenta a camada de USO, não a de pele
- **O que NÃO copiar:** o **layout em L**, as paredes 3.6×2.4m, a posição da pia/janela (isso é a
  POSIÇÃO da planta DELE; a nossa vem do PDF da planta_74, linear e fixa)
- **Status:** vira **validação de ergonomia** (não tema)

## Cotas extraídas (hipóteses) × nossas faixas (`tools/kitchen_ergonomics.py`)
| medida da imagem | valor | nossa faixa ERGO | veredito |
|---|---|---|---|
| sóculo / toe-kick | **10 cm** | 10–15 | ✅ confirma (low end) |
| profundidade base | **55–60 cm** | 55–60 | ✅ confirma exato |
| bancada → aéreo (clearance) | **60 cm** | 50–60 | ✅ confirma (topo) |
| cooktop → coifa | **65 cm** | 45–65 (under-cabinet) | ✅ confirma topo (valida slim) |
| módulo base | **60 cm** | 35–65 | ✅ confirma (~60 comum) |
| zona da pia | **100 cm** | — | ✅ run generoso (área de apoio dos 2 lados) |
| torre / aéreo até teto | **2.7 m** (pé-direito) | — | ✅ casa com "armário até o teto" do Felipe |
| lava-louças | **~55–60 cm** (35 = recuo/abertura) | std 60 | ✅ obrigatório do Felipe presente |
| janela | 1.2 m | — | info (a nossa é do PDF) |

**Conclusão das medidas:** a referência **CONFIRMA quase 1:1 as nossas faixas** — isto é uma
validação externa do `kitchen_ergonomics.py`, não uma medida nova a adotar. Reforça confiança.

## 10 saídas (foco em USO)
1. **Theme extraction:** n/a forte (madeira clara + tampo grafite + inox; não é a direção dark do Felipe).
2. **Form/skin:** FORMA = L + torre da geladeira + coifa chaminé. PELE = madeira clara (fora do gosto).
3. **Dimension hints:** a tabela acima (todas hipóteses, validadas contra ERGO).
4. **Ergonomics notes:** clearance 60, hood 65, base 55–60, toe-kick 10, módulo 60 — todos dentro do nosso padrão. Zona de pia 100cm = boa área de apoio (mirar isso na planta_74).
5. **Maintenance notes:** tampo escuro + inox = combinação durável/segura (alinha com Felipe).
6. **Buildability notes:** medidas 100% padrão de marcenaria — executável, nada de truque.
7. **What to COPY:** os **padrões ergonômicos** (já são os nossos → confiança) + a meta de zona de pia ~100cm + torre/aéreo até o teto.
8. **What to ADAPT:** nada de geometria (a nossa é fixa pelo PDF). Usar as cotas só como conferência.
9. **What to REJECT:** o **layout em L**, as paredes 3.6×2.4m, a pia/janela da foto (POSIÇÃO é do PDF; nossa cozinha é linear). Madeira clara (fora da direção dark).
10. **Theme preset:** n/a — esta referência **não vira tema**; vira **confirmação de gate ergonômico**.

## Veredito dos 4 gates
| gate | veredito | nota |
|---|---|---|
| theme_fit_gate | **REJECT (layout)** | é L; a planta_74 é linear/fixa — não copiar a estrutura |
| ergonomics_gate | **PASS** | todas as cotas batem com as faixas ERGO (validação externa) |
| maintenance_gate | **PASS** | tampo escuro + inox = durável |
| buildability_gate | **PASS** | medidas padrão, executável |

**Resumo:** referência usada do jeito CERTO — a foto não mandou na planta (rejeitamos o L);
as **medidas viraram conferência** e confirmaram o nosso `kitchen_ergonomics.py`. Pinterest deu a
hipótese; PDF + ergonomia validaram. Próximo experimento: medir a **zona de pia da planta_74** vs
os 100cm de apoio da referência (no nosso layout linear).
