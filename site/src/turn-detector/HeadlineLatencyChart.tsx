'use client';

/**
 * Headline bar chart: end-of-turn delay (mean latency in ms) at a fixed 5%
 * false-cutoff budget, English. This is the single-glance "how much dead air
 * does each model leave" view used as the lead asset in the repo README.
 *
 * It is intentionally NOT wired into the live leaderboard UI — it exists so the
 * screenshot pipeline (scripts/screenshot-assets.mjs) can render it to a PNG.
 * Colors, fonts, and tokens follow the same Bytes design system as the rest of
 * the site, so the rendered PNG matches the live charts.
 */

import { AxisBottom } from '@visx/axis';
import { GridColumns } from '@visx/grid';
import { Group } from '@visx/group';
import { ParentSize } from '@visx/responsive';
import { scaleBand, scaleLinear } from '@visx/scale';
import { Bar } from '@visx/shape';

import { TURN_DETECTOR_DATA } from './data';
import type { TurnDetectorData } from './selection';
import { rankingForBudget } from './selection';

const CUTOFF_BUDGET = 0.05;

const tokenColor = (token: string) => `oklch(var(--lk-color-${token}))`;
const SEPARATOR = 'oklch(var(--lk-color-separator1))';
const SEPARATOR2 = 'oklch(var(--lk-color-separator2))';
const HATCH_STROKE = 'oklch(var(--lk-color-fg2))';

const MARGIN = { top: 8, right: 96, bottom: 56, left: 8 } as const;
const ROW_HEIGHT = 56;
const BAR_HEIGHT = 22;
const LABEL_GAP = 8; // space between the model label and its bar

interface HeadlineLatencyChartProps {
  data?: TurnDetectorData;
}

export function HeadlineLatencyChart({ data = TURN_DETECTOR_DATA }: HeadlineLatencyChartProps) {
  const rows = rankingForBudget(data, { kind: 'cutoff', fraction: CUTOFF_BUDGET })
    .filter((r): r is { model: (typeof data.models)[number]; value: number } => r.value !== null)
    .map((r) => ({ model: r.model, ms: r.value * 1000 }));

  const height = MARGIN.top + MARGIN.bottom + rows.length * ROW_HEIGHT;

  return (
    <div className="bg-bg0 w-full p-8">
      <h3 className="text-fg0 font-display text-2xl font-medium tracking-tight sm:text-3xl">
        End-of-turn delay at a 5% false-cutoff budget (English)
      </h3>
      <p className="text-fg3 mt-2 max-w-3xl text-sm leading-relaxed sm:text-base">
        Average dead air after the user actually finishes, with each model tuned to interrupt no
        more than 5% of the time. Not inference time.
      </p>
      <div className="mt-6 w-full" style={{ height }}>
        <ParentSize>
          {({ width }) =>
            width > 0 ? <Bars width={width} height={height} rows={rows} /> : null
          }
        </ParentSize>
      </div>
    </div>
  );
}

interface BarsProps {
  width: number;
  height: number;
  rows: { model: TurnDetectorData['models'][number]; ms: number }[];
}

function Bars({ width, height, rows }: BarsProps) {
  const innerW = Math.max(0, width - MARGIN.left - MARGIN.right);
  const innerH = height - MARGIN.top - MARGIN.bottom;

  const maxMs = Math.max(...rows.map((r) => r.ms));
  // Round the axis up to a clean 250 ms step so the gridlines land on round numbers.
  const xMax = Math.ceil(maxMs / 250) * 250;

  const xScale = scaleLinear({ domain: [0, xMax], range: [0, innerW] });
  const yScale = scaleBand({
    domain: rows.map((r) => r.model.key),
    range: [0, innerH],
    paddingInner: 0,
  });

  return (
    <svg
      width={width}
      height={height}
      role="img"
      aria-label="End-of-turn delay in milliseconds at a 5% false-cutoff budget per model, English"
    >
      <defs>
        {/* Diagonal hatch for the silence-only VAD baseline — marks it as a
            timing-only reference rather than a learned model. */}
        <pattern id="vad-hatch" patternUnits="userSpaceOnUse" width={7} height={7}>
          <path d="M0,7 L7,0 M-1,1 L1,-1 M6,8 L8,6" stroke={HATCH_STROKE} strokeWidth={1} />
        </pattern>
      </defs>
      <Group left={MARGIN.left} top={MARGIN.top}>
        <GridColumns
          scale={xScale}
          height={innerH}
          numTicks={Math.round(xMax / 250)}
          stroke={SEPARATOR}
          strokeOpacity={0.6}
        />

        {rows.map((row) => {
          const band = yScale(row.model.key) ?? 0;
          const barY = band + (ROW_HEIGHT - BAR_HEIGHT - LABEL_GAP);
          const barW = xScale(row.ms);
          const isVad = row.model.key === 'vad';
          const color = tokenColor(row.model.colorToken);
          return (
            <Group key={row.model.key}>
              {/* Model label, above its bar. */}
              <text
                x={0}
                y={barY - LABEL_GAP}
                className={
                  row.model.isLiveKit
                    ? 'fill-fg0 text-[15px] font-semibold'
                    : 'fill-fg1 text-[15px]'
                }
                dominantBaseline="alphabetic"
              >
                {row.model.label}
              </text>
              {/* Bar — solid token color, or hatched for the VAD baseline. */}
              <Bar
                x={0}
                y={barY}
                width={barW}
                height={BAR_HEIGHT}
                fill={isVad ? 'url(#vad-hatch)' : color}
                rx={2}
              />
              {isVad && (
                <Bar
                  x={0}
                  y={barY}
                  width={barW}
                  height={BAR_HEIGHT}
                  fill="none"
                  stroke={HATCH_STROKE}
                  strokeOpacity={0.7}
                  rx={2}
                />
              )}
              {/* Value label at the bar end. */}
              <text
                x={barW + 10}
                y={barY + BAR_HEIGHT / 2}
                className={
                  row.model.isLiveKit
                    ? 'fill-fg0 font-mono text-[15px] font-semibold tabular-nums'
                    : 'fill-fg2 font-mono text-[15px] tabular-nums'
                }
                dominantBaseline="middle"
              >
                {Math.round(row.ms)} ms
              </text>
            </Group>
          );
        })}

        <AxisBottom
          scale={xScale}
          top={innerH}
          numTicks={Math.round(xMax / 250)}
          stroke={SEPARATOR2}
          tickStroke={SEPARATOR2}
          tickFormat={(v) => `${Number(v)}`}
          tickLabelProps={() => ({
            className: 'fill-fg3 font-mono text-[11px]',
            textAnchor: 'middle',
            dy: '0.25em',
          })}
          label="Mean delay after the user finishes speaking (ms)  ·  lower is better"
          labelProps={{ className: 'fill-fg3 text-xs', textAnchor: 'middle' }}
          labelOffset={24}
        />
      </Group>
    </svg>
  );
}
