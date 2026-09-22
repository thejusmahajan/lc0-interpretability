# Study Dialogue: Neural MCTS Foundations & First Principles

> **Purpose**: This document contains the complete, verbatim question-and-answer study dialogue between Thejus and the AI tutor exploring the foundations of Monte Carlo Tree Search (MCTS) in Leela Chess Zero (LC0), based on `docs/study/guide/neural_mcts_visual_guide_v2.pdf`.
>
> It captures the student's exact mental models, clarifying questions, and preferred pedagogical style (bare-bones, first-principles, zero-jargon, plain text, concrete board examples) to guide the Leader Agent in drafting a companion study guide.

---

## Leader Prompt: Intentions & Instructions for the Companion Study PDF

```markdown
# PROMPT FOR LEADER AGENT: Companion Study Guide for Neural MCTS

**Goal**: Create a companion step-by-step Study PDF alongside `docs/study/guide/neural_mcts_visual_guide_v2.pdf`.

**Pedagogical Style & Core Requirements**:
1. **Down to the Constituent Elements**: Break every equation and mechanism down to its physical origin and causal mechanism. Never introduce a term without explaining what physical entity it represents.
2. **Zero Unrendered LaTeX**: Use clean, plain text, ASCII diagrams, and standard arithmetic expressions that are immediately human-readable.
3. **Explicit State vs Action Grounding**: Never confuse or blur the distinction between State `s` (a discrete board position node) and Action `a` (a candidate move edge leaving that node).
4. **Distinguish Unvisited vs Visited Phases (FPU)**:
   - Explicitly trace how unvisited candidate moves initially inherit the parent position's prior evaluation as a baseline floor (`Q_FPU`), with policy priors `P` driving initial curiosity (`U`).
   - Explicitly trace the transition moment when a move is visited for the first time: the default placeholder is completely discarded and replaced by the real leaf evaluation from the child position.
5. **Concrete Numerical Traces**: Use small, concrete positions (like the 4-legal-move King+Pawn endgame `4k3/8/4K3/4P3/8/8/8/8 w - - 0 1`) so that every addition, division, visit increment, and sign flip can be calculated and verified by hand.
6. **Address Common Misconceptions**: Address the exact questions raised in the study log below (e.g. why bad moves don't drag down a position's average, why depth emerges naturally from re-visiting moves, and why the neural network outputs one value per position rather than one value per move).
```

---

## Verbatim Study Conversation Log

### Segment 1: Starting the Study & WDL Basics

**USER**:
> Let them run. In parallel lets do something else.
> I am finding difficulty in understanding this. Teach me. We already have a good pdf `C:\Users\Admin\Documents\chess_speak_out_loud\docs\study\guide\neural_mcts_visual_guide_v2.pdf`. I want to study this step by step. Assume the role of a teacher and teach me this. Small chunks at a time. Start!

**ASSISTANT**:
> Welcome! We are going to walk through **Inside LC0’s Mind: A Visual Guide** step-by-step. 
> 
> We will take this one bite-sized concept at a time, connect the math directly to real chess intuition, and make sure every piece clicks before moving to the next.
> 
> ---
> 
> # Lesson 1: How Leela Evaluates a Position (WDL & Net Value)
> 
> Traditional engines like Stockfish talk in **centipawns** (e.g., `+1.50` means "White is up 1.5 pawns"). 
> 
> Leela Chess Zero (LC0) does not think in pawns at all. Internally, its neural network outputs **probabilities of game outcomes**:
> 
> Win (w), Draw (d), Loss (l)
> 
> Because a game must end in one of these three outcomes, they always sum to 1.0:
> w + d + l = 1
> 
> ---
> 
> ### 1. Expected Score (E[score])
> 
> In tournament chess, a win gives you 1.0 point, a draw gives 0.5 points, and a loss gives 0.0 points. 
> 
> So the **expected tournament score** from a position is:
> E[score] = w + 0.5 * d   (Range: 0.0 to 1.0)
> 
> * A completely winning position (w=1, d=0, l=0) has E[score] = 1.0.
> * A completely drawn position (w=0, d=1, l=0) has E[score] = 0.5.
> * A completely lost position (w=0, d=0, l=1) has E[score] = 0.0.
> 
> ---
> 
> ### 2. The Internal Metric: Net Value (V)
> 
> For internal search calculations, Leela maps this onto a symmetric scale from **-1.0 (guaranteed loss)** to **+1.0 (guaranteed win)** with **0.0 being a dead draw**.
> 
> This is called the **Net Value (V)**:
> V = w - l   (Range: -1.0 to +1.0)
> 
> Notice what happens:
> * If w = 1.0 -> V = +1.0 (Guaranteed Win)
> * If w = l -> V = 0.0 (Balanced / Drawn, regardless of whether d=1.0 or w=0.4, l=0.4)
> * If l = 1.0 -> V = -1.0 (Guaranteed Loss)
> 
> ---
> 
> ### 3. The Negamax Golden Rule (Point of View)
> 
> In LC0, **V is always evaluated from the point of view of the player whose turn it is to move at that specific node**:
> 
> * If it is White's turn to move and V = +0.90, White is winning.
> * If it is Black's turn to move and V = +0.90, **Black is winning** (from Black's POV, +0.90 means Black has a 90% net win advantage).

