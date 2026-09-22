# GPU / BACKEND DIAGNOSIS — paste this whole block into a NEW Colab cell and run
# it AFTER cell 6 finishes (needs LC0_BIN, and engine/vision from cell 5).
import subprocess, time
WEIGHTS = "/content/repo/engine/791556.pb.gz"


def _gpu():
    return subprocess.run(
        ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
         "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()


def _show(raw, keys):
    for ln in raw.splitlines():
        if any(k in ln.lower() for k in keys):
            print("   ", ln.strip())


print("GPU idle baseline:", _gpu())

print("\n[A] lc0 benchmark — AUTO backend (what the app engine uses):")
r = subprocess.run([LC0_BIN, "benchmark", f"--weights={WEIGHTS}", "--num-positions=2"],
                   capture_output=True, text=True)
_show(r.stderr + r.stdout,
      ("creating backend", "backend:", "nps", "nodes/s", "cuda", "blas", "eigen", "error"))

print("\n[B] lc0 benchmark — FORCED --backend=cuda-fp16 (try 'cuda' if this errors):")
r2 = subprocess.run([LC0_BIN, "benchmark", f"--weights={WEIGHTS}",
                     "--backend=cuda-fp16", "--num-positions=2"],
                    capture_output=True, text=True)
_show(r2.stderr + r2.stdout,
      ("creating backend", "backend:", "nps", "nodes/s", "cuda", "error"))

print("\n[C] App engine (from cell 5) — is the net on the GPU + how fast is a real search?")
if "engine" in globals() and engine.is_available():
    print("   GPU with engine loaded:", _gpu(), " <- non-zero MiB = net is ON the GPU")
    t = time.time()
    res = await engine.analyze("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                               depth=None, multipv=2, time_limit=2.0)
    print(f"   analyze(2.0s) -> {time.time()-t:.2f}s wall, eval={res.get('evaluation')}")
    print("   GPU right after analyze:", _gpu())
else:
    print("   engine not built — run cell 5 first, then re-run this.")

print("\n[D] BT3 saliency (NeuralVision):")
if "vision" in globals():
    print("   vision.mode:", vision.mode, "(want 'attention')")
    t = time.time()
    s = vision.saliency_absolute("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    print(f"   saliency -> {time.time()-t:.2f}s / {len(s)} squares  (GPU: <0.1s, CPU: ~1-1.5s)")
else:
    print("   vision not built — run cell 5 first.")
print("\nGPU final:", _gpu())
