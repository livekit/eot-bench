/**
 * Render the README assets to PNG, in both color themes, from the built site.
 *
 * For each (asset × theme) it loads the off-page render target
 * (`?render=<asset>&theme=<theme>`, see src/RenderRoute.tsx), waits for fonts +
 * charts to settle, and captures the `#shot` element at 2× for crispness. The
 * brand fonts (Public Sans / CommitMono / TWK Everett) are bundled into the
 * build, so the PNGs render exact DESIGN.md typography.
 *
 * Run via `pnpm gen-assets` (which builds first). Outputs to repo `assets/`.
 */

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { extname, join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SITE_DIR = resolve(__dirname, '..');
const DIST_DIR = join(SITE_DIR, 'dist');
const ASSETS_DIR = resolve(SITE_DIR, '..', 'assets');
const SCALE = 2;

const TARGETS = [
  { asset: 'headline', theme: 'light', out: 'headline_latency_en_light.png' },
  { asset: 'headline', theme: 'dark', out: 'headline_latency_en_dark.png' },
  { asset: 'leaderboard', theme: 'light', out: 'leaderboard_light.png' },
  { asset: 'leaderboard', theme: 'dark', out: 'leaderboard_dark.png' },
];

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.woff2': 'font/woff2',
  '.svg': 'image/svg+xml',
  '.json': 'application/json',
};

// Must match `base` in vite.config.ts: the built index.html requests assets at
// absolute /benchmarks/eot-bench/… URLs, but we serve dist from root here.
const BASE_PREFIX = '/benchmarks/eot-bench';

function startServer() {
  const server = createServer(async (req, res) => {
    let urlPath = decodeURIComponent((req.url ?? '/').split('?')[0]);
    if (urlPath.startsWith(BASE_PREFIX)) urlPath = urlPath.slice(BASE_PREFIX.length) || '/';
    // Resolve within DIST_DIR and reject anything that escapes it (path traversal).
    const distRoot = DIST_DIR.endsWith('/') ? DIST_DIR : `${DIST_DIR}/`;
    const relPath = (urlPath === '/' ? 'index.html' : urlPath).replace(/^\/+/, '');
    const candidatePath = resolve(DIST_DIR, relPath);
    let filePath = candidatePath.startsWith(distRoot) ? candidatePath : join(DIST_DIR, 'index.html');
    if (!existsSync(filePath)) filePath = join(DIST_DIR, 'index.html'); // SPA fallback
    try {
      const body = await readFile(filePath);
      res.writeHead(200, { 'Content-Type': MIME[extname(filePath)] ?? 'application/octet-stream' });
      res.end(body);
    } catch {
      res.writeHead(404);
      res.end('not found');
    }
  });
  return new Promise((res) => {
    server.listen(0, '127.0.0.1', () => res({ server, port: server.address().port }));
  });
}

async function main() {
  if (!existsSync(join(DIST_DIR, 'index.html'))) {
    throw new Error(`No build found at ${DIST_DIR}. Run \`vite build\` first (pnpm gen-assets does this).`);
  }
  const { server, port } = await startServer();
  const base = `http://127.0.0.1:${port}`;
  const browser = await chromium.launch();
  const context = await browser.newContext({ deviceScaleFactor: SCALE, viewport: { width: 1320, height: 1600 } });
  const page = await context.newPage();

  for (const { asset, theme, out } of TARGETS) {
    await page.goto(`${base}/?render=${asset}&theme=${theme}`, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForSelector('#shot');
    await page.waitForTimeout(400); // let ParentSize/ResizeObserver settle the chart width
    const el = await page.$('#shot');
    const outPath = join(ASSETS_DIR, out);
    await el.screenshot({ path: outPath });
    console.log(`✓ ${out}`);
  }

  await browser.close();
  server.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