---

### Segment 2: Understanding Epistemic Uncertainty in WDL

**USER**:
> The expected score. Lets deal with that first. How can a position have both win, draw and loss probabilities?

**ASSISTANT**:
> In pure mathematics (by Zermelo’s Theorem), chess is a deterministic, perfect-information game. If you could calculate every single possibility to the end of the universe, the true theoretical outcome of any position is **exactly one number**:
> * It is a forced **Win** (w = 1.0, d = 0, l = 0), or
> * It is a forced **Draw** (w = 0, d = 1.0, l = 0), or
> * It is a forced **Loss** (w = 0, d = 0, l = 1.0).
> 
> So why does the neural network output something like w = 0.60, d = 0.30, l = 0.10?
> 
> The answer comes down to **two things**:
> 
> ---
> 
> ### 1. Epistemic Uncertainty (The "Imperfect Oracle" Reality)
> 
> Because chess has more than 10^40 reachable positions, no computer has calculated chess to the absolute end. 
> 
> The probabilities are **not physical dice rolls**—they represent the network's **degree of belief** (epistemic uncertainty) based on the millions of self-play games it studied during training:
> 
> > *"When games reached positions with these pawn structures, king safety levels, and piece balances, White won 60% of the time, Black held a draw 30% of the time, and Black managed to counter-attack and win 10% of the time."*
> 
> The network's value head is trained with cross-entropy loss against the real outcomes of its self-play games, so its output directly reflects that empirical frequency.
> 
> ---
> 
> ### 2. The Power of WDL: Not All "Equal" Positions Are the Same
> 
> Traditional engines like older Stockfish condensed everything into a single number: centipawns (e.g., `+0.70`). 
> 
> But a single number hides the nature of the position! Compare these two positions:
> 
> #### Position A: An Explosive Sicilian Brawl
> * w = 0.55
> * d = 0.10
> * l = 0.35
> * E[score] = 0.55 + 0.5 * (0.10) = **0.60**
> 
> #### Position B: A Dry Rook Endgame (Up a Doubled Pawn)
> * w = 0.20
> * d = 0.80
> * l = 0.00
> * E[score] = 0.20 + 0.5 * (0.80) = **0.60**
> 
> Notice:
> * **Both positions have the exact same Expected Score (0.60)** (roughly +0.80 in classical centipawns).
> * But in **Position A**, the draw probability is only 10%. It is razor-sharp; someone is likely getting mated, and White has a 35% risk of losing.
> * In **Position B**, the loss probability is 0%. White can press risk-free for the win, with an 80% chance that Black holds the draw.
> 
> Having distinct w, d, l probabilities allows Leela to understand **sharpness vs. safety** in a way a single scalar number never could.

---

### Segment 3: Net Value V and the Incremental Sample Mean Q

**USER**:
> Yes. E is computed from WDL and it is clear. What about the V value? And also move forward to the next step.

