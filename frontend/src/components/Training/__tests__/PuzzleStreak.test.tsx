import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PuzzleStreak from '../PuzzleStreak';
import * as trainingApi from '../../../api/training';

vi.mock('../../../api/training', () => ({
  listPuzzleSets: vi.fn(),
  createPuzzleSet: vi.fn(),
  deletePuzzleSet: vi.fn(),
  startPuzzleSession: vi.fn(),
  getPuzzleSession: vi.fn(),
  submitPuzzleMove: vi.fn(),
  nextPuzzle: vi.fn(),
}));

// Mock TrainingBoard to simulate user moves and inspect interactive state
vi.mock('../TrainingBoard', () => ({
  default: ({ onMove, interactive }: any) => (
    <div data-testid="mock-training-board" data-interactive={interactive ? 'true' : 'false'}>
      <button
        data-testid="move-btn-correct"
        disabled={!interactive}
        onClick={() => onMove && onMove('f6f4', 'Qxf4')}
      >
        Play Qxf4
      </button>
      <button
        data-testid="move-btn-wrong"
        disabled={!interactive}
        onClick={() => onMove && onMove('a7a6', 'a6')}
      >
        Play a6
      </button>
    </div>
  ),
}));

describe('PuzzleStreak UI Tests', () => {
  const mockSets: trainingApi.PuzzleSetMetadata[] = [
    {
      id: 'band-1500-2000',
      name: 'Band 1500-2000',
      min_rating: 1500,
      max_rating: 2000,
      themes: ['fork', 'pin'],
      size: 100,
      created: '2026-08-15T00:00:00',
    },
  ];

  const mockFirstPuzzle: trainingApi.PuzzlePayload = {
    id: 'sess-12345',
    session_id: 'sess-12345',
    set_id: 'band-1500-2000',
    index: 0,
    total: 50,
    streak: 0,
    best_streak: 0,
    alive: true,
    fen: 'rnb2rk1/ppp3pp/3bpq2/4N3/2BPpB2/4Q3/PPP2PPP/R3K2R w KQ - 2 12',
    orientation: 'black',
    rating: 1510,
    themes: ['advantage', 'middlegame', 'short'],
    puzzle_url: 'https://lichess.org/training/013Jo',
  };

  beforeEach(() => {
    vi.resetAllMocks();
    (trainingApi.listPuzzleSets as any).mockResolvedValue(mockSets);
    (trainingApi.startPuzzleSession as any).mockResolvedValue(mockFirstPuzzle);
  });

  it('1. Renders the set list and starts a session', async () => {
    render(<PuzzleStreak />);

    expect(screen.getByText(/Loading sets.../i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Band 1500-2000')).toBeInTheDocument();
    });

    const startBtn = screen.getByRole('button', { name: /Start streak Band 1500-2000/i });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(trainingApi.startPuzzleSession).toHaveBeenCalledWith('band-1500-2000');
      expect(screen.getByText(/🔥 Streak: 0/i)).toBeInTheDocument();
      expect(screen.getByText(/Puzzle 1 \/ 50/i)).toBeInTheDocument();
      expect(screen.getByTestId('mock-training-board')).toBeInTheDocument();
    });
  });

  it('2. A correct move advances; streak counter increments', async () => {
    const mockSolvedResult: trainingApi.PuzzlePayload = {
      ...mockFirstPuzzle,
      streak: 1,
      best_streak: 1,
      correct: true,
      solved: true,
    };

    const mockSecondPuzzle: trainingApi.PuzzlePayload = {
      ...mockFirstPuzzle,
      index: 1,
      streak: 1,
      best_streak: 1,
      rating: 1535,
      fen: 'r1bqkb1r/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3',
      themes: ['opening'],
      puzzle_url: 'https://lichess.org/training/p2',
    };

    (trainingApi.submitPuzzleMove as any).mockResolvedValue(mockSolvedResult);
    (trainingApi.nextPuzzle as any).mockResolvedValue(mockSecondPuzzle);

    render(<PuzzleStreak />);

    await waitFor(() => {
      expect(screen.getByText('Band 1500-2000')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Start streak Band 1500-2000/i }));

    await waitFor(() => {
      expect(screen.getByTestId('mock-training-board')).toBeInTheDocument();
    });

    const moveBtn = screen.getByTestId('move-btn-correct');
    fireEvent.click(moveBtn);

    await waitFor(() => {
      expect(trainingApi.submitPuzzleMove).toHaveBeenCalledWith('sess-12345', 'f6f4');
      expect(screen.getByText(/Correct! 🔥 Streak: 1/i)).toBeInTheDocument();
    });
  });

  it('3. A wrong move ends the run, shows the solution, and disables the board', async () => {
    const mockFailedResult: trainingApi.PuzzlePayload = {
      ...mockFirstPuzzle,
      alive: false,
      correct: false,
      solved: false,
      solution: ['f6f4', 'e4f4', 'f8f4'],
      solution_san: 'Qxf4 Qxf4 Rxf4',
      streak_ended_at: 0,
    };

    (trainingApi.submitPuzzleMove as any).mockResolvedValue(mockFailedResult);

    render(<PuzzleStreak />);

    await waitFor(() => {
      expect(screen.getByText('Band 1500-2000')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Start streak Band 1500-2000/i }));

    await waitFor(() => {
      expect(screen.getByTestId('mock-training-board')).toBeInTheDocument();
    });

    const wrongMoveBtn = screen.getByTestId('move-btn-wrong');
    fireEvent.click(wrongMoveBtn);

    await waitFor(() => {
      expect(trainingApi.submitPuzzleMove).toHaveBeenCalledWith('sess-12345', 'a7a6');
      expect(screen.getByText(/Streak over — 0 solved/i)).toBeInTheDocument();
      expect(screen.getByText(/Qxf4 Qxf4 Rxf4/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /New Streak/i })).toBeInTheDocument();
      // Board is disabled
      const board = screen.getByTestId('mock-training-board');
      expect(board.getAttribute('data-interactive')).toBe('false');
    });
  });

  it('4. Themes are not in the DOM before the puzzle resolves', async () => {
    render(<PuzzleStreak />);

    await waitFor(() => {
      expect(screen.getByText('Band 1500-2000')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Start streak Band 1500-2000/i }));

    await waitFor(() => {
      expect(screen.getByTestId('mock-training-board')).toBeInTheDocument();
    });

    // While puzzle is unsolved and active, spoiler themes must NOT be in the DOM
    expect(screen.queryByTestId('puzzle-themes')).not.toBeInTheDocument();
    expect(screen.queryByText('advantage')).not.toBeInTheDocument();
    expect(screen.queryByText('middlegame')).not.toBeInTheDocument();
  });
});
