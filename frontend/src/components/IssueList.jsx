const LABELS = { critical: "Fix first", warning: "Improve", tip: "Tip" };

export default function IssueList({ issues }) {
  if (!issues.length) {
    return <section className="card"><h2>No issues found</h2></section>;
  }
  return (
    <section className="card">
      <h2>What to fix</h2>
      <ul className="issues">
        {issues.map((issue) => (
          <li key={issue.id} className={`issue ${issue.severity}`}>
            <span className="badge">{LABELS[issue.severity]}</span>
            <div>
              <strong>{issue.title}</strong>
              <p>{issue.message}</p>
              {issue.details.length > 0 && (
                <details>
                  <summary className="muted small">Show examples</summary>
                  <ul className="examples">
                    {issue.details.map((d, i) => <li key={i}>{d}</li>)}
                  </ul>
                </details>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