**ASSISTANT**:
> ### Part 1: What is the Net Value (V)?
> 
> Now that Expected Score E[score] = w + 0.5*d is clear, where does V come from?
> 
> V = w - l   (Range: -1.0 to +1.0)
> 
> Notice the direct mathematical connection between V and E[score]. Since w + d + l = 1 (meaning d = 1 - w - l):
> 
> E[score] = w + 0.5 * (1 - w - l) = 0.5 + 0.5 * (w - l) = 0.5 + 0.5 * V
> 
> Rearranging gives:
> **V = 2 * E[score] - 1**
> 
> V is simply the tournament expected score **centered at zero**:
> * **E[score] = 0.50 (Draw/Equal)** -> V = 2*(0.50) - 1 = **0.0**
> * **E[score] = 1.00 (Win)** -> V = 2*(1.00) - 1 = **+1.0**
> * **E[score] = 0.00 (Loss)** -> V = 2*(0.00) - 1 = **-1.0**
> 
> #### Why does the search use V instead of E[score]?
> Because chess is a **zero-sum game**. If White has an advantage of +0.60, then from Black's perspective, Black is at -0.60.
> 
> When we switch turns between White and Black, flipping the evaluation is as simple as **multiplying by -1**:
> V_parent = -V_child
> 
> ---
> 
> # Lesson 2: Why a Move's Value Must Be Sampled (Q)
> 
> Now we step into the search tree.
> 
> When Leela wants to evaluate a candidate move a (say, `1. e4`), it doesn't just look at it once. It explores continuations down that branch over many iterations.
> 
> Every time the search explores a continuation of move a, it reaches a position at the bottom of the tree and gets a new evaluation x_i in [-1, +1] from the neural network.
> 
> ```
> Iteration 1 down move a: returns x1 = +0.80
> Iteration 2 down move a: returns x2 = +0.20 (opponent found a good defense!)
> Iteration 3 down move a: returns x3 = +0.50
> ```
> 
> To know how good move a is overall, the engine tracks two basic quantities:
> 1. **n_a (or N(s,a))**: The number of times this move has been visited.
> 2. **W(s,a)**: The sum of all values returned from those visits: W = x1 + x2 + ... + xn.
> 
> The move's current measured quality is the **Sample Mean**, called **Q(s, a)**:
> 
> **Q(s, a) = W(s, a) / n_a**
> 
> ---
> 
> ### The Incremental Update Equation (E4 in the Guide)
> 
> In computer code, instead of re-summing all past visits from scratch every time, LC0 updates Q incrementally whenever a new sample x_n arrives:
> 
> Q_n = Q_(n-1) + (1 / n) * (x_n - Q_(n-1))
> 
> Look at the beauty of this formula:
> * On visit **n = 2**, the step size is 1/2 = 0.50. A new surprise changes Q drastically.
> * On visit **n = 100**, the step size is 1/100 = 0.01. A single new result barely nudges the established average.
> 
> As visit counts grow, **Q(s, a) stabilizes and converges** to the true value of that move.

---

### Segment 4: Clarifying x_n vs Q_n

**USER**:
> In fig 1.5, x1 is on top and x2 is down as two parallel lines and Qn is the y axis. If the equation is true, then xn must be related to Qn. Correct?

**ASSISTANT**:
> **Exactly right!** You have spotted the exact mathematical relationship.
> 
> Let's break down what Figure 1.5 is showing:
> 
> ```
>  y-axis (Evaluation)
>   ▲
> 0.90 ├ - - - - - - - - - - - - - - - - - - - - - - - - - - -  x1 = 0.90 (1st sample was very optimistic)
>      │       ● (Q1 = 0.90)
>      │
> 0.55 ├───────┼───────● (Q2 = 0.55) ─── Steps down by 0.35! (halfway toward x2)
>      │       │       │
>      │       │       │       ● ─── ● ─── ● ─── ● (Q6 = 0.683)  [Fluctuations get smaller and smaller]
>      │       │       │
> 0.20 ├ - - - - - - - - - - - - - - - - - - - - - - - - - - -  x2 = 0.20 (2nd sample found a defense)
>      └───────┴───────┴───────┴───────┴───────┴───────►
>              n=1     n=2     n=3     n=4     n=5     n=6      x-axis (Visit Count n)
> ```
> 
> ---
> 
> ### What x_n and Q_n Mean Here:
> 
> 1. **x_n is the instantaneous sample**:  
>    It is the raw evaluation returned by the neural network at the leaf node on the n-th visit.
> 2. **Q_n is the accumulated running mean**:  
>    It is the overall score of the move after averaging all n visits: Q_n = (x1 + x2 + ... + xn) / n.
> 
> ---
> 
> ### Why the Formula Looks Like a Learning Update:
> 
> Look at Equation E4 written this way:
> 
> Q_n = Q_(n-1) + [Step Size (1 / n)] * [Prediction Error (x_n - Q_(n-1))]
> 
> * On **Visit 1**: Q1 = x1 = 0.90.
> * On **Visit 2**: The new visit returns x2 = 0.20.  
>   The "surprise" is (0.20 - 0.90) = -0.70.  
>   The step size is 1/2.  
>   So Q2 = 0.90 + 0.5 * (-0.70) = **0.55** (A huge jump of -0.35!).
> * On **Visit 6**: Even if a sample differs from the average, the step size is only 1/6 (about 0.02 to 0.03). The average barely wiggles.

---

