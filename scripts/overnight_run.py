"""Overnight training-data build: diagnose -> repertoires -> drill set.

Talks to the running backend (must be started from the cszero env, see
HOW_TO_RUN.md) over HTTP, so all engine work happens in the server process
and the EPD caches make the run crash-resumable: restarting this script
re-submits the job and cached positions are free.

Steps:
  1. Preflight: /api/health must report engine_mode "live" (waits up to
     5 minutes for the backend to come up, so it can be started together
     with the backend from overnight.bat).
  2. Slice the newest --games games of --player from --pgn (with their
     [%clk] comments intact) and submit a diagnosis job; poll until done.
  3. Build all four repertoires (weakness/sacrificial x white/black).
     Each build overwrites the server's single repertoire.json, so every
     variant is also saved to data/training/repertoire_<style>_<color>.json.
  4. Generate one drill set from the fresh profile.
  5. Write data/training/overnight_report.md.

Run:  <cszero-python> scripts/overnight_run.py
"""

import argparse
import datetime
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAINING_DIR = ROOT / "data" / "training"

LOG_PATH = TRAINING_DIR / "overnight_run.log"
REPORT_PATH = TRAINING_DIR / "overnight_report.md"

POLL_SECONDS = 30
JOB_TIMEOUT_HOURS = 20
# Transient-failure budget while polling (backend hiccup / restart).
RETRY_ATTEMPTS = 20
RETRY_WAIT = 30


def log(msg: str):
    line = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def api(base: str, method: str, path: str, body=None, timeout=120):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def api_retry(base, method, path, body=None, timeout=120,
              attempts=RETRY_ATTEMPTS):
    """Retry connection failures AND 5xx (transient: e.g. a read racing the
    server's atomic job-file rename). 4xx are real answers — raised at once."""
    for i in range(attempts):
        try:
            return api(base, method, path, body, timeout)
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise
            err = f"HTTP {e.code}"
        except Exception as e:
            err = str(e)
        if i == attempts - 1:
            raise RuntimeError(f"{method} {path} failed after {attempts} "
                               f"attempts: {err}")
        log(f"  transient problem on {path} ({err}); retry "
            f"{i + 1}/{attempts - 1} in {RETRY_WAIT}s")
        time.sleep(RETRY_WAIT)


# ----------------------------------------------------------------------
# PGN slicing (text-level, keeps [%clk] comments byte-for-byte)
# ----------------------------------------------------------------------

def split_games(pgn_text: str) -> list[str]:
    """Split a multi-game PGN into game strings. A game = a header block
    (lines starting with '[') plus the following movetext block."""
    blocks = re.split(r"\n\s*\n", pgn_text.strip())
    games, current = [], []
    for block in blocks:
        if block.lstrip().startswith("[Event"):
            if current:
                games.append("\n\n".join(current))
            current = [block]
        elif current:
            current.append(block)
    if current:
        games.append("\n\n".join(current))
    return games


def _sort_key(game_text: str):
    date = re.search(r'\[UTCDate "([^"]+)"\]', game_text)
    t = re.search(r'\[UTCTime "([^"]+)"\]', game_text)
    return ((date.group(1) if date else ""), (t.group(1) if t else ""))


def select_recent_games(pgn_text: str, player: str, n: int) -> list[str]:
    games = []
    for g in split_games(pgn_text):
        headers = re.findall(r'\[(White|Black) "([^"]+)"\]', g)
        if any(player.lower() in name.lower() for _, name in headers):
            games.append(g)
    games.sort(key=_sort_key)
    return games[-n:]


# ----------------------------------------------------------------------
# Run phases
# ----------------------------------------------------------------------

def wait_for_backend(base: str, minutes: int = 5) -> dict:
    deadline = time.time() + minutes * 60
    while True:
        try:
            health = api(base, "GET", "/api/health", timeout=10)
            if health.get("engine_mode") == "live":
                return health
            log(f"backend up but engine_mode={health.get('engine_mode')!r}; "
                "waiting for LC0...")
        except Exception:
            log("backend not reachable yet; waiting...")
        if time.time() > deadline:
            raise SystemExit(
                "FATAL: backend not live after "
                f"{minutes} min. Start it per HOW_TO_RUN.md and rerun.")
        time.sleep(15)


