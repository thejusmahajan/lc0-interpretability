# =====================================================================
#  KAGGLE DIAGNOSTIC RUN — instrument the 1,000-game hang (do NOT fix, OBSERVE).
#  Paste this whole thing into a fresh Kaggle notebook cell and run it.
#  It reuses the same backend/weights/lc0 your working run used, but with:
#    - env + hardware facts printed up front,
#    - periodic ALL-THREAD stack dumps (faulthandler) — the key hang tool,
#    - a 10s heartbeat logging per-GPU utilization + which stage/index we're at,
#    - a watchdog that declares HANG (and dumps stacks) if no progress for N sec.
#  Start SMALL and SAFE (2 workers, 150 games). Read the output, then tell Claude:
#    (a) which STAGE the last heartbeat showed when it froze,
#    (b) the repeated faulthandler stack dump (what each thread is stuck on),
#    (c) whether GPU1 shows 0% the whole time (the all-on-GPU0 bug).
# =====================================================================
import os, sys, glob, time, threading, subprocess, faulthandler
from pathlib import Path

WORKING = Path("/kaggle/working")
os.chdir(WORKING)
if str(WORKING) not in sys.path:
    sys.path.insert(0, str(WORKING))

# ---- knobs (override via env; defaults are small + safe for diagnosis) ----
MAX_GAMES    = int(os.environ.get("MAX_GAMES", "150"))
LC0_WORKERS  = int(os.environ.get("LC0_WORKERS", "1"))   # safe-by-default: 1 engine.
                                                          # multi-worker pins all to GPU0
                                                          # (F-06) + raises OOM risk (F-04).
HANG_SECONDS = int(os.environ.get("HANG_SECONDS", "150"))   # no progress this long => HANG
os.environ.setdefault("LC0_BACKEND", "cuda-fp16")
os.environ.setdefault("STEER_SEARCH_BUDGET", "50000")
# lc0 RamLimitMb is a cache CAP (not an allocation) and search is node-limited, so
# the diagnosis is cache-size-independent (the n=1≡n4 identity gate). A modest cap
# keeps us safe if workers are scaled later. [Gemini F-04, defused: box has ~30 GiB]
os.environ.setdefault("LC0_RAM_LIMIT_MB", "4096")
# The backend is imported FROM the dataset (/kaggle/input, read-only). store.py
# resolves its data/cache dir relative to its own __file__ and reads CSZERO_DATA_DIR
# at IMPORT time — so we MUST redirect it to a writable path BEFORE backend import,
# else EpdCache init dies with "[Errno 30] Read-only file system".
os.environ.setdefault("CSZERO_DATA_DIR", str(WORKING / "data"))
print(f"[cfg] MAX_GAMES={MAX_GAMES} LC0_WORKERS={LC0_WORKERS} HANG_SECONDS={HANG_SECONDS} "
      f"CSZERO_DATA_DIR={os.environ['CSZERO_DATA_DIR']}", flush=True)

# ---- install python deps (Kaggle has torch preinstalled; the rest are not) ----
print("[deps] installing python-chess + lczerolens + friends...", flush=True)
subprocess.run([sys.executable, "-m", "pip", "-q", "install",
                "python-chess", "onnx", "onnx2torch", "lczerolens",
                "python-dotenv", "numpy", "fastapi", "uvicorn",
                "google-generativeai", "tqdm", "nest_asyncio"], check=True)
print("[deps] done", flush=True)

# ---- 0. hardware facts (is it really 2 GPUs? how many CPUs?) ----
try:
    import torch
    gpu_count = torch.cuda.device_count()
    print(f"[env] torch {torch.__version__} | CUDA GPUs={gpu_count}", flush=True)
    for i in range(gpu_count):
        print(f"[env]   GPU{i}: {torch.cuda.get_device_name(i)}", flush=True)
except Exception as e:
    gpu_count = 0
    print("[env] torch/cuda unavailable:", e, flush=True)
print(f"[env] CPU count (vCPUs): {os.cpu_count()}", flush=True)

