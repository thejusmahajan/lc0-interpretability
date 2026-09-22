const BASE_URL = 'http://127.0.0.1:8000/api/training';

export async function diagnose(pgn: string, playerName: string) {
  const res = await fetch(`${BASE_URL}/diagnose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pgn, player_name: playerName }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getJobStatus(jobId: string) {
  const res = await fetch(`${BASE_URL}/jobs/${jobId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface SteerCandidate {
  uci: string;
  san?: string;
  eval_cp?: number;
  complexity?: number;
}

export interface SteerFinding {
  id: string;
  ply: number;
  move_number?: number;
  fen_before: string;
  user_color?: 'white' | 'black';
  opening?: { eco: string; name?: string };
  played?: SteerCandidate;
  best?: SteerCandidate;
  steer?: SteerCandidate;
  playable_candidates?: SteerCandidate[];
  eval_loss_cp?: number;
  had_sharp_move?: boolean;
  had_tal_move?: boolean;
}

export interface SteerSummaryItem {
  moves: number;
  sharp_moves?: number;
  tal_moves?: number;
  mean_complexity: number;
}

export interface ProfileData {
  player_name?: string;
  games_analyzed: number;
  moves_analyzed?: number;
  findings: any[];
  steer_findings?: SteerFinding[];
  steer_summary?: Record<string, SteerSummaryItem>;
  steer_budget_exhausted?: boolean;
  aggregates?: any;
  regressions?: any;
}

export async function getProfile(): Promise<ProfileData | null> {
  const res = await fetch(`${BASE_URL}/profile`);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(await res.text());
  }
  return res.json();
}

export async function generateDrills(count: number = 20) {
  const res = await fetch(`${BASE_URL}/drills/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ count }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getDrillsList() {
  const res = await fetch(`${BASE_URL}/drills`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getDrillSet(setId: string) {
  const res = await fetch(`${BASE_URL}/drills/${setId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function attemptDrill(setId: string, drillId: string, moveUci: string, ply: number = 0) {
  const res = await fetch(`${BASE_URL}/drills/attempt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ set_id: setId, drill_id: drillId, move_uci: moveUci, ply }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getDueDrills() {
  const res = await fetch(`${BASE_URL}/srs/due`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listRepertoires() {
  const res = await fetch(`${BASE_URL}/repertoires`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function buildRepertoire(color: 'white' | 'black', style: 'weakness' | 'sacrificial') {
  const res = await fetch(`${BASE_URL}/repertoire`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ color, style, build: true }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getTrends() {
  const res = await fetch(`${BASE_URL}/trends`);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(await res.text());
  }
  return res.json();
}

export async function getRepertoireTree(eco: string, color: 'white' | 'black') {
  const res = await fetch(`${BASE_URL}/repertoire/tree`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ eco, color }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// The user's most-played openings per color (by ECO), for the Train-mode
// selector — so trees are built for high-volume lines, not just the low-volume
// weakness recommendations.
export async function getTopOpenings(limit = 12): Promise<{
  white: { eco: string; name: string; count: number }[];
  black: { eco: string; name: string; count: number }[];
}> {
  const res = await fetch(`${BASE_URL}/repertoire/top-openings?limit=${limit}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getWeaknessRanking(n = 6): Promise<{
  ranking: { dim: string; value: number; count: number; ref_value: number;
             grade: number; importance: number; kind: 'weakness' | 'strength' }[];
  phase: { dim: string; value: number; count: number; ref_value: number;
           grade: number; importance: number; kind: 'weakness' | 'strength' }[];
  clock: { dim: string; value: number; count: number; ref_value: number;
           grade: number; importance: number; kind: 'weakness' | 'strength' }[];
}> {
  const res = await fetch(`${BASE_URL}/weakness-ranking?n=${n}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface UsualSuspect {
  theme: string;
  games: number;
  occurrences: number;
  mean_severity: number;
  rank_score: number;
  severity_label: 'high' | 'medium' | 'low';
  finding_ids: string[];
}

export interface UsualSuspectsResponse {
  suspects: UsualSuspect[];
  by_phase: any[];
  by_concept: any[];
}

export interface ApprovedSuspectsResponse {
  themes: string[];
  updated?: string;
}

export async function getUsualSuspects(): Promise<UsualSuspectsResponse | null> {
  const res = await fetch(`${BASE_URL}/usual-suspects`);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(await res.text());
  }
  return res.json();
}

export async function approveSuspects(themes: string[]): Promise<ApprovedSuspectsResponse> {
  const res = await fetch(`${BASE_URL}/usual-suspects/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ themes }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getApprovedSuspects(): Promise<ApprovedSuspectsResponse> {
  const res = await fetch(`${BASE_URL}/usual-suspects/approved`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function buildSuspectsDeck(count: number = 20): Promise<{ id: string; drills: any[]; [key: string]: any }> {
  const res = await fetch(`${BASE_URL}/usual-suspects/deck`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ count }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ------------------------------------------------------------------
// Intuition Speed-Drill API
// ------------------------------------------------------------------

export interface IntuitionPosition {
  epd: string;
  fen: string;
}

export interface IntuitionMove {
  uci: string;
  san: string;
  p: number;
}

export interface IntuitionGuessResult {
  correct: boolean;
  rank: number | null;
  your_move: IntuitionMove | null;
  top_move: IntuitionMove;
  top_policy: IntuitionMove[];
}

export interface IntuitionStats {
  total: number;
  correct: number;
  accuracy: number;
  recent_accuracy: number;
}

export async function startIntuitionSession(count: number = 12): Promise<IntuitionPosition[]> {
  const res = await fetch(`${BASE_URL}/intuition/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ count }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitIntuitionGuess(epd: string, uci: string): Promise<IntuitionGuessResult> {
  const res = await fetch(`${BASE_URL}/intuition/guess`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ epd, uci }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getIntuitionStats(): Promise<IntuitionStats> {
  const res = await fetch(`${BASE_URL}/intuition/stats`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ------------------------------------------------------------------
// Sacrifice / Tactical-Landmine Drill API
// ------------------------------------------------------------------

export interface SacPosition {
  id: string;
  fen: string;
}

export interface SacMove {
  uci: string;
  san: string;
  eval_cp: number;
  complexity: number;
}

export interface SafeMove {
  san: string;
  eval_cp: number;
}

export interface PlayableCandidate {
  uci: string;
  complexity: number;
  eval_cp: number;
}

export interface SacGuessResult {
  correct: boolean;
  acceptable: boolean;
  sac_move: SacMove;
  safe_move: SafeMove;
  eval_loss_cp: number;
  playable_candidates: PlayableCandidate[];
}

export interface SacStats {
  total: number;
  correct: number;
  acceptable: number;
  accuracy: number;
  recent_accuracy: number;
}

export async function startSacSession(count: number = 10, eco?: string): Promise<SacPosition[]> {
  const res = await fetch(`${BASE_URL}/sac/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ count, eco }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitSacGuess(finding_id: string, uci: string): Promise<SacGuessResult> {
  const res = await fetch(`${BASE_URL}/sac/guess`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ finding_id, uci }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSacStats(): Promise<SacStats> {
  const res = await fetch(`${BASE_URL}/sac/stats`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface OpeningSharpnessItem {
  eco: string;
  name: string;
  sacs: number;
  mean_complexity: number;
  n_positions: number;
  top_positions: string[];
  sharpness_score: number;
}

export interface OpeningSharpnessResponse {
  openings: OpeningSharpnessItem[];
}

export interface OpeningRecommendationItem {
  eco: string;
  name: string;
  color: 'white' | 'black';
  sac_idea: string;
  themes: string[];
  why: string;
}

export interface OpeningRecommendationsResponse {
  recommendations: OpeningRecommendationItem[];
}

export async function getOpeningSharpness(): Promise<OpeningSharpnessResponse> {
  const res = await fetch(`${BASE_URL}/openings/sharpness`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getOpeningRecommendations(color?: string): Promise<OpeningRecommendationsResponse> {
  const url = color ? `${BASE_URL}/openings/recommendations?color=${encodeURIComponent(color)}` : `${BASE_URL}/openings/recommendations`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface SacPlayoutResult {
  finding_id?: string;
  fen?: string;
  line?: string[];
  attacker_is_white?: boolean;
  attacker_eval_cp?: number;
  ply?: number;
  target_plies?: number;
  user_to_move?: boolean;
  quality?: 'great' | 'ok' | 'drift';
  lc0_best_attack?: {
    uci: string;
    san: string;
  };
  eval_after_cp?: number;
  lc0_reply?: {
    uci: string;
    san: string;
  } | null;
  is_complete?: boolean;
  summary?: {
    moves: number;
    great: number;
    ok: number;
    drift: number;
    final_eval_cp: number;
    verdict: string;
  };
  error?: string;
}

export type SacPlayoutStartResult = SacPlayoutResult;
export type SacPlayoutMoveResult = SacPlayoutResult;

export async function startSacPlayout(finding_id: string): Promise<SacPlayoutStartResult> {
  const res = await fetch(`${BASE_URL}/sac/playout/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ finding_id }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitPlayoutMove(
  finding_id: string,
  line: string[],
  user_uci: string,
  history: string[] = []
): Promise<SacPlayoutMoveResult> {
  const res = await fetch(`${BASE_URL}/sac/playout/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ finding_id, line, user_uci, history }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ------------------------------------------------------------------
// Puzzle Streak API
// ------------------------------------------------------------------

export interface PuzzlePayload {
  id: string;
  session_id: string;
  set_id: string;
  seed?: number;
  index: number;
  total: number;
  streak: number;
  best_streak: number;
  alive: boolean;
  fen: string;
  orientation: 'white' | 'black';
  rating: number;
  themes: string[];
  puzzle_url: string;
  correct?: boolean;
  solved?: boolean;
  opponent_uci?: string;
  ply?: number;
  solution?: string[];
  solution_san?: string;
  streak_ended_at?: number;
  completed?: boolean;
}

export interface PuzzleSetMetadata {
  id: string;
  name: string;
  min_rating: number;
  max_rating: number;
  themes: string[];
  size: number;
  created: string;
}

export interface CreatePuzzleSetParams {
  name: string;
  min_rating?: number;
  max_rating?: number;
  themes?: string[];
  size?: number;
}

export async function createPuzzleSet(params: CreatePuzzleSetParams): Promise<PuzzleSetMetadata> {
  const res = await fetch(`${BASE_URL}/puzzles/sets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listPuzzleSets(): Promise<PuzzleSetMetadata[]> {
  const res = await fetch(`${BASE_URL}/puzzles/sets`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deletePuzzleSet(setId: string): Promise<{ deleted: boolean }> {
  const res = await fetch(`${BASE_URL}/puzzles/sets/${setId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function startPuzzleSession(setId: string, seed?: number): Promise<PuzzlePayload> {
  const res = await fetch(`${BASE_URL}/puzzles/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ set_id: setId, seed }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getPuzzleSession(sessionId: string): Promise<PuzzlePayload> {
  const res = await fetch(`${BASE_URL}/puzzles/session/${sessionId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitPuzzleMove(sessionId: string, uci: string): Promise<PuzzlePayload> {
  const res = await fetch(`${BASE_URL}/puzzles/session/${sessionId}/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uci }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function nextPuzzle(sessionId: string): Promise<PuzzlePayload> {
  const res = await fetch(`${BASE_URL}/puzzles/session/${sessionId}/next`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}




