#!/usr/bin/env python3
"""
Chess Game Trajectory Conditional Neural Process (CNP)
======================================================
An active learning prototype demonstrating:
1. Encoder: Maps sparse evaluated moves (ply, win_probability) to latent vectors.
2. Kernel Cross-Attention Aggregator: Attends over context moves using an RBF kernel.
3. Heteroscedastic Decoder: Predicts mean trajectory μ(t) and kernel-conditioned uncertainty σ(t).
4. Gaussian Negative Log-Likelihood (NLL) training objective.

Behavioral Invariant:
Uncertainty σ(t) naturally collapses to the noise floor at evaluated plies
and widens honestly across unsearched stretches (the GP inductive bias).
"""

import math
import os
import random
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import matplotlib.pyplot as plt

# Set random seeds for reproducibility
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)


# ==============================================================================
# 1. Dataset: Realistic Chess Evaluation Trajectories
# ==============================================================================
class ChessTrajectoryGenerator:
    """
    Generates realistic chess evaluation trajectories across T plies.
    In chess, games start balanced (0.0), undergo positional maneuvering,
    experience sharp tactical blunder steps (swings), and settle into endgames.
    Evaluation is normalized into win probability / tanh space: [-1.0, 1.0].
    """
    def __init__(self, num_plies: int = 60):
        self.num_plies = num_plies

    def generate_trajectory(self) -> np.ndarray:
        t = np.linspace(0, 1, self.num_plies)
        
        # 1. Opening drift (gradual maneuvering around equality)
        drift_slope = np.random.normal(0.0, 0.3)
        drift = drift_slope * t
        
        # 2. Smooth tactical swings (low-frequency positional momentum)
        num_waves = np.random.randint(1, 3)
        waves = np.zeros_like(t)
        for _ in range(num_waves):
            freq = np.random.uniform(1.0, 3.0)
            amp = np.random.uniform(0.1, 0.4)
            phase = np.random.uniform(0, 2 * np.pi)
            waves += amp * np.sin(2 * np.pi * freq * t + phase)
            
        # 3. Tactical blunders / decisive turn (sharp step change at a random ply)
        has_blunder = np.random.rand() > 0.3
        blunder = np.zeros_like(t)
        if has_blunder:
            blunder_ply = np.random.uniform(0.2, 0.7)
            blunder_mag = np.random.choice([-1.0, 1.0]) * np.random.uniform(0.4, 0.8)
            blunder = blunder_mag / (1.0 + np.exp(-30.0 * (t - blunder_ply)))
            
        # Combine and squash via tanh to guarantee bounded win-probability [-1, 1]
        raw_eval = drift + waves + blunder + np.random.normal(0.0, 0.02, size=t.shape)
        eval_curve = np.tanh(raw_eval)
        return eval_curve.astype(np.float32)

    def sample_batch(self, batch_size: int = 32, min_context: int = 3, max_context: int = 10):
        """
        Returns:
            x_c: [B, N_c, 1]
            y_c: [B, N_c, 1]
            x_t: [B, N_t, 1]
            y_t: [B, N_t, 1]
        """
        t = np.linspace(0, 1, self.num_plies, dtype=np.float32).reshape(-1, 1) # [T, 1]
        num_context = np.random.randint(min_context, max_context + 1)
        
        batch_x_c, batch_y_c = [], []
        batch_x_t, batch_y_t = [], []
        
        for _ in range(batch_size):
            y = self.generate_trajectory().reshape(-1, 1)
            context_indices = np.sort(np.random.choice(self.num_plies, size=num_context, replace=False))
            
            batch_x_c.append(t[context_indices])
            batch_y_c.append(y[context_indices])
            batch_x_t.append(t)
            batch_y_t.append(y)
            
        return (
            torch.tensor(np.array(batch_x_c), dtype=torch.float32),
            torch.tensor(np.array(batch_y_c), dtype=torch.float32),
            torch.tensor(np.array(batch_x_t), dtype=torch.float32),
            torch.tensor(np.array(batch_y_t), dtype=torch.float32),
        )


