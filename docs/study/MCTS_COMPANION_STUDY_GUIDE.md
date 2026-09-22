# Neural MCTS — Companion Study Guide

A step-by-step companion to `guide/neural_mcts_visual_guide_v2.pdf`.

Every formula here is written in plain text. Every number can be checked with a
calculator. Nothing is asserted that you cannot verify yourself by the end of
Part 7.

This guide is built around the questions you actually asked. Where a section
answers one of them directly, it says so.

---

## Part 0 — The one position we will use throughout

```
FEN:  4k3/8/4K3/4P3/8/8/8/8 w - - 0 1

        a  b  c  d  e  f  g  h
   8 [  .  .  .  .  k  .  .  . ]     k = Black king (e8)
   7 [  .  .  .  .  .  .  .  . ]
   6 [  .  .  .  .  K  .  .  . ]     K = White king (e6)
   5 [  .  .  .  .  P  .  .  . ]     P = White pawn (e5)
   4 [  .  .  .  .  .  .  .  . ]
   3 [  .  .  .  .  .  .  .  . ]
   2 [  .  .  .  .  .  .  .  . ]
   1 [  .  .  .  .  .  .  .  . ]

White to move. Exactly 4 legal moves:

   Kd6  - step forward-left    (keeps the win)
   Kf6  - step forward-right   (keeps the win)
   Kf5  - step backward-right  (throws the win away, draws)
   Kd5  - step backward-left   (throws the win away, draws)
```

Four legal moves is the point. Every number in the search can be written on one
line, so nothing has to be taken on trust.

---

## Part 1 — What the network hands you, and where those numbers physically come from

You show the board to the neural network **once**. One forward pass. It returns
**two** things, and it is important to understand that they are two different
heads of the same network answering two different questions.

### 1.1 The value head answers: "How is this position going for the side to move?"

It outputs three probabilities:

```
   w = probability this position ends in a win  for the side to move
   d = probability this position ends in a draw
   l = probability this position ends in a loss for the side to move

   w + d + l = 1          (a game must end in exactly one of the three)
```

**Where these numbers physically come from.** They are not dice. Chess is
deterministic — the true value of a position is exactly one of win, draw, or
loss. These probabilities are the network's *degree of belief*, learned from
millions of self-play games. Read `w = 0.60` as:

> "Among the positions I was trained on that looked like this one, the side to
> move went on to win about 60% of the time."

That is **epistemic** uncertainty — uncertainty from limited knowledge, not from
randomness in the game.

Two derived numbers:

```
   Expected score   E = w + 0.5*d          range 0.0 .. 1.0
   Net value        V = w - l              range -1.0 .. +1.0

   and they are the same information rescaled:
       E = 0.5 + 0.5*V        V = 2*E - 1
```

For our position the network returns **V = +0.97602**.

**Why the search uses V and not E.** Chess is zero-sum. Whatever is good for
White by exactly that much is bad for Black. On the V scale, switching sides is
a single multiplication:

```
   V_from_the_other_side = -V
```

On the E scale you would have to write `1 - E`, which is clumsier to propagate.
That sign flip is the whole reason V exists.

### 1.2 The policy head answers: "Which moves look worth examining?"

For our position:

```
   Kd6   P = 0.4513    (45.13%)
   Kf6   P = 0.4423    (44.23%)
   Kf5   P = 0.0538     (5.38%)
   Kd5   P = 0.0526     (5.26%)
                        --------
                        100.00%
```

**What P is not.** P is *not* the evaluation of the move. The network has not
looked at any of these positions. P is a trained reflex — "in positions of this
shape, these are the moves that turned out to be worth examining." It is
attention, not judgement.

Notice the network put 89.4% of its attention on the two winning king moves and
still left 10.6% on the two that throw the win away. It is not certain. Good —
that residue is what lets the search check them cheaply and move on.

---

## Part 2 — State `s` and Action `a` (your question, answered directly)

