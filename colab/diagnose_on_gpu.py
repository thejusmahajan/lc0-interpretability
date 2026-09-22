# %% [markdown]
# # Chess Speak Out Loud — GPU diagnosis on Colab
#
# Runs the full diagnosis pipeline (LC0 + BT3) on a Colab **GPU** so a large PGN
# finishes in ~minutes instead of ~hours, then builds repertoire trees + drills.
# Outputs land in `data/training/` and are zipped for download.
#
# Validated on an A100 (cuda-fp16 ~167k nps). The `⚠️ ITERATE` cells are the
# env-specific parts (CUDA LC0 build, BT3 device); everything else invokes the
# pipeline exactly as the app does.
#
# ## Before you start — upload these to one Google Drive folder (NOT on GitHub;
#    nets + PGN are gitignored), then mount Drive below:
#   - `791556.pb.gz`  (small SE-ResNet, ~18 MB — fast policy net)
#   - `BT3-768x15x24h-swa-2790000.pb.gz`  (BT3 in lc0 format, ~183 MB — the STRONG
#       search net; recommended for the diagnosis, coherent with the saliency net)
#   - `bt3.onnx`      (BT3 for attention saliency, ~392 MB)
#   - your games PGN  (full export, or the curated `test_subset.pgn`)
#
# **Runtime → Change runtime type → A100 GPU** before running.

