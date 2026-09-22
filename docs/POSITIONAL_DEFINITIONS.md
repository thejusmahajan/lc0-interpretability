# Positional Fact Definitions (Batches 1, 2 & 3)

This document contains the ground-truth definitions for positional-fact extractors implemented in `backend/training/relational_facts.py`.

---

## 1. Pawn Weaknesses (`pawn_weaknesses`)

For a pawn of color `color` on square `s` (file `f`, rank `r`), where `dr = +1` for White and `-1` for Black:

- **Isolated Pawn**: `color` has no pawn on adjacent files (`f-1` or `f+1`) on any rank (0–7).
- **Doubled Pawns**: `color` has more than one pawn on file `f` (reported once per file listing all pawns on that file).
- **Backward Pawn**: A pawn is backward if ALL three conditions hold:
  1. **No friendly support**: No friendly pawn on an adjacent file (`f-1` or `f+1`) sits at a rank *not ahead* of `r` (i.e. no adjacent friendly pawn with `rank_adj * dr <= r * dr`).
  2. **Stop square blocked/controlled**: Its stop square (`s + dr`) is controlled OR occupied by an enemy pawn.
  3. **Semi-open file**: No friendly pawn exists on file `f` ahead of `s` (i.e. `rank * dr > r * dr`).

### Fact Schema
```json
{
  "kind": "pawn_weakness",
  "weakness": "isolated | doubled | backward",
  "square": "e6",
  "color": "White | Black",
  "attacked": true,
  "text": "Black's e6 pawn is backward (and under attack)"
}
```

---

## 2. Tied Defenders (`tied_defenders`)

A friendly piece (excluding pawns and kings) of color `color` is **tied to defense** if:
1. It defends a friendly pawn `W` on square `W_sq` (i.e. the piece square is in `board.attackers(color, W_sq)`).
2. The pawn `W` is an identified weakness (`isolated`, `backward`, or `doubled`).
3. The pawn `W` is currently attacked by at least one enemy piece (`board.attackers(not color, W_sq)` is non-empty).

### Fact Schema
```json
{
  "kind": "tied_defender",
  "piece": "R | N | B | Q",
  "square": "d7",
  "defends": "e6",
  "text": "The B on d7 is tied to the defence of the weak e6 pawn"
}
```

---

## 3. Outposts (`outposts`)

An enemy piece (Knight, Bishop, or Rook) on square `sq` is an **outpost** in `color`'s structure when:
1. `sq` is located in `color`'s half of the board (ranks 1–4 for White's half as defended against Black; ranks 5–8 for Black's half).
2. **Hole condition**: No `color` pawn can EVER challenge `sq` — i.e. neither adjacent file (`file(sq)-1` or `file(sq)+1`) contains a `color` pawn on a rank behind `sq` (where `pawn_rank * dr < sq_rank * dr`).

### Fact Schema
```json
{
  "kind": "outpost",
  "enemy_piece": "N | B | R",
  "square": "d5",
  "defender_color": "Black",
  "text": "The enemy N on d5 sits on an outpost — a hole Black can no longer challenge with a pawn"
}
```

---

## 4. Rook on 7th Rank (`rook_on_seventh`)

A `color` rook or queen occupying the enemy's 2nd rank (rank index 6 for White, rank index 1 for Black).

### Fact Schema
```json
{
  "kind": "rook_seventh",
  "piece": "R | Q",
  "square": "c7",
  "color": "White | Black",
  "text": "White's rook on c7 occupies the 7th rank"
}
```

---

## 5. Control of Open / Half-Open Files (`open_file_pieces`)

A `color` rook or queen on file `f` where:
- **Open file**: File `f` contains **0** pawns of either color.
- **Half-open file**: File `f` contains **0** `color` pawns, but the enemy has $\ge 1$ pawn.
- Files containing friendly pawns emit no fact.

### Fact Schema
```json
{
  "kind": "file_control",
  "piece": "R | Q",
  "square": "d1",
  "file": "d",
  "kind_of": "open | half-open",
  "text": "Black's rook on the open d-file"
}
```

---

## 6. Bishop Quality & Activity (`bishop_quality`)

For a `color` bishop on square `sq`:
- `own_pawns_on_color`: Count of friendly pawns (`color`) occupying squares of the **same color** (light/dark) as `sq`.
- `mobility`: Count of squares in `board.attacks(sq)` NOT occupied by friendly pieces.

A fact is emitted **only at clear extremes**:
- **Bad / Restricted**: `own_pawns_on_color >= 5` AND `mobility <= 3`.
- **Active**: `own_pawns_on_color <= 2` AND `mobility >= 7`.

### Fact Schema
```json
{
  "kind": "bishop_quality",
  "quality": "bad | active",
  "square": "c8",
  "color": "Black",
  "own_pawns_on_color": 6,
  "mobility": 1,
  "text": "Black's c8 bishop is a bad bishop — 6 of its own pawns sit on its colour, restricting it (mobility 1)"
}
```

---

## 7. Colour-Complex Weakness (`color_complex_weakness`)

Evaluates persistent color-complex weaknesses for `color` on square color `W` (`LIGHT` or `DARK`):

1. **Defender Gone (Hard Gate)**: `color` has **NO** bishop on color `W`. If `color` retains a bishop of color `W`, skip (emit no fact).
2. **Holes in Friendly Camp**: Camp ranks are defined as ranks 3–4 (indices 2–3) for White and ranks 5–6 (indices 4–5) for Black. A square `sq` of color `W` in `camp` is a **hole** if `_is_hole(board, sq, color)` is `True` (no friendly pawn on adjacent files behind `sq` can ever advance to attack it).
3. **Threshold**: Emit a fact ONLY if the count of such holes in `camp` is $\ge 3$.

### Fact Schema
```json
{
  "kind": "color_complex",
  "complex_color": "light | dark",
  "holes": ["a5", "c5", "e5", "g5", "b6", "d6", "f6", "h6"],
  "bishop_gone": true,
  "color": "Black",
  "text": "Black has a weak dark-square complex — 8 dark squares in its own camp that no pawn can cover, and its dark-squared bishop is gone: a5, c5, e5, g5, b6, d6, f6, h6"
}
```
