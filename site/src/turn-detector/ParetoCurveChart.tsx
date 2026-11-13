'use client';

import { useRef, useState } from 'react';
import { cn } from '../lib/cn';
import { AxisBottom, AxisLeft } from '@visx/axis';
import { curveMonotoneX } from '@visx/curve';
import { GridColumns, GridRows } from '@visx/grid';
import { Group } from '@visx/group';
import { ParentSize } from '@visx/responsive';
import { scaleLinear } from '@visx/scale';
import { LinePath } from '@visx/shape';

import type { Budget, FrontierPoint, TurnDetectorModel } from './selection';
import { metricForBudget, MIN_LATENCY_BUDGET } from './selection';

const tokenColor = (token: string) => `oklch(var(--lk-color-${token}))`;
const SEPARATOR = 'oklch(var(--lk-color-separator1))';
const SEPARATOR2 = 'oklch(var(--lk-color-separator2))';
const FG = 'oklch(var(--lk-color-fg1))';
const BG = 'oklch(var(--lk-color-bg1))';

const MIN_HEIGHT = 420;
const MARGIN = { top: 16, right: 20, bottom: 60, left: 64 } as const;
const LATENCY_DOMAIN_MAX = 2; // focus on the production-relevant low-latency region

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

interface ParetoCurveChartProps {
  models: TurnDetectorModel[];
  frontiers: Record<string, FrontierPoint[]>;
  budget: Budget;
  onBudgetChange: (budget: Budget) => void;
  activeModelKey?: string | null;
}

export function ParetoCurveChart(props: ParetoCurveChartProps) {
  return (
    // The chart fills its container, so it grows with the ranking beside it.
    <div className="relative min-h-[420px] w-full flex-1">
      <div className="absolute inset-0">
        <ParentSize>
          {({ width, height }) =>
            width > 0 ? <Chart width={width} height={Math.max(MIN_HEIGHT, height)} {...props} /> : null
          }
        </ParentSize>
      </div>
    </div>
  );
}

