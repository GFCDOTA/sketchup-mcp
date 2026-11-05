# Real-CLI event-bus lab — evidence report (2026-11-05)

**Verdict: PASS** — `SQLite → Claude Code CLI (real) → slugify.py → SQLite → Codex CLI (real) → JSON review → SQLite → Claude Code CLI (real, correction) → Codex (real, re-review) → REVIEW_APPROVED`, plus 4/4 live resilience checks against the real CLIs.

No mocks, simulators or paid APIs were used in this run. `agent.py` (the old simulator) was not involved.

## Provenance

| | |
|---|---|
| Harness commit | `53efa09933d1968bbd715868300eb60831e3e953`, `dirty: false` (recorded by the runner itself, `e2e/result.json` → `code`) |
| Claude Code CLI | `2.1.158 (Claude Code)` — native `claude.exe`, subscription OAuth (`apiKeySource: null`), model used `claude-sonnet-4-6` |
| Codex CLI | `codex-cli 0.164.0` — `node codex.js`, ChatGPT login |
| Python | 3.12.13 (sketchup-mcp venv), stdlib only |
| Host | Windows 11, lab dir `E:\Claude\data\runs\poc605_lab\lab_v2\` (outside every git checkout; the runner refuses otherwise) |
| E2E run | `run_20261105T011535Z`, wall 36 s, 3 worker processes, all exit 0 |

Child env: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (it **was set** on this machine), `CODEX_API_KEY`, `GH_TOKEN`, `GITHUB_TOKEN`, `GIT_ASKPASS` and the parent Claude Code session markers are removed before each CLI is spawned. `run_cli` refuses `--dangerously-skip-permissions`, `--yolo`, `--dangerously-bypass-approvals-and-sandbox`, `--full-auto`, `bypassPermissions`.

## Commands executed (no secrets)

```text
python run_real_e2e.py --run-live --lab-dir E:\Claude\data\runs\poc605_lab\lab_v2 --timeout 600 --lease 60 --max-wall 3000
python live_resilience.py --run-live --lab-dir E:\Claude\data\runs\poc605_lab\lab_v2
  └ python workers.py --role {claude|codex|coordinator} --run-dir <run> --lease 60 --timeout 600 --exit-when-idle

claude.exe -p --output-format json --permission-mode dontAsk --tools Read,Write,Edit
           --allowedTools Read,Write,Edit --setting-sources "" --strict-mcp-config --no-session-persistence
           (cwd = job workspace, prompt on stdin)
node codex.js exec --sandbox read-only --skip-git-repo-check --ephemeral -C <job workspace>
           --output-schema <job>/codex/review_schema.json --output-last-message <job>/codex/review_eNNN_aN.json -