> *"Action 'a' is essentially state 's' because a is the causal factor of s. Why
> then differentiate these two? A new move a means a new position s. Isn't it?"*

You are right that in chess they are linked deterministically:

```
   s' = Transition(s, a)          play move a in position s, arrive at s'
```

So why keep two symbols? Because they live in different places in the tree, and
they hold different numbers.

```
                          s  =  the position (a NODE, a circle)
                          |       - this is a board, White to move
                          |       - the network gave it V = +0.97602
          +-------+-------+-------+
          |       |       |       |
         Kd6     Kf6     Kf5     Kd5      <-- a = the ACTIONS (EDGES, arrows)
          |       |       |       |            each edge carries: P, n, W, Q
          v       v       v       v
         s1'     s2'     s3'     s4'      <-- the child positions (NODES again)
```

Read it out loud once:

* **`s` is a circle.** A board. Something you could set up with real pieces.
* **`a` is an arrow.** A choice. Not a board — you cannot set up an arrow.

**The statistics live on the arrows, not on the circles.** The visit count `n`,
the running total `W`, and the average quality `Q` are all properties of an
*edge*. When the guide writes `Q(s, a)`, it means: "the quality of the arrow `a`
leaving circle `s`." It needs both symbols because the same move name (`Kd6`)
means something different from a different position.

> **Your own summary, which was correct:** *"`a` is never a position. `s` is the
> position prior to the moves `a`."* Exactly. And the child positions `s'` are
> circles again, each with their own four arrows leaving them. That is how the
> tree grows.

---

## Part 3 — Every arrow carries exactly two numbers that matter

To choose which arrow to take, the engine computes one score per arrow:

```
   S(a)  =  Q(a)  +  U(a)
            ----     ----
            what     how much
            we       we still
            know     want to look
```

* **Q** is memory. What came back from the times we already went down this arrow.
* **U** is curiosity. How much attention this arrow deserves given that we have
  not looked much yet.

The engine always takes the arrow with the largest `S`. That is the entire
selection rule. Everything else is bookkeeping for these two numbers.

---

## Part 4 — Q, the running average (and what x_n physically is)

> *"So the x_n are the values from the value heads, that is V's of each position
> arising when a new candidate is visited. Correct?"* — Yes, exactly.

Each time the search goes down arrow `a` and eventually evaluates some position
at the bottom, one number comes back. Call the n-th such number `x_n`.

```
   W(a) = x_1 + x_2 + ... + x_n        running total
   n(a) = how many times we went down this arrow
   Q(a) = W(a) / n(a)                  the average
```

`Q` is a **sample mean**. Nothing more exotic than that.

The incremental form (which is what the code actually does, so it never has to
store the list) is:

```
   Q_new = Q_old + (x_n - Q_old) / n
```

Check it once by hand, with x_1 = 0.968 then x_2 = 0.900:

```
   n=1:  Q = 0.968
   n=2:  Q = 0.968 + (0.900 - 0.968)/2 = 0.968 - 0.034 = 0.934
   check: (0.968 + 0.900)/2 = 0.934                       agrees
```

**The sign flip, carefully.** `x_n` arrives from a position where it is the
*opponent's* turn. The network reports V from the point of view of whoever is to
move there. So before adding it into our total we negate it:

```
   x_n  =  -V(child position)
```

In our endgame, after `Kd6` it is Black to move, and the network says Black
stands at about **-0.968** (Black is losing). White's edge records:

```
   x_1 = -(-0.968) = +0.968
```

This is why the guide's figure shows the value "flipping sign at every level."
It is the same fact as `V_parent = -V_child` from Part 1.

---

## Part 5 — U, the curiosity term, and why it shrinks

```
   U(a)  =  c * P(a) * sqrt(N) / (1 + n(a))

   P(a)  = the policy prior for this arrow          (fixed, from the network)
   n(a)  = visits to THIS arrow                     (grows as we use it)
   N     = total visits made from this node         (grows as we use any arrow)
   c     = exploration constant                     (about 1.745 in our trace)
```

