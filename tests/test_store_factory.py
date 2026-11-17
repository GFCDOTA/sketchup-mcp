"""store_factory: o evento publicado a partir do bridge carrega a identidade completa do PR (repositorio + numero)."""
from __future__ import annotations

from tools.orchestration.store_factory import bridge_to_store_args


def test_the_published_payload_carries_the_repository_so_a_pr_number_is_never_matched_across_repos():
    args = bridge_to_store_args({"kind": "review", "state": "CHANGES_REQUESTED", "event_id": "review:1001", "pr": 7, "repo": "owner/name", "author": "x", "url": "u"},
                                {"head_sha": "a" * 40, "refs": []})
    assert args["payload"]["repo"] == "owner/name" and args["payload"]["pr"] == 7


def test_an_event_without_a_repository_publishes_none_instead_of_guessing_one():
    args = bridge_to_store_args({"kind": "review", "state": "CHANGES_REQUESTED", "event_id": "review:1001", "pr": 7, "author": "x", "url": "u"},
                                {"head_sha": "a" * 40, "refs": []})
    assert args["payload"]["repo"] is None
