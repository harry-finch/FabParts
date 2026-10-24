"""Repeat native UI cycles; Rust diagnostics identify each owned engine exactly."""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "local-data/fabparts-tech01b"
COPY = ROOT / "local-data/fabparts-tech01/catalogue-copy"
APP = (
    ROOT
    / "prototypes/fabparts-tech-01/src-tauri/target/release/bundle/macos"
    / "FabParts TECH-01.app/Contents/MacOS/fabparts-tech-01"
)


def hashes(folder):
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in folder.rglob("*")
        if p.is_file()
    }


def processes():
    result = subprocess.run(
        ["ps", "-ww", "-axo", "pid=,ppid=,pgid=,comm="],
        capture_output=True,
        text=True,
        check=True,
    )
    rows = {}
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 3)
        if len(fields) == 4:
            rows[int(fields[0])] = {"ppid": int(fields[1]), "pgid": int(fields[2])}
    return rows


def descendant(pid, parent, rows):
    seen = set()
    while pid in rows and pid not in seen:
        if pid == parent:
            return True
        seen.add(pid)
        pid = rows[pid]["ppid"]
    return pid == parent


def signal_owned_engine(launcher, app_pid, engine_pid):
    rows = processes()
    if launcher.poll() is not None or not descendant(app_pid, launcher.pid, rows):
        raise RuntimeError("Application outside the launched process tree; no signal sent")
    child = rows.get(engine_pid)
    if not child or child["ppid"] != app_pid or child["pgid"] != engine_pid:
        raise RuntimeError(f"Engine ownership/group changed for PID {engine_pid}; no signal sent")
    if os.getpgid(engine_pid) != engine_pid:
        raise RuntimeError("Engine group changed; no signal sent")
    os.killpg(engine_pid, signal.SIGTERM)


def events(log):
    records = []
    for line in log.read_text(errors="replace").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and record.get("component") == "fabparts-runtime":
            records.append(record)
    return records


