"""Run the frozen sidecar with no Python environment and check the complete read path."""

import argparse
import hashlib
import json
import subprocess
import tempfile
import threading
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--binary", type=Path, required=True)
parser.add_argument("--data-dir", type=Path, required=True)
args = parser.parse_args()
root = args.data_dir.resolve(strict=True)


def hashes():
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


before = hashes()
# No PATH, PYTHONPATH or Python installation is passed to the executable.
process = subprocess.Popen(
    [str(args.binary.resolve()), "--data-dir", str(root)],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    env={"TMPDIR": tempfile.gettempdir(), "LANG": "en_US.UTF-8"},
)
assert process.stdin is not None and process.stdout is not None
deadline = threading.Timer(30, process.kill)
deadline.start()
sequence = 0


def call(method, params=None):
    global sequence
    sequence += 1
    identity = f"smoke-{sequence}"
    process.stdin.write(
        json.dumps(
            {
                "protocol_version": 1,
                "request_id": identity,
                "method": method,
                "params": params or {},
            }
        )
        + "\n"
    )
    process.stdin.flush()
    response = json.loads(process.stdout.readline())
    assert response["request_id"] == identity and response["protocol_version"] == 1, response
    assert response["ok"], response
    return response["result"]


try:
    health = call("health")
    assert health["qt_loaded"] is False and health["read_only"] is True
    libraries = call("list_libraries")
    page = call("list_components", {"limit": 100})
    assert page["components"], "The real catalogue is empty"
    selected = page["components"][0]
    detail = call("get_component", {"id": selected["id"]})
    assert detail["id"] == selected["id"]
    search = call("list_components", {"search": selected["reference"]})
    assert search["total"] >= 1
    assert call("list_components", {"search": "__NO_MATCH_TECH_01__"})["total"] == 0
    call("shutdown")
    process.wait(timeout=10)
    assert process.returncode == 0
    assert before == hashes(), "Copy changed"
    print(
        json.dumps(
            {
                "packaged_sidecar": "PASS",
                "health": health,
                "libraries": len(libraries),
                "components": page["total"],
                "search": "PASS",
                "detail": "PASS",
                "shutdown": "PASS",
                "copy_unchanged": True,
                "binary": str(args.binary.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
finally:
    deadline.cancel()
    if process.poll() is None:
        process.kill()
        process.wait(timeout=5)
