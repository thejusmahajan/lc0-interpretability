# Engine Reference & Measured Binary Benchmark

## 1. Provenance Header

- **Binary Path**: `engine/lc0.exe`
- **Version**: v0.32.1 (built Nov 23 2025)
- **Search Algorithm**: Classic Neural MCTS
- **Primary Network Weights**: `BT3-768x15x24h-swa-2790000.pb.gz`
- **Diagnostic Network Weights**: `791556.pb.gz`
- **Exact Extraction Commands Run**:
  ```powershell
  ./lc0.exe --help --show-hidden
  ./lc0.exe describenet --weights=BT3-768x15x24h-swa-2790000.pb.gz
  ./lc0.exe describenet --weights=791556.pb.gz
  ```

## 2. Measured Architecture Comparison

Measured directly from binary output via `lc0 describenet` (`raw/describenet_bt3.txt` & `raw/describenet_791556.txt`):

| Property | Primary Net (BT3-768x15x24h) | Diagnostic Net (791556) | Source Output |
|---|---|---|---|
| Minimal Lc0 Version | v0.30.0 | v0.29.0 | `describenet` output |
| Input Format | `INPUT_CLASSICAL_112_PLANE` | `INPUT_CLASSICAL_112_PLANE` | `describenet` output |
| Network Body | `NETWORK_ATTENTIONBODY_WITH_MULTIHEADFORMAT` | `NETWORK_SE_WITH_HEADFORMAT` | `describenet` output |
| Policy Head | `POLICY_ATTENTION` | `POLICY_ATTENTION` | `describenet` output |
| Value Head | `VALUE_WDL` | `VALUE_WDL` | `describenet` output |
| Moves-Left Head (MLH) | `MOVES_LEFT_V1` | `MOVES_LEFT_V1` | `describenet` output |
| Encoders / Blocks | 15 Encoder Layers (24 Heads) | 15 SE Residual Blocks (192 Filters) | `describenet` output |
| Embedding Size / Dmodel | 768 / 768 (DFF 1024) | 192 | `describenet` output |
| Training Steps | 2,790,000 | 3,116,000 | `describenet` output |
| Policy Accuracy | 0.395877 (39.59%) | 66.7249 (66.72%) | `describenet` output |

## 3. UCI Options Reference (91 Options)

Total UCI options captured and documented: **91**.

### Search & PUCT (32 options)

#### `CPuct`
- **Flag Header**: `--cpuct=0.00..100.00`
- **Default**: `1.75` | Range: `0.00..100.00`
- **Verbatim Description**: cpuct_init constant from "UCT search" algorithm. Higher values promote more exploration/wider search, lower values promote more confidence/deeper search.

#### `CPuctAtRoot`
- **Flag Header**: `--cpuct-at-root=0.00..100.00`
- **Default**: `1.75` | Range: `0.00..100.00`
- **Verbatim Description**: cpuct_init constant from "UCT search" algorithm, for root node.

#### `CPuctBase`
- **Flag Header**: `--cpuct-base=1.00..1000000000.00`
- **Default**: `38739.00` | Range: `1.00..1000000000.00`
- **Verbatim Description**: cpuct_base constant from "UCT search" algorithm. Lower value means higher growth of Cpuct as number of node visits grows.

#### `CPuctBaseAtRoot`
- **Flag Header**: `--cpuct-base-at-root=1.00..1000000000.00`
- **Default**: `38739.00` | Range: `1.00..1000000000.00`
- **Verbatim Description**: cpuct_base constant from "UCT search" algorithm, for root node.

#### `CPuctFactor`
- **Flag Header**: `--cpuct-factor=0.00..1000.00`
- **Default**: `3.89` | Range: `0.00..1000.00`
- **Verbatim Description**: Multiplier for the cpuct growth formula.

#### `CPuctFactorAtRoot`
- **Flag Header**: `--cpuct-factor-at-root=0.00..1000.00`
- **Default**: `3.89` | Range: `0.00..1000.00`
- **Verbatim Description**: Multiplier for the cpuct growth formula at root.

#### `CacheHistoryLength`
- **Flag Header**: `--cache-history-length=0..7`
- **Default**: `0` | Range: `0..7`
- **Verbatim Description**: Length of history, in half-moves, to include into the cache key. When this value is less than history that NN uses to eval a position, it's possble that the search will use eval of the same position with different history taken from cache.

#### `MaxCollisionVisits`
- **Flag Header**: `--max-collision-visits=1..100000000`
- **Default**: `80000` | Range: `1..100000000`
- **Verbatim Description**: Total allowed node collision visits, per batch.

#### `MaxCollisionVisitsScalingEnd`
- **Flag Header**: `--max-collision-visits-scaling-end=0..100000000`
- **Default**: `145000` | Range: `0..100000000`
- **Verbatim Description**: Tree size where max collision visits reaches max. Set to 0 to disable scaling entirely.

#### `MaxCollisionVisitsScalingPower`
- **Flag Header**: `--max-collision-visits-scaling-power=0.01..100.00`
- **Default**: `1.25` | Range: `0.01..100.00`
- **Verbatim Description**: Power to apply to the interpolation between 1 and max to make it curved.

