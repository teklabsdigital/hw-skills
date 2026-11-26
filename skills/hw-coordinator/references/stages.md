# Stages: the coordinator's view

Read only the section for the stage at hand.

Each stage lists:

- **Entry:** what normally comes first.
- **Ask:** the questions for this stage, asked as one short batch with proposed answers (`questions.md`).
- **Human decides:** what only the engineer decides.
- **Checkpoint:** where the engineer looks and decides, if the stage has one.
- **Done:** what must exist before you call the stage done. Check each item from a report or a script, not from memory.
- **Brief:** which workers to start, and the worker procedure to name in the brief. The procedures live in the hw-worker skill's references; name the file and section, do not copy them.

## Opening rule

Every "Entry" is what normally comes first, never a lock. If the user wants to go on without it, say what is missing and the risk in plain English, record a decision in `design/decisions.md`, and go on.

Three designs, in the owner's words: logical (what the board does: blocks, interfaces, states), electrical (the schematic), physical (the board). ST1 to ST6 form one loop that repeats until stable. Checks and reviews at ST5 and ST6 feed back into requirements and parts. Going back is normal and is recorded with its reason.

A part added at any time gets its datasheet passes (ST3) before it enters the schematic, or in parallel with the schematic work, marked "rows pending" until the passes are done. With the datasheet reading setting "as parts are placed", see ST3.

No worker writes a document whose only use is as a step toward the real output. Scratch work goes in `.hwtmp/` inside the project and is never kept.

---

## ST0 Start and project setup

