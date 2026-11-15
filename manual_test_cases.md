# Phase 1 manual test cases

Record these five sessions yourself, extract scribbles from each, and replay the
scribbles you want to trust. Then send me the results for review.

The point of this session is to check that extraction now produces **many small
atomic scribbles** instead of one long journey, that each one states the starting
state it needs, and that a click on a file item records the item rather than the
list containing it.

---

## How to run each case

```bash
# 1. record — do the steps, then Ctrl+C in this terminal
.venv/Scripts/python.exe -m workflow_scriber watch -o case1.json

# 2. extract — newest recording, or name it explicitly
.venv/Scripts/python.exe -m workflow_scriber extract case1.json

# 3. replay one scribble (pick safe ones first)
.venv/Scripts/python.exe -m workflow_scriber.replay workflow_scriber/library/case1/workflows/<id>.json
```

Ground rules:

- **Do not touch the mouse or keyboard while a replay runs.** It moves the cursor
  physically and clicks the centre of whatever the selector resolves to.
- Use throwaway files only. Cases 1 and 2 delete things for real.
- Start each recording from the stated setup. The starting state is part of the
  test.
- Stop the recorder with **Ctrl+C in the terminal running `watch`**. That keypress
  lands in the recording as noise; extraction is expected to drop it.
- Action ids below are **illustrative**. Yours will differ. Match scribbles by
  what they contain, not by number.

---

## Case 1 — Explorer: open Desktop, delete one file, close

This is the session that produced the bad `name:Items View` scribble. It is the
most important case.

**Setup.** Create `scribble_a.txt` and `scribble_b.txt` on the Desktop. Close every
File Explorer window. Leave the terminal running `watch` visible.

**Do.**

1. Click the File Explorer taskbar button.
2. Click **Desktop** in the left navigation pane.
3. Scroll the file list until `scribble_a.txt` is visible. Scroll naturally, a few
   notches at a time.
4. Click `scribble_a.txt` once to select it. Do not shift-click, do not press arrows.
5. Press **Delete**.
6. Click the window's **Close** (X) button.
7. Ctrl+C in the terminal.

**Expected scribbles.**

| id | kind | contains | description should say |
|---|---|---|---|
| `explorer_open_desktop` | self-contained | taskbar click + Desktop nav click | From any state, opens Explorer at Desktop |
| `explorer_select_file` | fragment | the click on `scribble_a.txt` | With Explorer at a folder, selects the named file |
| `explorer_delete_selected_file` | fragment | the Delete key | With Explorer focused and a file selected, deletes it |
| `explorer_close_window` | fragment | the Close click | With an Explorer window open, closes it |
| `explorer_delete_file_from_desktop` | combined | open + navigate + select + delete | the whole journey, optional |

Overlap is expected and correct: the same clicks appear in both the small
fragments and the combined one.

**Check.**

- **The select click's selector is `name:scribble_a.txt`** (possibly with
  `,class:UIItem`), **not `name:Items View`**. This is the scroll-invalidation fix.
  If it still says `Items View`, the fix did not take and the rest of the case is
  unreliable — tell me before replaying anything.
- No `+{DOWN}` anywhere; you never pressed it.
- The scrolls are annotated but absent from every scribble.
- The terminal Ctrl+C is annotated with an empty purpose and excluded.
- Replay `explorer_open_desktop` first. It is safe and self-contained.
- Only replay the delete scribble with a throwaway file selected.

---

## Case 2 — Explorer: select a range, then delete

Checks that a range gesture is described honestly and kept separate from the
delete itself.

**Setup.** Create `scribble_c.txt`, `scribble_d.txt`, `scribble_e.txt` on the
Desktop so they sort next to each other. Open Explorer at Desktop **before**
starting `watch`, so the recording begins with Explorer already focused there.

**Do.**

1. Click `scribble_c.txt`.
2. Press **Shift+Down** twice, so all three are selected.
3. Press **Delete**.
4. Ctrl+C in the terminal.

**Expected scribbles.**

| id | kind | contains | description should say |
|---|---|---|---|
| `explorer_select_file_range` | fragment | click + two Shift+Down | Extends the selection to the next items in sort order |
| `explorer_delete_selected_files` | fragment | the Delete key | Deletes every selected item |
| `explorer_delete_file_range` | combined | all four actions | optional |

**Check.**

- The range scribble's description must **not** name only `scribble_c.txt`. It
  selects whatever is adjacent in the current sort order, and the recording never
  captured the other two names. Saying "the next items" is correct; naming three
  files is a hallucination.
- The delete scribble is separate from the range scribble, so a single-file delete
  can reuse it.
- This is the case where the old prompt claimed one file was deleted when two
  were. Read the `recording.summary` too.

---

## Case 3 — Chrome: new tab and open Outlook, from focused Chrome

Your example. Everything here is a state-scoped fragment: Chrome is already
focused, so no scribble should contain steps to launch it.

**Setup.** Chrome open and focused on any page. No other window in front.

**Do.**

1. Press **Ctrl+T**.
2. Type `outlook.office.com` into the address bar.
3. Press **Enter**.
4. Wait for the page to load. Do not click anything.
5. Ctrl+C in the terminal.