#### `MaxCollisionVisitsScalingStart`
- **Flag Header**: `--max-collision-visits-scaling-start=1..100000`
- **Default**: `28` | Range: `1..100000`
- **Verbatim Description**: Tree size where max collision visits starts scaling up from 1.

#### `MaxConcurrentSearchers`
- **Flag Header**: `--max-concurrent-searchers=0..128`
- **Default**: `1` | Range: `0..128`
- **Verbatim Description**: If not 0, at most this many search workers can be gathering minibatches at once.

#### `MinibatchSize`
- **Flag Header**: `--minibatch-size=0..1024`
- **Default**: `0` | Range: `0..1024`
- **Verbatim Description**: How many positions the engine tries to batch together for parallel NN computation. Larger batches may reduce strength a bit, especially with a small number of playouts. Set to 0 to use a backend suggested value.

#### `MinimumKLDGainPerNode`
- **Flag Header**: `--minimum-kldgain-per-node=0.00..1.00`
- **Default**: `0.00` | Range: `0.00..1.00`
- **Verbatim Description**: If greater than 0 search will abort unless the last KLDGainAverageInterval nodes have an average gain per node of at least this much.

#### `MinimumPickingWork`
- **Flag Header**: `--minimum-picking-work=1..100000`
- **Default**: `1` | Range: `1..100000`
- **Verbatim Description**: Search branches with more than this many collisions/visits may be split off to task workers.

#### `MinimumProcessingWork`
- **Flag Header**: `--minimum-processing-work=2..100000`
- **Default**: `20` | Range: `2..100000`
- **Verbatim Description**: This many visits need to be gathered before tasks will be used to accelerate processing.

#### `MinimumRemainingPickingWork`
- **Flag Header**: `--minimum-remaining-picking-work=0..100000`
- **Default**: `20` | Range: `0..100000`
- **Verbatim Description**: Search branches won't be split off to task workers unless there is at least this much work left to do afterwards.

#### `NNCacheSize`
- **Flag Header**: `--nncache=0..999999999`
- **Default**: `2000000` | Range: `0..999999999`
- **Verbatim Description**: Number of positions to store in a memory cache. A large cache can speed up searching, but takes memory.

#### `NodesAsPlayouts`
- **Flag Header**: `--[no-]nodes-as-playouts`
- **Default**: `false`
- **Verbatim Description**: Treat UCI `go nodes` command as referring to playouts instead of visits.

#### `NodesPerSecondLimit`
- **Flag Header**: `--nps-limit=0.00..1000000.00`
- **Default**: `0.00` | Range: `0.00..1000000.00`
- **Verbatim Description**: An option to specify an upper limit to the nodes per second searched. The accuracy depends on the minibatch size used, increasing for lower sizes, and on the length of the search. Zero to disable.

#### `Ponder`
- **Flag Header**: `(uci parameter)`
- **Default**: `false`
- **Verbatim Description**: Indicates to the engine that it will be requested to ponder. This postpones resetting the search tree until the search is started.

#### `RamLimitMb`
- **Flag Header**: `--ramlimit-mb=0..100000000`
- **Default**: `0` | Range: `0..100000000`
- **Verbatim Description**: Maximum memory usage for the engine, in megabytes. The estimation is very rough, and can be off by a lot. For example, multiple visits to a terminal node counted several times, and the estimation assumes that all positions have 30 possible moves. When set to 0, no RAM limit is enforced.

#### `RootHasOwnCpuctParams`
- **Flag Header**: `--[no-]root-has-own-cpuct-params`
- **Default**: `false`
- **Verbatim Description**: If enabled, cpuct parameters for root node are taken from *AtRoot parameters. Otherwise, they are the same as for the rest of nodes. Temporary flag for transition to a new version.

#### `SearchSpinBackoff`
- **Flag Header**: `--[no-]search-spin-backoff`
- **Default**: `false`
- **Verbatim Description**: Enable backoff for the spin lock that acquires available searcher.

#### `SmartPruningFactor`
- **Flag Header**: `--smart-pruning-factor=0.00..10.00`
- **Default**: `1.33` | Range: `0.00..10.00`
- **Verbatim Description**: Do not spend time on the moves which cannot become bestmove given the remaining time to search. When no other move can overtake the current best, the search stops, saving the time. Values greater than 1 stop less promising moves from being considered even earlier. Values less than 1 causes hopeless moves to still have some attention. When set to 0, smart pruning is deactivated.

#### `SmartPruningMinimumBatches`
- **Flag Header**: `--smart-pruning-minimum-batches=0..10000`
- **Default**: `0` | Range: `0..10000`
- **Verbatim Description**: Only allow smart pruning to stop search after at least this many batches have been evaluated. It may be useful to have this value greater than the number of search threads in use.

#### `SolidTreeThreshold`
- **Flag Header**: `--solid-tree-threshold=1..2000000000`
- **Default**: `100` | Range: `1..2000000000`
- **Verbatim Description**: Only nodes with at least this number of visits will be considered for solidification for improved cache locality.

#### `StickyEndgames`
- **Flag Header**: `--[no-]sticky-endgames`
- **Default**: `true`
- **Verbatim Description**: When an end of game position is found during search, allow the eval of the previous move's position to stick to something more accurate. For example, if at least one move results in checkmate, then the position should stick as checkmated. Similarly, if all moves are drawn or checkmated, the position should stick as drawn or checkmate.

