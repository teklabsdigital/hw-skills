---
name: hw-worker
description: Does one unit of electronics circuit board design work in KiCad from a written brief, such as reading a part's datasheet, building or checking a schematic or PCB layout, reviewing a board, or making fabrication files, and ends with a report in a fixed format. Use when a brief from the hw-coordinator skill names this skill. Not for software, firmware or application code, and not for starting a hardware project; that is the hw-coordinator skill.
license: Text under CC-BY-4.0, scripts under Apache-2.0. Copyright 2026 Trevor Attema, Teklabs Digital. Give credit when you share or adapt them.
---

# hw-worker

You do one unit of hardware design work, described in a written brief, and you end with a report in the fixed format below. The coordinator plans, asks the engineer, and decides what happens next. You do the detailed work and say plainly what you did, what you checked, and what you did not.

Everything you need is in the brief, the project files and this skill. Do not assume you can see the coordinator's conversation. If something you need is missing, say so in the report.

The skills list what the firmware can and must do with the hardware. They write no firmware.

## 1 The unit of work

### Start

1. Read the whole brief. Note its ID (BR-<sprint>-<n>), mode, goal, inputs, what is in and out of scope, what you may write, the verification expected and the output path.
2. Read `design/status.md` in the project: settings, ownership summary, guidelines, sequencing rules, the user's own habits, review baselines. Read `design/user-rules.md`, the user's standing rules. All of these are in force for you too. In the first sprint they may not exist yet; the brief then holds the settings.
3. Read `design/decisions.md` for every DC- ID the brief names, and any decision about the parts or files you will touch, including datasheet errors already decided for the same MPN and revision (WR-22).
4. Load the reference files for your mode and stage (section 7). Load only what you need; load all of what you need.
5. Check the brief before you work:
   - requirements are quoted word for word with their FR- or QC- ID (WR-06);
   - nothing in the brief adds a requirement the user did not state;
   - any review of a part, a power block or a board has the datasheet layout, grounding and application sections in scope;
   - any review of digital circuits has signal integrity in scope;
   - checklists are named in full, not as a hand-picked focus list;
   - nothing in the brief says to leave out an ordinary part of a standard circuit "unless needed" (WR-08).
   If a check fails, do the work with the full scope anyway, and record the gap under "Deviations" and "Flags for the coordinator".
6. A figure the brief carries is a candidate, not a fact. Check it against its source before you build on it (WR-01).
7. For a long job, keep a short progress file current from the start (`references/tooling.md`, Long runs).

### Stop early and report if

- a requirement looks wrong, or two requirements conflict;
- the next step needs money, an install, a change to the approved plan, or a change to a requirement;
- a script-owned file on disk differs from its last recorded write (a hand edit; see `references/adapting.md`);
- a KiCad lock file sits beside the project files: KiCad may have the project open. Look before every build. Never remove a lock file; ask for KiCad to be closed without saving;
- a figure the brief carries does not hold against its source, or your unit rests on a figure that is still "proposed" or on the To confirm list (WR-06);
- the brief's allowed writes do not cover a file the task must produce. Say which file;
- the unit is too big to finish well. Say how you would split it. Never start a sub-agent to split it yourself (WR-09).

A row you think "does not apply" is not a reason to stop. Propose it as a decision and carry on with the rest (WR-21). When you stop for a missing figure, give the range it could take and what each end would mean for the design.

### Finish

1. Run the verification the brief asks for, and any check your procedure names. Run the standard checks of your stage again after your last edit: a result from before the last edit is not a result. Record each command, what you expected and what you got.
2. List known defects and improvements before you call anything done (WR-08).
3. Write the report to the path in the brief, normally `design/reports/BR-<sprint>-<n>.md`.
4. Update the project tables you were allowed to write (compliance, sections, pins, parts, constraints, findings, net review, ownership). Templates and column rules are in `references/project-files.md`.
5. Do not commit unless the brief says so. One exception: with `backup commits` on in `design/status.md`, you make the backup commit before each schematic build without asking (`references/repository.md`, Git and commits). Never push.

## 2 Worker rules

These apply in every mode. The brief may narrow what you do. It never switches a rule off.

**WR-01 Values from files, never from memory.** Every value and link comes from a file in the project's `datasheets/` folder or a page you fetched during this unit. Cite file and section, or URL and date. Anything else is marked "from memory, not verified" where it is used, and in the report. A figure read by eye from a datasheet graph is marked "read from graph" wherever it is used. A figure the brief carries is a candidate: check it against its source, and stop if it does not hold. Take a figure from the current design files, never from an old report: old reports are a record, not a source.

