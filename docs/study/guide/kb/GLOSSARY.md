# Visual Guide & MCTS Theory Glossary

Every term and symbol used across *Inside LC0's Mind: A Visual Guide*, the 16 book chapters, and the LC0 engine reference. Alphabetized with definitions, source citations, and action location references.

---

## Glossary Entries

### Backpropagation
- **Definition**: The fourth phase of an MCTS iteration, propagating a leaf node's neural evaluation back up the search path to update parent visit counts $N$ and running average values $Q$.
- **Source Citation**: Guide §1.5, `FIG-1.6`, `ch05_machines_to_trees.tex:L180`.
- **Action Location**: `FIG-1.6`, `FIG-2.1`.

### Batching
- **Definition**: Grouping multiple leaf node positions into a single GPU/CPU tensor pass to maximize neural network throughput.
- **Source Citation**: `ENGINE_REFERENCE.md` (`--min-backend-throughput`), `ch08_engineering_reality.tex:L45`.
- **Action Location**: `FIG-1.4`, `ENGINE_REFERENCE.md` (`BackendOptions`).

### Centipawn ($CP$)
- **Definition**: Traditional chess evaluation unit equal to $1/100$th of a pawn, mapped to win probability via a sigmoidal logistic function.
- **Source Citation**: Guide §0.3, `FIG-0.4`, Equation~\eqref{eq:E3}, `ch02_currency_of_evaluation.tex:L60`.
- **Action Location**: `FIG-0.4`.

### Collision (Node Collision)
- **Definition**: Occurs when parallel search threads select the same unvisited leaf node before its neural evaluation returns, managed via virtual loss or task workers.
- **Source Citation**: `ENGINE_REFERENCE.md` (`MinimumPickingWork`, `TaskWorkers`), `ch08_engineering_reality.tex:L66-L76` (§"Collisions").
- **Action Location**: `ENGINE_REFERENCE.md` (`--minimum-picking-work`, `--max-collision-events`, `--max-collision-visits`).

### Contempt
- **Definition**: Artificial evaluation bias adjustment altering draw score or score expectation against opponents of differing Elo ratings.
- **Source Citation**: `ENGINE_REFERENCE.md` (`Contempt`, `UCI_RatingAdv`), `ch02_currency_of_evaluation.tex:L140`.
- **Action Location**: `ENGINE_REFERENCE.md` (`--contempt`).

### $c_{\text{puct}}$ (CPUCT Exploration Constant)
- **Definition**: Exploration multiplier governing how aggressively policy prior $P(a)$ and parent visit count $\sqrt{N}$ boost unvisited or low-visit move selection.
- **Source Citation**: Guide §1.4, `FIG-0.9`, Equation~\eqref{eq:E10}, Equation~\eqref{eq:E12}, `ch06_building_puct.tex:L130`.
- **Action Location**: `FIG-1.10`, `FIG-1.11d`.

### $d$ (Draw Probability)
- **Definition**: Neural value head output probability representing the likelihood of a drawn outcome, bounded in $[0, 1]$.
- **Source Citation**: Guide §0.3, `FIG-0.2`, `FIG-0.3`, Equation~\eqref{eq:E1}, `ch02_currency_of_evaluation.tex:L85`.
- **Action Location**: `FIG-0.3` (WDL Simplex), `FIG-0.4`.

### Dirichlet Noise
- **Definition**: Random noise sampled from a Dirichlet distribution added to root node policy priors to force exploration during self-play training or analysis.
- **Source Citation**: `ENGINE_REFERENCE.md` (`DirichletNoiseAlpha`, `DirichletNoiseEpsilon`), `ch06_building_puct.tex:L210`.
- **Action Location**: `ENGINE_REFERENCE.md` (`--noise-alpha`).

### Equation E1 (Expected Score Map)
- **Definition**: Formula $\mathbb{E}[\text{score}] = w + \frac{1}{2}d$ mapping Win/Draw/Loss probabilities to expected score in $[0, 1]$.
- **Source Citation**: Guide §0.3, `FIG-0.2`, `FIG-0.9`, Equation~\eqref{eq:E1}.
- **Action Location**: `FIG-0.3`.

### Equation E2 (Net Win Value)
- **Definition**: Formula $V = w - l \in [-1, +1]$ defining net win evaluation for the side-to-move.
- **Source Citation**: Guide §0.3, `FIG-0.2`, `FIG-0.9`, Equation~\eqref{eq:E2}.
- **Action Location**: `FIG-0.4`, `FIG-2.B`.

