# Phase 3 — Retrieval at Scale (Conditional)

**Status:** Conditional — do not start until the Phase 2 experiment passes  
**Depends on:** [Phase 2 — Composition + experiment](workflow_scriber_phase2_composition_plan.md)  
**Produces:** a lexical workflow index and retrieval API, only if scale demands it  
**May be cancelled:** if the library stays small or scribble cards fit in context

---

## 1. Goal

When the scribble library no longer fits in the agent's context, return a small,
ranked set of workflow cards for a natural-language request:

- goal and description;
- parameters and types;
- requires/provides;
- step intents and tools;
- status, confidence, and path to the full workflow.

The index is derived data. The scribbles/workflow JSON remains the source of
truth.

---

## 2. Why this is deferred

Composition is the north star. Retrieval is a scale fix, not a capability fix.

- During the Phase 2 experiment, the library is deliberately small so retrieval
  cannot confound the result.
- Building FTS5 before there is a demonstrated need would add infrastructure
  without testing the hypothesis.
- If the experiment fails, indexing would make a failed memory layer faster to
  search. That is not progress.

### 2.1 Triggers

Start only when **all** are true:

1. Phase 2 shows a measurable benefit for C or D.
2. There are more than ~30 scribbles, or the scribble bundle exceeds
   the context budget.
3. Brute-force lookup adds more than ~1 s or cannot fit the request context.
4. The user can name workflows faster than the agent can find them.

If none hold, cancel the phase.

---

## 3. Source of truth and freshness

- Library: `workflow_scriber/library/<recording_id>/workflows/*.json` and
  `scribbles.json`.
- Index: `workflow_scriber/library/index.db` (gitignored).
- Each row stores the file path and a content checksum.
- On query, check freshness cheaply; update affected rows or rebuild.
- Deleting/deprecating a workflow removes or masks its rows.
- Never hand-edit the index; always rebuild from the library.

---

## 4. Index schema

SQLite with FTS5, WAL mode.

```sql
CREATE TABLE workflows (
  workflow_id   TEXT PRIMARY KEY,
  recording_id  TEXT NOT NULL,
  kind          TEXT NOT NULL,          -- standalone | fragment
  title         TEXT NOT NULL,
  description   TEXT NOT NULL,
  apps          TEXT NOT NULL,          -- JSON array
  tags          TEXT NOT NULL,          -- JSON array
  parameters    TEXT NOT NULL,          -- JSON array
  requires      TEXT NOT NULL,          -- JSON array
  effects       TEXT NOT NULL,          -- JSON array
  confidence    REAL NOT NULL,
  path          TEXT NOT NULL,
  checksum      TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE TABLE steps (
  workflow_id  TEXT NOT NULL,
  step_id      TEXT NOT NULL,
  position     INTEGER NOT NULL,
  intent       TEXT NOT NULL,
  tool         TEXT NOT NULL,
  PRIMARY KEY (workflow_id, step_id)
);

CREATE VIRTUAL TABLE workflows_fts USING fts5(
  workflow_id UNINDEXED, title, description, apps, tags,
  tokenize = 'unicode61'
);

CREATE VIRTUAL TABLE steps_fts USING fts5(
  workflow_id UNINDEXED, step_id UNINDEXED, intent, tool,
  tokenize = 'unicode61'
);
```

Selectors and full arguments stay out; they are loaded from the workflow JSON on
use.

---

## 5. Query pipeline

```
request
  │
  ▼
normalize       lowercase, app/verb synonyms, preserve paths and quoted terms
  │
  ▼
lexical         FTS5 BM25 over workflows_fts + steps_fts
  │
  ▼
structured      filter/boost by app, kind, confidence, satisfiable requires
  │
  ▼
rank            combine scores; fragments are valid only with prerequisites
  │
  ▼
cards           top-k (default 5–8), ≤ ~2k tokens
  │
  ▼
composer
```

Rules:

- A `fragment` can be returned, but the card must show its preconditions.
- Unknown interfaces are shown as unknown; retrieval does not fill them.
- Scribbles whose descriptions the user has not accepted are excluded by default.
- If nothing relevant is found, return `none`; do not pad results.

---

## 6. Evaluation

30 natural-language requests written by someone who did not author the index:

- exact title words;
- description words but no title words;
- app-only requests;
- multi-step requests;
- paraphrases;
- near-misses that should return `none`.

| Metric | Target |
|---|---|
| Recall@5 | ≥ 0.90 |
| MRR | ≥ 0.70 |
| Scribble bundle | ≤ 2k tokens |
| Query latency p95 | ≤ 150 ms |
| False positive for `none` | 0 |
| Stale detection | 100 % |

Baseline: brute-force lexical matching over the workflow files. If FTS5 does not
beat it, keep the baseline. Embeddings are considered only if lexical retrieval
misses the gate after synonym and step indexing; then use a local model, store
the model id, and measure the gain.

---

## 7. Failure modes and mitigations

| Failure | Mitigation |
|---|---|
| Vocabulary gap (“directory” vs “folder”) | synonym table + step intents + evaluation set |
| Fragment returned without prerequisites | card shows preconditions; composer refuses |
| Stale index | checksum check; incremental update; rebuild |
| Over-broad query matches everything | require app/object term; return `none` |
| Sensitive text indexed | redact at write; index stored fields only |
| Index becomes a second source of truth | derived-only rule; rebuild command |
| Retrieval masks bad scribbles | Phase 2 gate is checked first |

---

## 8. Milestones

| Milestone | Deliverable |
|---|---|
| **M0 — Baseline** | brute-force search + 30-query set |
| **M1 — Schema + builder** | SQLite/FTS5 build, checksums, rebuild |
| **M2 — Query + cards** | normalization, BM25, structured filters, token budget |
| **M3 — Freshness + fallback** | incremental update, stale detection, brute-force fallback |
| **M4 — Evaluation** | recall/MRR/latency report; embeddings decision |

Phase 3 is complete when retrieval improves context gathering at scale without
changing the underlying workflow contracts.

---

## 9. Open questions

1. Should steps be a separate FTS table? Proposed: yes, for multi-intent queries.
2. Index parameter names? Proposed: lightly; users name values.
3. Where do synonyms live? Proposed: `library/synonyms.json`, reviewed like code.
4. What is the real trigger threshold? Proposed: measure at 30 scribbles; adjust
   from the context budget, not from intuition.
5. If scribble cards fit for the foreseeable library, is this phase deleted?
   Proposed: yes; keep the plan archived, not implemented.
