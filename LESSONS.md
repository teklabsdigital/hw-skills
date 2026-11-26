# Lessons

What was learned from using these skills, and where each lesson now lives in the skills.

The lessons come from using the skills on real boards. Each one is written as a rule, with what goes wrong without it and the place in the skills that carries it.

This release covers the work up to the schematic and its simulation. Lessons from the board stages (placement, routing, fabrication files) wait for the next release. They are listed at the end.

The skills are work in progress and are being refined. Feedback and improvements are welcome as pull requests.

Lessons are numbered HL-01 onward.

## Rails and power symbols

**HL-01 Draw every rail and ground with its power symbol, and let a power symbol name only a rail declared in one table.**
A rail on a label or a sheet pin looks like a signal and can end up as two nets. Power symbols join by name across all sheets, so two rails drawn with the same symbol name are one net, and KiCad's rules check does not flag it.
Where: `skills/hw-worker/references/schematic.md` (Generators; Conventions, Rails and nets; Scripted checks, `sch_check.py rails`); `skills/hw-worker/references/checklist-electrical.md` (EL-47); `skills/hw-worker/references/project-files.md` (rails.csv); `skills/hw-worker/references/tooling.md` (KiCad facts).

**HL-02 Nets that must stay apart get different names and a table row, and no signal goes on a global label.**
A return kept apart from ground and drawn with the ground symbol is joined to ground silently. A signal on a global label reaches every sheet that uses the name, listed for it or not.
Where: `skills/hw-worker/references/checklist-electrical.md` (EL-21); `skills/hw-worker/references/project-files.md` (separate-nets.csv); `skills/hw-worker/references/schematic.md` (Conventions, Rails and nets).

## Drawing and plots

**HL-03 Apply the drawing conventions without being asked, and let the user's recorded habits win.**
A drawing that starts in a corner, with supplies pointing sideways and near parts joined by labels, is hard to read. The user then spends the review on style and not on the circuit.
Where: `skills/hw-worker/references/schematic.md` (Conventions, Placement and text); `skills/hw-coordinator/references/questions.md` (Schematic (ST5)).

**HL-04 The worker looks at the plot of every changed sheet, the coordinator opens it again at hand-back, and the user is given a PDF.**
Text over a wire is seen only on the plot, and a report can call a sheet clean after a later edit broke it. The look is by eye and is a style duty, never evidence. A schematic file opened in the editor can be saved by accident and blocks the next build.
Where: `skills/hw-worker/references/schematic.md` (Visual check); `skills/hw-worker/SKILL.md` (WR-02); `skills/hw-coordinator/SKILL.md` (Role and focus; How changes are made).

## Modules and sheets

**HL-05 End the logical design in module definitions, one sub-sheet per module, and check the empty hierarchy before any part is drawn.**
Without agreed modules the sheet split is made while drawing, and nets between sheets grow without a decision. The exported netlist leaves out a net with no part pin, so a wrong sheet pin in an empty skeleton needs its own check.
Where: `skills/hw-worker/references/checklist-logical.md` (LG-26); `skills/hw-coordinator/references/stages.md` (ST4 Logical design); `skills/hw-worker/references/schematic.md` (Sheets, `sch_check.py modules --probe`).

**HL-06 Draw in a fixed order, top sheet first and the processor sheet last, with the main power path as wires on the top sheet.**
A processor sheet drawn early has its pins assigned again each time another sheet shows a new need. A top sheet of boxes joined only by labels does not show how power flows.
Where: `skills/hw-worker/references/schematic.md` (Sheets); `skills/hw-coordinator/references/stages.md` (ST4 Logical design; ST5 Schematic).

**HL-07 Number designators in a fixed block per module, and never type a designator into text.**
A part added on one sheet otherwise renumbers parts on another. Every comment, finding and report that named a designator is then wrong.
Where: `skills/hw-worker/references/schematic.md` (Generators); `skills/hw-worker/SKILL.md` (WR-15).

**HL-08 Removing a module is a procedure of its own.**
A removed module leaves rows, firmware lines, simulation files and open findings behind in several places. Each one misleads a later reader.
Where: `skills/hw-worker/references/project-files.md` (modules); `skills/hw-coordinator/references/briefs.md` (Mode notes, Removing a block).

