# MCTS & Neural Engine Concept Index (Question Router)

This index routes questions to their definitive primary and secondary locations across *Inside LC0's Mind: A Visual Guide* (v2.0, 44 pages), `ENGINE_REFERENCE.md`, `GLOSSARY.md`, and the 16 theoretical book chapters (`ch01`–`ch16`).

---

## 1. Topic $\rightarrow$ Location Table (80 Topics)

| Topic / Concept | Primary Location | Secondary Location |
|---|---|---|
| MCTS 4-Phase Iteration Cycle | Guide §1.5, `FIG-1.6` | `ch05_machines_to_trees.tex` §"The Four Steps" |
| Selection Phase & Score Max | Guide §1.5, `FIG-1.6`, `FIG-2.1` | `ch05` §"Selection" |
| Expansion Phase & Leaf Creation | Guide §1.5, `FIG-1.6`, `FIG-2.1` | `ch05` §"Expansion" |
| Evaluation Phase & Neural Pass | Guide §1.5, `FIG-1.3b`, `FIG-1.6` | `ch03_one_machine.tex` §"Evaluation" |
| Backpropagation & Sign Flip | Guide §1.5, `FIG-1.6`, `FIG-2.10` | `ch05` §"Backpropagation and the sign flip" |
| Expected Score Formula (E1) | Guide §0.3, `FIG-0.2`, `FIG-0.3` | `ch02_currency_of_evaluation.tex` §"WDL expectation" |
| Net Win Value $V = w - l$ (E2) | Guide §0.3, `FIG-0.2`, `FIG-0.4` | `ch02` §"Net value mapping" |
| Centipawn Logistic Mapping (E3) | Guide §0.3, `FIG-0.4` | `ch02` §"Centipawn conversion" |
| Incremental Sample Mean $W/N$ (E4) | Guide §0.4, `FIG-0.5` | `ch05` §"Running averages" |
| Standard Error $1/\sqrt{n}$ Law (E5) | Guide §0.5, `FIG-0.6` | `ch04_many_machines.tex` §"Standard error" |
| Hoeffding Concentration Bound (E6) | Guide §0.5, `FIG-0.6` | `ch04` §"Hoeffding inequality" |
| UCB1 Selection Rule (E7) | Guide §0.6, `FIG-0.7` | `ch04` §"UCB1 bandit rule" |
| Negamax Zero-Sum Backup (E8) | Guide §0.7, `FIG-0.8` | `ch05` §"Negamax formulation" |
| UCT Tree Selection Formula (E9) | Guide §0.7, `FIG-0.8` | `ch05` §"UCT for trees" |
| PUCT Selection Formula (E10) | Guide §1.4, `FIG-1.10` | `ch06_building_puct.tex` §"The PUCT equation" |
| First Play Urgency $Q_{\text{FPU}}$ (E11) | Guide §1.4, `FIG-2.B`, `FIG-2.0` | `ch06` §"First Play Urgency" |
| CPUCT Logarithmic Growth (E12) | Guide §1.4, `FIG-1.11d` | `ch06` §"CPUCT scaling" |
| Union Bound Derivation & $\ln N$ | Guide §0.6, `FIG-0.7` | `ch04` §"Choosing delta and union bounds" |
| Logarithmic Cheapness ($\sqrt{\ln M}$) | Guide §0.6(c), `FIG-0.7` | `ch04` §"Union bound logarithmic width" |
| Law of Large Numbers (LLN) | Guide §0.4, `FIG-0.5` | `ch04` §"Sample mean convergence" |
| Non-Uniform Monte Carlo Sampling | Guide §0.4 (Bridge Box) | `ch05` §"Biased tree exploration" |
| Brownian Motion & $1/\sqrt{n}$ Scaling | Guide §0.5 (Bridge Box), `FIG-0.6` | `ch04` §"Diffusion scaling" |
| Policy Prior Distribution $P(a)$ | Guide §1.2, `FIG-1.1` | `ch03` §"Policy vector" |
| Value Head WDL Probabilities | Guide §0.3, `FIG-0.3` | `ch02` §"WDL probabilities" |
| WDL Simplex Representation | Guide §0.3, `FIG-0.3` | `ch02` §"Simplex geometry" |
| Node Anatomy & Stored Fields | Guide §1.2, `FIG-1.2` | `ch05` §"Node datastructures" |
| Single-Pass Neural Evaluation | Guide §1.3, `FIG-1.3b` | `ch03` §"Forward pass" |
| GPU Batching & Pipeline | Guide §1.3, `FIG-1.4` | `ch08_engineering_reality.tex` §"Batching" |
| Search Engine & Net Separation | Guide §1.1, `FIG-1.A` | `ch01_what_an_engine_does.tex` §"Architecture" |
| Iteration 0 (Starting Tree State) | Guide §2.2, `FIG-2.0` | `ch07_search_by_hand.tex` §"Iter 0" |
| Iteration 1 (First Visit & Expansion) | Guide §2.2, `FIG-2.1` | `ch07` §"Iter 1" |
| Iteration 2 ($U$ Decay & Move Switch) | Guide §2.2, `FIG-2.2` | `ch07` §"Iter 2" |
| Depth Emergence from $U$ Decay | Guide §2.4, `FIG-2.11` | `ch07` §"Emergent depth" |
| Move Recommendation Criteria | Guide §2.3, `FIG-2.10` | `ch09_reading_a_tree.tex` §"Bestmove selection" |
| Refutation Discovery | Guide §3.1, `FIG-3.1` | `ch09` §"Trap detection" |
| Trap Avoidance Mechanism | Guide §3.2, `FIG-3.2` | `ch09` §"Refutation mechanics" |
| Transposition Graph Merging | Guide §3.3, `FIG-3.4` | `ch08` §"Transposition tables" |
| Graph vs Tree MCTS | Guide §3.3, `FIG-3.4` | `ch08` §"DAG search" |
| Position Sharpness & Volatility | Guide §4.1, `FIG-4.1` | `ch10_learned_formula.tex` §"Sharpness" |
| Policy Blindness Failure Mode | Guide §4.2, `FIG-4.2` | `ch06` §"Policy errors" |
| Steer Move / Sacrificial Lines | Guide §4.3, `FIG-4.4` | `ch16_style_as_objective.tex` §"Style" |
| 112 Input Planes Encoding | Guide §5.1, `ENGINE_REFERENCE.md` §2 | `ch10` §"Input representations" |
| Residual Block Architecture | Guide §5.1, `FIG-5.1` | `ch10` §"Residual networks" |
| Transformer / Attention Encoder | Guide §5.1, `ENGINE_REFERENCE.md` §2 | `ch11_attention.tex` §"Transformer body" |
| Policy Attention Head | Guide §5.1, `ENGINE_REFERENCE.md` §2 | `ch11` §"Attention policy" |
| Squeeze-and-Excitation (SE) | Guide §5.1, `ENGINE_REFERENCE.md` §2 | `ch10` §"SE blocks" |
| Attention Heatmaps & Salience | Guide §5.2, `FIG-5.3` | `ch14_attention_maps.tex` §"Salience maps" |
| Probing Neural Layers | Guide §5.3, `FIG-5.4` | `ch13_probes.tex` §"Linear probes" |
| Search Horizon & Lookahead | Guide §5.3, `FIG-5.4` | `ch15_lookahead.tex` §"Neural horizon" |
| Mind Change & Re-Evaluation | Guide §4.1, `FIG-4.1` | `ch09` §"Mind flips" |
| Product Visual Mapping Summary Card | Guide §6.2, `FIG-6.2` | `ch09` §"UI summary" |
| LC0 UCI Options (All 91) | `ENGINE_REFERENCE.md` §3 | `lc0_help.txt` |
| `CPuct` ($c_{\text{puct}}$ base) | `ENGINE_REFERENCE.md` §3, §5 | Guide §1.4, `FIG-1.10` |
| `CPuctBase` ($c_{\text{mod}}$) | `ENGINE_REFERENCE.md` §3, §5 | Guide §1.4, `FIG-1.10` |
| `CPuctFactor` ($c_{\text{factor}}$) | `ENGINE_REFERENCE.md` §3, §5 | Guide §1.4, `FIG-1.10` |
| `FpuValue` ($c_{\text{fpu}}$) | `ENGINE_REFERENCE.md` §3, §5 | Guide §1.4, `FIG-2.B` |
| `FpuStrategy` (reduction / absolute) | `ENGINE_REFERENCE.md` §3 | Guide §1.4, `FIG-2.B` |
| `FpuStrategyAtRoot` / `FpuValueAtRoot` | `ENGINE_REFERENCE.md` §3, §5 | `ch06` §"Root FPU" |
| `RootHasOwnCpuctParams` | `ENGINE_REFERENCE.md` §3, §5 | Guide §1.4 |
| `PolicyTemperature` | `ENGINE_REFERENCE.md` §3, §4 | `ch10` §"Temperature" |
| `DirichletNoiseAlpha` / `DirichletNoiseEpsilon` | `ENGINE_REFERENCE.md` §3, §4 | `ch06` §"Noise" |
| `SyzygyPath` / `SyzygyFastPlay` | `ENGINE_REFERENCE.md` §3, §4 | `ch08` §"Tablebases" |
| `UCI_ShowMovesLeft` / MLH | `ENGINE_REFERENCE.md` §3, §4 | `ch12_two_heads.tex` |
| `UCI_ShowWDL` / Raw WDL Display | `ENGINE_REFERENCE.md` §3, §4 | `ch02` §"WDL display" |
| `Contempt` / `UCI_RatingAdv` | `ENGINE_REFERENCE.md` §3, §4 | `ch02` §"Contempt" |
| `DrawScore` / `TwoFoldDraws` | `ENGINE_REFERENCE.md` §3, §4 | `ch02` §"Draw evaluation" |
| `SmartPruningFactor` / Minimum Batches | `ENGINE_REFERENCE.md` §3, §4 | `ch08` §"Pruning" |
| `VirtualLoss` / Threads | `ENGINE_REFERENCE.md` §3 | `ch08` §"Parallel search" |
| `TaskWorkers` / `MinimumPickingWork` | `ENGINE_REFERENCE.md` §3, §4 | `ch08` §"Parallel task workers" |
| `MaxPrefetch` / Cache Prefetching | `ENGINE_REFERENCE.md` §3, §4 | `ch08` §"Prefetching" |
| `NNCacheSize` / Evaluation Cache | `ENGINE_REFERENCE.md` §3 | `ch08` §"Neural caching" |
| `Backend` / `BackendOptions` | `ENGINE_REFERENCE.md` §3 | `ch08` §"GPU execution" |
| `RamLimitMb` / Memory Limits | `ENGINE_REFERENCE.md` §3 | `ch08` §"Memory allocation" |
| `MoveOverheadMs` / Time Manager | `ENGINE_REFERENCE.md` §3 | `ch08` §"Time management" |
| Cross-Entropy vs MSE in LC0 | `STUDY_CROSS_ENTROPY_AND_OPTIMIZATION.md` §2 | `ch12` §"Two Heads", `ch02` §"WDL" |
| WDL 3-Class Loss vs AlphaZero MSE | `STUDY_CROSS_ENTROPY_AND_OPTIMIZATION.md` §2 | `ch02` §"WDL probabilities" |
| PyTorch Training Loop & CE Optimization | `STUDY_CROSS_ENTROPY_AND_OPTIMIZATION.md` §3, §4 | `01_pytorch_fundamentals_and_headstart.md` |

