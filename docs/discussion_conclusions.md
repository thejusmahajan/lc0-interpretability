# Conclusions: How to Implement Tactical Steering

Based on the combined brainstorming of the LC0 Devs, Vishy, Tal, Magnus, Silver, and Hassabis, there are **5 distinct implementation vectors** to achieve this, each with unique requirements and drawbacks:

#### 1. MCTS PUCT Hacking (The Search Bias)
*   **What it needs:** Modification of the LC0 C++ search algorithm. You must inject a lightning-fast C++ tactical tagger directly into the node evaluation loop to inflate the score of branches containing the target motif.
*   **Result:** The engine brute-forces calculations toward the requested motif.
*   **Drawback:** Computationally massive (evaluating millions of nodes per second). High risk of the "Horizon Effect"—the engine might intentionally blunder a piece just to artificially reach a position that registers as a "pin."

#### 2. Conditional Neural Network Training (The Input Method)
*   **What it needs:** A massive compute cluster. You must take millions of Lichess games, tag them, and add new input "Concept Planes" (e.g., the Skewer Plane) to the neural network, then retrain LC0 from scratch.
*   **Result:** At runtime, you flip the "Skewer Plane" to `1.0`. The engine requires zero extra calculation time; its Policy head inherently "feels" that moves leading to skewers are better.
*   **Drawback:** Enormous time and financial cost to retrain the weights. 

#### 3. Multi-Objective Value Heads (The Output Method)
*   **What it needs:** Architecture change to the neural network to output two distinct value probabilities: $V_{win}$ and $V_{motif}$. Requires retraining.
*   **Result:** You give the user a mathematical dial at runtime ($V_{total} = V_{win} + \alpha V_{motif}$). You seamlessly mix objective strength with tactical desire.
*   **Drawback:** Requires modifying the pure RL self-play loop, potentially weakening the engine's core chess strength.

#### 4. Activation Steering / Representation Engineering (The Hallucination Method)
*   **What it needs:** AI interpretability research. You must map the hidden layers (ResNets) of the existing LC0 model to isolate the exact mathematical vector that represents the abstract concept of a "sacrifice." You then inject that vector into the hidden layers during live inference.
*   **Result:** Forces the engine to "hallucinate" the motif without needing to retrain the network or slow down the search tree.
*   **Drawback:** Highly experimental. If the vector isn't perfectly isolated, injecting it will turn the engine's evaluations into total garbage.

#### 5. Guided Trajectory Rollouts / Dense Rewards (The Pragmatic Synthesis)
*   **What it needs:** You do not reward the *motif*; you reward the underlying *board state* that creates the motif (e.g., restricting opponent mobility or maximizing branching factor). You apply a lightweight "Style Filter" to the MCTS leaf nodes. 
*   **Result:** The engine plays objectively sound moves but strictly avoids branches that don't fit the desired style. The tactical motifs (pins, forks) organically emerge as the mathematical tools the engine uses to satisfy the constraint.
*   **Drawback:** Pruning objectively superior branches will slightly reduce the engine's peak ELO, requiring careful tuning so it doesn't drop more than ~0.5 pawns in evaluation just to maintain the style.
