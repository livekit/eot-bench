import { TurnDetectorCharts } from './turn-detector/TurnDetectorCharts';

const REPO_URL = 'https://github.com/livekit/eot-bench';
const DATASET_URL = 'https://huggingface.co/datasets/livekit/eot-bench-data';

export default function App() {
  return (
    <div className="text-fg1 min-h-screen">
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
        <header className="mb-8">
          <p className="text-fg3 mb-3 font-mono text-xs tracking-wider uppercase">
            LiveKit · End-of-Turn Detection Benchmark
          </p>
          <h1 className="text-fg0 font-display text-3xl font-medium tracking-tight sm:text-4xl">
            End-of-Turn Detection Leaderboard
          </h1>
          <p className="text-fg2 mt-4 max-w-3xl text-base leading-relaxed">
            The hardest timing problem in voice AI: deciding <em>when</em> an agent should respond.
            Respond too soon and you cut the user off; wait too long and the agent feels slow. Every
            system below is evaluated on the same public dataset, scored causally at real pauses, and
            compared on the latency it adds after a true turn ending versus the false cut-offs it
            makes during mid-turn pauses.
          </p>
          <div className="mt-5 flex flex-wrap gap-3 text-sm">
            <a
              className="border-separator1 text-fg1 hover:border-accent hover:text-fg0 rounded-md border px-3 py-1.5 transition-colors"
              href={REPO_URL}
              target="_blank"
              rel="noreferrer"
            >
              GitHub repo
            </a>
            <a
              className="border-separator1 text-fg1 hover:border-accent hover:text-fg0 rounded-md border px-3 py-1.5 transition-colors"
              href={DATASET_URL}
              target="_blank"
              rel="noreferrer"
            >
              Dataset ↗ livekit/eot-bench-data
            </a>
          </div>
        </header>

        <main>
          <TurnDetectorCharts />
        </main>

        <section className="text-fg2 mt-12 max-w-3xl space-y-4 text-sm leading-relaxed">
          <h2 className="text-fg0 text-lg font-semibold">How to read this</h2>
          <p>
            Pick a <strong>budget</strong> — a maximum latency (how long the agent may wait) or a
            maximum false cut-off rate (how often it may interrupt). Every model is then held to that
            same budget and ranked on the other axis. The Pareto curve shows the full latency/cut-off
            tradeoff each model can support; the dot on each curve is its operating point at the
            current budget. Lower-left is better.
          </p>
          <p>
            A silence-only <strong>VAD baseline</strong> runs through the identical evaluation, so
            learned and commercial turn detectors are always measured against timing alone. Numbers
            are computed from the reproducible prediction artifacts committed under{' '}
            <a className="text-accent hover:underline" href={`${REPO_URL}/tree/main/output`}>
              <code>output/</code>
            </a>{' '}
            in the harness — see the repo to run a new model through the same grid.
          </p>
        </section>

        <footer className="border-separator1 text-fg3 mt-12 border-t pt-6 text-xs">
          Apache-2.0 licensed ·{' '}
          <a className="hover:text-fg1" href={DATASET_URL}>
            livekit/eot-bench-data
          </a>{' '}
          · Built by{' '}
          <a className="hover:text-fg1" href="https://livekit.io">
            LiveKit
          </a>
        </footer>
      </div>
    </div>
  );
}
