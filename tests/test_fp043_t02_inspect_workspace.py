"""T0.2: planning safe inspection scratch never writes near protected SKPs."""
from pathlib import Path

import pytest

from tools.sketchup.inspect_workspace import plan_inspect_workspace


@pytest.mark.parametrize("source_dir", ["artifacts/planta_74", "fixtures/planta_74", "runs/a/mcp"])
@pytest.mark.parametrize("job", ["cabinet_inspect", "shaker_inspect"])
def test_scratch_always_under_runs_and_does_not_mutate_input(tmp_path, source_dir, job):
    path = tmp_path / source_dir / "source.skp"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake fixture bytes used only to test destination policy")
    planned = plan_inspect_workspace(path, job=job, repo=tmp_path, stamp="fixed_test_001")
    assert planned["job_dir"].is_relative_to(tmp_path / "runs")
    assert planned["copy_skp"].parent == planned["job_dir"]
    assert planned["copy_skp"] != path
    assert planned["execution_authorized"] is False
    assert not planned["job_dir"].exists(), "pure plan must not allocate scratch"
    assert path.read_bytes() == b"fake fixture bytes used only to test destination policy"


@pytest.mark.parametrize("stamp", ["../escape", "/tmp/escape", "", "space text"])
def test_suspicious_stamp_is_blocked(tmp_path, stamp):
    skp = tmp_path / "artifacts/model.skp"
    skp.parent.mkdir(parents=True)
    skp.write_bytes(b"x")
    with pytest.raises(ValueError, match="stamp"):
        plan_inspect_workspace(skp, job="cabinet_inspect", repo=tmp_path, stamp=stamp)


def test_wrong_file_or_job_is_blocked_without_write(tmp_path):
    source = tmp_path / "artifacts/m.skp"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"x")
    with pytest.raises(ValueError, match="unsupported"):
        plan_inspect_workspace(source, job="../../arbitrary", repo=tmp_path, stamp="fixed")
    with pytest.raises(ValueError, match="existing"):
        plan_inspect_workspace(tmp_path / "missing.skp", job="cabinet_inspect", repo=tmp_path, stamp="fixed")
    with pytest.raises(ValueError, match="existing"):
        plan_inspect_workspace(source.with_suffix(".txt"), job="cabinet_inspect", repo=tmp_path, stamp="fixed")
    assert not (tmp_path / "runs").exists()


def test_symlink_outside_runs_is_blocked(tmp_path):
    destination = tmp_path / "outside"
    destination.mkdir()
    source = tmp_path / "artifacts/source.skp"
    source.parent.mkdir()
    source.write_bytes(b"x")
    try:
        (tmp_path / "runs").symlink_to(destination, target_is_directory=True)
    except OSError as exc:   # Windows sem Developer Mode/admin: WinError 1314; o CI (Linux) cobre o caso
        pytest.skip(f"sistema nega symlink: {exc}")
    with pytest.raises(ValueError, match="escaped runs"):
        plan_inspect_workspace(source, job="cabinet_inspect", repo=tmp_path, stamp="fixed_test")


def test_same_source_distinct_jobs_or_run_ids_get_distinct_paths(tmp_path):
    source = tmp_path / "artifacts/source.skp"
    source.parent.mkdir()
    source.write_bytes(b"x")
    a = plan_inspect_workspace(source, job="cabinet_inspect", repo=tmp_path, stamp="fixed001")
    b = plan_inspect_workspace(source, job="shaker_inspect", repo=tmp_path, stamp="fixed001")
    c = plan_inspect_workspace(source, job="cabinet_inspect", repo=tmp_path, stamp="fixed002")
    assert len({a["copy_skp"], b["copy_skp"], c["copy_skp"]}) == 3
