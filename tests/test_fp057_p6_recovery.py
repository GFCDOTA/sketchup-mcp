"""FP-057 P6: o cenario de recuperacao (claim, reinicio, falha de check, efeito unico, board sem duplicata, revisao pendente)."""
from __future__ import annotations

from tools.validation import recovery_proof as rp


def test_recovery_scenario_holds_end_to_end_offline():
    res = rp.run(9001, 9002)
    assert res["ok"], res
    assert res["recovery"] == {"checks_fail": "EDITING", "checks_pending": "CI_PENDING", "checks_pass": "MERGING", "merged": "BOARD_SYNC"}
    assert res["resume_after_restart"] and res["once_second_time_blocked"] and res["pending_review_does_not_block_others"]