### Equation E3 (Centipawn Logistic Map)
- **Definition**: Logistic mapping $\mathbb{E}[\text{score}] = \frac{1}{1 + 10^{-\text{cp}/400}}$ connecting centipawns to win probability.
- **Source Citation**: Guide §0.3, `FIG-0.4`, `FIG-0.9`, Equation~\eqref{eq:E3}.
- **Action Location**: `FIG-0.4`.

### Equation E4 (Incremental Sample Mean)
- **Definition**: Online update rule $Q_n = Q_{n-1} + \frac{1}{n}(x_n - Q_{n-1})$ computing running average evaluation $W/N$.
- **Source Citation**: Guide §0.4, `FIG-0.5`, `FIG-0.9`, Equation~\eqref{eq:E4}.
- **Action Location**: `FIG-0.5`, `FIG-2.1`.

### Equation E5 (Standard Error Law)
- **Definition**: Formula $\text{SE}(Q_n) = \sigma / \sqrt{n}$ demonstrating standard error decay with sample size.
- **Source Citation**: Guide §0.5, `FIG-0.6`, `FIG-0.9`, Equation~\eqref{eq:E5}.
- **Action Location**: `FIG-0.6`.

### Equation E6 (Hoeffding Concentration Bound)
- **Definition**: Non-parametric bound $\epsilon = R\sqrt{\ln(1/\delta)/2n}$ setting confidence interval width for sample means.
- **Source Citation**: Guide §0.5, `FIG-0.6`, `FIG-0.9`, Equation~\eqref{eq:E6}.
- **Action Location**: `FIG-0.6`, `FIG-0.7`.

### Equation E7 (UCB1 Selection Rule)
- **Definition**: Bandit rule $a^* = \argmax_i [Q_i + c\sqrt{\ln N / n_i}]$ balancing measured value and visit uncertainty.
- **Source Citation**: Guide §0.6, `FIG-0.7`, `FIG-0.9`, Equation~\eqref{eq:E7}.
- **Action Location**: `FIG-0.7`.

### Equation E8 (Negamax Sign Flip)
- **Definition**: Zero-sum value backup relation $V_{\text{parent}} = -V_{\text{child}}$ negating evaluation across two-player ply transitions.
- **Source Citation**: Guide §0.7, `FIG-0.8`, `FIG-0.9`, Equation~\eqref{eq:E8}.
- **Action Location**: `FIG-0.8`, `FIG-2.10`.

### Equation E9 (UCT Selection Rule)
- **Definition**: Tree search extension $a^* = \argmax_a [Q + c\sqrt{\ln N(s)/n_a}]$ applying UCB1 to search tree nodes.
- **Source Citation**: Guide §0.7, `FIG-0.8`, `FIG-0.9`, Equation~\eqref{eq:E9}.
- **Action Location**: `FIG-0.8`.

### Equation E10 (PUCT Selection Formula)
- **Definition**: LC0 core selection formula $S(a) = Q(a) + c_{\text{puct}} P(a) \frac{\sqrt{N}}{1+n_a}$ combining exploitation $Q$ and prior-guided curiosity $U$.
- **Source Citation**: Guide §1.4, `FIG-0.9`, `FIG-1.10`, Equation~\eqref{eq:E10}.
- **Action Location**: `FIG-1.10`, `FIG-2.2`.

### Equation E11 (First Play Urgency Baseline)
- **Definition**: Unvisited move baseline floor $Q_{\text{FPU}} = Q(\text{parent}) - c_{\text{fpu}}\sqrt{\sum P_{\text{vis}}}$.
- **Source Citation**: Guide §1.4, `FIG-0.9`, `FIG-1.10`, Equation~\eqref{eq:E11}.
- **Action Location**: `FIG-2.B`, `FIG-2.0`.

### Equation E12 (Logarithmic CPUCT Scaling)
- **Definition**: Formula $c_{\text{puct}}(N) = c_{\text{base}} + c_{\text{factor}}\ln\left(\frac{N+c_{\text{mod}}}{c_{\text{mod}}}\right)$ opening search width during deep analysis.
- **Source Citation**: Guide §1.4, `FIG-0.9`, `FIG-1.10`, Equation~\eqref{eq:E12}.
- **Action Location**: `FIG-1.11d`.

