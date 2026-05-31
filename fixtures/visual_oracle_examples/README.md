# Visual Oracle Example Pack

This package seeds the `Visual Oracle Gate / SKP Visual Self-Correction Loop`.

It contains:

- `bad_real/`: real screenshots from the planta_74 SKP review, including user-marked issues.
- `bad_synthetic/`: simplified diagrams for common visual-fidelity failure modes.
- `good_synthetic/`: a minimal positive reference.
- `manifest.json`: catalog of examples and expected finding types.

## Important policy

Synthetic images are only teaching aids. Real SKP failures and real canonical fixtures must remain the stronger source of truth.

The goal is not to make a perfect vision model in one PR. The goal is to create a repeatable habit:

```text
Generate SKP -> Generate PNGs -> Review visually -> Write findings -> Fix -> Regenerate -> Compare.
```

Core rule:

```text
The user is not the visual regression detector.
```
