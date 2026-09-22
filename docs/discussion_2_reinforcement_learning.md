# Discussion 2: Pure Reinforcement Learning & Entropy

**Participants:** Mikhail Tal, David Silver, Julian Schrittwieser

**Mikhail Tal:**
You computer scientists are obsessed with defining the tactic before it happens. "Steer towards a pin," you say. But a tactic is not a destination; it is the inevitable explosion that happens when you create intolerable tension. You cannot program a machine to "look for a sacrifice." Instead, you must teach it to crave chaos. To drive an engine toward a tactical motif, do not reward the motif itself—reward the *complexity*. Maximize the number of nightmare scenarios the opponent must calculate.

**David Silver:**
That is a beautiful human sentiment, Mikhail, but in reinforcement learning, we *can* formalize chaos. With AlphaZero, we used the simplest possible reward: +1 for a win, -1 for a loss. If we want an engine that hunts for specific motifs, we fundamentally alter the environment's reward function. We use **Reward Shaping**.
During self-play, the agent receives a +1 reward for winning, but it receives a +1.5 reward if it wins *and* the game transcription contains the requested motif. Through millions of games of self-play, the Policy network will naturally warp. It will learn a probability distribution that inherently favors dynamic, motif-rich continuations because they yield higher expected returns.

**Julian Schrittwieser:**
I have to push back on Reward Shaping, David. We saw what happened when we tried tweaking rewards in early RL environments—the agent learns to "game" the system. If you give a bonus for a sacrifice, the agent playing against itself will learn to purposefully play weak moves, allow its pieces to be captured, and harvest the sacrifice bonus before eventually winning. It corrupts the purity of the Nash equilibrium. The engine becomes tactically obsessed, but objectively weaker.

Instead of corrupting the reward, we alter the architecture. We use **Multi-Objective Reinforcement Learning**. 
We keep the AlphaZero architecture, but instead of one Value Head, we use two: $V_{win}$ (Probability of winning) and $V_{motif}$ (Probability of a specific motif occurring in this branch). The network learns both simultaneously without one polluting the other. At inference time, you simply give the user a dial. They set $V_{total} = V_{win} + \alpha V_{motif}$. You seamlessly steer the engine's preference without destroying its core chess strength.

**Mikhail Tal:**
Julian, your dial is logical, but it lacks soul. A sacrifice is not a mathematical probability, it is an attack on the opponent's psychology! If you want an engine to play like me, you must teach it to measure the opponent's discomfort. Can you mathematically define discomfort? 

**David Silver:**
Actually... we can. In RL, we call that **Intrinsic Motivation**, specifically driven by *Entropy*. 
Mikhail, what if we reward the engine not for the tactic, but for confusing the opponent? Every time our engine evaluates a move, it predicts the opponent's responses via its Policy network. If the opponent has one obvious reply, the entropy is low. If the opponent has ten equally terrifying replies and the Policy distribution is completely flat, the entropy is high. 
If we train the engine to maximize the *entropy of the opponent's policy*, the engine will relentlessly seek out razor-sharp, imbalanced positions. Tactics—pins, forks, sacrifices—will spontaneously emerge as a byproduct of the engine trying to maximize chaos!

**Julian Schrittwieser:**
That is brilliant for creating a chaotic engine, but the user specifically asked how to steer toward *one specific motif from a set*. Entropy generates all tactics, not a specific one.
If we want to surgically trigger a specific motif without retraining the entire network from scratch via self-play, we should use **Activation Steering**, also known as Representation Engineering.

**Mikhail Tal:**
Speak plainly, Julian. What are you steering?

**Julian Schrittwieser:**
The engine's "thoughts." Inside the deep ResNet layers of the neural network, the engine forms abstract concepts of the board. If we analyze the activations of the neurons when the engine looks at thousands of "fork" puzzles, we can isolate the exact mathematical vector that represents the *concept of a fork*.
During a live game, when the user says "drive towards a fork," we literally inject that "fork vector" directly into the hidden layers of the neural network at runtime. We are forcibly making the network hallucinate that a fork is present or imminent. The Policy network will react to this hallucination by outputting moves that actively try to realize the fork on the board.

**Mikhail Tal:**
*(Laughs)* So you are poisoning its brain with the ghost of a sacrifice, and watching it scramble to make the ghost real? That... is exactly how I play chess.