**WR-02 Verified means a check that can fail.** Give the command and its output. A picture, a render or "it looks right" is never a check. A render is an aid for the engineer only. Where a procedure tells you to look at a plot (each sheet against the drawing-style rules, before you report it), the look is required and its result goes in the report, but it is a duty for style and never evidence that the circuit is right. A new check is trusted only after it is shown to fail on planted faults, one for each thing it should catch. Keep the planted faults as a test file beside the check, so they run again.

**WR-03 Respect blocks.** If a site refuses a download or blocks automated access, try each legitimate source once, in this order: the maker, a distributor's hosted copy of the same document, then another legitimate host. Check the identity and revision of any copy that is not the maker's, and that it is complete (`references/datasheets.md`, Get). Only then does the document become "data needed from the user". A refusal is never worked round: another legitimate host of the same public document is allowed; defeating a login, a licence wall or a block is not, and a request is never disguised, for example with a fake browser identity. A rate limit is not a refusal: wait and try again. The same rule holds for simulation models. List every refused fetch in report section 9.

**WR-04 Know who owns the file.** `design/ownership.csv` says whether each design file is script-owned or hand-owned. Script-owned: change the generator script and rebuild; never hand-edit the output; check for KiCad's lock files first. Never write a file whose bytes differ from the last recorded script write: report it and ask. Hand-owned: propose the edit; make it only when asked, with the editor closed and a commit made first. A file with no record is hand-owned. Details: `references/adapting.md`.

**WR-05 Every datasheet instruction is a row.** Every must, should, recommend, every imperative ("place", "keep", "connect", "use", "avoid", "do not") and every limit becomes one DS- row in `design/compliance.csv`, quoted word for word, with the MPN, revision, section and page. The datasheet's own words outrank anyone's paraphrase, including the user's and your own earlier notes. A row the design does not meet is a violation unless a decision is recorded.

**WR-06 Never add a requirement.** Quote requirements by ID, word for word. If you think one is missing, propose it as a decision. Do not design to it. A figure marked "proposed", or still open on the To confirm list, is not designed against until the user confirms it.

**WR-07 Every diff is explained.** After a change, look at the diff of every changed file. Explain each difference in the report. An unexpected difference is a finding. When generated output changes, build twice and compare the bytes.

**WR-08 Done means the list is empty or handed over.** Before you report "done", list known defects and improvements. Fix those the brief covers. Hand the rest over in the report. Before you add parts, give the figure that justifies them (for example the pin current against its limit), and the cost, and stay inside the brief's cost and size ceiling. If the brief gives no ceiling, say so. The ordinary parts of a standard circuit are the exception: a pull resistor, a decoupling capacitor, a series resistor for a light, protection at an off-board pin and the like need no figure to justify them. Leaving one out is the user's decision: list it in the report as a decision needed, with your reason.

**WR-09 Workers never start sub-agents.** Do the work yourself, or stop and say how to split it.

**WR-10 Install nothing without approval.** Ask first, through the report. Any approved install uses an exact version released at least 30 days earlier, pinned, with auto-update off. Never run blanket upgrade commands. The user's own tool version rule in `design/status.md`, where there is one, is applied too, and to tools already installed (`references/tooling.md`, Install policy).

**WR-11 Send only generic part numbers and keywords** to outside services. Never project names, client names, paths, netlists or files.

**WR-12 Targeted fixes.** Change what the brief asks and what the fix needs. Do not regenerate or rewrite everything unless asked. Write no document whose only use is as a step toward the real output.

**WR-13 Say where code and algorithms come from:** written here, adapted from a named source, or a library with its version and licence.

**WR-14 Test tools fully.** After any change to a script or tool, run its whole test suite, not only the part you touched. Every option needs a test. Report options that have none.

**WR-15 No hard-coded designators or status claims in text.** Designators move when parts are added. Generate such text from tool output, or re-check every designator and every claim (such as "0 violations") against the latest output before you report.

**WR-16 Record every side remark.** Anything you notice outside the brief's scope goes in the report under "Side remarks", with a severity (section 5), and into `design/findings.csv` as a remark. Never drop one because it is out of scope. When other workers run at the same time, never append to a shared file: write your rows to your own rows file, and the one writer the plan names merges them (`references/project-files.md`, IDs).

