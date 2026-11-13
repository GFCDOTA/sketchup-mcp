"""Demo: producer -> SQLite -> two real child processes -> persisted results."""
import json
import tempfile
from pathlib import Path
from bus import Bus, process_one

with tempfile.TemporaryDirectory() as tmp:
    bus = Bus(Path(tmp) / "events.sqlite")
    bus.publish("pr:1:sha:abc:implement", "IMPLEMENT", {"text": "Hello World"})
    process_one(bus, "IMPLEMENT", "claude-simulator")
    artifact = json.loads(bus.rows()[0]["result"])["artifact"]
    bus.publish("pr:1:sha:abc:review", "REVIEW", {"artifact": artifact, "expected": "hello-world"})
    process_one(bus, "REVIEW", "codex-simulator")
    for row in bus.rows():
        print(row["kind"], row["state"], row["result"])