### Evaluation
- **Definition**: Neural network forward pass evaluating a leaf node position to return policy prior vector $P$ and value probabilities $(w, d, l)$.
- **Source Citation**: Guide §1.5, `FIG-1.6`, `ch03_one_machine.tex:L90`.
- **Action Location**: `FIG-1.6`, `FIG-1.3b`.

### Expansion
- **Definition**: Creating child move branches at a newly selected leaf node upon receiving its neural network evaluation.
- **Source Citation**: Guide §1.5, `FIG-1.6`, `ch05_machines_to_trees.tex:L120`.
- **Action Location**: `FIG-1.6`, `FIG-2.1`.

### FPU (First Play Urgency / $Q_{\text{FPU}}$)
- **Definition**: Default evaluation assigned to unvisited moves to prevent over-exploring bad moves or under-exploring promising moves before first visit.
- **Source Citation**: Guide §1.4, `FIG-0.9`, Equation~\eqref{eq:E11}, `ch06_building_puct.tex:L170`.
- **Action Location**: `FIG-2.B`, `FIG-2.0`.

### Hoeffding Inequality
- **Definition**: Non-parametric concentration inequality bounding the probability that a sample mean $Q_n$ deviates from expectation by more than $\epsilon$.
- **Source Citation**: Guide §0.5, `FIG-0.6`, Equation~\eqref{eq:E6}, `ch04_many_machines.tex:L85`.
- **Action Location**: `FIG-0.6`, `FIG-0.7`.

### $l$ (Loss Probability)
- **Definition**: Neural value head output probability representing expected loss likelihood for the side-to-move, bounded in $[0, 1]$.
- **Source Citation**: Guide §0.3, `FIG-0.2`, `FIG-0.3`, Equation~\eqref{eq:E2}, `ch02_currency_of_evaluation.tex:L75`.
- **Action Location**: `FIG-0.3`, `FIG-0.4`.

### Logistic Mapping
- **Definition**: Sigmoidal function mapping centipawn evaluations ($CP$) onto expected win/loss probabilities in $[0, 1]$.
- **Source Citation**: Guide §0.3, `FIG-0.4`, Equation~\eqref{eq:E3}, `ch02_currency_of_evaluation.tex:L110`.
- **Action Location**: `FIG-0.4`.

### Moves-Left Head (MLH)
- **Definition**: Auxiliary neural network head predicting remaining ply count until game termination to assist time management and ply-sensitive evaluations.
- **Source Citation**: `ENGINE_REFERENCE.md` (`UCI_ShowMovesLeft`), `ch12_two_heads.tex:L140`.
- **Action Location**: `ENGINE_REFERENCE.md` (`--show-movesleft`).

### $N$ / $n_a$ (Visit Count)
- **Definition**: Total visits accumulated by a parent node ($N$) or individual child move branch ($n_a$) across MCTS iterations.
- **Source Citation**: Guide §0.4, §1.4, `FIG-0.2`, `FIG-0.5`, Equation~\eqref{eq:E4}, Equation~\eqref{eq:E10}, `ch05_machines_to_trees.tex:L60`.
- **Action Location**: `FIG-1.2`, `FIG-2.2`.

### Negamax
- **Definition**: Zero-sum game formulation where parent evaluation equals negative child evaluation ($V_{\text{parent}} = -V_{\text{child}}$), eliminating separate White/Black scoring logic.
- **Source Citation**: Guide §0.7, `FIG-0.8`, Equation~\eqref{eq:E8}, `ch05_machines_to_trees.tex:L210`.
- **Action Location**: `FIG-0.8`, `FIG-2.10`.

### Node / Edge / Leaf
- **Definition**: Structural elements of search tree where nodes represent board states, edges represent move choices, and leaves represent unexpanded or newly reached states.
- **Source Citation**: Guide §1.2, `FIG-1.2`, `ch05_machines_to_trees.tex:L35`.
- **Action Location**: `FIG-1.2`, `FIG-2.0`.

### Policy ($P(a)$ / Prior Probability)
- **Definition**: Probability vector output by neural policy head assigning raw prior preference to each legal move before search begins.
- **Source Citation**: Guide §1.2, `FIG-0.2`, `FIG-1.1`, Equation~\eqref{eq:E10}, `ch03_one_machine.tex:L120`.
- **Action Location**: `FIG-1.1`, `FIG-1.10`.

