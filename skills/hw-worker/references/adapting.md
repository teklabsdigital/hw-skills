# Hand edits and existing projects

The skills' convention is AI-driven: the user says what they want, and workers make the change, normally by editing a generator script and rebuilding. Engineers will also edit files in KiCad themselves, or bring an existing KiCad project. This file is how a worker adapts to that, quietly and without fuss.

Report anything that behaves unexpectedly on this path as a finding.

## Contents

File ownership; Detecting a hand edit; Checks on the files as they are; Proposing an edit; Editing KiCad files safely; Adopting an existing project; Routing a hand-placed board.

## File ownership

`design/ownership.csv` records every design file: path, owner (script or hand), writer (script and stage), the hash of the bytes the script last wrote, and the commit (template in `references/project-files.md`).

- Mixed ownership is normal: a generated schematic and a hand-placed board, for example.
- A design file with no record is hand-owned.
- `design/status.md` carries a one-line summary, for example "schematic: script; board: hand since DC-041". Update it when ownership changes.
- A file moves from hand to script ownership only in a sprint of its own, when the user wants it.

## Detecting a hand edit

Before any script writes a design file, `build.py` hashes the file on disk and compares it with the recorded hash.

- **Equal:** the script writes the file and records the new hash.
- **Different:** that file is not written. Stop that step and report it. The coordinator asks the user.

Your report says what changed in meaning, not only that bytes differ. KiCad may re-save a file with byte changes even when nothing that matters changed.

- Schematic: export the netlist and the symbol fields from the file on disk and compare them with those from the last build: nets added, removed or changed (with pins), parts added or removed, field values changed.
- Board: `build.py` reads the board file as text and lists footprints added, removed, moved or rotated, value and pad-net changes, and changed counts of tracks, vias and zones. Add net classes and rules from the `.kicad_pro` and `.kicad_dru`; for anything more, read the board through KiCad's Python board API (`pcbnew`).
- Where the project is in git, add `git diff --stat` and the relevant hunks.
- If nothing changed in meaning, say so plainly.

A schematic that KiCad has only opened and re-saved is a common case. KiCad's own writer reorders items and rewrites some values, so the bytes differ from what the script wrote, though the netlist and fields are the same. The build then stops with exit 3, "NOT WRITTEN", and says for that file "no change in meaning found by this summary (N text lines differ; KiCad may have re-saved the file)". This is expected, not a fault. Report it as a change with no change in meaning, and put the same three choices below to the user.

Put three choices to the user, numbered:

1. keep the edit, and the file becomes hand-owned (`build.py --keep-hand <path>`);
2. carry the edit into the script, rebuild, and show the rebuilt file matches the edit in meaning;
3. overwrite the edit, recorded as a decision (`build.py --overwrite <path>=DC-nnn`).

Never overwrite a hand edit silently.

## Checks on the files as they are

Every check, table and review reads the KiCad files and `kicad-cli` output: the `.kicad_sch` symbols and fields, the netlist exported from it, the `.kicad_pcb` (as text or through `pcbnew`), the `.kicad_pro` and `.kicad_dru`, and the ERC and DRC reports. None reads a generator's variables or tables. So the checks run the same on generated, hand-edited and adopted projects.

- Checks never write to a design file.
- DRC with a zone re-pour saves the board, so on a hand-owned board run it on a copy. `python3 hwskills/pcblib.py drc BOARD` does this: a board with no script-owned row in `design/ownership.csv`, or whose hash no longer matches, is treated as hand-owned and copied first, and its bytes are checked unchanged afterwards. The same holds when the board, or its `.kicad_pro` or `.kicad_dru`, is recorded as written by the project's own build (`(own build)` writer): only a skill generator's files are written in place. A table problem that stops the project file being written ends the run with a plain message and exit 2, and nothing is written.
- For a hand-owned schematic, `design/parts.csv` is read from the symbol fields, not written into them, unless the user asks for the fields to be updated.

## Proposing an edit

The default for a hand-owned file: describe the change for the engineer to make.

For each change give:

- what: the part, net, field, track or zone;
- where: sheet and position, or board layer and coordinates;
- the new value or connection;
- why: the DS-, FR-, QC-, CN- or FD- item it serves, with the quote where it is a datasheet row;
- how to check it afterwards: the command to run.

Number the changes so the engineer can answer by number.

## Editing KiCad files safely

Only when the engineer asks you to make the edit yourself.

