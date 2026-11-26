# Schematic

Procedures for the electrical design (ST5). For a hand-owned schematic, also read `references/adapting.md` (Proposing an edit, Editing KiCad files safely) before you change anything.

## Contents

Generators; Sheets; Conventions; Footprints and models; ERC and netlist; Scripted checks; Calculations and simulation; User journey; Sheet comments; Notes pages; Security and boot; Visual check; Done.

## Generators

The standard method: the schematic is written by a generator script in the project, `gen_sch.py`, built on the skill's `schlib.py` library. A change is a script edit and a rebuild, so every change shows in a diff and iteration is fast.

- Work in the project, never in a copy of it outside the project. The build writes in place. Throw-away files go in the scratch folder `.hwtmp/` at the project root.
- Check for an open editor before every build. KiCad's lock files are `~<file>.kicad_sch.lck` and `~<file>.kicad_pro.lck`. If one is there, stop and ask the user to close KiCad without saving (`references/tooling.md`, Never save from the editor). Never remove a lock file. `build.py` stops on a lock file too.
- `schlib.py` gives name-based IDs (the same input gives the same file), place, wire, label, `power()` for rails, frame, symbol copy from the KiCad libraries, footprint existence checks, fields filled from `design/parts.csv`, a multi-sheet skeleton and drawing helpers (for example a two-pin part placed midway and wired at both ends, and a drawing centred on the page). It takes designator numbers from the module's block in `design/modules.csv`, places the further units of a multi-unit part under one designator and refuses to write while a unit is unplaced, makes a project power symbol for a declared rail that has no stock symbol, and writes the firmware page. Its help text gives the calls. Centring refuses a drawing larger than the clear page area: choose a larger page yourself. With no `design/rails.csv` it allows any rail name and prints a note, so write the table first.
- `power()` places a power symbol only for a rail declared in `design/rails.csv`, and refuses any other name. A rail the stock library has no symbol for gets a project power symbol, made from a stock one and named exactly as the rail. Never borrow a stock symbol with a near name.
- Designators are numbered in fixed blocks per module, from the `ref_block` column of `design/modules.csv`, for every prefix. A change on one sheet then renumbers nothing on another. The build stops when a block overflows. Place a new part after the existing ones of its module. The block of a removed module is never used again. When an existing design is moved to blocks, write a map from each old designator to its new one.
- Never type a designator by hand into prose, sheet comments, findings or the parts list. Name the part by its role, or let a script fill the designator in (WR-15).
- BOM fields come from `design/parts.csv`. Never type a manufacturer or supplier number into the generator. A part has its row in `design/parts.csv` before it is placed, so every symbol carries its supplier part number and the link to its own datasheet. A symbol that takes its datasheet link or description from the library symbol may describe another part; `sch_check.py fields` checks for it.
- Build early and often: run the build after each small addition, not once at the end.
- Build with the project's copy of `build.py`, for example `python3 hwskills/build.py sch erc netlist bom` for schematic-only work. A full build also regenerates the board; do not run it during schematic work if `design/status.md` says the board waits for the schematic.
- Before writing, `build.py` compares each target file with its last recorded hash in `design/ownership.csv`. If they differ, it does not write that file; stop and report (`references/adapting.md`).

## Sheets