Read each piece physically:

* **`P(a)` in the numerator** — the network's hunch gets a say. A move it likes
  starts loud.
* **`n(a)` in the denominator** — the more we have already looked down this
  arrow, the less curiosity it deserves. **Visit an arrow once and its `U`
  halves** (the denominator goes 1 -> 2). Visit it again and it drops to a
  third. This is the mechanism that forces the search to move on.
* **`sqrt(N)` in the numerator** — as the node as a whole gets more attention,
  everything gets a mild lift, so a promising-but-neglected arrow can come back
  into contention later. The square root makes this grow slowly.

So `U` is large when a move is well-liked and under-examined, and small when it
is either disliked or already well-examined. That is the entire idea.

---

## Part 6 — FPU: what an arrow is worth *before* you have ever taken it

This is the part you pushed hardest on, and you were right.

> *"Measured quality Q is for the state prior to the move Kd6, it is not the
> state that Kd6 caused... The bonus is added to the prior value of `s` and not
> the current state after the move Kd6."*

Correct, and here is the precise statement.

### Phase 1 — arrow never taken (n = 0)

There is no child position. The network has evaluated nothing down there. There
is literally no measurement to average. So the engine needs a placeholder, and
it uses the **parent position's own value** as the starting floor:

```
   Q(a) = Q(s)  -  k * sqrt( sum of P over arrows already visited )
          ----     ----------------------------------------------
          parent's the FPU reduction        (k = 0.33)
          RUNNING
          average
```

Two details that are easy to get wrong, and both matter:

* The first term is the parent's **running average Q(s)**, not its original
  network value `V(s)`. Early on they are equal, because the parent's only
  sample is its own evaluation. They drift apart as children report back.
* The sum is over the **policy mass already explored**, not the number of moves
  explored. Spending a visit on a 45% move makes the engine far more cautious
  about the rest than spending one on a 5% move would.

Read the reduction physically: *"we have already spent effort on arrows covering
this much of the network's attention, and none of it beat the parent, so be a
little more pessimistic about the untried ones."* At the very start nothing has
been visited, the sum is 0, and the placeholder is simply the parent's value.

This is called **First Play Urgency**.

### Phase 2 — the moment the arrow is taken for the first time (n goes 0 -> 1)

> *"When Kd6 is visited once and its state evaluation is made, does its previous
> default value get replaced by the new value?"* — **Yes. Completely.**

```
   BEFORE          Q(Kd6) = 0.97602   <- borrowed from the parent. A placeholder.
                                          Not a measurement of anything.

   the search plays Kd6, reaches the child position,
   the network evaluates it, the value comes back as x_1 = +0.96766

   AFTER           Q(Kd6) = 0.96766   <- its own measurement. n = 1, W = 0.96766.
```

The placeholder is **discarded, not blended**. It was never data. From this
moment on, `Q(Kd6)` is determined entirely by real evaluations returning from
below that arrow.

And crucially: the three arrows still at `n = 0` keep using the placeholder —
now with a slightly larger FPU reduction, because `Kd6`'s prior has joined the
"already visited" sum.

**One line to remember:**

```
   n = 0  ->  Q comes from the PARENT position   (borrowed, temporary)
   n >= 1 ->  Q comes from the CHILD positions   (measured, permanent)
```

---

## Part 7 — The full trace, four iterations, every number checkable

Constants, so you can reproduce every line:

```
   V(root) = 0.97602      c = 1.745      k = 0.33
   P:  Kd6 0.4513   Kf6 0.4423   Kf5 0.0538   Kd5 0.0526

   U(a)  = c * P(a) * sqrt(N) / (1 + n(a)),  N = max(1, visits from this node)
   Q_FPU = Q(parent) - k * sqrt(sum of P over visited arrows)
```

### Iteration 0 — nothing visited yet