### Segment 5: Where x_n Comes From (Leaf Node Evaluations)

**USER**:
> I don't understand. So the x_n are the values from the value heads, that is V's of each position arising when a new candidate is visited. Correct?

**ASSISTANT**:
> **YES, 100% correct!** 
> 
> You have grasped the exact mechanism. Let's trace it step-by-step so you can see the physical journey of an x_n:
> 
> ---
> 
> ### The Journey of x_n:
> 
> Suppose you are at the **Root Position** (White to move) and looking at candidate move **`Kd6`**:
> 
> ```
>                        [ ROOT (White to move) ]
>                               │
>                     Move a = "Kd6" (Edge)
>                               │
>                               ▼
>                  [ Child Node s1 (Black to move) ]
>                               │
>                     Move "Kd8" (Edge)
>                               │
>                               ▼
>                  [ Leaf Node s2 (White to move) ]
>                     ▲
>                     │ ◄── The Neural Network evaluates this leaf!
>                     │     Value Head outputs: V(s2) = +0.95
> ```
> 
> 1. **The Search walks down** the tree along move `Kd6` until it hits a brand-new position at the bottom (a **leaf node**).
> 2. **The Neural Network's Value Head** evaluates that leaf position and outputs a single number: V(leaf).
> 3. **That number travels back up the tree** to the root (with its sign flipped at each step for White/Black).
> 4. When that number arrives back at the `Kd6` branch at the root, **that is your x_n sample!**
> 
> ---
> 
> ### The Critical Rule: "One Value Per Position, Not Per Move" (Section 2.9 of the guide)
> 
> A very common beginner mistake is to think:
> > *"When Leela looks at a position, does the neural network output a separate value for each legal move?"*
> 
> **No!** The neural network never outputs a value for a move. 
> * The neural network only evaluates a **board position** s, producing one single V(s).
> * A move gets a value only when the search physically **makes the move** to create a child position, and the neural network evaluates that child position!
> 
> So over 6 visits to `Kd6`, the search explores 6 different sub-lines, getting 6 leaf evaluations: x1, x2, x3, x4, x5, x6. 
> 
> The average of those 6 leaf evaluations is:
> **Q(Kd6) = (x1 + x2 + ... + x6) / 6**

---

### Segment 6: What is State s vs Action a?

**USER**:
> What then is s?

**ASSISTANT**:
> In reinforcement learning and tree search, **s stands for "State"**.
> 
> In chess, **s is simply a specific board position**. 
> 
> ---
> 
> ### What defines a state s?
> 
> A state s contains everything needed to describe the exact situation on the board (essentially a FEN string):
> 1. **Piece placement**: Where all the pieces are on the 64 squares.
> 2. **Side to move**: Is it White's turn or Black's turn?
> 3. **Castling rights**: Can White or Black castle kingside/queenside?
> 4. **En passant square**: Is an en-passant capture possible this ply?
> 5. **Repetition history**: Has this position occurred before?
> 
> ---
> 
> ### How s and a make up the search tree:
> 
> Think of the search tree as alternating between **States (s)** and **Actions (a)**:
> 
> ```
>         [ State s (Root Position) ]       ◄── A tree NODE (Board configuration)
>                      │
>             Action a = "1. e4"            ◄── A tree EDGE (The move taken)
>                      │
>                      ▼
>         [ State s' (After 1. e4) ]        ◄── A new tree NODE (New board configuration)
>                      │
>             Action a' = "1... c5"         ◄── Another EDGE
>                      │
>                      ▼
>        [ State s'' (Sicilian Defense) ]   ◄── A deeper NODE
> ```
> 
> * **s (Node)** is the *noun*: "Where we are right now" (the board).
> * **a (Edge)** is the *verb*: "What move we make from this position".
> * **Q(s, a)** is: "The average value of choosing move a when standing in position s".
> * **P(a | s)** is: "The probability/prior of move a given position s".

---

### Segment 7: Why Separate s and a?

**USER**:
> Action 'a' is essentially state 's' because a is the causal factor of s. Why then differentialtes these two? A new move a means a new position s. Isn't it?