1. The engineer closes the KiCad editor. KiCad rewrites files it has open. Check for KiCad lock files beside the project files (`references/tooling.md`, KiCad facts) and say what you found. A lock file is a reason to stop and ask. Never remove one, and never work in a copy to get round one.
2. Commit before you touch it, as the commit settings allow (`references/repository.md`, Git and commits). The commit is the backup: no dated copy of the file is kept.
3. Board edits: through `pcbnew` on the closed file, in a short script you show in the report.
4. Schematic edits: version one limits these to field values (value, footprint, MPN and sourcing fields), made as careful text edits of the S-expression file. Change only the field's quoted value. Keep every other byte.
5. Do not rewire or redraw a hand-owned schematic by text edit. Propose those changes for the engineer instead.
6. After any edit: run ERC or DRC; export the netlist and compare it with the intent; show the diff. Then tell the engineer they can reopen the file.
7. Record the edit in the report's diff explanation. Ownership stays "hand".

## Adopting an existing project

When the folder already holds a KiCad project, the setup brief includes adoption. Do not redesign anything unless asked. Do not change any design file, and do not move any file: the project keeps its own layout, and the scripts find the KiCad files where they are.

0. **Setup first.** Adoption comes after the setup steps of `references/repository.md` (Layout), done beside the user's files: `design/` with every file from the templates in `references/project-files.md`, the six checklist copies in `design/checklists/`, the skill scripts (with `build.py`) in `hwskills/` by `build.py --copy-skill-scripts <project root>`, `datasheets/`, and the tool check in `design/status.md`. Nothing goes into the project's own `scripts/` or root, so its own `build.py`, `kicad_env.py`, `project_settings.py` and other files are never overwritten; the copy stops with a list if `hwskills/` already holds a file with other bytes. The skill scripts import only each other, whatever modules of the same name the project holds. In a project with its own generators, ask the user before using any skill script that writes design files there. Do not add an empty `hardware/` when the KiCad files are somewhere else. If setup has not been done, do it first, in the same brief if it allows, else stop and report.
1. **Inventory.** Files and folders; where the KiCad project is (the folder holding the `.kicad_pro`); KiCad version that saved them; sheets; board state (outline only, placed, routed, poured); libraries used and whether they are in the project; the rule file; BOM fields present; datasheets present; any generator scripts.
2. **Ownership.** Record every design file as hand-owned in `design/ownership.csv`: `python3 hwskills/build.py --adopt`. It finds the KiCad project wherever it is. When the files are not in `hardware/`, it writes their folder into `design/status.md` as one line, `KiCad folder: <folder>` (`KiCad folder: .` for the project root), and every script reads the KiCad files there from then on. If KiCad projects sit in several folders, it stops and lists them: ask the user which one is the board, write that line yourself, and run `--adopt` again (the build is always `python3 hwskills/build.py`). Exception: if the project has its own generator scripts and the user chose to keep them as the writers (first-session table), run the user's own build into a scratch folder (`python3 hwskills/build.py --adopt --reproduce "COMMAND"`, with the user's build command run from the project root of a scratch copy). Each file it reproduces byte for byte is recorded as script-owned, with that script as `writer` and the hash of the file on disk. A file it does not reproduce stays hand-owned; say why in the report (the script prints the reason for each file). From then on, a change to such a file is a change to the user's script and a run of the user's build.
3. **Exports.** `python3 hwskills/build.py erc netlist bom`. With no generator scripts, no stage writes a design file: ERC runs, and the netlist (machine path and export time stripped) and the BOM are written beside the KiCad files. Exports are always written again and never protected: a netlist or BOM the project keeps by hand is overwritten, so move it aside first if it matters. An ERC violation stops the build before the exports: record the violations as findings, then export with `python3 hwskills/build.py netlist bom`, which runs no ERC. The report is `ERC.json` beside the KiCad files. Violations the user decides to carry are listed under "Expected ERC items" in `design/status.md`, and the build then stops only when the list changes. A waiver is the user's decision, not yours.
4. **State files.** The minimum set for an adopted project, every one from its template: `status.md`, `decisions.md`, `requirements.md`, `parts.csv`, `pins.csv`, `compliance.csv`, `sections.csv`, `constraints.csv`, `fab-capabilities.csv`, `findings.csv`, `net-review.csv`, `ownership.csv` (step 2), and the checklist copies. A table with no rows yet still has its header line. `table_check.py` reports a table that is not there as "not present, check not run": listed, not failed, in an ordinary run, and a fail from the checkpoint on (`--stage ST6` or later; `ST11` for `constraints.csv` and `fab-capabilities.csv`). So copy every template: a missing file is a check that never ran. Then fill them:
   - `design/requirements.md` reconstructed from the schematic, notes and any README, every item marked "to confirm" with the engineer;
   - `design/parts.csv` from the symbol fields, with missing sourcing fields listed;
   - `design/pins.csv` as `references/datasheets.md` (Pin tables) says: every IC, module and connector, and every polarised part (diodes, LEDs, transistors, electrolytic and tantalum capacitors), one row per pin. For a plain connector or header pin, `name` is the symbol's pin name (for example "Pin_1"), and `functions` and `used_function` both hold the signal the pin carries in this design (or "passive");
   - DS- rows and the section inventory from the datasheets, with the three perspective passes for complex and pack parts (`references/datasheets.md`); fetch datasheets that are missing, once the user allows the downloads;
   - `design/fab-capabilities.csv` if the manufacturer is known;
   - `design/constraints.csv` seeded from the user's own rules: each rule in an existing `.kicad_dru`, and each net class the user set in the `.kicad_pro` (a class other than Default, or a Default changed from KiCad's own values). One CN- each, with `from` "user", `note` "existing rule file" or "existing net class", and `enforced_by` `dru:<rule name>` or `dru:netclass <Name>`. KiCad's untouched Default class is not a constraint; say in the report when it is the only rule.

   **Datasheets not in the project yet.** Write the pin rows from the schematic symbols, with `source` "schematic symbol, datasheet not fetched yet" and `confirmed` empty; write no DS- rows and no section inventory for that part; leave `compliance_done` and `pins_done` "no"; and list the missing datasheets first among the open items of the report. Nothing from memory. The passes run once the datasheets are fetched.

   **Net classes with no rule file.** A hand-made project often has no `.kicad_dru`, only the net classes in its `.kicad_pro`. These count: KiCad's own DRC applies them, and `table_check.py constraints` accepts a `dru:netclass <Name>` row when there is no rule file and the class's value in the project file reaches the row's limit, and says so in its output. A zone's own clearance setting can override a net class, so a clearance carried this way is "partial" for zones; say what covers the rest (a board check or a review).