#### `TaskWorkers`
- **Flag Header**: `--task-workers=-1..128`
- **Default**: `-1` | Range: `-1..128`
- **Verbatim Description**: The number of task workers to use to help the search worker. Setting to -1 will use a heuristic value.

#### `ThreadIdlingThreshold`
- **Flag Header**: `--thread-idling-threshold=0..128`
- **Default**: `1` | Range: `0..128`
- **Verbatim Description**: If there are more than this number of search threads that are not actively in the process of either sending data to the backend or waiting for data from the backend, assume that the backend is idle.

#### `TwoFoldDraws`
- **Flag Header**: `--[no-]two-fold-draws`
- **Default**: `true`
- **Verbatim Description**: Evaluates twofold repetitions in the search tree as draws. Visits to these positions are reverted when the first occurrence is played and not in the search tree anymore.

#### `WeightsFile`
- **Flag Header**: `-w,  --weights=STRING`
- **Default**: `<autodiscover>`
- **Verbatim Description**: Path from which to load network weights. Setting it to <autodiscover> makes it search in ./ and ./weights/ subdirectories for the latest (by file date) file which looks like weights.

### First Play Urgency (FPU) (4 options)

#### `FpuStrategy`
- **Flag Header**: `--fpu-strategy=CHOICE`
- **Default**: `reduction` | Allowed: `reduction,absolute`
- **Verbatim Description**: How is an eval of unvisited node determined. "First Play Urgency" changes search behavior to visit unvisited nodes earlier or later by using a placeholder eval before checking the network. The value specified with --fpu-value results in "reduction" subtracting that value from the parent eval while "absolute" directly uses that value.

#### `FpuStrategyAtRoot`
- **Flag Header**: `--fpu-strategy-at-root=CHOICE`
- **Default**: `same` | Allowed: `reduction,absolute,same`
- **Verbatim Description**: How is an eval of unvisited root children determined. Just like --fpu-strategy except only at the root level and adjusts unvisited root children eval with --fpu-value-at-root. In addition to matching the strategies from --fpu-strategy, this can be "same" to disable the special root behavior.

#### `FpuValue`
- **Flag Header**: `--fpu-value=-100.00..100.00`
- **Default**: `0.33` | Range: `-100.00..100.00`
- **Verbatim Description**: "First Play Urgency" value used to adjust unvisited node eval based on --fpu-strategy.

#### `FpuValueAtRoot`
- **Flag Header**: `--fpu-value-at-root=-100.00..100.00`
- **Default**: `1.00` | Range: `-100.00..100.00`
- **Verbatim Description**: "First Play Urgency" value used to adjust unvisited root children eval based on --fpu-strategy-at-root. Has no effect if --fpu-strategy-at-root is "same".

### Time Management (3 options)

#### `MoveOverheadMs`
- **Flag Header**: `--move-overhead=0..100000000`
- **Default**: `200` | Range: `0..100000000`
- **Verbatim Description**: Amount of time, in milliseconds, that the engine subtracts from its total available time (to compensate for slow connection, interprocess communication, etc).

#### `TimeManager`
- **Flag Header**: `--time-manager=STRING`
- **Default**: `legacy`
- **Verbatim Description**: Name and config of a time manager. Possible names are 'legacy' (default), 'smooth', 'alphazero', and simple. See https://lc0.org/timemgr for configuration details.

#### `WDLCalibrationElo`
- **Flag Header**: `--wdl-calibration-elo=0.00..10000.00`
- **Default**: `0.00` | Range: `0.00..10000.00`
- **Verbatim Description**: Elo of the active side, adjusted for time control relative to rapid.To retain raw WDL without sharpening/softening, use default value 0.

### Tablebases (Syzygy) (2 options)

#### `SyzygyFastPlay`
- **Flag Header**: `--[no-]syzygy-fast-play`
- **Default**: `false`
- **Verbatim Description**: With DTZ tablebase files, only allow the network pick from winning moves that have shortest DTZ to play faster (but not necessarily optimally).

#### `SyzygyPath`
- **Flag Header**: `-s,  --syzygy-paths=STRING`
- **Default**: `N/A`
- **Verbatim Description**: List of Syzygy tablebase directories, list entries separated by system separator (";" for Windows, ":" for Linux).

### Temperature & Noise (17 options)

#### `Contempt`
- **Flag Header**: `--contempt=STRING`
- **Default**: `N/A`
- **Verbatim Description**: The simulated Elo advantage for the WDL conversion. Comma separated list in the form [name=]value, where the name is compared with the `UCI_Opponent` value to find the appropriate contempt value. The default value is taken from `UCI_RatingAdv` and will be overridden if either a value without name is given, or if a name match is found.

#### `ContemptMaxValue`
- **Flag Header**: `--contempt-max-value=0.00..10000.00`
- **Default**: `420.00` | Range: `0.00..10000.00`
- **Verbatim Description**: The maximum value of contempt used. Higher values will be capped.

