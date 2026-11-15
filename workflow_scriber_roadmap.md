# Workflow Scriber — Roadmap (Research Capability Layer)

**Status:** Planning  
**Phase 0:** ✅ Complete — [record + replay](workflow_scriber_phase0_plan.md)  
**Core question:** Does scribble memory improve `gui_agent`'s context gathering, planning efficiency, speed, and accuracy on new tasks?  
**Next:** [Phase 1 — Extraction](workflow_scriber_phase1_scribbles_plan.md) → [Phase 2 — Composition + experiment](workflow_scriber_phase2_composition_plan.md) → [Phase 3 — Retrieval at scale](workflow_scriber_phase3_indexing_plan.md) (conditional)

---

## 0. Phase numbering

The old v2 plan is archived at `docs/archive/workflow_scriber_plan.v2.md`. Its
numbering no longer applies from Phase 1 onward:

| Old v2 phase | New home |
|---|---|
| Phase 0 — Resolve | Phase 0 (delivered differently; see the Phase 0 plan) |
| Phase 1 — Capture | Folded into Phase 0 |
| Phase 2 — Segment | Phase 1, deterministic preprocessing |
| Phase 3 — Map | Phase 1, one-shot extraction |
| Phase 4 — Name (LLM) | Phase 1, action annotations + scribbles |
| Phase 5 — Merge | Phase 2, composition; Phase 3, retrieval |

The new sequence is:

| Phase | Output | Question it answers |
|---|---|---|
| **0 — Record + replay** | raw flow JSON, pruned replay | Can we reproduce one recorded run? |
| **1 — Extract** | action annotations + N scribbles | Can one recording become useful, mechanically valid memory? |
| **2 — Compose + evaluate** | composed plans, experiment report | Does that memory make the agent better on new tasks? |
| **3 — Retrieve at scale** | searchable library | Can the agent find the right memory as the library grows? |

Phase 3 is **conditional**. It does not start until Phase 2 shows a measurable
benefit and the library/context actually becomes the bottleneck.

---

## 1. Where we are

Phase 0 delivers a clean transcript:

- `watch` maps human clicks/keys/scrolls to `gui_agent` tool calls, with selector
  candidates and element/window metadata.
- `replay` calls the real tools, keeps the first candidate that succeeds, and
  writes a pruned `.replayed.json`.
- `watch --events` is an opt-in WinEvent probe.

Known limits carried forward:

- Recorded elements can come from occluded windows; replay sometimes succeeds
  only because the background rect overlaps the intended foreground control.
- `press_key` has no focus guard; keystrokes are recorded one by one.
- There is no post-action state capture, so the transcript alone often cannot
  prove what an action changed.
- Every recording is one sample; it encodes incidental context as if it were
  part of the task.

[Phase 0 plan](workflow_scriber_phase0_plan.md) §6 has the full list. Phase 1's
recording enrichment exists to fix the last three limits.

---

## 2. The research bet

The product bet is not "build a workflow library." It is a testable claim:

> Giving the agent a compact, evidence-backed description of previously
> recorded actions, plus executable subsets, improves its ability to gather
> context and reason about a new task.

Three hypotheses:

| ID | Hypothesis |
|---|---|
| **H1** | Scribble descriptions and annotations improve context gathering and reasoning versus no memory or raw transcripts. |
| **H2** | Executable scribbles plus composition improve speed and accuracy versus scribble descriptions alone. |
| **H3** | Composition solves held-out tasks that no single recording covers. |

The north star is **composition**. Repeat execution is the baseline capability,
not the end state.

### Kill criterion

If the treatment conditions do not beat the baselines on success, context size,
or efficiency, stop. Do not build indexing, a review bureaucracy, or a richer
schema to rescue a hypothesis that failed. The experiment in Phase 2 is designed
to fail cheaply.

---

## 3. Artifact model

One recording does **not** produce one canonical workflow. It produces a bundle:

```
raw flow (immutable, full replay)
      │
      │ one-shot LLM, fixed template
      ▼
scribbles.json
  ├── action annotations       what each action did: observed, purpose
  └── scribbles                N subsets of the recording, each with title,
                               description, steps, parameters
      │
      ├── workflows/<id>.json  each scribble, replayable on its own
      └── full flow remains replayable (N + 1)
```

