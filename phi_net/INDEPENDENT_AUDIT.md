# Independent Audit — `phi_net` Kaggle Readiness

**Auditor:** Gemini (independent clean-room audit)  
**Date:** 2026-09-02  
**Commit Audited:** `83a7500` ("phi_net: pre-flight self-review -- 12 defects found and fixed before Kaggle")  
**Verdict:** **ACTION REQUIRED BEFORE KAGGLE RUN.**  
Full report registered at [`agents/reports/2026-09-02_phi-net-kaggle-training_AUDIT.md`](file:///c:/Users/Admin/Documents/chess_speak_out_loud/agents/reports/2026-09-02_phi-net-kaggle-training_AUDIT.md).

---

## Summary of Findings

Claude's self-review in commit `83a7500` caught several real defects (notably the $O(N)$ CUDA device-synchronization trap in `roc_auc`). However, **critical silent bugs persist in `phi_net` that will prematurely abort or degrade a Kaggle session.**

### The 4 Major Defects Found:

1. **The B1 Gate Trap Aborts B2 Prematurely (`phi_net/run_kaggle.py:82-90`):**
   `run_kaggle.py` checks `b1["gates_passed"]`, which enforces Gate **F1 ($> 0.70$)** on B1 (only 15 epochs on 100k rows). Per `PLAN §8b`, F1 is the falsification threshold for **B2 (40 epochs on 209k rows)**. A promising B1 run scoring 0.67 or 0.68 will fail F1, causing `run_kaggle.py` to **abort immediately without ever training B2**.

2. **`evaluate.py` Misses `sys.path` Repair (`phi_net/evaluate.py`):**
   Claude added `sys.path.insert(0, ...)` to `run_kaggle.py` but forgot `evaluate.py`. Running `python /kaggle/working/phi_net/evaluate.py` fails with `ModuleNotFoundError: No module named 'phi_net'`.

3. **`predict()` Hardcodes `use_amp=True` & Ignores `--no-amp` (`phi_net/train.py`, `phi_net/evaluate.py`):**
   Validation and test evaluations invoke `predict()` with default `use_amp=True`. Passing `--no-amp` does not disable fp16 autocast during evaluation.

4. **`GradScaler` Remains Active on CUDA Even With `--no-amp` (`phi_net/train.py`):**
   `_make_scaler` does not pass `enabled=use_amp`. Passing `--no-amp` leaves a live $65,536\times$ loss scaler running on pure fp32 parameters.

### Operational Improvements:
- **Stdout Block Buffering:** Add `flush=True` in `train.py` and `-u` in `HOW_TO_KAGGLE.md` to prevent ~96-epoch silent buffering in Kaggle notebook subprocesses.
- **Float32 Precision Truncation in `roc_auc`:** Use `.double().sum()` to prevent integer truncation when rank sums exceed $2^{24}$.
