import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import RepertoirePanel from '../RepertoirePanel';
import * as trainingApi from '../../../api/training';

// Mock TrainingBoard for deterministic unit/integration testing
vi.mock('../TrainingBoard', () => ({
  default: ({ fen, onMove, interactive }: any) => (
    <div data-testid="training-board" data-fen={fen} data-interactive={String(interactive)}>
      <button
        data-testid="move-d2d4"
        disabled={!interactive}
        onClick={() => onMove?.('d2d4', 'd4')}
      >
        Play d2d4
      </button>
      <button
        data-testid="move-e2e4"
        disabled={!interactive}
        onClick={() => onMove?.('e2e4', 'e4')}
      >
        Play e2e4
      </button>

      {/* Castling test helpers */}
      <button
        data-testid="move-e1g1"
        disabled={!interactive}
        onClick={() => onMove?.('e1g1', 'O-O')}
      >
        Play e1g1
      </button>
      <button
        data-testid="move-e1h1"
        disabled={!interactive}
        onClick={() => onMove?.('e1h1', 'O-O')}
      >
        Play e1h1
      </button>
      <button
        data-testid="move-e8g8"
        disabled={!interactive}
        onClick={() => onMove?.('e8g8', 'O-O')}
      >
        Play e8g8
      </button>
      <button
        data-testid="move-e8h8"
        disabled={!interactive}
        onClick={() => onMove?.('e8h8', 'O-O')}
      >
        Play e8h8
      </button>
      <button
        data-testid="move-e1c1"
        disabled={!interactive}
        onClick={() => onMove?.('e1c1', 'O-O-O')}
      >
        Play e1c1
      </button>
      <button
        data-testid="move-e1a1"
        disabled={!interactive}
        onClick={() => onMove?.('e1a1', 'O-O-O')}
      >
        Play e1a1
      </button>
      <button
        data-testid="move-e8c8"
        disabled={!interactive}
        onClick={() => onMove?.('e8c8', 'O-O-O')}
      >
        Play e8c8
      </button>
      <button
        data-testid="move-e8a8"
        disabled={!interactive}
        onClick={() => onMove?.('e8a8', 'O-O-O')}
      >
        Play e8a8
      </button>
    </div>
  ),
}));

vi.mock('../../../api/training', () => ({
  listRepertoires: vi.fn(),
  buildRepertoire: vi.fn(),
  getRepertoireTree: vi.fn(),
  getTopOpenings: vi.fn(() => Promise.resolve([])),
}));

