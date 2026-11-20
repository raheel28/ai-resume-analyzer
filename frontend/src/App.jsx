import { useState } from "react";
import CheckMode from "./components/CheckMode.jsx";
import MatchMode from "./components/MatchMode.jsx";
import ServerStatus from "./components/ServerStatus.jsx";

const MODES = {
  check: {
    label: "Resume check",
    blurb: "Upload a PDF or DOCX to see how an applicant tracking system reads it.",
  },
  match: {
    label: "Match to a job",
    blurb: "Add a job description and your resume to see how well you match, and what to change.",
  },
};

export default function App() {
  const [mode, setMode] = useState("check");

  return (
    <main className="page">
      <header>
        <h1>AI Resume Analyzer</h1>
        <nav className="tabs" role="tablist" aria-label="Mode">
          {Object.entries(MODES).map(([id, m]) => (
            <button key={id} type="button" role="tab" aria-selected={mode === id}
                    className={mode === id ? "on" : ""} onClick={() => setMode(id)}>
              {m.label}
            </button>
          ))}
        </nav>
        <p className="muted">{MODES[mode].blurb}</p>
      </header>

      <ServerStatus />

      {/* Both stay mounted so switching tabs doesn't throw away results. */}
      <div className="mode" hidden={mode !== "check"}><CheckMode /></div>
      <div className="mode" hidden={mode !== "match"}><MatchMode /></div>
    </main>
  );
}