**ASSISTANT**:
> In a deterministic game like chess, making move a from position s indeed leads deterministically to a new position s':
> 
> s' = Transition(s, a)
> 
> So why do mathematicians and search engines maintain a strict distinction between **State s** and **Action a**? 
> 
> There are **3 crucial reasons**:
> 
> ---
> 
> ### 1. One State s Contains Multiple Competing Actions a
> When you are standing at position s, you are standing at a **fork in the road**. You haven't moved yet.
> 
> * State s is the **crossroads** (the node).
> * Actions a1, a2, ..., a35 are the **35 different paths** leaving that crossroads.
> 
> When the neural network evaluates position s:
> * It takes **State s** as its single input (the board).
> * It outputs a probability distribution over all the candidate **Actions a**:
>   P(a1 | s) = 45%, P(a2 | s) = 30%, P(a3 | s) = 5% ...
> 
> The notation P(a | s) explicitly reads: *"What is the probability of choosing action a, **given that we are currently in state s**?"*
> 
> ---
> 
> ### 2. Transpositions: Different Actions Can Lead to the Same State
> In chess, different sequences of actions frequently reach the **exact same board position**:
> 
> * Line 1: `1. d4 Nf6 2. c4 e6 3. Nc3` -> **State S_Nimzo**
> * Line 2: `1. c4 e6 2. d4 Nf6 3. Nc3` -> **State S_Nimzo**
> * Line 3: `1. Nc3 Nf6 2. d4 e6 3. c4` -> **State S_Nimzo**
> 
> The first moves (`1. d4`, `1. c4`, `1. Nc3`) are completely different actions from the start position with different priors, but the resulting state S_Nimzo is identical. If we didn't separate actions from states, you couldn't represent transpositions.
> 
> ---
> 
> ### 3. Unvisited Moves: An Action Can Exist Before Its Child State is Created
> In the computer's memory during search:
> * When Leela expands the root position s, it lists all 35 legal candidate moves (Actions a).
> * But Leela has **not yet visited 33 of them**.
> * Those 33 unvisited moves exist in memory purely as **edges (Actions a)** with a prior P(a | s) and visit count n_a = 0.
> * The child State s' at the other end of that edge **has not even been built or evaluated yet!**
> 
> Only when the search chooses to step down that edge does it spend memory to create and evaluate the child State s'.

---

### Segment 8: Confirming the Node/Edge Mental Model

**USER**:
> So S is the position that the leaf node creates and a's are the branches from the leaf node s?

**ASSISTANT**:
> **YES! Exactly.**
> 
> Every single node in the tree—whether it is the **Root**, a **middle node**, or a **newly created Leaf**—is a position s. And the branches coming out of it are the candidate moves a.
> 
> ---
> 
> ### What happens the instant a new Leaf Node s is created:
> 
> When the search decides to explore a new line and creates a Leaf Node s:
> 
> ```
>                     [ Parent Node ]
>                           │
>                   (Chosen move a)
>                           │
>                           ▼
>             ╔══════════════════════════════╗
>             ║     NEW LEAF NODE (State s)  ║  ◄── The new board position
>             ║                              ║
>             ║  The Neural Network runs     ║
>             ║  ONE forward pass on s:      ║
>             ║                              ║
>             ║  1. Value Head:              ║
>             ║     V(s) = +0.82             ║  ──► (Backpropagates up to root)
>             ║                              ║
>             ║  2. Policy Head:             ║
>             ║     P(a1 | s) = 60%          ║  ──► Prepares the new branches
>             ║     P(a2 | s) = 30%          ║      ready for future visits!
>             ║     P(a3 | s) = 10%          ║
>             ╚══════════════════════════════╝
>                      /    │    \
>                     /     │     \
>                   (a1)   (a2)   (a3)   ◄── Future candidate moves from here
> ```
> 
> 1. **The Leaf Node is State s** (the new board position).
> 2. **The Value Head outputs V(s)**: This is the evaluation that travels back up the tree to update the averages (Q).
> 3. **The Policy Head outputs P(a | s)**: This populates all the outgoing branches (a1, a2, a3 ...) with their prior probabilities, so the search knows how promising each branch looks if it decides to visit this leaf again in a future iteration.

---

### Segment 9: The Prior State s vs Outgoing Moves a

**USER**:
> So, thinking 'a' as a position is incorrect. These are moves and 's' the the position that is prior to a's?

**ASSISTANT**:
> **YES! You have hit the nail right on the head.**
> 
> * **`a` is NEVER a position.** `a` stands for **Action** (a chess **move**, like `1. e4`, `Nf3`, or `Kd6`).
> * **`s` is the POSITION.** `s` stands for **State** (the board setup: pieces on squares, who is to move, castling rights).
> * **`s` is the position *prior* to `a`**: You are standing on board position `s`, and `a` is one of the legal moves you can choose to play from that position.

---

### Segment 10: Non-Uniform Sampling (Why Bad Moves Don't Drag Down Average Quality)