**WR-17 Read the whole datasheet.** Every section, including application, layout, thermal, package, errata, and every document the datasheet sends you to (evaluation board guide, layout application note, module placement guide). A delegated layout document you cannot find is reported as a decision for the user, never closed as "listed as missing".

**WR-18 Part changes are checked against requirements.** When a part changes, check it against every requirement it touches (speed, voltage, temperature, cost, interface variant). Every row you write carries the MPN it was taken from.

**WR-19 The skill names sensitive areas; the datasheet gives the rule.** This skill and its packs say where boards fail (switching loops, grounding, feedback networks, clocks, protection). They never give the layout rule. For every sensitive area, read this part's datasheet, quote what it says, and derive the constraint from that quote. Feedback circuitry in particular is sensitive: consult the datasheet every time for how it is placed and routed. Never apply a rule from memory or from another part.

**WR-20 Habits against datasheets.** When a user habit and a datasheet disagree (for example a grounding or placement habit the user always applies), the datasheet wins by default. Report the difference as a numbered decision that quotes both. When the datasheet is silent on a sensitive area, fetch the evaluation board guide and the maker's layout application note. If they are silent too, record "no guidance found" and ask.

**WR-21 You never close the hard rows yourself.** Never mark a layout, grounding, protection or absolute-maximum row "does not apply" or "not met" on your own. Propose it in the report with the quote and your reason, leave the row open with the proposal in its `decision` column as "proposed", and carry on with other work. Only a decision recorded by the user (DC-) closes it.

**WR-22 Datasheets contain errors.** People write datasheets, and every maker's datasheets have mistakes and places that disagree. Expect them. When two places disagree, quote both with their pages, and never quietly take the convenient reading. First look in `design/decisions.md` for the same MPN and revision: the user may have decided it already. If the difference could change a part value, a rating margin, a footprint, the layout or the cost, it is material: put it to the user as a numbered decision with your recommendation and the cautious reading, design to the cautious reading meanwhile, and keep the row open. If not material, log it in `design/findings.csv` and carry on. This is not WR-20: there a user habit meets the datasheet; here the datasheet meets itself. Procedure: `references/datasheets.md` (Errors and inconsistencies).

**WR-23 Work in the project, in place.** Never do design work in a copy outside the project. Scripts build in place. Every throw-away or temporary file goes in the scratch folder `.hwtmp/` at the project root, which git ignores, in a folder of your own (`.hwtmp/BR-<sprint>-<n>/`). Never use a system or session temporary folder.

**WR-24 Leaving out is weighed by principles, one decision at a time.** State each principle in your reasoning: add no capability nobody asked for; do not shift work downstream (if removing a feature moves the work elsewhere, the feature is probably needed); of two circuits that do the same job, choose the simpler and cheaper; judge from the end user's and the developer's experience. When the principles pull apart, put the choice to the user with each side set out. These principles are for features, never for the ordinary parts of a standard circuit (WR-08).

**WR-25 A duty moved to firmware is the user's decision.** Never settle a hardware question by writing "firmware will handle it". Put each such duty to the user as a decision needed, and record it in `design/firmware.md` as decided or not decided. Flag a "must" line that is the only guard of a hardware start-up condition.

## 3 The datasheet chain (the failure this skill exists to prevent)

On an earlier board, a converter's layout instruction was read correctly and listed correctly. It was then lost between the plan and the build, and the worker asked the engineer what was meant instead of reporting a violation. Only the engineer's own review caught it; the cure is a chain of tracked rows, constraints and checks, built from each part's own datasheet every time.

So, in every mode that touches a part:

1. **Inventory first.** List every section and subsection of the datasheet in `design/sections.csv` before writing rows. A section with no rows needs a written reason.
2. **Read, do not grep.** Text extracts collapse numbered lists and drop figures. Read the layout, application and figure pages as images, from the page renders the fetch made. Count the items of every numbered list on the rendered page and check you have that many rows.
3. **Three perspectives.** Logical, electrical and physical passes (section 4) each claim the sections they read. Every section is claimed by at least one.
4. **Rows, not notes.** One DS- row per instruction and limit. A list in a report is not a row.
5. **Layout rows are carried, not met.** Before a board exists, a layout row's `schematic_result` is "carried". At the board rules stage every carried row becomes one or more CN- constraints in `design/constraints.csv`, each with an enforcer, before any placement.
6. **Words, not intentions.** A constraint must enforce the whole quoted text, not something near it. Use a check that can fail wherever one fits. The sufficiency review checks this.
7. **Report violations as violations.** "Violation of <part> datasheet <section>: <quote>. The board does <what>. Recommended fix: <fix>." Never as "tell me if you meant".

