import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import IntuitionDrill, { INTUITION_SECONDS } from '../IntuitionDrill';
import * as trainingApi from '../../../api/training';

vi.mock('../../../api/training', () => ({
  startIntuitionSession: vi.fn(),
  submitIntuitionGuess: vi.fn(),
  getIntuitionStats: vi.fn(),
}));

// Mock TrainingBoard to simulate user moves easily
vi.mock('../TrainingBoard', () => ({
  default: ({ onMove, interactive }: any) => (
    <div data-testid="mock-training-board" data-interactive={interactive ? 'true' : 'false'}>
      <button data-testid="move-btn-e4" onClick={() => onMove && onMove('e2e4', 'e4')}>
        Play e4
      </button>
      <button data-testid="move-btn-d4" onClick={() => onMove && onMove('d2d4', 'd4')}>
        Play d4
      </button>
    </div>
  ),
}));

describe('IntuitionDrill UI Tests', () => {
  const mockPositions: trainingApi.IntuitionPosition[] = [
    {
      epd: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -',
      fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    },
    {
      epd: 'rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -',
      fen: 'rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1',
    },
  ];

  const mockStats: trainingApi.IntuitionStats = {
    total: 10,
    correct: 6,
    accuracy: 0.6,
    recent_accuracy: 0.7,
  };

  beforeEach(() => {
    vi.resetAllMocks();
    vi.useFakeTimers();
    (trainingApi.startIntuitionSession as any).mockImplementation(() => Promise.resolve(mockPositions));
    (trainingApi.getIntuitionStats as any).mockImplementation(() => Promise.resolve(mockStats));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('1. Renders board and timer for the first session position', async () => {
    render(<IntuitionDrill />);

    expect(screen.getByText(/Loading intuition session/i)).toBeInTheDocument();

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId('mock-training-board')).toBeInTheDocument();
    expect(screen.getByText(`⏱️ ${INTUITION_SECONDS}s`)).toBeInTheDocument();
    expect(screen.getByText(/Position 1 of 2/i)).toBeInTheDocument();
  });

  it('2. Making a move calls submitIntuitionGuess and displays reveal panel (top_policy, hit/miss, rank)', async () => {
    const mockGuessResult: trainingApi.IntuitionGuessResult = {
      correct: true,
      rank: 1,
      your_move: { uci: 'e2e4', san: 'e4', p: 0.55 },
      top_move: { uci: 'e2e4', san: 'e4', p: 0.55 },
      top_policy: [
        { uci: 'e2e4', san: 'e4', p: 0.55 },
        { uci: 'd2d4', san: 'd4', p: 0.25 },
        { uci: 'c2c4', san: 'c4', p: 0.10 },
      ],
    };

    (trainingApi.submitIntuitionGuess as any).mockImplementation(() => Promise.resolve(mockGuessResult));

    render(<IntuitionDrill />);

    await act(async () => {
      await Promise.resolve();
    });

    const moveBtn = screen.getByTestId('move-btn-e4');
    await act(async () => {
      fireEvent.click(moveBtn);
    });

    expect(trainingApi.submitIntuitionGuess).toHaveBeenCalledWith(
      'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -',
      'e2e4'
    );

    // Reveal panel check
    expect(screen.getByText(/HIT! You guessed LC0's #1 policy move!/i)).toBeInTheDocument();
    expect(screen.getByText(/LC0 Ranked Policy Top 5/i)).toBeInTheDocument();
    expect(screen.getByText('55.0%')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Next Position/i })).toBeInTheDocument();
  });

  it('3. Timeout (timer hitting 0) submits empty guess and displays miss reveal', async () => {
    const mockTimeoutResult: trainingApi.IntuitionGuessResult = {
      correct: false,
      rank: null,
      your_move: null,
      top_move: { uci: 'e2e4', san: 'e4', p: 0.55 },
      top_policy: [
        { uci: 'e2e4', san: 'e4', p: 0.55 },
        { uci: 'd2d4', san: 'd4', p: 0.25 },
      ],
    };

    (trainingApi.submitIntuitionGuess as any).mockImplementation(() => Promise.resolve(mockTimeoutResult));

    render(<IntuitionDrill />);

    await act(async () => {
      await Promise.resolve();
    });

    // Advance timer by 10 seconds to trigger timeout
    await act(async () => {
      vi.advanceTimersByTime(INTUITION_SECONDS * 1000 + 100);
    });

    expect(trainingApi.submitIntuitionGuess).toHaveBeenCalledWith(
      'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -',
      ''
    );

    expect(screen.getByText(/MISS! Your move was not in LC0's top moves/i)).toBeInTheDocument();
  });

  it('4. Completing session shows end-of-session accuracy summary and lifetime stats', async () => {
    const mockHitResult: trainingApi.IntuitionGuessResult = {
      correct: true,
      rank: 1,
      your_move: { uci: 'e2e4', san: 'e4', p: 0.55 },
      top_move: { uci: 'e2e4', san: 'e4', p: 0.55 },
      top_policy: [{ uci: 'e2e4', san: 'e4', p: 0.55 }],
    };

    (trainingApi.submitIntuitionGuess as any).mockImplementation(() => Promise.resolve(mockHitResult));

    render(<IntuitionDrill />);

    await act(async () => {
      await Promise.resolve();
    });

    // Position 1: Guess e4
    await act(async () => {
      fireEvent.click(screen.getByTestId('move-btn-e4'));
    });

    // Next button -> Position 2
    const nextBtn = screen.getByRole('button', { name: /Next Position/i });
    await act(async () => {
      fireEvent.click(nextBtn);
    });

    // Position 2: Guess e4
    await act(async () => {
      fireEvent.click(screen.getByTestId('move-btn-e4'));
    });

    // Finish Session button
    const finishBtn = screen.getByRole('button', { name: /Finish Session/i });
    await act(async () => {
      fireEvent.click(finishBtn);
    });

    expect(screen.getByText(/Session Complete!/i)).toBeInTheDocument();
    expect(screen.getByText(/2 \/ 2/i)).toBeInTheDocument();
    expect(screen.getByText(/100.0%/i)).toBeInTheDocument();
    expect(screen.getByText(/Lifetime Intuition Stats/i)).toBeInTheDocument();
    expect(screen.getByText(/60.0%/i)).toBeInTheDocument();
  });
});
