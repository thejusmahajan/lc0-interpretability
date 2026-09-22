import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import UsualSuspects from '../UsualSuspects';
import * as trainingApi from '../../../api/training';

vi.mock('../../../api/training', () => ({
  getUsualSuspects: vi.fn(),
  getApprovedSuspects: vi.fn(),
  approveSuspects: vi.fn(),
  buildSuspectsDeck: vi.fn(),
  getDueDrills: vi.fn(),
}));

describe('UsualSuspects UI Tests', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    (trainingApi.getUsualSuspects as any).mockImplementation(() => Promise.resolve({ suspects: [], by_phase: [], by_concept: [] }));
    (trainingApi.getApprovedSuspects as any).mockImplementation(() => Promise.resolve({ themes: ['fork'] }));
    (trainingApi.getDueDrills as any).mockImplementation(() => Promise.resolve({ count: 5 }));
    (trainingApi.approveSuspects as any).mockImplementation(() => Promise.resolve({ themes: ['fork'] }));
    (trainingApi.buildSuspectsDeck as any).mockImplementation(() => Promise.resolve({ id: 'suspects-12345' }));
  });

  it('1. Renders ranked theme cards and dashboard from mocked suspects payload', async () => {
    const mockSuspectsData: trainingApi.UsualSuspectsResponse = {
      suspects: [
        {
          theme: 'fork',
          games: 4,
          occurrences: 6,
          mean_severity: 512.0,
          rank_score: 2048.0,
          severity_label: 'high',
          finding_ids: ['g001-p01', 'g002-p02'],
        },
        {
          theme: 'pin',
          games: 2,
          occurrences: 3,
          mean_severity: 250.0,
          rank_score: 500.0,
          severity_label: 'medium',
          finding_ids: ['g003-p01'],
        },
      ],
      by_phase: [],
      by_concept: [],
    };

    (trainingApi.getUsualSuspects as any).mockResolvedValue(mockSuspectsData);

    render(<UsualSuspects onDeckBuilt={vi.fn()} />);

    expect(screen.getByText(/Loading usual suspects/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.queryByText(/Loading usual suspects/i)).not.toBeInTheDocument();
    });

    expect(screen.getAllByText('fork').length).toBeGreaterThan(0);
    expect(screen.getAllByText('pin').length).toBeGreaterThan(0);
    expect(screen.getByText('high')).toBeInTheDocument();
    expect(screen.getByText('medium')).toBeInTheDocument();

    // Pre-checked from getApprovedSuspects (fork was approved)
    const forkCheckbox = screen.getByLabelText('fork') as HTMLInputElement;
    expect(forkCheckbox.checked).toBe(true);

    const pinCheckbox = screen.getByLabelText('pin') as HTMLInputElement;
    expect(pinCheckbox.checked).toBe(false);

    // Dashboard check
    expect(screen.getByText('Top Weakness')).toBeInTheDocument();
    expect(screen.getByText('Openings pending ECO fix')).toBeInTheDocument();
    expect(screen.getByText('5 due')).toBeInTheDocument();
  });

  it('2. Toggling checkboxes and clicking Build my training deck calls approveSuspects, buildSuspectsDeck, and onDeckBuilt', async () => {
    const mockSuspectsData: trainingApi.UsualSuspectsResponse = {
      suspects: [
        {
          theme: 'fork',
          games: 4,
          occurrences: 6,
          mean_severity: 512.0,
          rank_score: 2048.0,
          severity_label: 'high',
          finding_ids: ['g001-p01'],
        },
        {
          theme: 'pin',
          games: 2,
          occurrences: 3,
          mean_severity: 250.0,
          rank_score: 500.0,
          severity_label: 'medium',
          finding_ids: ['g003-p01'],
        },
      ],
      by_phase: [],
      by_concept: [],
    };

    const onDeckBuiltMock = vi.fn();
    (trainingApi.getUsualSuspects as any).mockImplementation(() => Promise.resolve(mockSuspectsData));
    (trainingApi.approveSuspects as any).mockImplementation(() => Promise.resolve({ themes: ['fork', 'pin'] }));
    (trainingApi.buildSuspectsDeck as any).mockImplementation(() => Promise.resolve({
      id: 'suspects-abc12345',
      drills: [{ id: 'd-1' }],
    }));

    render(<UsualSuspects onDeckBuilt={onDeckBuiltMock} />);

    await waitFor(() => {
      expect(screen.getAllByText('fork').length).toBeGreaterThan(0);
    });

    // Check 'pin'
    const pinCheckbox = screen.getByLabelText('pin');
    fireEvent.click(pinCheckbox);

    // Click 'Build my training deck'
    const buildBtn = screen.getByRole('button', { name: /Build my training deck/i });
    fireEvent.click(buildBtn);

    await waitFor(() => {
      expect(trainingApi.approveSuspects).toHaveBeenCalledWith(['fork', 'pin']);
      expect(trainingApi.buildSuspectsDeck).toHaveBeenCalledWith(20);
      expect(onDeckBuiltMock).toHaveBeenCalledWith('suspects-abc12345');
    });
  });

  it('3. Renders empty state message when suspects is empty', async () => {
    (trainingApi.getUsualSuspects as any).mockResolvedValue({
      suspects: [],
      by_phase: [],
      by_concept: [],
    });

    render(<UsualSuspects onDeckBuilt={vi.fn()} />);

    await waitFor(() => {
      expect(
        screen.getByText(/No recurring weaknesses detected yet \(min 2 games floor\)\./i)
      ).toBeInTheDocument();
    });
  });

  it('4. Renders no-profile message when getUsualSuspects returns null', async () => {
    (trainingApi.getUsualSuspects as any).mockResolvedValue(null);

    render(<UsualSuspects onDeckBuilt={vi.fn()} />);

    await waitFor(() => {
      expect(
        screen.getByText(/Run a diagnosis first to discover your usual suspects\./i)
      ).toBeInTheDocument();
    });
  });
});