### 3.1 Two layers, linked by action ids

| Layer | Purpose | Consumer |
|---|---|---|
| **Annotations + scribble descriptions** | Semantic memory: what happened and what it was for | Agent reasoning, composition, retrieval |
| **Scribble workflow file** | Executable memory: the recorded tool calls and selector ladders | Replay, deterministic executor |
| **Raw flow** | Ground truth and fallback replay | Validator, human inspection, executor |

The description is not a second copy of the tool calls. It is what the agent
reads and what Phase 3 indexes. The workflow file is what the executor runs.
Both cite raw action ids, so every claim is traceable.

### 3.2 Every scribble is individually replayable

The LLM picks recorded action ids and code copies those actions into a
raw-flow-format file. A scribble that drops setup actions fails replay; that
is the signal to keep them, not a separate scribble class.

### 3.3 Multiple interpretations are allowed

One recording can yield several overlapping scribbles ("open and navigate",
"create and name", "close and clean up"). The full flow stays as the faithful
replay. Conflicts are not resolved by picking one canonical interpretation; they
are exposed as alternatives, each citing the recorded actions it uses.

---

## 4. Shared contracts

| Artifact | Produced by | Consumed by | Key fields |
|---|---|---|---|
| Raw flow `.json` | Phase 0 | Phase 1 | actions, tool, args, selectors, element, window, point |
| Scribbles file `scribbles.json` | Phase 1 | Phase 2, Phase 3 | action annotations, scribble descriptions, provenance |
| Scribble workflow `.json` | Phase 1 | replay, Phase 2 executor | raw-flow format: recorded actions with `source_n` |
| Plan `.json` | Phase 2 | executor | ordered concrete calls, bindings, checks |
| Index | Phase 3 | Phase 2 retrieval | workflow/step records, interfaces, lexical keys |

Detailed schemas live in each phase plan.

---

## 5. Invariants

1. **No invented executable facts.** Tools, selectors, and arguments come from
   the recording or a validated bridge. Annotations cite recorded actions and
   leave the purpose empty when the transcript does not show it.
2. **Every action is annotated.** Actions that do not belong to a scribble are
   simply left out of it.
3. **Raw recordings are immutable.** Scribble files are overlays with
   provenance.
4. **Identity before coordinates.** Selectors carry foreground/window identity.
   Points are evidence, not the contract.
5. **One-shot extraction.** Scribble extraction is one structured template
   fill, not an agent tool-call loop. Deterministic parsing and validation
   follow.
6. **Replay is mechanical validation, not semantic truth.** Replay proves tool
   resolution and execution. Semantic quality is decided by the Phase 2
   experiment and, for destructive steps, by execution gating.
7. **No per-step LLM on the happy path.** Composition is planned once;
   execution is deterministic.
8. **Destructive actions are gated at execution.** Close/delete/overwrite/purchase
   steps need confirmation when a plan runs (Phase 2). Scribbles carry no risk field.
9. **Privacy before storage.** Password fields, secrets, and user-defined
   patterns are redacted before annotations or workflows are written.
10. **`gui_agent` stays read-only** until an explicit integration milestone. The
    scriber imports its tools; it does not monkeypatch the agent.
11. **Least assumptions.** Unknown is better than invented. Every inferred
    purpose, parameter, or interface has evidence or is marked unknown.
12. **Indexing is conditional.** No search infrastructure until composition is
    proven and scale demands it.

---

## 6. Where the LLM sits

| Stage | Deterministic | LLM |
|---|---|---|
| Normalize a flow | typing spans, window transitions, time gaps | — |
| Extract annotations + scribbles | parse, validate refs/tools/selectors, replay | one-shot template fill: describe, segment, prune, parameterize, categorize |
| Compose | binding, interface matching, ordering, bridge insertion | select scribbles and resolve intent; handle ambiguity |
| Execute | tool calls, precondition/postcondition checks, retries | only on verification failure (agent fallback) |
| Retrieve | FTS/lexical index | embeddings only if lexical retrieval misses the gate |