**USER**:
> I want to understand the move search mechanism and the quality value. So Q=W/N, this is understood. Now, lets say I go to a move a1 from a state 's_1' and it has a high value. All the other moves a_n, n ne 1, are all bad or even blunders. This would drastically reduce the average value of the parent move that caused the state s_1. Now if there is another state s_2, its candidates a_1 is of lesser than the a_1 of s_1 and a_n's are also not bad so that in average s_2 has a higher quality. But that would make the correct a_1 of s_1 rejected because the overall s_1 quality is low.

**USER**:
> You are writing latex here and it is not translated to equations. Completely gibberish.

**ASSISTANT**:
> I apologize! I will stop using LaTeX formatting entirely and write everything in clean, plain text and clear diagrams.
> 
> Here is the exact answer to your question in plain language:
> 
> ---
> 
> ### The Question:
> If a position has **one brilliant move (a1)** and **29 terrible blunders (a2 to a30)**, won't the 29 blunders drag down the average quality of the position?
> 
> ### The Answer:
> **No, because Leela does not visit all moves equally.**
> 
> Here is what happens inside the search over 1,000 visits:
> 
> ```
>                   [ Position s1 (Your turn) ]
>                   Total visits: 1,000
>                   Average Score Q: +0.90 (Winning!)
>                          /      |      \
>         ┌───────────────┘       |       └──────────────┐
>         ▼                       ▼                      ▼
>   Move a1 (Brilliant)     Move a2 (Blunder)      Move a30 (Blunder)
>   Visits: 970             Visits: 1              Visits: 1
>   Score: +0.95            Score: -0.80           Score: -0.80
> ```
> 
> ---
> 
> ### Why this happens step-by-step:
> 
> 1. **On Visit 1 to a blunder (Move a2)**:  
>    The neural network evaluates it and says: *"This is a disaster, score is -0.80."*
> 2. **The engine immediately abandons it**:  
>    Because its score is -0.80, the search engine says: *"I am never looking down this line again."* That blunder stays stuck at **1 visit forever**.
> 3. **On Visit 1 to the winning move (Move a1)**:  
>    The neural network says: *"This is winning, score is +0.95."*
> 4. **The engine pours all its attention into the winning move**:  
>    Out of the next 1,000 search visits, the engine spends **970 visits on Move a1** and **almost 0 visits on the blunders**.
> 
> ---
> 
> ### Doing the math in plain numbers:
> 
> The total score added up for the position:
> * Points from the brilliant move: 970 visits * (+0.95) = **+921.5**
> * Points from the 29 blunders combined: 29 visits * (-0.80) = **-23.2**
> 
> Total accumulated points = +921.5 - 23.2 = **+898.3**
> 
> Now divide by the 1,000 total visits:
> **Average Q = +898.3 / 1,000 = +0.90 (Still a clear win!)**
> 
> ---
> 
> ### The Takeaway:
> In MCTS, a position's average is **weighted by visits**. 
> 
> Because bad moves get abandoned after just 1 look, they only contribute 1% to the total score. The winning move gets 97% of the visits, so the position's score is almost entirely determined by the best move.

---

### Segment 11: Concrete Example (Tracing 4-Move Endgame Iteration by Iteration)

**USER**:
> Wait. The position 's' has an initial value and each of its candidates have probabilites attached to it. Does these probabilities play a role in running many iterations over the move 'a' having a high value?
> Don't use latex.
> I don't understand your explanation. Seems like you are mixing up things. Lets have an example position and go from there.