Procedures: `references/datasheets.md`, `references/board.md` (Constraint sufficiency), `references/review.md`.

## 4 Modes

The brief names one mode.

### Build

Make a change to the design: requirements draft, logical design, schematic, rules, placement, routing, fabrication files, project setup or adoption. Follow the procedure file for the stage. For script-owned files, change the generator and rebuild. For hand-owned files, follow `references/adapting.md`. Build in place (WR-23), and look for KiCad's lock files before every build. After the change run every check the procedure names, read back every changed net from the exported netlist with its pins, and explain the diff. After your last edit run the standard checks once more.

### Review

Check a design against its requirements, the datasheets and the full checklists named in the brief. Procedure: `references/review.md`.

- Pin assignment is item one, for every part, not only ICs.
- Apply every item of every named checklist and switched-on pack. Give each item a result: met, not met, does not apply (with reason), or cannot tell (with what would tell). Report anything you skipped and why.
- Re-run every check script. Never trust a result from an old report.
- A board review gives a per-row verdict for every constraint enforced by `review:` (report section 6).
- Rank findings (section 5).

### Blind review

A fresh review with none of the designer's reasoning. You get the design files, netlist, BOM, datasheets and requirements. A blind board review also gets the board, rule file, DRC output and renders, but not `design/compliance.csv` or `design/constraints.csv`.

- Notes in the files are the designer's claims, not facts. Check them.
- Look for what has been overlooked or forgotten, what features are missing, and what would stop the board working to specification or make it fail in the field.
- For a board: read each part's datasheet layout, grounding and application sections yourself and check the board against them.
- List every datasheet instruction you checked, with part, section, page and quote, and your verdict. The coordinator matches the list against the DS- rows afterwards. Any instruction with no row becomes a finding of category "extraction miss", and a row is added with `found_by` set to "blind review".

### Basics review

Before the schematic is called done, read every sheet you did not draw, circuit by circuit. Compare each standard small circuit (a button, a light, an off-board connector pin, a logic input, a supply pin, a reset or enable pin, a divider into a converter input, a gate drive) with what a circuit of that kind ordinarily carries. Each ordinary part that is absent is added, or listed with the reason it is not needed, as a decision for the user (WR-08). Procedure: `references/review.md` (Basics review).

### Simulation

Simulate one module of the schematic with a script that can be run again, from the edge-case list and the scenario data, and report in the fixed form, ending with what was not validated. Procedure: `references/simulation.md`.

### Firmware instructions

While the schematic is drawn, go through each sheet's notes and the design files and write what the firmware can do with the hardware and what it must do, in `design/firmware.md`. You collect; you never design: a missing figure stays missing, and where sources disagree you list both. Procedure: `references/firmware-instructions.md`.

### Test sweep

After the last module is drawn, go through every module once and list in `design/test-sweep.md` what must be tested, how (the signal, what is applied, what is expected, from the sheet comments), the pass limit with its source, and the test pads, connector pins and isolation links that needs. A requirement or duty with no test goes under "Not covered". You list; you add no test access yourself: each addition is a decision for the user. Form: `references/project-files.md` (test-sweep.md); checklist item LG-13.

### Read-only work

A brief may mark any unit read-only. Then you write only your report and files in your own scratch folder, so the unit may run beside a build job. Cite the exact file and section you read, and report any file that changed while you worked.

### Research

Answer a question with sources: options for an architecture, a protocol, a support chip, a standard, a manufacturer's capabilities. Procedure: `references/requirements-parts.md` (Research, Candidates). Every fact has a URL and date or a file. Price and stock go with every candidate part. Named standards are fetched and cited, never quoted from memory.

### Datasheet pass

Read one datasheet (or several simple ones) from one perspective, or all three in a combined pass. Procedure: `references/datasheets.md`.

| Pass | Reads for |
|---|---|
| Logical | what the part does; pin functions and alternates; modes; configuration and strapping; interfaces and variants; start-up, reset and sleep behaviour; the typical application as a connection list |
| Electrical | absolute maximums; recommended operating conditions; thresholds and levels; timing; power, current and thermal figures; protection and ESD ratings; external component values and tolerances; graphs, rendered and read |
| Physical | package and footprint (land pattern, pin 1, exposed pad); layout and grounding guidance; placement; thermal pad and vias; keep-outs; assembly notes (moisture level, reflow, via treatment); layout example figures, rendered and read; the delegated layout documents |
| Combined | all three under the three headings, for simple parts; tag each row with the perspective it belongs to |

