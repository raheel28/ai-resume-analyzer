# AI Resume Analyzer

Two modes, both ending in **make changes → download the updated resume**:

1. **Resume check:** ATS-readiness score with specific fixes, plus an AI review with
   rewrites of your weakest bullets.
2. **Match to a job:** paste a job description or upload it as a file. You get a keyword
   match score (which required and nice-to-have skills you show or are missing), an AI fit
   review, rewrites tailored to the job, and tick boxes to add missing skills you really have.

## Status

| Milestone | What | Status |
|---|---|---|
| 1 | Parse PDF/DOCX, rule-based ATS check, upload UI | ✅ done |
| 2 | AI review: rubric rating, strengths/improvements, guarded bullet rewrites | ✅ done |
| 3 | Apply selected edits + download (DOCX in place, or rebuilt ATS DOCX/PDF) | ✅ done |
| 4 | Job description match: keyword score, AI fit review, tailored rewrites, add missing skills | ✅ done |
| 5 | Evals (guard + keyword matcher), usage metrics, CI, deploy config, one-page export with links | ✅ done |
| 6 | Semantic (embedding) skill matching; more eval data from real resumes | next |
| 6 | Deploy (backend: Render/Railway, frontend: Vercel) | |

## Run it

Backend (Python 3.11+):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add GEMINI_API_KEY to enable the AI review
uvicorn app.main:app --reload # http://localhost:8000/docs
pytest                        # 57 tests incl. eval thresholds, no API key needed (AI tests use a fake client)
```

Frontend:

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173, proxies /api to :8000
```

## How scoring works

The ATS score uses only rules, with no LLM, so the same file always gets the same score.
There are 15 weighted checks in three groups:

- **Parseability:** Is the text extractable (not a scanned image)? Are there tables,
  multiple columns, images, contact details in the header/footer, or icon-font characters?
- **Structure:** Contact details, standard sections (Experience/Projects, Education, Skills),
  recognisable headings, length, and consistent dates.
- **Content:** Do bullets start with action verbs? Are results quantified? Are bullets
  short? Are first-person pronouns avoided?

Each check returns a 0–1 score and a weight. The overall score is the weighted mean.
Issues are sorted by severity, then by weight.

## How the AI review works

`POST /api/ai-review` (file + optional `target_role`) makes a single Gemini call with a
Pydantic response schema. It returns:

- **Rubric:** impact, clarity, technical depth and role fit, each scored 1–10 with a
  reason. Scores are clamped to that range, and the average ×10 gives the AI score.
- **Strengths and improvements:** 3 and 4 points, specific to the resume.
- **Rewrites of the weakest bullets.** Before they reach the user, `ai/guard.py` rejects any
  rewrite that:
  - adds a number that isn't in the original bullet (`[X%]` placeholders are allowed and
    flagged for the user to fill in),
  - adds a tool or name that appears nowhere in the resume, or
  - quotes an "original" bullet that isn't actually in the resume.

The resume goes into the prompt inside `<resume>` tags as untrusted content. Any prompt
injection in the file can only affect the AI section, because the ATS score is rule-based.
The frontend calls `/api/analyze` and `/api/ai-review` at the same time, so the ATS score
appears instantly and the AI review fills in a few seconds later. Without an API key the
endpoint returns 503 and the UI says the AI review is off.

To switch providers, add a class with `generate(system, prompt, Schema)` in
`llm/client.py`.

## Results (measured)

### Guard against invented facts: `python -m evals.run_guard`

There are 74 hand-labelled AI-style rewrites of one sample resume. Each is labelled
**accept** (honest rewording) or **reject** (invents a number, tool, scale, leadership
claim, award or employer).

| | Dev set (50 cases in round 1; 61 now) | Held-out set (24, never tuned on) |
|---|---|---|
| Invented facts caught, before | 50% (14/28) | 29% (4/14) |
| Invented facts caught, **after** | 100% (28/28) | **100% (14/14)** |
| Honest rewrites wrongly blocked, after | 0% (0/22) | **10% (1/10)** |

