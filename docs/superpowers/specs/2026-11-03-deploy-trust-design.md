# Deploy PropTalk with visible trust — design

**Date:** 2026-11-03 · **Deadline:** 2 hours from plan approval

## Intent
A reviewer opens a public Streamlit Community Cloud link cold, the morning after, and the first
click works. The impression to leave: *this person ships reliable tools people can trust.*
Depth over breadth: a smaller feature set that cannot fail beats a bigger one.

## Goals
1. Deployed, and verified against the live URL, not localhost.
2. Example questions work even if the LLM key is missing or its quota is exhausted.
3. Every answer shows how it was produced, using only data the pipeline already returns.
4. A restrained, non-generic look, picked by the owner from 2–3 static mockups.

## Non-goals
- New query features, new datasets, new eval runs.
- Installing cult-ui into the app. It is React/shadcn/Tailwind v4/Motion (per its README) and
  Streamlit cannot host it without a custom-component build. It is a visual reference and a
  mockup tool only.

## Anti-goals (failure even if it "works")
- The link errors or hangs at first open.
- A number in the UI that does not come from `results/metrics.json`.
- Cached output passed off as a live answer.
- Animated chrome that makes a trust tool look like a template.
- Any employer or institution reference in the repo (CLAUDE.md).

## Approaches considered
| | Approach | Trade-off | Verdict |
|---|---|---|---|
| A | Deploy as-is plus a big new feature | Most "wow"; highest chance of a broken 8am link | Rejected |
| B | Reliability first (data bootstrap, cached example answers, per-session cap, plain errors), then a trust panel and theme | Less flashy; every addition supports the "trust" message | **Chosen** |
| C | Rebuild the front end in Next.js with cult-ui | Real cult-ui; leaves Streamlit Cloud and won't fit in 2 hours | Rejected |

## Decided
- Cached example answers store the **model's output only**. The SQL or pandas code still goes
  through the guard and the engine live, and the UI labels the result "saved model output, executed live".
- Streamlit Cloud root-level secrets are also exposed as environment variables (Streamlit docs,
  secrets-management page), so `os.getenv("LLM_API_KEY")` needs no change.
- The pandas executor is at `EXEC_CONTRACT = 3`; the v2 eval measured contract 2. The trust panel
  must say so rather than imply the number applies unchanged.
- The owner deploys (Streamlit account); Claude does not.
- Live LLM calls only with the owner's go-ahead (CLAUDE.md: rate-limited API).

## Left to the builder
Exact copy, colors and layout within the chosen mockup; the per-session cap value (default 8).