5. **Checks.** Run every check the stage allows: the ERC of step 3; `python3 hwskills/sch_check.py all --record`; `python3 hwskills/table_check.py all`; DRC on a copy with `python3 hwskills/pcblib.py drc BOARD` (run with KiCad's Python); `python3 hwskills/board_check.py` for constraints enforced by `check:`, and the board checks the board's state supports. In an ordinary run (no `--stage`), open review items, checklist items with no result, tables not present, and board severities left at KiCad's defaults are listed and counted, not failed. Report each list and count.
   - **Severities.** An existing project file usually holds KiCad's own board severities, lower than the skills' raised list (dangling tracks and vias, for example, are warnings there). `table_check.py suppress` lists each with the recommended value. They are the user's project settings in a hand-owned file: do not change them. Put them to the user as one numbered decision: raise them (the user does it in KiCad's board setup, or asks you to, under Editing KiCad files safely), or keep them, recorded as a DC- decision that names each check. They fail from the board checkpoint (`--stage ST11`) until one or the other is done. A severity lower than KiCad's own default is a suppression, and fails in any run without a decision.
6. **Findings.** Rank them (severity, then category) and report. Hard datasheet rows the design does not meet are violations, stated as such.
7. **First sprint.** Propose one, tied to the user's goal. Moving files to script ownership is not part of it unless the user asks.

## Routing a hand-placed board

The grid router does not read KiCad files itself. The driver in `pcblib.py` does: `python3 hwskills/pcblib.py route BOARD OUT_DIR` (run with KiCad's Python) reads a placed `.kicad_pcb` (pads, keep-outs, existing tracks and zones, net classes), routes only the unrouted nets, keeps existing tracks as fixed obstacles, and writes the result to a copy in OUT_DIR for the engineer to review. The input board is never written; its hash is checked afterwards.

- It uses the outer two layers only.
- Run DRC with re-pour and the board checks on the routed copy. Report results before the engineer adopts the copy.
- The engineer decides whether the copy replaces the board. If it does, record it; ownership stays "hand" unless the user decides otherwise.