**ASSISTANT**:
> Let us use the exact chess position from Chapter 2 and 3 of the visual guide. It has only 4 legal moves, so we can track every single number cleanly.
> 
> ---
> 
> ### The Position: King and Pawn Endgame
> 
> * **Board**: White King on e6, White Pawn on e5. Black King on e8.
> * **Turn**: White to move.
> * White has exactly **4 legal moves**:
>   1. `Kd6` (Steps forward left — winning move)
>   2. `Kf6` (Steps forward right — winning move)
>   3. `Kf5` (Steps backward right — gives away the win, draws)
>   4. `Kd5` (Steps backward left — gives away the win, draws)
> 
> ---
> 
> ### Step 0: The First Look (Iteration 0)
> 
> Leela sends this board to the neural network for a single forward pass.
> 
> The network returns two things:
> 1. **Value Head (Position Evaluation)**:  
>    Value V = **+0.976** (White is winning, roughly a 98% win chance).
> 2. **Policy Head (Move Probabilities P)**:  
>    * `Kd6`: Probability P = **45.1%**
>    * `Kf6`: Probability P = **44.2%**
>    * `Kf5`: Probability P = **5.4%**
>    * `Kd5`: Probability P = **5.3%**
> 
> Notice that the network put 89.3% of its attention on the two winning moves (`Kd6` and `Kf6`), but still left about 10.7% on the two bad retreating moves.
> 
> ---
> 
> ### Step 1: Who gets picked for Iteration 1?
> 
> Before any move has been visited, every move has:
> * Visits n = 0
> * Quality Q = +0.976 (starts at the baseline value of the position)
> 
> Now the engine calculates the Total Selection Score S for each move:
> 
> * Score for `Kd6` = Quality (0.976) + Bonus based on 45.1% probability = **1.764**
> * Score for `Kf6` = Quality (0.976) + Bonus based on 44.2% probability = **1.748**
> * Score for `Kf5` = Quality (0.976) + Bonus based on 5.4% probability = **1.070**
> * Score for `Kd5` = Quality (0.976) + Bonus based on 5.3% probability = **1.068**
> 
> `Kd6` has the tallest score (**1.764**). 
> 
> **The engine selects `Kd6` for Iteration 1.**
> 
> ---
> 
> ### Step 2: What happens during Iteration 1?
> 
> 1. The engine makes the move `Kd6` on an internal board.
> 2. It sends the new position to the neural network.
> 3. The neural network evaluates this new position: Value = **+0.968** (Confirmed winning!).
> 4. That value returns to the root:
>    * Visits for `Kd6` becomes **n = 1**.
>    * Quality average for `Kd6` is now **Q = +0.968**.
>    * Total visits to the root position becomes **N = 1**.
> 
> ---
> 
> ### Step 3: Who gets picked for Iteration 2? (The Shift!)
> 
> Now we must pick the move for Iteration 2. Let's look at the scores:
> 
> * **For `Kd6`**:  
>   It was just visited (n = 1). Because it was visited, its exploration bonus is **cut in half**!  
>   Its score drops from 1.764 down to **1.361**.
> * **For `Kf6`**:  
>   It has not been visited yet (n = 0). Its bonus is still large.  
>   Its score is **1.522**.
> * **For `Kf5`**: Score is **0.844**.
> * **For `Kd5`**: Score is **0.842**.
> 
> Look at what happened:
> Even though `Kd6` returned a great winning evaluation (+0.968), its score dropped to 1.361 because its curiosity bonus shrank.
> 
> Now `Kf6` has the tallest score (**1.522 > 1.361**).
> 
> **The engine selects `Kf6` for Iteration 2!**

---

### Segment 12: Why Re-visit a Move? (Emergent Depth)

**USER**:
> So, for the iteration 2, the value of kd6 is not taken into account and the MCTS is occupied in going to the next move. Correct? Say if the first move still have the highest score even when the curiosity factor is halved, it will again be selected. what is the point of visiting it again? Go on the same move untill the other move gets selected?

**ASSISTANT**:
> ### Part 1: Was the value of `Kd6` ignored in Iteration 2?
> 
> No, the value of `Kd6` **was** included! 
> 
> Look at what made up `Kd6`'s score of **1.361**:
> * Measured Quality Q = **+0.968** (its confirmed winning value!)
> * Exploration Bonus U = **0.393** (halved from before)
> * Total Score S = 0.968 + 0.393 = **1.361**
> 
> `Kd6` still had its great quality score (+0.968), but `Kf6` had a huge unvisited curiosity bonus that pushed it slightly higher to **1.522**.
> 
> ---
> 
> ### Part 2: "What is the point of visiting a move again?"
> 
> This is the most important insight in all of MCTS:
> 
> **When the engine visits a move a second time, it does NOT repeat the same check. It looks ONE MOVE DEEPER down that line!**
> 
> Let's see what actually happens when a move is selected again:
> 
> ```
> [ Iteration 1 ]
> Root (White to move) ───► Plays 1. Kd6 (Depth 1: Node created!)
> 
> [ Iteration 2 ]
> Root (White to move) ───► Plays 1. Kf6 (Depth 1: Node created!)
> 
> [ Iteration 3 ]
> Root (White to move) ───► Walks down 1. Kf6 
>                                 │
>                                 └───► Black plays 1... Kf8 (Depth 2: New Leaf created!)
> 
> [ Iteration 4 ]
> Root (White to move) ───► Walks down 1. Kd6 
>                                 │
>                                 └───► Black plays 1... Kd8 (Depth 2: New Leaf created!)
> ```
> 
> ---
> 
> ### How Depth "Emerges" Naturally
> 
> In traditional engines like Stockfish, the programmer tells the engine: *"Calculate everything to depth 15."*
> 
> In Leela, **there is no depth setting at all!**
> 
> 1. On Visit 1 down `Kd6`: The engine evaluates the position after `1. Kd6` (Depth 1).
> 2. On Visit 2 down `Kd6`: The engine asks: *"What is Black's best reply to 1. Kd6?"* It steps down to `1... Kd8` and evaluates that new board (Depth 2).
> 3. On Visit 3 down `Kd6`: It asks: *"What does White do after 1. Kd6 Kd8?"* It plays `2. e6` and evaluates that board (Depth 3).
> 
> Every time a move is selected again, the search walks down the established branch and **creates a brand-new child at the bottom**. 
> 
> That is how the engine calculates a 5-move or 10-move deep tactical line!

