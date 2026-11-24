import { useRef } from "react";

export default function JDInput({ value, onChange, disabled }) {
  const input = useRef(null);
  const mode = value.mode;

  return (
    <section className="card jd">
      <div className="jd-head">
        <h2>Job description</h2>
        <div className="seg" role="tablist" aria-label="How to add the job description">
          <button type="button" role="tab" aria-selected={mode === "text"}
                  className={mode === "text" ? "on" : ""}
                  onClick={() => onChange({ ...value, mode: "text" })}>Paste text</button>
          <button type="button" role="tab" aria-selected={mode === "file"}
                  className={mode === "file" ? "on" : ""}
                  onClick={() => onChange({ ...value, mode: "file" })}>Upload file</button>
        </div>
      </div>

      {mode === "text" ? (
        <>
          <textarea
            className="jd-text"
            rows={9}
            maxLength={20000}
            disabled={disabled}
            placeholder="Paste the full job posting: responsibilities, requirements, nice-to-haves…"
            value={value.text}
            onChange={(e) => onChange({ ...value, text: e.target.value })}
          />
          <p className="muted small">{value.text.trim().length.toLocaleString()} characters</p>
        </>
      ) : (
        <div className="jd-file">
          <input ref={input} type="file" accept=".pdf,.docx,.txt,.md" hidden
                 onChange={(e) => {
                   const f = e.target.files?.[0];
                   if (f) onChange({ ...value, file: f });
                   e.target.value = "";
                 }} />
          <button type="button" disabled={disabled} onClick={() => input.current?.click()}>
            {value.file ? "Choose a different file" : "Choose file"}
          </button>
          <span className={value.file ? "" : "muted"}>
            {value.file ? value.file.name : "PDF, DOCX or TXT, max 2 MB"}
          </span>
          {value.file && (
            <button type="button" className="link" onClick={() => onChange({ ...value, file: null })}>
              Remove
            </button>
          )}
        </div>
      )}
    </section>
  );
}

export function jdReady(jd) {
  return jd.mode === "text" ? jd.text.trim().length >= 80 : Boolean(jd.file);
}

export function jdPayload(jd) {
  return jd.mode === "text" ? { text: jd.text } : { file: jd.file };
}
