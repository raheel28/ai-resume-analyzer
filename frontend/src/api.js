const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export async function analyzeResume(file) {
  const body = new FormData();
  body.append("file", file);

  const res = await fetch(`${API_BASE}/api/analyze`, { method: "POST", body });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function aiReview(file, targetRole) {
  const body = new FormData();
  body.append("file", file);
  body.append("target_role", targetRole ?? "");

  const res = await fetch(`${API_BASE}/api/ai-review`, { method: "POST", body });
  if (!res.ok) {
    let detail = `AI review failed (${res.status})`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export async function applyChanges(file, changes, format, keepLayout, addSkills = []) {
  const body = new FormData();
  body.append("file", file);
  body.append("changes", JSON.stringify(changes));
  body.append("add_skills", JSON.stringify(addSkills));
  body.append("format", format);
  body.append("keep_layout", keepLayout ? "true" : "false");

  const res = await fetch(`${API_BASE}/api/apply`, { method: "POST", body });
  if (!res.ok) {
    let detail = `Couldn't apply changes (${res.status})`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `resume_updated.${format}`;
  return {
    blob: await res.blob(),
    filename,
    applied: Number(res.headers.get("X-Applied-Count") ?? changes.length),
    notFound: Number(res.headers.get("X-Not-Found-Count") ?? 0),
    skillsAdded: Number(res.headers.get("X-Skills-Added") ?? 0),
    pages: res.headers.get("X-Pages") ? Number(res.headers.get("X-Pages")) : null,
  };
}

function jdForm(file, jd) {
  const body = new FormData();
  body.append("file", file);
  if (jd.file) body.append("jd_file", jd.file);
  else body.append("jd_text", jd.text ?? "");
  return body;
}

async function postJson(path, body, fallback) {
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", body });
  if (!res.ok) {
    let detail = `${fallback} (${res.status})`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const matchResume = (file, jd) => postJson("/api/match", jdForm(file, jd), "Match failed");
export const aiMatch = (file, jd) => postJson("/api/ai-match", jdForm(file, jd), "AI match review failed");

/** Ping the API. Free hosting sleeps when idle, so the first call can take ~1 minute. */
export async function health(timeoutMs = 90000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}/api/health`, { signal: ctrl.signal });
    if (!res.ok) throw new Error(`Health check failed (${res.status})`);
    return res.json();
  } finally {
    clearTimeout(timer);
  }
}