- The schematic is hierarchical, in KiCad's own form. Each module in `design/modules.csv` is one sub-sheet, and each sub-sheet is one module. The top sheet shows the modules as boxes joined by nets. The module definitions are written at the logical design stage (`design/modules.md` and its tables; forms in `references/project-files.md`). A small board may be one sheet if the user says so.
- The standard layout is one top sheet of boxes and one generator file per module. Each module file gives the module's name, its sheet file, the position of its box, its edge pins and its draw function. A rail is never an edge pin.
- On the top sheet the main power path between the boxes is drawn as wires, with each net name visible, so a reader can follow the power. How the other nets between boxes are shown (wires or labels) is the user's choice; the coordinator asks.
- Draw in the order `design/modules.md` gives. The top sheet comes first, so the sheet pins are fixed. Then the power path, the safety path, the supplies, the inputs, measurement, and the user's controls and indicators. The processor sheet comes last, so its pins are assigned once.
- Check the skeleton before any part is drawn. KiCad's exported netlist leaves out a net with no part pin, so an empty hierarchy cannot be checked from it. `sch_check.py modules --probe` makes a throw-away build with one test point on every hierarchical label, and checks that each top-level net reaches the modules `design/module-nets.csv` lists for it. It then cuts one net in the copy and must fail on it, so the check is shown to catch a fault. The probe copy is built in `.hwtmp/` and removed.
- Page size follows what is on the sheet: a smaller page for a sheet with little on it, a larger one for a dense sheet.
- Do not put too much on one sheet. A sheet a reader cannot take in at once should be split.
- If the multi-sheet build fails ERC or does not open cleanly, stop and report. Do not fall back to one flat sheet without the user.

## Conventions

Apply these unprompted unless `design/status.md` records the user's own conventions (the `Schematic drawing habits:` line), which win. Each rule says how it is checked. "By eye" means no script checks it: you look at the plot (Visual check) and give the result in the report.

Rails and nets:

- every supply rail and every ground is drawn with the KiCad standard power symbol for it, never with a label. This is the default, not something to ask for (`sch_check.py rails`);
- a rail is global through its power symbol. It is never a sheet pin, a hierarchical label or a local label (`sch_check.py rails`);
- a power symbol is used only for a rail that is one net in the whole design. Two nets that differ get different names, even at the same voltage, and are never joined through a shared symbol name. A return that is kept apart from ground is not drawn with the ground symbol. Nets that must stay separate are rows of `design/separate-nets.csv`, each with the one part allowed to join them (`sch_check.py rails`);
- three kinds of label, each with one use. A local label is for a net that stays on one sheet. A hierarchical label is only for a net that crosses a module's edge as a sheet pin. No signal goes on a global label (`sch_check.py rails`, `sch_check.py modules`);
- parts that sit close together on one net are joined by a drawn wire, and turned so the wire is short. A label is used only for a net that leaves the area or the sheet. Labels have meaningful names (by eye).

Placement and text:

- a titled frame around each functional block on a sheet (by eye);
- signal flow left to right, supplies at the top, ground at the bottom. Supply symbols point up and ground symbols point down (by eye);
- the blocks on a sheet are centred on the page and aligned on one another. The drawing does not start from the top-left corner (by eye; the centring helper in `schlib.py` places it);
- a two-pin part drawn between two rails or two nodes sits midway between them (by eye; the midway helper in `schlib.py` places it);
- reference, value and label text sits beside its part, aligned, and never over other text, a wire or the frame. This is a rule the drawing must meet. `sch_check.py overlap` reports text that overlaps and the build needs none; alignment and position are by eye;
- decoupling capacitors drawn beside the supply pin they serve, pull resistors beside the pin they pull (by eye).

Circuit defaults:

- every button or switch read by a processor has a small debounce capacitor at the switch. Debounce is never left to firmware alone. The value comes from a calculation in `design/calcs/` against the input's thresholds and the switch's contact rating, with the margin stated (EL-48);
- the ordinary parts of a standard small circuit are drawn without a figure to justify each one. Leaving one out is the user's decision, and is reported as one (`references/review.md`, Basics review);
- every not-fitted or optional part marked as such, with its reason;
- every unused pin handled as its datasheet says (tie, pull or leave open), with a no-connect mark where it is left open (`sch_check.py unused`);
- every sheet carries its sheet comments (below).

## Footprints and models