# ---- 0b. SHOW what is actually in /kaggle/input (weights? zip? nets? pgn?) ----
print("[input] relevant files under /kaggle/input:", flush=True)
_found_any = False
for _root, _dirs, _files in os.walk("/kaggle/input"):
    # Kaggle extracts a loose .gz upload into a DIRECTORY named `X.pb` — flag those
    # too, else the weights look "missing" (their inner file has an arbitrary name).
    for _dn in _dirs:
        if _dn.endswith((".pb.gz", ".pb")):
            print(f"[input]  <DIR>      {os.path.join(_root, _dn)}  (Kaggle-extracted net?)", flush=True)
            _found_any = True
    for _fn in _files:
        if _fn.endswith((".pb.gz", ".pb", ".onnx", ".pgn", ".zip")) or _fn == "lc0":
            _p = os.path.join(_root, _fn)
            try:
                _sz = os.path.getsize(_p) / 1e6
            except OSError:
                _sz = -1
            print(f"[input]  {_sz:9.1f} MB  {_p}", flush=True)
            _found_any = True
if not _found_any:
    print("[input]  (NONE found — is the dataset attached?)", flush=True)

# ---- 1. periodic ALL-THREAD stack dumps: if it freezes, these show EXACTLY
#         what every engine loop-thread + the main task is stuck on ----
faulthandler.enable()
# NOTE: no periodic dump_traceback_later — it printed an ALL-THREAD stack dump every
# 60s (thousands of lines, looks like a crash but is benign). The heartbeat's
# hang-watchdog below dumps stacks only on a REAL stall (idle > HANG_SECONDS).

# ---- 2. shared progress state + heartbeat/GPU logger + hang watchdog ----
_last = {"t": time.time(), "stage": "init", "n": 0}
_stop = threading.Event()

def _gpu_line():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip()
        return "  ".join("GPU%s:%s%% %s/%sMiB" % tuple(r.split(", "))
                         for r in out.splitlines()) if out else "(no smi)"
    except Exception as e:
        return f"(smi err: {e})"

def _heartbeat():
    t0 = time.time()
    hung = False
    while not _stop.wait(10):
        idle = time.time() - _last["t"]
        print(f"[hb {int(time.time()-t0):5d}s] stage={_last['stage']} n={_last['n']} "
              f"idle={idle:.0f}s | {_gpu_line()}", flush=True)
        if idle > HANG_SECONDS and not hung and _last["stage"] != "init":
            hung = True
            print(f"\n[HANG] no progress {idle:.0f}s (> {HANG_SECONDS}). ALL-THREAD STACKS:\n", flush=True)
            faulthandler.dump_traceback()
            print("\n[HANG] ^ that is where it is stuck. Copy this whole block to Claude.\n", flush=True)

threading.Thread(target=_heartbeat, daemon=True).start()

# ---- 3. make the dataset's `backend` package importable (no copy needed) ----
if not (WORKING / "backend").exists():
    _bk = glob.glob("/kaggle/input/**/backend/engine_manager.py", recursive=True) or \
          glob.glob("/kaggle/input/**/diagnose_on_kaggle.py", recursive=True)
    if _bk:
        _root = Path(_bk[0]).parent
        if _root.name == "backend":
            _root = _root.parent           # .../backend/engine_manager.py -> dataset root
        sys.path.insert(0, str(_root))
        print(f"[setup] backend from dataset: {_root}", flush=True)

def _find(name):
    # Return a real FILE only. Kaggle can extract a loose .gz into a DIRECTORY of
    # the same name; handing lc0 a directory path makes it spin on "Is a directory".
    p = WORKING / "engine" / name
    if p.is_file():
        return str(p)
    for h in (glob.glob(f"/kaggle/input/**/{name}", recursive=True) +
              glob.glob(f"{WORKING}/**/{name}", recursive=True)):
        if os.path.isfile(h):
            return h
    return None

import shutil
(WORKING / "engine").mkdir(exist_ok=True)

def _lc0_runs(path):
    """True iff this lc0 binary actually executes. Guards against a cached binary
    built for a different Kaggle image (missing/changed CUDA/glibc libs) silently
    failing to start -> engine would drop to mock mode. stdin=DEVNULL so it can't
    accidentally enter (and hang in) UCI mode."""
    try:
        r = subprocess.run([str(path), "--help"], capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=30)
        return r.returncode == 0 or b"lc0" in (r.stdout + r.stderr).lower()
    except Exception:
        return False

