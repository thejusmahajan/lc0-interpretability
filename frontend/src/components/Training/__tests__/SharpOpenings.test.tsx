import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SharpOpenings from '../SharpOpenings';
import * as trainingApi from '../../../api/training';

vi.mock('../../../api/training', () => ({
  getOpeningSharpness: vi.fn(),
  getOpeningRecommendations: vi.fn(),
  startSacSession: vi.fn(() => Promise.resolve([])),
  getSacStats: vi.fn(() => Promise.resolve({ total: 0, correct: 0, acceptable: 0, accuracy: 0, recent_accuracy: 0 })),
  submitSacGuess: vi.fn(),
  startSacPlayout: vi.fn(),
  submitPlayoutMove: vi.fn(),
}));

vi.mock('../TrainingBoard', () => ({
  default: () => <div data-testid="training-board" />,
}));

describe('SharpOpenings Component Tests', () => {
  const mockSharpnessData = {
    openings: [
      {
        eco: 'D02',
        name: 'London System',
        sacs: 13,
        mean_complexity: 0.724,
        n_positions: 25,
        top_positions: ['s-001-p010', 's-001-p014'],
        sharpness_score: 9.412,
      },
      {
        eco: 'C44',
        name: "King's Pawn Game",
        sacs: 5,
        mean_complexity: 0.564,
        n_positions: 12,
        top_positions: ['s-002-p008'],
        sharpness_score: 2.82,
      },
    ],
  };

  const mockRecommendationsData = {
    recommendations: [
      {
        eco: 'C51',
        name: 'Evans Gambit',
        color: 'white',
        sac_idea: 'Offer b4 pawn to gain rapid development.',
        themes: ['sacrifice', 'pin'],
        why: 'Forces sharp tactical calculations.',
      },
      {
        eco: 'D08',
        name: 'Albin Countergambit',
        color: 'black',
        sac_idea: 'Counter-strike with 2...e5!',
        themes: ['sacrifice', 'pawnWedge'],
        why: 'Refuses dry Queen Gambit positions.',
      },
    ],
  };

  beforeEach(() => {
    vi.resetAllMocks();
    (trainingApi.getOpeningSharpness as any).mockResolvedValue(mockSharpnessData);
    (trainingApi.getOpeningRecommendations as any).mockResolvedValue(mockRecommendationsData);
    (trainingApi.startSacSession as any).mockResolvedValue([]);
    (trainingApi.getSacStats as any).mockResolvedValue({ total: 0, correct: 0, acceptable: 0, accuracy: 0, recent_accuracy: 0 });
  });

  it('1. Renders ranked openings with sac counts and headline banner', async () => {
    render(<SharpOpenings />);

    await waitFor(() => {
      expect(screen.getByText(/Your London System \(D02\) hides 13 sharp positions/i)).toBeInTheDocument();
    });

    expect(screen.getByText('D02')).toBeInTheDocument();
    expect(screen.getByText('London System')).toBeInTheDocument();
    expect(screen.getByText('13 ⚔️')).toBeInTheDocument();

    expect(screen.getByText('C44')).toBeInTheDocument();
    expect(screen.getByText("King's Pawn Game")).toBeInTheDocument();
    expect(screen.getByText('5 ⚔️')).toBeInTheDocument();
  });

  it('2. Clicking "Drill this opening" triggers SacDrill with correct eco filter', async () => {
    (trainingApi.startSacSession as any).mockResolvedValue([
      { id: 's-001-p010', fen: 'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3' },
    ]);

    render(<SharpOpenings />);

    await waitFor(() => {
      expect(screen.getByText('London System')).toBeInTheDocument();
    });

    const drillBtns = screen.getAllByRole('button', { name: /Drill this opening/i });
    fireEvent.click(drillBtns[0]); // Click D02 drill button

    await waitFor(() => {
      expect(trainingApi.startSacSession).toHaveBeenCalledWith(10, 'D02');
    });

    expect(screen.getByText(/⚔️ D02 Sharp Positions Training/i)).toBeInTheDocument();
  });

  it('3. Recommendations section renders cards and supports color filtering', async () => {
    render(<SharpOpenings />);

    await waitFor(() => {
      expect(screen.getByText('Evans Gambit')).toBeInTheDocument();
    });

    expect(screen.getByText('Albin Countergambit')).toBeInTheDocument();
    expect(screen.getByText('#pin')).toBeInTheDocument();

    // Filter by Black
    (trainingApi.getOpeningRecommendations as any).mockResolvedValue({
      recommendations: [mockRecommendationsData.recommendations[1]],
    });

    const blackBtn = screen.getByRole('button', { name: /^black$/i });
    fireEvent.click(blackBtn);

    await waitFor(() => {
      expect(trainingApi.getOpeningRecommendations).toHaveBeenCalledWith('black');
    });
  });

  it('4. Renders friendly empty state when no sharp openings found', async () => {
    (trainingApi.getOpeningSharpness as any).mockResolvedValue({ openings: [] });
    (trainingApi.getOpeningRecommendations as any).mockResolvedValue({ recommendations: [] });

    render(<SharpOpenings />);

    await waitFor(() => {
      expect(screen.getByText(/No analyzed sharp positions found yet/i)).toBeInTheDocument();
    });
  });
});