- Every symbol has a footprint that exists in the KiCad libraries or the project library. A missing footprint is a violation, or a waiver (DC-); never "will add later". An earlier board reached layout with footprints on 7 of 47 parts.
- The footprint matches the package of the exact MPN (`design/parts.csv` `package`), checked against the package drawing in the physical pass.
- Every footprint has a 3D model that exists on disk, or a waiver.
- Library pinning: symbols, footprints and models the project uses are copied into the project library, with the KiCad library version recorded, so a library update cannot change the board.
- Optional footprints for tuning (snubber, filter, series resistors, a second capacitor) come from datasheet optional parts and reviewer remarks; each is a recorded choice.

### Parts not in the KiCad libraries

1. Look for the maker's own symbol, footprint and 3D model first, then a distributor's or library service's download. Record the source, the date and the licence terms in `datasheets/README.md` (publishing may depend on them, PB-01).
2. A downloaded part is not trusted. Check it as if you made it (steps 4 and 5).
3. Otherwise make it in the project library: the symbol from the datasheet pin table (pin numbers and names exactly as in `design/pins.csv`); the footprint from the datasheet's recommended land pattern, or from the package drawing by the method the datasheet or the library's own conventions name; the 3D model from a library model of the same package outline, or a simple block of the drawing's maximum height.
4. Check the footprint against the datasheet's drawing, dimension by dimension: pad size and pitch, pin 1, top or bottom view, the exposed pad and its paste, courtyard and silkscreen outline. Write a short script that reads the footprint file and prints each dimension beside the drawing's value, so the check can fail.
5. Check the 3D model's height, offset and rotation against the drawing (`model_checked` in `design/parts.csv`).
6. Anything not checked by a script goes under "Not verified", marked "by hand, not a script".

## ERC and netlist

1. Run ERC through `build.py` (or `kicad-cli sch erc --severity-all`). Expected: 0 violations. Any violation is fixed or waived by a decision (DC-), and the waiver is passed to the build. A violation that waits on a sheet not yet drawn is not waived: record a decision and list it under "Expected ERC items" in `design/status.md` (`project-files.md`). The build then stops only on a violation that is not listed, or a listed one that is gone, and still exports the netlist. An expected item names the violation's text and one of its items, such as a pin of a part. The number of a power symbol or power flag reference is ignored, because KiCad does not name the same power symbol in every run: write `#PWR` or `#FLG`.
2. Never lower an ERC severity or add an exclusion without a decision. `table_check.py suppress` reports lowered severities and exclusions with no decision.
3. Export the netlist with `python3 hwskills/build.py netlist`, which strips the machine path and export time. Do not commit a raw `kicad-cli` netlist.
4. Read back every net you changed, with all its pins, from the exported netlist. Compare each with the intent and put the list in the report.
5. Hidden pins and power pins: list them per symbol. None may join a net silently. `sch_check.py pins` lists them.

What KiCad does and does not tell you:

- The exported netlist leaves out a net with no part pin on it.
- Power symbols join by name across every sheet. ERC does not flag two rails joined by a shared power symbol name; `sch_check.py rails` does.
- ERC reports empty sub-sheets, and missing power flags until the supply sheet is drawn. These are the violations that wait on a sheet not yet drawn (step 1).
- An unused pin tied to ground can raise a pin conflict. The pin may need the passive type in the project's copy of the symbol; record that change.
- Removing a label renames its net. Compare which pins are on a net, not the net's name.

## Scripted checks

Run these on every schematic build and give their output. Run the whole set again after your last edit; a result from before the last edit is not a result. They read the exported netlist, the `.kicad_sch` files and the project tables, never the generator's internals.