def get_linux_lc0():
    """Find a WORKING lc0 (working dir -> dataset -> PATH), else compile it.
    Cache the compiled binary in the DATASET under engine/lc0 to skip the ~6-min
    build across sessions (/kaggle/working is wiped on Stop/Start). A cached binary
    is trusted ONLY if it actually runs; otherwise we recompile. Set
    LC0_FORCE_COMPILE=1 to always rebuild (e.g. to pick up a new lc0 version)."""
    force = os.environ.get("LC0_FORCE_COMPILE") == "1"
    lc0_bin = WORKING / "engine" / "lc0"
    if not force and lc0_bin.exists():
        os.chmod(lc0_bin, 0o755)
        if _lc0_runs(lc0_bin):
            print("[lc0] found in working dir (validated)", flush=True); return str(lc0_bin)
        print("[lc0] working-dir binary does not run — ignoring", flush=True)
    if not force:
        for cand in glob.glob("/kaggle/input/**/lc0", recursive=True):
            if os.path.isfile(cand) and not cand.endswith((".py", ".pb", ".gz", ".onnx")):
                try:
                    # Copy to the WRITABLE working dir FIRST, then chmod/validate the COPY.
                    # NEVER chmod `cand` under /kaggle/input — it is READ-ONLY, so chmod
                    # raises [Errno 30] and (previously swallowed) skipped a good binary,
                    # forcing a needless recompile. [found by Gemini log triage]
                    shutil.copy(cand, lc0_bin); os.chmod(lc0_bin, 0o755)
                    if not _lc0_runs(lc0_bin):
                        print("[lc0] dataset binary does not run — skipping:", cand, flush=True); continue
                    print("[lc0] found in dataset (validated):", cand, flush=True); return str(lc0_bin)
                except Exception as e:
                    print(f"[lc0] dataset candidate {cand} unusable: {e}", flush=True)
        sys_lc0 = shutil.which("lc0")
        if sys_lc0 and _lc0_runs(sys_lc0):
            print("[lc0] found on PATH:", sys_lc0, flush=True); return sys_lc0
    _lc0_seen = [c for c in glob.glob("/kaggle/input/**/lc0", recursive=True) if os.path.isfile(c)]
    print(f"[lc0] no usable cached binary — lc0 files in /kaggle/input: {_lc0_seen or 'NONE (versioning trap? wrong dataset version attached)'}", flush=True)
    print("[lc0] compiling from source (ninja -j1 lc0, a few min)...", flush=True)
    subprocess.run(["apt-get", "update", "-qq"], check=False)
    subprocess.run(["apt-get", "install", "-qq", "-y", "meson", "ninja-build",
                    "libz-dev", "libopenblas-dev"], check=False)
    clone_dir = WORKING / "lc0_src"
    if not clone_dir.exists():
        subprocess.run(["git", "clone", "--recursive",
                        "https://github.com/LeelaChessZero/lc0.git", str(clone_dir)], check=True)
    build_dir = clone_dir / "build" / "release"
    subprocess.run(["meson", "setup", str(build_dir), str(clone_dir)], check=True)
    # Build ONLY the lc0 target, SERIALLY (-j1). The prior `ninja -j2` (all targets)
    # OOM-killed the host (exit 137) — it was compiling gtest/gmock/encoder_test/
    # engine_test we never use, and running 2 heavy nvcc/LTO units at once. `lc0`
    # target skips the tests; -j1 halves peak compiler RAM. (Slower, but this is only
    # the fallback — the real fix is shipping a prebuilt lc0 in the dataset so we never
    # compile. See KAGGLE_BEST_PRACTICES.md §3.)
    subprocess.run(["ninja", "-C", str(build_dir), "-j1", "lc0"], check=True)
    shutil.copy(build_dir / "lc0", lc0_bin); os.chmod(lc0_bin, 0o755)
    print("[lc0] compiled ->", lc0_bin, flush=True)
    return str(lc0_bin)