def _find_running_job_id():
    """The runner shares the machine with the backend: when a submit is
    answered 409 (job already running — e.g. a retried POST whose first
    attempt actually landed), attach to that job instead of dying."""
    jobs = []
    for p in (TRAINING_DIR / "jobs").glob("*.json"):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if j.get("status") == "running":
            jobs.append((p.stat().st_mtime, j.get("id")))
    return max(jobs)[1] if jobs else None


def run_diagnosis(base: str, pgn: str, player: str) -> dict:
    try:
        job = api_retry(base, "POST", "/api/training/diagnose",
                        {"pgn": pgn, "player_name": player},
                        timeout=120, attempts=3)
        job_id = job["job_id"]
        log(f"diagnosis job {job_id} submitted")
    except urllib.error.HTTPError as e:
        if e.code != 409:
            raise
        job_id = _find_running_job_id()
        if not job_id:
            raise SystemExit("FATAL: server says a job is running but none "
                             "found in data/training/jobs")
        log(f"a diagnosis is already running — attaching to job {job_id}")

    started = time.time()
    last = {}
    while True:
        if time.time() - started > JOB_TIMEOUT_HOURS * 3600:
            raise SystemExit(f"FATAL: job still running after "
                             f"{JOB_TIMEOUT_HOURS}h — inspect job {job_id}")
        state = api_retry(base, "GET", f"/api/training/jobs/{job_id}")
        if state.get("status") == "error":
            raise SystemExit(f"FATAL: diagnosis failed: {state.get('error')}")
        prog = state.get("progress") or {}
        if prog != last:
            total = prog.get("total", "?")
            log(f"  stage A {prog.get('stage_a_done', 0)}/{total} "
                f"(flagged {prog.get('flagged', 0)}, scramble-skipped "
                f"{prog.get('time_scramble_skipped', 0)}) | "
                f"stage B {prog.get('stage_b_done', 0)}/{prog.get('flagged', 0)}")
            last = prog
        if state.get("status") == "done":
            log("diagnosis done")
            return prog
        time.sleep(POLL_SECONDS)


def build_repertoires(base: str) -> dict:
    out = {}
    for style in ("weakness", "sacrificial"):
        for color in ("white", "black"):
            name = f"{style}_{color}"
            try:
                rep = api_retry(base, "POST", "/api/training/repertoire",
                                {"color": color, "build": True, "style": style},
                                timeout=900, attempts=4)
                path = TRAINING_DIR / f"repertoire_{name}.json"
                path.write_text(json.dumps(rep, indent=2), encoding="utf-8")
                n = len(rep.get("recommendations", []))
                log(f"repertoire {name}: {n} lines -> {path.name}")
                out[name] = rep
            except Exception as e:
                # One variant failing must not sink the others.
                log(f"repertoire {name} FAILED: {e}")
                out[name] = None
    return out


def generate_drills(base: str, count: int):
    try:
        ds = api_retry(base, "POST", "/api/training/drills/generate",
                       {"count": count}, timeout=1800, attempts=2)
        log(f"drill set {ds.get('id')} generated "
            f"({len(ds.get('drills', []))} drills)")
        return ds
    except Exception as e:
        log(f"drill generation FAILED: {e}")
        return None


def top_items(d: dict, key: str, n=8):
    return sorted(((m, s) for m, s in (d or {}).items()),
                  key=lambda kv: -kv[1].get(key, 0))[:n]