#### `ContemptMode`
- **Flag Header**: `--contempt-mode=CHOICE`
- **Default**: `play` | Allowed: `play,white_side_analysis,black_side_analysis,disable`
- **Verbatim Description**: Affects the way asymmetric WDL parameters are applied. Default is 'play' for matches, use 'white_side_analysis' and 'black_side_analysis' for analysis. Use 'disable' to deactivate contempt.

#### `DirichletNoiseAlpha`
- **Flag Header**: `--noise-alpha=0.00..10000000.00`
- **Default**: `0.30` | Range: `0.00..10000000.00`
- **Verbatim Description**: Alpha of Dirichlet noise to control the sharpness of move probabilities. Larger values result in flatter / more evenly distributed values.

#### `DirichletNoiseEpsilon`
- **Flag Header**: `--noise-epsilon=0.00..1.00`
- **Default**: `0.00` | Range: `0.00..1.00`
- **Verbatim Description**: Amount of Dirichlet noise to combine with root priors. This allows the engine to discover new ideas during training by exploring moves which are known to be bad. Not normally used during play.

#### `PolicyTemperature`
- **Flag Header**: `--policy-softmax-temp=0.10..10.00`
- **Default**: `1.36` | Range: `0.10..10.00`
- **Verbatim Description**: Policy softmax temperature. Higher values make priors of move candidates closer to each other, widening the search.

#### `TempCutoffMove`
- **Flag Header**: `--temp-cutoff-move=0..1000`
- **Default**: `0` | Range: `0..1000`
- **Verbatim Description**: Move number, starting from which endgame temperature is used rather than initial temperature. Setting it to 0 disables cutoff.

#### `TempDecayDelayMoves`
- **Flag Header**: `--tempdecay-delay-moves=0..100`
- **Default**: `0` | Range: `0..100`
- **Verbatim Description**: Delay the linear decrease of temperature by this number of moves, decreasing linearly from initial temperature to 0. A value of 0 starts tempdecay after the first move.

#### `TempDecayMoves`
- **Flag Header**: `--tempdecay-moves=0..640`
- **Default**: `0` | Range: `0..640`
- **Verbatim Description**: Reduce temperature for every move after the first move, decreasing linearly over this number of moves from initial temperature to 0. A value of 0 disables tempdecay.

#### `TempEndgame`
- **Flag Header**: `--temp-endgame=0.00..100.00`
- **Default**: `0.00` | Range: `0.00..100.00`
- **Verbatim Description**: Temperature used during endgame (starting from cutoff move). Endgame temperature doesn't decay.

#### `TempValueCutoff`
- **Flag Header**: `--temp-value-cutoff=0.00..100.00`
- **Default**: `100.00` | Range: `0.00..100.00`
- **Verbatim Description**: When move is selected using temperature, bad moves (with win probability less than X than the best move) are not considered at all.

#### `TempVisitOffset`
- **Flag Header**: `--temp-visit-offset=-1000.00..1000.00`
- **Default**: `0.00` | Range: `-1000.00..1000.00`
- **Verbatim Description**: Adjusts visits by this value when picking a move with a temperature. If a negative offset reduces visits for a particular move below zero, that move is not picked. If no moves can be picked, no temperature is used.

#### `Temperature`
- **Flag Header**: `--temperature=0.00..100.00`
- **Default**: `0.00` | Range: `0.00..100.00`
- **Verbatim Description**: Tau value from softmax formula for the first move. If equal to 0, the engine picks the best move to make. Larger values increase randomness while making the move.

#### `UCI_RatingAdv`
- **Flag Header**: `(uci parameter)`
- **Default**: `0.00` | Range: `-10000.00..10000.00`
- **Verbatim Description**: UCI extension used by some GUIs to pass the estimated Elo advantage over the current opponent, used as the default contempt value.

#### `WDLContemptAttenuation`
- **Flag Header**: `--wdl-contempt-attenuation=-10.00..10.00`
- **Default**: `1.00` | Range: `-10.00..10.00`
- **Verbatim Description**: Scales how Elo advantage is applied for contempt. Use 1.0 for realistic analysis, and 0.5-0.6 for optimal match performance.

#### `WDLEvalObjectivity`
- **Flag Header**: `--wdl-eval-objectivity=0.00..1.00`
- **Default**: `1.00` | Range: `0.00..1.00`
- **Verbatim Description**: When calculating the centipawn eval output, decides how objective/contempt influenced the reported eval should be. Value 0.0 reports the internally used WDL values, 1.0 attempts an objective eval.

#### `WDLMaxS`
- **Flag Header**: `--wdl-max-s=0.00..10.00`
- **Default**: `1.40` | Range: `0.00..10.00`
- **Verbatim Description**: Limits the WDL derived sharpness s to a reasonable value to avoid erratic behavior at high contempt values. Default recommended for regular chess, increase value for more volatile positions like DFRC or piece odds.

### Moves-Left Head (7 options)

#### `MovesLeftConstantFactor`
- **Flag Header**: `--moves-left-constant-factor=-1.00..1.00`
- **Default**: `0.00` | Range: `-1.00..1.00`
- **Verbatim Description**: A simple multiplier to the moves left effect, can be set to 0 to only use an effect scaled by Q.

#### `MovesLeftMaxEffect`
- **Flag Header**: `--moves-left-max-effect=0.00..1.00`
- **Default**: `0.03` | Range: `0.00..1.00`
- **Verbatim Description**: Maximum bonus to add to the score of a node based on how much shorter/longer it makes the game when winning/losing.

