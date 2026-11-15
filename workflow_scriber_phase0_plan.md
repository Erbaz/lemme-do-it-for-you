# `workflow_scriber` — Phase 0 (Inverted Capture)

**Status:** ✅ Complete — 2026-11-15  
**Evidence:** `workflow_scriber/recorded_flows/workflow_20261115_004759.json` (12 actions), `.replayed.json` (pruned), `.events.txt` (WinEvent probe)  
**Supersedes:** Phase 0 of the archived v2 plan (`docs/archive/workflow_scriber_plan.v2.md` §5–§7)  
**Next:** [Roadmap](workflow_scriber_roadmap.md) → [Phase 1 — Extraction](workflow_scriber_phase1_scribbles_plan.md)

---

## 1. Problem restated

The first recorder resolved **after** the click:

```
click (x,y)  →  ControlFromPoint(x,y)  →  build_selector(element)  →  round-trip verify
```

That fails for three independent reasons:

1. **Hit-test returns chrome, not the target.** `ElementFromPoint` gives the topmost OS element (often a Chromium frame pane), not the `ButtonControl` underneath.
2. **No canonical element → selector.** `AutomationId` is path-dependent, `Name` is not always queryable, `RuntimeId` is session-scoped.
3. **Clicks mutate state before resolution.** Minimize / Close destroy the window; by worker time the target is gone and resolution returns `element: null`.

`gui_agent` succeeds because it resolves **before** it clicks: it discovers the element via its own tree walker, holds the reference, then clicks the center of that element's rect.

The fix: **invert the direction.** Discover interactable elements ahead of time with `gui_agent`'s own tree walker (so every selector is one `gui_agent` can already resolve), then map the human click to whichever discovered element's rect contains `(x,y)`.

---

## 2. Delivered design (as built)

```
startup
  DiscoveryIndex.build()
    walk desktop, depth ≤ 10 (the depth find_element can replay)
    keep interactable elements: selector, rect, fingerprint, window pid/title
    drop window-sized ancestors (≥ 80% of the top-level window)

mouse_down  →  pending (x, y, t)
mouse_up    →  find_at(x, y)
                 interactive tier first, then smallest area, then deepest
               candidate_selectors(fingerprint)
               emit click_element {selector, selectors, double_click}
               double-click upgrades the first record instead of adding one

keys        →  one press_key per non-modifier key
wheel       →  scroll_element on the element under the cursor

replay
  for each action: call the real gui_agent tool
  selector tools: try candidates in order; first tool success wins
  stop on exhausted candidates
  write <flow>.replayed.json (pruned; original untouched)
```

**Record-time verification was not implemented.** A physical `click_element` cannot be test-run without clicking, so the recorder cannot silently prove a selector. Replay is the oracle: it calls the real tool and prunes the ladder to the first candidate that the tool accepts. This replaced the draft's "silent verify" step.

**Optional event probe.** `watch --events` installs WinEvent hooks (foreground, focus, invoke, selection, menu popup), maps them to UIA elements, and writes `<flow>.events.txt`. Recording is unchanged. It is a measurement tool, not part of the selector path; see caveats.

---

## 3. Constraints (unchanged)

| Constraint | What it meant |
|---|---|
| Do not edit any file under `gui_agent/` | Discovery imports `_collect_interactable`, `_build_selector`; replay imports the real tools. No monkeypatching. |
| Do not import `gui_agent.main` | It loads `.env` and builds an LLM at import time. |
| `find_element` hardcodes `maxDepth=10` | Discovery uses the same depth limit; deeper elements are out of scope. |
| Selector grammar is `name:`, `class:`, `id:`, comma-combined | `control_type:` and `index:` are unusable in this codebase, so the ladder is rungs 1–4. |
| `click_element` physically moves the mouse | The recorder never test-clicks; it records the ladder and lets replay decide. |

---

## 4. Delivered modules

| File | Role |
|---|---|
| `workflow_scriber/discovery.py` | `DiscoveryIndex`: desktop walk, window-like ancestor filter, `find_at`, cache-miss refresh |
| `workflow_scriber/fingerprint.py` | Element identity and the selector ladder (`id`, `name`, `name+class`, `class`) with safety filters |
| `workflow_scriber/recorder.py` | Hook events → tool calls; pending click, double-click upgrade, scroll/key records |
| `workflow_scriber/watcher.py` | Low-level mouse/key hooks, worker thread, foreground capture, session writer, optional event probe |
| `workflow_scriber/replay.py` | Runs a flow through the real `gui_agent` tools, prunes candidates, writes `.replayed.json` |
| `workflow_scriber/win32_input.py` | Hook structs, key tables, SendKeys conversion |
| `workflow_scriber/events.py` | Opt-in WinEvent probe; debug only, not in the recording path |