## Parts and cost

**HL-09 Read a part's lifecycle on the maker's own page before it is proposed, for the exact orderable code.**
A design drawn around a part that is ended, or not recommended for new designs, is redrawn later. One package of a part can be active while another is ended.
Where: `skills/hw-worker/references/requirements-parts.md` (Candidates; Parts check); `skills/hw-worker/references/checklist-electrical.md` (EL-27).

**HL-10 Ask the user's suppliers and their order once, browse the makers' own ranges first, then check each option can be bought.**
A worker that does not know the order searches the wrong place or asks again. A search that starts at one supplier's filters finds only what that supplier lists, so the report states how far the search reached.
Where: `skills/hw-coordinator/references/questions.md` (First session; Preferences (ST1, ST2)); `skills/hw-worker/references/requirements-parts.md` (Research; Candidates).

**HL-11 Show every block price and pivot beside the running cost of the whole board, and offer a market scan for a board that will be sold.**
A block that looks cheap alone can take the board over its cost target. A design with no cost target and no look at competing products can meet every requirement and still be the wrong product.
Where: `skills/hw-worker/references/checklist-logical.md` (LG-21); `skills/hw-worker/references/requirements-parts.md` (Research, Market scan); `skills/hw-coordinator/references/stages.md` (ST2 Research); `skills/hw-coordinator/SKILL.md` (Settings; Pivots).

**HL-12 A part the user chose for a kind of position goes to every position of that kind.**
The choice is otherwise applied only to the sheet in hand. The other sheets keep a different part for the same job.
Where: `skills/hw-worker/references/requirements-parts.md` (Chosen parts); `skills/hw-worker/references/checklist-electrical.md` (EL-55); `skills/hw-worker/references/schematic.md` (Scripted checks, `sch_check.py chosen`).

**HL-13 Every symbol carries its supplier part number and the link to its own datasheet.**
A symbol that takes its link or description from the library symbol can describe another part. The parts list then points a buyer to the wrong page.
Where: `skills/hw-worker/references/schematic.md` (Generators; Scripted checks, `sch_check.py fields`); `skills/hw-worker/references/checklist-electrical.md` (EL-37).

**HL-14 Judge a rating in its real conditions: ambient plus enclosure rise, the stated time or waveform, and the voltage on every node two blocks share.**
A part rated for the ambient limit alone runs hot in a closed box. A rating quoted without its condition reads as a plain limit. A part on a shared node can see a surge that only the other block's research knew about.
Where: `skills/hw-worker/references/checklist-electrical.md` (EL-08; EL-13; EL-50); `skills/hw-worker/references/requirements-parts.md` (Candidates); `skills/hw-coordinator/references/stages.md` (ST3 Parts and datasheets).

## Datasheets

**HL-15 When a site refuses a fetch, try the other legitimate sources once in a fixed order, never work round the refusal, and take every figure from a saved file.**
Stopping at the first refusal sends the user to fetch documents a distributor hosts openly, and disguising a request is never allowed. A copy not from the maker can be an old revision or lack pages, so it is checked first. A figure from an unsaved page cannot be read again.
Where: `skills/hw-worker/SKILL.md` (WR-03); `skills/hw-worker/references/datasheets.md` (Get); `skills/hw-worker/references/tooling.md` (PDF tools); `skills/hw-coordinator/SKILL.md` (Asking for data).

**HL-16 Reading datasheets as parts are placed is an option for the user, offered with its risk.**
The full pass chain is slow on a board with many simple parts. The short form can miss an instruction outside the sections read, so the user chooses it and the pin rows are still written.
Where: `skills/hw-worker/references/datasheets.md` (Reading as parts are placed); `skills/hw-coordinator/SKILL.md` (Settings; The datasheet chain).

**HL-17 A figure a brief carries is a candidate, and an old report is a record, not a source.**
A figure copied from brief to brief keeps being used after its source changed. The worker checks it against the source and stops if it does not hold.
Where: `skills/hw-worker/SKILL.md` (WR-01; Stop early and report if); `skills/hw-coordinator/references/briefs.md` (Brief template, Carried figures).