Every arrow has `n = 0`, so every `Q` is the placeholder. Nothing is visited, so
the FPU reduction is `k * sqrt(0) = 0` and the placeholder is the parent's value
itself. `N = max(1, 0) = 1`.

```
   arrow   n   Q         U = 1.745 * P * 1 / (1+0)     S = Q + U
   -----   -   -------   ---------------------------   ---------
   Kd6     0   0.97602   1.745*0.4513 = 0.78752        1.76354
   Kf6     0   0.97602   1.745*0.4423 = 0.77181        1.74783
   Kf5     0   0.97602   1.745*0.0538 = 0.09388        1.06990
   Kd5     0   0.97602   1.745*0.0526 = 0.09179        1.06781
```

All four `Q` are identical, so **the policy prior alone decides the first move
examined.**

> **Selected: Kd6.** Play it, evaluate the child, `x_1 = +0.96766` comes back.
> Now `n(Kd6) = 1`, `Q(Kd6) = 0.96766`.
> The root's own average updates too: `Q(root) = mean(0.97602, 0.96766) = 0.97184`.

### Iteration 1 — one arrow has a real measurement

Visited policy mass is `0.4513`, so the reduction is
`0.33 * sqrt(0.4513) = 0.33 * 0.67179 = 0.22169`, and unvisited arrows sit at
`0.97184 - 0.22169 = 0.75015`.

```
   arrow   n   Q         U = 1.745 * P * 1 / (1+n)     S
   -----   -   -------   ---------------------------   -------
   Kd6     1   0.96766   1.745*0.4513/2 = 0.39376      1.36142
   Kf6     0   0.75015   1.745*0.4423/1 = 0.77181      1.52196
   Kf5     0   0.75015   1.745*0.0538/1 = 0.09388      0.84403
   Kd5     0   0.75015   1.745*0.0526/1 = 0.09179      0.84194
```

`Kd6`'s evaluation came back **excellent** (+0.96766) — and its score still
*fell*, from 1.76354 to 1.36142. Two separate things did that:

1. Its `U` halved, because `n` went 0 -> 1.
2. Its `Q` dropped slightly, the borrowed 0.97602 giving way to the measured
   0.96766.

Meanwhile `Kf6` kept its full curiosity bonus.

> **Selected: Kf6.** `x_1 = +0.98598` comes back — even better than Kd6's.
> `Q(root) = mean(0.97602, 0.96766, 0.98598) = 0.97655`.

### Iteration 2 — both good moves now measured

Visited policy mass is `0.4513 + 0.4423 = 0.8936`, so the reduction grows to
`0.33 * sqrt(0.8936) = 0.33 * 0.94531 = 0.31195`, and unvisited arrows drop to
`0.97655 - 0.31195 = 0.66460`.

`N = 2` now, so `sqrt(N) = 1.41421`.

```
   arrow   n   Q         U = 1.745 * P * 1.41421 / (1+n)     S
   -----   -   -------   ---------------------------------   -------
   Kd6     1   0.96766   1.745*0.4513*1.41421/2 = 0.55696    1.52462
   Kf6     1   0.98598   1.745*0.4423*1.41421/2 = 0.54585    1.53183
   Kf5     0   0.66460   1.745*0.0538*1.41421/1 = 0.13279    0.79739
   Kd5     0   0.66460   1.745*0.0526*1.41421/1 = 0.12983    0.79443
```

> **Selected: Kf6 — for the second time.**

Note how close it was: 1.53183 against 1.52462. `Kf6` won only because its
measured value came back higher. The two bad moves have fallen to about 0.79 and
are no longer competitive.

### Iteration 3 — and this is the answer to "why revisit a move?"

`Kf6` is entered again. Its second sample comes back lower, `x_2 = +0.95128`,
and the average moves accordingly:

```
   Q(Kf6) = (0.98598 + 0.95128) / 2 = 0.96863        n(Kf6) = 2
```

Check with the incremental form:
`0.98598 + (0.95128 - 0.98598)/2 = 0.98598 - 0.01735 = 0.96863`. Agrees.