Rule of thumb: **LLM at the edges, deterministic in the loop.**

---

## 7. Evaluation

The evaluation has two different jobs; do not conflate them.

### 7.1 Phase 1 — mechanical validity

- Every raw action is annotated.
- Every annotation and step cites action ids.
- Zero invented tools, selectors, or arguments (code copies recorded actions).
- Every scribble replays on its own.
- The full flow still replays.
- The user accepts the scribble descriptions.

This does **not** prove the scribbles are semantically useful. It proves they
are grounded and executable.

### 7.2 Phase 2 — capability experiment (the semantic gate)

Conditions:

| Condition | Agent receives |
|---|---|
| **A** | No workflow memory (current agent) |
| **B** | Raw recorded transcripts as context |
| **C** | Scribble descriptions + annotations only |
| **D** | Scribble descriptions + executable scribbles + composition |

Task suite: **held-out tasks that require composing ingredients from recorded
workflows**. The recordings are not the test tasks. Example: record "create a
folder", "move a file", and "open a folder"; test "create an invoices folder and
move last month's PDFs into it."

Metrics: task success, end-state correctness, wall-clock time, tool calls,
planning turns, context tokens, human interventions, and handoff rate. Run the
same model, temperature, and machine; randomize order.

Decision:

- C must beat A/B on at least one primary metric without regressing another.
- D must beat C on speed or accuracy, or composition is not earning its
  complexity.
- If neither holds, stop and reassess the hypothesis before Phase 3.

### 7.3 Phase 3 — retrieval (conditional)

30 natural-language queries against the library; recall@5, MRR, latency, and
scribble bundle size. Only after the Phase 2 gate and only if brute-force
lookup is actually too slow or too large.

### 7.4 Gold set

- **Ingredients:** 10–15 recordings across Explorer, Chrome, VS Code, and
  Notepad, with different names/paths/windows.
- **Held-out composition tasks:** 10–15 requests that combine ingredients in
  ways no single recording covers.
- The recordings are inputs; the composition tasks are the test.

---

## 8. Cleanup and docs map

Moved out of the repository root:

- `workflow_scriber_plan.v1.md` → `docs/archive/workflow_scriber_plan.v1.md`
- `workflow_scriber_plan.md` (v2) → `docs/archive/workflow_scriber_plan.v2.md`

Active documents:

- [Phase 0 — Record + replay](workflow_scriber_phase0_plan.md) — complete
- [Phase 1 — Extraction](workflow_scriber_phase1_scribbles_plan.md)
- [Phase 2 — Composition + experiment](workflow_scriber_phase2_composition_plan.md)
- [Phase 3 — Retrieval at scale](workflow_scriber_phase3_indexing_plan.md) —
  conditional

---

## 9. Non-goals

- Branching, loops, and collection iteration inside a workflow. The happy path
  plus agent fallback is the model.
- Human review of executable mechanics. Replay validates mechanics; the user
  reviews scribble descriptions; the experiment validates semantics.
- Autonomous workflow discovery without a recording.
- Agent-promoted runs in this cycle. The user records; the LLM interprets.
- Multi-user, cross-machine, or hosted operation.
- Screenshot/video capture in the first extraction version.
- Indexing before composition is proven.

---

## 10. Open decisions

1. **Scribble replayability.** Decided: every scribble is individually
   replayable; there are no fragment scribbles.
2. **One call per recording.** Decided for now: one call plus at most one
   repair. Chunking is deferred until a recording is actually too long.
3. **Interface inference.** Deferred. Scribbles carry no preconditions or
   effects; Phase 2 decides whether composition needs them.
4. **Agent integration for the experiment.** Proposed: an evaluation harness
   that feeds context bundles to the existing agent loop, with no production
   edits to `gui_agent`.
5. **Phase 3 trigger.** Proposed: at least 30 scribbles or a measured
   context/latency bottleneck, and only after the Phase 2 gate passes.
6. **Default execution path.** Proposed: full replay remains the fallback; a
   composed plan is used only when its scribbles replay and the end state
   checks out.
