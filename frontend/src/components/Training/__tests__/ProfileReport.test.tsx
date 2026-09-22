import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ProfileReport from '../ProfileReport';

vi.mock('../WeaknessRanking', () => ({
  default: () => <div data-testid="weakness-ranking-mock" />,
}));

describe('ProfileReport Tactical Steering (TS2) Tests', () => {
  const mockProfileWithSteer = {
    player_name: 'SteerTester',
    games_analyzed: 15,
    moves_analyzed: 450,
    steer_budget_exhausted: true,
    steer_summary: {
      C61: { moves: 12, tal_moves: 4, mean_complexity: 0.385 },
      B00: { moves: 5, tal_moves: 0, mean_complexity: 0.120 },
    },
    steer_findings: [
      {
        id: 's-001-p10',
        ply: 10,
        fen_before: 'r1bqk1nr/pppp1ppp/2n5/2b5/2BpP3/2P2N2/PP3PPP/RNBQK2R b KQkq - 0 5',
        user_color: 'black',
        opening: { eco: 'C61' },
        played: { uci: 'g8f6', san: 'Nf6' },
        steer: { uci: 'd7d6', san: 'd6', complexity: 0.395 },
        eval_loss_cp: 42,
        had_tal_move: true,
      },
      {
        id: 's-002-p14',
        ply: 14,
        fen_before: 'rnbqk2r/pppp1ppp/5n2/4p3/1b2P3/2N2N2/PPPP1PPP/R1BQKB1R w KQkq - 0 4',
        user_color: 'white',
        opening: { eco: 'C61' },
        played: { uci: 'd2d3', san: 'd3' },
        steer: { uci: 'c3d5', san: 'Nd5', complexity: 0.220 },
        eval_loss_cp: 15,
        had_tal_move: false,
      },
    ],
    findings: [],
    aggregates: {
      intuitive_blindness_rate: 0.12,
      attention_blindness_rate: 0.04,
      by_motif: {},
      by_opening: {},
      by_concept: {},
    },
  };

  it('renders Tactical Steering stat box in header and main TS2 panel', () => {
    render(
      <ProfileReport
        profile={mockProfileWithSteer}
        onFindingClick={vi.fn()}
        onGenerateDrills={vi.fn()}
      />
    );

    expect(screen.getByText('Tactical Steering')).toBeInTheDocument();
    expect(screen.getByTestId('steer-section')).toBeInTheDocument();
    expect(screen.getByText('Budget Exhausted')).toBeInTheDocument();
    expect(screen.getByTestId('steer-summary-table')).toBeInTheDocument();
  });

  it('renders steering summary by opening table with accurate ECO metrics', () => {
    render(
      <ProfileReport
        profile={mockProfileWithSteer}
        onFindingClick={vi.fn()}
        onGenerateDrills={vi.fn()}
      />
    );

    const summaryTable = screen.getByTestId('steer-summary-table');
    expect(summaryTable).toHaveTextContent('C61');
    expect(summaryTable).toHaveTextContent('0.385');
    expect(summaryTable).toHaveTextContent('B00');
  });

  it('renders steer candidate cards and triggers onFindingClick when clicked', () => {
    const handleFindingClick = vi.fn();
    render(
      <ProfileReport
        profile={mockProfileWithSteer}
        onFindingClick={handleFindingClick}
        onGenerateDrills={vi.fn()}
      />
    );

    const steerCard = screen.getByTestId('steer-card-s-001-p10');
    expect(steerCard).toBeInTheDocument();
    expect(steerCard).toHaveTextContent('Sharp Move');
    expect(steerCard).toHaveTextContent('Nf6');
    expect(steerCard).toHaveTextContent('d6');

    fireEvent.click(steerCard);
    expect(handleFindingClick).toHaveBeenCalledTimes(1);
    expect(handleFindingClick).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 's-001-p10',
        severity: 'sharp',
        fen_before: 'r1bqk1nr/pppp1ppp/2n5/2b5/2BpP3/2P2N2/PP3PPP/RNBQK2R b KQkq - 0 5',
      })
    );
  });

  it('renders gracefully when steer_findings and steer_summary are omitted or empty', () => {
    const emptyProfile = {
      player_name: 'EmptyTester',
      games_analyzed: 5,
      findings: [],
      aggregates: {},
    };

    render(
      <ProfileReport
        profile={emptyProfile}
        onFindingClick={vi.fn()}
        onGenerateDrills={vi.fn()}
      />
    );

    expect(screen.queryByTestId('steer-section')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Weakness Profile/i })).toBeInTheDocument();
  });
});
