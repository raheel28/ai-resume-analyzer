function tone(score) {
  if (score >= 75) return "good";
  if (score >= 55) return "ok";
  if (score >= 35) return "warn";
  return "bad";
}

function SkillRow({ row, checked, onToggle }) {
  return (
    <li className={`skill ${row.found ? "found" : "missing"}`}>
      <span className="mark" aria-hidden="true">{row.found ? "✓" : "✗"}</span>
      <span className="skill-name">{row.skill}</span>
      <span className={`tag ${row.importance}`}>{row.importance === "required" ? "Required" : "Nice to have"}</span>
      {!row.found && onToggle && (
        <label className="check add-skill">
          <input type="checkbox" checked={checked} onChange={(e) => onToggle(row.skill, e.target.checked)} />
          I have this, add to Skills
        </label>
      )}
    </li>
  );
}

/**
 * Overall match score + keyword table. Missing skills can be ticked to be
 * added to the resume's Skills section on download.
 */
export default function MatchSummary({ match, ai, addSkills, onToggleSkill }) {
  const keyword = match.score;
  const aiScore = ai.status === "done" ? ai.data.score : null;
  // Overall: keyword coverage is stable and ATS-like; the AI score adds judgement
  // about experience and seniority. Weighted 60/40 when both exist.
  const overall = keyword != null && aiScore != null
    ? Math.round(0.6 * keyword + 0.4 * aiScore)
    : keyword ?? aiScore;

  const extra = ai.status === "done" ? ai.data.other_requirements ?? [] : [];
  const missingCount = match.skills.filter((s) => !s.found).length;

  return (
    <section className="card">
      <div className="summary">
        <div className={`score ${overall != null ? tone(overall) : ""}`}>
          <span className="score-number">{overall ?? "–"}</span>
          <span className="score-label">match</span>
        </div>
        <div className="categories">
          <p className="muted small">{match.file.name} vs job description</p>
          <div className="category">
            <div className="category-row">
              <span>Keyword match</span><span>{keyword ?? "n/a"}</span>
            </div>
            <div className="bar"><div className={`fill ${tone(keyword ?? 0)}`} style={{ width: `${keyword ?? 0}%` }} /></div>
          </div>
          <div className="category">
            <div className="category-row">
              <span>AI fit</span>
              <span>{aiScore ?? (ai.status === "loading" ? "…" : "n/a")}</span>
            </div>
            <div className="bar"><div className={`fill ${tone(aiScore ?? 0)}`} style={{ width: `${aiScore ?? 0}%` }} /></div>
          </div>
          <p className="small">
            <strong>{match.required_found} of {match.required_total}</strong> required skills found
          </p>
        </div>
      </div>

      {match.note && <p className="muted small">{match.note}</p>}

      {match.skills.length > 0 && (
        <>
          <h3>Skills in the job description</h3>
          {missingCount > 0 && (
            <p className="muted small">
              Only tick a missing skill if you really have it. It will be added to your Skills section when you download.
            </p>
          )}
          <ul className="skills">
            {match.skills.map((row) => (
              <SkillRow key={row.skill} row={row} checked={addSkills.includes(row.skill)}
                        onToggle={onToggleSkill} />
            ))}
          </ul>
        </>
      )}

      {extra.length > 0 && (
        <>
          <h3>Other requirements the AI spotted</h3>
          <ul className="skills">
            {extra.map((row) => <SkillRow key={row.skill} row={row} />)}
          </ul>
        </>
      )}
    </section>
  );
}
