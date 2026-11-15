# Phase 2 — Composition and the Capability Experiment

**Status:** Planned  
**Depends on:** [Phase 1 — Extraction](workflow_scriber_phase1_scribbles_plan.md)  
**Produces:** a composer, a deterministic executor, and an experiment report  
**Feeds:** [Phase 3 — Retrieval at scale](workflow_scriber_phase3_indexing_plan.md) only if the experiment passes

---

## 1. Goal

This phase answers the research question:

> Does scribble memory improve `gui_agent`'s context
> gathering, planning efficiency, speed, and accuracy on new tasks?

It delivers two things:

1. **A composition pipeline** — select scribbles/fragments, bind
   parameters, order them by interface, fill gaps, and execute one plan.
2. **A controlled experiment** — compare an agent with no memory, raw
   transcripts, scribble descriptions, and descriptions plus executable composition.

Composition is the north star. If it does not beat the baselines, the roadmap
stops before indexing.

---

## 2. Hypotheses and conditions

| ID | Hypothesis |
|---|---|
| **H1** | Scribble descriptions and annotations improve context gathering and reasoning versus no memory or raw transcripts. |
| **H2** | Executable scribbles plus composition improve speed or accuracy versus scribble descriptions alone. |
| **H3** | Composition solves held-out tasks that no single recording covers. |

| Condition | What the agent receives | What runs |
|---|---|---|
| **A** | No workflow memory | existing `gui_agent` loop |
| **B** | Raw recorded transcripts as context | existing agent loop |
| **C** | Scribble descriptions + annotations only (no executable scribbles) | existing agent loop |
| **D** | Scribble descriptions + scribbles + composer | one composition call, then deterministic executor |

A and B are baselines. C tests the descriptions' value as context. D tests the
value of executable composition.

### 2.1 Experimental controls

- Same model, temperature, system prompt, machine, display scaling, and app
  versions across conditions.
- Randomized task order; record every run.
- Keep the library small enough that retrieval is not the bottleneck. Brute-force
  scribble injection is acceptable here; Phase 3 is not part of the experiment.
- Held-out tasks only. The recorded tasks are ingredients, not the test set.
- No production edits to `gui_agent/`; use an evaluation harness.

---

## 3. Task suite

### 3.1 Ingredients

10–15 recordings across Explorer, Chrome, VS Code, and Notepad, each recorded
2–3 times with different names, paths, or window positions. They yield
annotations and scribbles.

Example ingredients:

- open Explorer at a folder;
- create and name a folder;
- copy or move a file;
- open a recorded web search;
- open Notepad and save a file;
- close a window.

### 3.2 Held-out composition tasks

10–15 requests that require combining ingredients in ways no single recording
covers. Examples:

- “Create an invoices folder in Downloads and put a copy of report.txt inside.”
- “Open the recorded search, then save its title in a new Notepad file.”
- “Create a folder, then move the file I recorded moving into it.”
- “Open Explorer at the recorded folder, create a folder, and close the window.”

Tasks must be solvable with the recorded tools and scribbles. If a
task needs an unrecorded capability, it is out of scope for the experiment.

### 3.3 End-state definitions

Each task has an objective end-state check (file exists, window focused, text
present). Use the Phase 1 verification predicates. A task is successful only if
the end-state check passes, not because a tool returned a string.

---

## 4. Composition pipeline

```
request
  │
  ▼
scribble cards        scribble descriptions, not full raw flows
  │
  ▼
selection              choose workflows/fragments; cite ids; explain gaps
  │
  ▼
binding                parameters from request; missing → ask, never guess
  │
  ▼
interface match        requires/provides; unknown → refuse or bridge
  │
  ▼
ordering               topological; cycles/conflicts → stop
  │
  ▼
plan.json              concrete tool calls, macros expanded, selector ladders
  │
  ▼
executor               precondition → call → verify → next
```

### 4.1 Scribble card

The composer sees compact cards, not full scribble bundles:

```json
{
  "id": "explorer_create_folder",
  "title": "Create and name a folder in File Explorer",
  "description": "Opens File Explorer, goes to Documents, creates a folder and names it.",
  "parameters": [{"name": "folder_name", "default": "test"}],
  "steps": ["Open File Explorer and go to Documents", "Create and name the folder"]
}
```

The full workflow file is loaded only for the selected scribbles.

### 4.2 Selection rules

- The composer must cite scribble ids and say why each is needed.
- Every scribble replays on its own, so any of them can start a plan.
- If two scribbles produce the same effect differently, that is an ambiguity:
  ask the user before mutating.
- If no scribble fits, return `unsupported`; do not invent a workflow.

### 4.3 Binding rules