The first version only caught capitalised terms and digits. The eval showed it missed:
- lowercase tech ("kubernetes")
- spelled-out quantities ("doubled", "three times")
- scale claims ("millions of customers")
- invented leadership ("Led a team…")
- invented awards

**Round 2 (found on the live site).** Testing the deployed app with real Gemini output
showed two more ways a rewrite could exaggerate:
- dropping a qualifier: "by *about* 15%" became "by 15%", and "20+" became "20"
- vague scale words: "high-volume", "large-scale", "at scale"

I added those live outputs, plus similar cases and honest counterparts, to the dev set
(now 61 cases). Before the fix it caught 80% (28/35); after, 100% (35/35), with 0 of 26
honest rewrites blocked. The held-out set didn't change (still 14/14 caught, 1/10 wrongly
blocked), so the fix didn't break anything there.

The held-out set was written **before** the fixes, to check they generalise. Its
remaining error is "algorithms" being read as a skill claim. It is left unfixed on
purpose, so the held-out number stays honest. Full output is in `evals/results/`.

Limits: this is a small set built around one resume, all written by the author. Treat it
as a regression test, not a benchmark.

### Job description keyword extraction: `python -m evals.run_keywords`

There are 12 hand-labelled job ads (76 skills), including traps like "Go to our careers
site" and "the rest of the process". It was measured once, with no tuning on this set.

| Precision | Recall | Required vs nice-to-have |
|---|---|---|
| 96% | 97% | 96% |

Known errors:
- `Next.js` / `Express.js` also count as JavaScript.
- "ML Engineer" is read as Machine learning, which is arguably right.
- "Swift" alone, with no iOS context nearby, is missed.
- "desirable" / "is good to have" in the middle of a sentence isn't treated as nice-to-have.

### Real usage: `python -m evals.usage_report`

Every AI call appends one line to `backend/data/metrics.jsonl` with:
- latency, which model answered, retries and fallbacks, provider error codes
- how many rewrites the guard rejected, and why

It **never stores resume or job description text**. The report shows success rate,
median/p90 latency, fallback rate and guard rejection rate on real model output.

## Deploy

- **Abuse protection:** per-IP rate limits (`AI_RATE_LIMIT`, default 10 AI reviews/hour;
  `BASIC_RATE_LIMIT`, 60 requests/minute) return 429 with a friendly "try again in…"
  message. Set `TRUST_PROXY=1` behind Render/Railway so limits use the visitor's real IP.
  Uploads are capped at 5 MB (resume) and 2 MB (job description).
- **Cold starts:** if the API takes more than 2.5s to answer (a free Render instance
  waking up), the page shows a "Waking up the server…" banner with a timer.
- **One service (Render):** the root `Dockerfile` builds the React site, then runs
  FastAPI, which serves the API at `/api/...` and the site at `/`. That means one URL, no
  CORS setup and one deploy. `render.yaml` is a Blueprint for it: on Render choose
  **New → Blueprint**, pick the repo, and paste `GEMINI_API_KEY` when asked. Every push to
  `main` redeploys. The free plan sleeps after 15 idle minutes (about a minute to wake);
  the Starter plan stays awake. Render's free disk is wiped on redeploys, so download
  `data/metrics.jsonl` first if you want to keep it.
- *(Optional split deploy: `backend/Dockerfile` for the API only, plus `frontend/` on
  Vercel with `VITE_API_BASE` set to the API URL and `CORS_ORIGINS` set on the API.)*
- **CI:** `.github/workflows/ci.yml` runs the tests (including the eval thresholds, which
  fail the build if guard recall or keyword precision/recall drop), builds the frontend,
  and builds and smoke-tests the single-service Docker image that Render deploys.

## Exports