# Resolve weights/nets/pgn FIRST (fail fast) — lc0 compile below is ~6 min, so
# check the cheap prerequisites before paying for it.
# NOTE: Kaggle mangles a loose `.pb.gz` upload TWO ways: (1) it DECOMPRESSES it, so
# the file arrives as raw `.pb`; (2) worse, it can extract it into a DIRECTORY named
# `X.pb` whose real network file sits inside under an arbitrary name (this is what
# made lc0 spin on "error: Is a directory"). lc0 loads a network by magic bytes, not
# extension, but it needs a FILE. Resolve to a real file, digging into a directory.
def _resolve_weight_file(name):
    cands = []
    p = WORKING / "engine" / name
    if p.exists():
        cands.append(str(p))
    cands += glob.glob(f"/kaggle/input/**/{name}", recursive=True)
    cands += glob.glob(f"{WORKING}/**/{name}", recursive=True)
    for c in cands:
        if os.path.isfile(c):
            return c
        if os.path.isdir(c):
            inner = [f for f in glob.glob(os.path.join(c, "**", "*"), recursive=True)
                     if os.path.isfile(f)]
            if inner:
                big = max(inner, key=os.path.getsize)
                print(f"[weights] '{name}' is a DIR (Kaggle-extracted) -> largest inner "
                      f"file: {big} ({os.path.getsize(big)/1e6:.1f} MB)", flush=True)
                return big
    return None

def _find_weights():
    # Order matters: net PREFERENCE dominates extension. Try BOTH forms of the
    # diagnosis net (BT3) before falling back to the live-app net (791556) — else
    # a mixed decompression state (BT3 as .pb, 791556 still .pb.gz) would silently
    # run the diagnosis on the WRONG net (LEADER_BIBLE §4). [Gemini F-03]
    for name in ("BT3-768x15x24h-swa-2790000.pb.gz", "BT3-768x15x24h-swa-2790000.pb",
                 "791556.pb.gz", "791556.pb"):
        hit = _resolve_weight_file(name)
        if hit:
            return hit
    return None

SEARCH_WEIGHTS = _find_weights()

# Kaggle does not always extract an uploaded .zip — the weights may be trapped
# inside it. If not found loose, locate a zip containing them and extract the
# engine nets to the working dir.
if not SEARCH_WEIGHTS:
    import zipfile
    _wanted = ("BT3-768x15x24h-swa-2790000.pb.gz", "BT3-768x15x24h-swa-2790000.pb",
               "791556.pb.gz", "791556.pb", "bt3.onnx")
    _zips = glob.glob("/kaggle/input/**/*.zip", recursive=True) + \
            glob.glob(f"{WORKING}/**/*.zip", recursive=True)
    print(f"[weights] no loose weights; zips found: {_zips or 'NONE'}", flush=True)
    for zpath in _zips:
        try:
            with zipfile.ZipFile(zpath) as zf:
                members = [n for n in zf.namelist()
                           if any(n.endswith(w) for w in _wanted)]
                print(f"[weights]   {zpath}: net members = {members or 'none'}", flush=True)
                if any(n.endswith((_wanted[0], _wanted[1])) for n in members):
                    print(f"[weights]   extracting nets from {zpath} ...", flush=True)
                    for n in members:
                        target = WORKING / "engine" / Path(n).name
                        with zf.open(n) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                    break
        except Exception as e:
            print("[weights]   zip probe failed:", zpath, e, flush=True)
    SEARCH_WEIGHTS = _find_weights()

assert SEARCH_WEIGHTS, (
    "LC0 WEIGHTS NOT FOUND. lc0's cuda-fp16 backend needs a network file (.pb.gz "
    "OR a decompressed .pb); without it lc0 errors 'requires a network file' and "
    "every search HANGS. NOTE: Kaggle auto-extracts loose .gz uploads, so your "
    "BT3-768x15x24h-swa-2790000.pb.gz may have landed as BT3-768x15x24h-swa-2790000.pb "
    "(this script now accepts that). If NEITHER form is present, the file didn't "
    "upload at all — add it to the dataset under engine/, bump the notebook to the "
    "new dataset version, and re-run.")
# Normalize into a clean gzipped file in the WRITABLE working dir. The resolved path
# may be under read-only /kaggle/input, or be a raw decompressed protobuf, or a file
# with an arbitrary name inside a Kaggle-extracted dir. Re-gzipping raw protobuf (or
# copying an already-gzipped net) yields an unambiguous .pb.gz lc0 loads cleanly.
# gzip-magic aware => never double-gzip a file that is already compressed.
import gzip as _gzip
def _is_gzip(path):
    with open(path, "rb") as _f:
        return _f.read(2) == b"\x1f\x8b"
_clean_w = str(WORKING / "engine" / "search_weights.pb.gz")
_src_is_gz = _is_gzip(SEARCH_WEIGHTS)
if _src_is_gz:
    shutil.copy(SEARCH_WEIGHTS, _clean_w)