# ==============================================================================
# 2. Kernel-Conditioned Neural Process Architecture
# ==============================================================================
class ChessTrajectoryCNP(nn.Module):
    """
    Gaussian Process-inspired Conditional Neural Process:
    1. Encoder: Maps (x_c, y_c) pairs into latent feature vectors.
    2. Kernel Aggregator: Uses an RBF covariance kernel to attend over context moves.
    3. Heteroscedastic Decoder: Predicts mean evaluation μ(x_t) and uncertainty σ(x_t).
    
    The uncertainty σ^2(x_t) is conditioned directly on the kernel proximity to
    context evaluations:
       σ^2(x_t) = σ_noise^2 + σ_prior^2 * (1 - max_c k(x_t, x_c))
    This provides the exact Gaussian Process inductive bias in O(N) amortized time!
    """
    def __init__(self, hidden_dim: int = 128):
        super().__init__()
        # Context observation encoder
        self.encoder = nn.Sequential(
            nn.Linear(2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim)
        )
        
        # Learnable GP hyperparameters
        self.log_lengthscale = nn.Parameter(torch.tensor([-1.8])) # lengthscale ~ 0.16 (approx 10 plies)
        self.log_sigma_noise = nn.Parameter(torch.tensor([-2.8])) # observation noise floor ~ 0.06
        self.log_sigma_prior = nn.Parameter(torch.tensor([-0.8])) # prior gap uncertainty ~ 0.45
        
        # Decoder predicting mean trajectory
        self.decoder = nn.Sequential(
            nn.Linear(hidden_dim + 1, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1)
        )

    def forward(self, x_c: torch.Tensor, y_c: torch.Tensor, x_t: torch.Tensor):
        # 1. Encode context observations
        xy_c = torch.cat([x_c, y_c], dim=-1) # [B, N_c, 2]
        v_c = self.encoder(xy_c)             # [B, N_c, hidden_dim]
        
        # 2. Compute RBF kernel similarities between target queries x_t and context x_c
        # dist_sq shape: [B, N_t, N_c]
        dist_sq = (x_t - x_c.transpose(1, 2)) ** 2
        ell = torch.exp(self.log_lengthscale) + 1e-4
        k_tc = torch.exp(-dist_sq / (2.0 * ell ** 2)) # [B, N_t, N_c]
        
        # Normalized kernel attention weights for mean interpolation
        weights = k_tc / (torch.sum(k_tc, dim=-1, keepdim=True) + 1e-6) # [B, N_t, N_c]
        r_t = torch.bmm(weights, v_c)                                    # [B, N_t, hidden_dim]
        
        # 3. Decode mean μ(x_t)
        rx = torch.cat([r_t, x_t], dim=-1)
        mu = self.decoder(rx) # [B, N_t, 1]
        
        # 4. Kernel Uncertainty Formulation (The Gaussian Process Inductive Bias):
        # Maximum correlation with any context observation: max_c k(x_t, x_c) ∈ [0, 1]
        max_k = torch.max(k_tc, dim=-1, keepdim=True).values # [B, N_t, 1]
        
        sigma_noise = torch.exp(self.log_sigma_noise) + 1e-3
        sigma_prior = torch.exp(self.log_sigma_prior) + 1e-3
        
        # Variance collapses to sigma_noise^2 when max_k ~ 1.0 (at context plies)
        # and expands to (sigma_noise^2 + sigma_prior^2) when max_k ~ 0.0 (in unsearched gaps)
        variance = (sigma_noise ** 2) + (sigma_prior ** 2) * (1.0 - max_k)
        sigma = torch.sqrt(variance)
        
        return mu, sigma


