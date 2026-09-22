import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import TrainingTab from '../TrainingTab';
import { openingColorLabel } from '../openingColor';
import * as trainingApi from '../../../api/training';

vi.mock('../../../api/training', () => ({
  getProfile: vi.fn(),
  getDueDrills: vi.fn(),
  getTrends: vi.fn(),
  getDrillsList: vi.fn(),
  generateDrills: vi.fn(),
  getDrillSet: vi.fn(),
  attemptDrill: vi.fn(),
  listRepertoires: vi.fn(),
  buildRepertoire: vi.fn(),
  getRepertoireTree: vi.fn(),
  getTopOpenings: vi.fn(() => Promise.resolve([])),
  getWeaknessRanking: vi.fn(() => Promise.resolve({ ranking: [] })),
  getUsualSuspects: vi.fn(() => Promise.resolve(null)),
  getApprovedSuspects: vi.fn(() => Promise.resolve({ themes: [] })),
  approveSuspects: vi.fn(() => Promise.resolve({ themes: [] })),
  buildSuspectsDeck: vi.fn(() => Promise.resolve({ id: 'suspects-123' })),
  startIntuitionSession: vi.fn(() => Promise.resolve([])),
  submitIntuitionGuess: vi.fn(() => Promise.resolve({ correct: false, rank: null, your_move: null, top_move: { uci: 'e2e4', san: 'e4', p: 0.5 }, top_policy: [] })),
  getIntuitionStats: vi.fn(() => Promise.resolve({ total: 0, correct: 0, accuracy: 0, recent_accuracy: 0 })),
  startSacSession: vi.fn(() => Promise.resolve([])),
  submitSacGuess: vi.fn(() => Promise.resolve({ correct: false, acceptable: false, sac_move: { uci: 'd2d4', san: 'd4', eval_cp: 15, complexity: 4.5 }, safe_move: { san: 'Bb5', eval_cp: 30 }, eval_loss_cp: 15, playable_candidates: [] })),
  getSacStats: vi.fn(() => Promise.resolve({ total: 0, correct: 0, acceptable: 0, accuracy: 0, recent_accuracy: 0 })),
  getOpeningSharpness: vi.fn(() => Promise.resolve({ openings: [] })),
  getOpeningRecommendations: vi.fn(() => Promise.resolve({ recommendations: [] })),
}));

vi.mock('../TrainingBoard', () => ({
  default: () => <div data-testid="training-board" />,
}));

describe('Training UI QA Sweep Tests', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    (trainingApi.getProfile as any).mockResolvedValue(null);
    (trainingApi.getDueDrills as any).mockResolvedValue({ count: 0, due: [] });
    (trainingApi.getTrends as any).mockResolvedValue(null);
    (trainingApi.getDrillsList as any).mockResolvedValue([]);
    (trainingApi.listRepertoires as any).mockResolvedValue([]);
  });

  it('Mounts TrainingTab with navigation buttons and initial Diagnose PGN view', async () => {
    render(<TrainingTab />);

    expect(screen.getByRole('button', { name: /Diagnose PGN/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Weakness Profile/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Review \(0 due\)/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Progress/i })).toBeDisabled();

    expect(screen.getByText(/New Diagnosis/i)).toBeInTheDocument();
  });

  it('Enables Weakness Profile and mounts ProfileReport when profile is present', async () => {
    const mockProfile = {
      player_name: 'TestPlayer',
      games_analyzed: 10,
      moves_analyzed: 300,
      findings: [
        {
          id: 'f-001',
          move_number: 12,
          severity: 'blunder',
          fen_before: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
          user_color: 'white',
          played: { uci: 'e2e4', san: 'e4', p: 0.1 },
          best: { uci: 'd2d4', san: 'd4', p: 0.8 },
          opening: { eco: 'C99', name: 'Ruy Lopez' },
        },
      ],
      aggregates: {
        intuitive_blindness_rate: 0.15,
        attention_blindness_rate: 0.05,
        by_motif: { quietMove: { blind: 2, missed: 1, confirmed: 1 } },
        by_opening: {
          C99: { moves: 20, moves_white: 20, moves_black: 0, blind: 2, blind_rate: 0.1 },
        },
      },
    };

    (trainingApi.getProfile as any).mockResolvedValue(mockProfile);

    render(<TrainingTab />);

    const profileBtn = screen.getByRole('button', { name: /Weakness Profile/i });

    await waitFor(() => {
      expect(profileBtn).not.toBeDisabled();
    });

    fireEvent.click(profileBtn);

    expect(await screen.findByRole('heading', { name: /Weakness Profile/i })).toBeInTheDocument();
    expect(screen.getByText(/C99/i)).toBeInTheDocument();
  });

  it('openingColorLabel helper correctly derives color ownership strings', () => {
    expect(openingColorLabel({ moves_white: 10, moves_black: 0 })).toBe('White');
    expect(openingColorLabel({ moves_white: 0, moves_black: 15 })).toBe('Black');
    expect(openingColorLabel({ moves_white: 10, moves_black: 10 })).toBe('Both');
    expect(openingColorLabel({ moves_white: 0, moves_black: 0 })).toBe('—');
  });

  it('Mounts Training Drills saved sets view and handles empty saved sets state', async () => {
    (trainingApi.getDrillsList as any).mockResolvedValue([]);

    render(<TrainingTab />);

    const drillsBtn = screen.getByRole('button', { name: /Training Drills/i });
    fireEvent.click(drillsBtn);

    expect(await screen.findByRole('heading', { name: /Saved Drill Sets/i })).toBeInTheDocument();
    expect(screen.getByText(/No saved drill sets. Generate one to start training!/i)).toBeInTheDocument();
  });

  it('Enables Review button when due items exist', async () => {
    (trainingApi.getDueDrills as any).mockResolvedValue({
      count: 3,
      due: [{ drill_id: 'd-1', set_id: 's-1', drill: { id: 'd-1', fen: '8/8/8/8/8/8/8/8 w - - 0 1' } }],
    });

    render(<TrainingTab />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Review \(3 due\)/i })).not.toBeDisabled();
    });
  });
});
