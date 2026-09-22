# UI Performance Best Practices Reference: React 19 + Vite

> **Project**: Chess Speak Out Loud (`frontend/`)  
> **Target Stack**: React 19.x, Vite 6/8, TypeScript 5/6, Chessground 9.x  
> **Author**: AI AI Coding Assistant (Instance 3 — UI Performance Audit & Reference)  
> **Status**: APPROVED REFERENCE (Durable Engineering Guide)

---

## Executive Overview & Performance Budgets

The **Chess Speak Out Loud** frontend presents a unique set of UI performance challenges:
1. **Data-Dense Dashboards**: A single weakness profile diagnosis can contain **200+ findings** (e.g., 213 tactical/positional blunders) and **250+ tactical steering items** (e.g., 263 steer findings).
2. **Interactive Heavy Graphics**: The UI renders custom interactive board overlays using SVG vectors (neural saliency heatmaps, candidate arrows, hot squares) on top of Lichess Chessground DOM boards.
3. **Engine-Driven High-Frequency State Updates**: Real-time evaluation updates and position steps update FENs, policy candidate move lists, and saliency maps.

### Target Performance Metrics (Budgets)

| Metric | Target | Measurement Tool | Why It Matters |
| :--- | :--- | :--- | :--- |
| **First Contentful Paint (FCP)** | `< 0.8s` | Lighthouse / Web Vitals | Fast load for returning users |
| **Largest Contentful Paint (LCP)** | `< 1.2s` | Lighthouse / Web Vitals | Visual readiness of main workspace |
| **Interaction to Next Paint (INP)** | `< 50ms` (Good: `< 100ms`) | Chrome Performance / Web Vitals | Instant feedback when clicking cards/moves |
| **Initial JS Bundle (Gzipped)** | `< 180 KB` | `vite build` + Visualizer | Low initial load latency |
| **Frame Rate during Board Interactions** | `60 FPS` (16.6ms budget) | React Profiler / DevTools | Smooth piece dragging & overlay updates |
| **DOM Node Count** | `< 800 nodes` per view | Chrome DevTools DOM tree | Prevents memory bloat & slow style recalculations |

---

## 1. Rendering Large Data Lists (200+ Items)

### The Problem in Dense Chess Dashboards
Unvirtualized mapping (`items.map(...)`) of hundreds of finding cards creates thousands of heavy DOM nodes. For 213 findings, rendering 213 cards—each with move badges, swing CP indicators, motif tags, and click event handlers—creates **~2,500 DOM elements**. This causes:
- **Mount Latency**: 150ms–300ms main-thread blocking time when loading a profile.
- **Layout Thrashing**: Any parent state change triggers expensive browser style recalculation and layout passes across all 2,500 elements.
- **Memory Pressure**: Detached DOM nodes and un-collected event listeners degrade long-session responsiveness.

### Virtualization vs. Pagination vs. CSS `content-visibility`

| Technique | When to Use | Advantages | Disadvantages / Trade-offs |
| :--- | :--- | :--- | :--- |
| **Virtualization** (`@tanstack/react-virtual`) | Long scrollable lists (50+ cards, 100+ move rows) | Only renders items in active viewport (+ overscan buffer); constant ~20-30 DOM nodes regardless of list length | Requires explicit container height or dynamic height measurement |
| **Pagination / Infinite Scroll** | Grouped table data or multi-tab views | Simplest DOM reduction; highly accessible | Requires user navigation click; hides summary context |
| **CSS `content-visibility: auto`** | Off-screen cards in long static documents | Browser-native rendering skip; zero JS overhead | Initial layout height estimation required (`contain-intrinsic-size`); DOM nodes still exist in tree |

### Recommended Pattern: Virtualized Finding Grid (`@tanstack/react-virtual`)

For React 19 + TypeScript, `@tanstack/react-virtual` (v3) provides headless, high-performance windowing:

