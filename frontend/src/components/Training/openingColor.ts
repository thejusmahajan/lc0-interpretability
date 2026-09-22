// Per-color opening ownership label derived from the pipeline's
// by_opening aggregate (moves_white / moves_black). Legacy profiles
// predating the color aggregate lack those keys and fall back to '—'.
export function openingColorLabel(stats: { moves_white?: number; moves_black?: number }): string {
  const w = stats.moves_white ?? 0;
  const b = stats.moves_black ?? 0;
  if (w > 0 && b > 0) return 'Both';
  if (w > 0) return 'White';
  if (b > 0) return 'Black';
  return '—';
}