# %% [markdown]
# ## 1. GPU check
# %%
import subprocess, sys
print(subprocess.run(["nvidia-smi"], capture_output=True, text=True).stdout or "NO GPU — set Runtime→GPU")
import importlib
try:
    import torch
    print("torch", torch.__version__, "| cuda:", torch.cuda.is_available(),
          "|", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu")
except Exception as e:
    print("torch not yet installed:", e)

# %% [markdown]
# ## 2. Mount Drive (nets + PGN live here) and set paths
# %%
from google.colab import drive
drive.mount("/content/drive")
# ⚠️ EDIT these to where you put the files on your Drive:
DRIVE = "/content/drive/MyDrive/colab_chess_speak_out_loud"          # folder holding the 3 files
WEIGHTS_SRC     = f"{DRIVE}/791556.pb.gz"                        # small fast net
BT3_WEIGHTS_SRC = f"{DRIVE}/BT3-768x15x24h-swa-2790000.pb.gz"    # strong search net (lc0 fmt)
BT3_SRC         = f"{DRIVE}/bt3.onnx"                            # BT3 for saliency
# === WHICH GAMES ===  default = the curated 30-game validation subset.
# Upload test_subset.pgn to Drive first (built by colab/build_test_subset.py).
# Swap to the full corpus only for a real full run (9000 games — hours!).
PGN_SRC         = f"{DRIVE}/test_subset.pgn"                       # <- 30-game subset
# PGN_SRC       = f"{DRIVE}/lichess_derdiedasdie_2026-07-21.pgn"   # <- FULL corpus (slow!)
PLAYER_NAME = "derdiedasdie"
import os
for p in (WEIGHTS_SRC, BT3_WEIGHTS_SRC, BT3_SRC, PGN_SRC):
    print(("OK  " if os.path.exists(p) else "MISSING "), p)

# %% [markdown]
# ## 3. Clone the repo (private → needs a GitHub token) + install deps
# %%
GH_REPO = "thejusmahajan/chess_speak_out_loud"
BRANCH = "windows-dev"
# Private repo -> Colab needs READ access. Best: store a FINE-GRAINED, READ-ONLY
# PAT (scoped to just this repo) in Colab Secrets — left sidebar 🔑 icon -> add a
# secret named GH_TOKEN, toggle "Notebook access" on. NEVER hardcode the token
# here: the notebook auto-saves to Drive and would leak it.
try:
    from google.colab import userdata
    GH_TOKEN = userdata.get("GH_TOKEN") or ""
except Exception:
    GH_TOKEN = ""   # (if you must, paste a token here temporarily — less safe)
if not GH_TOKEN:
    print("WARNING: no GH_TOKEN — a private-repo clone/fetch will fail. Add it to "
          "Colab Secrets, or make the repo public (code only; nets/PGN are gitignored).")
%cd /content
url = f"https://{GH_TOKEN}@github.com/{GH_REPO}.git" if GH_TOKEN else f"https://github.com/{GH_REPO}.git"
if not os.path.exists("/content/repo"):
    subprocess.run(["git", "clone", "--branch", BRANCH, "--depth", "1", url, "repo"], check=True)
else:
    # ALWAYS pull latest — a runtime restart keeps /content/repo, so a plain
    # clone-if-absent would silently run STALE code (this exact trap caused a
    # fixed crash to recur). Force the working tree to origin/<branch>.
    subprocess.run(["git", "-C", "repo", "fetch", "-q", "origin", BRANCH], check=True)
    subprocess.run(["git", "-C", "repo", "reset", "--hard", f"origin/{BRANCH}"], check=True)
%cd /content/repo
print("repo at:", subprocess.run(["git", "-C", "/content/repo", "rev-parse", "--short", "HEAD"],
                                  capture_output=True, text=True).stdout.strip())
# The conda env holds the deps locally; on Colab pip-install the real ones:
!pip -q install python-chess onnx onnx2torch lczerolens python-dotenv numpy fastapi uvicorn google-generativeai
# torch is preinstalled on Colab with CUDA — do NOT reinstall it.

# %% [markdown]
# ## 4. Place weights + get a working CUDA LC0 (validate cache, else compile)
# lc0 uses the GPU via its own CUDA backend (not torch). There's no prebuilt
# Linux-CUDA release, so we compile from source ONCE and cache the binary to
# Drive per GPU type. On every run we VALIDATE the cached binary by actually
# running a cuda-fp16 benchmark here (proves the binary works + the CUDA runtime
# libs are present this session); only if that fails do we recompile. Foolproof.
# %%
os.makedirs("/content/repo/engine", exist_ok=True)
import shutil
shutil.copy(WEIGHTS_SRC,     "/content/repo/engine/791556.pb.gz")
shutil.copy(BT3_WEIGHTS_SRC, "/content/repo/engine/BT3-768x15x24h-swa-2790000.pb.gz")
shutil.copy(BT3_SRC,         "/content/repo/engine/bt3.onnx")

# LC0 compilation & binary resolution:
# Official LC0 GitHub releases do not provide pre-compiled Linux CUDA archives.
# We compile LC0 from source (takes ~1 min with ninja) and cache per GPU type (T4 vs A100).

import torch
gpu_name = torch.cuda.get_device_name(0).replace(" ", "_") if torch.cuda.is_available() else "cpu"
LC0_DRIVE_BIN = f"{DRIVE}/lc0_{gpu_name}"
_WEIGHTS_CHECK = "/content/repo/engine/791556.pb.gz"   # small net for a quick validate


def lc0_works(binpath):
    """A cached/compiled binary counts as 'correct' only if it runs a cuda-fp16
    benchmark HERE — proving the binary is intact AND the CUDA runtime libs are
    present in this session (a cached binary from another session can be stale)."""
    if not binpath or not os.path.exists(binpath):
        return False
    try:
        os.chmod(binpath, 0o755)
        r = subprocess.run([binpath, "benchmark", f"--weights={_WEIGHTS_CHECK}",
                            "--backend=cuda-fp16", "--num-positions=1", "--movetime=1000"],
                           capture_output=True, text=True, timeout=180)
        blob = (r.stdout + r.stderr).lower()
        ok = ("nodes/second" in blob) and ("error" not in blob)
        if not ok:
            print("  cached binary failed validation (will recompile)")
        return ok
    except Exception as e:
        print("  validation error (will recompile):", e)
        return False


LC0_BIN = None
print(f"Checking for a cached, WORKING lc0 for {gpu_name} ...")
if lc0_works(LC0_DRIVE_BIN):
    LC0_BIN = LC0_DRIVE_BIN
    print("OK — using cached validated lc0:", LC0_DRIVE_BIN)
else:
    print("No valid cached binary — compiling from source (~a few min)...")

# Compile only if we still lack a working binary. Magics run at cell top-level.
if LC0_BIN is None:
    !apt-get update -qq && apt-get install -y -qq git ninja-build libprotobuf-dev protobuf-compiler libopenblas-dev
    !pip -q install meson
    !cd /content && if [ ! -d "lc0" ]; then git clone -b release/0.31 --recurse-submodules https://github.com/LeelaChessZero/lc0.git; fi
    !rm -rf /content/lc0/build
    !cd /content/lc0 && ./build.sh
    _fresh = "/content/lc0/build/release/lc0"
    if lc0_works(_fresh):
        LC0_BIN = _fresh
        try:
            shutil.copy(_fresh, LC0_DRIVE_BIN)
            print("Cached freshly built lc0 to Drive:", LC0_DRIVE_BIN)
        except Exception as e:
            print("Could not cache to Drive:", e)
    else:
        raise RuntimeError("freshly built lc0 failed the cuda-fp16 benchmark — see the build log above")

print("lc0 binary READY:", LC0_BIN)

# %% [markdown]
# ## 5. Build the engine + vision objects (same classes the app uses)
# %%
sys.path.insert(0, "/content/repo")
from backend.engine_manager import LC0Engine
from backend.neural_vision import NeuralVision

# SEARCH net for the diagnosis. BT3 (strong transformer) gives a far more
# reliable profile than the small 791556 AND is coherent with the BT3 saliency
# below — the same net does the "looking" (attention) and the "calculating"
# (search). The A100 makes its lower nps affordable. Swap to 791556 for a
# fast/rough pass. Cell 5b sizes the node budgets to match whichever net this is.
SEARCH_WEIGHTS = "/content/repo/engine/BT3-768x15x24h-swa-2790000.pb.gz"
# SEARCH_WEIGHTS = "/content/repo/engine/791556.pb.gz"   # fast/small alternative

# Force the fp16 tensor-core backend — lc0's auto pick ("cu-auto") leaves the
# A100 at ~22k nps; "cuda-fp16" hits ~168k nps (~8x). Works on any modern NVIDIA
# GPU (T4/L4/A100). engine_manager also honors os.environ["LC0_BACKEND"].
engine = LC0Engine(engine_path=LC0_BIN,
                   weights_path=SEARCH_WEIGHTS,
                   custom_uci_options={"Backend": "cuda-fp16"})
await engine.start()   # Colab notebooks allow top-level await
print("engine available (GPU LC0):", engine.is_available(), "| net:", SEARCH_WEIGHTS.split("/")[-1])

# ⚠️ ITERATE — BT3 on GPU. NeuralVision loads bt3.onnx via lczerolens; whether it
# lands on the GPU depends on lczerolens' device handling. Try enabling a default
# CUDA device BEFORE constructing it; if attention saliency errors, fall back to
# CPU (remove the set_default_device line) — LC0 will still be GPU-accelerated.
if torch.cuda.is_available():
    try:
        torch.set_default_device("cuda")
    except Exception as e:
        print("could not set default cuda device:", e)
vision = NeuralVision(onnx_path="/content/repo/engine/bt3.onnx")
print("vision mode:", vision.mode)   # want "attention"; "policy_fallback" = BT3 didn't load

# %% [markdown]
# ## 5b. GPU smoke test — confirm BT3 is on the A100 + measure the batched wins
# Uses the `vision` built above (device-aware). Prints the model device (want
# cuda:0) and times serial-vs-batched saliency + evaluate_batch. Writes and
# auto-downloads gpu_smoke.txt. Cheap (~15s) — run before any full diagnosis.
# %%
import time as _t
_R = []
def _o(*a):
    _s = " ".join(str(x) for x in a); print(_s); _R.append(_s)

_o("=== BT3 device ===")
_dev = next(vision.model.parameters()).device
_o("BT3 model device:", _dev, "->", "ON GPU" if "cuda" in str(_dev) else "STILL ON CPU (!)")
_FENS = [
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
    "6k1/5ppp/8/8/8/8/5PPP/6K1 b - - 0 1",
] * 16
_o("")
_o("=== saliency: serial vs batched ===")
_a = _t.time(); [vision.saliency_absolute(f) for f in _FENS[:16]]; _ts = _t.time() - _a
_o(f"  serial  x16: {_ts:.2f}s ({_ts/16*1000:.0f} ms/pos)")
_a = _t.time(); vision.saliency_absolute_batch(_FENS[:64]); _tb = _t.time() - _a
_o(f"  batched x64: {_tb:.2f}s ({_tb/64*1000:.0f} ms/pos) -> {(_ts/16)/max(_tb/64,1e-9):.1f}x faster/pos")
_o("")
_o("=== evaluate_batch (TS2 candidate-screen primitive) ===")
_a = _t.time(); _res = vision.evaluate_batch(_FENS[:64]); _te = _t.time() - _a
_r0 = _res[0]
_o(f"  evaluate_batch x64: {_te:.2f}s ({_te/64*1000:.0f} ms/pos)")
_o(f"  sample value={_r0['value']:+.3f} top={_r0['policy'][0]['uci']}@{_r0['policy'][0]['p']:.3f} "
   f"legal_mass={sum(m['p'] for m in _r0['policy']):.3f}")
import shutil as _sh
open("/content/gpu_smoke.txt", "w", encoding="utf-8").write("\n".join(_R))
try: _sh.copy("/content/gpu_smoke.txt", f"{DRIVE}/gpu_smoke.txt")
except Exception as _e: print("(Drive copy failed:", _e, ")")
print("\n>>> gpu_smoke.txt saved to Drive (files.download hangs in some browsers;"
      " grab it from your Drive folder or the left-sidebar file browser).")

# %% [markdown]
# ## 5c. GPU search tuning — node-limited depth (converts GPU speed into time savings)
# The default 6.0s/3.0s limits were cranked up on CPU for search depth; on a fast
# GPU they explore absurdly deep and waste wall-clock. Node budgets make depth
# hardware-INDEPENDENT (same nodes = same quality, only faster here) and are sized
# below to match the SEARCH net chosen in Cell 5 — smaller for the strong BT3,
# larger for the small 791556. Applies to Stage B, TS2, repertoire, and gems.
# %%
from backend.training import metrics
# Mutate DEFAULT_CONFIG IN PLACE (not replace) so every holder sees it: the
# pipeline reads metrics.DEFAULT_CONFIG at runtime, but select_repertoire/gems
# capture it as a default arg by identity — a replace() would leave those blind.
#
# Node budgets SCALE WITH THE SEARCH NET (SEARCH_WEIGHTS, set in Cell 5):
#  - BT3 is strong per node and runs at lower nps -> fewer nodes give a reliable
#    eval, and smaller budgets keep wall-time sane.
#  - 791556 is small/fast -> larger budgets ~match its CPU-era depth (6s/3s@20k nps).
# These are starting points — check the net probe's nps and the 3-game timing,
# then raise for more depth / lower for more speed.
if "BT3" in SEARCH_WEIGHTS:
    # The diagnosis is bound by deep lc0 searches, so this is the main
    # speed/quality dial. "high" = validated quality baseline (the 20-finding
    # reference); "low" = ~2.5x faster (node-knee test — verify §5 findings hold).
    BT3_BUDGET = "high"    # "high" (quality) or "low" (fast)
    _BUDGETS = {
        "high": {"confirm_best_nodes": 40_000, "confirm_played_nodes": 20_000,
                 "repertoire_eval_nodes": 30_000, "gem_screen_nodes": 10_000,
                 "gem_confirm_nodes": 40_000},
        "low":  {"confirm_best_nodes": 15_000, "confirm_played_nodes": 8_000,
                 "repertoire_eval_nodes": 12_000, "gem_screen_nodes": 5_000,
                 "gem_confirm_nodes": 15_000},
    }
    _NODE_BUDGETS = _BUDGETS[BT3_BUDGET]
    print("BT3 budget level:", BT3_BUDGET)
else:                                  # small 791556
    _NODE_BUDGETS = {
        "confirm_best_nodes": 120_000, "confirm_played_nodes": 60_000,
        "repertoire_eval_nodes": 80_000, "gem_screen_nodes": 30_000,
        "gem_confirm_nodes": 120_000,
    }
for _f, _v in _NODE_BUDGETS.items():
    object.__setattr__(metrics.DEFAULT_CONFIG, _f, _v)   # frozen dataclass -> bypass
print("search net:", SEARCH_WEIGHTS.split("/")[-1])
print("node budgets:", _NODE_BUDGETS)

# %% [markdown]
# ## DIAGNOSIS — runs AFTER Cell 5. GPU/CPU per component, per-stage timing, Stage B findings.
# Writes a clean `diagnosis_report.txt`, copies it to Drive, and auto-downloads it to your
# machine (no terminal copy-paste). Step 4 overwrites profile.json with a 3-game profile.
# %%
import subprocess, time, shutil
from collections import Counter
from backend.training import store, pipeline

WEIGHTS = SEARCH_WEIGHTS   # benchmark the SAME net the engine actually searches with
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
R = []
def out(*a):
    s = " ".join(str(x) for x in a); print(s); R.append(s)


def _gpu():
    return subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                           "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()


out("=== 1) lc0 backend + speed (forced cuda-fp16 = what the app engine uses) ===")
out("GPU idle:", _gpu())
b = subprocess.run([LC0_BIN, "benchmark", f"--weights={WEIGHTS}",
                    "--backend=cuda-fp16", "--num-positions=2"],
                   capture_output=True, text=True)
for ln in (b.stderr + b.stdout).splitlines():
    if any(k in ln.lower() for k in ("creating backend", "nodes/second", "error")):
        out("  ", ln.strip())

out("")
out("=== 2) app engine: is the net on the GPU? (non-zero MiB while alive) ===")
if "engine" in globals() and engine.is_available():
    out("GPU w/ engine loaded:", _gpu())
    t = time.time()
    await engine.analyze(START, multipv=2, time_limit=2.0)
    out(f"analyze(2.0s) wall: {time.time()-t:.2f}s")
else:
    out("engine not built — run Cell 5 first")

out("")
out("=== 3) BT3 saliency device/speed ===")
if "vision" in globals():
    out("vision.mode:", vision.mode, "(want 'attention')")
    t = time.time()
    n = len(vision.saliency_absolute(START))
    out(f"one saliency: {time.time()-t:.2f}s over {n} squares  (GPU <0.1s / CPU ~1.5s)")
else:
    out("vision not built — run Cell 5 first")

out("")
out("=== 4) instrumented 3-game run: where does the wall-clock go? ===")
raw = open(PGN_SRC, encoding="utf-8").read()
blocks = raw.split("\n[Event ")
allg = [(g if i == 0 else "[Event " + g) for i, g in enumerate(blocks)]
mine = [g for g in allg if PLAYER_NAME.lower() in g.lower()][:3]
subset = "\n\n".join(mine)
out(f"running {len(mine)} games...")

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
    out(f"  {lbl:18s}: " + (f"{w[0]:.1f}s -> {w[1]:.1f}s  ({w[1]-w[0]:.1f}s active)"
                            if w else "-- (never reported / 0 items)"))
out(f"  TOTAL 3 games: {tot:.1f}s")

out("")
out("=== 5) what the 3-game run PRODUCED (Stage B ground truth) ===")
prof = store.load_profile()
fs = prof.get("findings", [])
out("findings:", len(fs),
    "| severity:", dict(Counter(f.get("severity") for f in fs)),
    "| confirmed:", dict(Counter(bool(f.get("confirmation", {}).get("confirmed")) for f in fs)))
out("by_phase:", prof.get("aggregates", {}).get("by_phase"))
out("")
out("GPU final:", _gpu())

# --- write a clean report file, copy to Drive, and download it (no copy-paste) ---
report = "\n".join(R)
open("/content/diagnosis_report.txt", "w", encoding="utf-8").write(report)
try:
    shutil.copy("/content/diagnosis_report.txt", f"{DRIVE}/diagnosis_report.txt")
    print("copied report to Drive:", f"{DRIVE}/diagnosis_report.txt")
except Exception as e:
    print("(could not copy to Drive:", e, ")")
print("\n>>> diagnosis_report.txt saved to Drive + /content — grab it from your Drive"
      " folder or the left-sidebar file browser (files.download hangs in some browsers).")

# %% [markdown]
# ## 6. VALIDATE on a small subset first (do NOT run the full PGN blindly)
# Slice the newest N games of the player, run diagnosis, confirm it produces a
# non-degenerate profile, and time it — then scale up.
# %%
import re, time, chess.pgn
from tqdm.notebook import tqdm
from backend.training import store, pipeline, metrics

# Search depth is configured once in Cell 5b (node-limited, quality-preserving).
# Do NOT reset DEFAULT_CONFIG here — that would wipe the node budgets.

def select_recent_games(pgn_text, player, n):
    player_lower = player.lower()
    raw_blocks = pgn_text.split("\n[Event ")
    games = []
    for i, b in enumerate(raw_blocks):
        full_game = b if i == 0 else "[Event " + b
        if player_lower in full_game.lower():
            games.append(full_game)
    
    def key(g):
        d = re.search(r'\[UTCDate "([^"]+)"\]', g)
        t = re.search(r'\[UTCTime "([^"]+)"\]', g)
        return ((d.group(1) if d else ""), (t.group(1) if t else ""))
        
    games.sort(key=key)
    return games[-n:]

print("Reading PGN file...")
pgn_text = open(PGN_SRC, encoding="utf-8").read()
N_TEST = 40
subset_games = select_recent_games(pgn_text, PLAYER_NAME, N_TEST)
print(f"Selected {len(subset_games)} games for player '{PLAYER_NAME}'. Starting diagnosis...")

# The pipeline prints its OWN correct per-stage bars (Stage A / Stage B / TS2).
# We don't wrap it — the old wrapper bar used one total for all stages, which
# made Stage B look frozen near 0%. To run the CURATED subset instead of "recent
# N", set PGN_SRC = ".../test_subset.pgn" in Cell 2 and N_TEST large enough.
subset = "\n\n".join(subset_games)
t0 = time.time()
os.environ["STEER_SEARCH_BUDGET"] = "50000"
await pipeline.run_diagnosis("colab-test", subset, PLAYER_NAME, engine, vision)

prof = store.load_profile()
dt = time.time() - t0
print(f"✅ {N_TEST} test games completed in {dt:.0f}s ({dt/N_TEST:.1f}s/game) -> "
      f"findings={len(prof.get('findings',[]))} "
      f"by_phase={'yes' if 'by_phase' in prof.get('aggregates',{}) else 'NO'}")

# %% [markdown]
# ## 7. Full run (set N to how many games you want; None = all)
# %%
N_FULL = None     # None = analyze ALL games in the PGN (e.g. all 4000+ games)
games = select_recent_games(pgn_text, PLAYER_NAME, N_FULL or 10**9)
print(f"Starting FULL diagnosis over all {len(games)} games for player '{PLAYER_NAME}'...")

await pipeline.run_diagnosis("colab-full", "\n\n".join(games), PLAYER_NAME, engine, vision)
if pbar_full is not None:
    pbar_full.close()
    pipeline._progress = orig_progress

prof = store.load_profile()
agg = prof.get("aggregates", {})
print("✅ FULL DIAGNOSIS COMPLETED!")
print("games", prof.get("games_analyzed"), "moves", prof.get("moves_analyzed"),
      "findings", len(prof.get("findings", [])),
      "| by_phase:", agg.get("by_phase"), "| by_clock:", agg.get("by_clock"))

# %% [markdown]
# ## 8. Build repertoires + a few trees + a drill set (optional)
# %%
from backend.training import select_repertoire, drills
for style in ("weakness", "sacrificial"):
    for color in ("white", "black"):
        try:
            rep = await select_repertoire.build_repertoire(prof, color, engine, style=style)
            store.save_repertoire(rep)
            print(f"repertoire {style}/{color}: {len(rep.get('recommendations',[]))} lines")
        except Exception as e:
            print(f"repertoire {style}/{color} failed:", e)

# a couple of variation trees for the top openings (adjust ECOs/colors)
for eco, color in [("A40", "white"), ("A46", "white"), ("D02", "white")]:
    try:
        tree = await select_repertoire.build_repertoire_tree(
            eco, color, PGN_SRC, PLAYER_NAME, engine, profile=prof)
        n_crit = sum(1 for n in tree["nodes"] if n.get("critical"))
        print(f"tree {eco}/{color}: {len(tree['nodes'])} nodes, {n_crit} critical")
    except Exception as e:
        print(f"tree {eco}/{color} failed:", e)

await engine.stop()

# %% [markdown]
# ## 9. Package the artifacts for download
# The whole `data/training/` (profile.json, profiles/, repertoire_*.json,
# repertoire_tree_*.json, drills/, srs.json, cache/) — bring it back to your
# machine and drop it into the repo's `data/training/`.
# %%
!cd /content/repo && zip -q -r /content/cszero_training_data.zip data/training && ls -lh /content/cszero_training_data.zip
# Save to Drive (reliable) — files.download hangs in some browsers. Retrieve the
# zip from your Drive folder or the left-sidebar file browser, then unzip into
# the local repo's data/training/.
shutil.copy("/content/cszero_training_data.zip", f"{DRIVE}/cszero_training_data.zip")
print(">>> training.zip saved to Drive:", f"{DRIVE}/cszero_training_data.zip")
