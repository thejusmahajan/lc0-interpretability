# Research note — Learned Look-Ahead in chess neural networks (BT3)

**Status:** LOGGED for future discussion. Not scheduled, not started. Parked
alongside `POST_VALIDATION_BACKLOG.md`. Revisit deliberately.

**Why this is on our radar specifically:** the research is about **Lc0's BT3** —
the exact transformer we just adopted as the diagnosis search net — and we
*already* extract BT3 intermediate layers via `lczerolens` (that's how the
saliency heatmap works). So the machinery to explore this is largely in place.

## The idea
**Learned look-ahead** = an emergent phenomenon where the network implicitly
simulates future moves *inside its hidden layers during a single forward pass*,
without any external search (no MCTS/minimax). The net doesn't just statically
score the board — its middle layers "think" several plies ahead.

Source papers (to pull when we revisit):
- *Evidence of Learned Look-Ahead in a Chess-Playing Neural Network*
- *Learned Priors Override Look-Ahead in a Chess-Playing Neural Network*

### Four findings
1. **Future-move representation.** The 64 squares are tokens (LLM-style). Even when
   predicting only the next move, middle layers hold accurate internal pictures of
   the board **3–7 plies ahead**. A simple **linear probe** on those layers can
   predict the optimal move two turns ahead with up to ~92% accuracy.
2. **Time-traveling attention heads.** Specific "look-ahead" heads route information
   **forward and backward in time** — pulling from squares where pieces *will* be,
   and feeding that back to earlier layers to shape the immediate choice.
3. **Causal importance.** These future representations are causal, not decorative:
   suppressing the activations on squares of a future combination **changes the
   net's immediate move** — proof it relies on internal "future simulation."
4. **Priors override look-ahead ("forgotten puzzles").** In intermediate layers the
   net *finds* the winning line / forced mate — but as it flows to the output
   layers, deep **training priors can override the discovery**, rejecting a correct
   winning move because it "looks" risky or materially expensive, and picking a
   safer, inferior move instead.

## Why it matters to *this* project (connections, for discussion)
- **Finding 4 is the standout for us.** It's a *mechanistic explanation* for two
  things we already want:
  - **Hidden gems / optical traps** (`gems.py`, backlog **B1**): "low policy, high
    search" isn't just a stats quirk — the net's *intermediate look-ahead found the
    move* but its output prior suppressed it. We could surface: *"BT3's deeper
    layers saw this winning sacrifice; its instinct talked it out of it."*
  - **Tactical steering / the Tal engine** (TS2, backlog **B3/B4**): the whole point
    of Tal-style play is trusting a sound sacrifice that "looks" wrong. A "suppressed
    win" probe would find exactly the moves the net's *own priors* flinch at — the
    most on-theme feature imaginable for the sacrificial repertoire.
- **Findings 1–2 deepen the AI-vision backlog:**
  - **B2 (tensor attention rays):** the "time-traveling heads" are literally
    forward/backward-in-time rays — a richer, research-grounded version of B2.
  - A **future-board overlay:** read the middle-layer probe and render *what the net
    foresees* 3–7 plies out, not just current-board attention.

## Feasibility / caveats (so future-us is honest)
- Linear probes must be **trained** (need labeled data: positions → future move).
  Non-trivial but small models; the papers show it's doable.
- Interpretability results are **architecture-specific** — they were shown on a
  particular Leela net; our BT3 build may differ. Would need to re-verify the probe
  works on *our* `BT3-768x15x24h`.
- `lczerolens` gives us the layer hooks; extracting *which* heads/layers carry the
  look-ahead signal is the research-y part.

## Open questions for the next discussion
- Can we reproduce the linear probe on our BT3 to read "future move" from mid layers?
- Is a "suppressed-win detector" (Finding 4) reliable enough to be a *feature*, or
  only an occasional flourish?
- Does it belong as a diagnosis signal (offline, per position) or a live overlay?

Related: `POST_VALIDATION_BACKLOG.md` (B1 optical-trap/gems, B2 rays, B3 sparring,
B4 Tal persona), `docs/discussion_4_ai_vision_gukesh_tal.md`.
