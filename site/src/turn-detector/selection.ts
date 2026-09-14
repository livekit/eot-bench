/**
 * Shared types and pure selection logic for the connected turn-detector
 * benchmark visualizations.
 *
 * The three views (Pareto curve, ranking table, multilingual heatmap) are
 * driven by a single `Budget` selection. Given a budget, every derived metric
 * is computed by interpolating a model's Pareto frontier — see the functions
 * below. All logic here is pure (no React) so it can be unit-reasoned and
 * reused across the three views.
 */

/** A point on a model's Pareto frontier: `[meanLatencySeconds, cutoffFraction]`. */
export type FrontierPoint = readonly [latencySeconds: number, cutoffFraction: number];

/** Chart color tokens from `@repo/bytes-core` (`--lk-color-<token>`). */
export type ChartColorToken =
  | 'chart1'
  | 'chart2'
  | 'chart3'
  | 'chart4'
  | 'chart5'
  | 'chart6'
  | 'chart7'
  | 'chart8'
  | 'chart9'
  | 'chart10'
  | 'chart11'
  | 'chartSuccess'
  | 'chartSerious'
  | 'chartModerate';

export interface TurnDetectorModel {
  /** Stable internal key, decoupled from the display label. */
  key: string;
  /** Display label — already relabeled (e.g. "LiveKit turn detector v1.0"). */
  label: string;
  /** Chart color token used for this model's series. */
  colorToken: ChartColorToken;
  /** Whether this is one of the LiveKit models (highlighted in the UI). */
  isLiveKit?: boolean;
}

export interface DiscriminationRow {
  model: string;
  auc: number;
  precision: number;
  recall: number;
  f1: number;
}

export interface TurnDetectorData {
  models: TurnDetectorModel[];
  /** Language codes, e.g. `['ar', 'de', 'en', ...]`. */
  languages: string[];
  /** English/overall Pareto frontier per model key (sorted by latency asc). */
  frontiers: Record<string, FrontierPoint[]>;
  /** Per-language Pareto frontiers: `byLanguage[lang][modelKey]`. */
  byLanguage: Record<string, Record<string, FrontierPoint[]>>;
  /** Static discrimination table (AUC/precision/recall/F1) from the post. */
  discrimination: DiscriminationRow[];
}

/**
 * The selection that connects all three views.
 *
 * - `latency`: a vertical x-line. We minimize cut-off rate subject to a latency
 *   budget — the derived metric is cut-off rate (lower is better).
 * - `cutoff`: a horizontal y-line. We minimize latency subject to a cut-off-rate
 *   budget — the derived metric is latency (lower is better).
 */
export type Budget = { kind: 'latency'; seconds: number } | { kind: 'cutoff'; fraction: number };

/**
 * Audio models are scored 200 ms after speech ends, so a latency budget at or
 * below 200 ms is degenerate. Keep the slider and drag floor strictly above it.
 */
export const MIN_LATENCY_BUDGET = 0.21;

/** Which quantity the ranking/heatmap show for a given budget kind. */
export type MetricKind = 'cutoff' | 'latency';

export function metricKindForBudget(budget: Budget): MetricKind {
  return budget.kind === 'latency' ? 'cutoff' : 'latency';
}

const EPSILON = 1e-9;

/**
 * Minimum achievable cut-off rate within a latency budget `L`.
 *
 * On a (latency, cutoff) Pareto frontier both quantities are minimized, so
 * cut-off rate is non-increasing as latency grows. The best (lowest) cut-off
 * within `latency <= L` is the cut-off of the in-budget frontier point with the
 * largest latency. We deliberately do NOT interpolate past the budget: a point
 * at `latency > L` is a policy that overruns the budget, and blending it in
 * would report a cut-off no real in-budget policy achieves. Clamping this way
 * matches the harness's exact-grid operating point (`compare-models`). Returns
 * `null` when no configuration is that fast (budget below the frontier's
 * fastest point).
 */