| Command | What it does | Result |
|---|---|---|
| `sch_check.py pins` | symbol pins, footprint pads and netlist against `design/pins.csv`; used functions supported; limits; hidden and power pins; unconfirmed rows | pass or fail |
| `sch_check.py alloc` | two uses of one peripheral instance, timer or DMA channel; debug pins reused; functions blocked while the radio runs | pass or fail |
| `sch_check.py powerup` | every control input has a pull, tie or driver giving its required state while the microcontroller is in reset; fights; names the part that gives each state. A state given only by an internal pull is listed for the reviewer, not failed. A pin of an IC not marked as a control input whose name reads as an enable, reset, shutdown or address pin is listed for the reviewer too. With no control input in `design/pins.csv` it is not run | pass or fail, or not run |
| `sch_check.py rails` | a power symbol whose name is not a rail in `design/rails.csv`; a rail that is more than one net; two rails, or a label, on one rail wire; a rail passed as a sheet pin or on a hierarchical, local or global label; a signal on a global label; two nets of `design/separate-nets.csv` joined by anything but their one link part. It compares the drawing as it read it with KiCad's own netlist, and its pass line says "not proven" when it could not. Buses are not followed | pass or fail |
| `sch_check.py modules` | `design/modules.csv` and `design/module-nets.csv` are consistent; exactly one sheet per module (a sheet of text only, such as the firmware page, is no module); the top sheet holds only module boxes; every designator is in its module's block; every net that joins two or more sheets is a table net and joins only the modules listed for it. A table net that is drawn with part pins on it, and is no net of its own in the netlist, fails: it is joined to another net, and the fail names that net. A table net on labels with no part pin yet, or on no label, is a note. With `--probe`, the same on the empty skeleton, where a table net that does not reach its modules fails | pass or fail |
| `sch_check.py drive` | two or more transistor bases on one net with no resistor each. Shared gates are listed | pass or fail |
| `sch_check.py chosen` | every position of a kind in `design/chosen-parts.csv`, with the part drawn there and its supplier number; a position with another part and no recorded exception | pass or fail |
| `sch_check.py fields` | a symbol with no supplier part number or no datasheet link; a datasheet link or description that names another part; a part number or supplier number that differs from `design/parts.csv`. Run it by name: it is not part of `all` | pass or fail |
| `sch_check.py overlap` | text that overlaps other text, a symbol or a wire on a sheet. Text overlap only, from estimated text sizes; the frame and the other style rules are by eye. Run it by name: it is not part of `all` | pass or fail |
| `sch_check.py protect` | every net that reaches a connector, button, exposed metal or antenna, with the parts on its path; a resistor to a rail or ground is listed as a pull, not as part of the path | review list |
| `sch_check.py domains` | voltage-domain crossings and back-feed into an unpowered part | review list |
| `sch_check.py opendrain` | pulls per open-drain bus and rail | review list; a net with no pull fails until its item is closed |
| `sch_check.py unused` | unconnected pins with the datasheet's note | review list |
| `sch_check.py decouple-list` | capacitors on each supply net | review list; supply pins with no capacitor to ground fail until the item is closed |
| `sch_check.py testpoints` | nets lacking a requested test point | pass or fail |
| `sch_check.py currents` | current through each divider and pull. A supply rail is at the voltage `design/rails.csv` gives it; a range is taken at its highest | numbers |
| `sch_check.py railcap` | total capacitance per rail, for the regulator's and source's limits | numbers |
| `sch_check.py netload` | the load on each rail and each driven net, summed across every sheet that touches it, and its share of a budget you give. Resistor loads only: add the supply currents of ICs and transistors from the budget calculation | numbers |
| `table_check.py compliance` | rows with no schematic result; hard rows closed without a decision | pass or fail |
| `table_check.py parts` | sourcing fields, packages, footprints, models, cost; stock and price dates older than 30 days are listed with their age (a fail only with `--stage ST12`, before ordering) | pass or fail |
| `table_check.py netreview` | review-list items in `design/net-review.csv` not closed with a reason, listed and counted; closed items without a date or a cited part or row | pass or fail; open items fail only with `--stage ST6`, the schematic checkpoint |
| `table_check.py checklists` | checklist items that apply with no result in any review report, listed and counted | pass or fail; they fail only with `--stage ST6` or later, for the items of stages up to it |

A table check whose table is not there prints "not present, check not run" and is listed, not failed, until the checkpoint (`--stage ST6`; `ST11` for `constraints.csv` and `fab-capabilities.csv`).

