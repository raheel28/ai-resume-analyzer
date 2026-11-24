import { useState } from "react";
import { aiMatch, matchResume } from "../api.js";
import UploadZone from "./UploadZone.jsx";
import JDInput, { jdPayload, jdReady } from "./JDInput.jsx";
import MatchSummary from "./MatchSummary.jsx";
import AIReview from "./AIReview.jsx";
import ApplyPanel from "./ApplyPanel.jsx";

export default function MatchMode() {
  const [jd, setJd] = useState({ mode: "text", text: "", file: null });
  const [file, setFile] = useState(null);
  const [match, setMatch] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [ai, setAi] = useState({ status: "idle" });
  const [selected, setSelected] = useState([]);
  const [addSkills, setAddSkills] = useState([]);

  const busy = loading || ai.status === "loading";
  const ready = file && jdReady(jd);

  function runAi(f = file) {
    setSelected([]);
    setAi({ status: "loading" });
    aiMatch(f, jdPayload(jd))
      .then((data) => setAi({ status: "done", data }))
      .catch((e) => setAi({ status: "error", message: e.message,
                            disabled: e.message.includes("GEMINI_API_KEY") }));
  }

  async function compare(f = file) {
    if (!f || !jdReady(jd)) return;
    setLoading(true);
    setError("");
    setMatch(null);
    setAddSkills([]);
    runAi(f);
    try {
      setMatch(await matchResume(f, jdPayload(jd)));
    } catch (e) {
      setError(e.message);
      setAi({ status: "idle" });
    } finally {
      setLoading(false);
    }
  }

  function handleFile(f) {
    setFile(f);
    if (jdReady(jd)) compare(f);
  }

  function toggleSkill(skill, on) {
    setAddSkills((all) => (on ? [...all, skill] : all.filter((s) => s !== skill)));
  }

  return (
    <>
      <JDInput value={jd} onChange={setJd} disabled={busy} />

      <UploadZone onFile={handleFile} disabled={busy} />
      {file && <p className="muted small">Resume: <strong>{file.name}</strong></p>}

      <button type="button" className="primary" disabled={!ready || busy} onClick={() => compare()}>
        {busy ? "Comparing…" : match ? "Compare again" : "Compare with job description"}
      </button>
      {!jdReady(jd) && (
        <p className="muted small">
          {jd.mode === "text" ? "Paste the job description (at least a few lines)." : "Choose a job description file."}
        </p>
      )}
      {error && <p className="error">{error}</p>}

      {match && (
        <>
          <MatchSummary match={match} ai={ai} addSkills={addSkills} onToggleSkill={toggleSkill} />
          <AIReview state={ai} onRetry={() => runAi()} onSelectionChange={setSelected}
                    title="AI match review" improveLabel="Gaps for this job" />
          <ApplyPanel key={`${file.name}-${file.lastModified}`} file={file}
                      selected={selected} skills={addSkills} />
        </>
      )}
    </>
  );
}