#### `MovesLeftQuadraticFactor`
- **Flag Header**: `--moves-left-quadratic-factor=-1.00..1.00`
- **Default**: `-0.65` | Range: `-1.00..1.00`
- **Verbatim Description**: A factor which is multiplied by the square of Q of parent node and the base moves left effect.

#### `MovesLeftScaledFactor`
- **Flag Header**: `--moves-left-scaled-factor=-2.00..2.00`
- **Default**: `1.65` | Range: `-2.00..2.00`
- **Verbatim Description**: A factor which is multiplied by the absolute Q of parent node and the base moves left effect.

#### `MovesLeftSlope`
- **Flag Header**: `--moves-left-slope=0.00..1.00`
- **Default**: `0.00` | Range: `0.00..1.00`
- **Verbatim Description**: Controls how the bonus for shorter wins or longer losses is adjusted based on how many moves the move is estimated to shorten/lengthen the game. The move difference is multiplied with the slope and capped at MovesLeftMaxEffect.

#### `MovesLeftThreshold`
- **Flag Header**: `--moves-left-threshold=0.00..1.00`
- **Default**: `0.80` | Range: `0.00..1.00`
- **Verbatim Description**: Absolute value of node Q needs to exceed this value before shorter wins or longer losses are considered.

#### `UCI_ShowMovesLeft`
- **Flag Header**: `--[no-]show-movesleft`
- **Default**: `false`
- **Verbatim Description**: Show estimated moves left.

### WDL & Contempt (9 options)

#### `DrawScore`
- **Flag Header**: `--draw-score=-1.00..1.00`
- **Default**: `0.00` | Range: `-1.00..1.00`
- **Verbatim Description**: Adjustment of the draw score from white's perspective. Value 0 gives standard scoring, value -1 gives Armageddon scoring.

#### `KLDGainAverageInterval`
- **Flag Header**: `--kldgain-average-interval=1..10000000`
- **Default**: `100` | Range: `1..10000000`
- **Verbatim Description**: Used to decide how frequently to evaluate the average KLDGainPerNode to check the MinimumKLDGainPerNode, if specified.

#### `MaxOutOfOrderEvalsFactor`
- **Flag Header**: `--max-out-of-order-evals-factor=0.00..100.00`
- **Default**: `2.40` | Range: `0.00..100.00`
- **Verbatim Description**: Maximum number of out of order evals during gathering of a batch is calculated by multiplying the maximum batch size by this number.

#### `OutOfOrderEval`
- **Flag Header**: `--[no-]out-of-order-eval`
- **Default**: `true`
- **Verbatim Description**: During the gathering of a batch for NN to eval, if position happens to be in the cache or is terminal, evaluate it right away without sending the batch to the NN. When off, this may only happen with the very first node of a batch; when on, this can happen with any node.

#### `ScoreType`
- **Flag Header**: `--score-type=CHOICE`
- **Default**: `WDL_mu` | Allowed: `centipawn,centipawn_with_drawscore,centipawn_2019,centipawn_2018,win_percentage,Q,W-L,WDL_mu`
- **Verbatim Description**: What to display as score. Either centipawns (the UCI default), win percentage or Q (the actual internal score) multiplied by 100.

#### `UCI_ShowWDL`
- **Flag Header**: `--[no-]show-wdl`
- **Default**: `false`
- **Verbatim Description**: Show win, draw and lose probability.

#### `WDLBookExitBias`
- **Flag Header**: `--wdl-book-exit-bias=-2.00..2.00`
- **Default**: `0.65` | Range: `-2.00..2.00`
- **Verbatim Description**: The book exit bias used when measuring engine Elo. Value of startpos is around 0.2, value of 50% white win is 1. Only relevant if target draw rate is above 80%; ignored if WDLCalibrationElo is set.

#### `WDLDrawRateReference`
- **Flag Header**: `--wdl-draw-rate-reference=0.00..1.00`
- **Default**: `0.50` | Range: `0.00..1.00`
- **Verbatim Description**: Set this to the draw rate predicted by the used neural network at default settings. The accuracy rescaling is done relative to the reference draw rate.

#### `WDLDrawRateTarget`
- **Flag Header**: `--wdl-draw-rate-target=0.00..1.00`
- **Default**: `0.00` | Range: `0.00..1.00`
- **Verbatim Description**: To define the accuracy of play, the target draw rate in equal positions is used as a proxy. Ignored if WDLCalibrationElo is set. To retain raw WDL without sharpening/softening, use default value 0.

### Batching & Collisions (7 options)

#### `BackendOptions`
- **Flag Header**: `-o,  --backend-opts=STRING`
- **Default**: `N/A`
- **Verbatim Description**: Parameters of neural network backend. Exact parameters differ per backend.

#### `ConfigFile`
- **Flag Header**: `-c,  --config=STRING`
- **Default**: `lc0.config`
- **Verbatim Description**: Path to a configuration file. The format of the file is one command line parameter per line, e.g.: --weights=/path/to/weights