| Type | Validation |
|---|---|
| `string` | non-empty; no invalid path separators |
| `path` | exists, or parent exists when creating |
| `app` | known process/window |
| `choice` | must be an allowed value |
| `literal` | must equal the recorded literal |

- Every value traces to the request or a declared default.
- Missing required values block the plan; the composer asks.
- Sensitive values are redacted in logs.
- A binding that changes the end state is shown in the plan preview.

### 4.4 Interfaces and least assumptions

Composition needs `requires` and `provides`. They are inferences from observed
before/after state, so:

- every interface carries evidence and confidence;
- `unknown` is a valid value;
- an unknown interface cannot be silently assumed satisfied;
- a bridge may establish a known precondition, but it must be a validated bridge
  from the bridge library, not an inline invention.

If the library cannot prove an interface, composition stops and reports the
gap. That is the correct failure, not a guess.

### 4.5 Bridges

Small validated tool-call sequences for gaps:

- `focus_window(process_or_title)`;
- `open_app(process_or_path)`;
- `wait_for(selector, timeout)`.

Rules:

- bridges are data files with signatures, steps, verification, risk, provenance;
- the composer may select a bridge, never author one inline;
- a failed bridge postcondition is reported, not hidden;
- replace a repeating bridge with a proper recorded workflow.

### 4.6 Ordering and conflicts

- Order by `requires`/`provides`; independent steps follow the request order.
- Cycles, conflicting effects, or two workflows writing the same parameter are
  errors, not choices.
- The final order is visible in the plan preview.

---

## 5. Plan format

```json
{
  "plan_version": "1.0",
  "request": "Create an invoices folder in Downloads and copy report.txt into it",
  "workflows": ["explorer_create_folder", "explorer_copy_file"],
  "bindings": {"folder_name": "invoices", "source": "report.txt"},
  "steps": [
    {
      "plan_step_id": "p1",
      "source": {"workflow": "explorer_create_folder", "step": "s1"},
      "intent": "Focus File Explorer",
      "tool": "click_element",
      "args": {"selector": "id:Appid: Microsoft.Windows.Explorer"},
      "verify": [{"kind": "window_focused", "args": {"process": "explorer.exe"}}],
      "risk": "safe",
      "on_failure": "stop"
    }
  ],
  "preconditions": [{"kind": "app_running", "args": {"process": "explorer.exe"}}],
  "postconditions": [{"kind": "item_exists", "args": {"name": "invoices"}}],
  "mode": "execute"
}
```

The plan is fully concrete: macros expanded, bindings substituted, selector
ladders ordered. It is the audit artifact.

---

## 6. Executor

### 6.1 Modes

| Mode | Behavior |
|---|---|
| `dry-run` | resolve selectors and evaluate preconditions; no mutation |
| `execute` | run all steps with verification |
| `verify` | evaluate preconditions/postconditions only |
| `from-step` | resume after a failure |
| `stop-after` | run through a named step |

### 6.2 Step lifecycle

```
check requires → resolve target(s) → confirm risk if needed
→ call tool → verify expected effect → record result
```

- **Precondition failure:** stop before mutation; report the predicate and
  current value. No blind retry.
- **Target resolution failure:** try the next recorded selector; if all fail,
  stop and offer agent handoff. Never click a different window.
- **Postcondition failure:** `retry` once, `agent` handoff, `stop`, or a declared
  fallback step.
- **Foreground/window change:** stop and report.
- **Destructive step:** require confirmation unless the plan was explicitly
  approved for it.

### 6.3 Verification predicates

| Predicate | Check |
|---|---|
| `app_running` | process exists |
| `window_focused` | foreground window matches process/title |
| `element_exists` | selector resolves within timeout |
| `element_value` | element value/name/text matches |
| `item_exists` | file/folder exists at the bound path |

If a predicate cannot be evaluated, the step is `unverified` and the report says
so. Tool return strings are never treated as success.

### 6.4 Logs and handoff

- `<plan>.run.json`: per-step status, resolved selector, verification, timestamps,
  redacted arguments, failure reason.
- `from-step` re-checks preconditions before resuming.
- Handoff to `gui_agent` includes the completed steps, the failed step, the
  current UI context, and the remaining goal. The agent must not redo completed
  steps blindly.

---

## 7. Measuring the research question

### 7.1 Primary metrics

| Metric | Why it matters |
|---|---|
| Task success | Does the composed plan reach the defined end state? |
| End-state correctness | Success must be verified, not inferred |
| Wall-clock time | The “one go” speed claim |
| Tool calls | Efficiency versus agent-per-step |
| Planning turns / LLM calls | Context-gathering and reasoning cost |
| Context tokens | Are the scribble cards compact enough to help? |
| Human interventions | Practical usability |
| Handoff rate | How often composition fails into the agent |

