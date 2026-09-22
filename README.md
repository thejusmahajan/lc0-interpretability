# LC0 Interpretability & Attention Analysis Toolchain

A toolchain for extracting, mapping, and inspecting self-attention mechanisms in chess neural networks. Specifically, it applies PyTorch forward hooks over a 15-layer transformer architecture (Leela Chess Zero BT3) to read attention across 64 board tokens, serving the resulting saliency maps through a FastAPI backend and an interactive React chessboard.

---

## The Two Silent Bugs

During development and validation, two subtle bugs produced plausible but invalid attention extractions without raising runtime exceptions:

1. **Input Representation (Bare FEN vs. History Planes):**
   Evaluating static positions from bare FEN strings without historical board states left 84 of the network's 112 input planes unpopulated (history planes remained zeroed). The network still produced well-formed policy priors and evaluations, but the attention maps reflected an incomplete board context rather than the true state representation seen during search.

2. **Frame of Reference (Orientation Inversion):**
   Attention maps for Black-to-move positions were extracted in the White perspective due to an unmirrored coordinate orientation in the tensor hook pipeline. Because piece placements and spatial saliency still appeared coherent at a casual glance, this orientation error went undetected until systematic coordinate symmetry testing was applied. One finding had already been included in a published write-up before the inversion was diagnosed and publicly corrected.

A detailed technical breakdown of the orientation bug, the diagnostic procedure, and the coordinate transformation fix is documented in [`docs/writeup_attention_frame_bug.md`](docs/writeup_attention_frame_bug.md).

---

## Correctness & Mutation Testing

The analysis pipeline and backend services are verified by a comprehensive suite of **345 automated tests**.

Correctness is guarded via mutation testing: test cases were verified against deliberate mutations in the hook extraction logic, coordinate transformations, and data contracts to confirm that any regression or inverted frame produces an immediate test failure. In this suite, passing tests serve as empirical verification that invariants hold across both player perspectives and varying game phases.

---

## How to Run

### Environment & Prerequisites

Running the full pipeline with live neural attention requires:
- **Python 3.11** with `torch`, `python-chess`, `fastapi`, and `uvicorn`.
- **Node.js** (v18+) for the React frontend interface.
- **Engine Binaries & Weights** (placed in `engine/`):
  - LC0 engine binary (`lc0.exe` or equivalent).
  - BT3 transformer network weights (`bt3.onnx`) for attention saliency extraction.
  - Policy network weights (e.g., `791556.pb.gz`) for search and candidate move priors.

### 1. Running Tests

To verify the test suite:

```bash
pytest backend/tests -v
```

To run test collection only:

```bash
pytest backend/tests --collect-only -q
```

### 2. Starting the Backend

From the repository root:

```bash
python -m uvicorn backend.app:app --reload --port 8000
```

### 3. Starting the Frontend

From the `frontend/` directory:

```bash
cd frontend
npm install
npm run dev
```

The interactive board interface is accessible at `http://localhost:5173`. Detailed operational notes, runtime health checks, and troubleshooting steps are available in [`HOW_TO_RUN.md`](HOW_TO_RUN.md).

---

## Status and Limitations

This codebase is research and diagnostic software designed for observational attention extraction.

**Explicit Scope Boundaries:**
- **No causal intervention:** The toolchain records attention distributions during inference; it does not perform causal interventions on internal activations.
- **No activation patching:** The current pipeline does not perform activation patching across counterfactual board states.
- **No circuit discovery:** There is no automated identification or pruning of attention circuits.
- **No trained or fine-tuned network:** Network weights are evaluated as released by the Leela Chess Zero project; no custom fine-tuning or training was performed.
- **No trained probe:** Representations are inspected directly via layer hooks without training auxiliary linear or non-linear probes.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