Review lists are not pass or fail, with two exceptions below. Each item goes into `design/net-review.csv` and is closed by a written reason: a protection part named, a decision, or "checked per pin on the board (CN-)". A worker may close an item with a reason that cites a part or a row; anything that needs a judgement about risk (for example "no protection needed on this header") is proposed and closed by the user.

Two review lines fail by themselves: an open-drain net with no pull (`opendrain`), and a supply net that has supply pins and no capacitor to ground (`decouple-list`). Each prints a FAIL line and the script exits 1. The fail ends when a part is fitted, or when the item is closed with a reason in `design/net-review.csv`. A closed item whose line has changed since is open again, and fails again. A pin left unconnected is in the `unused` list and does not fail here.

`powerup` with nothing to check is not a pass. When no row of `design/pins.csv` has `control_input` yes, `all` names it as not run, and `powerup` asked for by name exits 2. If the board really has no control input, record it with the line `Control inputs: none` in `design/status.md`, with its decision; the check then passes and says the count is 0. A pin of an IC (a U or IC designator) marked "no" whose name reads as an enable, reset, shutdown or address pin is printed as a review line. Check each one against its datasheet and give the result in the report. The script goes by the name only, so it can miss a control pin with another name.

Example of what `powerup` exists to catch: a boost converter's enable pin left floating while a microcontroller is meant to drive it. Before firmware runs, the converter may switch on or off by itself. The table says the enable must be "off" in reset; the check fails unless a pull-down (or another defined driver) gives that state, and names it.

`powerup` covers reset. It does not cover a processor that hangs with its pins still driven, or a reset that leaves a timer output running. Those are LG-11, judged by you from the datasheets.

Internal pulls: never rely on a part's internal pull where its datasheet says not to. An earlier board did, and withdrew it. `powerup` cannot tell which internal pulls a datasheet rules out, so it lists each pin that relies on one ("review: relies on an internal pull"). Check each against the part's datasheet and give the result in the report.

Chosen parts: when the user names a part for a kind of position, it goes to every position of that kind in the whole design. The report lists the positions the part went to and those it did not, from `sch_check.py chosen`. Another part at such a position needs the user's decision for that position, recorded in `design/chosen-parts.csv` (`except_refs`) and by a decision of the user that names the designator.

Project checks: a check that belongs to this one project lives in the project's own checks folder (`checks` under `scripts` at the project root) and is run by the build through the `checks` list in `design/build.json`.

If a script does not exist yet in the project's `hwskills/` folder, do the check by hand from the same inputs, mark it "by hand, not a script", and list it under "Not verified" in the report.

## Calculations and simulation

Every threshold, divider, timing network, current limit and budget gets a worst-case script in `design/calcs/` (template in `references/project-files.md`). No hand-only worst case. Inputs come from DS- rows and `design/parts.csv` tolerances; results go into the rows' `design_value` and `margin`.

`design/calcs/` is the one calculations folder. The generator and the sheet comments read their values from it, so a value is worked out in one place only.

A worst-case threshold result counts leakage and bias currents, or lists the terms it left out (`worstcase.py` prints them). When a term is added, run the rail budget again.

Each sheet report states the load the sheet adds to each rail. After every block, give the share of each rail's budget used, from `sch_check.py netload` (give it each rail's budget and the level) and the budget calculation, and flag a rail above the level the brief sets.

