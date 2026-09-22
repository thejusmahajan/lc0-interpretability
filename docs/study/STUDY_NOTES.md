# Neural MCTS Visual Guide — Study Session Notes

This document records the Q&A study log for *Inside LC0's Mind: A Visual Guide*. All facts, values, formulas, and citations are verified against the authoritative corpus (`KNOWLEDGE_BASE.md`, `engine_data.json`, `simulate_search.py`, and chapters `ch01`–`ch16`).

---

## Cold-Start Check

### 1. Root Value and Move Priors
- **Question:** What is the network's value for the root of the K+P endgame position, and what are the four move priors?
- **Answer:**
  - **Root Value:** $V(\text{root}) = +0.97602$
  - **Priors:** $P(\text{Kd6}) = 45.13\%$, $P(\text{Kf6}) = 44.23\%$, $P(\text{Kf5}) = 5.38\%$, $P(\text{Kd5}) = 5.26\%$
- **Citations:** [KNOWLEDGE_BASE.md §2.1](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/visual_guide/KNOWLEDGE_BASE.md#L69-L73); [`simulate_search.py`:L23-L24](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/tools/simulate_search.py#L23-L24)

### 2. First Visits to Refuted Moves (Kf5 and Kd5)
- **Question:** At which node budget do Kf5 and Kd5 first receive a visit, what do they return, and what happens to them afterwards?
- **Answer:**
  - **Node Budget:** Budget **128** (first visited between budget 64 and 128).
  - **Returned Value:** Both return $Q = 0.000$ (with draw probability $d = 1.000$).
  - **Aftermath:** Neither move receives any further visits through budget 800 (staying at exactly 1 visit each for the next 672 search iterations).
- **Citations:** [KNOWLEDGE_BASE.md §2.4](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/visual_guide/KNOWLEDGE_BASE.md#L129-L157); `engine_data.json` (`positions.kp_endgame.ladder`)

### 3. Selection Behavior at Iteration 2
- **Question:** At iteration 2, Kd6 has the best measured score in the position and is not selected. Why?
- **Answer:** Visiting Kd6 in iteration 1 increased its visit count denominator $(1 + n_a)$ from 1 to 2, halving its exploration bonus $U(\text{Kd6})$. Consequently, its total selection score $S(\text{Kd6}) = Q + U$ fell below $S(\text{Kf6})$, whose unvisited exploration bonus $U(\text{Kf6})$ remained un-attenuated ($n_{\text{Kf6}} = 0$) on top of its FPU value ($Q_{\text{FPU}} = 0.75015$).
- **Citations:** [KNOWLEDGE_BASE.md §2.3](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/visual_guide/KNOWLEDGE_BASE.md#L96-L127); [`simulate_search.py`:L57-L62](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/tools/simulate_search.py#L57-L62)

### 4. Ground Truth: Kd6 vs. Kf6
- **Question:** Which is objectively better in that position, Kd6 or Kf6 — and how do you know?
- **Answer:** **Kd6** is objectively better. Stockfish 16.1 evaluation at depth 30 evaluates **Kd6 as mate in 12**, whereas **Kf6 is mate in 18** (both win, but Kd6 forces mate faster).
- **Citations:** [KNOWLEDGE_BASE.md §1](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/visual_guide/KNOWLEDGE_BASE.md#L48-L62); `engine_data.json` (`positions.kp_endgame.stockfish`)

---

## Session Q&A Log

### Q1: The 4-Phase MCTS Loop from the Opening Node
- **Question:** We start with the opening node at the top of our tree. We have the list of moves and their corresponding P's and V's. This is from the first hunch of the network. Now the Manager slides the moves to the MCTS along with the P's and V's. Then what happens?
- **Answer:** MCTS enters its 4-phase iteration loop:
  1. **Selection (Phase 1):** MCTS computes $S(a) = Q(a) + U(a)$ for all legal moves at the root. At Iteration 1 ($N=0$), $Q(a) = Q_{\text{FPU}} = V(\text{root}) = +0.97602$ for all moves, so ranking is decided by the highest prior $P(a)$ (Kd6 selected).
  2. **Expansion (Phase 2):** MCTS steps down the selected edge to create the child node in memory.
  3. **Evaluation (Phase 3):** The new leaf is evaluated by the neural network in a single forward pass to get its own $V(\text{leaf})$ and child priors.
  4. **Backpropagation (Phase 4):** The leaf value backs up to the root, updating $N$ and $W$, with the value flipping sign at each ply (alternating side-to-move frame).
- **Citations:** [ch05_machines_to_trees.tex §One iteration, four phases](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch05_machines_to_trees.tex#L41-L78); [ch07_search_by_hand.tex §Iteration 1](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch07_search_by_hand.tex#L97-L120); [KNOWLEDGE_BASE.md §2.6](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/visual_guide/KNOWLEDGE_BASE.md#L182-L195)

---

### Q2: What Policy Priors ($P$) and Value ($V$) Represent
- **Question:** Kd6, Kf6 are the two moves with almost equal P's and highest V's. What do these numbers represent?
- **Answer:**
  - **Correction on Premise:** Moves do *not* carry individual $V$ values from the root network call. The network gives **one** $V(\text{root})$ for the position as a whole, plus a set of Policy priors $P(a)$ for legal moves.
  - **Policy Prior $P(a \mid s)$:** A probability distribution predicting **which move a full MCTS search by this engine would end up choosing**. It is a fast intuition of search behavior, not a goodness score or evaluation of move outcomes.
  - **Position Value $V(s)$:** A scalar evaluation of the current position ($V = w - l$), ranging from $-1.0$ (loss) to $+1.0$ (win). $V(\text{root}) = +0.97602$ indicates White holds a near-certain win ($97.6\%$ win, $2.4\%$ draw, $0\%$ loss).
- **Citations:** [ch12_two_heads.tex §What the policy is a model of](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch12_two_heads.tex#L96-L100); [ch12_two_heads.tex §The policy sees the move; the value sees the consequence](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch12_two_heads.tex#L185-L186); [ch02_currency_of_evaluation.tex §The value of a position](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch02_currency_of_evaluation.tex#L57-L60); [KNOWLEDGE_BASE.md §2.1](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/visual_guide/KNOWLEDGE_BASE.md#L68-L77)

---

### Q3: Roles of $V$ vs. $P$ in MCTS Search
- **Question:** So V is the initial hunch of the game outcome which doesn't have any bearing on how MCTS sees the moves. MCTS searches only according to the P values. Correct?
- **Answer:** **No, that is not correct.** PUCT selection uses both $Q$ (derived from $V$) and $U$ (derived from $P$):
  $$S(a) = Q(a) + U(a)$$
  - **Role of $V$ in $Q(a)$:** For unvisited moves, $Q(a) = Q_{\text{FPU}} = V(\text{root}) - 0.33\sqrt{\sum_{\text{visited}}P}$. For visited moves, $Q(a)$ is the average of $V(\text{leaf})$ values backed up from leaf evaluations. $V$ directly sets the baseline exploitation score.
  - **Role of $P$ in $U(a)$:** $P(a)$ powers the exploration bonus $U(a) = c_{\text{puct}}(N) \cdot P(a) \cdot \frac{\sqrt{\max(N,1)}}{1+n_a}$.
- **Citations:** [ch07_search_by_hand.tex:L57](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch07_search_by_hand.tex#L57); [ch07_search_by_hand.tex:L99-L101](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch07_search_by_hand.tex#L99-L101); [ch05_machines_to_trees.tex §One iteration, four phases](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch05_machines_to_trees.tex#L71-L77); [KNOWLEDGE_BASE.md §2.2](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/visual_guide/KNOWLEDGE_BASE.md#L81-L85)

---

### Q4: Detailed Step-by-Step Mechanism of $V$ and $P$ When Presented to MCTS
- **Question:** Explain in detail what happens when the position value $V$ and the $P$ priors are presented to the MCTS engine. (Note: `neural_mcts_visual_guide_v2` omits these explicit formulas; recorded here as noted).
- **Answer:**
  1. **The Dilemma for Unvisited Moves:** When MCTS receives $V(\text{root})$ and $P$ at a new node, zero moves have been visited ($n_a = 0$). To calculate selection score $S(a) = Q(a) + U(a)$, MCTS needs a $Q(a)$ value for every candidate move.
  2. **Inheriting Parent $V$ via FPU:** Instead of using $Q=0$ (which would be wildly inaccurate in won or lost positions), unvisited moves inherit the parent position's value $V$, penalized by First Play Urgency (FPU):
     $$Q_{\text{FPU}}(a) = Q(\text{parent}) - 0.33 \cdot \sqrt{\sum_{\text{visited}} P}$$
  3. **Setting the Baseline (Iteration 1):** In our position, $V(\text{root}) = +0.97602$. Before any move is visited, $\sum_{\text{visited}} P = 0$, so $Q_{\text{FPU}} = +0.97602$ for all 4 moves. $V$ sets the baseline optimism for the entire move list.
  4. **Transition to Measured $Q$ (Iteration 2+):** When a move (e.g. Kd6) is visited, it is expanded and its leaf evaluated to get $V(\text{leaf}) = +0.96766$. Kd6 now has a *measured* average $Q(\text{Kd6}) = +0.96766$, while unvisited moves (Kf6, Kd5, Kf5) drop to $Q_{\text{FPU}} = 0.97184 - 0.33\sqrt{0.4513} = 0.75015$.
  5. **Summary:** $V$ provides the initial $Q_{\text{FPU}}$ baseline for unvisited moves, and downstream $V(\text{leaf})$ evaluations supply the measured $Q(a)$ values as search progresses.
- **Citations:** [ch06_building_puct.tex §First-play urgency](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch06_building_puct.tex#L273-L295); [ch07_search_by_hand.tex §Iteration 1 & 2](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch07_search_by_hand.tex#L97-L141); [KNOWLEDGE_BASE.md §2.2](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/visual_guide/KNOWLEDGE_BASE.md#L81-L85)

---

### Q5: Intuitive Step-by-Step Summary of Handing $V$ and $P$ to MCTS
- **Question:** Explain more simply. I have given my position evaluation and the moves priors to the MCTS. What happens next?
- **Answer:**
  1. **MCTS builds a scorecard:** Every candidate move gets a selection score $S = \text{Quality} + \text{Exploration}$.
  2. **$V$ fills in initial Quality:** Since no move has been played yet, MCTS uses the position evaluation $V = +0.97602$ as the starting Quality for *every single move*.
  3. **$P$ picks the first winner:** Because all moves tie on starting Quality ($+0.97602$), the move priors $P$ decide the winner. Kd6 ($P = 45.13\%$) gets the highest exploration bonus and is selected for Iteration 1.
  4. **The first move is tested:** MCTS plays Kd6 down the tree, and the network evaluates that new board position to get a real measured value ($V = +0.96766$).
  5. **MCTS updates the scorecard:** Kd6's temporary estimate is replaced with its real measured value ($+0.96766$). The unvisited moves drop slightly in estimate (FPU penalty). MCTS then recalculates scores and picks the move for Iteration 2 (Kf6).
- **Citations:** [ch07_search_by_hand.tex §Iteration 1 & 2](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch07_search_by_hand.tex#L97-L141); [KNOWLEDGE_BASE.md §2.3](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/visual_guide/KNOWLEDGE_BASE.md#L96-L120)

---

### Q6: Why Move Priors ($P$) Are Not the Final Scorecard
- **Question:** But the scorecard is already there. Correct? The P values are the scorecard. Why does it need to build another score?
- **Answer:** **No, $P$ values are NOT the final scorecard.** $P$ is merely a static initial guess (intuition), while $S = Q + U$ is a dynamic scorecard built during search (calculation).
  1. **$P$ is an imperfect guess, not an oracle:** In our K+P endgame, $P$ assigns $10.64\%$ of its attention to Kd5 and Kf5 — moves that throw away a win. Relying on $P$ alone would mean playing blunders.
  2. **Search is a policy improvement operator:** Search tests moves deeper down the tree, measures their actual outcomes ($V$), and builds a dynamic score $S = Q + U$. "Intuition guides calculation; calculation corrects intuition."
  3. **$P$ is static; $S$ updates live:** $P$ never changes during search. But $S$ continuously updates after every iteration as visits ($N$) pile up and real measured values ($Q$) back up.
- **Citations:** [ch07_search_by_hand.tex:L86-L90](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch07_search_by_hand.tex#L86-L90); [ch12_two_heads.tex §Why this improves anything](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch12_two_heads.tex#L226-L245); [KNOWLEDGE_BASE.md §2.1](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/visual_guide/KNOWLEDGE_BASE.md#L75-L77)

---

### Q7: Comparison to Human Candidate Move Selection & Calculation
- **Question:** Is it like human players listing candidate moves first and then analyzing each move?
- **Answer:** **Yes, conceptually, but with three crucial differences.**
  - **The Conceptual Analogy:** The relationship between $P$ and MCTS mirrors human thought: *"Intuition guides calculation; calculation corrects intuition."* Initial policy intuition ($P$) proposes where to start looking, and deep calculation ($Q$) verifies or refutes it.
  - **Difference 1 (No Hard Filter):** Humans usually select 2–3 candidate moves and ignore the rest entirely. MCTS assigns a non-zero prior $P$ to *every legal move* — there is no hard filter, so low-prior moves (like a 1.6% queen sac) can still be pulled in if visits pile up elsewhere.
  - **Difference 2 (Engine Intuition, Not Human):** $P$ models what *this engine's search* would choose, not human choice or human candidate selection.
  - **Difference 3 (Node-by-Node Interleaving):** Humans often analyze line A several plies deep before switching to line B. MCTS recalculates $S = Q + U$ across all candidate moves after *every single node visit*.
- **Citations:** [ch12_two_heads.tex:L244](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch12_two_heads.tex#L244); [ch12_two_heads.tex §What the policy is a model of](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch12_two_heads.tex#L96-L100); [ch12_two_heads.tex:L86-L88](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch12_two_heads.tex#L86-L88); [ch06_building_puct.tex:L335](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/design_session/book/chapters/ch06_building_puct.tex#L335)
