# PyTorch Fundamentals & Headstart Guide

## 1. What PyTorch Actually Is

At its core, **PyTorch** is two tightly integrated systems:

1. **A GPU-Accelerated Tensor Library**: Like NumPy, but optimized to execute multidimensional array operations in parallel across thousands of GPU cores (CUDA/ROCm).
2. **A Dynamic Reverse-Mode Automatic Differentiation Engine (`torch.autograd`)**: Tracks mathematical operations on tensors dynamically at runtime to compute exact analytical gradients ($\frac{\partial \mathcal{L}}{\partial \mathbf{W}}$) via the chain rule during the backward pass.

In classical scientific modeling (e.g. physics, differential equations, biostatistics), you define equations and often approximate derivatives numerically or solve analytical equations by hand. In PyTorch, you write the **forward calculation** (how input data transforms into predictions), and PyTorch automatically builds a dynamic execution graph to compute derivatives with `loss.backward()`.

---

## 2. The 5 Core Pillars of PyTorch

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│  1. Tensors  │ ──►  │  2. Modules  │ ──►  │ 3. Loss &    │
│ (Data & GPU) │      │ (Parameters) │      │    Autograd  │
└──────────────┘      └──────────────┘      └──────────────┘
                             ▲                     │
                             │   ┌──────────────┐  ▼
                             └── │ 4. Optimizer │ ◄┘
                                 │ (SGD / Adam) │
                                 └──────────────┘
```

### Pillar 1: `torch.Tensor` (Data Structure)
A multidimensional array with hardware and type awareness:
```python
import torch

# Create a tensor on CPU or GPU
x = torch.tensor([[1.0, 2.0], [3.0, 4.0]], dtype=torch.float32)
device = "cuda" if torch.cuda.is_available() else "cpu"
x = x.to(device)  # Moves memory directly to GPU VRAM
```

### Pillar 2: `torch.autograd` (Automatic Differentiation)
When `requires_grad=True`, PyTorch records every mathematical operation on that tensor:
```python
w = torch.tensor([2.0], requires_grad=True)
b = torch.tensor([1.0], requires_grad=True)

# Equation: y = 3*w + b
y = 3.0 * w + b

# Compute dy/dw and dy/db
y.backward()
print(w.grad)  # tensor([3.0])  -> dy/dw = 3
print(b.grad)  # tensor([1.0])  -> dy/db = 1
```

### Pillar 3: `torch.nn.Module` (Parameterized Neural Layers)
All layers, linear transformations, and deep network architectures inherit from `nn.Module`. It handles weight initialization and device placement:
```python
import torch.nn as nn

class LinearProbe(nn.Module):
    def __init__(self, in_features, num_classes):
        super().__init__()
        # nn.Linear holds weight matrix W [num_classes, in_features] and bias b
        self.fc = nn.Linear(in_features, num_classes)

    def forward(self, x):
        # Defines computation: y = x @ W^T + b
        return self.fc(x)
```

### Pillar 4: Loss Functions & Optimizers (`torch.optim`)
- **Loss Function**: Quantifies prediction error (e.g. `nn.CrossEntropyLoss`, `nn.MSELoss`, `nn.MarginRankingLoss`).
- **Optimizer**: Updates parameters using calculated gradients:
  $$\mathbf{W}_{\text{new}} \leftarrow \mathbf{W}_{\text{old}} - \eta \nabla_{\mathbf{W}} \mathcal{L}$$

### Pillar 5: Data Pipelines (`Dataset` & `DataLoader`)
Handles streaming, shuffling, and multi-process batching:
```python
from torch.utils.data import DataLoader, TensorDataset

dataset = TensorDataset(features_tensor, labels_tensor)
loader = DataLoader(dataset, batch_size=64, shuffle=True)
```

---

## 3. The Canonical 5-Line Training Loop

Almost every neural network training step in PyTorch follows this exact sequence:

```python
for batch_x, batch_y in loader:
    optimizer.zero_grad()                  # 1. Reset gradients from previous step
    predictions = model(batch_x)           # 2. Forward pass: compute predictions
    loss = criterion(predictions, batch_y) # 3. Compute loss scalar
    loss.backward()                        # 4. Backward pass: compute dLoss/dWeight
    optimizer.step()                       # 5. Optimizer updates parameters
