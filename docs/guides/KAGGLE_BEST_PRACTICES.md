# Kaggle Best Practices & Diagnostic Reference Manual

**Document Status**: Durable Project Reference  
**Target Execution Environment**: Kaggle T4×2 GPU Notebook Instance  
**Primary Workload**: AI Chess Engine Diagnostic (`colab/kaggle_diagnostic_run.py`) — `lc0` C++ CUDA binary engine + PyTorch/ONNX Neural Vision attention model  

---

## Executive Summary & Failure History Mapping

This document establishes the definitive best practices for running high-performance C++ CUDA executables (`lc0`) alongside deep neural network evaluation pipelines (PyTorch / ONNX) on Kaggle GPU instances.

### Resolved Failures & Direct Mitigations

| # | Specific Failure Mode | Root Cause | Named Mitigation | Document Section |
|---|---|---|---|---|
| **1** | `Exit 137` (OOM-killed) during `lc0` compile | Host RAM exhaustion during parallel `meson` + `ninja -j2` compilation (compiling `gtest`, CUDA fp16 kernels, LTO) | Prebuilt binary deployment inside `.zip` dataset archive; single-target `ninja -j1 lc0` fallback | [Section 3](#3-the-lc0-compile-oom-specifically--ranked-solutions) & [Section 4](#4-persisting-compiled-binaries--navigating-dataset-versioning) |
| **2** | `Exit 137` / VRAM pressure with 2 engines | Both `lc0` instances defaulted to GPU 0, exceeding 15.3 GiB VRAM capacity and failing CUDA graph capture | Explicit per-process GPU pinning via `CUDA_VISIBLE_DEVICES` (GPU 0 & GPU 1 isolation) | [Section 6](#6-runtime-memory-budgeting-for-2-lc0-engines--pytorch-on-t42) |
| **3** | `/kaggle/working` wiped on Stop→Start | Session reset empties working directory, triggering 6-minute recompiles | Storing compiled assets in Kaggle Datasets mounted at `/kaggle/input` | [Section 4](#4-persisting-compiled-binaries--navigating-dataset-versioning) |
| **4** | Dataset auto-extraction mangled uploads | Single `.pb.gz` file auto-decompressed into a directory named `X.pb/`, breaking engine path resolution | Wrapping all binaries and weights in a `.zip` archive before upload | [Section 5](#5-uploading-binaries--compressed-nets-without-mangling) |
| **5** | Dataset versioning trap | Notebook remained pinned to an old dataset version; uploaded `lc0` binary stayed invisible | Explicit Dataset Version update/pinning via Kaggle Data panel | [Section 4](#4-persisting-compiled-binaries--navigating-dataset-versioning) |
| **6** | `files.download` hangs indefinitely | `google.colab.files.download` is proprietary to Colab and non-functional on Kaggle | Notebook Output tab retrieval, Kaggle CLI output download, or base64 stdout encoding | [Section 7](#7-reliable-output-retrieval-alternatives) |

---

## 1. Resource Limits (T4×2 Instance Specifications & In-Notebook Verification)

The table below outlines Kaggle GPU instance specifications. Limits marked **CITED** originate from official Kaggle documentation. Limits marked **NEEDS-VERIFY** reflect environment-dependent settings that must be checked using the provided in-notebook verification commands.

| Resource Metric | Stated Limit / Value | Status | In-Notebook Verification Command |
|---|---|---|---|
| **Host System RAM** | ~13 GB to 29 GB (Environment dependent) | **NEEDS-VERIFY** | `!free -h` <br> *or Python:* `import psutil; print(f"{psutil.virtual_memory().total / 1e9:.2f} GB")` |
| **GPU Hardware** | 2 × NVIDIA Tesla T4 | **CITED** | `!nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv` |
| **VRAM per GPU** | 15.3 GiB (16,160 MiB per GPU) | **NEEDS-VERIFY** | `!nvidia-smi` |
| **vCPU Cores** | 4 vCPU Cores | **CITED** | `import os; print(os.cpu_count())` <br> *or:* `!lscpu | grep "CPU(s):"` |
| **`/kaggle/working` Disk** | ~5 GB persistent / ~20 GB working space | **NEEDS-VERIFY** | `!df -h /kaggle/working` |
| **`/kaggle/temp` Disk** | ~16 GB temporary scratchpad | **NEEDS-VERIFY** | `!df -h /kaggle/temp` |
| **Session Wall-Clock Limit** | 12 hours (Interactive) / 9 hours (Batch Commit) | **CITED** | Checked via Kaggle Notebook Session Timer |
| **Idle Timeout** | 60 minutes (Interactive GPU session) | **CITED** | Checked via Kaggle Notebook Settings |
| **Weekly GPU Quota** | 30 hours per week | **CITED** | Checked via Kaggle Profile / Account Settings |

---

## 2. Exit 137 & Memory OOM — Diagnosis & Live Monitoring

`Exit 137` indicates process termination via `SIGKILL` (Signal 9). On Kaggle, this typically stems from the Linux Kernel Out-Of-Memory (OOM) Killer.

### 2.1 Distinguishing Host-RAM OOM vs. GPU-VRAM OOM

```
                      ┌────────────────────────────────────────┐
                      │    Process Crashes or Terminates       │
                      └───────────────────┬────────────────────┘
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
    [Host-RAM OOM (Kernel Kill)]                     [GPU-VRAM OOM (CUDA Error)]
  - Process exits instantly (Exit code 137)        - Python exception raised
  - Silent crash in shell / Ninja build            - RuntimeError: CUDA out of memory
  - No Python traceback                            - "Not enough GPU memory to capture CUDA graphs"
  - Kernel log entry in dmesg                      - Process may remain alive until unhandled
```

* **Host-RAM OOM (Kernel Kill)**: The OS kernel forcefully kills the process because total host RAM consumption exceeds available physical memory and swap. Ninja build jobs, compiler linkers, or engine RAM caches crossing 13–29 GB trigger this.
* **GPU-VRAM OOM (CUDA Error)**: Occurs when PyTorch, ONNX, or `lc0` requests VRAM exceeding 15.3 GiB on a single T4 card. PyTorch throws `torch.cuda.OutOfMemoryError` or `lc0` logs CUDA graph capture failures.

### 2.2 In-Notebook Diagnostics & Live Monitoring

#### Check Kernel Logs for OOM Kills
```bash
!dmesg -T | grep -i -E "oom|killed process" | tail -n 20
```

#### Background Host-RAM Monitoring Thread (Python)
Include this snippet prior to running memory-intensive workloads to log live RAM utilization:

```python
import psutil
import time
import threading

def start_ram_monitor(interval_sec: int = 5, warn_threshold_pct: float = 85.0):
    def _monitor():
        while True:
            mem = psutil.virtual_memory()
            if mem.percent >= warn_threshold_pct:
                print(f"⚠️ [RAM MONITOR WARNING] Host RAM at {mem.percent}% "
                      f"({mem.used / 1e9:.2f} / {mem.total / 1e9:.2f} GB)")
            time.sleep(interval_sec)
    
    thread = threading.Thread(target=_monitor, daemon=True)
    thread.start()
    print("✅ Live Host-RAM monitoring thread started.")

start_ram_monitor(interval_sec=3, warn_threshold_pct=80.0)
```

---

## 3. The `lc0` Compile-OOM Specifically — Ranked Solutions

Building `lc0` from source via `meson` + `ninja -j2` invokes concurrent `nvcc` and `g++` compilation units. This process builds `gtest`, `gmock`, `encoder_test`, `engine_test`, CUDA fp16 kernels, and performs Link-Time Optimization (LTO), quickly exceeding host RAM limits.

Below are the ranked solutions to eliminate compile-time OOMs:

```
Rank 1 (Best): Ship Prebuilt Binary in Dataset  ─────► ZERO compile time, ZERO host RAM compile risk
Rank 2: Target Single Binary (`ninja lc0`)      ─────► Skips gtest, gmock, encoder_test, engine_test
Rank 3: Restrict Parallelism (`ninja -j1`)       ─────► Halves concurrent nvcc/g++ RAM overhead
Rank 4: Disable LTO & Tests in Meson             ─────► Eliminates high-RAM link step (-Db_lto=false)
Rank 5: Restrict NVCC Arch to `sm_75`           ─────► Avoids compiling CUDA kernels for unused architectures
Rank 6: Enable `ccache`                         ─────► Caches object files across scratch builds
```

### Concrete Commands for Compile Solutions

#### Solution 1 (RANK 1 — BEST): Avoid Compilation Entirely
Ship prebuilt Linux `lc0` compiled for NVIDIA T4 (`sm_75`) in a Kaggle Dataset. See [Section 4](#4-persisting-compiled-binaries--navigating-dataset-versioning).

#### Solution 2: Build ONLY the `lc0` Binary Target
Do NOT run bare `ninja`. Specify the `lc0` target to prevent building test suites:
```bash
ninja -C build lc0
```

#### Solution 3: Limit Compilation Parallelism to 1 Job
Force Ninja to execute sequentially (`-j1`), keeping peak compiler RAM usage below ~3.5 GB:
```bash
ninja -C build -j1 lc0
```

#### Solution 4: Disable LTO & Test Suites via Meson Setup
Configure Meson without Link-Time Optimization and without unit test targets:
```bash
meson setup build --buildtype=release -Dbuild_tests=false -Db_lto=false
```

#### Solution 5: Restrict CUDA Compute Architecture to `sm_75`
Pass architecture flags so `nvcc` builds exclusively for the T4 GPU (`compute_75,sm_75`):
```bash
meson setup build --buildtype=release -Dbuild_tests=false -Db_lto=false -Dcc_archs=sm_75
```

---

## 4. Persisting Compiled Binaries & Navigating Dataset Versioning

### 4.1 How `/kaggle/working` Reset Works
When a Kaggle notebook session is stopped or restarted, the `/kaggle/working` directory is completely reset. Any compiled binary, cloned repository, or temporary build artifact stored in `/kaggle/working` is permanently erased.

### 4.2 The Kaggle Dataset Versioning Trap (Failure #5)
When you upload a new version to an existing Kaggle Dataset via the UI or API, **existing Kaggle Notebooks attached to that dataset DO NOT automatically update to the latest version**. The notebook remains pinned to the specific immutable version attached at session creation.

### 4.3 Step-by-Step Dataset Creation & Version Pinning Procedure

#### Step 1: Create Local Dataset Directory
Organize the prebuilt `lc0` binary and neural network weights inside a local folder:
```bash
mkdir -p ./kaggle_lc0_dataset
cp lc0 ./kaggle_lc0_dataset/
cp BT3-768x15x24h-swa-2790000.pb.gz ./kaggle_lc0_dataset/
cp bt3.onnx ./kaggle_lc0_dataset/
```

#### Step 2: Initialize & Push Dataset via Kaggle API
```bash
# Generate metadata file
kaggle datasets init -p ./kaggle_lc0_dataset

# Edit ./kaggle_lc0_dataset/dataset-metadata.json:
# {
#   "title": "CSZero Prebuilt Engine & Nets",
#   "id": "yourusername/cszero-prebuilt-engine-nets",
#   "licenses": [{"name": "CC0-1.0"}]
# }

# Upload dataset
kaggle datasets create -p ./kaggle_lc0_dataset --public
```

#### Step 3: Updating Existing Datasets
```bash
kaggle datasets version -p ./kaggle_lc0_dataset -m "Update lc0 binary compiled for sm_75"
```

#### Step 4: Updating Version Pinning inside the Notebook UI
1. Open the Kaggle Notebook editor.
2. In the right-hand panel, expand the **Data** tab.
3. Locate the attached dataset (`cszero-prebuilt-engine-nets`).
4. Click the **three vertical dots (...)** or **refresh icon** next to the dataset.
5. Select **"Update dataset version"** and choose **"Always use latest version"** (or explicitly select the latest version number).

```python
# In-notebook assertion to confirm binary visibility
import os

dataset_path = "/kaggle/input/cszero-prebuilt-engine-nets"
assert os.path.exists(dataset_path), f"Dataset path {dataset_path} missing!"
print("Attached files:", os.listdir(dataset_path))
```

---

## 5. Uploading Binaries & Compressed Nets WITHOUT Mangling

### 5.1 Kaggle Auto-Extraction Behavior (Failure #4)
Kaggle's dataset ingestion backend automatically decompresses single standalone `.gz` files upon upload. 

* **The Problem**: Uploading `BT3-768x15x24h-swa-2790000.pb.gz` directly causes Kaggle to decompress it into a **directory** named `BT3-768x15x24h-swa-2790000.pb/` containing an extracted file under a modified filename. When `lc0` is passed this path, it attempts to open a directory as a file and hangs or crashes with `"Is a directory"`.
* **Binary Execution Bit Loss**: Extensionless Linux binaries uploaded raw can lose execution permissions (`chmod +x` bit reset).

### 5.2 Proven Solution: Package Assets in a `.zip` Archive
Wrapping files inside a multi-file `.zip` archive bypasses Kaggle's single-file auto-decompression pipeline.

#### Local Packaging Command
```bash
zip -9 chess_engine_assets.zip lc0 BT3-768x15x24h-swa-2790000.pb.gz bt3.onnx
```

#### In-Notebook Clean Extraction Code
```python
import zipfile
import os
import stat

zip_input_path = "/kaggle/input/cszero-prebuilt-engine-nets/chess_engine_assets.zip"
target_dir = "/kaggle/working/engine"

os.makedirs(target_dir, exist_ok=True)

if os.path.exists(zip_input_path):
    with zipfile.ZipFile(zip_input_path, 'r') as zip_ref:
        zip_ref.extractall(target_dir)
    
    # Restore executable permission on lc0 binary
    lc0_bin = os.path.join(target_dir, "lc0")
    if os.path.exists(lc0_bin):
        st = os.stat(lc0_bin)
        os.chmod(lc0_bin, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print(f"✅ Extracted lc0 binary to {lc0_bin} and granted execution permissions.")
else:
    raise FileNotFoundError(f"Archive missing at {zip_input_path}")
```

---

## 6. Runtime Memory Budgeting for 2 `lc0` Engines + PyTorch on T4×2

Running a multi-engine diagnostic pool requires partitioning host RAM, vCPUs, and GPUs across processes.

### 6.1 Host RAM Budgeting
By default, `lc0` allocates **8192 MB (8 GB)** for its neural network node cache (`RamLimitMb`). Launching 2 `lc0` engines with default settings requires `2 × 8 GB = 16 GB` RAM. Combined with PyTorch/ONNX allocations (~3 GB) and Python system overhead (~2.5 GB), host RAM reaches ~21.5 GB, triggering a Host-RAM OOM Kill (`Exit 137`) on 13 GB host instances.

#### Solution
Set `LC0_RAM_LIMIT_MB` to **2048 MB (2 GB)** per engine instance.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Kaggle Host RAM (13 GB Cap)                     │
├──────────────┬──────────────┬────────────────────────┬─────────────────┤
│ LC0 Engine 0 │ LC0 Engine 1 │ PyTorch + ONNX Model   │ OS / Python     │
│   (2.0 GB)   │   (2.0 GB)   │        (3.0 GB)        │   (2.5 GB)      │
└──────────────┴──────────────┴────────────────────────┴─────────────────┘
 Total Footprint: ~9.5 GB (Safe within 13 GB ceiling)
```

### 6.2 vCPU & Threading Allocation (4 Cores Total)
To prevent CPU context-switching overhead:
* **Engine 0**: UCI option `Threads = 1` (or 2)
* **Engine 1**: UCI option `Threads = 1` (or 2)
* **PyTorch CPU Threads**: `torch.set_num_threads(2)`

### 6.3 GPU Pinning & VRAM Allocation (Failure #2)
Kaggle T4×2 presents two GPUs: GPU 0 and GPU 1 (15.3 GiB VRAM each). If two `lc0` sub-processes launch without explicit GPU pinning, both default to GPU 0. VRAM utilization on GPU 0 reaches ~14.8/15.3 GiB, triggering `"Not enough GPU memory to capture CUDA graphs"`.

#### Python Subprocess Isolation Pattern
Explicitly assign each engine worker to a separate GPU using `CUDA_VISIBLE_DEVICES`:

```python
import os
import subprocess

def launch_pinned_lc0_engine(gpu_id: int, binary_path: str, weights_path: str, ram_limit_mb: int = 2048):
    # Copy current environment and set CUDA_VISIBLE_DEVICES
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    
    # Under CUDA_VISIBLE_DEVICES=gpu_id, the process sees only 1 GPU (as CUDA device 0)
    cmd = [
        binary_path,
        f"--weights={weights_path}",
        f"--backend-opts=gpu=0"
    ]
    
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )
    
    # Configure UCI options via STDIN
    uci_commands = f"""
uci
setoption name RamLimitMb value {ram_limit_mb}
setoption name Threads value 1
isready
"""
    process.stdin.write(uci_commands)
    process.stdin.flush()
    
    print(f"✅ Launched LC0 Engine worker on physical GPU {gpu_id} (PID {process.pid})")
    return process

# Launch Engine 0 on physical GPU 0, Engine 1 on physical GPU 1
engine_0 = launch_pinned_lc0_engine(gpu_id=0, binary_path="/kaggle/working/engine/lc0", weights_path="/kaggle/working/engine/BT3-768x15x24h-swa-2790000.pb.gz")
engine_1 = launch_pinned_lc0_engine(gpu_id=1, binary_path="/kaggle/working/engine/lc0", weights_path="/kaggle/working/engine/BT3-768x15x24h-swa-2790000.pb.gz")
```

---

## 7. Reliable Output Retrieval Alternatives

### 7.1 Why `files.download` Fails on Kaggle (Failure #6)
`google.colab.files.download` depends on Google Colab's custom browser frontend communication layer. Calling this function inside Kaggle raises an `ImportError` or hangs the cell indefinitely.

### 7.2 Approved Output Retrieval Methods

#### Method 1: Notebook "Save Version" Output Tab (Recommended)
1. Write all output artifacts (`profile.json`, `attempts.jsonl`, logs) to `/kaggle/working/data/training/`.
2. Click **Save Version** -> Select **Save & Run All (Commit)**.
3. Once complete, open the notebook page -> Navigate to the **Output** section.
4. Download the files or entire output directory directly via the Kaggle web UI.

#### Method 2: Kaggle CLI Output Download
Retrieve outputs remotely using the Kaggle CLI:
```bash
kaggle notebooks output <username>/<notebook-slug> -p ./downloaded_outputs/
```

#### Method 3: Output Dataset Upload via Kaggle API
Push output files to a dedicated output dataset at the completion of a script run:
```bash
kaggle datasets version -p /kaggle/working/data/training -m "Diagnostic run outputs"
```

#### Method 4: Base64 Stdout Printing (Instant Inline Retrieval)
For small JSON/log files, encode the content in Base64 and print it directly to cell output for copying:

```python
import base64

def print_file_base64(filepath: str):
    if os.path.exists(filepath):
        with open(filepath, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        print(f"=== BEGIN {os.path.basename(filepath)} BASE64 ===")
        print(encoded)
        print(f"=== END {os.path.basename(filepath)} BASE64 ===")
    else:
        print(f"File {filepath} not found.")

# Usage
print_file_base64("/kaggle/working/data/training/profile.json")
```

*Local Decoding*: `echo "<BASE64_STRING>" | base64 -d > profile.json`

---

## 8. Session & GPU-Quota Hygiene

### 8.1 Quota Optimization Rules
* **Avoid On-Demand Compiles**: Compiling `lc0` on every session start wastes 6–10 minutes of GPU quota per run. Always use prebuilt binary datasets.
* **Manually Stop Interactive Sessions**: Closing the browser tab does **NOT** terminate an interactive session. It will remain active for 60 minutes, consuming 1 hour of weekly GPU quota. Always click **Stop Session** in the notebook UI when work is finished.

### 8.2 Execution Mode Trade-Offs

| Execution Mode | Max Wall-Clock | Idle Timeout | Recommended Use Case |
|---|---|---|---|
| **Interactive Mode** | 12 Hours | 60 Minutes | Code development, rapid debugging, step-by-step verification |
| **Save & Run All (Batch)** | 9 Hours | None | Full 30-game diagnostic runs, multi-hour MCTS evaluations |

### 8.3 Required Kernel Restarts
Restart the Python kernel (**Kernel → Restart**) when:
1. PyTorch throws `torch.cuda.OutOfMemoryError` (to clear fragmented CUDA memory pools).
2. CUDA driver returns `CUDA initialization error` or deadlock state.
3. `/kaggle/working` disk space is exhausted.

---

## 9. Recommended Setup Checklist for THIS Project

Follow this checklist to configure and launch `colab/kaggle_diagnostic_run.py` without encountering compile OOMs, path errors, or GPU allocation failures.

### Phase 1: Local Dataset Preparation (One-Time Setup)
- [ ] Compile `lc0` locally or in a setup kernel for `sm_75` (NVIDIA T4).
- [ ] Assemble `lc0`, `BT3-768x15x24h-swa-2790000.pb.gz`, and `bt3.onnx` into `chess_engine_assets.zip`.
- [ ] Create/Update Kaggle Dataset `cszero-prebuilt-engine-nets` using Kaggle API or Web UI.

### Phase 2: Notebook Configuration
- [ ] Set Notebook Accelerator to **GPU T4×2**.
- [ ] Attach dataset `cszero-prebuilt-engine-nets`.
- [ ] Verify Dataset Version Pinning in Data tab: Select **"Always use latest version"**.

### Phase 3: Notebook Execution Sequence

#### Cell 1: Hardware & Dataset Verification
```bash
!nvidia-smi
!free -h
!ls -la /kaggle/input/cszero-prebuilt-engine-nets/
```

#### Cell 2: Environment Variable Configuration
```python
import os

# Limit per-engine RAM to 2 GB (prevents Host OOM Exit 137)
os.environ["LC0_RAM_LIMIT_MB"] = "2048"

# Enable 2 engine workers on 2 separate GPUs
os.environ["LC0_WORKERS"] = "2"

# Direct all data outputs to writable working directory
os.environ["CSZERO_DATA_DIR"] = "/kaggle/working/data"

print("✅ Environment variables configured.")
```

#### Cell 3: Asset Extraction & Permissions
```python
import zipfile
import os
import stat

zip_path = "/kaggle/input/cszero-prebuilt-engine-nets/chess_engine_assets.zip"
target_dir = "/kaggle/working/engine"
os.makedirs(target_dir, exist_ok=True)

with zipfile.ZipFile(zip_path, "r") as z:
    z.extractall(target_dir)

lc0_path = os.path.join(target_dir, "lc0")
st = os.stat(lc0_path)
os.chmod(lc0_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

print("✅ Extracted assets clean:")
print(os.listdir(target_dir))
```

#### Cell 4: Execute Diagnostic Suite
```python
# Execute diagnostic run script
!python colab/kaggle_diagnostic_run.py
```

#### Cell 5: Inspect / Retrieve Results
```python
# Verify profile output file exists
import os
profile_path = "/kaggle/working/data/training/profile.json"
assert os.path.exists(profile_path), f"Missing output profile at {profile_path}"
print(f"✅ Diagnostic run complete. Output size: {os.path.getsize(profile_path)} bytes.")
```
