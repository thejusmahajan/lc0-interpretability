"""The Phi network.

Phi answers one question: *is this a position of the shape where the side to move
goes wrong?* It is a *potential function* over configurations, not a second
opinion about who is winning -- no engine evaluation appears anywhere in its
inputs, its labels, or its loss. See `docs/plans/PLAN_CONFIGURATION_STEERING.md`
sections 3 and 4.

Architecture is deliberately ordinary: a small residual CNN over an 18x8x8 board,
in the AlphaZero shape, with two heads. Nothing here needs to be clever. The
interesting risk in this project has never been the model -- it was the dataset,
twice.
"""

from __future__ import annotations

import torch
import torch.nn as nn


class ResidualBlock(nn.Module):
    """Standard 3x3 residual block. Padding 1 keeps the board 8x8 throughout --
    a chess board has no border to discard, and every square matters."""

    def __init__(self, channels: int):
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, 3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(channels)
        self.conv2 = nn.Conv2d(channels, channels, 3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(channels)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = x
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        return self.relu(out + residual)


class PhiNet(nn.Module):
    """18x8x8 -> (phi logit, 20 motif logits).

    Two heads, and they answer different questions:

    * **phi**  -- "is a storm possible from here", one logit, trained on every row.
    * **motif** -- "which storm", 20 logits over the frozen theme vocabulary in
      ``manifest.json``. This head is trained on **positives only**; see the note
      in ``train.py`` about why the negatives' motif labels are unusable.
    """

    def __init__(self, in_planes: int = 18, channels: int = 64, blocks: int = 6,
                 n_motifs: int = 20):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(in_planes, channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
            nn.ReLU(inplace=True),
        )
        self.tower = nn.Sequential(*[ResidualBlock(channels) for _ in range(blocks)])

        # Phi head: squeeze to 8 channels, then a small MLP over all 64 squares.
        self.phi_head = nn.Sequential(
            nn.Conv2d(channels, 8, 1, bias=False),
            nn.BatchNorm2d(8),
            nn.ReLU(inplace=True),
            nn.Flatten(),
            nn.Linear(8 * 64, 128),
            nn.ReLU(inplace=True),
            nn.Linear(128, 1),
        )

        # Motif head: wider squeeze, since it predicts 20 co-occurring labels.
        self.motif_head = nn.Sequential(
            nn.Conv2d(channels, 16, 1, bias=False),
            nn.BatchNorm2d(16),
            nn.ReLU(inplace=True),
            nn.Flatten(),
            nn.Linear(16 * 64, n_motifs),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """``x`` is (B, 18, 8, 8). Accepts uint8 and casts -- callers keep the
        resident dataset in uint8 to save memory and cast per batch."""
        if x.dtype != torch.float32 and x.dtype != torch.float16:
            x = x.float()
        h = self.tower(self.stem(x))
        return self.phi_head(h).squeeze(-1), self.motif_head(h)

    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters())


def build_model(channels: int = 64, blocks: int = 6, n_motifs: int = 20) -> PhiNet:
    return PhiNet(channels=channels, blocks=blocks, n_motifs=n_motifs)