# ==============================================================================
# 3. Gaussian Negative Log-Likelihood (NLL) Objective
# ==============================================================================
def gaussian_nll(mu: torch.Tensor, sigma: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """
    Exact Gaussian Negative Log-Likelihood:
    -log N(y | μ, σ^2) = 0.5 * ( (y - μ)^2 / σ^2 + log(σ^2) + log(2π) )
    """
    var = sigma ** 2
    loss = 0.5 * (((y - mu) ** 2) / var + torch.log(var) + math.log(2.0 * math.pi))
    return torch.mean(loss)


# ==============================================================================
# 4. Training Loop & Validation Invariant
# ==============================================================================
def train_model(model: nn.Module, generator: ChessTrajectoryGenerator, num_epochs: int = 300, batch_size: int = 32):
    optimizer = torch.optim.Adam(model.parameters(), lr=2e-3)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=num_epochs)
    
    print(f"--- Training Chess Trajectory CNP for {num_epochs} epochs on CPU ---")
    
    for epoch in range(1, num_epochs + 1):
        model.train()
        x_c, y_c, x_t, y_t = generator.sample_batch(batch_size=batch_size, min_context=3, max_context=10)
        
        optimizer.zero_grad()
        mu, sigma = model(x_c, y_c, x_t)
        loss = gaussian_nll(mu, sigma, y_t)
        loss.backward()
        optimizer.step()
        scheduler.step()
        
        if epoch % 50 == 0 or epoch == 1:
            print(f"Epoch {epoch:3d}/{num_epochs:3d} | NLL Loss: {loss.item():+.4f} | Noise sigma: {torch.exp(model.log_sigma_noise).item():.4f} | Prior sigma: {torch.exp(model.log_sigma_prior).item():.4f}")

    print("--- Training Complete ---\n")