function Chart({
  width,
  height,
  models,
  frontiers,
  budget,
  onBudgetChange,
  activeModelKey,
}: ParetoCurveChartProps & { width: number; height: number }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [dragging, setDragging] = useState(false);

  const innerW = Math.max(0, width - MARGIN.left - MARGIN.right);
  const innerH = height - MARGIN.top - MARGIN.bottom;

  const points = models.flatMap((m) => frontiers[m.key] ?? []);
  const minCut = points.length ? Math.min(...points.map((p) => p[1])) : 0.01;
  const maxLat = LATENCY_DOMAIN_MAX;
  const maxCut = Math.min(1, Math.max(0.3, ...points.map((p) => p[1])));

  const xScale = scaleLinear({ domain: [0, maxLat], range: [0, innerW] });
  const yScale = scaleLinear({ domain: [0, maxCut], range: [innerH, 0] });

  const clipId = 'pareto-plot-clip';

  function updateFromPointer(clientX: number, clientY: number) {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    if (budget.kind === 'latency') {
      const px = clamp(clientX - rect.left - MARGIN.left, 0, innerW);
      onBudgetChange({
        kind: 'latency',
        seconds: clamp(xScale.invert(px), MIN_LATENCY_BUDGET, maxLat),
      });
    } else {
      const py = clamp(clientY - rect.top - MARGIN.top, 0, innerH);
      onBudgetChange({ kind: 'cutoff', fraction: clamp(yScale.invert(py), minCut, maxCut) });
    }
  }

  const guideX = budget.kind === 'latency' ? xScale(budget.seconds) : null;
  const guideY = budget.kind === 'cutoff' ? yScale(budget.fraction) : null;

  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      role="img"
      aria-label="Pareto frontier of false cut-off rate versus mean latency for each model"
    >
      <defs>
        <clipPath id={clipId}>
          <rect x={0} y={0} width={innerW} height={innerH} />
        </clipPath>
      </defs>
      <Group left={MARGIN.left} top={MARGIN.top}>
        <GridRows
          scale={yScale}
          width={innerW}
          numTicks={5}
          stroke={SEPARATOR}
          strokeOpacity={0.6}
        />
        <GridColumns
          scale={xScale}
          height={innerH}
          numTicks={5}
          stroke={SEPARATOR}
          strokeOpacity={0.6}
        />

        <g clipPath={`url(#${clipId})`}>
          {models.map((model) => {
            const frontier = frontiers[model.key];
            if (!frontier || frontier.length === 0) return null;
            const dimmed = activeModelKey != null && activeModelKey !== model.key;
            return (
              <LinePath<FrontierPoint>
                key={model.key}
                data={frontier}
                x={(d) => xScale(d[0])}
                y={(d) => yScale(d[1])}
                curve={curveMonotoneX}
                stroke={tokenColor(model.colorToken)}
                strokeWidth={activeModelKey === model.key ? 3 : model.isLiveKit ? 2.5 : 1.5}
                strokeOpacity={dimmed ? 0.2 : 1}
                strokeDasharray={model.key === 'vad' ? '4 3' : undefined}
                fill="none"
              />
            );
          })}

          {/* Operating point per model at the current budget — ties the curve to the ranking. */}
          {models.map((model) => {
            const value = metricForBudget(frontiers[model.key], budget);
            if (value === null) return null;
            const cx = budget.kind === 'latency' ? xScale(budget.seconds) : xScale(value);
            const cy = budget.kind === 'latency' ? yScale(value) : yScale(budget.fraction);
            if (cx < 0 || cx > innerW || cy < 0 || cy > innerH) return null;
            const dimmed = activeModelKey != null && activeModelKey !== model.key;
            const formatted =
              budget.kind === 'latency'
                ? `${(value * 100).toFixed(1)}% cut-off`
                : `${Math.round(value * 1000)} ms`;
            return (
              <circle
                key={model.key}
                cx={cx}
                cy={cy}
                r={activeModelKey === model.key ? 6 : 4}
                fill={tokenColor(model.colorToken)}
                stroke={BG}
                strokeWidth={1.5}
                opacity={dimmed ? 0.25 : 1}
              >
                <title>{`${model.label}: ${formatted}`}</title>
              </circle>
            );
          })}
        </g>

        {/* Draggable budget guide line. */}
        {guideX !== null && (
          <line
            x1={guideX}
            x2={guideX}
            y1={0}
            y2={innerH}
            stroke={FG}
            strokeWidth={1.5}
            strokeDasharray="5 4"
          />
        )}
        {guideY !== null && (
          <line
            x1={0}
            x2={innerW}
            y1={guideY}
            y2={guideY}
            stroke={FG}
            strokeWidth={1.5}
            strokeDasharray="5 4"
          />
        )}

        <AxisLeft
          scale={yScale}
          numTicks={5}
          stroke={SEPARATOR2}
          tickStroke={SEPARATOR2}
          tickFormat={(v) => `${Math.round(Number(v) * 100)}%`}
          tickLabelProps={() => ({
            className: 'fill-fg3 font-mono text-[10px]',
            dx: '-0.25em',
            dy: '0.25em',
          })}
          label="False cut-off rate"
          labelProps={{ className: 'fill-fg2 text-xs', textAnchor: 'middle' }}
          labelOffset={40}
        />
        <AxisBottom
          scale={xScale}
          top={innerH}
          numTicks={5}
          stroke={SEPARATOR2}
          tickStroke={SEPARATOR2}
          tickFormat={(v) => `${Number(v).toFixed(1)}s`}
          tickLabelProps={() => ({
            className: 'fill-fg3 font-mono text-[10px]',
            textAnchor: 'middle',
            dy: '0.25em',
          })}
          label="Mean latency"
          labelProps={{ className: 'fill-fg2 text-xs', textAnchor: 'middle' }}
          labelOffset={28}
        />

        {/* Pointer overlay — click or drag to move the budget line. */}
        <rect
          x={0}
          y={0}
          width={innerW}
          height={innerH}
          fill="transparent"
          className={cn(budget.kind === 'latency' ? 'cursor-ew-resize' : 'cursor-ns-resize')}
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            setDragging(true);
            updateFromPointer(e.clientX, e.clientY);
          }}
          onPointerMove={(e) => {
            if (dragging) updateFromPointer(e.clientX, e.clientY);
          }}
          onPointerUp={(e) => {
            setDragging(false);
            e.currentTarget.releasePointerCapture(e.pointerId);
          }}
        />
      </Group>
    </svg>
  );
}