**HL-18 Read the application text for protection parts it asks for outside the typical circuit.**
A clamp or series resistor named only in a paragraph is missed when the typical circuit alone is copied.
Where: `skills/hw-worker/references/datasheets.md` (Reference designs); `skills/hw-worker/references/checklist-electrical.md` (EL-33).

## Requirements and research

**HL-19 Start from the problem and the user's story, ask early where the user interface lives, and show off-board items as physical things.**
A list of features with no story grows, and nobody can say which one the user would miss. The interface answer decides which controls and radio parts the board needs. A name in a block list hides what the connector or control looks like.
Where: `skills/hw-coordinator/references/questions.md` (Problem and user story (ST1); Interfaces (ST1)); `skills/hw-worker/references/requirements-parts.md` (Logical design).

**HL-20 Never design against a figure that is only proposed.**
A figure a worker proposed, and the user never confirmed, becomes a requirement by being built on.
Where: `skills/hw-worker/SKILL.md` (WR-06); `skills/hw-worker/references/requirements-parts.md` (Requirements); `skills/hw-coordinator/SKILL.md` (Never).

**HL-21 Keep the requirements file to the current state, short enough to read in one sitting.**
A file that keeps every replaced text beside the new one is not read. A small change then needs no new draft, only the items touched and the decision behind each.
Where: `skills/hw-worker/references/requirements-parts.md` (Requirements); `skills/hw-worker/references/project-files.md` (requirements.md).

**HL-22 Record the basis for every surge or over-voltage figure, for every external input.**
A surge figure with no basis is defended or dropped by opinion. The basis is a standard, a measured figure or the user's choice.
Where: `skills/hw-worker/references/checklist-electrical.md` (EL-05); `skills/hw-coordinator/references/questions.md` (Environment (ST1)).

**HL-23 Write the board-type switches with the exact names the scripts read, and retest them at every requirements change.**
A switch written in other words is not seen by the checks. A switch set off on a condition stays off after the condition has gone, and the checks it would add never run.
Where: `skills/hw-worker/references/packs.md` (Board-type switches); `skills/hw-worker/references/checklist-logical.md` (LG-17); `skills/hw-coordinator/SKILL.md` (Pivots).

**HL-24 Blocks researched at the same time share their assumptions and report their interface figures, and a protective block is researched from the problem first.**
Each block otherwise assumes its own voltage, current and timing at the shared edge. A search that starts from a known kind of part never looks at a simpler way to stop the same failure.
Where: `skills/hw-worker/references/requirements-parts.md` (Research); `skills/hw-coordinator/references/stages.md` (ST2 Research); `skills/hw-coordinator/references/briefs.md` (Mode notes, Research).

## Leaving things out

**HL-25 The ordinary parts of a standard circuit need no figure to justify them, and leaving one out is the user's decision.**
A rule that every added part needs a figure was read as a reason to drop pull resistors, filters and protection at off-board pins. One case is fixed: every button or switch read by a processor has a small debounce capacitor.
Where: `skills/hw-worker/SKILL.md` (WR-08); `skills/hw-worker/references/schematic.md` (Conventions, Circuit defaults); `skills/hw-worker/references/checklist-electrical.md` (EL-48).

**HL-26 Weigh a proposal to leave a feature out by named principles, one decision at a time.**
"Keep it simple" alone removes features whose work then lands on the user or the developer. Where the principles pull apart, the user chooses with each side set out.
Where: `skills/hw-worker/SKILL.md` (WR-24); `skills/hw-coordinator/SKILL.md` (Leaving things out); `skills/hw-worker/references/checklist-logical.md` (LG-20).

**HL-27 Every sheet is read by a worker that did not draw it, for what any engineer would expect to see and does not.**
The other checks ask whether what was drawn is right. None of them asks what is missing.
Where: `skills/hw-worker/references/review.md` (Basics review); `skills/hw-worker/SKILL.md` (4 Modes, Basics review); `skills/hw-coordinator/references/stages.md` (ST5 Schematic, Closing steps).

## Electrical checks

