function tone(score) {
  if (score >= 85) return "good";
  if (score >= 70) return "ok";
  if (score >= 50) return "warn";
  return "bad";
}

export default function ScoreSummary({ report }) {
  const { score, grade, categories, file } = report;
  return (
    <section className="card summary">
      <div className={`score ${tone(score)}`}>
        <span className="score-number">{score}</span>
        <span className="score-label">{grade}</span>
      </div>
      <div className="categories">
        <p className="muted small">
          {file.name} · {file.words} words{file.pages ? ` · ${file.pages} page(s)` : ""}
        </p>
        {categories.map((c) => (
          <div key={c.id} className="category">
            <div className="category-row">
              <span>{c.label}</span>
              <span>{c.score}</span>
            </div>
            <div className="bar">
              <div className={`fill ${tone(c.score)}`} style={{ width: `${c.score}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
