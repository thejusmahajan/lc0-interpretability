# =====================================================================
#  FULL DIAGNOSIS — paste this whole block into a NEW Colab cell and run
#  it AFTER Cell 5 (needs LC0_BIN, engine, vision, PGN_SRC, PLAYER_NAME).
#  It reports, in one shot:
#    1) lc0 backend + speed (what the app engine actually uses)
#    2) whether the engine's net is on the GPU
#    3) BT3 saliency device/speed
#    4) per-STAGE wall-clock on a tiny 3-game run (where the time goes)
#    5) whether Stage B actually produced + confirmed findings
#  NOTE: step 4 overwrites profile.json with a 3-game profile — fine, you
#  re-run the real diagnosis afterward. Paste the whole output back.
# =====================================================================
import subprocess, time
from collections import Counter
from backend.training import store, pipeline

WEIGHTS = "/content/repo/engine/791556.pb.gz"
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _gpu():
    return subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                           "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()


print("=== 1) lc0 backend + speed (what the app engine gets) ===")
print("GPU idle:", _gpu())
b = subprocess.run([LC0_BIN, "benchmark", f"--weights={WEIGHTS}", "--num-positions=2"],
                   capture_output=True, text=True)
for ln in (b.stderr + b.stdout).splitlines():
    if any(k in ln.lower() for k in ("creating backend", "backend:", "nps", "nodes/s",
                                     "blas", "eigen", "error")):
        print("  ", ln.strip())

print("\n=== 2) app engine: is the net on the GPU? (non-zero MiB while alive) ===")
if "engine" in globals() and engine.is_available():
    print("GPU w/ engine loaded:", _gpu())
    t = time.time()
    await engine.analyze(START, multipv=2, time_limit=2.0)
    print(f"analyze(2.0s) wall: {time.time()-t:.2f}s")
else:
    print("engine not built — run Cell 5 first")

print("\n=== 3) BT3 saliency device/speed ===")
if "vision" in globals():
    print("vision.mode:", vision.mode, "(want 'attention')")
    t = time.time()
    n = len(vision.saliency_absolute(START))
    print(f"one saliency: {time.time()-t:.2f}s over {n} squares  (GPU <0.1s / CPU ~1.5s)")
else:
    print("vision not built — run Cell 5 first")

print("\n=== 4) instrumented 3-game run: where does the wall-clock go? ===")
raw = open(PGN_SRC, encoding="utf-8").read()
blocks = raw.split("\n[Event ")
allg = [(g if i == 0 else "[Event " + g) for i, g in enumerate(blocks)]
mine = [g for g in allg if PLAYER_NAME.lower() in g.lower()][:3]
subset = "\n\n".join(mine)
print(f"running {len(mine)} games...")

t0 = time.time()
ev = []
_orig = pipeline._progress
def _tap(job_id, **kw):
    _orig(job_id, **kw)
    ev.append((time.time() - t0, kw))
pipeline._progress = _tap
await pipeline.run_diagnosis("diag3", subset, PLAYER_NAME, engine, vision)
pipeline._progress = _orig
tot = time.time() - t0

def _win(key):
    ts = [t for t, kw in ev if kw.get(key) is not None]
    return (min(ts), max(ts)) if ts else None
for lbl, key in [("Stage A (policy)", "stage_a_done"),
                 ("Stage B (confirm)", "stage_b_done"),
                 ("TS2 (steering)", "stage_steer_done")]:
    w = _win(key)
    print(f"  {lbl:18s}: " + (f"{w[0]:.1f}s -> {w[1]:.1f}s  ({w[1]-w[0]:.1f}s active)"
                              if w else "-- (never reported / 0 items)"))
print(f"  TOTAL 3 games: {tot:.1f}s")

print("\n=== 5) what the 3-game run PRODUCED (Stage B ground truth) ===")
prof = store.load_profile()
fs = prof.get("findings", [])
print("findings:", len(fs),
      "| severity:", dict(Counter(f.get("severity") for f in fs)),
      "| confirmed:", dict(Counter(bool(f.get("confirmation", {}).get("confirmed")) for f in fs)))
print("by_phase:", prof.get("aggregates", {}).get("by_phase"))
print("\nGPU final:", _gpu())
