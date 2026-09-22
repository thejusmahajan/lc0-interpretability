# =====================================================================
#  NET PROBE — does lc0 run the strong BT3 net, and how fast on the A100?
#  Paste into a Colab cell after Cell 4 (needs LC0_BIN). Benchmarks the small
#  current net vs the strong BT3 transformer, both on cuda-fp16.
#  Requires BT3-768x15x24h-swa-2790000.pb.gz uploaded to Drive + copied to
#  /content/repo/engine/ (add it next to the 791556 copy in Cell 5).
# =====================================================================
import subprocess, os

NETS = {
    "791556 (small SE-ResNet, current)": "/content/repo/engine/791556.pb.gz",
    "BT3-768x15x24h (strong transformer)": "/content/repo/engine/BT3-768x15x24h-swa-2790000.pb.gz",
}


def bench(label, weights):
    print(f"\n=== {label} ===")
    if not os.path.exists(weights):
        print("  MISSING:", weights, "(upload it to Drive + copy into engine/)")
        return
    r = subprocess.run(
        [LC0_BIN, "benchmark", f"--weights={weights}", "--backend=cuda-fp16",
         "--num-positions=3", "--movetime=5000"],
        capture_output=True, text=True)
    out = (r.stdout + r.stderr).splitlines()
    nps = [l for l in out if "nodes/second" in l.lower()]
    backend = [l for l in out if "creating backend" in l.lower()]
    err = [l for l in out if any(k in l.lower() for k in
           ("error", "not supported", "unknown", "exception", "failed", "invalid"))]
    print("  backend:", backend[-1].strip() if backend else "(none)")
    print("  nps    :", nps[-1].strip() if nps else "(no nps line)")
    if err:
        print("  ERR    :", err[0].strip()[:180])


for label, path in NETS.items():
    bench(label, path)
print("\nDONE — paste the whole output. Big net = fewer nps but far stronger eval.")