---

## 2. Question-Shape $\rightarrow$ Route

When taking student questions, route by question structure:

1. **"Why does X have that mathematical form?"** (e.g. why $\ln N$, why $\sqrt{N}$, why $1/(1+n_a)$)
   - **Route**: Guide §0.6 (Union bounds), §1.4 (PUCT derivation), `FIG-1.11`, Equations E1--E12. Escalate to `ch04` or `ch06` for multi-page mathematical proofs.
2. **"What is the exact numerical value of X in LC0?"** (e.g. what is $c_{\text{puct}}$, what is $Q_{\text{FPU}}$)
   - **Route**: `figure_data.json` for benchmark values; `ENGINE_REFERENCE.md` §3 & §5 for binary defaults.
3. **"Is move X good in position Y?"**
   - **Route**: Refuse to analyze or give model opinions. State clearly: *"Move quality can only be determined by executing engine search (`lc0.exe` or `stockfish`), not from model memory."*
4. **"What would happen if I changed parameter X?"** (e.g. changing `SmartPruningFactor` or `PolicyTemperature`)
   - **Route**: Look up `ENGINE_REFERENCE.md` §3 for flag name and verbatim help text description, then state plainly: *"The exact performance effect of changing this flag in this build has not been measured here."*
5. **"How does the neural network represent X internally?"** (e.g. history planes, attention layers, probes)
   - **Route**: Guide Part 5 (§5.1--§5.3), `ENGINE_REFERENCE.md` §2 (`describenet` table), escalate to `ch10`--`ch15` for network probing details.