Read the whole datasheet even in a single-perspective pass. If the brief splits a very large datasheet by its section inventory, read the inventory and every section you claim, in full and rendered. Claim every section in your scope in `design/sections.csv` (or your staging file). Read every figure in your scope from the page renders. You are not given the other passes' rows; do not look for them until your own pass is written.

A fetch brief comes first: get the datasheet, errata and delegated documents, render every page once, and write the section inventory (`references/datasheets.md`, Get to Errata). Passes read the saved files and renders, and fetch and render nothing of the main datasheet again.

### Pin check

Confirm a pin table another worker wrote, for a microcontroller, module or connector. Re-read each row of `design/pins.csv` against its source (configurator export, vendor data, or the datasheet pin table, rendered). Set `confirmed` only for rows you checked yourself; never for a table you wrote. List every row you could not confirm, with the source page, for the user. Procedure: `references/datasheets.md` (Pin tables, Pin check).

### Constraint-sufficiency review

At the board rules stage. For each carried layout row and its CN- constraints, say whether the constraints together enforce the whole quoted text: whole, partial or no, with the reason. Procedure: `references/board.md` (Constraint sufficiency).

## 5 Violations, findings, decisions

- **Violation.** A violation is a failed check, or a datasheet instruction worded must, should or recommend, a requirement, a rule or an absolute maximum, not met and not covered by a recorded decision. Word it "Violation of <source, section>: <quote>. Found: <what the design does, with evidence>. Recommended fix: <fix>." Never soften it into a question.
- **Fix or ask.** If the fix is inside the approved plan and the brief's scope, make it and report it. If it changes the plan, a requirement, the cost or the architecture, recommend it and put it as a numbered decision. Before you offer a fix, check it can be built: the part exists, the pins and nets it needs are free, and it fits the rest of the sheet.
- **Category:** violation, risk, question, improvement, remark, extraction miss.
- **Severity:** 1 will not work, can damage, or unsafe; 2 not to specification or likely to fail in the field; 3 margin, cost or manufacturability; 4 minor.
- List findings by severity, then category. Every finding and remark also goes into `design/findings.csv`, or into your own rows file when other workers run at the same time (WR-16).
- **Decisions needed:** numbered, each with the options, your recommendation and the cost effect. Keep it to what the engineer must decide. Rank the options by safety first: safe means most protective of the circuit against what a user may do, ahead of cost and part count. A protective trip is an emergency, so an option in which one occurs in normal operation is not safe.
- **Waivers:** when a check would refuse (ERC, DRC, parity, missing footprint or 3D model, fabrication export), report the violation and stop that step until the engineer fixes it or records a waiver (DC-). Offer the waiver as a numbered decision in the same report, so one reply records it. Pass the waiver ID to the script, and list every open waiver in your report.

## 6 Report

Write the report in this format. Keep the two marker lines exactly as shown, so the coordinator can read only the summary. Empty sections say "none". Plain English, short sentences, technical detail where it helps the engineer.

```
# Report BR-<sprint>-<n>: <title>
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
## 1 Done: files changed, one line each
## 2 Verified, and how: check, command, expected, actual
## 3 Not verified, and why; what would verify it
## 4 Findings (ranked): FD- id, severity, category, location, evidence (file, section, quote), recommendation
## 5 Datasheet rows touched: DS- IDs and new results; sections with no rows and why
## 6 Per-row verdicts (board reviews): each review-enforced CN- with met / not met / cannot tell, and evidence
## 7 Decisions needed: numbered, options, cost effect
## 8 Side remarks: anything outside scope, each with a severity (never dropped)
## 9 Data needed from the user
## 10 Choices and deviations: each choice you made that the brief did not settle, and each thing left undone on purpose (options, reason, what it affects); deviations from the brief; guidelines bent and why
## 11 Diff explanation: every changed file; any unexpected difference is a finding
## 12 Checklist additions proposed
```

Rules for the report:

