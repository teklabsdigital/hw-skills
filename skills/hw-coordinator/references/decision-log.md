# Decision log

`design/decisions.md` is a detailed log of every decision in the project. You keep it from the user's first message to the end. It holds the user's decisions, the choices you make on your own judgement, and the choices workers make inside their tasks, each marked with who decided. Nothing is decided silently: whatever was chosen on the user's behalf reaches the user in a report.

## What goes in

- **The user's decisions:** the first-session table and each change to it, plans approved, parts chosen, proposals accepted or declined, waivers, pivots, going on with items open at a checkpoint, the answer on a datasheet error.
- **Your own choices:** a default you applied without asking, a switch you inferred, the order of the work, what a brief covers and leaves out, a worker's proposal you accepted inside the approved plan, a step you deferred.
- **Workers' choices:** every line under "Choices made" in a report summary (detail in its section 10). Log each one, with "worker" and the brief ID as who decided.
- **Things not done, with the reason:** a check skipped or not run, a review or a blind review declined, a guideline bent, a recommendation not taken, simulation declined, a delegated document not fetched.
- **Datasheet errors** the user decided (the worker skill's rule WR-22), naming the MPN and the datasheet revision, so the question is not asked again when the part is used again.
- **Questions answered,** while the "log every prompt" setting is on. It is on by default: the log is how decisions are tracked and how the skills are improved. Each question you put to the user and the answer goes in as kind "question answered", with the user's words quoted. It is a lighter entry in the same form: Options and each part of Affects say "none", and Status is "closed (answered)". An answer that decides something is a full decision entry instead. With the setting off, only decisions are logged.

A finding is not a decision. It becomes one when someone chooses what to do about it.

## Who writes it

You are its only writer. Workers never write it: they report their choices and proposals, and you log them. In a tool with no sub-agents, where you run the units yourself, the same holds. The first entry is the user's first message, in the user's words. The first-session table follows, written before the setup worker starts. `table_check.py log-append` adds an entry with the next number and today's date. It never changes an earlier entry: when the new entry replaces one, set the old entry's status yourself, as the command prints.

## Entry form

<!-- decision-entry:start -->
```
## <What was decided, in one plain sentence> (DC-012)
Kind: <decision | waiver | pivot | not done | question answered>
Decided by: <user | coordinator | worker BR-nn-nn>; seen by user: <yes, date | no>
Date: <YYYY-MM-DD>
Stage: <STn, or several>
Options: <each option considered, the chosen one marked>
Reason: <why; cite FR-, QC-, DS-, FD- IDs and datasheet sections>
Affects: requirements <IDs or none>; parts <...>; schematic <...>; board <...>; cost <effect or none>
Status: <in force | open | closed (how, and DC-nnn if a later entry ended it) | superseded by DC-nnn>
Replaces: <DC-nnn, or several; only when this entry changes earlier decisions>
```
<!-- decision-entry:end -->

## Rules

- Append only: a new entry goes at the end with the next DC- number.
- Never rewrite an entry. Only its `Status` and its "seen by user" may change later.
- A change of mind is a new entry with `Replaces:`. The old entry's `Status` becomes "superseded by" the new one. Nothing is overwritten.
- One entry may replace several: list every ID on its `Replaces:` line, and mark each old entry "superseded by" it.
- An entry that a later one ends without changing it is "closed (how, DC-nnn)". This covers an open or not-done entry that a later answer settles, and a reading that hung off a decision since replaced. "superseded by" is only for an entry named on a `Replaces:` line.
- A wrong field in an old entry, such as `Affects`, is corrected by a new entry that names the old one and gives the right value.
- `Affects` is always filled: each of its parts names what changes, or says "none".
- When an entry replaces or ends another, set the old entry's `Status` in the same turn.
- A figure in `design/status.md` that comes from a decision is copied from the entry, never retyped from memory.
- A to-confirm line (TC-) is marked "answered (DC-nnn)" only when the entry quotes the user's own words. Your reading of a short reply is not an answer; ask.
- Search the log before you ask the user a question. It may already be answered.
- Anything you or a worker decided carries "seen by user: no" until you have listed it in a report to the user.
- `table_check.py decisions` checks the fields, the IDs and their order, and the back-pointers. `table_check.py summary` lists the entries the user has not seen.

## Reporting

- Every report to the user, and always the last one of a session, has the line "Decided on your behalf since the last report:", listing each unseen entry by its plain statement, with the ID in brackets and who decided. Then mark those entries "seen by user: yes, <date>".
- The user may reverse any of them. A reversal is a new entry that replaces the old one.
- At the start of a session, read the last ten entries and every entry the user has not seen.