#### `HistoryFill`
- **Flag Header**: `--history-fill-new=CHOICE`
- **Default**: `fen_only` | Allowed: `no,fen_only,always`
- **Verbatim Description**: Neural network uses 7 previous board positions in addition to the current one. During the first moves of the game such historical positions don't exist, but they can be synthesized. This parameter defines when to synthesize them (always, never, or only at non-standard fen position).

#### `MaxCollisionEvents`
- **Flag Header**: `--max-collision-events=1..65536`
- **Default**: `917` | Range: `1..65536`
- **Verbatim Description**: Allowed node collision events, per batch.

#### `MaxPrefetch`
- **Flag Header**: `--max-prefetch=0..1024`
- **Default**: `0` | Range: `0..1024`
- **Verbatim Description**: When the engine cannot gather a large enough batch for immediate use, try to prefetch up to X positions which are likely to be useful soon, and put them into cache.

#### `MinimumPerTaskProcessing`
- **Flag Header**: `--minimum-per-task-processing=1..100000`
- **Default**: `8` | Range: `1..100000`
- **Verbatim Description**: Processing work won't be split into chunks smaller than this (unless its more than half of MinimumProcessingWork).

#### `Threads`
- **Flag Header**: `--[no-]preload`
- **Default**: `0` | Range: `0..128`
- **Verbatim Description**: Initialize backend and load net on engine startup. [DEFAULT: false] -t,  --threads=0..128 Number of (CPU) worker threads to use, 0 for the backend default.

### Backend & Hardware (2 options)

#### `Backend`
- **Flag Header**: `-b,  --backend=CHOICE`
- **Default**: `blas` | Allowed: `blas,eigen,trivial,random,check,roundrobin,recordreplay,multiplexing,demux`
- **Verbatim Description**: Neural network computational backend to use.

#### `IdlingMinimumWork`
- **Flag Header**: `--idling-minimum-work=0..10000`
- **Default**: `0` | Range: `0..10000`
- **Verbatim Description**: Only early exit gathering due to 'idle' backend if more than this many nodes will be sent to the backend.

### Logging & Miscellaneous (8 options)

#### `LogFile`
- **Flag Header**: `-h,  --help  Show help and exit.`
- **Default**: `N/A`
- **Verbatim Description**: --show-hidden Show hidden options. Use with --help. -l,  --logfile=STRING Write log to that file. Special value <stderr> to output the log to the console.

#### `LogLiveStats`
- **Flag Header**: `--[no-]log-live-stats`
- **Default**: `false`
- **Verbatim Description**: Do VerboseMoveStats on every info update.

#### `MultiPV`
- **Flag Header**: `--multipv=1..500`
- **Default**: `1` | Range: `1..500`
- **Verbatim Description**: Number of game play lines (principal variations) to show in UCI info output.

#### `PerPVCounters`
- **Flag Header**: `--[no-]per-pv-counters`
- **Default**: `false`
- **Verbatim Description**: Show node counts per principal variation instead of total nodes in UCI.

#### `StrictTiming`
- **Flag Header**: `--[no-]strict-uci-timing`
- **Default**: `false`
- **Verbatim Description**: The UCI host compensates for lag, waits for the 'readyok' reply before sending 'go' and only then starts timing.

#### `UCI_Chess960`
- **Flag Header**: `--[no-]chess960`
- **Default**: `false`
- **Verbatim Description**: Castling moves are encoded as "king takes rook".

#### `UCI_Opponent`
- **Flag Header**: `(uci parameter)`
- **Default**: `N/A`
- **Verbatim Description**: UCI option used by the GUI to pass the name and other information about the current opponent.

#### `VerboseMoveStats`
- **Flag Header**: `-v,  --[no-]verbose-move-stats`
- **Default**: `false`
- **Verbatim Description**: Display Q, V, N, U and P values of every move candidate after each move.

## 4. Previously Uncovered Topics (6 Measured Gaps)

Derived strictly by filtering the parsed binary UCI options and measured `describenet` outputs. No facts or flag names originate outside the binary outputs.

### 1. Syzygy / Endgame Tablebases

- **`SyzygyFastPlay`** (`--[no-]syzygy-fast-play` | Default: `false`): With DTZ tablebase files, only allow the network pick from winning moves that have shortest DTZ to play faster (but not necessarily optimally).
- **`SyzygyPath`** (`-s,  --syzygy-paths=STRING` | Default: `N/A`): List of Syzygy tablebase directories, list entries separated by system separator (";" for Windows, ":" for Linux).

### 2. Moves-Left Head (MLH)

