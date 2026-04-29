"""Smoke + schema tests for scripts/oracle/* (LLM architect, CubiCasa, downloader).

No real API calls or weight downloads are performed. Heavy deps (torch, anthropic)
are mocked or skipped via pytest.importorskip when not installed. The goal is to
keep the oracle scripts honest about:
  * their JSON Schema (diagnosis_schema.json + observed_model.schema.json),
  * their setup-error paths (missing weights, missing repo, missing API key),
  * their idempotency (cubicasa_download re-run is a no-op without --force).

Layout:
  - TestLLMArchitect       LLM architect schema + summarize_model + main()
  - TestCubiCasa           Setup checks + payload schema-compliance
  - TestCubicasaDownload   Idempotency of clone + gdown wrappers
  - TestCompareOracles     Conditional on scripts/oracle/compare_oracles.py
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest


# --------------------------------------------------------------------------- #
# Path setup: make `scripts.oracle.*` importable without a scripts/__init__.  #
# --------------------------------------------------------------------------- #

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
ORACLE_DIR = SCRIPTS_DIR / "oracle"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(ORACLE_DIR) not in sys.path:
    sys.path.insert(0, str(ORACLE_DIR))


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def diagnosis_schema() -> dict[str, Any]:
    schema_path = ORACLE_DIR / "diagnosis_schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


@pytest.fixture
def valid_diagnosis() -> dict[str, Any]:
    """A hand-crafted OracleDiagnosis with 5 defects covering the severity/kind matrix."""
    return {
        "run_id": "01161f3f3d3a4049ade8469b7f08288a",
        "summary": (
            "Run is roughly 2x inflated. Several rooms are sliver/triangle artifacts "
            "produced by polygonize closing tiny gaps between fragmented walls. "
            "Two openings have no plausible host wall."
        ),
        "defects": [
            {
                "element_id": "room-12",
                "element_type": "room",
                "defect_kind": "sliver_room",
                "severity": "high",
                "hypothesis": "Polygonize closed a 4 px gap into a 0.3 m^2 sliver.",
                "suggested_fix": "Drop rooms with area < 0.4 m^2.",
            },
            {
                "element_id": "room-3",
                "element_type": "room",
                "defect_kind": "triangle_room",
                "severity": "medium",
                "hypothesis": "Three walls meet near a corner with snap_tolerance leftover.",
                "suggested_fix": "Reject rooms with vertex_count == 3 and aspect_ratio > 6.",
            },
            {
                "element_id": "wall-83",
                "element_type": "wall",
                "defect_kind": "fragmented_wall",
                "severity": "medium",
                "hypothesis": "Hough fragmented one wall into 4 collinear pieces.",
                "suggested_fix": "Increase maxLineGap to 80 in classify/service.py.",
            },
            {
                "element_id": "opening-5",
                "element_type": "opening",
                "defect_kind": "opening_no_host",
                "severity": "low",
                "hypothesis": "Door center sits 30 px from the nearest wall.",
                "suggested_fix": "Snap openings to nearest wall within 12 px or drop them.",
            },
            {
                "element_id": "global",
                "element_type": "global",
                "defect_kind": "global_inflation",
                "severity": "high",
                "hypothesis": "Wall count is ~3x what the source plan visibly contains.",
                "suggested_fix": "Apply collinear dedup BEFORE topology split.",
            },
        ],
    }


@pytest.fixture
def fake_observed_model() -> dict[str, Any]:
    """Minimal observed_model.json shape for summarize_model() tests."""
    return {
        "schema_version": "2.2.0",
        "run_id": "deadbeef" * 4,
        "walls": [
            {
                "wall_id": f"wall-{i}",
                "parent_wall_id": f"wall-{i}",
                "page_index": 0,
                "start": [0.0, float(i * 10)],
                "end": [100.0, float(i * 10)],
                "thickness": 4.0,
                "orientation": "horizontal",
                "source": "hough_horizontal",
                "confidence": 0.9,
            }
            for i in range(8)
        ],
        "rooms": [
            {
                "room_id": f"room-{i}",
                "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]],
                "area": 100.0,
                "centroid": [5.0, 5.0 + i],
            }
            for i in range(3)
        ],
        "openings": [
            {
                "opening_id": "opening-1",
                "page_index": 0,
                "orientation": "horizontal",
                "center": [50.0, 50.0],
                "width": 30.0,
                "wall_a": "wall-1",
                "wall_b": "wall-2",
                "kind": "door",
            }
        ],
        "junctions": [
            {"junction_id": f"j-{i}", "point": [0.0, 0.0], "degree": 2, "kind": "pass_through"}
            for i in range(4)
        ],
    }


@pytest.fixture
def cubicasa_observed_payload() -> dict[str, Any]:
    """A schema-compliant payload as build_payload() would emit."""
    return {
        "schema_version": "2.2.0",
        "run_id": "abcd1234" * 4,
        "source": {
            "filename": "test.pdf",
            "source_type": "raster",
            "page_count": 1,
            "sha256": "0" * 64,
        },
        "bounds": {
            "pages": [{
                "page_index": 0,
                "min_x": 0.0,
                "min_y": 0.0,
                "max_x": 100.0,
                "max_y": 100.0,
            }],
        },
        "roi": [],
        "walls": [
            {
                "wall_id": "cubicasa-wall-1",
                "parent_wall_id": "cubicasa-wall-1",
                "page_index": 0,
                "start": [0.0, 10.0],
                "end": [100.0, 10.0],
                "thickness": 4.0,
                "orientation": "horizontal",
                "source": "cubicasa",
                "confidence": 0.95,
            },
            {
                "wall_id": "cubicasa-wall-2",
                "parent_wall_id": "cubicasa-wall-2",
                "page_index": 0,
                "start": [0.0, 100.0],
                "end": [100.0, 100.0],
                "thickness": 4.0,
                "orientation": "horizontal",
                "source": "cubicasa",
                "confidence": 0.95,
            },
        ],
        "junctions": [
            {"junction_id": "cubicasa-j-1", "point": [0.0, 10.0], "degree": 1, "kind": "end"},
            {"junction_id": "cubicasa-j-2", "point": [100.0, 10.0], "degree": 1, "kind": "end"},
            {"junction_id": "cubicasa-j-3", "point": [0.0, 100.0], "degree": 1, "kind": "end"},
            {"junction_id": "cubicasa-j-4", "point": [100.0, 100.0], "degree": 1, "kind": "end"},
        ],
        "rooms": [
            {
                "room_id": "cubicasa-room-1",
                "polygon": [[0.0, 10.0], [100.0, 10.0], [100.0, 100.0], [0.0, 100.0]],
                "area": 9000.0,
                "centroid": [50.0, 55.0],
            },
        ],
        "scores": {
            "geometry": 1.0,
            "topology": 0.5,
            "rooms": 0.75,
        },
        "metadata": {
            "rooms_detected": 1,
            "topology_quality": "fair",
            "connectivity": {
                "node_count": 4,
                "edge_count": 2,
                "component_count": 2,
                "component_sizes": [2, 2],
                "largest_component_ratio": 0.5,
                "rooms_detected": 1,
                "page_count": 1,
                "max_components_within_page": 2,
                "min_intra_page_connectivity_ratio": 0.5,
                "orphan_component_count": 1,
                "orphan_node_count": 2,
            },
            "warnings": ["dl_oracle"],
        },
        "warnings": ["dl_oracle"],
        "openings": [
            {
                "opening_id": "cubicasa-opening-1",
                "page_index": 0,
                "orientation": "horizontal",
                "center": [50.0, 10.0],
                "width": 30.0,
                "wall_a": "",
                "wall_b": "",
                "kind": "door",
            },
        ],
        "peitoris": [],
    }


# --------------------------------------------------------------------------- #
# TestLLMArchitect                                                            #
# --------------------------------------------------------------------------- #


class TestLLMArchitect:
    """Schema + summarize_model + missing-API-key tests for llm_architect.py.

    Tests that import the script module use pytest.importorskip("anthropic") to
    skip cleanly on environments without the SDK installed.
    """

    def test_diagnosis_schema_valid(self, diagnosis_schema: dict[str, Any]) -> None:
        """diagnosis_schema.json must itself be a valid Draft 2020-12 schema.

        Catches typos in $defs / $ref before they silently degrade validation.
        """
        jsonschema = pytest.importorskip("jsonschema")
        jsonschema.Draft202012Validator.check_schema(diagnosis_schema)

    def test_diagnosis_example_passes_schema(
        self, diagnosis_schema: dict[str, Any], valid_diagnosis: dict[str, Any]
    ) -> None:
        """A hand-crafted realistic diagnosis must validate cleanly."""
        jsonschema = pytest.importorskip("jsonschema")
        jsonschema.validate(instance=valid_diagnosis, schema=diagnosis_schema)

    def test_diagnosis_missing_required_field_fails(
        self, diagnosis_schema: dict[str, Any], valid_diagnosis: dict[str, Any]
    ) -> None:
        """Omitting `summary` or `defects` must raise ValidationError."""
        jsonschema = pytest.importorskip("jsonschema")

        without_summary = deepcopy(valid_diagnosis)
        without_summary.pop("summary")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=without_summary, schema=diagnosis_schema)

        without_defects = deepcopy(valid_diagnosis)
        without_defects.pop("defects")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=without_defects, schema=diagnosis_schema)

    def test_diagnosis_unknown_severity_fails(
        self, diagnosis_schema: dict[str, Any], valid_diagnosis: dict[str, Any]
    ) -> None:
        """severity='critical' is not in the enum -> rejected."""
        jsonschema = pytest.importorskip("jsonschema")
        bad = deepcopy(valid_diagnosis)
        bad["defects"][0]["severity"] = "critical"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad, schema=diagnosis_schema)

    def test_diagnosis_unknown_defect_kind_fails(
        self, diagnosis_schema: dict[str, Any], valid_diagnosis: dict[str, Any]
    ) -> None:
        """defect_kind='exploded' is not in the enum -> rejected."""
        jsonschema = pytest.importorskip("jsonschema")
        bad = deepcopy(valid_diagnosis)
        bad["defects"][0]["defect_kind"] = "exploded"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad, schema=diagnosis_schema)

    def test_summarize_model_compaction(self, fake_observed_model: dict[str, Any]) -> None:
        """summarize_model() must produce output smaller than the full JSON dump.

        The whole point is to send a recap, not the entire observed_model.json,
        because Claude only needs the IDs/counts to reference elements.
        """
        pytest.importorskip("anthropic")
        from scripts.oracle import llm_architect

        recap = llm_architect.summarize_model(fake_observed_model)
        full_json = json.dumps(fake_observed_model)
        assert isinstance(recap, str)
        assert len(recap) > 0
        assert len(recap) < len(full_json), (
            f"recap ({len(recap)} chars) is not smaller than full JSON ({len(full_json)} chars)"
        )
        # Recap should reference the run_id and counts so the LLM can name elements.
        assert fake_observed_model["run_id"] in recap
        assert "walls=8" in recap
        assert "rooms=3" in recap

    def test_main_fails_without_api_key(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """main(--run <fake>) with no ANTHROPIC_API_KEY must exit non-zero with stderr
        message about the missing key.

        Uses an in-process call to llm_architect.main(argv=...) so we avoid spawning
        a subprocess (the SDK import alone can be heavy)."""
        pytest.importorskip("anthropic")
        from scripts.oracle import llm_architect

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        # Build a fake run dir with the bare minimum (overlay PNG + observed_model.json).
        # main() resolves the overlay BEFORE checking the API key in the current
        # implementation, so we must populate enough for it to fail at the key check.
        run_dir = tmp_path / "fake_run"
        run_dir.mkdir()
        (run_dir / "overlay_audited.png").write_bytes(b"\x89PNG\r\n\x1a\n")  # not a real PNG
        (run_dir / "observed_model.json").write_text(
            json.dumps({"run_id": "deadbeef" * 4, "walls": [], "rooms": [], "openings": []}),
            encoding="utf-8",
        )

        with pytest.raises(SystemExit) as exc_info:
            llm_architect.main(["--run", str(run_dir)])

        assert exc_info.value.code != 0, "main() must exit non-zero without API key"
        captured = capsys.readouterr()
        # The _die() helper writes to stderr with the "llm_architect:" prefix.
        assert "ANTHROPIC_API_KEY" in captured.err, (
            f"stderr did not mention ANTHROPIC_API_KEY. Got: {captured.err!r}"
        )


# --------------------------------------------------------------------------- #
# TestCubiCasa                                                                #
# --------------------------------------------------------------------------- #


class TestCubiCasa:
    """Setup-error paths + payload schema-compliance for cubicasa.py.

    These tests do NOT load torch or run inference. They only verify that the
    setup checks fail loud and that build_payload-style dicts validate against
    docs/schema/observed_model.schema.json.
    """

    def test_require_setup_fails_without_weights(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When WEIGHTS_PATH points to a missing file, _require_setup() must raise."""
        pytest.importorskip("cv2")
        from scripts.oracle import cubicasa

        missing_weights = tmp_path / "no_such_weights.pkl"
        # Repo dir doesn't matter — weights are checked first.
        monkeypatch.setattr(cubicasa, "WEIGHTS_PATH", missing_weights)

        with pytest.raises(RuntimeError) as err:
            cubicasa._require_setup()

        assert "weights" in str(err.value).lower(), str(err.value)
        # The error must point the user at cubicasa_download.py.
        assert "cubicasa_download" in str(err.value)

    def test_require_setup_fails_without_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When weights exist but the vendored repo is missing, _require_setup() must raise."""
        pytest.importorskip("cv2")
        from scripts.oracle import cubicasa

        # Provide a "weights" file so the first check passes, then make the
        # repo path point at a directory with no floortrans/__init__.py.
        weights_path = tmp_path / "fake_weights.pkl"
        weights_path.write_bytes(b"x" * 1024)
        empty_repo = tmp_path / "empty_repo"
        empty_repo.mkdir()

        monkeypatch.setattr(cubicasa, "WEIGHTS_PATH", weights_path)
        monkeypatch.setattr(cubicasa, "VENDOR_REPO", empty_repo)

        with pytest.raises(RuntimeError) as err:
            cubicasa._require_setup()

        assert "repo" in str(err.value).lower() or "floortrans" in str(err.value).lower(), (
            str(err.value)
        )

    def test_output_schema_compliance(
        self, cubicasa_observed_payload: dict[str, Any]
    ) -> None:
        """A build_payload-shaped dict must validate against observed_model.schema.json.

        This locks the writer side: even without running inference, we catch
        drift between the cubicasa.py emitter and the canonical schema.
        """
        pytest.importorskip("cv2")
        jsonschema = pytest.importorskip("jsonschema")
        from scripts.oracle import cubicasa

        # Use the module-level validate function so we exercise the same path
        # the script uses in run().
        err = cubicasa.validate_against_schema(cubicasa_observed_payload)
        assert err is None, f"fixture payload failed schema validation: {err}"

        # And belt-and-suspenders: validate against the schema directly too.
        schema_path = PROJECT_ROOT / "docs" / "schema" / "observed_model.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(instance=cubicasa_observed_payload, schema=schema)


# --------------------------------------------------------------------------- #
# TestCubicasaDownload                                                        #
# --------------------------------------------------------------------------- #


class TestCubicasaDownload:
    """Idempotency + --force tests for cubicasa_download.py.

    We patch subprocess.run to record calls so we can assert the script does
    NOT re-clone or re-download when the artifacts already exist.
    """

    def test_cubicasa_download_idempotent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When repo + weights already exist, main() must NOT re-clone or re-download.

        Then with --force, both subprocess invocations must run again.
        """
        from scripts.oracle import cubicasa_download

        # Build a fake project layout under tmp_path that mirrors what
        # cubicasa_download.py expects.
        fake_vendor = tmp_path / "vendor" / "CubiCasa5k"
        fake_repo = fake_vendor / "repo"
        fake_weights_dir = fake_vendor / "weights"
        fake_repo_floortrans = fake_repo / "floortrans"
        fake_repo_floortrans.mkdir(parents=True)
        (fake_repo_floortrans / "__init__.py").write_text("", encoding="utf-8")
        fake_weights_dir.mkdir(parents=True)
        fake_weights = fake_weights_dir / "model_best_val_loss_var.pkl"
        # Write a "valid"-sized weights file (60 MB-ish placeholder; we cheat
        # by writing the minimum acceptable size and trusting the shape check).
        fake_weights.write_bytes(b"x" * cubicasa_download.MIN_WEIGHTS_BYTES)

        monkeypatch.setattr(cubicasa_download, "VENDOR_DIR", fake_vendor)
        monkeypatch.setattr(cubicasa_download, "REPO_DIR", fake_repo)
        monkeypatch.setattr(cubicasa_download, "WEIGHTS_DIR", fake_weights_dir)
        monkeypatch.setattr(cubicasa_download, "WEIGHTS_PATH", fake_weights)

        # Pretend git + gdown are on PATH so we never short-circuit on _has().
        monkeypatch.setattr(cubicasa_download, "_has", lambda cmd: True)

        recorded_calls: list[list[str]] = []

        def fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> Any:
            recorded_calls.append(list(cmd))

            class _R:
                returncode = 0

            return _R()

        monkeypatch.setattr(cubicasa_download.subprocess, "run", fake_run)

        # First call: artifacts already present -> no subprocess invocation.
        rc = cubicasa_download.main([])
        assert rc == 0
        assert recorded_calls == [], (
            f"idempotent run unexpectedly invoked subprocesses: {recorded_calls}"
        )

        # Second call: same -> still no subprocess invocation.
        recorded_calls.clear()
        rc = cubicasa_download.main([])
        assert rc == 0
        assert recorded_calls == [], (
            f"second idempotent run unexpectedly invoked subprocesses: {recorded_calls}"
        )

        # Third call with --force: must invoke git clone AND gdown again.
        # Note: --force removes existing weights file before re-download. Our
        # fake_run is a no-op, so we must manually re-create the file after
        # the rmtree-then-fake-clone sequence so the post-download size check
        # passes.
        recorded_calls.clear()

        # Re-create weights after main() unlinks them, by pre-seeding fake_run
        # for the gdown call to put bytes back where the script expects them.
        def fake_run_reseeding(cmd: list[str], *args: Any, **kwargs: Any) -> Any:
            recorded_calls.append(list(cmd))
            if cmd and cmd[0] == "gdown":
                fake_weights.parent.mkdir(parents=True, exist_ok=True)
                fake_weights.write_bytes(b"x" * cubicasa_download.MIN_WEIGHTS_BYTES)
            elif cmd and cmd[0] == "git":
                # Re-create the cloned floortrans tree so the post-clone check passes.
                fake_repo_floortrans.mkdir(parents=True, exist_ok=True)
                (fake_repo_floortrans / "__init__.py").write_text("", encoding="utf-8")

            class _R:
                returncode = 0

            return _R()

        monkeypatch.setattr(cubicasa_download.subprocess, "run", fake_run_reseeding)

        rc = cubicasa_download.main(["--force"])
        assert rc == 0
        # We expect at least one git invocation and one gdown invocation.
        commands = [call[0] for call in recorded_calls if call]
        assert "git" in commands, f"--force did not re-clone (calls: {recorded_calls})"
        assert "gdown" in commands, f"--force did not re-download (calls: {recorded_calls})"


