"""
Acceptance tests for relational_facts module.

Reproduces the proven read on position:
rn3rk1/pp3ppp/1q3n2/2b5/b1pN4/1P2P1PP/P1P1P1BK/R1BQ1R2 b - - 0 17, pov = Black.
"""

import chess
from backend.training.relational_facts import (
    protected_passed_pawns,
    attacks_on_valuable,
    pins_and_xrays,
    conditional_pins,
    defender_removed,
    king_pressure,
    relational_facts,
)


def get_acceptance_boards():
    """
    Start position: rn3rk1/pp3ppp/1q3n2/2b5/b1pN4/1P2P1PP/P1P1P1BK/R1BQ1R2 b - - 0 17
    Line: 1... c4xb3 (White waits e.g. a2a3) 2... b3xc2
    """
    start_fen = "rn3rk1/pp3ppp/1q3n2/2b5/b1pN4/1P2P1PP/P1P1P1BK/R1BQ1R2 b - - 0 17"
    start_board = chess.Board(start_fen)

    # Black plays c4xb3
    board_after_c4b3 = start_board.copy()
    board_after_c4b3.push_san("cxb3")

    # White waits with a2a3
    board_after_waiting = board_after_c4b3.copy()
    board_after_waiting.push_san("a3")

    # Black plays b3xc2
    board_after_b3c2 = board_after_waiting.copy()
    board_after_b3c2.push_san("bxc2")

    return start_board, board_after_c4b3, board_after_waiting, board_after_b3c2


def test_protected_passed_pawns_acceptance():
    """
    1. protected_passed_pawns includes c2, defended by a4, 1 from queening.
    Fails if passer check miscalculates enemy pawn blockers or defender attacks.
    """
    _, _, _, board_after_b3c2 = get_acceptance_boards()
    facts = protected_passed_pawns(board_after_b3c2, chess.BLACK)

    c2_passers = [f for f in facts if f["pawn"] == "c2"]
    assert len(c2_passers) == 1, (
        f"Expected 1 protected passed pawn on c2, found {len(c2_passers)} in {facts}"
    )

    fact = c2_passers[0]
    assert fact["distance"] == 1, f"Expected distance=1 to queening, got {fact['distance']}"
    assert "a4" in fact["defenders"], f"Expected defender a4 in {fact['defenders']}"


def test_attacks_on_valuable_acceptance():
    """
    2. attacks_on_valuable includes Pc2 attacks the Q on d1.
    Fails if attack detection misses pawns attacking queens.
    """
    _, _, _, board_after_b3c2 = get_acceptance_boards()
    facts = attacks_on_valuable(board_after_b3c2, chess.BLACK)

    c2_q_attacks = [
        f for f in facts if f["attacker_square"] == "c2" and f["target_square"] == "d1"
    ]
    assert len(c2_q_attacks) == 1, (
        f"Expected Pc2 attacking Qd1, found {len(c2_q_attacks)} in {facts}"
    )
    assert c2_q_attacks[0]["target_piece"] == "Q"


def test_conditional_pins_acceptance():
    """
    3. conditional_pins(..., c2) reports a White piece on c2 would be pinned by Ba4 to Qd1.
    Evaluated after ...b3xc2 when b3 is clear.
    Fails if hypothetical placement or slider ray scanning ignores clear rays.
    """
    _, _, _, board_after_b3c2 = get_acceptance_boards()
    facts = conditional_pins(board_after_b3c2, chess.BLACK, "c2")

    c2_pins = [
        f for f in facts if f["square"] == "c2" and f["attacker_square"] == "a4" and f["target_square"] == "d1"
    ]
    assert len(c2_pins) == 1, (
        f"Expected conditional pin on c2 by Ba4 to Qd1, found {len(c2_pins)} in {facts}"
    )
    assert c2_pins[0]["target_piece"] == "Q"


def test_defender_removed_acceptance():
    """
    4. defender_removed(start, Bxd4=c5d4, Black) reports the captured knight controlled c2.
    Fails if capture check does not record attacker coverage of captured piece before removal.
    """
    start_board, _, _, _ = get_acceptance_boards()
    move_c5d4 = chess.Move.from_uci("c5d4")

    fact = defender_removed(start_board, move_c5d4, chess.BLACK)
    assert fact is not None, "Expected defender_removed fact for Bxd4, got None"
    assert fact["captured_piece"] == "N"
    assert fact["captured_square"] == "d4"
    assert "c2" in fact["controlled_squares"], (
        f"Expected c2 in controlled squares of Nd4, got {fact['controlled_squares']}"
    )


def test_negative_mutation_no_bogus_xray_g1():
    """
    5. Negative / mutation: pins_and_xrays on the start position must NOT report the bogus
    "Bc5 x-rays to g1" family — assert no pin fact naming g1 as the pinned-to target through a blocked ray.
    Fails if collinearity check allows pins through multiple blocking pieces or to empty/non-valuable squares.
    """
    start_board, _, _, _ = get_acceptance_boards()
    facts = pins_and_xrays(start_board, chess.BLACK)

    g1_pins = [f for f in facts if f["target_square"] == "g1"]
    assert len(g1_pins) == 0, (
        f"Found bogus x-ray/pin fact targeting g1 through blocked ray: {g1_pins}"
    )


def test_relational_facts_composition():
    """
    Test composition function relational_facts over the acceptance line.
    """
    start_fen = "rn3rk1/pp3ppp/1q3n2/2b5/b1pN4/1P2P1PP/P1P1P1BK/R1BQ1R2 b - - 0 17"
    line_ucis = ["c4b3", "a2a3", "b3c2"]

    res = relational_facts(start_fen, line_ucis, chess.BLACK)
    assert "position_facts" in res
    assert "per_move" in res
    assert len(res["per_move"]) == 3