### Policy Blindness
- **Definition**: Failure mode where policy prior $P(a) \approx 0$ suppresses a tactical move, requiring thousands of visits before $U(a)$ grows enough to force exploration.
- **Source Citation**: Guide §4.2, `FIG-4.2`, `ch06_building_puct.tex:L240`.
- **Action Location**: `FIG-4.2`.

### Principal Variation (PV)
- **Definition**: The sequence of highest-visit moves leading from root down through search tree, representing the engine's primary line of play.
- **Source Citation**: Guide §2.3, `FIG-2.10`, `ch09_reading_a_tree.tex:L80`.
- **Action Location**: `FIG-2.10`.

### PUCT (Predictor + Upper Confidence Bound for Trees)
- **Definition**: Selection algorithm scaling exploration bonus $U(a)$ by policy prior $P(a)$ and parent visit growth $\sqrt{N}/(1+n_a)$.
- **Source Citation**: Guide §1.4, `FIG-0.9`, Equation~\eqref{eq:E10}, `ch06_building_puct.tex:L115`.
- **Action Location**: `FIG-1.9`, `FIG-1.10`.

### $Q(a)$ (Exploitation Value / Running Average)
- **Definition**: Expected value of move $a$ calculated as the running average of neural value backpropagations through its subtree.
- **Source Citation**: Guide §0.4, §1.4, `FIG-0.2`, `FIG-0.5`, Equation~\eqref{eq:E4}, `ch05_machines_to_trees.tex:L95`.
- **Action Location**: `FIG-0.5`, `FIG-1.11a`.

### Regret
- **Definition**: Cumulative loss in expected payoff suffered by choosing sub-optimal moves during search rather than the true best move.
- **Source Citation**: Guide §0.6, `ch04_many_machines.tex:L40`.
- **Action Location**: `FIG-0.7`.

### Salience
- **Definition**: Magnitude of attention or gradient weights highlighting specific board squares or features critical to neural predictions.
- **Source Citation**: Guide §5.2, `FIG-5.3`, `ch14_attention_maps.tex:L50`.
- **Action Location**: `FIG-5.3`.

### Selection
- **Definition**: First phase of MCTS iteration traversing down tree from root to unexpanded leaf by choosing move with maximum total score $S(a) = Q(a) + U(a)$.
- **Source Citation**: Guide §1.5, `FIG-1.6`, `ch05_machines_to_trees.tex:L75`.
- **Action Location**: `FIG-1.6`, `FIG-2.1`.

### Sharpness
- **Definition**: Steepness of value or policy probability distribution shifts across nearby move variations or position perturbations.
- **Source Citation**: Guide §4.1, `FIG-4.1`, `ch10_learned_formula.tex:L130`.
- **Action Location**: `FIG-4.1`.

### Smart Pruning
- **Definition**: Search optimization halting tree search early when unvisited or secondary candidate moves cannot mathematically overtake current best move.
- **Source Citation**: `ENGINE_REFERENCE.md` (`SmartPruningFactor`), `ch08_engineering_reality.tex:L160`.
- **Action Location**: `ENGINE_REFERENCE.md` (`--smart-pruning-factor`).

### Steer Move / Tal Move
- **Definition**: Aggressive or sacrificial move choice that disrupts opponent evaluation stability and shifts search tree trajectory into non-standard lines.
- **Source Citation**: Guide §4.3, `FIG-4.4`, `ch16_style_as_objective.tex:L90`.
- **Action Location**: `FIG-4.4`.

### $S(a)$ (Total Selection Score)
- **Definition**: Combined priority bar $S(a) = Q(a) + U(a)$ governing candidate move selection during MCTS search.
- **Source Citation**: Guide §1.4, `FIG-0.2`, Equation~\eqref{eq:E10}, `ch06_building_puct.tex:L150`.
- **Action Location**: `FIG-1.10`, `FIG-2.2`.

### Syzygy / Tablebase
- **Definition**: Precomputed endgame database providing exact Win/Draw/Loss and Distance-To-Zero ground truth for positions with up to 6-7 pieces.
- **Source Citation**: `ENGINE_REFERENCE.md` (`SyzygyPath`), `ch08_engineering_reality.tex:L210`.
- **Action Location**: `ENGINE_REFERENCE.md` (`--syzygy-paths`).