The unvisited arrows drop again, to `0.97024 - 0.31195 = 0.65829`, because the
root's own running average moved.

**The important part is not the arithmetic — it is where that second sample came
from.** See 8.2.

---

## Part 8 — Your three questions, answered with the numbers above

### 8.1 "Won't a cluster of bad moves drag down the parent's average?"

> *"I go to move a1 from state s1 and it has a high value. All the other moves
> are bad or even blunders. This would drastically reduce the average value of
> the parent move that caused s1."*

This is the sharpest question in the whole log, and the answer is that **the
average is not taken over moves. It is taken over visits** — and visits are
distributed wildly unequally.

After four iterations:

```
   Kd6   visited 1 time
   Kf6   visited 2 times
   Kf5   visited 0 times     <- contributes NOTHING to any average
   Kd5   visited 0 times     <- contributes NOTHING to any average
```

An unvisited blunder contributes exactly zero terms to `W`. A blunder that *is*
visited once contributes one bad term — then its `U` halves, its `Q` collapses to
the bad measured value, and it is never selected again. Run to 10,000 nodes and
the split is typically 97%+ of visits on the best one or two moves.

Watch the two bad moves being squeezed out **without ever being played**:

```
   before iteration 1:  Kf5 = 1.06990    (0.69 behind the leader)
   before iteration 2:  Kf5 = 0.84403    (0.68 behind)
   before iteration 3:  Kf5 = 0.79739    (0.73 behind, and falling)
```

They fall because the FPU reduction keeps growing as good moves absorb policy
mass. The engine becomes progressively more sceptical of the untried remainder.

So the parent's value never becomes "the average of one good move and three
blunders." It becomes, very nearly, "the value of the good moves" — because the
good moves supplied essentially every sample.

**This is the single most important idea in MCTS.** Uniform search averages over
moves. MCTS *samples* moves in proportion to how promising they look, so the
average is dominated by the lines actually worth playing.

### 8.2 "Why visit a move again? What is the point?"

> *"Say if the first move still has the highest score even when the curiosity
> factor is halved, it will again be selected. What is the point of visiting it
> again? Go on the same move until the other move gets selected?"*

Iteration 3 selects `Kf6` for the second time. What physically happens is **not**
a repeat of iteration 2.

The first visit to `Kf6` created the child position and evaluated it. That child
now exists in the tree, with **its own arrows** and its own statistics.

So the second visit does not stop there. It passes *through* and applies the same
selection rule one level down, choosing among Black's replies, and evaluates a
position **two plies deep**.

```
   Visit 1 to Kf6:   root --Kf6--> [child] evaluate here          depth 1
   Visit 2 to Kf6:   root --Kf6--> child --reply--> [grandchild]  depth 2
                                              evaluate here
```

And the consequence is visible in the numbers. The first look at `Kf6` returned
`+0.98598`. The second, one ply deeper, returned `+0.95128` — Black's best reply
takes some of the shine off. The average settles at `0.96863`, a better estimate
than either sample alone.

**Revisiting a move is how the search gets deeper.** Depth is never scheduled.
Nobody writes "now search 18 plies." Depth is the *consequence* of the same move
winning the `S` comparison repeatedly, each win pushing the frontier one level
further down that line.

That is why a strong engine's principal variation is long while its refuted
sidelines are one node deep. The tree is deliberately unbalanced.

### 8.3 "Why does the network evaluate positions rather than moves?"

Because a move is not a thing you can look at. It is a *transition*. The network
takes a board as input — 8x8 of pieces, castling rights, side to move. You
cannot feed it "Kd6" without first playing Kd6 and producing a board.

```
   V is a property of a CIRCLE (a position).
   Q is a property of an ARROW (a move), and it is built out of
     the V's of the circles that arrow leads to.
```

A move acquires a value only by being played, reaching a position, and having
*that position* evaluated. Which is exactly why an unvisited arrow has no `Q` of
its own and has to borrow one (Part 6).

