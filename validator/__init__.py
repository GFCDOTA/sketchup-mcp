"""Planta validator — scores PNGs registered in runs/png_history/manifest.jsonl
against the consensus model, the source .skp inspection report, and the
source PDF baseline. See docs/validator_protocol.md for the contract.
"""
__all__ = ["pipeline", "scorers"]