### Temperature (Policy Temperature)
- **Definition**: Softmax scaling exponent applied to move prior probabilities or visit counts to control search exploration width and move sampling randomness.
- **Source Citation**: `ENGINE_REFERENCE.md` (`PolicyTemperature`), `ch10_learned_formula.tex:L170`.
- **Action Location**: `ENGINE_REFERENCE.md` (`--policy-softmax-temp`).

### Transposition
- **Definition**: Reaching an identical board position via different move orders, merged in graph-based MCTS to share visit counts and evaluations.
- **Source Citation**: Guide §3.3, `FIG-3.4`, `ch08_engineering_reality.tex:L75`.
- **Action Location**: `FIG-3.4`.

### UCB1 (Upper Confidence Bound 1)
- **Definition**: Classic multi-armed bandit algorithm selecting arm maximizing sample mean plus $\sqrt{c \ln N / n_i}$ confidence radius.
- **Source Citation**: Guide §0.6, `FIG-0.7`, Equation~\eqref{eq:E7}, `ch04_many_machines.tex:L110`.
- **Action Location**: `FIG-0.7`.

### UCT (Upper Confidence Bounds applied to Trees)
- **Definition**: Extension of UCB1 algorithm to tree search domains substituting subtree evaluation averages and parent visit counts.
- **Source Citation**: Guide §0.7, `FIG-0.8`, Equation~\eqref{eq:E9}, `ch05_machines_to_trees.tex:L140`.
- **Action Location**: `FIG-0.8`.

### Union Bound (Boole's Inequality)
- **Definition**: Probability inequality stating probability of at least one event occurring is bounded by sum of individual probabilities, justifying logarithmic confidence radius scaling.
- **Source Citation**: Guide §0.6, `FIG-0.7`, `ch04_many_machines.tex:L145`.
- **Action Location**: `FIG-0.7`.

### $U(a)$ (Exploration Bonus / Curiosity)
- **Definition**: Uncertainty bonus term $c_{\text{puct}} P(a) \frac{\sqrt{N}}{1+n_a}$ favoring unvisited moves with high neural priors.
- **Source Citation**: Guide §1.4, `FIG-0.2`, Equation~\eqref{eq:E10}, `ch06_building_puct.tex:L160`.
- **Action Location**: `FIG-1.10`, `FIG-2.2`.

### Value Head ($V$ / WDL)
- **Definition**: Neural network output head evaluating scalar net win value $V = w - l \in [-1, +1]$ or full $(w, d, l)$ probability vector.
- **Source Citation**: Guide §0.3, §1.2, `FIG-0.2`, Equation~\eqref{eq:E2}, `ch03_one_machine.tex:L140`.
- **Action Location**: `FIG-0.3`, `FIG-1.1`.

### Virtual Loss
- **Definition**: A fictitious loss booked on every edge of a selected-but-not-yet-evaluated path ($N \mathrel{+}= 1$, $W \mathrel{-}= 1$) so that the next selection goes elsewhere; removed and replaced by the true value when the evaluation returns.
- **Source Citation**: `ch08_engineering_reality.tex:L35-L64` (§"Virtual loss", incl. the worked example $N{=}9, W{=}7.2$).
- **Action Location**: **No UCI flag exists.** `lc0.exe` v0.32.1 exposes no `--virtual-loss` option — the word does not occur in `raw/lc0_help.txt`. The tunable neighbours are `--max-collision-events` (917) and `--max-collision-visits` (80000). See `ADDENDUM.md` §F.

### $w$ (Win Probability)
- **Definition**: Neural value head output probability representing expected win likelihood for side-to-move, bounded in $[0, 1]$.
- **Source Citation**: Guide §0.3, `FIG-0.2`, `FIG-0.3`, Equation~\eqref{eq:E1}, `ch02_currency_of_evaluation.tex:L70`.
- **Action Location**: `FIG-0.3`, `FIG-0.4`.

### WDL (Win-Draw-Loss)
- **Definition**: Three-element categorical probability vector $(w, d, l)$ returned by LC0's value head summing to $1.0$.
- **Source Citation**: Guide §0.3, `FIG-0.3`, `ch02_currency_of_evaluation.tex:L50`.
- **Action Location**: `FIG-0.3` (WDL Simplex).