```

## Events persisted in SQLite (`e2e/events.json`, `e2e/transitions.json`)

| id | job | type | status | attempt | parent | idempotency key |
|---:|---|---|---|---:|---:|---|
| 1 | jobA-fresh | IMPLEMENT_REQUESTED | DONE | 1 | – | `jobA-fresh:r1:implement` |
| 2 | jobB-seeded-defect | REVIEW_REQUESTED | DONE | 1 | – | `jobB-seeded-defect:r0:review:69a26c2f8f2bf3db` |
| 3 | jobA-fresh | IMPLEMENT_COMPLETED | RECORDED | 0 | 1 | `jobA-fresh:r1:implement_completed` |
| 4 | jobA-fresh | REVIEW_REQUESTED | DONE | 1 | 1 | `jobA-fresh:r1:review:2a2cdf9746fe3636` |
| 5 | jobB-seeded-defect | REVIEW_CHANGES_REQUESTED | DONE | 1 | 2 | `…:r0:review_changes_requested:69a26c2f8f2bf3db` |
| 6 | jobB-seeded-defect | IMPLEMENT_REQUESTED | DONE | 1 | 5 | `jobB-seeded-defect:r1:implement` |
| 7 | jobA-fresh | REVIEW_APPROVED | RECORDED | 0 | 4 | `jobA-fresh:r1:review_approved:2a2cdf9746fe3636` |
| 8 | jobB-seeded-defect | IMPLEMENT_COMPLETED | RECORDED | 0 | 6 | `jobB-seeded-defect:r1:implement_completed` |
| 9 | jobB-seeded-defect | REVIEW_REQUESTED | DONE | 1 | 6 | `jobB-seeded-defect:r1:review:ab2ec95c75bf77c2` |
| 10 | jobB-seeded-defect | REVIEW_APPROVED | RECORDED | 0 | 9 | `…:r1:review_approved:ab2ec95c75bf77c2` |

A duplicate `IMPLEMENT_REQUESTED` with the same key (`jobA-fresh:r1:implement`, different payload) was published at seed time: same id returned, `created=False`, no second job, original payload kept.

Scenario B starts from a **labeled, human-written defective v0** (`return text.lower().replace(" ", "-")`: no strip, no collapse) so that the correction loop is exercised; finding and fixing the defect was left entirely to the real agents.

## Subprocesses (`e2e/subprocess_runs.json`)

| agent | event | PID | exit | timed out | duration | outcome |
|---|---:|---:|---:|---|---:|---|
| claude | 1 | 28288 | 0 | no | 11.3 s | ok |
| codex | 2 | 6736 | 0 | no | 11.4 s | ok → REQUEST_CHANGES |
| codex | 4 | 3960 | 0 | no | 9.3 s | ok → APPROVE |
| claude | 6 | 25792 | 0 | no | 12.4 s | ok (correction round 1) |
| codex | 9 | 23508 | 0 | no | 8.9 s | ok → APPROVE |

Workers: claude 24924, codex 12144, coordinator 31228 (PIDs of the venv launcher; see finding 5). Full prompts/stdout/stderr per run: `e2e/logs/`.

## Files written by Claude (`e2e/artifacts/<job>/`)

jobA-fresh (`sha256 2a2cdf97…`), from scratch:
```python
import re


def slugify(text: str) -> str:
    text = text.strip()
    text = text.lower()
    text = re.sub(r' +', '-', text)
    return text
```
jobB-seeded-defect (`sha256 ab2ec95c…`), Claude's correction of v0 after Codex's review:
```python
import re

def slugify(text: str) -> str:
    return re.sub(r" +", "-", text.strip().lower())