- **Entry:** the first-session table confirmed.
- **Ask:** nothing more (see "First session" in SKILL.md).
- **Human decides:** the table; approval to install or clone anything.
- **Checkpoint:** the setup plan, which is part of the first-session table.
- **Done:**
  - git repository, private, no remote unless asked. If the user wants none yet, record that as a decision and go on: the checks that compare with a commit say "cannot tell" instead, and the sufficiency baseline (`design/constraints-reviewed.csv`) needs no git;
  - the project layout: `README.md`, `AGENTS.md` (or the tool's own file), `.gitignore` (with `design/.private-terms`, the scratch folder `.hwtmp/`, KiCad's local state files, such as `*.kicad_prl`, and saved third-party documents if the user said they are not committed), `.gitattributes`, `hwskills/`, `scripts/` for the project's generators, `hardware/` (an existing project keeps its own folder for the KiCad files), `datasheets/`, `design/`, `docs/`, and `firmware/` with a README only;
  - the `design/` files written from the worker's templates, with the confirmed settings in `design/status.md`, `design/user-rules.md` started with any rule the user has already given, and `design/build.json` with the project's build settings;
  - the scratch folder `.hwtmp/` made at the project root and git-ignored. Every throw-away file goes there, never in a system or session temporary folder;
  - the living checklists and packs copied into `design/checklists/`: `logical.md`, `electrical.md`, `board.md`, `packs.md`, `fabrication.md` and `repository.md` (from the worker's `checklist-*.md` and `packs.md`);
  - the tool check recorded: KiCad version, Python, C compiler, which PDF route exists (the tool's own PDF reading, the macOS scripts, or none yet). The release date of each tool already installed is reported and checked against the user's `Tool version rule:`, not only new installs; each exception is a decision. KiCad's own update check and backup settings are the user's settings outside the project: they are reported, never changed;
  - the grid router cloned and built at a pinned tag or commit, with its tests run, if the user approved. If not (no approval, or no C compiler), record that and go on: everything up to placement works without it, and routing waits or is done by hand;
  - the skill scripts copied with `build.py --copy-skill-scripts <project root>` into `hwskills/`, with the skills version recorded, so the project builds without the skills installed. The copy never overwrites: a file there with other bytes stops it with a list, and you ask the user;
  - `design/status.md` with its `Execution mode:` line (`platforms.md`);
  - `design/ownership.csv` started;
  - `design/decisions.md` started, with the user's first message as its first entry and then one entry per row of the first-session table (`decision-log.md`);
  - for an existing project, the adoption report (below).
- **First sprint (SP-01, setup and requirements draft).** The setup worker and the requirements-draft worker run in parallel, so each owns its own files and never writes the other's:
  - you write `design/decisions.md` (the user's first message, then the first-session table) and `design/sprints/SP-01-setup.md` from the confirmed table before either starts;
  - the setup worker writes every other file in `design/` except `design/requirements.md` and `design/decisions.md`, and records the confirmed settings in `design/status.md`;
  - the requirements-draft worker writes only `design/requirements.md` and its own report. Its brief holds the confirmed settings, because `design/status.md` may not exist yet when it starts.
- **Brief:** build worker "set up the project"; procedure: worker references repository.md (Layout; Git and commits), tooling.md (Install policy; KiCad; PDF tools; Router). Remind the worker: never install without approval; exact versions at least 30 days old; no auto-update; the user's own tool version rule, if one was given; on Windows and Linux, report anything that behaves differently; the router needs a C compiler, and a failure there is reported, not worked around.

### Adopting an existing project

When the folder already holds a KiCad project, the first-session table says it will be adopted. This is not a separate question. Brief a build worker "adopt the project"; procedure: worker reference adapting.md (Adopting an existing project). The brief says: change no design file.

The worker:

0. Runs after setup (ST0 above), which adds `design/`, `hwskills/` and `datasheets/` beside the user's files and moves nothing. The project's own `build.py`, `scripts/` and modules are never touched: the skill scripts live only in `hwskills/` and import only each other. In a project that has its own generators, `pcblib.py drc` runs on a copy when the project's own build writes the board or project files. Ask the user before any skill script writes design files there.
1. Takes an inventory: files, where the KiCad project is, KiCad version, sheets, board state, libraries, rule file, BOM fields, datasheets present, any generator scripts.
2. Records every design file as hand-owned, and the folder that holds the KiCad files when it is not `hardware/` (one line in `design/status.md`); the layout is kept. If the project has its own generator scripts and the user chose to keep them as writers (first-session table), each file a script makes is recorded as script-owned with that script as its writer, but only after the worker has run the user's build and shown it reproduces the file on disk. A file it cannot reproduce stays hand-owned, and the worker says why.
3. Exports the netlist and the BOM (`build.py erc netlist bom`).
4. Builds the state files, every template copied: requirements drafted from the schematic and notes, marked "to confirm" with the engineer; `parts.csv` from the symbol fields; `pins.csv` per part; DS- rows from the datasheets (ST3, with three passes for complex and pack parts), or, while the datasheets are not fetched yet, pin rows from the symbols marked unconfirmed; `fab-capabilities.csv` if the manufacturer is known; `constraints.csv` seeded from the user's own rule file and net classes.
5. Runs every check, and ranks the findings.
6. Proposes a first sprint.

You then report the ranked findings, and put the first sprint to the user. No redesign unless asked.

---

## ST1 Requirements (the logical design starts here)

- **Entry:** the first-session table confirmed (the draft runs beside ST0), or a pivot.
- **Ask:** with the requirements read, as one batch built from the draft's "to confirm" list, each with a proposed answer. `questions.md` Problem and user story, Environment, Misuse, Interfaces, Test points and Preferences, only for the areas the switches turned on. The problem the product solves and one user story; every supply the board might see, and for each external input the surge or over-voltage it must survive and on what basis; how each power source really behaves (its limits, its impedance, how it responds to load), so a model of it can be made before the input block is drawn or simulated; the temperature range (asked, never assumed); the region of use; what a user could do wrong, and how protection ranks against cost; interfaces with exact variants and speeds; whether controls and display are on the board or in an app; size and enclosure if known; indicators and buttons; budget and cost sensitivities, and for a board that will be sold the market scan and a cost target; service life; test points for bench work and for production test and programming.
- **Human decides:** functional requirements, quality characteristics, budget.
- **Checkpoint:** the user reads the requirements draft. A read, not a lock.
- **Done:** `design/requirements.md` with the problem and the user story, FR- and QC- items, environment profile, misuse table, user journey, board profile (switches on and off with reasons), test points; each item with its source (the user's words and date, or "proposed, to confirm"). Every feature was tested against the user story before it went in. A switch kept off on a stated condition records the condition; test it again at every requirements change, and ask again whether the board will be sold when the signs change. A figure marked proposed is not designed against until the user confirms it.
- **Brief:** build worker for the draft; procedure: worker reference requirements-parts.md (Requirements; Environment). Research worker for any named standard: fetched and cited, never from memory. Remind the worker: quote the user; mark inferences "proposed, to confirm"; never add a requirement.

If the enclosure is not known, record that the board shape will be provisional.

---

## ST2 Research

- **Entry:** open questions on protocols, architectures or support chips.
- **Ask:** options to explore; parts or ecosystems the user knows well.
- **Human decides:** the architecture direction. Never change it without asking.
- **Done:** options side by side, each with function fit, price, stock, ecosystem, risk and sources. Each block price is shown beside the running cost of the whole board.
- **Brief:** research worker, with the requirements quoted by ID, word for word; a brief that spans most of the requirements cites them by ID at a named commit instead (`briefs.md`, Research). Procedure: worker reference requirements-parts.md (Research; Candidates). The brief says: search broadly; do not narrow by one package or one filter too early; price and stock with every candidate, in the order of the user's `Suppliers:` line; a source for every fact; generic part numbers and keywords only to outside services.

**The research loop.** Research before part choice is a loop: research, report, the user reads, pivot or accept, repeat. Expect it to go round more than once. A pivot here is normal research and takes the light form (SKILL.md, "Pivots").

**Market scan.** For a board that will be sold, the scan and a cost target come before part research, in the form the user chose at setup: light (a cost target and a comparison table) or full (a research step of its own). "None" is recorded as a decision.

**Blocks researched apart.** Briefs for blocks researched in parallel carry the same stated assumptions, and each asks for the block's interface figures. A cross-block recheck follows before parts are chosen.

---

## ST3 Parts and datasheets

- **Entry:** a candidate part chosen for a block.
- **Ask:** `questions.md` Parts and derating: approval for any part that raises cost; the user's derating policy (once, recorded). Suppliers and preferred makers are not asked again: use the `Suppliers:` line in `design/status.md`.
- **Human decides:** part choice; every "does not apply" or "not met" on a layout, grounding, protection or absolute-maximum row (ask while other work goes on); what to do about a delegated layout document that cannot be found; each material datasheet error (worker rule WR-22), logged with the MPN and revision so it is not asked again.
- **Checkpoint:** a part enters the schematic when its DS- rows and its pin table exist. Rows may still be open.
- **Done, for each part:**
  - datasheet, revision and text extract in `datasheets/`; errata where the maker publishes them; every delegated document (evaluation board guide, layout application note, module placement guide) fetched or raised as a decision;
  - `parts.csv` row complete, including role and category. A category that belongs to a pack switches the pack on; say so in your next report;
  - `sections.csv` lists every section of the datasheet, the passes that claimed it, and the rows each took; no section unclaimed;
  - the passes done: three separate workers (logical, electrical, physical) for complex or sensitive parts, or one combined pass for simple parts, per the setting;
  - every page of the datasheet and its delegated documents rendered once by the fetch; after the merge, the pages behind figure and graph rows kept in `design/renders/`;
  - `compliance.csv` rows for every instruction and limit, including figure and graph rows read from the page renders;
  - the typical application and the evaluation board written down as a list of their parts and values. No schematic exists yet; each difference from the design gets its row and reason at ST5;
  - `pins.csv` for the part;
  - for every node shared by two blocks, one table of every part on it, with the voltage at normal, at surge and at each named single-fault case against each part's rating;
  - for every microcontroller, module and connector, and any part the user names: the pin check done by a second worker (what normally comes first; open rows are listed, never a lock).
- **Brief:** in this order:
  1. **Fetch.** One worker gets the datasheet, errata and the documents it delegates to, saves them, renders every page once, writes the `datasheets/README.md` lines and the revision in `parts.csv`, writes the section inventory, and notes any simulation model the maker publishes. Passes never fetch or render the main datasheet, so parallel passes never write the same file (`briefs.md`, Fetch).
  2. **Passes.** Complex or sensitive parts (power, microcontroller, radio, interface ICs) and every part in a switched-on pack: three datasheet-pass workers, one per perspective, using the perspective briefs in `briefs.md`. Simple parts (passives, connectors, jellybean discretes): one combined pass with the three headings, the default; one worker may take several parts. For a datasheet too large for one worker to read well, split it by the section inventory: each pass reads the inventory and only the sections it claims, in full, from the renders. Say the expected size in the sprint plan.
  3. **Merge,** below.
  4. **Pin check.** For every microcontroller, module and connector, and any part the user names: a pin-check brief to a different worker from the one that wrote the pin table (`briefs.md`, Pin check brief). What it cannot confirm goes to the user as one batch at the schematic checkpoint.

  Procedure: worker reference datasheets.md, all sections, and the project's copy of the packs, `design/checklists/packs.md`, for the part's category. Each brief goes in its own file in `design/briefs/`.

What to watch for in the reports:

- sections with no rows, and why;
- rows needing a user decision;
- pins the pin check could not confirm;
- figures that could not be read. If no PDF route can render pages, tell the user: figure rows stay open;
- fetches a site refused, listed in one place in the report, with the sources tried;
- datasheet errors and inconsistencies: material ones are decisions for the user, the rest are findings;
- simulation models the fetch found, for the simulation step at ST5;
- choices the workers made, which you log.

When the passes are done, a worker merges rows that two passes both wrote into one row with both tags, never dropping either, and resolves every section flagged by `table_check.py sections` (worker reference datasheets.md, Merging passes).

**Datasheets read as parts are placed.** The user may choose this form at setup (the `datasheet reading` setting) in place of the up-front passes. Each part's datasheet is then read as the part is placed, and each value and connection cites its section. No pass documents are written. Say the risk when you offer it: an instruction outside the sections read can be missed. Under this form the fetch still runs first, the pin rows are still written as each part is placed, so the pin check runs, and the DS- rows for a part are written with its sheet. The checkpoint above and the ST5 "Done" list then apply sheet by sheet. Recommend the blind review more strongly: it is the check for what was not read.

---

## ST4 Logical design

- **Entry:** requirements and candidate parts exist.
- **Ask:** blocks and interfaces as the user sees them; the sleep and wake strategy; what each indicator and button tells the user.
- **Human decides:** the block split, interfaces, states.
- **Checkpoint:** the user agrees the block diagram, the states and the module definitions.
- **Done:** "Logical design" in `design/requirements.md`: blocks, interfaces, power tree, states (start-up to shutdown, sleep, fault, removal), user-journey steps (unbox, plug in, power up, connect, use, fault, unplug, store) mapped to FR- IDs. The stage ends in the module definitions. Each module maps to exactly one sub-sheet of the schematic:
  - `design/modules.md`: per module its purpose, edge nets, parts and open points, and the drawing order;
  - the tables the scripts read: `design/modules.csv` (one row per module, with its sheet and its fixed designator block), `design/module-nets.csv` (the nets between modules), `design/rails.csv` (the declared rails) and `design/separate-nets.csv` (nets that must stay separate).
- **Drawing order,** given in `design/modules.md`: the top sheet first, so the sheet pins are fixed; then the power path, the safety path, the supplies, inputs, measurement, and user input and output; the processor sheet last, so its pins are assigned once.
- **Brief:** build worker; procedure: worker reference requirements-parts.md (Logical design). Then a review worker with the full logical checklist (checklist-logical.md). The brief says: derive the features a user needs, not only those listed (a pairing button was missed this way once); put non-obvious connections and their layout cost to the user as decisions.

---

## ST5 Schematic (electrical design)

- **Entry:** the logical design agreed for the blocks in the sprint.
- **Ask:** `questions.md` Schematic, and Security and boot:
  - the feature list as it stands, shown before the first sheet is drawn, for the user to confirm;
  - sheet style. Default: a hierarchical schematic in KiCad's native form. The top sheet shows the modules as boxes joined by nets, and each module is one sub-sheet. The main power path between the boxes is drawn as wires with each net name visible, so the reader can follow the power; ask only how the other nets between boxes are joined, by wires or by labels. One sheet with functional frames is the other form, if the user prefers it;
  - the user's schematic drawing habits: rails, labels, wires, text and page balance. Record them on the `Schematic drawing habits:` line;
  - what testing the user plans (`questions.md`, Test points);
  - simulation: which modules, if any, the user declines, and controller in the loop where firmware closes a control loop (see below);
  - the hardware-set security and boot features found for this microcontroller: debug lock, readout protection, secure boot, one-time fuses, boot-mode pins;
  - whether the user wants to assign microcontroller pins in the vendor's configuration tool. Its export is the highest-trust source for the pin table;
  - whether any grounding or layout instruction in the carried rows needs its own net, a net tie, a sense connection or a footprint in the schematic (a worker proposes the list).
- **Human decides:** circuit trade-offs; simulation declined for a module; controller in the loop; leaving out an ordinary part of a standard circuit; the hardware-set security and boot choices.
- **Done:**
  - schematic built; ERC 0 violations, or each one waived by a decision;
  - the netlist read back for every changed net, with its pins;
  - every part has a footprint and a 3D model (or a waiver) and four sourcing fields: manufacturer, part number, supplier, supplier part number. A part not in the KiCad libraries gets its symbol, footprint and 3D model made, or taken from the maker, and checked against the datasheet's drawing (worker reference schematic.md, Footprints and models);
  - for each carried grounding or layout row, a note whether the schematic must provide anything (its own net, a net tie, a sense connection, a footprint); if so, it is a schematic row too;
  - the typical-application list from ST3 compared with the schematic, each difference a row with a reason;
  - the scripted checks run (pins, power-up states, protection walk, domains, open-drain, unused pins, test points, currents, rail capacitance, allocation, decoupling list); every review-list item in `net-review.csv` closed with a written reason;
  - worst-case scripts in `design/calcs/` run for every threshold, divider, timing network and current limit. `design/calcs/` is the one calculations folder: generators and sheet comments read their values from it;
  - the user-journey walk-through done;
  - sheet comments on every sheet. This is the default, not an option: a very short theory of operation in plain English, a short paragraph for each important part of the circuit, and the thresholds that matter for testing with what to look at. The text is generated with the sheet from the same calculation that sets the values, holds no value that is not on the sheet or in a calculation, and is updated with every change;
  - the firmware instructions in `design/firmware.md` collected for every sheet drawn so far, starting with the first sheet;
  - the closing steps below, in their order.
- **Closing steps,** after the last sheet, in this order:
  1. **Basics review.** For each sheet, start a worker that did not draw it. It reads the sheet circuit by circuit. Each standard small circuit is compared with what a circuit of that kind ordinarily carries. Each ordinary part that is absent is added, or listed with the reason it is not needed, as a decision for the user. It comes first because it may add parts. Procedure: worker reference review.md (Basics review).
  2. **Simulation** of the modules not yet simulated (see below).
  3. **Test sweep.** One sweep through every module lists what must be tested, how (the signal, what is applied, what is expected, from the sheet's testing notes), and which test pads, connector pins and isolation links that needs. Output: `design/test-sweep.md`. The pads and links it finds are then added to the schematic. No test access is drawn before the sweep. The sweep is a list; it runs no test.
  4. **Firmware page.** The schematic closes with a text sheet that lists all the work the hardware leaves to firmware, made from `design/firmware.md`. Procedure: worker reference firmware-instructions.md (Collecting; The firmware page). The skills list what firmware must do and write none.
  5. The user examines the schematic (ST6).
- **Brief:** build worker per module, with the DS- rows in scope quoted; procedure: worker reference schematic.md, all sections. Build work is serial, in the drawing order, and one build brief covers at most two sheets. A read-only job (simulation, the firmware collection, a review) may run beside a build. The brief sets the rail budget level above which a load is flagged. A multi-sheet build that fails is reported; it is never silently replaced by one flat sheet. For a hand-owned schematic, add worker reference adapting.md (Proposing an edit; Editing KiCad files safely). Remind the worker: designators shift when parts are added; render a whole sheet from a PDF, not a square thumbnail; do not rely on internal pulls a datasheet rules out; KiCad must be closed while regenerating, and a lock file stops the build; with backup commits on, commit before each build; a worker that leaves out an ordinary part of a standard circuit lists it as a decision for the user.

**Simulation.** Simulation is a step of this stage, done module by module. It is not an install: `spice.py` loads the simulator library that ships inside KiCad. The procedure is the worker reference simulation.md; do not copy it into a brief. A module is simulated once its sheet is drawn, as a read-only job, and the rest at closing step 2. It matters most for: converter loop stability where the datasheet leaves the compensation to the designer; an input filter in front of a converter; analog circuits with dynamic or frequency behaviour; timing networks. These fail in ways hand checks miss.

- On a new project, send one module to simulation first, to prove the set-up. Only then brief the others.
- Each power input needs a source model that behaves like the real source (ST1). An ideal source hides the faults the source causes.
- The brief starts from the module's edge-case list (`briefs.md`, Simulation).
- Where firmware closes a control loop, offer controller in the loop: the control rule runs beside the circuit model. Say what it costs in time and what it shows. The user chooses; record the answer as the `controller in the loop` setting.
- The user may decline simulation for a module. Log it in `design/decisions.md` as kind "not done", with the reason.

Say plainly what simulation can and cannot show:

- what it can show: how the circuit behaves (start-up, loop response, transients, filter response, timing), and whether the design understands the part as the datasheet describes it;
- what it cannot show: the board. Layout, grounding, parasitics and heat are not in the model, so a good simulation never closes a layout or grounding row;
- that a model is the maker's, at a version, and is only as good as the maker made it.

Models are committed in `sim/models/` and listed in `design/sim-models.csv`. Results go in `sim/<module>/results/`, with the model's name and version, and are reported as simulation results, never as a bench test.

---

## ST6 Schematic review

- **Entry:** ST5 done for the scope, or a block changed since the last review (the baseline is the commit recorded at that review).
- **Ask:** which review modes. Offer a blind review.
- **Human decides:** each finding; whether the loop is finished.
- **Checkpoint: the schematic checkpoint.** Report the counts from `table_check.py summary`:
  - FR- ticked with evidence; QC- with results;
  - datasheet rows by schematic result; layout rows "carried" with constraints;
  - sections with no rows; sections no pass claimed; extraction misses found so far;
  - parts with no checked pin table, by designator, and the pins the pin check could not confirm, as one batch for the user;
  - the parts check: stock and price checked on a stated date (a check, not a freeze; parts can still change);
  - the engineer's own read of each block (for example power stage, drivers, interfaces, protocols, filtering), recorded.

  The engineer decides whether to go on to the board.
- **Done:** review reports; `findings.csv` triaged; checklist results.
- **Brief:** review workers with the full logical and electrical checklists and the switched-on packs; procedure: worker reference review.md. Pin assignment is item one, for every part. Thermal review at rising ambient. The board is out of scope here, except that datasheet layout sections are read and their rows carried. The blind worker gets only design files, datasheets and requirements (`briefs.md`).

---

## ST7 Board rules

- **Entry:** the schematic checkpoint, or the user goes on with items open (recorded).
- **Ask:** `questions.md` Manufacturer: manufacturer and service level; thickness, copper weights, a named stack-up; impedance control if a bus needs it; the clearance standard, if any (otherwise "own figure"); the user's own rule habits.
- **Human decides:** the capability table; the result of the constraint-sufficiency review. The user sees verdicts, not the raw table.
- **Checkpoint:** the capability table and the constraint verdicts, reported before any placement.
- **Done:**
  - `fab-capabilities.csv`, every value sourced (page and date, or "from the user"), including the assembler's limits (moisture level, reflow) and fees. A value that cannot be found is asked for, never filled from memory;
  - `constraints.csv` with every carried layout row, every design-intent rule (for example no vias on a bus), every user habit, and a default plane-link width rule. Each constraint uses a `check:` or `dru:` enforcer wherever one fits; a `review:` enforcer alone carries a written reason why no script fits. Report plainly how many rest on a reviewer's verdict alone; the user decides whether that is enough;
  - rule file and project file generated from the tables;
  - rule severities start from a raised list; any lowering is a recorded decision;
  - `table_check.py fabcap constraints suppress` clean;
  - the constraint-sufficiency review done: for each carried row, whether its constraints together enforce the whole quoted text (whole, partial, no). Partial or no gets more constraints or a `review:` enforcer.
- **Brief:** research worker for the manufacturer's pages; build worker for the rules; review worker for sufficiency (`briefs.md`). Procedure: worker reference board.md (Rules; Constraints; Constraint sufficiency). Remind the worker: never tighter than capability; every clearance names its standard or says "own figure".

---

## ST8 Physical definition

- **Entry:** ST7 under way or done.
- **Ask:** `questions.md` Physical and enclosure: outline, size, orientation, thickness; holes and keep-outs; the enclosure (drawing or 3D model); light pipes and button caps; connectors and mating parts; header pitches; where power enters; battery or external; LED sizes and colours; buttons; antenna position; which end faces the user; an outline file for the enclosure designer; the silkscreen content; fiducials and tooling holes for machine assembly.
- **Human decides:** every physical choice, and trade-offs such as antenna clearance against an LED position.
- **Checkpoint:** the physical definition agreed. If the enclosure is unknown, say the shape is provisional.
- **Done:**
  - outline, holes, fixed parts and keep-outs in the board; decisions recorded;
  - for a new board with no board generator yet, the project's board generator written (worker reference board.md, Board generator), unless the board is hand-owned;
  - fiducials and tooling holes placed as the assembler asks, if the board is machine-assembled;
  - the silkscreen content plan agreed: connector labels, what each LED and button means, polarity and pin-1 marks, the revision mark;
  - the outline exported as STEP or DXF for whoever designs the enclosure, if the user asked, and again whenever the outline or a user-facing part moves.
- **Brief:** build worker; procedure: worker reference board.md (Physical definition; Board generator for a new board). Remind the worker: a plain rectangle fits nothing; never give up an antenna keep-out without saying so.

---

## ST9 Placement and 3D sign-off

- **Entry:** ST8 agreed.
- **Ask:** `questions.md` User's own habits: placement habits (functional blocks, support parts at their pins, anything else the user always does).
- **Human decides:** the 3D sign-off before routing.
- **Checkpoint:** the user's 3D sign-off: LEDs, buttons, antenna, connectors, headers, all parts with their 3D models, unrouted. A rat's nest is fine.
- **Done:** every part placed by block; every 3D model present and checked for height and offset (or waived); courtyard DRC clean; placement constraints checked by `board_check.py`.
- **Brief:** build worker; procedure: worker reference board.md (Constraints; Placement; 3D sign-off). Ask for renders the user can look at. A picture is not a model check.

---

## ST10 Routing

- **Entry:** the 3D sign-off.
- **Ask:** confirm the routing guidelines. The owner's default list, which "may be bent":
  - power paths first, with widths sized for the load;
  - each block routed internally before blocks are joined;
  - then analog and sensitive inputs, crystals and their capacitors;
  - buses, with length matching and impedance where the speed needs it;
  - one direction per layer;
  - power on inner layers;
  - no isolated copper islands;
  - few vias, to the manufacturer's specification;
  - return paths checked.

  Say plainly: the router uses only the two outer layers today, so "power on inner layers" means planes. Inner-layer tracks are a known limit, reported as a bent guideline. Ask for the user's own routing habits too.
- **Human decides:** whether to accept each bend.
- **Done:** DRC 0 violations and 0 unconnected, or each waived; `board_check.py` passed; artefact scan clean or listed; known improvements listed. Never "done" with a list of improvements in hand.
- **Brief:** build worker; procedure: worker reference board.md (Routing; Planes and vias; Router; DRC and layout checks; Artefacts; Improvements before done). For a board the engineer placed by hand, add worker reference adapting.md (Routing a hand-placed board). Remind the worker: two fill engines, so re-pour with the command-line tool; a failed plane drop fills the board with ground tracks; report progress on long runs and set a budget.

Changes after the 3D sign-off are expected; the router makes re-routing fast.

---

## ST11 Board review

- **Entry:** ST10 done, or anything changed after a board review.
- **Ask:** which review modes. Recommend the blind board review whenever the board has carried layout rows: it is the only check for datasheet instructions the passes missed. The user may decline; if so, say once what is lost and record the decision.
- **Human decides:** each finding; whether to run the blind board review.
- **Checkpoint: the board checkpoint.**
  - DRC clean or waived;
  - every constraint enforced, or bent with a decision;
  - every carried layout row has a board result;
  - every review-enforced constraint has a per-row verdict in the board review report (`table_check.py constraints`), with measurements or coordinates from the board file as evidence;
  - every check done by hand, listed under "Not verified";
  - extraction misses from the blind review logged and turned into rows;
  - findings triaged.
- **Done:** review reports; checklist results.
- **Brief:** the board gets its own reviewer. Review worker with the full board checklist and the switched-on packs, the datasheet layout pages, the rule file, DRC output, constraints and renders; procedure: worker reference review.md (Board review). Pin item one at board level: pads against the package drawing of the exact part ordered. Blind board review per `briefs.md`: it gets the datasheets, not the compliance table or the constraints.

---

## ST12 Fabrication files

- **Entry:** the board checkpoint.
- **Ask:** `questions.md` Order: assembled by the board house or hand-built (asked earlier where it changes the design; confirmed here); the offered checks; order options; whether to tidy the designators first.
- **Human decides:** order or not; any waiver.
- **Checkpoint: parts check 2** (a check before ordering, not a freeze). Report:
  - stock and price checked today;
  - the capability table restated with its sources, so the user can see it matches the service ordered;
  - parts with no checked pin table, by designator;
  - constraints with no board result;
  - open waivers;
  - if the shape is provisional: "ordering now risks paying twice";
  - the manufacturer checks manufacturability only. Pin assignment and circuit correctness are ours.
- **Done:** order files in `hardware/<manufacturer>/`; BOM and placement files in the assembler's format and a neutral set; not-fitted and variant lists; consistency check; hand-assembly list if hand-built; files repeatable (built twice, same bytes); the designators tidied first, if the user asked; a release record (schematic PDF, assembly drawing, every FR- re-checked with its evidence, open waivers, what is not verified, the commit); an offer to tag the ordered commit.
- **Brief:** build worker; procedure: worker reference fabrication.md. An unclean check at export is a violation; the export goes ahead only with a recorded waiver, offered in the same message so one reply records it. A script-owned board saved from the editor shows up in the ownership check; put the three choices to the user.

Stock problems found here can send work back into the ST1 to ST6 loop. That is normal.

---

## ST13 Repository and publication (optional)

- **Entry:** a commit (per the commit setting or the user's request), or a request to publish.
- **Ask:** `questions.md` Repository: licence (the user's choice); README images and text; public or private; before any remote is made, the repository name, the user's naming convention and the organisation or account it goes under; whether saved third-party PDFs are committed. Before publishing, check the licence of each simulation model in `sim/models/`; a model whose licence does not allow it is left out, with a note of where to get it.
- **Human decides:** everything that is published.
- **Checkpoint:** the confidentiality scan, shown only when it finds something.
- **Done:** README; licence files; release items checked; a fresh-context "clone, build, compare" review offered.
- **Brief:** build worker; procedure: worker reference repository.md. Review worker for the cold read. Never change the visibility of any other repository.

---

## Later stages (reserved)

Bring-up, firmware and test are not in this version. `design/firmware.md` holds the firmware instructions (what firmware must do: pins, drive strengths, start-up sequence, fuses), and `design/test-sweep.md` lists what must be tested. The skills write no firmware and run no test. Firmware pin definitions generated from `pins.csv` are reserved for the firmware stage.