export function cutoffAtLatency(frontier: readonly FrontierPoint[], L: number): number | null {
  let best: number | null = null;
  for (const point of frontier) {
    const [lat, cut] = point;
    if (lat <= L + EPSILON && (best === null || cut < best)) best = cut;
  }
  return best;
}

/**
 * Minimum achievable mean latency within a cut-off-rate budget `C`.
 *
 * Latency is non-increasing as cut-off rate grows along the frontier, so the
 * lowest latency for `cutoff <= C` is the latency of the in-budget frontier
 * point with the smallest latency. As with `cutoffAtLatency`, we clamp rather
 * than interpolate across the budget so the reported latency belongs to a real
 * policy that meets the cut-off budget, matching the harness's exact-grid
 * operating point (`compare-models`). Returns `null` when the model's frontier
 * never reaches a cut-off rate that low.
 */
export function latencyAtCutoff(frontier: readonly FrontierPoint[], C: number): number | null {
  let best: number | null = null;
  for (const point of frontier) {
    const [lat, cut] = point;
    if (cut <= C + EPSILON && (best === null || lat < best)) best = lat;
  }
  return best;
}

/** Derived metric (cut-off fraction or latency seconds) for a single frontier. */
export function metricForBudget(
  frontier: readonly FrontierPoint[] | undefined,
  budget: Budget,
): number | null {
  if (!frontier || frontier.length === 0) return null;
  return budget.kind === 'latency'
    ? cutoffAtLatency(frontier, budget.seconds)
    : latencyAtCutoff(frontier, budget.fraction);
}

export interface RankingRow {
  model: TurnDetectorModel;
  /** Derived metric value, or `null` when the budget is unreachable. */
  value: number | null;
}

/** Models ranked by the derived metric at `budget` (lower is better, nulls last). */
export function rankingForBudget(data: TurnDetectorData, budget: Budget): RankingRow[] {
  const rows: RankingRow[] = data.models.map((model) => ({
    model,
    value: metricForBudget(data.frontiers[model.key], budget),
  }));
  return rows.sort((a, b) => {
    if (a.value === null && b.value === null) return 0;
    if (a.value === null) return 1;
    if (b.value === null) return -1;
    return a.value - b.value;
  });
}

/** A single heatmap cell: derived metric for one (language, model) pair. */
export interface HeatmapCell {
  language: string;
  modelKey: string;
  value: number | null;
}

/** Derived metric per (language, model) at `budget`, plus the value range. */
export interface HeatmapResult {
  cells: HeatmapCell[];
  /** Min/max across all non-null cells — for the color ramp. */
  min: number;
  max: number;
}

export function heatmapForBudget(data: TurnDetectorData, budget: Budget): HeatmapResult {
  const cells: HeatmapCell[] = [];
  let min = Infinity;
  let max = -Infinity;
  for (const language of data.languages) {
    const perModel = data.byLanguage[language] ?? {};
    for (const model of data.models) {
      const value = metricForBudget(perModel[model.key], budget);
      cells.push({ language, modelKey: model.key, value });
      if (value !== null) {
        if (value < min) min = value;
        if (value > max) max = value;
      }
    }
  }
  if (!Number.isFinite(min)) {
    min = 0;
    max = 1;
  }
  return { cells, min, max };
}

/**
 * Normalized "goodness" of a value in `[0, 1]` for the heatmap color ramp.
 * Lower metric values are better for both cut-off and latency, so `1` is best.
 */
export function goodness(value: number, min: number, max: number): number {
  if (max - min < EPSILON) return 1;
  return 1 - (value - min) / (max - min);
}

/** Format a derived metric value for display, given the budget kind. */
export function formatMetric(value: number | null, kind: MetricKind): string {
  if (value === null) return 'n/a';
  return kind === 'cutoff' ? `${(value * 100).toFixed(1)}%` : `${Math.round(value * 1000)} ms`;
}
