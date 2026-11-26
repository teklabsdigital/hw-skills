# Reporting to the user, and reading the reply

Read this when you report to the user, put decisions to them, read a short reply, pause or resume, or amend a brief. The report template is in SKILL.md, "Reporting".

## Contents

The report; What a report says; Numbered decisions; Recommending; Reading a reply; Answering a question; Before you ask; Pause, end of day, interruption and restart; Amending a brief.

## The report

- Open with the main points and any failure. Detail comes after, and only as much as the step deserves: a small step gets a few lines.
- Keep to the length the Reports setting gives. When there is more, link the file that holds it.
- A checkpoint report opens with the main points and one whole proposed course the user can accept with one word. Never hand the user a list of parts to assemble into a plan.
- If a part or value the user chose was stopped by a check, that is the first line of the report, with the reason (see "Recommending").
- Close every report with the four closing lines of the template: the short answer, who acts next, the one standing list of what waits on the user, and how far it is to the next thing the user can look at.
- A report that rests on a worker report, a plan or a plot ends with clickable links to those files. A plan is linked beside the question that asks for its approval.
- While schematic work runs, link the PDF plot of a sheet, not the schematic file. Opening the schematic file in KiCad locks the project and blocks the next build.
- Before you say work is committed, check with git. Do not say it from memory.

## What a report says

- Tell each open item or fault case as a short story in physical terms: who does what, what happens to the product, what the fix is and what it costs.
- "Risk" always says risk of what.
- Explain terms the user may not know. Keep the standard engineering terms the user does know: plain English must not replace them.
- Show every block price, and every pivot, beside the running cost of the whole board. A draft parts list comes with a cost list ranked from the dearest, and one line on what each main part does.
- When a fix gains one margin by spending another, show both sides. It is a trade, not a gain.
- A default or a reading you took without the user's answer stays in the report's list until the user has seen it.
- An assumption that nobody can measure yet stays on the list. Do not ask about it again until something changes.

## Numbered decisions

- Each open decision has one running number. A number is never used again, even when its decision is closed.
- Each time decisions are put to the user, and on every resume, restate each one in full plain words. Never by its number or label alone.
- Each decision gives its options, the cost effect of each, and your recommendation.
- Ask a few things at once: at most five. When there are more, rank them by what blocks work, ask the top ones, and say what you held back and where it is listed.
- An offer to commit is its own numbered item.
- Before you offer a fix as an option, have a worker check that it can be built. A fix the user accepts stays on the status file's list of what is accepted and not yet drawn until it is on a sheet.

## Recommending

- Before a recommendation goes to the user, test it against the requirements and the user's stated principles (`design/user-rules.md`). If it departs from one, say so in the same line.
- A recommendation that reverses an agreed figure or an earlier decision says so in the same line, with the ID of what it reverses.
- When you rank options, the one most protective of the circuit against what a user may do comes first, ahead of cost and part count. "Safe" means that. A protective trip is an emergency: a design in which it occurs in normal operation is not a safe option.
- The user's own choice of a part or value still passes through every check. If a check stops it, hold the choice. Do not drop it and do not force it. Say so first, with the reason.
- When the user leaves a choice to you, name the one case that would overturn your choice, and check that case before you act on it.

## Reading a reply

- A bare "ok" or "yes" covers only the items your last message numbered, and only those that gave one stated option. An item with two options open, or marked "to confirm", is not settled by "ok".
- Silence is never a yes. A partial answer settles only what it answers. A short answer does not settle items you did not ask.
- Map a blanket reply ("all fine", "go") to every numbered item it could cover, and read the result back in one line per item.
- Say back, before use: dictated names, part numbers and numbers; any answer that contradicts an earlier one; and your reading of any unclear words.
- When a new answer contradicts an earlier decision, say so at once and change neither until the user chooses.
- A to-confirm line (TC-) is marked answered only when the user's words settle that line's own question. Quote those words. If the answer was to a related line, this line stays open and says what is missing.
- A question the user asks is a question. Answer it. Do not write it into the requirements.
- An idea the user offers goes into the next brief as an item the worker must answer.
- A link the user pastes is stored without its tracking parameters.

## Answering a question

- A direct question gets a direct answer in the same turn: the best answer, and how sure you are. Say which parts are from memory and not verified.
- "Will it work?" and a candidate the user names get the same: one answer with its confidence, then what would confirm it.
- If your first answer missed, give one best guess next, not a list.
- When the user's picture of a failure is wrong, say so in your first reply. When the user is reassured, say what the explanation does not cover.

## Before you ask

Search `design/decisions.md` for an earlier answer before a question goes to the user. If the user has already said it, use it and cite the entry.

## Pause, end of day, interruption and restart

**Pause or end of day.** When the user says to pause or stop for the day:

1. Let running workers reach a safe point, or stop them and note which were stopped. Read each one's progress file (`design/progress/BR-nn-nn.md`).
2. Write to `design/status.md`: the sprint step in progress, the briefs out and their state, the open decisions with their numbers, and the next step.
3. Log what was decided since the last report, and mark it seen once you have listed it.
4. Commit only per the commit settings, or offer a commit as a numbered item. Check with git before you say it is done.
5. Say, in a few lines: what is done, what is half done and where it stands, what waits on the user, and the first step of the next session.

**Interrupted run.** When a run was cut off (a reset, a crash, a closed session), check before anything else:

1. `git status` and the diff: which files changed, and whether each change is whole.
2. Each brief that was out: its report, or if none, its progress file.
3. KiCad's lock files. If the project is open, ask the user to close it. Never remove a lock file.
4. The scratch folder `.hwtmp/`, for half-written output.
5. The standard checks and `table_check.py summary`, run now. A result from before the interruption is not a result.

Then report what you found and ask before you repair anything outside the plan.

**Resume.** Run the start-of-session routine. Restate every open decision in full plain words, with its number.

**Restarting a stopped worker.** Start a fresh worker on the same brief, with this block added to the brief as a dated amendment:

```
Restart, <date>. The earlier run of this brief stopped at: <step, from its progress file or report>.
Already done and checked: <files, each with the check that passed>.
Not done: <list>.
Do not trust: <files that may be half written>. Check each before you build on it.
Start from: <step>.
```

## Amending a brief

- A brief is amended by a dated addition at its end. It is never rewritten: the report must be checkable against what the worker was told.
- Amend when the change is small and inside the brief's scope and allowed writes: a corrected figure, an added item to answer, a narrowed scope.
- Stop the worker and write a new brief when the goal, the mode or the allowed writes change, or when what the worker has already done rests on what changed.
- New input from the user reaches a running worker only through an amendment, passed on by whatever route the tool gives. If the tool gives none, let the worker finish or stop it. Never assume a running worker has seen the user's latest words.
- If the new input changes a requirement, update `design/requirements.md` first, through a worker, and log the decision. A later brief then quotes the new text. A brief never quotes a requirement that the file does not yet hold.
- When a report comes back with decisions, sort them before you ask the user: those the log already answers, those inside the approved plan (you decide and log them), and those that are the user's. Only the last kind is put to the user.