Removed with Phase 0: `capture.py` and `tree.py` (the old `ControlFromPoint`-centric path).

---

## 5. Gate result

The accepted gate is one real end-to-end flow, recorded and replayed on this machine, with the end state visually confirmed.

| Criterion | Result |
|---|---|
| Real desktop flow recorded | ✅ 12 actions, scriber 0.5.0, File Explorer + terminal |
| Replay calls every tool | ✅ 12/12 tools called; every first candidate was accepted |
| End state correct | ✅ Confirmed by the user |
| Empty selector / `element: null` for clicks | ✅ None in the accepted run |
| No `gui_agent` edits | ✅ `git diff gui_agent/` empty |
| Original recording preserved | ✅ `.replayed.json` is a separate pruned copy |

The draft's original 20-button ≥ 90 % uniqueness gate was not re-run against this final architecture; it was replaced by the end-to-end flow above. Earlier exploratory runs covered `name:Home`, taskbar buttons, and tab/Close controls.

---

## 6. Caveats (observed, not hypothetical)

### Identity and replay

1. **The accepted run still recorded occluded-window elements.** Three actions' `element` metadata came from processes other than the recorded foreground window: a background tab titled `main.log. Unmodified.` (`pid 21324`), a Chrome bookmark separator (`pid 19380`), and Qoder's Close button (`pid 25984`). The flow nonetheless completed because those elements' rect centers landed on the intended foreground controls at the same screen coordinates:
   - `desktop.ini` rect overlapped Explorer's Address Bar → replay focused the Address Bar.
   - Chrome `Separator` rect overlapped Explorer's New button → replay opened the New menu.
   - Qoder `Close` rect overlapped Explorer's Close → replay closed Explorer.
   This is **geometry compensation, not correct identity**. Move or resize the background window between record and replay and the same selectors will click the wrong place. Fixing this is the top Phase 1 item.
2. **Replay success is the tool's return string, not a postcondition.** "Clicked element" means the tool resolved a selector and clicked; it does not prove the intended UI changed. This run was visually confirmed by the user, but later validation should add an identity/topmost check before invoking.
3. **Generic names are cross-window ambiguous.** `name:Close`, `name:Separator`, `name:New` can match any window. `click_element` searches from the desktop root, so correct behavior currently depends on tree order (topmost/foreground windows usually come first). A different foreground app or window order can mis-target.
4. **Replay clicks the element's rect center, not the recorded point.** The point is stored as metadata only. If the recorded element is off-center relative to the human's click, replay lands elsewhere; this is what makes the occlusion cases above work by luck.
5. **The index is a snapshot.** Menus, flyouts, and dialogs that appear after startup may miss until a cache miss triggers `maybe_refresh` (0.75 s debounce). Right-click menus are the main risk.

### Input and focus

6. **`press_key` has no focus guard.** If a click focuses the wrong control, every subsequent key goes to the wrong place. The accepted flow worked because focus happened to be correct.
7. **Keystroke fidelity is not guaranteed.** `ToUnicodeEx` + SendKeys cannot reproduce every case: IME composition, non-ASCII characters, dead keys, key repeat, and some punctuation. Test with an IME and a non-Latin search box.
8. **Double-click detection is fixed** at 0.45 s / 6 px. Slow double-clicks become two single clicks; fast repeated clicks may upgrade unintentionally.
9. **Scroll targets the element under the cursor**, which is not always the actual scroll container; the wheel may be handled by an ancestor.

### Privacy

10. **No redaction yet.** Every non-modifier key is recorded, including characters typed into password fields. `IsPassword` is stored in element metadata but is not used to suppress or mask keystrokes. Do not record secrets until this is implemented.

### Environment

