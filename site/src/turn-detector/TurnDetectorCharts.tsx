'use client';

import { useMemo, useState } from 'react';
import { cn } from '../lib/cn';

import { TURN_DETECTOR_DATA } from './data';
import { LanguageHeatmap } from './LanguageHeatmap';
import { ParetoCurveChart } from './ParetoCurveChart';
import { RankingTable } from './RankingTable';
import type { Budget, TurnDetectorData } from './selection';
import {
  formatMetric,
  metricKindForBudget,
  MIN_LATENCY_BUDGET,
  rankingForBudget,
} from './selection';

const tokenColor = (token: string) => `oklch(var(--lk-color-${token}))`;

const LATENCY_PRESETS = [
  { label: '300 ms', seconds: 0.3 },
  { label: '600 ms', seconds: 0.6 },
] as const;
const CUTOFF_PRESETS = [
  { label: '5%', fraction: 0.05 },
  { label: '10%', fraction: 0.1 },
] as const;

const DEFAULT_LATENCY: Budget = { kind: 'latency', seconds: 0.3 };
const DEFAULT_CUTOFF: Budget = { kind: 'cutoff', fraction: 0.05 };

interface TurnDetectorChartsProps {
  data?: TurnDetectorData;
  /** Initial budget (defaults to a 300 ms latency target). */
  initialBudget?: Budget;
  /**
   * `'snapshot'` renders a static composite for the README screenshot pipeline:
   * the interactive chrome (budget controls, drag hint) is hidden and the outer
   * margin dropped, leaving caption + legend + Pareto + ranking + heatmap.
   */
  variant?: 'default' | 'snapshot';
}