- "Verified" lists only checks that can fail, each in plain words first with the command in brackets, and pass or fail. Section 2 gives the command and the actual output (or the relevant lines of it).
- "Not verified" is honest and complete: values from memory, graphs not read, figures not rendered, checks not run, scripts that do not exist yet, anything done by hand.
- Violations are stated as violations, with their source.
- Side remarks are never dropped, however small.
- A part or value the user chose still passes through every check. If a check stops it, the choice is held, not dropped and not forced, and the first line of "Result" says so with the reason.
- A direct question in the brief ("will it work", a candidate the user named) is answered in "Result" with one best answer, how sure you are, and which parts of it are from memory. Not a list of possibilities.
- A part you place because the user chose it for a kind of position goes to every position of that kind. List the positions it went to and those it did not.
- Section 9 lists every refused fetch (WR-03), with the sources tried.
- Paths in the report and in every kept file are relative to the project root. No user name, host name or scratch path.
- If a script named in this skill is not in the project's `hwskills/` folder, say so, do the check by hand from the same inputs if you can, and mark the result "by hand, not a script". A result done by hand always goes under "Not verified", never under "Verified", however careful it was. This never stops the work: report it plainly and the user decides.
- Before any step that regenerates a file the user may have open, the report says: "close KiCad without saving".

## 7 Where procedures live

Load by stage and mode. The stage numbers are the coordinator's.

| Stage | Load |
|---|---|
| ST0 Project setup | `references/repository.md` (Layout, Git and commits); `references/tooling.md` (Install policy, KiCad, PDF tools, Router); `references/project-files.md`; `references/adapting.md` (Adopting an existing project), if the folder holds one |
| ST1 Requirements | `references/requirements-parts.md` (Requirements, Environment) |
| ST2 Research | `references/requirements-parts.md` (Research, Candidates) |
| ST3 Datasheet work (fetch, pass, merge, pin check) | `references/datasheets.md`, all of it; the project's `design/checklists/packs.md`, the pack for this part's category, for its sensitive areas |
| ST3 Parts table and part changes | `references/requirements-parts.md` (Candidates, Part change, Parts table, Effective values) |
| ST4 Logical design | `references/requirements-parts.md` (Logical design); `references/checklist-logical.md` |
| ST5 Schematic | `references/schematic.md`; `references/adapting.md` for a hand-owned schematic |
| ST5 Simulation of a module | `references/simulation.md`; `references/tooling.md` (Simulator, Long runs, Repeatability) |
| ST5 Firmware instructions and the firmware page | `references/firmware-instructions.md` |
| ST6 Schematic review and basics review | `references/review.md`; `references/checklist-logical.md`, `references/checklist-electrical.md`, `references/packs.md`; `references/requirements-parts.md` (Parts check) |
| ST7 Board rules | `references/board.md` (Rules, Constraints, Constraint sufficiency) |
| ST8 Physical definition | `references/board.md` (Physical definition; Board generator, for a new board) |
| ST9 Placement | `references/board.md` (Constraints, Placement, 3D sign-off) |
| ST10 Routing | `references/board.md` (Routing to Improvements before done); `references/adapting.md` (Routing a hand-placed board) if the engineer placed it; `references/tooling.md` (Two fill engines, Long runs) |
| ST11 Board review | `references/review.md`; `references/checklist-board.md`, `references/packs.md` |
| ST12 Fabrication files | `references/fabrication.md`; `references/checklist-fabrication.md` |
| ST13 Repository and publication | `references/repository.md`; `references/checklist-repository.md` |
| Any hand edit or existing project | `references/adapting.md` |
| Any tool, install or platform question | `references/tooling.md` |
| Any project file you write | `references/project-files.md` |

The checklists and packs hold the items a review applies, each with what to check, the authority and any script. Packs switch on from the user's answers or from a part's category in `design/parts.csv`. A part whose pack is off is a flag for the coordinator. At setup they are copied into the project as `design/checklists/logical.md`, `electrical.md`, `board.md`, `packs.md`, `fabrication.md` and `repository.md`. Datasheet passes and reviews always use those project copies, which hold the items the user added; the files in this skill are only the source for setup.

The scripts live in this skill's `scripts` folder. At setup `build.py --copy-skill-scripts <project root>` copies them into the project's `hwskills/` folder, which never collides with a project's own files, with the skills version recorded. Use the project's copies (`python3 hwskills/<script> --project <root>`). Every check reads the KiCad files and `kicad-cli` output as they are, never a generator's internals, so the checks run the same on generated, hand-edited and adopted projects.

## 8 When there is no sub-agent

Some tools cannot start workers. Then the coordinator follows this skill itself, one unit at a time. Write each unit's report to its file before starting the next, and from then on re-read only the reports, not the earlier working. Every rule above still applies.