describe('RepertoireTrainer Integration & Edge-Case Tests', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    (trainingApi.listRepertoires as any).mockResolvedValue([
      {
        style: 'weakness',
        color: 'white',
        recommendations: [
          { eco: 'A40', name: "Queen's Pawn Opening", line_pgn: '1. d4 e6', eval_cp: 26 },
        ],
      },
    ]);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // 1. Loading state
  it('1. Renders loading state while tree fetch is pending', async () => {
    (trainingApi.getRepertoireTree as any).mockReturnValue(new Promise(() => {})); // Never resolves

    render(<RepertoirePanel />);
    const trainBtn = await screen.findByRole('button', { name: /Train Repertoire/i });
    fireEvent.click(trainBtn);

    expect(screen.getByText(/Building \/ Loading Variation Tree.../i)).toBeInTheDocument();
  });

  // 2. Error state
  it('2. Renders error message when tree fetch fails', async () => {
    (trainingApi.getRepertoireTree as any).mockRejectedValue(new Error('Network error fetching tree'));

    render(<RepertoirePanel />);
    const trainBtn = await screen.findByRole('button', { name: /Train Repertoire/i });
    fireEvent.click(trainBtn);

    expect(await screen.findByText(/Network error fetching tree/i)).toBeInTheDocument();
  });

  // 3. Empty tree (nodes: [])
  it('3. Renders friendly empty state and non-interactive board for empty nodes', async () => {
    (trainingApi.getRepertoireTree as any).mockResolvedValue({
      eco: 'A40',
      color: 'white',
      root_fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
      nodes: [],
    });

    render(<RepertoirePanel />);
    const trainBtn = await screen.findByRole('button', { name: /Train Repertoire/i });
    fireEvent.click(trainBtn);

    expect(await screen.findByText(/No Trainable Variation Tree/i)).toBeInTheDocument();
    expect(screen.getByText(/too few of your games reach this line/i)).toBeInTheDocument();
    expect(screen.queryByTestId('training-board')).not.toBeInTheDocument();
  });

  // 4. Degenerate root (1 node, user-node, no user_move)
  it('4. Renders friendly state for degenerate single-node tree with no user_move', async () => {
    (trainingApi.getRepertoireTree as any).mockResolvedValue({
      eco: 'C99',
      color: 'white',
      root_fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
      nodes: [
        {
          id: 'C99-w-0001',
          fen_before: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
          ply: 0,
          is_user_node: true,
          n_games: 1,
          parent: null,
          children: [],
          opponent_replies: [],
        },
      ],
    });

    render(<RepertoirePanel />);
    const trainBtn = await screen.findByRole('button', { name: /Train Repertoire/i });
    fireEvent.click(trainBtn);

    expect(await screen.findByText(/No Trainable Variation Tree/i)).toBeInTheDocument();
    expect(screen.queryByTestId('training-board')).not.toBeInTheDocument();
  });

  // 5. Happy path rich tree
  it('5. Happy path: user plays correct move -> advances; wrong move -> error message', async () => {
    const fen0 = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    const fen1AfterReply = 'rnbqkbnr/pppp1ppp/4p3/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 2';

    (trainingApi.getRepertoireTree as any).mockResolvedValue({
      eco: 'A40',
      color: 'white',
      root_fen: fen0,
      tabiya_ply: 1,
      depth: 6,
      n_games: 10,
      nodes: [
        {
          id: 'A40-w-0001',
          fen_before: fen0,
          ply: 0,
          is_user_node: true,
          user_move: { uci: 'd2d4', san: 'd4' },
          eval_cp: 26,
          complexity: 0.23,
          user_blind_rate: 0.1,
          critical: false,
          children: ['A40-w-0002'],
          opponent_replies: [{ uci: 'e7e6', san: 'e6', count: 10, pct: 1.0 }],
        },
        {
          id: 'A40-w-0002',
          fen_before: fen1AfterReply,
          ply: 2,
          is_user_node: true,
          user_move: { uci: 'g1f3', san: 'Nf3' },
          eval_cp: 30,
          complexity: 0.25,
          user_blind_rate: 0.0,
          critical: false,
          children: [],
          opponent_replies: [],
        },
      ],
    });

    render(<RepertoirePanel />);
    const trainBtn = await screen.findByRole('button', { name: /Train Repertoire/i });
    fireEvent.click(trainBtn);

    const board = await screen.findByTestId('training-board');
    expect(board).toHaveAttribute('data-interactive', 'true');

    // Test Wrong move
    const wrongMoveBtn = screen.getByTestId('move-e2e4');
    fireEvent.click(wrongMoveBtn);

    expect(screen.getByText(/Wrong move! Correct move is d4 \(d2d4\)/i)).toBeInTheDocument();

    // Test Correct move
    const correctMoveBtn = screen.getByTestId('move-d2d4');
    fireEvent.click(correctMoveBtn);

    expect(screen.getByText(/Correct! Played d4/i)).toBeInTheDocument();

    // Wait for opponent reply animation
    await waitFor(
      () => {
        expect(screen.getByText(/Ply 2 \/ Depth 6/i)).toBeInTheDocument();
      },
      { timeout: 4000 }
    );
  });

  // 6. Black repertoire root (ply 0 opponent node)
  it('6. Black repertoire root: auto-plays opponent reply at ply 0 and lands on user node', async () => {
    const fen0 = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    const fen1AfterOpp = 'rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1';

    (trainingApi.getRepertoireTree as any).mockResolvedValue({
      eco: 'A40',
      color: 'black',
      root_fen: fen0,
      depth: 6,
      n_games: 5,
      nodes: [
        {
          id: 'A40-b-0001',
          fen_before: fen0,
          ply: 0,
          is_user_node: false,
          children: ['A40-b-0002'],
          opponent_replies: [{ uci: 'd2d4', san: 'd4', count: 5, pct: 1.0 }],
        },
        {
          id: 'A40-b-0002',
          fen_before: fen1AfterOpp,
          ply: 1,
          is_user_node: true,
          user_move: { uci: 'e7e6', san: 'e6' },
          eval_cp: -20,
          complexity: 0.22,
          user_blind_rate: 0.0,
          critical: false,
          children: [],
          opponent_replies: [],
        },
      ],
    });

    render(<RepertoirePanel />);
    const trainBtn = await screen.findByRole('button', { name: /Train Repertoire/i });
    fireEvent.click(trainBtn);

    await waitFor(
      () => {
        expect(screen.getByText(/Ply 1 \/ Depth 6/i)).toBeInTheDocument();
      },
      { timeout: 4000 }
    );

    expect(screen.getByText(/Your turn: find the correct repertoire move/i)).toBeInTheDocument();
  });

  // 7. Castling move equivalence
  it('7. Accepts both castling spellings (e1g1 / e1h1, e8g8 / e8h8, e1c1 / e1a1, e8c8 / e8a8)', async () => {
    const fen0 = 'r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1';
    (trainingApi.getRepertoireTree as any).mockResolvedValue({
      eco: 'A00',
      color: 'white',
      root_fen: fen0,
      depth: 4,
      nodes: [
        {
          id: 'A00-w-0001',
          fen_before: fen0,
          ply: 0,
          is_user_node: true,
          user_move: { uci: 'e1h1', san: 'O-O' },
          eval_cp: 50,
          children: [],
          opponent_replies: [],
        },
      ],
    });

    render(<RepertoirePanel />);
    const trainBtn = await screen.findByRole('button', { name: /Train Repertoire/i });
    fireEvent.click(trainBtn);

    await screen.findByTestId('training-board');

    // Entering e1g1 should be accepted when target is e1h1
    const moveBtn = screen.getByTestId('move-e1g1');
    fireEvent.click(moveBtn);

    expect(screen.getByText(/Correct! Played O-O/i)).toBeInTheDocument();
  });

  // 8. Critical badge + stats
  it('8. Renders critical node badge and detailed statistics', async () => {
    const fen0 = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    (trainingApi.getRepertoireTree as any).mockResolvedValue({
      eco: 'A40',
      color: 'white',
      root_fen: fen0,
      depth: 6,
      nodes: [
        {
          id: 'A40-w-0001',
          fen_before: fen0,
          ply: 2,
          is_user_node: true,
          user_move: { uci: 'd2d4', san: 'd4' },
          eval_cp: 26,
          complexity: 0.35,
          user_blind_rate: 0.5,
          critical: true,
          critical_reason: 'blind_rate',
          children: [],
          opponent_replies: [],
        },
      ],
    });

    render(<RepertoirePanel />);
    const trainBtn = await screen.findByRole('button', { name: /Train Repertoire/i });
    fireEvent.click(trainBtn);

    expect(await screen.findByText(/⚡ CRITICAL NODE \(blind_rate\)/i)).toBeInTheDocument();
    expect(screen.getByText(/\+0\.26/i)).toBeInTheDocument();
    expect(screen.getByText(/0\.35/i)).toBeInTheDocument();
    expect(screen.getByText(/50%/i)).toBeInTheDocument();
  });

  // 9. Opponent reply re-roll
  it('9. Re-roll line allows switching between opponent reply branches', async () => {
    const fen0 = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    (trainingApi.getRepertoireTree as any).mockResolvedValue({
      eco: 'A40',
      color: 'white',
      root_fen: fen0,
      depth: 6,
      nodes: [
        {
          id: 'A40-w-0001',
          fen_before: fen0,
          ply: 0,
          is_user_node: true,
          user_move: { uci: 'd2d4', san: 'd4' },
          eval_cp: 26,
          children: [],
          opponent_replies: [
            { uci: 'e7e6', san: 'e6', count: 6, pct: 0.6 },
            { uci: 'c7c6', san: 'c6', count: 4, pct: 0.4 },
          ],
        },
      ],
    });

    render(<RepertoirePanel />);
    const trainBtn = await screen.findByRole('button', { name: /Train Repertoire/i });
    fireEvent.click(trainBtn);

    expect(await screen.findByText(/e6 \(60%\)/i)).toBeInTheDocument();
    expect(screen.getByText(/c6 \(40%\)/i)).toBeInTheDocument();

    const c6Btn = screen.getByText(/c6 \(40%\)/i);
    fireEvent.click(c6Btn);

    expect(c6Btn).toHaveClass('active');
  });

  // 10. Branch completion
  it('10. Shows Branch complete banner at leaf node; Walk Another Line and Reset Line function', async () => {
    const fen0 = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    (trainingApi.getRepertoireTree as any).mockResolvedValue({
      eco: 'A40',
      color: 'white',
      root_fen: fen0,
      depth: 4,
      nodes: [
        {
          id: 'A40-w-0001',
          fen_before: fen0,
          ply: 0,
          is_user_node: true,
          user_move: { uci: 'd2d4', san: 'd4' },
          eval_cp: 26,
          children: [],
          opponent_replies: [],
        },
      ],
    });

    render(<RepertoirePanel />);
    const trainBtn = await screen.findByRole('button', { name: /Train Repertoire/i });
    fireEvent.click(trainBtn);

    await screen.findByTestId('training-board');

    // Play move -> leaf node reached
    const moveBtn = screen.getByTestId('move-d2d4');
    fireEvent.click(moveBtn);

    expect(await screen.findByText(/Branch complete!/i)).toBeInTheDocument();

    const resetBtn = screen.getByRole('button', { name: /Reset Line/i });
    expect(resetBtn).toBeEnabled();
    fireEvent.click(resetBtn);

    expect(screen.getByText(/Your turn: find the correct repertoire move/i)).toBeInTheDocument();
  });

  // 11. Child matching by FEN (en-passant / double pawn push FEN match)
  it('11. Matches child node by exact FEN including double pawn push en-passant square', async () => {
    const fen0 = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    const fenAfterE5 = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2';

    (trainingApi.getRepertoireTree as any).mockResolvedValue({
      eco: 'C20',
      color: 'white',
      root_fen: fen0,
      depth: 4,
      nodes: [
        {
          id: 'C20-w-0001',
          fen_before: fen0,
          ply: 0,
          is_user_node: true,
          user_move: { uci: 'e2e4', san: 'e4' },
          children: ['C20-w-0002'],
          opponent_replies: [{ uci: 'e7e5', san: 'e5', count: 5, pct: 1.0 }],
        },
        {
          id: 'C20-w-0002',
          fen_before: fenAfterE5,
          ply: 2,
          is_user_node: true,
          user_move: { uci: 'g1f3', san: 'Nf3' },
          children: [],
          opponent_replies: [],
        },
      ],
    });

    render(<RepertoirePanel />);
    const trainBtn = await screen.findByRole('button', { name: /Train Repertoire/i });
    fireEvent.click(trainBtn);

    await screen.findByTestId('training-board');

    const moveBtn = screen.getByTestId('move-e2e4');
    fireEvent.click(moveBtn);

    await waitFor(
      () => {
        expect(screen.getByText(/Ply 2 \/ Depth 4/i)).toBeInTheDocument();
      },
      { timeout: 4000 }
    );
  });
});