else:
    with open(SEARCH_WEIGHTS, "rb") as _s, _gzip.open(_clean_w, "wb") as _d:
        shutil.copyfileobj(_s, _d)
print(f"[weights] resolved {SEARCH_WEIGHTS} (gzip={_src_is_gz}) -> normalized "
      f"{_clean_w} ({os.path.getsize(_clean_w)/1e6:.1f} MB)", flush=True)
SEARCH_WEIGHTS = _clean_w
print(f"[weights] using: {SEARCH_WEIGHTS}", flush=True)
ONNX = _find("bt3.onnx")
# F-01: the backend is imported FROM the dataset, and its neural_vision.py writes a
# temp shape-inference file NEXT TO the onnx. On the read-only /kaggle/input mount
# that throws Errno 30 and silently drops us to policy_fallback (zeroing attention
# findings). Copy the onnx to the WRITABLE working dir so its parent is writable —
# this restores attention mode even against the OLD dataset code (no rebuild needed).
if ONNX and ONNX.startswith("/kaggle/input"):
    _onnx_local = str(WORKING / "engine" / "bt3.onnx")
    if not os.path.exists(_onnx_local):
        print(f"[setup] copying onnx to writable dir -> {_onnx_local}", flush=True)
        shutil.copy(ONNX, _onnx_local)
    ONNX = _onnx_local
pgn_hits = glob.glob("/kaggle/input/**/lichess_derdiedasdie_2026-07-21.pgn", recursive=True) or \
           glob.glob(f"{WORKING}/**/lichess_derdiedasdie_2026-07-21.pgn", recursive=True)
assert pgn_hits, "PGN not found"

# Only now (weights + pgn confirmed) do the expensive lc0 build/find (~6 min).
LC0_BIN = get_linux_lc0()
assert LC0_BIN, "lc0 binary could not be found or built"
PGN = pgn_hits[0]
print(f"[setup] lc0={LC0_BIN}", flush=True)
print(f"[setup] weights={SEARCH_WEIGHTS}", flush=True)
print(f"[setup] onnx={ONNX}", flush=True)
print(f"[setup] pgn={PGN}", flush=True)

# ---- 4. build engine (SMALL pool) + vision ----
from backend.engine_manager import LC0Engine
from backend.engine_pool import EnginePool
from backend.neural_vision import NeuralVision
from backend.training import pipeline

# F-06 GPU-split fix: EnginePool calls _factory() once per worker (zero-arg
# contract, unchanged — so no signature drift / test breakage). A stateful counter
# assigns each worker its own GPU round-robin via lc0's BackendOptions="gpu=N", so a
# 2-worker pool lights up BOTH T4s instead of piling onto GPU0. n=1 -> worker 0 ->
# gpu 0, byte-identical to before.
def _factory():
    # GPU pinning happens at START time via CUDA_VISIBLE_DEVICES (see _start_engines),
    # NOT here: the backend is imported from the (possibly STALE) dataset, whose
    # LC0Engine may not accept a gpu_id kwarg — passing one raised
    # "TypeError: unexpected keyword argument 'gpu_id'". The env approach works with
    # ANY backend version. Backend (cuda-fp16) comes from the LC0_BACKEND env.
    return LC0Engine(LC0_BIN, SEARCH_WEIGHTS)

engine = EnginePool(LC0_WORKERS, _factory) if LC0_WORKERS > 1 else _factory()
if gpu_count:
    try:
        torch.set_default_device("cuda")
    except Exception as e:
        print("[setup] set_default_device warn:", e, flush=True)
vision = NeuralVision(onnx_path=ONNX)
print(f"[setup] vision.mode={vision.mode}", flush=True)

# ---- 5. select N games + tap _progress so the heartbeat sees liveness ----
raw = open(PGN, encoding="utf-8").read()
parts = raw.split("\n[Event ")
allg = [parts[0]] + ["[Event " + p for p in parts[1:]]
mine = [g for g in allg if "derdiedasdie" in g.lower()][:MAX_GAMES]
pgn_text = "\n\n".join(mine)
print(f"[setup] running {len(mine)} games", flush=True)

