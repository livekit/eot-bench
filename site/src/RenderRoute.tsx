/**
 * Off-page render targets for the README screenshot pipeline
 * (scripts/screenshot-assets.mjs). Visiting the site with `?render=<asset>&
 * theme=<light|dark>` mounts a single asset on a bare, theme-pinned canvas with
 * a stable `#shot` wrapper for Playwright to capture. Normal visitors never hit
 * this — `main.tsx` only uses it when the `render` param is present.
 */

import { HeadlineLatencyChart } from './turn-detector/HeadlineLatencyChart';
import { TurnDetectorCharts } from './turn-detector/TurnDetectorCharts';

export type RenderAsset = 'headline' | 'leaderboard';

/** Pin the theme deterministically regardless of OS preference. The CSS treats
 *  `.dark` as forced-dark and `.light` as forced-light (opting out of the
 *  prefers-color-scheme dark block). */
export function applyTheme(theme: 'light' | 'dark') {
  const root = document.documentElement;
  root.classList.remove('light', 'dark');
  root.classList.add(theme);
}

export function RenderRoute({ asset }: { asset: RenderAsset }) {
  if (asset === 'headline') {
    return (
      <div id="shot" className="bg-bg0 w-[1040px]">
        <HeadlineLatencyChart />
      </div>
    );
  }
  return (
    <div id="shot" className="bg-bg0 w-[1200px] p-8">
      <TurnDetectorCharts variant="snapshot" />
    </div>
  );
}