**HL-28 List every path by which an energy store can drain through the board, and check each source alone, each pair, and the same cases with firmware stopped.**
A store drained by accident through a divider or an unpowered part is a fault that shows only after days. Back-feed between sources is found on the bench when it was not asked on paper.
Where: `skills/hw-worker/references/checklist-electrical.md` (EL-51; EL-52).

**HL-29 For every output that can do harm, find its state when the processor hangs, resets or leaves its pins floating.**
A reset state table is not enough. A hang leaves pins driven, and some resets leave a timer output running.
Where: `skills/hw-worker/references/checklist-logical.md` (LG-11); `skills/hw-worker/references/schematic.md` (Scripted checks); `skills/hw-worker/references/datasheets.md` (Silence sweep).

**HL-30 Give every protective threshold margin in both directions, test each protective part on paper against the misuse cases, and write the failure it guards against as a walk-through.**
A threshold set from the nominal case trips in normal use, or too late, at a tolerance corner. A part chosen for one case can fail in another: the other polarity, a live plug-in, a wrong connection.
Where: `skills/hw-worker/references/checklist-electrical.md` (EL-53; EL-54); `skills/hw-worker/references/checklist-logical.md` (LG-05); `skills/hw-worker/references/schematic.md` (Sheet comments).

**HL-31 Keep one calculations folder; a worst-case result counts leakage or lists what it left out, and each rail's load is summed across sheets after every block.**
A value worked out in two places differs in one of them sooner or later. A divider result that leaves out the current into its pin can be wrong by more than its margin. A rail filled sheet by sheet is found over budget only at the last sheet.
Where: `skills/hw-worker/references/schematic.md` (Calculations and simulation; Scripted checks, `sch_check.py netload`); `skills/hw-worker/references/checklist-electrical.md` (EL-15); `skills/hw-worker/references/checklist-logical.md` (LG-10).

## Simulation

**HL-32 Simulate with the simulator KiCad ships, check the engine on known answers, and prove the set-up on one module before the others start.**
A simulator that needs an install waits on approval, so simulation is skipped. A fault in the set-up otherwise costs every module at once.Where: `skills/hw-worker/references/simulation.md` (Nothing to install; Set-up proven first; Engine check); `skills/hw-worker/scripts/spice.py`.

**HL-33 Generate the circuit file from the exported netlist, and never type or edit it.**
A circuit typed by hand is a different circuit. The run generates the file again first and stops if it differs, so a stale file is never simulated.
Where: `skills/hw-worker/references/simulation.md` (Circuit file; Scenarios).

**HL-34 Treat a model file as data, check each model alone where the design uses it, commit it, and check its licence before publishing.**
A model can be right in general and wrong at the design's operating points. A file that holds simulator commands or includes is refused, never stripped by hand. Models kept outside the project make the simulation run on one machine only.
Where: `skills/hw-worker/references/simulation.md` (Models; Model check); `skills/hw-worker/references/repository.md` (Layout, Simulation files); `skills/hw-worker/references/checklist-repository.md` (PB-11).

**HL-35 Give every power input a source model that behaves like the real source.**
An ideal voltage source hides the faults the input block exists to handle.
Where: `skills/hw-worker/references/simulation.md` (Power sources); `skills/hw-coordinator/references/questions.md` (Environment (ST1)).

**HL-36 Run the whole normal sequence first, then scenarios from a written list of edge cases, with scenarios and limits kept as data.**
A fault in normal start-up or shut-down is otherwise found by chance. Scenarios made up while scripting cover what the circuit suggests, not what people and the world do. A limit with no source is not a pass limit.
Where: `skills/hw-worker/references/simulation.md` (First run; Edge-case list; Scenarios).

**HL-37 Close every simulation report with what it did not validate, and offer a stand-in controller only as the user's choice.**
Makers' models describe a typical part, so a pass says nothing about tolerance, spread, layout or heat, and the worst-case calculation still stands. A loop closed by firmware is not shown by the circuit alone; the stand-in costs work and is not the firmware.
Where: `skills/hw-worker/references/simulation.md` (What typical models settle; Controller in the loop; Report form); `skills/hw-worker/references/checklist-electrical.md` (EL-45).