# IDEMPOTENT patch: re-running this cell WITHOUT a kernel restart must not double-wrap
# _progress. Previously `_orig_progress = pipeline._progress` captured the ALREADY-patched
# _tap on a second run, so _tap called itself -> RecursionError. Unwrap to the real original.
_orig_progress = getattr(pipeline._progress, "_kaggle_orig", pipeline._progress)
def _tap(job_id, **kw):
    _last["t"] = time.time()
    if kw.get("stage_steer_done") is not None:
        _last["stage"], _last["n"] = "TS2", kw["stage_steer_done"]
    elif kw.get("stage_b_done") is not None:
        _last["stage"], _last["n"] = "B", kw["stage_b_done"]
    elif kw.get("stage_a_done") is not None:
        _last["stage"], _last["n"] = "A", kw["stage_a_done"]
    return _orig_progress(job_id, **kw)
_tap._kaggle_orig = _orig_progress
pipeline._progress = _tap

# ---- 6. run under asyncio with clean start/stop ----
import asyncio
async def _start_engines():
    # Pin each pool worker to its own physical GPU via CUDA_VISIBLE_DEVICES, set in the
    # parent env right before THAT worker's subprocess spawns. SERIAL (not gather) so the
    # per-worker env can't race. Backend-version-agnostic: does NOT rely on the dataset's
    # LC0Engine supporting gpu_id. Child procs inherit the env at spawn; restoring it
    # afterward doesn't affect them or the parent's already-initialized torch vision (GPU0).
    if isinstance(engine, EnginePool):
        _saved = os.environ.get("CUDA_VISIBLE_DEVICES")
        for i, w in enumerate(engine._workers):
            g = i % max(gpu_count, 1)
            os.environ["CUDA_VISIBLE_DEVICES"] = str(g)
            print(f"[pool] starting worker {i} -> GPU {g} (CUDA_VISIBLE_DEVICES={g})", flush=True)
            await w.start()
        if _saved is None:
            os.environ.pop("CUDA_VISIBLE_DEVICES", None)
        else:
            os.environ["CUDA_VISIBLE_DEVICES"] = _saved
    elif hasattr(engine, "start"):
        await engine.start()

async def _main():
    await _start_engines()
    t0 = time.time()
    # Remove any STALE profile.json before the run. run_diagnosis swallows exceptions, so
    # if it crashes, the honest-done check would otherwise read a PREVIOUS run's profile and
    # falsely report success (e.g. a 2-game smoke's numbers on a 100-game run). Deleting it
    # first means a crash => no profile => the assert below fires loudly.
    from backend.training import store as _store0
    _pp0 = os.path.join(_store0.TRAINING_DIR, "profile.json")
    try:
        if os.path.exists(_pp0):
            os.remove(_pp0)
    except OSError:
        pass
    try:
        await pipeline.run_diagnosis("kaggle_diag", pgn_text, "derdiedasdie", engine, vision)
        # run_diagnosis SWALLOWS exceptions internally (pipeline.py:705) and the
        # "kaggle_diag" job is never create_job()'d, so update_job no-ops — a crash
        # would otherwise be disguised as a clean [DONE] in 0s. Prove a real profile
        # with findings was actually written before claiming success. [Gemini F-02]
        import json as _json
        from backend.training import store as _store
        _pp = os.path.join(_store.TRAINING_DIR, "profile.json")
        assert os.path.exists(_pp), (
            "NO profile.json written — run_diagnosis crashed internally and swallowed "
            "the exception (see traceback above). This is NOT a successful run.")
        _prof = _json.load(open(_pp, encoding="utf-8"))
        _nf = len(_prof.get("findings", []))
        _ns = len(_prof.get("steer_findings", []))
        assert _nf > 0, "profile has ZERO findings — diagnosis did not truly analyze."
        _ga = _prof.get("games_analyzed")
        assert _ga == len(mine), (
            f"profile games_analyzed={_ga} != requested {len(mine)} — this profile is STALE "
            "or the run was truncated; not a clean full run.")
        print(f"\n[DONE] REAL run: {_nf} findings, {_ns} steer_findings | vision={vision.mode} "
              f"| games={_prof.get('games_analyzed')} moves={_prof.get('moves_analyzed')} "
              f"| {time.time()-t0:.0f}s", flush=True)
    finally:
        if hasattr(engine, "stop"):
            await engine.stop()
        _stop.set()
        faulthandler.cancel_dump_traceback_later()

try:
    import nest_asyncio; nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(_main())
except RuntimeError:
    asyncio.run(_main())