- The rebuilt resume (PDF or DOCX) is fitted to **one page**. It starts at a comfortable
  10.5pt and steps down to an 8.5pt minimum. If it still doesn't fit, the app says how many
  pages it is instead of silently cutting content.
- **Links are kept:** link targets from the original file (e.g. the word "GitHub" →
  github.com/you) come back clickable, and bare emails and `linkedin.com/...` /
  `github.com/...` text become clickable too.

## Job description match

- `POST /api/match` (resume + `jd_text` or `jd_file`) gives a keyword score that comes out
  the same every time. `jd/lexicon.py` lists about 90 skills with their aliases ("JS" →
  JavaScript, "k8s" → Kubernetes), and patterns that avoid false hits like "Go to our
  website" or "the rest of the team". Skills that appear only after "nice to have" /
  "preferred" / "bonus" count as nice-to-have. Required skills count double in the score.
- `POST /api/ai-match` gives an AI fit rubric (skills match, relevant experience, seniority,
  impact), strengths, gaps, other requirements the keyword list missed, and rewrites tailored
  to the job. The same guard applies, so a rewrite can't slip in a skill from the job ad that
  you don't have.
- The overall match score is 60% keywords + 40% AI fit.

## Applying changes

Each AI rewrite can be edited and ticked. Rewrites with `[X]` placeholders start unticked,
and the server refuses them until the placeholders are filled. `POST /api/apply` (file +
JSON list of `{original, replacement}` + `format` + `keep_layout`) returns the updated file
as a download:

- **DOCX upload, "keep my layout":** only the matching paragraphs in your own file change,
  so fonts, spacing and list styles stay the same.
- **Anything else** (PDF uploads, or a PDF download): the extracted text, with your changes,
  is rebuilt into a single-column template with standard headings and real bullets. The PDF
  embeds its font. With reportlab's default Helvetica, `•` turns into `(cid:127)` when an ATS
  reads it, which is the problem the checker warns about.

PDF text comes out one visual line at a time, so bullets that wrap onto a second line are
joined back together (`merge_wrapped_bullets`) before matching and rebuilding.

## Layout

```
backend/app/
  main.py              FastAPI routes (/api/health, /api/analyze)
  parsing/extract.py   PDF/DOCX -> text + layout signals (tables, columns, images, header text)
  parsing/sections.py  heading detection -> sections
  ats/checks.py        individual checks
  ats/score.py         weighting, grade, issue ordering
  ai/review.py         general review prompt, rubric scoring, rewrite filtering
  ai/match_review.py   resume-vs-JD review prompt
  jd/lexicon.py        skill names + alias patterns
  jd/match.py          JD reading (text/pdf/docx/txt), required vs nice, keyword score
  ai/guard.py          rejects rewrites with invented numbers/skills
  ai/schemas.py        Pydantic schemas the model must return
  edit/apply.py        validate changes, edit DOCX in place, apply to extracted lines
  edit/render.py       rebuild as clean ATS DOCX / PDF
  metrics.py           privacy-safe per-request usage log
  ratelimit.py         per-IP sliding-window limits (no extra dependencies)
  llm/client.py        provider-agnostic LLM wrapper (Gemini + FakeClient for tests)
backend/tests/         sample resumes are generated in code, no binary fixtures
backend/evals/         labelled datasets, eval runners, saved results, usage report
frontend/src/          React + Vite: CheckMode, MatchMode (JDInput, MatchSummary), AIReview, ApplyPanel
```

## Known limits

- Multi-column PDF detection is a heuristic based on gaps between words. Right-aligned
  dates can cause false positives on short pages.
- An unknown heading in ALL CAPS is treated as a section heading, so an all-caps job title
  can be flagged as a non-standard heading. This is only a tip, so it barely affects the score.
- The guard is conservative. It can reject a good rewrite that uses a common capitalised word
  missing from the resume. The rejected rewrites are returned in `rejected_rewrites` so you can tune it.
- The page count for a DOCX isn't known without rendering it, so only the word count is checked.