**HL-38 Make runs repeatable: the same files twice, a stated cap on processes, and one fixed order of fallbacks on record.**
A result that depends on machine speed cannot be checked. A set of runs with no cap loads the user's machine.
Where: `skills/hw-worker/references/simulation.md` (Repeatable runs); `skills/hw-worker/references/tooling.md` (Long runs; Repeatability).

## Firmware instructions and test

**HL-39 List what the firmware can and must do from the first sheet on, write no firmware, and close the schematic with a generated firmware page.**
A list made at the end is rebuilt from memory, and duties stated on early sheets are lost. A list kept only in a file beside the drawing does not travel with it.
Where: `skills/hw-worker/references/firmware-instructions.md` (Purpose; Collecting; The firmware page); `skills/hw-worker/references/checklist-logical.md` (LG-19).

**HL-40 The collector of firmware instructions never designs.**
A missing threshold filled in by the collector looks decided. A missing figure is written as missing, and two sources that disagree are both listed.
Where: `skills/hw-worker/references/firmware-instructions.md` (The collector never designs; Line form).

**HL-41 Every duty left to firmware needs a signal it can read and a way to act, and moving a duty to firmware is the user's decision.**
A duty with no signal behind it is found after the board is made. "Firmware will handle it" closes a hardware question without anyone agreeing, and guards nothing before firmware runs.
Where: `skills/hw-worker/references/firmware-instructions.md` (A signal for every duty; Moving a duty to firmware); `skills/hw-worker/references/checklist-electrical.md` (EL-44; EL-49); `skills/hw-worker/SKILL.md` (WR-25).

**HL-42 Put comments on every sheet, generated with the sheet.**
A sheet with no theory of operation and no thresholds cannot be reviewed or tested by someone who did not draw it. Comments typed by hand go stale at the next change.
Where: `skills/hw-worker/references/schematic.md` (Sheet comments); `skills/hw-coordinator/references/questions.md` (Schematic (ST5)).

**HL-43 Ask the user's test plan at the start of the schematic, and sweep every module for what must be tested once the last one is drawn.**
Test pads added sheet by sheet miss the tests that cross modules. The sweep lists the signal, what is applied, what is expected and what the board needs for it.
Where: `skills/hw-worker/references/checklist-logical.md` (LG-13); `skills/hw-worker/SKILL.md` (4 Modes, Test sweep); `skills/hw-coordinator/references/stages.md` (ST5 Schematic, Closing steps).

## Working with the user

**HL-44 Open with a short greeting that shows the whole process in five steps.**
A user who does not know what is coming cannot tell how far the work is, or why a question is asked now.
Where: `skills/hw-coordinator/references/process.md` (The greeting; The five steps; Where are we).

**HL-45 A bare "ok" settles only what was asked, and a question is not a requirement.**
Read as wide approval, "ok" closes items the user never looked at. A question taken as an instruction changes the design without a decision; it gets a direct answer.
Where: `skills/hw-coordinator/SKILL.md` (Listening); `skills/hw-coordinator/references/reporting.md` (Reading a reply; Answering a question).

**HL-46 Search the log before asking, and when a new answer contradicts an earlier decision, change neither until the user chooses.**
Asked twice, the user answers in other words and two answers stand. The later answer may be a slip, or the earlier one out of date; only the user knows which.
Where: `skills/hw-coordinator/references/reporting.md` (Before you ask); `skills/hw-coordinator/SKILL.md` (Listening; Never); `skills/hw-worker/references/checklist-logical.md` (LG-08).

**HL-47 Write a rule the user gives mid-work into the standing rules in the same turn, and answer each of the user's own ideas by name.**
A rule given in passing reaches the worker in hand and no later one. An idea the user offered and no report mentions looks ignored.
Where: `skills/hw-worker/references/project-files.md` (user-rules.md); `skills/hw-coordinator/references/briefs.md` (Brief template; Reading a report).

**HL-48 Hold a choice a check stops and say so first, offer the most protective option first, and offer no fix until it is known it can be built.**
A worker that quietly draws something else leaves the user believing their choice was built. A cheaper option shown as an improvement hides what it gives up. A fix that cannot be drawn wastes a round.
Where: `skills/hw-coordinator/references/reporting.md` (The report; Numbered decisions; Recommending); `skills/hw-worker/SKILL.md` (5 Violations, findings, decisions; 6 Report).

