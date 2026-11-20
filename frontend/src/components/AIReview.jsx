import { useEffect, useState } from "react";
import AILoader from "./AILoader.jsx";
import { allFilled, fill, inputType, parsePlaceholders, validate } from "../placeholders.js";

const LABELS = {
  impact: "Impact",
  clarity: "Clarity",
  technical_depth: "Technical depth",
  relevance: "Role fit",
  skills_match: "Skills match",
  experience_relevance: "Relevant experience",
  seniority_fit: "Seniority fit",
};

function tone(score10) {
  if (score10 >= 8) return "good";
  if (score10 >= 6) return "ok";
  if (score10 >= 4) return "warn";
  return "bad";
}

function PlaceholderInput({ ph, value, onChange }) {
  const [touched, setTouched] = useState(false);
  const error = validate(ph, value);
  const showError = error && (touched || (value ?? "") !== "");
  const numeric = inputType(ph) === "number";
  return (
    <label className={`ph ${showError ? "invalid" : ""}`}>
      <span className="ph-label">{ph.raw}</span>
      <span className="ph-field">
        {ph.kind === "money" && <span className="affix">{ph.symbol}</span>}
        <input
          type={numeric ? "number" : "text"}
          inputMode={ph.kind === "count" ? "numeric" : numeric ? "decimal" : "text"}
          min={numeric ? (ph.kind === "count" ? 1 : 0) : undefined}
          max={ph.kind === "percent" ? 1000 : undefined}
          step={ph.kind === "count" ? 1 : numeric ? "any" : undefined}
          maxLength={ph.kind === "text" ? 40 : undefined}
          placeholder={ph.label}
          value={value ?? ""}
          aria-invalid={Boolean(showError)}
          onBlur={() => setTouched(true)}
          onChange={(e) => onChange(e.target.value)}
        />
        {ph.kind === "percent" && <span className="affix">%</span>}
        {(ph.kind === "count" || ph.kind === "number") && ph.unit && <span className="affix">{ph.unit}</span>}
      </span>
      {showError && <span className="ph-error">{error}</span>}
    </label>
  );
}

function Rewrite({ item, edit, onChange }) {
  const [copied, setCopied] = useState(false);
  const placeholders = parsePlaceholders(edit.text);
  const complete = allFilled(edit.text, edit.values);
  const filled = fill(edit.text, edit.values);

  // A rewrite can only stay selected while every placeholder has a valid value.
  // Filling in the last one selects it automatically.
  function change(next) {
    const nowComplete = allFilled(next.text, next.values);
    const selected = nowComplete && (next.selected || (!complete && placeholders.length > 0));
    onChange({ ...next, selected });
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(filled);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked; user can select the text manually */
    }
  }

  return (
    <li className={`rewrite ${edit.selected ? "selected" : ""}`}>
      <p className="before">{item.original}</p>
      <textarea
        className={placeholders.length && !complete ? "needs-input" : ""}
        value={edit.text}
        rows={2}
        aria-label="Suggested bullet (editable)"
        onChange={(e) => change({ ...edit, text: e.target.value })}
      />

      {placeholders.length > 0 && (
        <div className="ph-box">
          <p className="small"><strong>Fill in your real numbers</strong> (required before this can be used)</p>
          <div className="ph-grid">
            {placeholders.map((ph) => (
              <PlaceholderInput key={ph.id} ph={ph} value={edit.values[ph.id]}
                onChange={(v) => change({ ...edit, values: { ...edit.values, [ph.id]: v } })} />
            ))}
          </div>
          <p className="small preview"><span className="muted">Preview:</span> {filled}</p>
        </div>
      )}

      <div className="rewrite-meta">
        <label className="check" title={complete ? "" : "Fill in every placeholder first"}>
          <input
            type="checkbox"
            checked={edit.selected}
            disabled={!complete}
            onChange={(e) => change({ ...edit, selected: e.target.checked })}
          />
          Use this
        </label>
        <span className="muted small grow">{item.reason}</span>
        <button type="button" onClick={copy} disabled={!complete}>{copied ? "Copied" : "Copy"}</button>
      </div>
    </li>
  );
}

function Rewrites({ rewrites, onSelectionChange }) {
  // Rewrites without placeholders start selected; ones with placeholders are
  // locked until every value is filled in with the right type.
  const [edits, setEdits] = useState(() =>
    rewrites.map((r) => ({ text: r.suggested, values: {},
                           selected: parsePlaceholders(r.suggested).length === 0 }))
  );
  const update = (i, next) => setEdits((all) => all.map((e, j) => (j === i ? next : e)));

  useEffect(() => {
    onSelectionChange?.(
      rewrites
        .map((r, i) => ({ original: r.original, edit: edits[i] }))
        .filter(({ edit }) => edit.selected && edit.text.trim() && allFilled(edit.text, edit.values))
        .map(({ original, edit }) => ({ original, replacement: fill(edit.text, edit.values).trim() }))
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edits, rewrites]);

  return (
    <>
      <h3>Suggested bullet rewrites</h3>
      <p className="muted small">
        Checked so they don't add numbers or skills that aren't already in your resume.
        Edit any suggestion and tick the ones you want; download below.
      </p>
      <ul className="rewrites">
        {rewrites.map((r, i) => (
          <Rewrite key={i} item={r} edit={edits[i]} onChange={(next) => update(i, next)} />
        ))}
      </ul>
    </>
  );
}

export default function AIReview({ state, onRetry, onSelectionChange, title = "AI review", improveLabel = "Improve" }) {
  if (state.status === "idle") return null;

  if (state.status === "loading") {
    return (
      <section className="card">
        <h2>{title}</h2>
        <AILoader />
      </section>
    );
  }

  if (state.status === "error") {
    return (
      <section className="card">
        <h2>{title}</h2>
        <p className={state.disabled ? "muted" : "error"}>{state.message}</p>
        {!state.disabled && (
          <button type="button" className="primary" onClick={onRetry}>Try again</button>
        )}
      </section>
    );
  }

  const { score, rubric, strengths, improvements, rewrites, target_role, model } = state.data;
  return (
    <section className="card ai">
      <div className="ai-head">
        <h2>{title}{target_role ? ` · ${target_role}` : ""}</h2>
        <span className="ai-meta">
          {model && <span className="muted small">{model}</span>}
          {score != null && <span className="pill">{score}/100</span>}
        </span>
      </div>

      <div className="rubric">
        {rubric.map((c) => (
          <div key={c.criterion} className="category">
            <div className="category-row">
              <span>{LABELS[c.criterion] ?? c.criterion}</span>
              <span>{c.score}/10</span>
            </div>
            <div className="bar">
              <div className={`fill ${tone(c.score)}`} style={{ width: `${c.score * 10}%` }} />
            </div>
            <p className="muted small">{c.reason}</p>
          </div>
        ))}
      </div>

      <div className="two-col">
        <div>
          <h3>Strengths</h3>
          <ul>{strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
        </div>
        <div>
          <h3>{improveLabel}</h3>
          <ul>{improvements.map((s, i) => <li key={i}>{s}</li>)}</ul>
        </div>
      </div>

      {rewrites.length > 0 && <Rewrites rewrites={rewrites} onSelectionChange={onSelectionChange} />}
    </section>
  );
}