**Expected scribbles.**

| id | kind | contains | description should say |
|---|---|---|---|
| `chrome_open_new_tab` | fragment | Ctrl+T | With Chrome focused, opens a new tab; address bar focused |
| `chrome_open_outlook` | fragment | typing + Enter, maybe Ctrl+T | With Chrome focused, opens Outlook mail |
| `chrome_navigate_to_url` | fragment | typing + Enter | With the address bar focused, goes to the typed address |

**Check.**

- No scribble tries to launch Chrome. The starting state is "Chrome focused", and
  the description must say so.
- `context.json` shows a `typing_spans` entry whose text is `outlook.office.com`.
  The URL is baked into the scribble — there are no parameters now, and that is
  expected. Reuse comes from `chrome_open_new_tab` being separate.
- Ctrl+T is recorded as `^t`, not as the letter `t`.
- Chrome's tree is large and noisy. If `visible` is full of unrelated controls,
  that is a recording observation, not a failure.

---

## Case 4 — Notepad: open a file from Explorer, type, save, close

Exercises double-click, typed text, and a save shortcut.

**Setup.** Create `Desktop\scribble_test\note.txt` containing one line of text.
Close Notepad and every Explorer window.

**Do.**

1. Click the File Explorer taskbar button.
2. Click **Desktop** in the navigation pane.
3. Double-click the `scribble_test` folder.
4. Double-click `note.txt`. Notepad opens.
5. Click at the end of the existing line and type ` hello`.
6. Press **Ctrl+S**.
7. Click Notepad's **Close** (X) button.
8. Ctrl+C in the terminal.

**Expected scribbles.**

| id | kind | contains | description should say |
|---|---|---|---|
| `explorer_open_desktop` | self-contained | taskbar + Desktop nav | same primitive as Case 1 |
| `explorer_open_folder` | fragment | double-click on the folder | With Explorer at a folder, opens the named subfolder |
| `explorer_open_text_file_in_notepad` | fragment | double-click on `note.txt` | Opens the file in Notepad |
| `notepad_save_file` | fragment | Ctrl+S | With Notepad focused, saves the open file |
| `notepad_close_window` | fragment | the Close click | With Notepad open, closes it |

**Check.**

- Each double-click is **one** action with `double_click: true`, not two clicks.
- The typed ` hello` appears as one typing span, and the space is recorded as
  `{SPACE}`.
- Ctrl+S is `^s` and is not treated as typed text.
- `explorer_open_desktop` should look the same as in Case 1. Two recordings
  producing the same primitive is the reuse signal we want.
- If Notepad asks to save on close, you did step 6 — but if a dialog appears,
  record what you actually do and note it. Do not invent steps afterwards.

---

## Case 5 — Cross-app noise

Checks that unrelated actions are annotated but never turned into scribbles, and
that a background element is not mistaken for the click target.

**Setup.** Explorer open at Desktop. Chrome open behind it. A terminal visible.

**Do.**

1. Click somewhere in the Explorer file list, then scroll up and down a few times.
2. Click the Chrome taskbar button so Chrome comes forward.
3. Click anywhere on the Chrome page.
4. Click the Explorer taskbar button to come back.
5. Click an empty area of the Desktop wallpaper.
6. Ctrl+C in the terminal.

**Expected scribbles.**

| id | kind | contains |
|---|---|---|
| `explorer_focus_window` | fragment | the Explorer taskbar click |
| `chrome_focus_window` | fragment | the Chrome taskbar click |

Possibly nothing else. This session has no real task, so **few or no scribbles is
a correct outcome**. If extraction fails because the model cannot find a
worthwhile workflow, that is acceptable here — note it and move on.

**Check.**

- Every action still gets an annotation. Noise gets `purpose: ""`.
- The wallpaper click and the random scrolls appear in no scribble.
- Where a click hit an element belonging to a different process than the
  foreground window, `context.json` shows `identity_conflict: true` and a
  `foreground_target`. The scribble must use the foreground one.

---

## Known limitations — do not test around these

- **Windows-key shortcuts record incorrectly.** The Windows modifier has no
  SendKeys prefix, so Win+R is recorded as a plain `r`. Avoid Win+R, Win+S, Win+E
  in these cases; click instead. This is a recorder gap, not an extraction bug.
- **Virtualized lists only expose what is near the viewport.** An item scrolled
  far out of view may not exist in the tree at all. Scroll it into view before
  clicking, as in Case 1.
- **A closed window has no tree.** Scribbles that assume an app is open must say
  so in the description; they cannot be replayed from nothing.
- **Replay success is a tool string, not a verified end state.** After each
  replay, look at the screen and confirm the described end state actually
  happened.

---

## What to send me for review

For each case:

1. The `scribbles.json` (or just its `recording` and `scribbles` sections).
2. The `workflows/<id>.json` for any scribble whose selector you doubt —
   especially the file-item click in Case 1.
3. Which scribbles you replayed, and whether the screen matched the description.
4. Anything the model claimed that did not happen.

I will check the decomposition, the starting-state wording, selector correctness,
and whether any scribble is unsafe to replay.