### 7.2 Decision rule

- **H1:** C must beat A and B on at least one primary metric without regressing
  success. If scribble context does not help, the semantic layer is not earning
  its cost.
- **H2:** D must beat C on time or tool calls at equal or better success. If not,
  executable composition is not worth the complexity.
- **H3:** D must solve a meaningful share of held-out composition tasks, not just
  the recorded ones.
- **Kill:** if neither H1 nor H2 holds, stop. Do not start Phase 3 or enrich the
  schema to rescue the result.

Because the sample is small, report per-task results and effect sizes, not just
averages. A single lucky run is not evidence.

### 7.3 Confounds to control

- Same library and scribble cards across C and D.
- No retrieval differences: inject the same scribbles.
- Same display scale, app versions, and starting state.
- Recorded ingredients do not overlap the held-out tasks.
- The agent prompt does not mention which condition it is in.

---

## 8. Integration with `gui_agent`

`gui_agent/` stays read-only.

- **A/B/C:** an evaluation harness injects the condition's context into the
  existing agent loop. No production code changes.
- **D:** the composer emits `plan.json`; the scriber executor runs it. On
  failure, control returns to the agent with the run log.
- If the harness needs a context-loading tool, expose it outside `gui_agent/`
  (CLI or wrapper), not by monkeypatching the agent.

Production integration is a separate decision after the experiment passes.

---

## 9. Acceptance gate

### 9.1 Mechanical

| Criterion | Target |
|---|---|
| Composed plans with invented tools/selectors | 0 |
| Wrong-target clicks | 0 |
| Steps verified | ≥ 90 % of mutating steps |
| Clean precondition failure | 2/2 adversarial cases |
| Selector-drift diagnosis | Stops at the right step, no wrong click |
| Resume from failure | `from-step` succeeds after a transient injected failure |
| Unknown interface | Refused, not guessed |

### 9.2 Research

- C beats A/B on at least one primary metric without a success regression, or H1
  is rejected.
- D beats C on time or tool calls at equal/better success, or H2 is rejected.
- D solves a meaningful share of held-out composition tasks, or H3 is rejected.
- The report includes per-task data, condition setup, and failure analysis.

If the research gate fails, the correct outcome is to stop or narrow the bet,
not to add features.

---

## 10. Failure modes and mitigations

| Failure | Mitigation |
|---|---|
| Scribbles help only because they leak the recorded task | Held-out composition tasks; no overlap |
| Retrieval confounds the result | Small library; same scribbles for C/D |
| Composer hallucinates a workflow | Allowlist of scribble ids |
| Fragments used without prerequisites | Interface check; refuse unknown |
| Selector drift | candidate ladder + resolution check before mutation |
| Hidden modal state | precondition/postcondition checks; stop and hand off |
| Wrong foreground window | window/focus check before each step |
| Destructive composition | risk gate + explicit confirmation |
| Partial execution | run log + from-step + current-state re-check |
| “Tool returned” mistaken for success | verified end state only |
| Small sample overinterpreted | per-task report; effect sizes; no single-run claims |

---

## 11. Milestones

| Milestone | Deliverable |
|---|---|
| **M0 — Baselines + harness** | condition A and B runs, task suite, end-state checks |
| **M1 — Scribble context (C)** | scribble cards injected into the agent loop |
| **M2 — Composer** | selection, binding, interface matching, `plan.json` |
| **M3 — Executor** | modes, verification, risk gate, run log |
| **M4 — Fragments + bridges** | fragment preconditions, bridge library, handoff |
| **M5 — Experiment report** | A/B/C/D results, per-task analysis, go/no-go decision |

Phase 2 is complete when the experiment either supports the hypothesis or
clearly rejects it, and the composition pipeline is mechanically safe either
way.

---

## 12. Open questions

1. **C vs D framing.** Is C “scribble descriptions as context for the existing agent,” and D
   “one composer call + executor”? Proposed: yes; that isolates context value
   from execution value.
2. **Handoff budget.** What handoff rate makes composition worthwhile? Proposed:
   report it; set the threshold after the baseline is measured.
3. **Success bar for novel tasks.** What counts as a meaningful share? Proposed:
   define after the task suite is piloted; do not tune it to the result.
4. **Composer call count.** One call for the whole plan, or one per scribble
   workflow? Proposed: one for the whole plan; retry only on invalid output.
5. **Fragment default.** If a fragment lacks a precondition, refuse or ask the
   user for the missing state? Proposed: refuse execution, explain the gap, and
   offer an agent handoff.
6. **Library size for the experiment.** Proposed: keep it under ~20 scribbles so
   retrieval is not a confound.