def wait_event(log, predicate, launcher, start=0, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for event in events(log)[start:]:
            if predicate(event):
                return event
        if launcher.poll() is not None:
            raise RuntimeError(f"Launcher exited with code {launcher.returncode} before event")
        time.sleep(0.1)
    raise RuntimeError("Expected runtime event absent after timeout; inspect the cycle log")


def wait_no_orphans(app_pid, groups):
    deadline = time.monotonic() + 5
    while True:
        rows = processes()
        remaining = {
            pid: row
            for pid, row in rows.items()
            if pid == app_pid or row["ppid"] == app_pid or row["pgid"] in groups
        }
        if not remaining:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Processes remaining after close: {remaining}")
        time.sleep(0.1)


def run_cycle(mode, number, directory, copy):
    log_path = directory / f"cycle-{number}.log"
    report = directory / f"cycle-{number}.json"
    before = hashes(copy)
    result = {"result": "RUNNING", "mode": mode, "cycle": number, "stage": "launch"}

    def save():
        report.write_text(json.dumps(result, indent=2) + "\n")

    environment = dict(os.environ, FABPARTS_DIAGNOSTICS="1", CARGO_NET_OFFLINE="true")
    if mode == "release":
        command = [str(APP), "--data-dir", str(copy)]
        result["app_sha256"] = hashlib.sha256(APP.read_bytes()).hexdigest()
    else:
        command = [
            "npm",
            "run",
            "tauri",
            "--",
            "dev",
            "--no-watch",
            "--no-dev-server",
            "--features",
            "custom-protocol",
            "--",
            "--",
            "--data-dir",
            str(copy),
        ]
    with log_path.open("w") as log:
        launcher = subprocess.Popen(
            command,
            cwd=ROOT / "prototypes/fabparts-tech-01",
            env=environment,
            stdout=log,
            stderr=log,
        )
        result["launcher_pid"] = launcher.pid
        save()
        try:
            # Development can compile before the native process starts.
            ready = wait_event(
                log_path,
                lambda e: e["event"] == "ready",
                launcher,
                timeout=180 if mode == "dev" else 60,
            )
            app_pid = ready["app_pid"]
            result.update(stage="search_select", app_pid=app_pid)
            wait_event(
                log_path,
                lambda e: e["event"] == "request_ok" and e.get("method") == "get_component",
                launcher,
            )
            first = len(events(log_path))
            save()
            input(
                f"Cycle {number} — Recherchez NE555, sélectionnez sa ligne et vérifiez la fiche. "
                "Appuyez ensuite sur Entrée ici : "
            )
            for method in ("list_components", "get_component"):
                wait_event(
                    log_path,
                    lambda e, method=method: (
                        e["event"] == "request_ok" and e.get("method") == method
                    ),
                    launcher,
                    start=first,
                    timeout=5,
                )
            current = [e for e in events(log_path) if e["event"] == "ready"][-1]
            engine = current["sidecar_pid"]
            result.update(stage="interrupt", initial_engine=engine)
            save()
            signal_owned_engine(launcher, app_pid, engine)
            wait_event(
                log_path,
                lambda e: e["event"] == "request_failed" and e.get("sidecar_pid") == engine,
                launcher,
                start=first,
                timeout=15,
            )
            result["stage"] = "restart"
            save()
            input(
                "Vérifiez « Moteur indisponible », cliquez « Redémarrer le moteur », "
                "attendez le catalogue puis Entrée ici : "
            )
            new = wait_event(
                log_path,
                lambda e: e["event"] == "ready" and e.get("sidecar_pid") != engine,
                launcher,
                start=first,
            )
            wait_event(
                log_path,
                lambda e: (
                    e["event"] == "request_ok"
                    and e.get("sidecar_pid") == new["sidecar_pid"]
                    and e.get("method") == "get_component"
                ),
                launcher,
                start=first,
            )
            result.update(stage="close", restarted_engine=new["sidecar_pid"])
            save()
            input("Fermez cette instance FabParts avec ⌘Q, puis Entrée ici : ")
            launcher.wait(timeout=10)
            records = events(log_path)
            if launcher.returncode != 0 or not any(e["event"] == "app_closed" for e in records):
                raise RuntimeError(f"Incomplete app close, launcher code {launcher.returncode}")
            groups = {e["sidecar_pid"] for e in records if e["event"] == "spawned"}
            wait_no_orphans(app_pid, groups)
            if before != hashes(copy):
                raise RuntimeError("Catalogue copy changed")
            result.update(
                result="PASS",
                stage="complete",
                exit_code=launcher.returncode,
                no_orphans=True,
                observed_groups=sorted(groups),
                copy_unchanged=True,
                ui_confirmation="manual search, detail, unavailable, restart, catalogue, quit",
            )
        except (Exception, KeyboardInterrupt) as error:
            result.update(
                result="FAIL",
                error=f"{type(error).__name__}: {error}",
                exit_code=launcher.poll(),
                copy_unchanged=before == hashes(copy),
            )
        save()
        # Never silently close a failed native run or an unrelated application.
    print(f"Cycle {number}: {result['result']} ({result['stage']}) — {report}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("release", "dev"), default="release")
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--data-dir", type=Path, default=COPY)
    args = parser.parse_args()
    if not 1 <= args.cycles <= 10:
        parser.error("--cycles must be between 1 and 10")
    directory = BASE / "runs" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S-%fZ")
    directory.mkdir(parents=True)
    summary = {
        "mode": args.mode,
        "requested_cycles": args.cycles,
        "cycles": [],
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    for number in range(1, args.cycles + 1):
        result = run_cycle(args.mode, number, directory, args.data_dir.resolve(strict=True))
        summary["cycles"].append(result)
        (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        if result["result"] != "PASS":
            print("Essai conservé. Fermez l'instance restante avant de reprendre.")
            return 1
    print(f"native_lifecycle: PASS — {args.cycles} cycle(s) {args.mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