```tsx
import React, { useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';

interface Finding {
  id: string;
  move_number: number;
  severity: string;
  played?: { san?: string; uci?: string };
  best?: { san?: string; uci?: string };
}

interface VirtualizedFindingsGridProps {
  findings: Finding[];
  onFindingClick: (finding: Finding) => void;
}

export const VirtualizedFindingsGrid: React.FC<VirtualizedFindingsGridProps> = React.memo(({
  findings,
  onFindingClick,
}) => {
  const parentRef = useRef<HTMLDivElement>(null);

  const rowVirtualizer = useVirtualizer({
    count: findings.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 140, // estimated height per card in px
    overscan: 5,             // render 5 extra cards above/below viewport
  });

  return (
    <div
      ref={parentRef}
      className="virtual-findings-container"
      style={{ height: `600px`, overflowY: 'auto', position: 'relative' }}
    >
      <div
        style={{
          height: `${rowVirtualizer.getTotalSize()}px`,
          width: '100%',
          position: 'relative',
        }}
      >
        {rowVirtualizer.getVirtualItems().map((virtualRow) => {
          const finding = findings[virtualRow.index];
          return (
            <div
              key={finding.id}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              <FindingCard finding={finding} onClick={() => onFindingClick(finding)} />
            </div>
          );
        })}
      </div>
    </div>
  );
});
```

### Key Strategies & List Rules
1. **Never use array index (`key={idx}`) for dynamic lists**: Index keys force React to reuse component state across items when filtering or sorting, leading to incorrect renders and lost state. Always use unique identifiers (`key={finding.id}`).
2. **Set `contain-intrinsic-size` for CSS fallbacks**:
   ```css
   .finding-card-container {
     content-visibility: auto;
     contain-intrinsic-size: 140px;
   }
   ```

---

## 2. Preventing Needless Re-renders (Component Optimization)

### React 19 Component Optimization Principles
In React 19, re-renders are triggered by state changes, context updates, or parent re-evaluations. Component-level memoization remains critical for expensive subtrees (like chess board containers and report grids).

### 1. `React.memo` for Heavy Visual Subtrees
Wrap heavy presentation components that receive props:

```tsx
export const ProfileHeader = React.memo<ProfileHeaderProps>(
  ({ gamesAnalyzed, blindnessRate, attentionRate }) => {
    return (
      <div className="profile-header glass-panel">
        <h2>Weakness Profile</h2>
        {/* Render stats */}
      </div>
    );
  }
);
```

### 2. Callback & Object Reference Stability (`useCallback` / `useMemo`)
Passing inline functions or new object/array literals into child components invalidates `React.memo` equality checks (`Object.is`).

#### ❌ Anti-Pattern (Breaks Memoization)
```tsx
// Re-creates array reference and inline arrow function on every parent render!
<TrainingBoard
  fen={selectedFinding.fen_before}
  policy={[selectedFinding.best, selectedFinding.played].filter(Boolean)}
  onMove={(uci) => handleMove(uci)}
/>
```

#### ✅ Optimized Pattern
```tsx
const policyCandidates = useMemo(
  () => [selectedFinding?.best, selectedFinding?.played].filter(Boolean),
  [selectedFinding?.best, selectedFinding?.played]
);

const handleBoardMove = useCallback((uci: string, san: string) => {
  // stable move handler logic
}, []);

<TrainingBoard
  fen={selectedFinding.fen_before}
  policy={policyCandidates}
  onMove={handleBoardMove}
/>
```

### 3. Context Splitting & State Colocation
Keep state as close to where it is consumed as possible.
- **State Colocation**: Hover states or input text (`pgnInput`) should stay inside the local form component rather than hoisted to `App` or `TrainingTab`.
- **Context Splitting**: If using React Context, split high-frequency contexts (e.g., active FEN / mouse move) from low-frequency contexts (e.g., user settings / theme).

---

## 3. Code-Splitting & Lazy Loading Heavy Views

### Tab-Level & View-Level Code Splitting
The app features distinct modes: **Analysis Mode** (`PgnViewer`), **Training Mode** (`TrainingTab`), **Repertoire Trainer**, and **Progress Panel**. Standard static imports force the browser to parse all tabs on initial load.

### Implementation Pattern with `React.lazy` + `Suspense`

```tsx
// App.tsx
import React, { useState, Suspense, lazy } from 'react';

// Lazy loading heavy top-level views
const PgnViewer = lazy(() => import('./components/PgnViewer'));
const TrainingTab = lazy(() => import('./components/Training/TrainingTab'));

const LoadingFallback = () => (
  <div className="tab-loading-spinner glass-panel">
    <div className="spinner" />
    <span>Loading view...</span>
  </div>
);

export default function App() {
  const [activeTab, setActiveTab] = useState<'analysis' | 'training'>('analysis');

  return (
    <div className="app-layout">
      <header className="app-header">{/* ... header navigation ... */}</header>
      <main className="main-content">
        <Suspense fallback={<LoadingFallback />}>
          {activeTab === 'analysis' ? <PgnViewer /> : <TrainingTab />}
        </Suspense>
      </main>
    </div>
  );
}
```