---

### Segment 13: The FPU Transition (Unvisited Placeholder vs. Real Measured Quality)

**USER**:
> Measured quality Q is for the state prior to the move Kd6, it is not the state that Kd6 caused. I meant that when I said the value of Kd6 is not taken into account.
> No, the value comes from the position s before Kd6 and not after the valuation of position of Kd6. The bonus is added to the prior value of 's' and not the current state after the move Kd6.

**ASSISTANT**:
> You are describing the mechanism known as **FPU (First Play Urgency)**.
> 
> Let's look at why you are right about what happens initially, and how it transitions once a move is visited.
> 
> ---
> 
> ### Phase 1: Before a move has ever been visited (Iteration 0)
> 
> You are completely correct here. 
> 
> Before `Kd6` is visited:
> * No child position exists yet.
> * No evaluation of the board after `Kd6` has been made.
> * So where does the engine get a value for `Kd6`? 
> 
> It takes the **prior value of position s (the root value +0.97602)** and uses it as the baseline floor for all candidate moves.
> 
> In Iteration 0:
> * Every move starts with the **value of position s (+0.97602)**.
> * The exploration bonus (from the probability P) is added directly to that prior value of position s.
> 
> That is why:
> * Score for `Kd6` = (Prior value of s: 0.97602) + (Bonus based on P = 45.1%) = **1.764**
> * Score for `Kf6` = (Prior value of s: 0.97602) + (Bonus based on P = 44.2%) = **1.748**
> 
> At this starting point, the ranking is decided entirely by the probabilities P added to the prior value of position s.
> 
> ---
> 
> ### Phase 2: After `Kd6` is visited (Iteration 1 and beyond)
> 
> Now the search physically steps into `Kd6` and evaluates the new position:
> 
> 1. **For `Kd6` (The visited move)**:  
>    It now has its **own real measurement** from the new position (+0.96766). Its score no longer uses the placeholder from position s—it uses its actual measured child result.
> 
> 2. **For `Kf6`, `Kf5`, `Kd5` (The unvisited moves)**:  
>    They still have zero visits! They still do not have their own child evaluations. So they **continue** to use the baseline value derived from position s (adjusted by the FPU penalty).
> 
> ---
> 
> ### Summary:
> * **For UNVISITED moves**: The value comes from the prior position `s` (the FPU baseline) + the bonus U.
> * **For VISITED moves**: The value comes from the actual child positions reached down that line + the bonus U.

---

### Segment 14: The Default Placeholder is Replaced

**USER**:
> When Kd6 is visited once and its state evaluation is made, does its previous default value gets replaced by the new value?

**ASSISTANT**:
> **YES! Exactly.**
> 
> The moment `Kd6` is visited once:
> 
> 1. **The default placeholder is thrown away completely.**
> 2. **The new measured value (+0.96766) takes its place as Q.**
> 
> ---
> 
> ### Look at how the numbers change for `Kd6`:
> 
> * **Before Visit 1 (n = 0)**:  
>   `Kd6` had no measurement of its own. It used the default placeholder value (+0.97602).
> 
> * **After Visit 1 (n = 1)**:  
>   The default placeholder is gone. `Kd6` now has its own real measured average:
>   
>   Quality Q = **+0.96766**
> 
> From this point on, `Kd6`'s value is determined **100% by the real evaluations** that come back from playing down that move.
> 
> ---
> 
> ### What about the other moves that haven't been visited yet (`Kf6`, `Kf5`, `Kd5`)?
> 
> Because they still have **n = 0 visits**, they still use the default placeholder value from the parent position!
> 
> They will keep using the placeholder until the search visits them and replaces their placeholder with their own real measurement.