- **Architecture Fact (from `raw/describenet_bt3.txt`)**: Network head output includes `MOVES_LEFT_V1` auxiliary remaining ply prediction.
- **`MovesLeftConstantFactor`** (`--moves-left-constant-factor=-1.00..1.00` | Default: `0.00` | Range: `-1.00..1.00`): A simple multiplier to the moves left effect, can be set to 0 to only use an effect scaled by Q.
- **`MovesLeftMaxEffect`** (`--moves-left-max-effect=0.00..1.00` | Default: `0.03` | Range: `0.00..1.00`): Maximum bonus to add to the score of a node based on how much shorter/longer it makes the game when winning/losing.
- **`MovesLeftQuadraticFactor`** (`--moves-left-quadratic-factor=-1.00..1.00` | Default: `-0.65` | Range: `-1.00..1.00`): A factor which is multiplied by the square of Q of parent node and the base moves left effect.
- **`MovesLeftScaledFactor`** (`--moves-left-scaled-factor=-2.00..2.00` | Default: `1.65` | Range: `-2.00..2.00`): A factor which is multiplied by the absolute Q of parent node and the base moves left effect.
- **`MovesLeftSlope`** (`--moves-left-slope=0.00..1.00` | Default: `0.00` | Range: `0.00..1.00`): Controls how the bonus for shorter wins or longer losses is adjusted based on how many moves the move is estimated to shorten/lengthen the game. The move difference is multiplied with the slope and capped at MovesLeftMaxEffect.
- **`MovesLeftThreshold`** (`--moves-left-threshold=0.00..1.00` | Default: `0.80` | Range: `0.00..1.00`): Absolute value of node Q needs to exceed this value before shorter wins or longer losses are considered.
- **`UCI_ShowMovesLeft`** (`--[no-]show-movesleft` | Default: `false`): Show estimated moves left.

### 3. Contempt & WDL Customization

- **`Contempt`** (`--contempt=STRING` | Default: `N/A`): The simulated Elo advantage for the WDL conversion. Comma separated list in the form [name=]value, where the name is compared with the `UCI_Opponent` value to find the appropriate contempt value. The default value is taken from `UCI_RatingAdv` and will be overridden if either a value without name is given, or if a name match is found.
- **`ContemptMaxValue`** (`--contempt-max-value=0.00..10000.00` | Default: `420.00` | Range: `0.00..10000.00`): The maximum value of contempt used. Higher values will be capped.
- **`ContemptMode`** (`--contempt-mode=CHOICE` | Default: `play` | Allowed: `play,white_side_analysis,black_side_analysis,disable`): Affects the way asymmetric WDL parameters are applied. Default is 'play' for matches, use 'white_side_analysis' and 'black_side_analysis' for analysis. Use 'disable' to deactivate contempt.
- **`DrawScore`** (`--draw-score=-1.00..1.00` | Default: `0.00` | Range: `-1.00..1.00`): Adjustment of the draw score from white's perspective. Value 0 gives standard scoring, value -1 gives Armageddon scoring.
- **`TwoFoldDraws`** (`--[no-]two-fold-draws` | Default: `true`): Evaluates twofold repetitions in the search tree as draws. Visits to these positions are reverted when the first occurrence is played and not in the search tree anymore.
- **`UCI_ShowWDL`** (`--[no-]show-wdl` | Default: `false`): Show win, draw and lose probability.
- **`WDLBookExitBias`** (`--wdl-book-exit-bias=-2.00..2.00` | Default: `0.65` | Range: `-2.00..2.00`): The book exit bias used when measuring engine Elo. Value of startpos is around 0.2, value of 50% white win is 1. Only relevant if target draw rate is above 80%; ignored if WDLCalibrationElo is set.
- **`WDLCalibrationElo`** (`--wdl-calibration-elo=0.00..10000.00` | Default: `0.00` | Range: `0.00..10000.00`): Elo of the active side, adjusted for time control relative to rapid.To retain raw WDL without sharpening/softening, use default value 0.
- **`WDLContemptAttenuation`** (`--wdl-contempt-attenuation=-10.00..10.00` | Default: `1.00` | Range: `-10.00..10.00`): Scales how Elo advantage is applied for contempt. Use 1.0 for realistic analysis, and 0.5-0.6 for optimal match performance.
- **`WDLDrawRateReference`** (`--wdl-draw-rate-reference=0.00..1.00` | Default: `0.50` | Range: `0.00..1.00`): Set this to the draw rate predicted by the used neural network at default settings. The accuracy rescaling is done relative to the reference draw rate.
- **`WDLDrawRateTarget`** (`--wdl-draw-rate-target=0.00..1.00` | Default: `0.00` | Range: `0.00..1.00`): To define the accuracy of play, the target draw rate in equal positions is used as a proxy. Ignored if WDLCalibrationElo is set. To retain raw WDL without sharpening/softening, use default value 0.
- **`WDLEvalObjectivity`** (`--wdl-eval-objectivity=0.00..1.00` | Default: `1.00` | Range: `0.00..1.00`): When calculating the centipawn eval output, decides how objective/contempt influenced the reported eval should be. Value 0.0 reports the internally used WDL values, 1.0 attempts an objective eval.
- **`WDLMaxS`** (`--wdl-max-s=0.00..10.00` | Default: `1.40` | Range: `0.00..10.00`): Limits the WDL derived sharpness s to a reasonable value to avoid erratic behavior at high contempt values. Default recommended for regular chess, increase value for more volatile positions like DFRC or piece odds.

### 4. Smart Pruning

- **`SmartPruningFactor`** (`--smart-pruning-factor=0.00..10.00` | Default: `1.33` | Range: `0.00..10.00`): Do not spend time on the moves which cannot become bestmove given the remaining time to search. When no other move can overtake the current best, the search stops, saving the time. Values greater than 1 stop less promising moves from being considered even earlier. Values less than 1 causes hopeless moves to still have some attention. When set to 0, smart pruning is deactivated.
- **`SmartPruningMinimumBatches`** (`--smart-pruning-minimum-batches=0..10000` | Default: `0` | Range: `0..10000`): Only allow smart pruning to stop search after at least this many batches have been evaluated. It may be useful to have this value greater than the number of search threads in use.