```

---

## 4. Complete End-to-End Minimal Example

```python
import torch
import torch.nn as nn
import torch.optim as optim

# 1. Generate toy dataset: y = 1 if (x0 + x1 > 0) else 0 (Binary classification)
X = torch.randn(1000, 10)            # 1000 samples, 10 features
y = (X[:, 0] + X[:, 1] > 0).long()   # Target class: 0 or 1

# 2. Define a 2-layer Neural Network
class SimpleClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(10, 32), # Layer 1: 10 inputs -> 32 hidden units
            nn.ReLU(),         # Non-linear activation function
            nn.Linear(32, 2)   # Layer 2: 32 hidden units -> 2 class logits
        )

    def forward(self, x):
        return self.net(x)

model = SimpleClassifier()
criterion = nn.CrossEntropyLoss()
optimizer = optim.AdamW(model.parameters(), lr=0.01)

# 3. Train for 5 epochs
model.train()
for epoch in range(5):
    optimizer.zero_grad()
    logits = model(X)
    loss = criterion(logits, y)
    loss.backward()
    optimizer.step()
    print(f"Epoch {epoch+1} | Loss: {loss.item():.4f}")

# 4. Evaluation / Inference (Disable gradient tracking)
model.eval()
with torch.no_grad():
    sample = torch.randn(1, 10)
    pred_class = model(sample).argmax(dim=-1).item()
    print(f"Prediction for new sample: Class {pred_class}")
```

---

## 5. Secret Weapon for Mechanistic Interpretability: Forward Hooks

PyTorch allows non-invasive inspection of intermediate hidden layers using **Forward Hooks** (`register_forward_hook`). This is how `backend/neural_vision.py` intercepts LC0 transformer attention matrices without modifying LC0's model code:

```python
activations = {}

def hook_fn(module, input, output):
    # Intercept layer output tensor during forward pass
    activations["layer_output"] = output.detach()

# Register hook onto a specific layer
hook_handle = model.net[0].register_forward_hook(hook_fn)

# Run standard inference
model(sample)

# Hidden activations are captured
print("Captured layer output shape:", activations["layer_output"].shape)

# Remove hook when done
hook_handle.remove()
```

---

## 6. Is PyTorch Similar to `tidymodels`?

**Short answer**: **No, they operate at completely different layers of abstraction and solve different problems.**

Here is the exact comparison:

| Dimension | `tidymodels` (R / Tidyverse) | `PyTorch` (Python) |
|---|---|---|
| **Core Nature** | High-level orchestration framework for classical machine learning and statistics | Low-level computational tensor & differentiable programming engine |
| **Primary Domain** | Tabular data, clinical trials, GLMs, Random Forests, XGBoost, survival analysis | Deep neural networks, transformers, vision, mechanistic interpretability, RL |
| **Abstraction Level** | **High**: You define a model spec (`rand_forest() %>% set_engine("ranger")`), recipes, and call `fit()`. Math/gradients are hidden. | **Low / Explicit**: You define exact tensor operations ($y = XW^T + b$), custom loss functions, and manage the backpropagation loop manually. |
| **Direct Equivalent** | Python's **`scikit-learn`** (or `tidymodels` $\approx$ `recipes` + `rsample` + `parsnip` + `yardstick`) | **JAX**, **TensorFlow**, or C++/CUDA libraries |
| **High-level wrapper** | `tidymodels` is *already* the wrapper. | **`PyTorch Lightning`**, **`FastAI`**, or **`HuggingFace Trainer`** wrap PyTorch to give a higher-level API. |

### The Conceptual Bridge (From R/Biostatistics to Deep Learning):
- If you used `tidymodels` in R for clinical statistics, you were applying **pre-built estimators** to **tabular data frames**.
- In `PyTorch`, you are writing **differentiable computation graphs**. Think of it more like writing a custom differential equation or numerical physics simulation where every mathematical parameter can be tuned automatically by gradient descent.