export function TurnDetectorCharts({
  data = TURN_DETECTOR_DATA,
  initialBudget = DEFAULT_LATENCY,
  variant = 'default',
}: TurnDetectorChartsProps) {
  const isSnapshot = variant === 'snapshot';
  const [budget, setBudget] = useState<Budget>(initialBudget);
  const [activeModelKey, setActiveModelKey] = useState<string | null>(null);

  const bounds = useMemo(() => {
    const points = data.models.flatMap((m) => data.frontiers[m.key] ?? []);
    return {
      minCut: points.length ? Math.min(...points.map((p) => p[1])) : 0.01,
    };
  }, [data]);

  const kind = metricKindForBudget(budget);
  const leader = rankingForBudget(data, budget).find((r) => r.value !== null);

  return (
    <div className={cn('text-fg1', !isSnapshot && 'my-10')}>
      <div className="border-separator1 bg-bg1 rounded-lg border p-4 sm:p-6">
        {/* Controls */}
        {!isSnapshot && (
        <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <span className="text-fg3 mb-2 block font-mono text-xs tracking-wider uppercase">
              Constrain by
            </span>
            <div
              className="border-separator1 inline-flex rounded-md border p-0.5"
              role="group"
              aria-label="Budget type"
            >
              <BudgetToggle
                active={budget.kind === 'latency'}
                label="Latency budget"
                onClick={() => setBudget(DEFAULT_LATENCY)}
              />
              <BudgetToggle
                active={budget.kind === 'cutoff'}
                label="Cut-off budget"
                onClick={() => setBudget(DEFAULT_CUTOFF)}
              />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-4">
              <label htmlFor="td-budget-slider" className="text-fg2 text-sm">
                {budget.kind === 'latency' ? 'Max latency' : 'Max false cut-off rate'}
              </label>
              <span className="text-fg0 font-mono text-sm tabular-nums">
                {budget.kind === 'latency'
                  ? `${Math.round(budget.seconds * 1000)} ms`
                  : `${(budget.fraction * 100).toFixed(1)}%`}
              </span>
            </div>
            {budget.kind === 'latency' ? (
              <input
                id="td-budget-slider"
                type="range"
                className="accent-accent w-full sm:w-64"
                min={MIN_LATENCY_BUDGET}
                max={2}
                step={0.01}
                value={budget.seconds}
                aria-label="Maximum latency in seconds"
                onChange={(e) => setBudget({ kind: 'latency', seconds: Number(e.target.value) })}
              />
            ) : (
              <input
                id="td-budget-slider"
                type="range"
                className="accent-accent w-full sm:w-64"
                min={bounds.minCut}
                max={0.6}
                step={0.005}
                value={budget.fraction}
                aria-label="Maximum false cut-off rate as a fraction"
                onChange={(e) => setBudget({ kind: 'cutoff', fraction: Number(e.target.value) })}
              />
            )}
            <div className="flex items-center gap-2">
              <span className="text-fg3 text-xs">Presets:</span>
              {budget.kind === 'latency'
                ? LATENCY_PRESETS.map((p) => (
                    <PresetChip
                      key={p.label}
                      label={p.label}
                      active={Math.abs(budget.seconds - p.seconds) < 1e-6}
                      onClick={() => setBudget({ kind: 'latency', seconds: p.seconds })}
                    />
                  ))
                : CUTOFF_PRESETS.map((p) => (
                    <PresetChip
                      key={p.label}
                      label={p.label}
                      active={Math.abs(budget.fraction - p.fraction) < 1e-6}
                      onClick={() => setBudget({ kind: 'cutoff', fraction: p.fraction })}
                    />
                  ))}
            </div>
          </div>
        </div>
        )}

        {/* Readout — dynamic numbers sit in fixed-width slots so the sentence doesn't reflow. */}
        {leader && (
          <p className="text-fg2 mb-4 text-sm">
            At a{' '}
            <span className="text-fg0 inline-block min-w-[3.75rem] text-left font-mono tabular-nums">
              {budget.kind === 'latency'
                ? `${Math.round(budget.seconds * 1000)} ms`
                : `${(budget.fraction * 100).toFixed(1)}%`}
            </span>{' '}
            {budget.kind === 'latency' ? 'latency' : 'cut-off'} budget,{' '}
            <span className="text-fg0 font-medium">{leader.model.label}</span> leads with{' '}
            <span className="text-fg0 inline-block min-w-[4rem] text-left font-mono tabular-nums">
              {formatMetric(leader.value, kind)}
            </span>{' '}
            {kind === 'cutoff' ? 'false cut-offs' : 'mean latency'}.
          </p>
        )}

        {/* Legend */}
        <div className="mb-4 flex flex-wrap gap-x-4 gap-y-2">
          {data.models.map((model) => (
            <button
              key={model.key}
              type="button"
              className={cn(
                'flex items-center gap-1.5 rounded text-xs transition-opacity',
                activeModelKey != null && activeModelKey !== model.key && 'opacity-40',
              )}
              onMouseEnter={() => setActiveModelKey(model.key)}
              onMouseLeave={() => setActiveModelKey(null)}
              onFocus={() => setActiveModelKey(model.key)}
              onBlur={() => setActiveModelKey(null)}
            >
              <span
                aria-hidden
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: tokenColor(model.colorToken) }}
              />
              <span className={cn('text-fg2', model.isLiveKit && 'text-fg0 font-medium')}>
                {model.label}
              </span>
            </button>
          ))}
        </div>

        {/* Curve + ranking */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_360px]">
          {/* min-w-0 lets the 1fr track shrink below the chart SVG's measured width; without it
              the explicitly-sized SVG pins the track wide and ParentSize never scales back down. */}
          <div className="min-w-0">
            <ParetoCurveChart
              models={data.models}
              frontiers={data.frontiers}
              budget={budget}
              onBudgetChange={setBudget}
              activeModelKey={activeModelKey}
            />
            {!isSnapshot && (
              <p className="text-fg3 mt-3 text-center text-xs">
                Drag the dashed line, or use the slider, to set the budget.
              </p>
            )}
          </div>
          <div>
            <h4 className="text-fg2 mb-2 text-sm font-semibold">Ranking</h4>
            <RankingTable
              data={data}
              budget={budget}
              activeModelKey={activeModelKey}
              onActiveModelChange={setActiveModelKey}
            />
          </div>
        </div>

        {/* Heatmap */}
        <div className="mt-8">
          <h4 className="text-fg2 mb-2 text-sm font-semibold">Per-language performance</h4>
          <LanguageHeatmap
            data={data}
            budget={budget}
            activeModelKey={activeModelKey}
            onActiveModelChange={setActiveModelKey}
          />
        </div>
      </div>
    </div>
  );
}

function BudgetToggle({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'rounded px-3 py-1.5 text-sm transition-colors',
        active ? 'bg-bg3 text-fg0' : 'text-fg3 hover:text-fg1',
      )}
    >
      {label}
    </button>
  );
}

function PresetChip({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'border-separator1 rounded-full border px-2 py-0.5 font-mono text-xs transition-colors',
        active ? 'border-accent text-fg0' : 'text-fg3 hover:text-fg1',
      )}
    >
      {label}
    </button>
  );
}
