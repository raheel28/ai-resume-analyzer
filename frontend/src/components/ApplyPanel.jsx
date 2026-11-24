import { useState } from "react";
import { applyChanges } from "../api.js";
import { ANY_BRACKET } from "../placeholders.js";

function download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function plural(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export default function ApplyPanel({ file, selected = [], skills = [] }) {
  const isDocx = file?.name.toLowerCase().endsWith(".docx");
  const [format, setFormat] = useState(isDocx ? "docx" : "pdf");
  const [keepLayout, setKeepLayout] = useState(true);
  const [status, setStatus] = useState({ state: "idle" });

  const unfilled = selected.filter((c) => ANY_BRACKET.test(c.replacement));
  const inPlace = isDocx && format === "docx" && keepLayout;
  const nothingSelected = selected.length === 0 && skills.length === 0;
  const canApply = file && unfilled.length === 0 && !(inPlace && nothingSelected);

  const parts = [];
  if (selected.length) parts.push(plural(selected.length, "rewrite"));
  if (skills.length) parts.push(plural(skills.length, "skill"));
  const label = nothingSelected
    ? "Download ATS-clean version"
    : `Download updated resume (${parts.join(" + ")})`;

  async function handleApply() {
    setStatus({ state: "working" });
    try {
      const res = await applyChanges(file, selected, format, inPlace, skills);
      download(res.blob, res.filename);
      const done = [];
      if (res.applied) done.push(`${plural(res.applied, "rewrite")} applied`);
      if (res.skillsAdded) done.push(`${plural(res.skillsAdded, "skill")} added to Skills`);
      let message = done.length ? done.join(", ") + "." : "Downloaded an ATS-clean version.";
      if (res.notFound) message += ` ${res.notFound} rewrite(s) couldn't be matched in your file and were skipped.`;
      if (res.pages === 1) message += " Fits on one page.";
      const warning = res.pages > 1
        ? `This comes to ${res.pages} pages even at the smallest readable text size. ` +
          "Remove a few bullets (older or less relevant ones first) and download again."
        : null;
      setStatus({ state: "done", message, warning });
    } catch (e) {
      setStatus({ state: "error", message: e.message });
    }
  }

  return (
    <section className="card apply">
      <h2>Make changes &amp; download</h2>
      <p className="muted small">
        {nothingSelected
          ? "Nothing selected yet. Tick rewrites or skills above, or download a clean ATS-friendly version as it is."
          : `Selected: ${parts.join(" and ")}.`}
      </p>

      <div className="apply-options">
        <label>
          Format{" "}
          <select value={format} onChange={(e) => setFormat(e.target.value)}>
            <option value="docx">Word (.docx)</option>
            <option value="pdf">PDF</option>
          </select>
        </label>
        {isDocx && format === "docx" && (
          <label className="check">
            <input type="checkbox" checked={keepLayout}
                   onChange={(e) => setKeepLayout(e.target.checked)} />
            Keep my original layout
          </label>
        )}
      </div>

      <p className="muted small">
        {inPlace
          ? "Only the selected bullets and skills change; your fonts and formatting stay as they are."
          : "Rebuilt in a clean one-page ATS template (standard headings, real bullets, clickable links, no tables or icons)."}
      </p>

      {unfilled.length > 0 && (
        <p className="small hint">
          Fill in the [placeholders] in {plural(unfilled.length, "selected rewrite")} before downloading.
        </p>
      )}

      <button type="button" className="primary" disabled={!canApply || status.state === "working"}
              onClick={handleApply}>
        {status.state === "working" ? "Building…" : label}
      </button>

      {status.state === "done" && <p className="small success">{status.message}</p>}
      {status.state === "done" && status.warning && <p className="small hint">{status.warning}</p>}
      {status.state === "error" && <p className="small error">{status.message}</p>}
    </section>
  );
}