Typical scripts: regulator design equations with effective values; under-voltage and lockout thresholds; supply drop budget (cable, connector, fuse, reverse-polarity part and filter at peak load against the regulator's minimum input); clock frequency budget against the protocol; interface timing (set-up and hold with level shifters and track delays; baud error); current per rail per state; life (capacitor life at temperature, contact cycles, flash endurance).

Simulation is a step of the schematic stage, done module by module. The procedure, the files and the report form are in `references/simulation.md`. The user may decline it for a module, and that is recorded. A simulation never replaces the worst-case calculation, and it never closes a layout or grounding row.

## User journey

Walk the user journey from `design/requirements.md` against the schematic: for each step, the button, indicator, connector or access it needs is on the sheet and connected to something that makes it work. Report each step and its result. Missing features are proposed as decisions, not added.

A sheet that holds user controls or indicators reports what each one needs from outside the sheet: a firmware duty, a rail that must be up, a part on another sheet.

## Sheet comments

Every sheet carries plain-English comments, on the sheet. This is the default, not an option the user is asked about.

- A very short theory of operation for the sheet.
- A short paragraph for each important part of the circuit. A protective block's paragraph walks through the failure it guards against, step by step.
- The thresholds that matter for testing, each with what to look at.
- A short note beside each non-obvious circuit, citing the DS- row or decision behind it.

The comments are generated with the sheet. Their values come from the same calculation in `design/calcs/` that sets the part values. A comment holds no value that is not on the sheet or in a calculation, and no designator typed by hand. Regenerate the comments with every change to the sheet.

## Notes pages

Notes pages are whole text sheets. The firmware page is one the schematic always closes with: a text sheet inside the schematic that lists the work the hardware leaves to firmware, generated from `design/firmware.md`. The collection procedure and the page are in `references/firmware-instructions.md`. Other notes pages (overview, quality report) are made if the user wants them.

For every notes page:

- write it in plain English;
- generate designators, counts and status claims from the tables and the latest tool output, never by hand (WR-15); re-check every one before reporting;
- mention tools or how the files were made only if the user wants it;
- read back any dictated name or number to the user before it goes on a sheet (the coordinator does this).

## Security and boot

At the schematic stage, find the hardware-set security and boot features of each microcontroller from its reference manual and security application notes:

- debug lock and readout protection, and how they are set;
- secure boot and key storage;
- one-time fuses or option bytes;
- boot-mode and strapping pins, their sampled state at reset, and what drives them.

Each feature the design uses is a row and a pin-table entry. Every irreversible step (a fuse burn, a permanent lock) is flagged in the report and recorded as a decision. Firmware-side settings go in the firmware instructions, `design/firmware.md` (`references/firmware-instructions.md`).

Never settle a hardware question by writing "firmware will handle it". Moving a duty to firmware is a decision made with the user: propose it, and record it in `design/firmware.md` as decided or not decided. Flag any "must" line that is the only guard of a hardware start-up condition.

## Visual check

The visual check is required before a sheet is reported. It is for drawing style and readability, not correctness. It is never evidence that the circuit is right, and it never replaces a script (WR-02).

1. Export the whole schematic as a PDF (`kicad-cli sch export pdf`), then render each page to an image. Do not use square thumbnails; they cut wide sheets.
2. Look at every sheet you changed. Check it against each rule under Conventions that is marked "by eye", one by one. Also look for labels not aligned with their wires or pins, text outside frames, crowded areas and wires through labels. `sch_check.py overlap` covers text overlap only.
3. Give the result in the report: each sheet looked at, the image file, and each rule as met or not met. Mark it "by eye, not a script".
4. Fix what the brief covers; list the rest as findings. The user cares about label alignment.

## Done

No lock file found before each build; ERC 0 violations or each waived; every changed net read back; every part with a footprint, a 3D model (or waiver), four sourcing fields and its datasheet link; every scripted check run after the last edit, `rails`, `modules`, `chosen`, `fields` and `overlap` among them, and its review lists closed with reasons in `design/net-review.csv`; worst-case scripts run; each module simulated, or the user's decision not to recorded; user-journey walk-through done; every sheet with its sheet comments, generated from the calculations; every sheet you changed looked at as a plot, with the result per style rule in the report; firmware duties from your sheets passed to `design/firmware.md`; every DS- row for the parts in scope has a schematic result; each difference from the typical-application list (written at the parts stage) has its reason; for each carried grounding or layout row, a note whether the schematic must provide anything (its own net, a net tie, a sense connection, a footprint), and if so it is a schematic row as well, proposed to the user as one list; pin rows not yet confirmed listed by designator; the diff explained.