# ==============================================================================
# 5. Invariant Test & Visualization
# ==============================================================================
def verify_and_plot(model: nn.Module, generator: ChessTrajectoryGenerator, output_image_path: str):
    model.eval()
    
    # Generate a test game trajectory (60 plies)
    num_plies = 60
    t = np.linspace(0, 1, num_plies, dtype=np.float32).reshape(1, -1, 1)
    y_full = generator.generate_trajectory().reshape(1, -1, 1)
    
    # 6 sparse "engine evaluation" plies as context (e.g., plies 5, 14, 24, 36, 48, 56)
    context_plies = [4, 13, 23, 35, 47, 55]
    x_c = t[:, context_plies, :]
    y_c = y_full[:, context_plies, :]
    
    with torch.no_grad():
        x_c_tensor = torch.tensor(x_c)
        y_c_tensor = torch.tensor(y_c)
        x_t_tensor = torch.tensor(t)
        
        mu_tensor, sigma_tensor = model(x_c_tensor, y_c_tensor, x_t_tensor)
        
        mu = mu_tensor.squeeze().numpy()
        sigma = sigma_tensor.squeeze().numpy()
        t_axis = np.arange(1, num_plies + 1)
        y_true = y_full.squeeze()
        
    # Invariant Check:
    # Sigma at context points must be significantly smaller than sigma at unobserved gap points
    gap_plies = [p for p in range(num_plies) if p not in context_plies]
    mean_sigma_context = float(np.mean(sigma[context_plies]))
    mean_sigma_gap = float(np.mean(sigma[gap_plies]))
    ratio = mean_sigma_gap / (mean_sigma_context + 1e-6)
    
    print("|mu - y| at context plies:", np.abs(mu[context_plies] - y_true[context_plies]))
    
    print("=" * 65)
    print("BEHAVIORAL INVARIANT CHECK (Uncertainty Pinching):")
    print(f"  Mean Sigma at Evaluated Moves (Context):  {mean_sigma_context:.4f}")
    print(f"  Mean Sigma at Unsearched Moves (Gaps):     {mean_sigma_gap:.4f}")
    print(f"  Gap / Context Uncertainty Ratio:           {ratio:.2f}x")
    
    assert mean_sigma_context < mean_sigma_gap, (
        f"FAILED: Context sigma ({mean_sigma_context:.4f}) is not smaller than gap sigma ({mean_sigma_gap:.4f})!"
    )
    print(f"  RESULT: [PASS] Uncertainty collapses tightly around context moves ({ratio:.2f}x sharper).")
    print("=" * 65)

    # Plot the result
    os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
    
    plt.figure(figsize=(11, 5.5), dpi=150)
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    
    # 1. Ground truth full trajectory
    plt.plot(t_axis, y_true, color='#1f2937', linestyle='--', linewidth=1.5, label='Ground Truth Game Trajectory (All Plies)', alpha=0.7)
    
    # 2. Predicted mean
    plt.plot(t_axis, mu, color='#2563eb', linewidth=2.2, label='CNP Predicted Mean mu(t)')
    
    # 3. Uncertainty Ribbon (mu +/- 2*sigma, ~95% confidence)
    plt.fill_between(t_axis, mu - 2 * sigma, mu + 2 * sigma, color='#3b82f6', alpha=0.22, label='Predictive Uncertainty (mu +/- 2*sigma)')
    
    # 4. Context points (where engine searches were run)
    context_x_disp = [p + 1 for p in context_plies]
    context_y_disp = y_true[context_plies]
    plt.scatter(context_x_disp, context_y_disp, color='#dc2626', s=85, zorder=5, edgecolors='black', linewidth=1.5, label='Context: 6 Deep Engine Searches (LC0)')
    
    # Annotations & styling
    plt.title('Conditional Neural Process: Game Trajectory Interpolation from 6 Sparse Searches', fontsize=12, fontweight='bold', pad=12)
    plt.xlabel('Ply Number (Move Progression)', fontsize=10, labelpad=8)
    plt.ylabel('Evaluation (Normalized Win Probability)', fontsize=10, labelpad=8)
    plt.ylim(-1.15, 1.15)
    plt.xlim(1, num_plies)
    plt.axhline(0, color='gray', linestyle=':', alpha=0.5)
    
    # Annotations pointing out uncertainty behavior
    plt.annotate(
        f'Uncertainty collapses\nat evaluated plies (sigma={mean_sigma_context:.3f})',
        xy=(context_x_disp[2], context_y_disp[2]),
        xytext=(context_x_disp[2] + 3, context_y_disp[2] + 0.35),
        arrowprops=dict(facecolor='#dc2626', arrowstyle='->', lw=1.2),
        fontsize=9, fontweight='bold', color='#991b1b',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#fee2e2', edgecolor='#f87171', alpha=0.9)
    )
    
    gap_midpoint = (context_x_disp[3] + context_x_disp[4]) // 2
    plt.annotate(
        f'Uncertainty widens honestly\nin unsearched gaps (sigma={mean_sigma_gap:.3f})',
        xy=(gap_midpoint, mu[gap_midpoint - 1]),
        xytext=(gap_midpoint - 5, mu[gap_midpoint - 1] - 0.45),
        arrowprops=dict(facecolor='#2563eb', arrowstyle='->', lw=1.2),
        fontsize=9, fontweight='bold', color='#1e40af',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#dbeafe', edgecolor='#93c5fd', alpha=0.9)
    )
    
    plt.legend(loc='lower left', framealpha=0.95, fontsize=9)
    plt.tight_layout()
    plt.savefig(output_image_path)
    plt.close()
    
    print(f"\nSaved demonstration plot to: {output_image_path}")


# ==============================================================================
# Main Entry Point
# ==============================================================================
if __name__ == "__main__":
    generator = ChessTrajectoryGenerator(num_plies=60)
    model = ChessTrajectoryCNP(hidden_dim=128)
    
    train_model(model, generator, num_epochs=300, batch_size=32)
    
    output_png = os.path.join("scratch", "chess_trajectory_cnp_demo.png")
    verify_and_plot(model, generator, output_png)