---

## 3. Cross-Reference Map (Guide ↔ Book Chapters)

Use this map to escalate from visual guide summaries to deep theoretical book chapters:

- **Guide §0.3--§0.5 (Expectation & Concentration)** $\longleftrightarrow$ `ch02` (*Currency of Evaluation*) & `ch04` (*Many Machines*)
- **Guide §0.6 (Union Bounds & UCB1)** $\longleftrightarrow$ `ch04` (*Choosing $\delta$ and Union Bounds*)
- **Guide §0.7 (Negamax & UCT)** $\longleftrightarrow$ `ch05` (*Machines to Trees*)
- **Guide §1.2--§1.3 (Node Anatomy & Policy/Value)** $\longleftrightarrow$ `ch03` (*One Machine*)
- **Guide §1.4--§1.5 (PUCT Derivation & Iteration Cycle)** $\longleftrightarrow$ `ch06` (*Building PUCT*)
- **Guide §2.1--§2.4 (Search by Hand & Depth Emergence)** $\longleftrightarrow$ `ch07` (*Search by Hand*)
- **Guide §3.1--§3.3 (Refutations & Transposition Graphs)** $\longleftrightarrow$ `ch08` (*Engineering Reality*) & `ch09` (*Reading a Tree*)
- **Guide §4.1--§4.3 (Traps, Blindness & Style)** $\longleftrightarrow$ `ch10` (*Learned Formula*) & `ch16` (*Style as Objective*)
- **Guide §5.1--§5.3 (Neural Architectures & Probes)** $\longleftrightarrow$ `ch11` (*Attention*), `ch12` (*Two Heads*), `ch13` (*Probes*), `ch14` (*Attention Maps*), `ch15` (*Lookahead*)

---

## 4. The Honest Gap List

The following topics are **uncovered or unmeasured** in this corpus. The study companion must explicitly acknowledge these as gaps rather than attempting to answer from memory:

1. **Stub Chapters & Appendices**:
   - `ch17_real_sharpness.tex`, `ch18_numbers_to_sentences.tex`, `ch19_capstone.tex` (stub placeholders).
   - `appA_notation.tex` through `appF_sources.tex` (stub placeholders).
2. **Thinly Documented LC0 Options**:
   - `KLDGainAverageInterval`, `MinimumKLDGainPerNode`, `MinimumProcessingWork`, `MinimumPerTaskProcessing`, `IdlingMinimumWork`, `ThreadIdlingThreshold`, `SearchSpinBackoff`, `RamLimitMb` (help text gives range/defaults but lacks detailed mathematical formulas).
3. **Training & Optimization Pipeline**:
   - Self-play game generation mechanics, reinforcement learning loss functions, policy/value gradient updates, learning rate schedules, Dirichlet noise scheduling during training, TPU/GPU cluster orchestration (the corpus covers *inference search*, not network training).