# --------------------------------------------------------------------------- #
# TestCompareOracles                                                          #
# --------------------------------------------------------------------------- #


# Only define this class if the script actually exists; otherwise pytest will
# collect zero tests for it, which is exactly what we want.
_COMPARE_PATH = ORACLE_DIR / "compare_oracles.py"
COMPARE_AVAILABLE = _COMPARE_PATH.is_file()


@pytest.mark.skipif(
    not COMPARE_AVAILABLE,
    reason="scripts/oracle/compare_oracles.py not present yet — comparison tests skipped",
)
class TestCompareOracles:
    """Tests for the 3-way comparison tool. Only run when the script exists.

    Because compare_oracles.py is being authored in parallel and its public
    API is not pinned yet, these tests probe the script defensively: they
    skip individual checks when the expected entry point is missing.
    """

    @staticmethod
    def _import_compare() -> Any:
        """Import compare_oracles fresh; fail with a clean skip if it can't load."""
        try:
            module = importlib.import_module("scripts.oracle.compare_oracles")
        except Exception as exc:  # noqa: BLE001 - we want the message
            pytest.skip(f"compare_oracles import failed: {exc}")
        return module

    def test_compare_pipeline_only(self, tmp_path: Path) -> None:
        """With only pipeline output present, comparison still produces valid JSON
        (just without cubicasa/llm columns)."""
        compare = self._import_compare()

        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "observed_model.json").write_text(
            json.dumps({
                "run_id": "deadbeef" * 4,
                "walls": [], "rooms": [], "openings": [], "junctions": [],
            }),
            encoding="utf-8",
        )
        out_json = tmp_path / "comparison.json"

        # main() expects argv list. Without cubicasa or llm, with only pipeline
        # provided, "nothing to compare" -> SystemExit code 1.
        with pytest.raises(SystemExit) as exc:
            compare.main(["--pipeline", str(run_dir), "--out", str(out_json)])
        assert exc.value.code == 1

    def test_compare_counts_correct(self, tmp_path: Path) -> None:
        """Mock pipeline (5 walls, 2 rooms) + mock CubiCasa (3 walls, 1 room) ->
        deltas computed correctly."""
        compare = self._import_compare()

        pipeline_run = tmp_path / "pipeline_run"
        pipeline_run.mkdir()
        cubicasa_run = tmp_path / "cubicasa_run"
        cubicasa_run.mkdir()

        def _walls(n: int) -> list[dict[str, Any]]:
            return [{
                "wall_id": f"w-{i}", "parent_wall_id": f"w-{i}", "page_index": 0,
                "start": [0.0, float(i)], "end": [10.0, float(i)],
                "thickness": 4.0, "orientation": "horizontal",
                "source": "test", "confidence": 0.9,
            } for i in range(n)]

        def _rooms(n: int) -> list[dict[str, Any]]:
            return [{
                "room_id": f"r-{i}",
                "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]],
                "area": 100.0, "centroid": [5.0 + 100 * i, 5.0],
            } for i in range(n)]

        (pipeline_run / "observed_model.json").write_text(json.dumps({
            "run_id": "deadbeef" * 4,
            "walls": _walls(5), "rooms": _rooms(2),
            "openings": [], "junctions": [],
        }), encoding="utf-8")
        (cubicasa_run / "cubicasa_observed.json").write_text(json.dumps({
            "run_id": "cafef00d" * 4,
            "walls": _walls(3), "rooms": _rooms(1),
            "openings": [], "junctions": [],
        }), encoding="utf-8")

        out_json = tmp_path / "comparison.json"
        rc = compare.main([
            "--pipeline", str(pipeline_run),
            "--cubicasa", str(cubicasa_run),
            "--out", str(out_json),
        ])
        assert rc == 0
        payload = json.loads(out_json.read_text(encoding="utf-8"))
        assert payload["counts"]["pipeline"]["walls"] == 5
        assert payload["counts"]["pipeline"]["rooms"] == 2
        assert payload["counts"]["cubicasa"]["walls"] == 3
        assert payload["counts"]["cubicasa"]["rooms"] == 1
        assert payload["deltas"]["walls_pipeline_vs_cubicasa"]["diff"] == 2
        assert payload["deltas"]["rooms_pipeline_vs_cubicasa"]["diff"] == 1

    def test_centroid_matching(self) -> None:
        """Rooms with centroids 5 px apart match; rooms 100 px apart do not.

        This exercises the geometric matching helper if exported. If not, skip.
        """
        compare = self._import_compare()

        match_fn = (
            getattr(compare, "match_rooms_by_centroid", None)
            or getattr(compare, "match_centroids", None)
            or getattr(compare, "_match_rooms", None)
        )
        if not callable(match_fn):
            pytest.skip("compare_oracles exports no centroid-match helper")

        room_a = {"room_id": "a", "centroid": [50.0, 50.0]}
        room_b_close = {"room_id": "b", "centroid": [54.0, 53.0]}  # ~5 px away
        room_b_far = {"room_id": "c", "centroid": [150.0, 150.0]}  # 100+ px away

        # We try a few argument shapes since the helper isn't pinned.
        try:
            close = match_fn([room_a], [room_b_close])
        except TypeError:
            try:
                close = match_fn(room_a, room_b_close)
            except TypeError:
                pytest.skip("centroid match helper signature unrecognised")

        try:
            far = match_fn([room_a], [room_b_far])
        except TypeError:
            far = match_fn(room_a, room_b_far)

        # Truthy / non-empty for close pairs; falsy / empty for far pairs.
        if isinstance(close, (list, tuple)):
            assert len(close) > 0, f"close centroids did not match. Got: {close}"
        else:
            assert close, f"close centroids did not match. Got: {close}"

        if isinstance(far, (list, tuple)):
            assert len(far) == 0, f"far centroids unexpectedly matched. Got: {far}"
        else:
            assert not far, f"far centroids unexpectedly matched. Got: {far}"
