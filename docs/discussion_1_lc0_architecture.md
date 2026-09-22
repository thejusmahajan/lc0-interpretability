# Discussion 1: Hacking the Engine vs. Conditional Training

**Participants:** Viswanathan Anand, LC0 Search Developer (Dev 1), LC0 Neural Network Architect (Dev 2)

**Vishy Anand:**
As a human player, I don't always play the absolute "best" computer move. If I'm playing against an opponent who struggles with calculation, I might consciously steer the game toward a position rich in *pins* and *sacrifices*, even if it means sacrificing 0.3 pawns in engine evaluation. Can we force Leela to do this? Can we tell her, "I want you to aim for a discovered attack"?

**LC0 Dev 1 (Search & MCTS Expert):**
It is absolutely possible, Vishy, but it requires hacking how Leela explores the game tree. Leela uses Monte Carlo Tree Search (MCTS). When she considers a move, she balances the neural network's suggested move (Policy) against the expected win rate of that line (Value). 

To force a motif, we could inject a **Heuristic Bias into the PUCT formula** (the math that decides which branch to search next). If we run our new Lichess Python Tagger over the Principal Variation (PV) of the branches being explored, and the tagger spots a "discovered attack," we can artificially inflate the Win Probability (Q-value) of that branch by, say, +10%. Leela's search would suddenly prioritize exploring and playing lines that lead to that tactic.

**Vishy Anand:**
That sounds like you are tricking the engine. If you artificially inflate the evaluation, won't Leela play objectively bad moves just to force a discovered attack?

**LC0 Dev 1:**
Yes, that’s the danger. It’s what we call the "Horizon Effect" of biased search. She might blunder a piece just because the resulting position contains a meaningless pin. Furthermore, running a Python tagger on millions of MCTS nodes per second is computationally impossible. We'd have to write a lightning-fast C++ bitboard tagger just to evaluate the nodes quickly enough.

**LC0 Dev 2 (Neural Network Architect):**
Exactly, hacking the search tree is brute-force and computationally expensive. A much more elegant, Leela-native way to do this is through **Conditional Training** at the Neural Network level.

Right now, Leela's input planes just describe where the pieces are. But we can add new "Concept Planes." Imagine taking 50 million games from the Lichess database. We run the Lichess tagger over all of them. If a game features a "skewer", we set a special input plane to `1.0`. We train a new Leela network to predict the moves played in those games, *conditioned* on those concept planes.

**Vishy Anand:**
So you are saying that if we train her to know what a "skewer game" looks like, we can turn that setting on at runtime? 

**LC0 Dev 2:**
Precisely! At inference time, when you ask Leela for a move, we flip the "Skewer Plane" to `1.0`. The Policy head of the neural network will intuitively "feel" that moves leading to skewers are better, and output higher probabilities for them. It requires zero extra calculation time during the search. She wouldn't be "calculating" toward a skewer; her raw chess intuition would naturally steer the position into geometries where skewers thrive. It's similar to how Maia Chess was trained to mimic human ELO levels.

**LC0 Dev 1:**
To add to that, we could even use an **Auxiliary Output Head**. We can train Leela so that, alongside predicting the Win/Draw/Loss (WDL) percentages, she outputs a "Motif Probability Vector." 
If you demand a fork, we tell the MCTS search algorithm: *"Only deeply search branches where Leela's Neural Network predicts a >60% chance of a fork occurring."* 

**Vishy Anand:**
This is fascinating. The Search approach forces her to calculate towards the tactic, while the Neural Network approach gives her a "tactical personality," much like how Mikhail Tal natively saw sacrifices that positional players wouldn't even consider. 

If we implement the Conditional Training approach, the engine could become the ultimate chess coach. You could tell Leela: *"Play a game against me, but steer the game toward Greek Gift sacrifices so I can practice defending them."* 

**LC0 Dev 2:**
Exactly. And because she still relies on her core understanding of chess, she won't play inherently losing moves to get there. She will simply choose the highest-evaluating move that *also* maximizes the probability of the requested motif.
