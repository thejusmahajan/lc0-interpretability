# =====================================================================
#  BACKEND PROBE — paste into a Colab cell and run (needs LC0_BIN).
#  lc0 benchmarked at ~16k nps = it is on CPU. This finds out WHY and
#  whether forcing cuda-fp16 fixes it. Runs in ~15s. Paste output back.
# =====================================================================
import subprocess
WEIGHTS = "/content/repo/engine/791556.pb.gz"


def sh(cmd):
    return subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True).stdout


print("=== runtime CUDA libs visible to the loader? ===")
libs = sh("ldconfig -p | grep -Ei 'cudnn|cublas|cudart' | head -n 8")
print(libs or "  (NONE found via ldconfig — this is why cuda backend won't load)")


def bench(label, extra):
    r = subprocess.run(
        [LC0_BIN, "benchmark", f"--weights={WEIGHTS}", "--num-positions=1", "--movetime=3000"] + extra,
        capture_output=True, text=True)
    out = (r.stdout + r.stderr).splitlines()
    backend = [l for l in out if "creating backend" in l.lower() or "selected backend" in l.lower()]
    nps = [l for l in out if "nodes/second" in l.lower()]
    err = [l for l in out if any(k in l.lower() for k in ("error", "exception", "not found", "failed", "assert"))]
    print(f"\n=== {label} ===")
    print("  backend:", backend[-1].strip() if backend else "(no backend line printed)")
    print("  nps    :", nps[-1].strip() if nps else "(no nps line)")
    if err:
        print("  ERR    :", err[0].strip()[:160])


bench("AUTO (what the app currently gets)", [])
bench("FORCED cuda-fp16", ["--backend=cuda-fp16"])
bench("FORCED cuda", ["--backend=cuda"])
print("\nDONE — paste the whole output.")
