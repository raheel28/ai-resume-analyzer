import { useState } from "react";
import { aiReview, analyzeResume } from "../api.js";
import UploadZone from "./UploadZone.jsx";
import ScoreSummary from "./ScoreSummary.jsx";
import IssueList from "./IssueList.jsx";
import AIReview from "./AIReview.jsx";
import ApplyPanel from "./ApplyPanel.jsx";

export default function CheckMode() {
  const [targetRole, setTargetRole] = useState("");
  const [file, setFile] = useState(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [ai, setAi] = useState({ status: "idle" });
  const [selected, setSelected] = useState([]);

  function runAiReview(f = file) {
    if (!f) return;
    setSelected([]);
    setAi({ status: "loading" });
    aiReview(f, targetRole)
      .then((data) => setAi({ status: "done", data }))
      .catch((e) => setAi({ status: "error", message: e.message,
                            disabled: e.message.includes("GEMINI_API_KEY") }));
  }

  async function handleFile(f) {
    setFile(f);
    setLoading(true);
    setError("");
    setReport(null);
    runAiReview(f);
    try {
      setReport(await analyzeResume(f));
    } catch (e) {
      setError(e.message);
      setAi({ status: "idle" });
    } finally {
      setLoading(false);
    }
  }

  const passed = report?.checks.filter((c) => c.passed) ?? [];

  return (
    <>
      <label className="field">
        <span>Target role <span className="muted">(optional)</span></span>
        <input type="text" maxLength={100} placeholder="e.g. Junior Backend Engineer"
               value={targetRole} onChange={(e) => setTargetRole(e.target.value)} />
      </label>

      <UploadZone onFile={handleFile} disabled={loading || ai.status === "loading"} />
      {loading && <p className="muted">Analysing…</p>}
      {error && <p className="error">{error}</p>}

      {report && (
        <>
          {report.warnings.map((w) => <p key={w} className="banner">{w}</p>)}
          <ScoreSummary report={report} />
          <AIReview state={ai} onRetry={() => runAiReview()} onSelectionChange={setSelected} />
          <IssueList issues={report.issues} />
          {passed.length > 0 && (
            <details className="card">
              <summary>{passed.length} checks passed</summary>
              <ul className="passed">
                {passed.map((c) => (
                  <li key={c.id}>✓ {c.title}: <span className="muted">{c.message}</span></li>
                ))}
              </ul>
            </details>
          )}
          <ApplyPanel key={`${file.name}-${file.lastModified}`} file={file} selected={selected} />
        </>
      )}
    </>
  );
}