def write_report(args, timings, prog, profile, reps, drill_set):
    agg = (profile or {}).get("aggregates", {})
    lines = [
        "# Overnight training build — "
        f"{datetime.date.today().isoformat()}",
        "",
        f"- PGN: `{args.pgn}` — newest {args.games} games of "
        f"`{args.player}`",
        f"- Total wall time: {timings['total'] / 3600:.1f} h "
        f"(diagnosis {timings['diagnosis'] / 3600:.1f} h, "
        f"repertoires {timings['repertoires'] / 60:.0f} min, "
        f"drills {timings['drills'] / 60:.0f} min)",
        "",
        "## Diagnosis",
        f"- Games analyzed: {profile.get('games_analyzed')}",
        f"- Moves analyzed: {profile.get('moves_analyzed')} "
        f"(+{profile.get('time_scramble_skipped', 0)} skipped as time "
        "scramble, clock < 20s)",
        f"- Findings: {len(profile.get('findings', []))}",
        f"- Intuitive blindness rate: "
        f"{agg.get('intuitive_blindness_rate', 0):.1%}",
        f"- Regressions vs training history: "
        f"{', '.join(profile.get('regressions', [])) or 'none'}",
        "",
        "### Top blind motifs",
    ]
    for m, s in top_items(agg.get("by_motif"), "blind"):
        lines.append(f"- {m}: blind {s.get('blind', 0)}, "
                     f"missed {s.get('missed', 0)}, "
                     f"confirmed {s.get('confirmed', 0)}")
    lines += ["", "### Worst openings (by blind count)"]
    for eco, s in top_items(agg.get("by_opening"), "blind", 6):
        lines.append(f"- {eco}: blind {s.get('blind', 0)} in "
                     f"{s.get('moves', 0)} moves "
                     f"(rate {s.get('blind_rate', 0):.1%})")
    lines += ["", "## Repertoires (also saved as JSON next to this file)"]
    for name, rep in (reps or {}).items():
        if not rep:
            lines.append(f"- {name}: FAILED (see overnight_run.log)")
            continue
        recs = rep.get("recommendations", [])
        lines.append(f"- **{name}**: {len(recs)} lines")
        for r in recs[:3]:
            lines.append(f"    - {r.get('name', r.get('tag', '?'))} "
                         f"({r.get('eco', '?')}) — {r.get('line_pgn', '')}")
    lines += ["", "## Drills"]
    if drill_set:
        by_src = {}
        for d in drill_set.get("drills", []):
            by_src[d["source"]] = by_src.get(d["source"], 0) + 1
        lines.append(f"- Set `{drill_set['id']}`: "
                     + ", ".join(f"{v} {k}" for k, v in by_src.items()))
    else:
        lines.append("- Drill generation failed (see overnight_run.log)")
    lines += ["",
              "_Note: the app's Repertoire view shows the last-built "
              "variant (sacrificial/black); the other three are in the "
              "JSON files above._", ""]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log(f"report written -> {REPORT_PATH}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pgn", default=str(
        ROOT / "games_of_derdiedasdie" / "lichess_derdiedasdie_2026-07-19.pgn"))
    ap.add_argument("--player", default="derdiedasdie")
    ap.add_argument("--games", type=int, default=300)
    ap.add_argument("--drill-count", type=int, default=20)
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    t0 = time.time()
    log("=== overnight run starting ===")
    log(f"pgn={args.pgn} player={args.player} games={args.games}")

    health = wait_for_backend(args.base_url)
    log(f"backend live (version {health.get('version')})")

    pgn_text = Path(args.pgn).read_text(encoding="utf-8")
    games = select_recent_games(pgn_text, args.player, args.games)
    if not games:
        raise SystemExit(f"FATAL: no games of {args.player} in {args.pgn}")
    log(f"selected {len(games)} most recent games "
        f"(from {_sort_key(games[0])[0]} to {_sort_key(games[-1])[0]})")

    t_diag = time.time()
    prog = run_diagnosis(args.base_url, "\n\n".join(games), args.player)
    diag_secs = time.time() - t_diag

    profile = api_retry(args.base_url, "GET", "/api/training/profile")

    t_rep = time.time()
    reps = build_repertoires(args.base_url)
    rep_secs = time.time() - t_rep

    t_dr = time.time()
    drill_set = generate_drills(args.base_url, args.drill_count)
    drill_secs = time.time() - t_dr

    try:
        write_report(args,
                     {"total": time.time() - t0, "diagnosis": diag_secs,
                      "repertoires": rep_secs, "drills": drill_secs},
                     prog, profile, reps, drill_set)
    except Exception:
        # Everything is already saved server-side; a report formatting
        # problem must not turn a finished night into a "failed" one.
        import traceback
        log("report writing FAILED (data is safe):\n" + traceback.format_exc())
    log(f"=== overnight run complete in "
        f"{(time.time() - t0) / 3600:.1f} h ===")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        if e.code not in (0, None):
            log(str(e))
        raise
    except Exception:
        import traceback
        log("FATAL:\n" + traceback.format_exc())
        raise