## Reports, briefs and decisions

**HL-49 Give every report one fixed form, number decisions in one running series in physical terms, and at a checkpoint give one whole proposed course.**
A long report buries the one decision the user must make. Numbers that restart make "yes to 2" unclear. Twenty separate questions make the user design the board one answer at a time.
Where: `skills/hw-coordinator/SKILL.md` (Reporting; Checkpoints); `skills/hw-coordinator/references/reporting.md` (The report; What a report says; Numbered decisions).

**HL-50 Log every prompt by default, say what each decision affects, and mark a replaced entry in the same turn.**
What the user said in passing is the first thing lost. A replaced decision that still reads as current is followed by the next worker.
Where: `skills/hw-coordinator/references/decision-log.md` (What goes in; Entry form; Rules); `skills/hw-coordinator/SKILL.md` (Settings).

**HL-51 A brief names the requirements at a commit, the user's rules, the ceilings and every file the worker may write, and a worker stopped on one item finishes the rest.**
A worker told too little guesses, and one with too few allowed files stops or writes outside them. One missing figure otherwise costs the whole unit of work.
Where: `skills/hw-coordinator/references/briefs.md` (Brief template; Checks before you send a brief); `skills/hw-worker/SKILL.md` (Stop early and report if).

**HL-52 Each shared file has one writer, parallel workers write their own rows files, and schematic builds run one after another.**
Two workers appending to one table lose rows or reuse an ID. Two builds at once write the same files, and a brief with more than two sheets comes back too large to read with care.
Where: `skills/hw-worker/SKILL.md` (WR-16); `skills/hw-coordinator/SKILL.md` (Sprints); `skills/hw-coordinator/references/stages.md` (ST5 Schematic).

**HL-53 After each report, sweep the shared files and close each finding with the decision that settles it.**
Findings stay open after they were settled, and an item accepted but not yet drawn drops out of sight.
Where: `skills/hw-coordinator/references/briefs.md` (Reading a report); `skills/hw-worker/references/project-files.md` (findings.csv).

**HL-54 A long job keeps a progress file, and after a pause or interruption the state of the files is checked before anything else.**
Without it the coordinator must stop a job to see how far it is. Work resumed from memory builds on files that were half written, and the user returns to decisions no longer in mind.
Where: `skills/hw-worker/references/project-files.md` (progress files); `skills/hw-coordinator/references/reporting.md` (Pause, end of day, interruption and restart); `skills/hw-worker/references/repository.md` (Git and commits).

**HL-55 Write no document whose only use is as a step toward the real output.**
Step-only plans and summaries cost time, and they go stale beside the files that matter.
Where: `skills/hw-worker/SKILL.md` (WR-12); `skills/hw-coordinator/references/stages.md` (Opening rule).

## Working in the project folder

**HL-56 Work in the project in place, with all scratch files in one git-ignored folder inside it.**
A design changed in a copy is carried back by hand, and changes are lost there. Files in a system temporary folder vanish between sessions.
Where: `skills/hw-worker/SKILL.md` (WR-23); `skills/hw-worker/references/repository.md` (Layout, Scratch); `skills/hw-coordinator/SKILL.md` (Never).

**HL-57 Look for KiCad's lock files before every build, and stop if the project is open.**
A build under an open editor is overwritten when the user saves. A lock file is never removed, and a copy is never built to get round one.
Where: `skills/hw-worker/references/tooling.md` (Never save from the editor); `skills/hw-worker/references/schematic.md` (Generators); `skills/hw-coordinator/SKILL.md` (How changes are made).

**HL-58 Ask at setup whether a backup is committed before each build, and check with git before saying work is committed.**
With no backup, a build that goes wrong has nothing to go back to. "Committed" said from memory is wrong when the commit failed. A backup commit is never pushed.
Where: `skills/hw-worker/references/repository.md` (Git and commits, Backup commits); `skills/hw-coordinator/SKILL.md` (Settings; Commits).

