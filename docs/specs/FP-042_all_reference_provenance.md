# FP-042/P6 — cobertura integral dos registros de artefatos e referências

Manifesto `fp042_references.v1.json`: 1060 arquivos de fase P6 com disposição `retain_canonical_location`, derivados do inventário e Git tree `9326521753c6f6893df215273c70b9bd2ab639f2`. Cada entrada inclui path, Git blob SHA, tamanho e agrupamento de pasta.

Este gate é **fail-closed** para: caminho removido, blob alterado, referência P6 não registrada, referência fora de P6 inserida, hash malformado e duplicidade. Rodado em pytest e na esteira de fidelity gates.

### O que isso comprova
Cada arquivo rastreado no escopo continua no mesmo caminho com o mesmo conteúdo de bytes Git. A checklist de cobertura não pula JSONs, relatórios ou arquivos de estudo.

### O que NÃO comprova
Não demonstra que o SKP abre, que materiais renderizam corretamente ou que os arquivos externos ausentes são recuperáveis. A validação visual/humana e o SketchUp real L2 continuam como pendências explícitas; hashes Git também não provam qualidade da documentação. Um novo baseline de hash deve ser intencional e revisado.
