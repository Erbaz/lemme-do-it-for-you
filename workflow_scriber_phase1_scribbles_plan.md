# Phase 1 — Scribbles

**Status:** Code complete; manual test session pending ([manual_test_cases.md](manual_test_cases.md))  
**Depends on:** [Phase 0 — Record + replay](workflow_scriber_phase0_plan.md)  
**Next:** [Phase 2 — Composition + experiment](workflow_scriber_phase2_composition_plan.md)

---

## 1. Idea

One recording is a long sequence of tool calls. One LLM call reads it and returns
**scribbles**: small, atomic, reusable workflows, each a subset of those actions.

One scribble is one capability — "open File Explorer at the Desktop", "open a new
Chrome tab", "delete the selected file". Scribbles overlap freely; the same
actions may appear in several. Each one either carries the actions that establish
its starting state, or is a short fragment whose description states what must
already be true. Both kinds are wanted: a self-contained primitive can be called
from nothing, and a state-scoped fragment is small enough to be safe.

The LLM picks action ids and writes descriptions. It never writes tool calls,
selectors or arguments. Code copies the chosen actions into a file in the
raw-flow format, so every scribble replays on its own. The full recording stays
replayable too: N scribbles + 1.

Descriptions are what Phase 3 will index and search.

---

## 2. Output

`workflow_scriber/library/<recording_id>/`

| File | Contents |
|---|---|
| `scribbles.json` | recording summary, one annotation per action, the scribbles |
| `workflows/<id>.json` | one replayable scribble |
| `context.json` | exactly what the LLM saw |
| `llm_responses.json` | the LLM's raw replies |

Re-running `extract` replaces the folder.

### Scribble

```json
{
  "id": "explorer_open_desktop",
  "title": "Open File Explorer at the Desktop folder",
  "description": "From any state, opens File Explorer from the taskbar and goes to the Desktop folder. Ends with File Explorer showing the Desktop.",
  "actions": [1, 2],
  "steps": [
    {"intent": "Open File Explorer", "actions": [1]},
    {"intent": "Go to the Desktop folder", "actions": [2]}
  ],
  "workflow": "workflows/explorer_open_desktop.json"
}
```

Nothing is added by code except `workflow`. There are no parameters: a scribble
is replayed as recorded, and reuse comes from having many small ones rather than
from substituting values into a long one.

### Annotation

```json
{"action": 14, "observed": "Typed 't' into the rename edit.", "purpose": "Name the new folder."}
```

No confidence, risk, tags, parameters, preconditions or effects. Those were
speculation the agent did not need, and they invited wrong claims. The starting
state is prose in `description`, not a field.

---

## 3. Pipeline

```
raw flow → normalize → context card → one LLM call → validate
                                          │
                        invalid ──► one repair call ──► fail, write nothing
                                          │
                              materialize → library/<recording_id>/
```

- **normalize** (`normalize.py`): per action, the typed character, focus,
  `focus_after`, window, identity conflict, and whether it is replayable.
  Typing spans group consecutive characters into the same control. A control is
  compared by type, id and class, not Name, because an edit's Name is its text.
- **context card** (`scribbles.context_card`): one compact JSON object per
  action, empty fields dropped. Saved as `context.json`.
- **validate** (`scribbles.validate`): ids exist, order, no repeats, all
  replayable, steps cover the actions exactly once, unique snake_case ids, no two
  scribbles with the same action set, description ≤ 600 chars.
- **failure**: if both attempts are invalid, `extract` raises and nothing is
  written. Scribbles only ever come from the LLM; there is no deterministic
  fallback that invents one.

---

## 4. What the transcript tells the LLM

Two fields decide what an action acted on, and the prompt is explicit about it:

- `focus` — the element with keyboard focus. **A key press acts on this.**
- `target` — the element under the cursor at a click. Often a cell or a
  decoration; in file lists it can name a different row than the user picked.

When they disagree, `focus` wins. This matters: a click recorded as
`target: PASSPORT_ERBAZ.pdf` followed by `{DELETE}` with `focus: test` deleted
the folder `test`, not the PDF. An earlier prompt let the model assert the PDF
was deleted.

Other fields: `foreground_target` (used when `identity_conflict` is set),
`visible` (named controls when the window changed), `gap_s`, `replayable`.

---

## 5. Recording enrichment

Added by the recorder; older recordings still work without them.

| Field | Meaning |
|---|---|
| `focus` | Focused element when the worker handled the event |
| `foreground` | Foreground window's element under the cursor, when the hit element is in another process |
| `visible` | Up to 40 named controls, recorded when the window title changes; icon-font glyphs are skipped |
| `redacted` | Characters typed into a password field are recorded empty; replay refuses them |

Caveat: focus is read on the worker thread, so it can lag the event slightly.

Scrolling invalidates the spatial index: items move but the container's rect does
not, so a click after a scroll used to resolve to the container (`name:Items View`)
instead of the item. The recorder now marks the index stale on scroll and rebuilds
it once, before the next click. Repeated scrolls do not each trigger a rebuild.

---

## 6. Replay as review

Replay proves the selectors resolve and the actions run. It does not prove the
description is right. The user reviews descriptions in `scribbles.json`.

On an identity conflict, the foreground selectors are tried first and the
recorded ones remain as fallbacks.

---

## 7. Commands

```
python -m workflow_scriber watch
python -m workflow_scriber extract            # newest recording in recorded_flows/
python -m workflow_scriber extract <flow>.json
python -m workflow_scriber.replay workflow_scriber/library/<rec>/workflows/<id>.json
python -m unittest discover -s workflow_scriber/tests -t .
```

The LLM uses the same `.env` settings as `gui_agent`. Timeout 180 s.

---

## 8. Remaining

- **Manual test session:** [manual_test_cases.md](manual_test_cases.md) — record
  the scenarios, extract, replay each scribble, review the descriptions.
- **Long recordings:** chunking deferred until one is actually too long.
- **Selector/tool autocomplete index:** a derived lookup over the same recordings,
  keyed on UI state plus recent actions. Deferred to its own phase; it needs the
  literal-selector vs selector-shape decision first. Atomic scribbles are its
  input, which is why they come first.
