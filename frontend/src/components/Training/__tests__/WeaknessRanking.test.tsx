import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ProfileReport from '../ProfileReport';
import * as trainingApi from '../../../api/training';

vi.mock('../../../api/training', () => ({
  getWeaknessRanking: vi.fn(),
}));

describe('WeaknessRanking UI Tests', () => {
  const dummyProfile = {
    player_name: 'TestPlayer',
    games_analyzed: 10,
    aggregates: {
      by_opening: { C61: { moves: 120, blind_rate: 0.40 } },
    },
  };

  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('1. Loading state renders while the fetch promise is pending', async () => {
    let resolvePromise: (val: any) => void = () => {};
    const pendingPromise = new Promise((resolve) => {
      resolvePromise = resolve;
    });
    (trainingApi.getWeaknessRanking as any).mockReturnValue(pendingPromise);

    render(
      <ProfileReport
        profile={dummyProfile}
        onFindingClick={vi.fn()}
        onGenerateDrills={vi.fn()}
      />
    );

    expect(screen.getByTestId('ranking-loading')).toBeInTheDocument();
    expect(screen.getByText(/Analyzing opening performance/i)).toBeInTheDocument();

    resolvePromise({ ranking: [], phase: [], clock: [] });
    await waitFor(() => {
      expect(screen.queryByTestId('ranking-loading')).not.toBeInTheDocument();
    });
  });

  it('2. Renders all three sections with their items and human labels', async () => {
    const mockData = {
      ranking: [
        { dim: 'C61', value: 0.40, count: 120, ref_value: 0.11, grade: -2.9, importance: 31.7, kind: 'weakness' as const },
      ],
      phase: [
        { dim: 'middlegame', value: 0.25, count: 300, ref_value: 0.12, grade: -2.0, importance: 20.0, kind: 'weakness' as const },
        { dim: 'endgame', value: 0.08, count: 150, ref_value: 0.15, grade: 1.0, importance: 8.0, kind: 'strength' as const },
      ],
      clock: [
        { dim: 'normal', value: 0.13, count: 400, ref_value: 0.18, grade: 0.5, importance: 6.0, kind: 'strength' as const },
        { dim: 'fast', value: 0.30, count: 100, ref_value: 0.15, grade: -2.2, importance: 15.0, kind: 'weakness' as const },
      ],
    };
    (trainingApi.getWeaknessRanking as any).mockResolvedValue(mockData);

    render(
      <ProfileReport
        profile={dummyProfile}
        onFindingClick={vi.fn()}
        onGenerateDrills={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('ranking-list')).toBeInTheDocument();
    });

    expect(screen.getByText('Openings')).toBeInTheDocument();
    expect(screen.getByText('Game Phase')).toBeInTheDocument();
    expect(screen.getByText('Time Pressure')).toBeInTheDocument();

    expect(screen.getByTestId('ranking-item-C61')).toHaveTextContent('C61');
    expect(screen.getByText('Middlegame')).toBeInTheDocument();
    expect(screen.getByText('Endgame')).toBeInTheDocument();
    expect(screen.getByText('Normal (1–3 min)')).toBeInTheDocument();
    expect(screen.getByText('Under time pressure (<1 min)')).toBeInTheDocument();
  });

  it('3. Empty phase/clock shows muted run a fresh diagnosis note while openings render', async () => {
    const mockData = {
      ranking: [
        { dim: 'C61', value: 0.40, count: 120, ref_value: 0.11, grade: -2.9, importance: 31.7, kind: 'weakness' as const },
      ],
      phase: [],
      clock: [],
    };
    (trainingApi.getWeaknessRanking as any).mockResolvedValue(mockData);

    render(
      <ProfileReport
        profile={dummyProfile}
        onFindingClick={vi.fn()}
        onGenerateDrills={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('ranking-list')).toBeInTheDocument();
    });

    expect(screen.getByTestId('ranking-item-C61')).toBeInTheDocument();

    const emptyNotes = screen.getAllByText(/Run a fresh diagnosis to rank by/i);
    expect(emptyNotes).toHaveLength(2);
    expect(screen.getByTestId('phase-empty')).toHaveTextContent(/game phase/i);
    expect(screen.getByTestId('clock-empty')).toHaveTextContent(/time pressure/i);
  });

  it('4. Formatting — value 0.40 renders as 40.0% and count 120 as games; badges render', async () => {
    const mockData = {
      ranking: [
        { dim: 'C61', value: 0.40, count: 120, ref_value: 0.112345, grade: -2.9, importance: 31.789, kind: 'weakness' as const },
      ],
      phase: [],
      clock: [],
    };
    (trainingApi.getWeaknessRanking as any).mockResolvedValue(mockData);

    render(
      <ProfileReport
        profile={dummyProfile}
        onFindingClick={vi.fn()}
        onGenerateDrills={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('ranking-item-C61')).toBeInTheDocument();
    });

    const item = screen.getByTestId('ranking-item-C61');
    expect(item).toHaveTextContent('40.0% blind');
    expect(item).toHaveTextContent('120 games');
    expect(item).toHaveClass('weakness');
    expect(item.textContent).not.toContain('0.112345');
    expect(item.textContent).not.toContain('31.789');
  });

  it('5. Empty ranking ({ ranking: [], phase: [], clock: [] }) renders friendly message', async () => {
    (trainingApi.getWeaknessRanking as any).mockResolvedValue({ ranking: [], phase: [], clock: [] });

    render(
      <ProfileReport
        profile={dummyProfile}
        onFindingClick={vi.fn()}
        onGenerateDrills={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('ranking-empty')).toBeInTheDocument();
    });

    expect(screen.getByText(/Not enough games analyzed yet to rank your openings/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Weakness Profile/i })).toBeInTheDocument();
  });

  it('6. Fetch error renders graceful inline message and profile remains intact', async () => {
    (trainingApi.getWeaknessRanking as any).mockRejectedValue(new Error('Network error fetching ranking'));

    render(
      <ProfileReport
        profile={dummyProfile}
        onFindingClick={vi.fn()}
        onGenerateDrills={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('ranking-error')).toBeInTheDocument();
    });

    expect(screen.getByText(/Network error fetching ranking/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Weakness Profile/i })).toBeInTheDocument();
  });
});