```

## Codex reviews (`e2e/artifacts/<job>/review_e*.json`)

| review | verdict | inspected / verbatim excerpt | requirements unmet | issues |
|---|---|---|---|---|
| jobB v0 (e002) | REQUEST_CHANGES | `return text.lower().replace(" ", "-")` | strip_ends, collapse_spaces, example | major: "does not remove whitespace at either end or collapse consecutive spaces…"; tests judged inadequate |
| jobA (e004) | APPROVE | `text = re.sub(r' +', '-', text)` | – | – |
| jobB fix (e009) | APPROVE | `return re.sub(r" +", "-", text.strip().lower())` | – | – |

The worker validates every review: the JSON schema (enforced by `--output-schema`), the sha256 echo, coverage of the 4 requirement ids, consistency (no APPROVE with an unmet requirement or blocker/major issue), `inspected == true`, and that `code_excerpt` is a verbatim line of the reviewed file. Workspace file hashes were taken before/after each Codex run; any change would fail the review.

## Tests

- Harness acceptance tests (outside the agent workspace, so the implementer cannot edit them): **5/5 OK** for both jobs.
- Claude's own `test_slugify.py`: 14 tests (jobA) and 10 tests (jobB), OK.
- Deterministic suite `python -m unittest discover`: **24 tests OK** (5 original + 19 new).

## Attempts

- jobA: 1 implementation round, 0 change requests, approved on first review.
- jobB: review of v0 → 1 change request → 1 correction round → approved. Limit is 3 rounds (`MAX_ROUNDS`), beyond which the coordinator emits `JOB_FAILED` (unit-tested).
- No event needed a retry; no DLQ in the E2E.

## Live resilience against the real CLIs (`resilience/resilience.json`) — 4/4 PASS

| check | what happened |
|---|---|
| R1 Claude not logged in (`CLAUDE_CONFIG_DIR` = empty dir) | PID 25556, exit 1, `"Not logged in · Please run /login"` → event DLQ + `JOB_FAILED`, no IMPLEMENT_COMPLETED |
| R2 Codex not logged in (`CODEX_HOME` = empty dir) | PID 38700, exit 1, `401 Unauthorized` → DLQ + `JOB_FAILED`, no verdict event |
| R3 Claude timeout (3 s) | PIDs 8580, 12228 killed (`timed_out=1`) → attempt 1 back to PENDING (backoff), attempt 2 → DLQ + `JOB_FAILED` |
| R4 worker killed mid-run | worker 5316 + its Claude child 23668 killed with `taskkill /T /F`; event stayed `RUNNING` (not lost); after lease expiry a new worker (16728) reclaimed it as attempt 2, real Claude run 39572 exit 0, `DONE` + `REVIEW_REQUESTED` |

## Resilience coverage map

| requirement | where proven |
|---|---|
| two consumers never process the same job | `test_two_consumer_processes_never_share_a_job` (2 OS processes, 40 events), `test_only_one_of_two_claimers_wins` |
| duplicate events → no duplicate work | seed in this run; `test_duplicate_publish_does_not_create_second_job_nor_overwrite` |
| killing the worker does not delete the event / restart recovers | R4 (real Claude); `test_killed_worker_does_not_lose_event_and_restart_recovers` |
| retry and DLQ | R3 (real Claude); `test_retry_then_dlq_records_job_failed` |
| old reviews not applied to new versions | `test_stale_review_request_is_superseded`, `test_stale_change_request_does_not_trigger_new_round`; sha re-checked after each review |
| completed jobs not re-run | `test_completed_job_is_never_claimed_again`; fencing in `test_expired_lease_is_recovered_and_old_owner_is_fenced` |
| auth errors / timeouts are not success | R1, R2, R3 |

## Failures found during the lab (real, all fixed or documented)

1. **Existing PoC tests errored on Windows (5/5).** `with sqlite3.connect()` commits but never closes, so the DB file stayed locked and `TemporaryDirectory` cleanup failed. Fixed in `bus.py` with `contextlib.closing`.
2. **Codex reviewed without reading the code.** In an earlier run from commit `539d719`, Codex's read-only sandbox on Windows could not spawn processes (`O sistema não pode executar o programa especificado`; `python.exe` access denied). Codex returned a schema-valid `REQUEST_CHANGES` saying it could not inspect anything, and the harness accepted it as a verdict, so the correction loop ran for the wrong reason while all automatic checks were green. Fixed in `53efa09`: the exact persisted file contents (bound to the sha) and the harness's real test output are embedded in the prompt, and reviews must assert `inspected` and quote a verbatim line. The very first run (`lab`, also before this fix) happened to get a genuine review. That shows the old path worked only some of the time.
3. **Codex cannot execute Python in its read-only sandbox on this host.** Tests are therefore executed by the harness and handed over to Codex as output. Codex analyzes them; it does not run them.
4. **Claude reports `subtype: "success"` together with `is_error: true` when not logged in.** A consumer that checked `subtype` alone would record a false success. The parser requires `is_error == false`, `subtype == "success"` and exit 0.
5. **Recorded worker PID ≠ `os.getpid()`.** The uv venv `python.exe` is a launcher that starts the real interpreter as a child. `taskkill /T` kills both; the lease owner name carries the interpreter PID.
6. **PR #605 CI was already red before this lab** (FP-042 strict inventory gate, PR policy, pytest). The inventory gate needs the new files registered in `docs/specs/fp042_inventory.v1.json`, which is outside the PoC directory. It was left untouched on purpose (scope: "do not change files outside the PoC").

## Not proven

OS-level fencing of a CLI that keeps running after losing its lease (its result is refused, but the process is not killed), exactly-once external side effects, GitHub reconciliation, multi-host operation, and continuous or scheduled execution. Nothing here is wired to FP-057, the SketchUp MCP or any scheduler.