**HL-59 Apply the user's tool version rule to tools already installed, and report the editor's update settings without changing them.**
A version rule applied only to new installs leaves the tools in daily use outside it.
Where: `skills/hw-worker/references/tooling.md` (Install policy); `skills/hw-worker/SKILL.md` (WR-10); `skills/hw-coordinator/references/stages.md` (ST0 Start and project setup).

**HL-60 Ask once whether third-party documents are committed, and keep reports free of machine paths and user names.**
Some documents may not be copied. A path in a report shows who worked on the project and where.
Where: `skills/hw-worker/references/repository.md` (Layout, Third-party documents); `skills/hw-worker/SKILL.md` (6 Report); `skills/hw-worker/references/checklist-repository.md` (PB-12).

## Scripts and checks

**HL-61 Trust a new check only after it fails on planted faults, and keep the faults as a test.**
A check that has never failed may be unable to fail. Several checks passed for a long time because they were reading nothing.
Where: `skills/hw-worker/SKILL.md` (WR-02).

**HL-62 A check that read nothing fails or says so: an unreadable row, an empty scan, a missing table.**
A reader that skips what it cannot parse reports a pass on the rest. A scan that fails on every maker's contact address is switched off, so those are counted apart and accepted findings go in a reviewed list.
Where: `skills/hw-worker/references/project-files.md` (requirements.md; scan-reviewed.csv); `skills/hw-worker/references/repository.md` (Confidentiality scan); `skills/hw-worker/references/schematic.md` (Scripted checks).

**HL-63 A count holds only what is settled: an open finding is open, a withdrawn item is counted apart, and a bare mention of a rule ID is not a result.**
A finding marked open with a note was counted as triaged, and a checklist item was counted as done because a report named it. The summary then misled the checkpoint.
Where: `skills/hw-worker/references/project-files.md` (findings.csv; requirements.md); `skills/hw-worker/scripts/table_check.py` (checklists).

**HL-64 Run the checks again after the last edit, and compare the list of expected rule-check items, not their count.**
A result from before the last edit is not a result. A build that allows a count lets a new violation hide behind one that has gone.
Where: `skills/hw-worker/references/schematic.md` (Scripted checks; ERC and netlist); `skills/hw-worker/references/review.md` (Order of work); `skills/hw-worker/references/project-files.md` (status.md).

**HL-65 Keep project settings and checks out of the copied scripts, and load a tool only from inside the project.**
An edit inside a copied script is lost at the next copy. A search that climbs above the project root can run another copy of a tool unnoticed.
Where: `skills/hw-worker/references/project-files.md` (build.json); `skills/hw-worker/references/repository.md` (Layout); `skills/hw-worker/references/tooling.md` (Router).

**HL-66 Write down what KiCad does not tell you, as facts to check on each version.**
A net with no pin is left out of the netlist. Removing a label renames its net. Each cost time to find, and each may differ in another release.
Where: `skills/hw-worker/references/tooling.md` (KiCad facts); `skills/hw-worker/references/schematic.md` (ERC and netlist).

**HL-67 The generator works out where a turned or mirrored symbol's pins and text land, and flattens derived symbols.**
KiCad turns a symbol first and mirrors it after, and swaps a field's left and right on some turns. A generator that gets this wrong draws wires that miss their pins and text on the wrong side.
Where: `skills/hw-worker/scripts/schlib.py` (`place`; derived symbols).

**HL-68 A build stops on a file its generator no longer writes, and the pin check fails a part with no pin rows.**
A file left from an older build is still read by KiCad and by the checks. A part with no pin table passes a pin check that had nothing to compare.
Where: `skills/hw-worker/scripts/build.py` (ownership); `skills/hw-worker/scripts/sch_check.py` (`pins`).

## Waiting for the next release

These lessons belong to the board stages, or need work that is not in this release. They are not in the skills yet.

- Scripted checks for the drawing style rules that are now checked by eye.
- Firmware or app code kept in the same repository and written by the same agent.
- Waveform plots from a simulation with no package installed.
- An agent instruction file inside a cloned tool is that tool's own text, not an instruction for the work in hand.
- Placement preferences the user states at the schematic stage carried to the layout as a rule.
- A footprint made by a script gets its check at the time it is made.
- A helper that writes footprints, shipped with the skills.