The policy head does output one number per move — but as established in Part 1,
`P` is attention, not evaluation. The network is saying "look here," not "this
is good."

---

## Part 9 — Check yourself

Do these with a calculator. Answers follow.

1. At iteration 0, why do all four arrows have the same `Q`?
2. `Kd6` returned an *excellent* +0.968 and its score still fell from 1.763 to
   1.361. Give both reasons.
3. Compute `U(Kf5)` at iteration 2 from scratch.
4. An arrow has `n = 3`, `W = 1.80`. A fourth evaluation returns `x_4 = 0.20`.
   Compute the new `Q` both ways (direct and incremental).
5. Which value does an unvisited arrow use — the parent's or the child's? Why
   can it not be the child's?
6. If the search runs 10,000 iterations and `Kd5` is visited 3 times, roughly
   how much does `Kd5` affect the root's final estimate?
7. The FPU baseline fell from 0.75015 to 0.66460 even though no new bad news
   arrived. Why?

<details>
<summary>Answers</summary>

1. None of them has been visited, so none has a measurement of its own. All four
   borrow the same parent value 0.97602. Only `P` distinguishes them, through `U`.
2. (a) `n` went 0 -> 1 so `U` halved, 0.78752 -> 0.39376. (b) `Q` was replaced,
   the borrowed 0.97602 giving way to the measured 0.96766.
3. `1.745 * 0.0538 * sqrt(2) / (1+0) = 1.745 * 0.0538 * 1.41421 = 0.13279`.
4. Direct: `(1.80 + 0.20)/4 = 0.500`. Incremental: `Q_old = 1.80/3 = 0.600`,
   then `0.600 + (0.20 - 0.600)/4 = 0.600 - 0.100 = 0.500`. Same.
5. The parent's, reduced by the FPU term. It cannot be the child's because the
   child position has not been created or evaluated — there is nothing to read.
6. Almost nothing: 3 samples out of 10,000, about 0.03% of the weight. This is
   8.1 restated.
7. The *visited policy mass* grew from 0.4513 to 0.8936 when Kf6 was visited, so
   the reduction `0.33*sqrt(mass)` grew from 0.22169 to 0.31195. The engine gets
   more sceptical of untried moves as the explored share rises.

</details>

---

## One-page summary

```
   THE NETWORK, once per new position:
      value head  -> w, d, l  ->  V = w - l        (how the position stands)
      policy head -> P per move                    (where to look first)

   EVERY ARROW carries:  P (fixed), n (visits), W (total), Q = W/n (average)

   SELECTION, at every node, every iteration:
      S(a) = Q(a) + U(a)
      U(a) = c * P(a) * sqrt(N) / (1 + n(a))
      take the largest S

   Q, depending on the visit count:
      n = 0   ->  borrowed from the parent, minus the FPU reduction
      n >= 1  ->  the real average of values returned from the child positions
                  (the borrowed number is discarded, never blended)

   BACKUP:  x_n = -V(child)     because the sides alternate

   WHY IT WORKS:
      bad moves are sampled once and abandoned, so they barely enter the average
      good moves are sampled repeatedly, and each repeat pushes one ply deeper
      depth is never scheduled - it emerges from the same move winning again
```

---

*Companion to `docs/study/guide/neural_mcts_visual_guide_v2.pdf`. Every number
here is taken from that guide's own figure sources (`guide/figures/fig_2_*.tex`),
so the two documents agree to five decimal places. The constants c = 1.745 and
k = 0.33 reproduce every published score exactly.*

*One subtlety worth stating, because getting it wrong is easy: the FPU baseline
is computed from the parent's **running average Q**, not from its original
network value V. The two differ as soon as children start reporting back — using
V here gives 0.75433 where the engine gives 0.75015. LC0's real exploration
constant also grows slowly with visit count rather than staying fixed, which
changes none of the mechanisms described here.*
