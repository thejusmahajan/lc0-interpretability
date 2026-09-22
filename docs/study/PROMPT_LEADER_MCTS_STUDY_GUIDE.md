# TASK FOR LEADER AGENT: Companion Study Guide for Neural MCTS

## Objective
Create a companion step-by-step Study PDF / Guide to accompany `docs/study/guide/neural_mcts_visual_guide_v2.pdf`.

This guide must be grounded in the student's actual learning trajectory and mental models documented in [`docs/study/STUDY_DIALOGUE_MCTS_FOUNDATIONS.md`](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/study/STUDY_DIALOGUE_MCTS_FOUNDATIONS.md).

---

## Pedagogical Principles & Requirements

1. **Down to the Constituent Elements**:
   - Break down every single concept, variable, and equation to its physical origin and causal mechanism.
   - Never introduce an abstraction without grounding it in concrete chess mechanics.

2. **Clean Typography / Zero Unrendered Math**:
   - Present all formulas with plain, readable text, clean arithmetic, and ASCII/Unicode diagrams.
   - Ensure every calculation can be parsed effortlessly without relying on client-side math renderers.

3. **Explicit State (`s`) vs. Action (`a`) Separation**:
   - Clearly distinguish a **State `s`** (a board position node representing the situation prior to a move) from an **Action `a`** (a candidate move edge leaving that node).
   - Reiterate that an action is a move choice, not a position.

4. **The Unvisited vs. Visited Transition (First Play Urgency / FPU)**:
   - **Phase 1 (Unvisited, $n = 0$)**: Explain that unvisited candidate moves initially inherit the parent position's prior evaluation as a baseline floor (`Q_FPU`), with policy priors `P` driving initial curiosity (`U`).
   - **Phase 2 (Visited, $n \ge 1$)**: Explicitly trace the transition moment when a move is visited for the first time: the default placeholder is completely discarded and replaced by the real leaf evaluation from the child position.

5. **Concrete Micro-Examples**:
   - Trace the 4-legal-move King+Pawn endgame (`4k3/8/4K3/4P3/8/8/8/8 w - - 0 1`) across Iterations 0, 1, 2, and 3.
   - Show every visit count, FPU penalty drop, and Q-update so they can be verified by hand arithmetic.

6. **Address the Student's Exact Questions & Misconceptions**:
   - **Non-Uniform Sampling**: Explain why a cluster of bad blunders in a position does not drag down the position's average quality (because bad moves are abandoned after 1 visit, while winning moves receive 97%+ of the computational budget).
   - **Emergent Depth**: Explain why the engine revisits a move (to drill one ply deeper into the variation, creating new leaf nodes downstream).
   - **Position vs. Move Evaluation**: Clarify that the neural network evaluates board positions ($V(s)$), never moves directly. A move receives an evaluation only when played to reach a new child state.

---

## Reference Materials

* Primary Visual Guide: [`docs/study/guide/neural_mcts_visual_guide_v2.pdf`](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/study/guide/neural_mcts_visual_guide_v2.pdf)
* Student Dialogue & Q&A Log: [`docs/study/STUDY_DIALOGUE_MCTS_FOUNDATIONS.md`](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/study/STUDY_DIALOGUE_MCTS_FOUNDATIONS.md)
