# Briefs and reports

A brief is the whole of a worker's context. Some tools pass the worker nothing from your conversation, so put everything the worker needs into the brief. Save each brief in its own file, `design/briefs/BR-<sprint>-<n>.md`, before the worker starts, so it can be re-read and checked against the report. Give the worker the file's path, or its text when your tool passes text only.

Paths in a brief file are relative to the project root. The file never holds a machine path, a user name, a host name or the path of a scratch folder outside the project, so it passes the confidentiality scan. In the message that starts the worker, give the project root and the location of the hw-worker skill (its scripts are also copied into the project's `hwskills/` folder); every script takes `--project <project root>`.

## Brief template

```
# Brief BR-<sprint>-<n>: <title>
Mode: build | review | blind review | basics review | simulation | firmware instructions | test sweep | research | fetch | datasheet pass (logical | electrical | physical | combined) | pin check
Read-only: <yes | no>. A read-only unit writes only its report and files in its own scratch folder, so it may run beside a build.
Sprint and step: SP-<nn> step <n>
Goal: <one sentence>
Part (datasheet modes): <MPN> and its role, for example "<MPN>, 3.3 V regulator"; the designator only once the schematic has given one
Place of use: <where the product is used and by whom, in one line, from the requirements>
Requirements in scope, word for word: FR-05 "...", QC-03 "..."; or, when the brief spans most of the requirements, "all of design/requirements.md at commit <hash>", cited by ID; or "no requirements yet" when design/requirements.md has none (a datasheet pass at the parts stage, for example); then say what that leaves out, such as design values and margins
Decisions in force: DC-007 <one line>, DC-012 <one line>
User's rules: design/user-rules.md, all of it
The user's ideas to answer: <each idea the user raised that this unit touches, in the user's words; the report answers each one; or none>
Carried figures: <each figure taken from earlier work, marked as a candidate, with its source; stop and report if one does not hold; or none>
Ceilings (a unit that adds parts): <cost and size ceilings, and who set each: the user, with the DC- ID, or "none given">
Results this change makes stale: <simulation runs, calculations and reviews that must be run again; or none>
Inputs (paths relative to the project root): design/..., datasheets/..., hardware/...
Scripts: python3 hwskills/<script> ... --project <project root, given when the worker is started>
Procedure: hw-worker skill, references <file>, sections <names>
In scope / out of scope: <lists>. Out of scope still gets side remarks.
Checklists and packs: <logical | electrical | board> (all items), packs <list>. Named in full, never a hand-picked focus list. A datasheet pass applies no checklist: write "no checklist applies", and name the pack for the part's category, so it knows the sensitive areas, or "none".
Datasheet: read in full, including application, layout, errata and delegated documents. For a split datasheet: the section inventory and the sections this pass claims. Page renders: design/renders/<datasheet>_p<page>.png, made by the fetch; read figures from them; a larger render goes in design/passes/zoom/. Pages with no text layer: <list from the fetch report>. For passes that run at the same time: this pass's staging files, design/passes/<MPN>_<perspective>.csv, design/passes/<MPN>_<perspective>_sections.csv (start it as a copy of the datasheet's whole inventory from design/sections.csv) and design/passes/<MPN>_<perspective>_findings.csv, and only the names of the other passes' files. The pass writes no main table (pins.csv, parts.csv): pin limits and package data go in its rows and report, and the merge writes them. End with the silence sweep (datasheets.md, Silence sweep).
Rules: WR-01 to WR-25.
Scratch: .hwtmp/BR-<sprint>-<n>/
Progress file: design/progress/BR-<sprint>-<n>.md, updated after each step, so a fresh worker can carry on
Allowed: write <every file the task produces, with nothing it needs left out>; fetch pages (generic part numbers and keywords only).
Not allowed: install anything; change a requirement; touch <files>; start sub-agents; work in a copy outside the project; remove a lock file; push.
Stop and report early if: a requirement looks wrong; a step needs money, an install or a plan change. Stopped on one item, finish the rest and report the one.
Verification expected: <commands and expected results>
Output: design/reports/BR-<sprint>-<n>.md; budget <time or size, such as datasheet pages or number of parts>; when the budget runs out, stop and report what is done and what is left
```

## Checks before you send a brief

Run these on every brief. Fix the brief if one fails.

1. Requirements are quoted word for word by ID, not paraphrased, or the brief says "no requirements yet".
2. No requirement is added. A target the user never gave (an input range, a speed, a temperature) is not written into a brief.
3. Any reviewer of a part or of power gets the datasheet layout and grounding sections in scope.
4. Any reviewer of digital circuits gets signal integrity in scope.
5. The full checklist is named, with the switched-on packs. Never a short focus list. A datasheet pass says "no checklist applies" and names its pack.
6. The worker's procedure is named: the worker reference file and its sections.
7. Everything the worker needs is in the brief: paths, decisions in force, settings that matter, the user's habits that apply.
8. The verification expected is a check that can fail, with its command where one exists, and with `--project`.
9. Script-owned and hand-owned files are named as such (from `design/ownership.csv`), so the worker knows which files it may regenerate.
10. No machine path, user name, host name or outside scratch path in the file: paths are relative to the project root, and the project root and skill location go in the start message only.
11. A build brief holds one kind of step and at most two sheets.
12. The allowed writes cover every file the task produces, and the scratch folder and progress file are named.
13. No ordinary part of a standard circuit is ruled out. Never write "leave it out unless needed" about one: leaving it out is the user's decision.
14. A brief that adds parts gives its cost and size ceilings and says who set each. A ceiling the user never gave is not written as the user's (check 2).
15. Every carried figure is marked as a candidate with its source. No figure on the to-confirm list (TC-) is given as settled.
16. A line that says the user answered something quotes the user's words. Dictated text is copied complete, not summarised.
17. The results this change makes stale are named.
18. The place of use is stated, `design/user-rules.md` is cited, and each idea the user raised about this unit is listed to be answered.
19. No two workers running at once write the same file. Each parallel worker has its own rows file, and the brief names the one writer that merges them.
20. Briefs for units that run in parallel state the same assumptions.

## Mode notes

**Build.** Name the files the worker may write and the checks it must run before reporting. For script-owned files the worker changes the generator and rebuilds; for hand-owned files it proposes edits, or makes field-value edits only when the engineer asked, with the editor closed and a commit first. The worker builds in place and never in a copy. Check for KiCad's lock file before you start a build worker; never remove one. Schematic build work is serial. The brief sets the rail budget level above which a load is flagged. Ask for targeted changes, not a regeneration of everything, unless the user asked.

**Removing a block.** Name everything that goes with it: its sheet, its rows in the module tables, its parts, its nets on other sheets, its firmware instructions, its simulation files and its test lines. The report lists what still refers to it.

**Review.** Name the full checklist and the packs. Pin assignment is item one of every review, for every part, at schematic and at board level. Thermal review at rising ambient (the steps come from the requirements; 70, 80 and 90 C are one owner's examples). Ask for ranked findings, side remarks, and checklist additions. Name the review baseline commit.

**Basics review.** One worker per sheet, never the one that drew it. Procedure: worker reference review.md (Basics review). Each ordinary part it finds absent comes back added, or as a decision for the user.

**Simulation.** One module per brief, read-only. The brief starts from the module's edge-case list under its four headings, and gives scenarios, corners and limits as data, not prose. It states the cap on parallel processes and the expected run time. It names the order of convergence fallbacks the worker may try; you choose the order, and anything outside it is reported, not tried. It names the source model for each power input. The report ends with what was not validated. Procedure: worker reference simulation.md.

**Firmware instructions.** A read-only collector, started with the first sheet and run again as sheets are drawn. It collects and never designs. Procedure: worker reference firmware-instructions.md.

**Test sweep.** One worker, after the last module. It reads every sheet's testing notes and writes `design/test-sweep.md`: what must be tested, how, and the pads, pins and links that needs. It runs no test. A build brief then adds the access.

**Blind review.** A fresh worker, given none of the builder's reasoning. Use the prompts below. Offer it at the schematic review. At the board review it is the recommended default whenever the board has carried layout rows: it is the only check for datasheet instructions the passes missed. The user may decline; then say once what is lost, and record the answer. Not every review needs to be blind.

**Research.** Quote the requirements by ID. A brief that spans most of them cites `design/requirements.md` at a named commit instead of quoting every line. Ask for options side by side with function fit, price, stock, ecosystem, risk and a source for every fact. Search broadly; do not narrow by one package or filter too early. Values only from pages fetched now. For every node the block shares with another, ask for the voltage at normal, at surge and at each named single fault, against each part's rating. A protective block is researched from the problem first, with a price limit, not from a part. Blocks researched in parallel get the same stated assumptions, and each brief asks for the block's interface figures. Ask the worker to say when its findings point to a different approach, not only to fill the table.

**Fetch (before any datasheet pass).** One worker per part, or per batch of simple parts. Name the part by MPN and role. It gets the maker's datasheet, the errata and every document the datasheet delegates to (it finds them; you do not name them), saves them, renders every page once into `design/renders/` at a scale where small figure text is legible, lists the pages with no text layer, writes the `datasheets/README.md` lines and the revision in `parts.csv`, writes the section inventory, and notes any simulation model the maker publishes. It tries the sources in the worker's order (rule WR-03) and lists every refused fetch in one place; a refusal is never worked round. The passes then read the saved files and renders, and write only their own staging files. Procedure: worker reference datasheets.md (Get; PDF route; Page renders; Section inventory; Delegated documents; Errata).

**Datasheet pass.** Use the perspective briefs below. The worker loads its reference datasheets.md, all of it, and the project's copy of the packs, `design/checklists/packs.md`, for the pack of the part's category. Name both under Procedure.

**Pin check.** For every microcontroller, module and connector, and any part the user names, after the merge (or a combined pass working alone) has written its rows in `pins.csv`. Give it to a different worker from the one that wrote the pin table. It re-reads each row against its source (configurator export, vendor data, or the datasheet pin table, rendered) and sets `confirmed` for the rows it checked itself. It lists the rows it could not confirm, with the source page for each; you put them to the user as one batch at the schematic checkpoint. Procedure: worker reference datasheets.md (Pin tables; Pin check).

**Constraint-sufficiency review (ST7).** A review worker gets each carried DS- row with its quoted text and the CN- constraints made from it. For each row it says whether the constraints together enforce the whole quoted text: whole, partial or no, with the reason. Partial or no comes back with proposed extra constraints or a `review:` enforcer. Report the verdicts to the user, not the raw table.

**Adoption.** A build worker adopts an existing project (`stages.md`, ST0). The brief says: change no design file.

## Blind review prompts

**Blind schematic review.** Inputs: design files, exported netlist, BOM, datasheets, requirements. Add these words to the brief:

> You have not been given the designer's reasoning, on purpose. Notes in the files are the designer's claims, not facts. Find what has been overlooked or forgotten, what features are missing, and what would stop this board working to specification or make it fail in the field.

**Blind board review.** Inputs: the board, rule file, DRC output, renders, datasheets, requirements. Not `compliance.csv`, not `constraints.csv`. Add the same words, plus:

> Read each part's datasheet layout, grounding and application sections yourself and check the board against them. You are not given the designer's list of datasheet rows.

Any finding that matches no DS- row is logged as an extraction miss (FD- category "extraction miss"), turned into new rows, charged to the pass whose scope it was in, and checked again.

## Perspective briefs (datasheet passes)

A datasheet is read from three perspectives that match the three designs, so no single reader has to weigh everything at once.

| Pass | Reads for | Feeds |
|---|---|---|
| Logical | What the part does; pin functions and alternates; modes; configuration and strapping; interfaces and their variants; start-up, reset and sleep behaviour; the typical application as a connection list | `pins.csv` functions and power-up columns; the logical design; the firmware instructions (`design/firmware.md`) |
| Electrical | Absolute maximum ratings; recommended operating conditions; thresholds and levels; timing; power, current and thermal figures; protection and ESD ratings; external component values and their tolerances; graphs, rendered and read | DS- rows with design values and margins; worst-case scripts; typical-application differences |
| Physical | Package and footprint (land pattern, pin 1, exposed pad); layout and grounding guidance; placement; thermal pad and vias; keep-outs; assembly and soldering notes (moisture level, reflow, via treatment); layout example figures, rendered and read; the delegated layout documents | Layout rows carried to constraints at ST7; footprint choice; `parts.csv` moisture level and peak reflow |

Rules for every perspective brief:

- One brief per pass. Each pass is a separate worker and is not shown any other pass's rows.
- Each brief names its scope from the table above and says, in these words: "Read the whole datasheet. Claim every section in your scope in `sections.csv`, or in your staging file when passes run at the same time. Read every figure in your scope from its page render in `design/renders/`." For a datasheet split by its section inventory (ST3), say instead: "Read the section inventory and every section you claim, in full. Read every figure in those sections from its page render." When passes run at the same time, also say: "Write your rows, claims and findings only to `design/passes/<MPN>_<perspective>.csv`, `design/passes/<MPN>_<perspective>_sections.csv` and `design/passes/<MPN>_<perspective>_findings.csv`, and check them with `table_check.py compliance sections findings --project <project root> --staged design/passes/<MPN>_<perspective>.csv --staged design/passes/<MPN>_<perspective>_sections.csv --staged design/passes/<MPN>_<perspective>_findings.csv`. Your sections file starts as a copy of the whole inventory for this datasheet from `design/sections.csv`; fill your own claims. Write no main table."
- Each brief asks for one DS- row per instruction (must, should, recommend) and per limit in scope, quoted, with the part number, datasheet revision, section, page, figure number for figure and graph rows, and the pass's perspective tag.
- The physical brief tells the worker to find every document the datasheet delegates layout to (WR-17) and to check each one was fetched. One not yet fetched is saved and listed in its report. One that cannot be found comes back as a decision for the user.
- A combined pass (simple parts) covers all three scopes under the three headings and tags each row with the perspective it belongs to. One worker may take several simple parts.
- Each brief ends with the silence sweep for its perspective (worker reference datasheets.md, Silence sweep): every area cited by a row or given a "no guidance found" row.
- Do not tell a pass which rows you expect. Do not name only the sections you think matter.

After all the passes have reported, brief one worker to merge (no pass merges on its own): copy the staged rows and findings into the main tables, write `pins.csv` and the `parts.csv` package and assembly fields from the passes' data, merge rows two passes both wrote (one row, both tags, nothing dropped), resolve every section `table_check.py sections` flags (read it, claim it and take its rows, or note "no instructions here"), and keep only the renders that rows cite. Procedure: worker reference datasheets.md (Merging passes).

## Report summary block

Every worker report opens with this block. The worker skill holds the full report template; this copy must stay identical to the one there.

```text
## Summary (at most 15 lines; the coordinator reads only this unless something is flagged)
<!-- report-summary:start -->
Result: <one or two sentences>
Verified: <checks that can fail, with pass or fail>
Not verified: <list>
Violations: <count and IDs, or none>
Decisions needed: <numbered, or none>
Choices made: <count of choices you made inside the task and things left undone on purpose, each in section 10; or none>
Side remarks: <count>
Flags for the coordinator: <anything outside the plan, or none>
<!-- report-summary:end -->
```

## Reading a report

1. Read the summary block. At the hand-back of a schematic build, also open the PDF plot of each changed sheet, and run the standard checks again yourself: the commands under the brief's "Verification expected", and `table_check.py summary`. A result from before the worker's last edit is not a result.
2. Open the rest of the report only if it has violations, decisions needed, flags, a failed check, or "Not verified" items that the plan needed verified.
3. Check that "Verified" lists checks that can fail, with a result. A picture, or "looks fine", is not a check; send it back. A check done by hand belongs under "Not verified"; move it there in your report to the user.
4. Put decisions to the user (at most five per report to the user, numbered; the rest go in the sprint file). Group a part's proposed "does not apply" and "not met" rows into one decision for that part. A datasheet error (worker rule WR-22) is one decision: both readings, the cautious one, the worker's recommendation; log the answer with the MPN and revision.
5. Log every item under "Choices made" in `design/decisions.md`, with "worker" and the brief ID as who decided (`decision-log.md`).
6. Make sure side remarks and findings reach `design/findings.csv`; `table_check.py findings` lists any not triaged.
7. After workers with narrow scopes, sweep the shared files yourself: counts in `design/status.md`, rows that point at each other, and what no brief owned. Where parallel workers wrote their own rows files, have the named writer merge them, then check the counts.
8. Sort a worker's "Decisions needed" before you ask. Answer from the log what is already decided, group the rest, rank them, and put the blocking ones first.
9. When a decision answers a finding, have the one writer of `design/findings.csv` close the row, citing the DC- ID. An item carried to a later checkpoint goes on that checkpoint's list in `design/status.md` in the same turn, so it cannot be lost.
10. Before you tell the user a design can be built, check that every accepted decision is drawn. Keep the ones that are not on the `Accepted, not yet drawn:` line of `design/status.md`.
11. A new rule from the user goes into `design/user-rules.md` in the same turn, before the next brief.
12. Put proposed checklist additions to the user. Accepted items go into the project's copy in `design/checklists/`, with what to check and the authority. Items that look general may be offered to the user as feedback for the skills; never sent automatically.