### Sub-Panel Lazy Loading in `TrainingTab.tsx`
```tsx
// TrainingTab.tsx
const DiagnosePanel = lazy(() => import('./DiagnosePanel'));
const ProfileReport = lazy(() => import('./ProfileReport'));
const DrillMode = lazy(() => import('./DrillMode'));
const RepertoirePanel = lazy(() => import('./RepertoirePanel'));
const ProgressPanel = lazy(() => import('./ProgressPanel'));
```

---

## 4. Bundle Size Optimization & Asset Delivery

### Analyzing Bundle Footprint with Vite
Add `rollup-plugin-visualizer` to audit JS chunk compositions:

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';

export default defineConfig({
  plugins: [
    react(),
    visualizer({
      filename: './dist/stats.html',
      open: false,
      gzipSize: true,
      brotliSize: true,
    }),
  ],
});
```

### Deferring / Dynamic Script Loading for Non-Critical Vendor Assets
If loading third-party scripts like Lichess PGN viewer (`lichess-pgn-viewer.min.js`), load them on-demand via dynamic script injection rather than unconditional `<script>` tags in `index.html`.

### Image & SVG Asset Optimization Rules
1. **Convert PNG Assets to WebP/AVIF**:
   - `hero.png` (13 KB PNG) → Convert to `hero.webp` (~4-5 KB) or `hero.avif` (~3 KB), reducing image download payload by ~65-75%.
2. **SVG Sprite Management**:
   - Keep vector icons in a single `<svg>` sprite sheet (`public/icons.svg`) referenced via `<use href="/icons.svg#icon-name" />`.
   - Run SVGO on all raw SVGs to strip editor metadata, XML declarations, and redundant attributes.

---

## 5. Vite Production Build Configuration & Chunking

### Optimal `vite.config.ts` Manual Chunking Strategy
By default, Rollup bundles all npm packages into a single monolith vendor chunk. Splitting heavy chess libraries (`chessground`, `chessops`) and framework dependencies (`react`, `react-dom`) optimizes browser caching.

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    target: 'es2022',
    sourcemap: false,
    cssCodeSplit: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('react') || id.includes('react-dom')) {
              return 'vendor-react';
            }
            if (id.includes('chessground') || id.includes('chessops')) {
              return 'vendor-chess';
            }
            return 'vendor-misc';
          }
        },
      },
    },
  },
});
```

---

## 6. Performance Measurement & Verification Protocols

Never guess UI wins—measure empirically using standard browser metrics:

### 1. Component Profiling with `<Profiler>`
Wrap suspected hotspots to capture render duration and commit counts:

```tsx
import { Profiler } from 'react';

function onRenderCallback(
  id: string,
  phase: 'mount' | 'update',
  actualDuration: number,
  baseDuration: number,
  startTime: number,
  commitTime: number
) {
  if (actualDuration > 16) {
    console.warn(`[PERF ALERT] ${id} (${phase}) took ${actualDuration.toFixed(2)}ms`);
  }
}

<Profiler id="ProfileReport" onRender={onRenderCallback}>
  <ProfileReport profile={profile} />
</Profiler>
```

### 2. Web Vitals Real User Monitoring (RUM) Protocol
Integrate `web-vitals` library in `main.tsx`:

```typescript
import { onINP, onLCP, onCLS } from 'web-vitals';

onINP((metric) => console.log('INP:', metric.value, metric.rating));
onLCP((metric) => console.log('LCP:', metric.value, metric.rating));
onCLS((metric) => console.log('CLS:', metric.value, metric.rating));
```

### 3. Automated Benchmark via Vitest Component Performance Tests
Verify render count and execution time thresholds in test setup:

```tsx
it('renders 200 findings within performance budget', () => {
  const start = performance.now();
  render(<VirtualizedProfileReport profile={largeMockProfile} />);
  const duration = performance.now() - start;
  expect(duration).toBeLessThan(100); // 100ms render budget
});
```

---

## 7. Version & Compatibility Matrix

- **React**: 19.x (Strict Mode enabled; concurrent rendering support)
- **Vite**: 6.x / 8.x (Native ESM dev server; Rollup 4 bundling engine)
- **TypeScript**: 5.x / 6.x (`verbatimModuleSyntax` & strict null checks)
- **Chessground**: 9.x (Native DOM chess board rendering)
- **@tanstack/react-virtual**: 3.x (Headless virtualization engine)

---
*Reference document generated for the `chess_speak_out_loud` project repository.*