11. **DPI and multi-monitor coordinates** are physical pixels at the current scaling. 125 %/150 % scaling and negative-coordinate monitors are not yet validated.
12. **Elevated apps (UIPI)** may not expose UIA/events to a non-elevated scriber; run both at the same integrity for now.
13. **Slow or hung apps** can block UIA resolution on the worker; there is no timeout per call.
14. **Deep Chromium/Electron elements** beyond `maxDepth=10` cannot be discovered or replayed.
15. **Replay timing** is a fixed 0.3 s delay; downloads, page loads, and modal animations may need explicit waits.

### Event probe

16. `AccessibleObjectFromEvent` → `ElementFromIAccessible` failed for every observed event; the log shows `<focus fallback>` (the probe fell back to `GetFocusedControl` / `ControlFromPoint`). Focus events are duplicated across child hwnds, and some events arrive after the source window is destroyed (invalid hwnd / RPC error).
17. `contains_click` is rectangle containment only; it does not check z-order, so a background element can report `contains_click=yes` while the foreground owns the pixel.
18. The probe is diagnostic only and does not feed the recorder. Do not treat its output as selector verification.

---

## 7. UI flows to test

### P0 — before relying on the recorder

| Flow | What it stresses | Pass signal |
|---|---|---|
| Explorer in front of Chrome; click the Address Bar and type | Occlusion + focus | Recorded element is the foreground Address Bar; typing lands there on replay |
| Same names in two apps (`Close`, `New`, `Share`, `Search`) | Cross-window ambiguity | Replay acts on the intended foreground window, even after moving it |
| Context menu → submenu → item | Dynamic index + popup roots | Menu item recorded; replay opens the same item |
| Password field / login page | Privacy | **Block until redaction exists**; verify no characters are persisted |
| 125 % / 150 % scaling and a secondary monitor | Coordinates | Points and rects stay consistent; replay hits the same element |
| Slow/hung app (UIA call stalls) | Worker liveness | Recorder stays responsive; no silent loss of subsequent actions |

### P1 — common desktop work

| Flow | What it stresses |
|---|---|
| Start menu, taskbar buttons, system tray, notification center | Shell/UWP surfaces, `Shell_TrayWnd`, flyouts |
| File Open/Save dialog, overwrite-confirmation dialog | Modal dialogs, dynamic trees |
| Inline rename in Explorer, then Enter/Esc | Edit focus and commit/cancel paths |
| Chrome/VS Code/Explorer tabs, tab close, window Close/Minimize/Maximize | Generic `Close`, target destruction |
| Long list scroll (vertical and horizontal) | Scroll target and amount mapping |
| Keyboard-only: Tab/Shift+Tab, Alt+F4, accelerators, Ctrl+A/C/V | Focus and modifier replay |
| IME and non-ASCII text entry | Keystroke fidelity |
| Single vs double click on a desktop icon/file | Double-click upgrade |
| Two instances of the same app | pid/window scoping |
| Deep web/Electron control (page button, editor tab) | `maxDepth=10` limit |

### P2 — edge cases

| Flow | What it stresses |
|---|---|
| Right-click and drag | `mouse_click` metadata vs cursor-position semantics |
| Download, navigation, modal wait | Fixed replay delay |
| Toast/auto-dismiss UI | Snapshot staleness |
| RTL / high-contrast theme | Names and layout assumptions |

---

## 8. Follow-ups (not Phase 0)

1. **P1 — record-time topmost filter.** In `DiscoveryIndex.find_at`, restrict candidates to the foreground window (or verify with `ControlFromPoint`/z-order) before tier/area ranking. This directly fixes the occlusion cases in §6.1.
2. **P2 — replay pre-flight identity check.** Compare the resolved element's fingerprint/topmost status with the recorded one before invoking; mark `verified` and fall back to the recorded point only when safe.
3. **P3 — focus verification before `press_key`.** Confirm the focused control is the expected target before sending characters.
4. **P4 — event-assisted scoping.** Only after the `AccessibleObjectFromEvent` mapping actually works; today it falls back for every event.
5. **Privacy** — password/denylist/pause hotkey before any real daily use.
6. **Optional gate harness** — restore a 20-button uniqueness/coverage measurement if the 90 % gate is needed again.

---

## 9. How to run

```bash
python -m workflow_scriber watch                      # record
python -m workflow_scriber.replay workflow_20261115_004759.json   # replay + prune
python -m workflow_scriber watch --events -o probe.json           # + WinEvent log
```

Recorded JSON and `.replayed.json` files are gitignored under `recorded_flows/`. The `.events.txt` log is also a generated artifact; keep it locally for diagnosis.
