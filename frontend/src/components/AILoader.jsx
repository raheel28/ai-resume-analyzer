import { useEffect, useState } from "react";

const EXPECTED_SECONDS = 12;

const STEPS = [
  { at: 0, label: "Reading your resume" },
  { at: 3, label: "Scoring impact, clarity, depth and role fit" },
  { at: 8, label: "Finding your weakest bullets" },
  { at: 13, label: "Writing rewrites" },
  { at: 18, label: "Checking rewrites for invented numbers or skills" },
];

export default function AILoader() {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => setElapsed((Date.now() - start) / 1000), 200);
    return () => clearInterval(id);
  }, []);

  const progress = 95 * (1 - Math.exp(-elapsed / (EXPECTED_SECONDS / 2.5)));
  const step = [...STEPS].reverse().find((s) => elapsed >= s.at);
  const slow = elapsed > 25;

  return (
    <div className="ai-loader" role="status" aria-live="polite">
      <div className="ai-loader-row">
        <span className="spinner" aria-hidden="true" />
        <span>{step.label}…</span>
        <span className="muted small elapsed">{Math.floor(elapsed)}s</span>
      </div>
      <div className="bar ai-bar">
        <div className="fill ok" style={{ width: `${progress}%` }} />
      </div>
      <p className="muted small">
        {slow
          ? "Taking longer than usual. The model may be busy, so the server is retrying or switching to a backup model."
          : "Estimated progress. AI reviews usually take 5–20 seconds."}
      </p>
    </div>
  );
}