### 5. Node Collisions & Task Workers

- **`MaxPrefetch`** (`--max-prefetch=0..1024` | Default: `0` | Range: `0..1024`): When the engine cannot gather a large enough batch for immediate use, try to prefetch up to X positions which are likely to be useful soon, and put them into cache.
- **`MinimumPickingWork`** (`--minimum-picking-work=1..100000` | Default: `1` | Range: `1..100000`): Search branches with more than this many collisions/visits may be split off to task workers.
- **`MinimumProcessingWork`** (`--minimum-processing-work=2..100000` | Default: `20` | Range: `2..100000`): This many visits need to be gathered before tasks will be used to accelerate processing.
- **`MinimumRemainingPickingWork`** (`--minimum-remaining-picking-work=0..100000` | Default: `20` | Range: `0..100000`): Search branches won't be split off to task workers unless there is at least this much work left to do afterwards.
- **`TaskWorkers`** (`--task-workers=-1..128` | Default: `-1` | Range: `-1..128`): The number of task workers to use to help the search worker. Setting to -1 will use a heuristic value.

### 6. Temperature & Exploration Noise

- **`DirichletNoiseAlpha`** (`--noise-alpha=0.00..10000000.00` | Default: `0.30` | Range: `0.00..10000000.00`): Alpha of Dirichlet noise to control the sharpness of move probabilities. Larger values result in flatter / more evenly distributed values.
- **`DirichletNoiseEpsilon`** (`--noise-epsilon=0.00..1.00` | Default: `0.00` | Range: `0.00..1.00`): Amount of Dirichlet noise to combine with root priors. This allows the engine to discover new ideas during training by exploring moves which are known to be bad. Not normally used during play.
- **`PolicyTemperature`** (`--policy-softmax-temp=0.10..10.00` | Default: `1.36` | Range: `0.10..10.00`): Policy softmax temperature. Higher values make priors of move candidates closer to each other, widening the search.
- **`TempCutoffMove`** (`--temp-cutoff-move=0..1000` | Default: `0` | Range: `0..1000`): Move number, starting from which endgame temperature is used rather than initial temperature. Setting it to 0 disables cutoff.
- **`TempDecayDelayMoves`** (`--tempdecay-delay-moves=0..100` | Default: `0` | Range: `0..100`): Delay the linear decrease of temperature by this number of moves, decreasing linearly from initial temperature to 0. A value of 0 starts tempdecay after the first move.
- **`TempDecayMoves`** (`--tempdecay-moves=0..640` | Default: `0` | Range: `0..640`): Reduce temperature for every move after the first move, decreasing linearly over this number of moves from initial temperature to 0. A value of 0 disables tempdecay.
- **`TempEndgame`** (`--temp-endgame=0.00..100.00` | Default: `0.00` | Range: `0.00..100.00`): Temperature used during endgame (starting from cutoff move). Endgame temperature doesn't decay.
- **`TempValueCutoff`** (`--temp-value-cutoff=0.00..100.00` | Default: `100.00` | Range: `0.00..100.00`): When move is selected using temperature, bad moves (with win probability less than X than the best move) are not considered at all.
- **`TempVisitOffset`** (`--temp-visit-offset=-1000.00..1000.00` | Default: `0.00` | Range: `-1000.00..1000.00`): Adjusts visits by this value when picking a move with a temperature. If a negative offset reduces visits for a particular move below zero, that move is not picked. If no moves can be picked, no temperature is used.
- **`Temperature`** (`--temperature=0.00..100.00` | Default: `0.00` | Range: `0.00..100.00`): Tau value from softmax formula for the first move. If equal to 0, the engine picks the best move to make. Larger values increase randomness while making the move.

## 5. Constants Cross-Check Table

| Visual Guide Constant | Visual Guide Value | Binary Default (`lc0.exe`) | Match / Nuance Notes |
|---|---|---|---|
| $c_{\mathrm{puct}}$ base | 1.745 | `CPuct DEFAULT: 1.75` | Match (1.75 printed to 2 dp in binary help output). |
| $c_{\mathrm{puct}}$ base parameter | 38740 | `CPuctBase DEFAULT: 38739.00` | Match ($c_{\mathrm{mod}} = 38740$; denominator $c_{\mathrm{mod}}-1 = 38739$). |
| $c_{\mathrm{puct}}$ factor | 3.894 | `CPuctFactor DEFAULT: 3.89` | Match (3.89 printed to 2 dp in binary help output). |
| $Q_{\mathrm{FPU}}$ penalty multiplier | 0.33 | `FpuValue DEFAULT: 0.33` | Match (`FpuStrategy DEFAULT: reduction`). |
| Root CPUCT Parameters | Same formula | `RootHasOwnCpuctParams DEFAULT: false` | Match (root uses standard CPUCT parameters). |
| Root FPU Strategy | Same formula | `FpuStrategyAtRoot DEFAULT: same`, `FpuValueAtRoot DEFAULT: 1.00` | Nuance (separate root FPU path exists, currently set to `same`). |
