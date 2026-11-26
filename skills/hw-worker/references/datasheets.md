# Datasheets

How to get, read and record a part's datasheet. Used at the parts stage (ST3) for every part, before it enters the schematic, and whenever a part changes. The user may choose at setup to read as parts are placed instead (Reading as parts are placed). Read all of this file before a datasheet pass.

The aim: every instruction and limit in the datasheet ends up as a tracked row with a result, and the layout and grounding instructions are carried to the board as constraints before any placement. A list in a report is not enough. The rules behind this are WR-01, WR-05, WR-17, WR-19, WR-20, WR-21 and WR-22 in the skill file.

## Contents

Get; PDF route; Page renders; Read in full; Section inventory; Extraction traps; Figures and graphs; Delegated documents; Errata; Reference designs; Compliance rows; What one row holds; Citing a place; Errors and inconsistencies; Perspective passes; Silence sweep; Merging passes; End-of-pass checks; Reading as parts are placed; Pin tables; Pin check; Vendor pin data; Configurator export.

## Get

Getting the files is one step, done by a fetch brief (or by a combined pass that works alone) before any perspective pass starts. Passes that run at the same time read the saved files and never fetch the main datasheet themselves, so no two workers write the same file.

1. Find the maker's own datasheet for the exact MPN, the current revision. Try the sources in this order, each once: the maker's site; a copy hosted by a distributor, the user's suppliers first; then another legitimate public host of the same document. Only when all three fail does the document become data needed from the user (WR-03). The rules for a refusal and for a copy are below the list.
2. Save it as `datasheets/<MPN>.pdf`, with any character a file name cannot hold replaced by "-". Designators shift while the schematic grows, so file names do not use them. Several parts sharing one datasheet share one file, named after the first MPN; list the others in the README.
3. Make a text extract beside it, `datasheets/<MPN>.txt` (see PDF route).
4. Add a line to `datasheets/README.md`: file, part, MPN, maker, document number and revision of the saved copy, date of the revision, whether a newer revision is known, where the copy came from (maker, distributor or other host), URL, date fetched, and the designators once the schematic gives them.
5. Record the revision in `design/parts.csv` (`datasheet`, `datasheet_revision`).
6. Fetch the errata (see Errata) and every delegated document (see Delegated documents) the same way.
7. Render every page of each saved PDF once (Page renders).
8. Write the section inventory (below), so the passes can claim sections from it.
9. Note any simulation model the maker publishes for the part (its name, format and URL) in `datasheets/README.md` and in the report. Do not fetch a model that needs a login or a licence; the refusal rule below serves models too. How models are fetched, recorded and kept is in `references/simulation.md`.

Send only the generic part number to search engines and supplier sites (WR-11).

**A refusal is never worked round.** Another legitimate host of the same public document is allowed. Defeating a login, a licence wall or a block is not, and a request is never disguised. A rate limit is not a refusal: wait, then try again. The brief names the order of fetch tools to use. List every refused fetch in the report under "Data needed from the user": the URL, the date and the sources tried. Keep no list of which sites refuse; that changes, so each run tries afresh.

**A copy not from the maker.** Check its identity (MPN, document number) and its revision. Check it is complete and unaltered: reject a copy with an added cover page or with pages missing. Compare its values with the maker's copy before they enter a design row. If the maker's copy cannot be had, mark the README line and each row from it "not confirmed latest".

**Every figure comes from a saved file.** A figure read from a web page that was not saved cannot be read again. Save the source in `datasheets/` with a README line, or mark the figure "not re-checkable" where it is used. `table_check.py datasheets` checks that every file in `datasheets/` has a README line and a text extract. A maker's product page, read for the lifecycle of a part, is saved as text under the name `datasheets/<MPN>_product-page.txt`; `table_check.py parts` compares it with `design/parts.csv` (`references/requirements-parts.md`, Parts check).

**Documents that need care.** A document that may not be copied (a standard's preview, a file whose copyright notice forbids it) is committed or kept out as the `Third-party PDFs committed:` line of `design/status.md` and `references/repository.md` say. If it is kept out, its README line still records the URL, revision and date, and says "not committed". For a very large PDF in several languages, save the whole file, extract and render only the pages in the working language, and record which pages in the README line.

## PDF route

Use the first that works, and record which one in `design/status.md` at setup:

1. Your tool's own PDF reading and page viewing.
2. On macOS only, the skill's two scripts: `pdftext.swift` (text extract) and `pdfpage.swift` (render pages to images). Run them with `swift <script> <in.pdf> <out.txt>`, `swift <script> <in.pdf> <page> <out.png> [scale]` for one page, and `swift <script> <in.pdf> all <prefix> [scale]` for every page. `pdftext.swift` prints the pages that have no text layer (scanned pages, drawings saved as images): their text is only in the renders.
3. Elsewhere, an install the user approves, at an exact version at least 30 days old (`references/tooling.md`, Install policy).

Count a PDF's pages with the PDF tool or script, not with a system file command. A graphics error line in a script's output does not mean the text is incomplete.

You must be able to look at rendered pages. If you cannot, say so in the report's first lines, leave every figure and graph row open, and tell the coordinator the figures were not read. Never write a figure row from the text extract alone.

## Page renders

The fetch brief renders every page of each saved PDF once, into `design/renders/<datasheet>_p<page>.png`, at a scale that keeps the smallest figure text legible (the script's default does; check one drawing page and render again larger if it is not). It lists in its report, and in `datasheets/README.md`, the pages with no text layer, so every pass reads those from the renders. `<datasheet>` is the file name in `datasheets/` without `.pdf`, so parts that share one datasheet share its renders. `<page>` is the PDF page number, counted from 1 at the first page of the file, not the number printed on the page. With the macOS script: `swift pdfpage.swift datasheets/<datasheet>.pdf all design/renders/<datasheet>`. It leaves pages already rendered as they are, so a second run writes nothing.

- Passes read these renders and never write into `design/renders/`, so passes that run at the same time cannot collide.
- A pass that needs a larger view of a small figure or table renders that page again into `design/passes/zoom/<datasheet>_p<page>_<perspective>.png`, at the scale it needs. It never touches the shared renders. The merge deletes `design/passes/zoom/`.
- A delegated document a pass fetches itself is rendered by that pass, under its own file name, and listed in its report.
- After the merge, the pages behind figure and graph rows are kept, so a reviewer can check the reading. The merge deletes the rest; they can be made again from the saved PDF. `table_check.py compliance` lists the renders no row cites.

## Read in full

Read every page, in order, including:

- the front page summary and the feature list (limits hide here);
- pin configuration and functions;
- absolute maximum ratings, ESD ratings, recommended operating conditions, thermal information;
- electrical characteristics and timing, with their test conditions and footnotes;
- typical characteristics (graphs);
- detailed description, functional modes, configuration, programming;
- application and implementation, including the design procedure and the typical application;
- power supply recommendations;
- layout guidelines and layout example;
- device and documentation support (this is where delegated documents are named);
- mechanical, packaging and orderable information: package drawing, land pattern, stencil, tape and reel, moisture level and reflow notes;
- revision history (it tells you what changed and why).

Footnotes and table notes are part of the text. "Note" boxes are part of the text.

Reading means looking at each page. Searching the text extract for keywords is a way to check you missed nothing afterwards, not a way to read.

## Section inventory

Before writing any row, list every section and subsection heading of the datasheet in `design/sections.csv`, one row each, with its pages and category. Use the datasheet's own numbering and titles. Include sections with no instructions in them. A parent heading whose text all sits in its subsections is still a row: the pass that claims its subsections claims it too, with the note "heading only". The fetch brief writes the inventory once. Passes that run at the same time record their claims in their staging files (Merging passes), not in `design/sections.csv`: each pass first copies every row of its datasheet's inventory from `design/sections.csv` into its sections staging file, then fills its own claims and row counts. `table_check.py sections --staged` compares the file with the inventory: an empty file, or a section left out or added, fails; sections the pass did not claim are listed.

For a datasheet too large for one worker to read well, the brief may split it by this inventory: each pass reads the inventory and every section it claims, in full, from the renders. The merge then flags any section no pass claimed.

Categories: pins, absolute-maximum, operating, electrical, timing, thermal, functional, configuration, application, typical-application, power-supply, layout, grounding, package, assembly, errata, revision-history, ordering, other.

As you work, fill `claimed_by` with your perspective for each section you read for rows, and the row counts in `rows_logical`, `rows_electrical`, `rows_physical`.

A section in category layout, grounding, application, thermal or typical-application with zero rows needs a note: "no instructions here (<brief ID>, <date>)", or the reason. `table_check.py sections` flags any such section without a note, and any section no perspective claimed. A section still unclaimed after all passes is resolved by the merge brief (Merging passes), not by a pass.

## Extraction traps

Text extracts lose structure. Known cases:

- **Numbered lists collapse.** The item numbers can come out as a run of bare digits, with the items after them as running prose, so a keyword search finds only some of them. Always read layout, application and protection-placement pages from their renders, count the list items on the image, and check you have at least one row per item.
- **Tables flatten.** Columns run together; minimum, typical and maximum swap; units drift to the next row. Read limits from the rendered table when the extract is not clearly aligned.
- **Footnotes detach** from the value they qualify. Find each footnote marker on the rendered page.
- **Figures vanish.** Layout examples, typical application schematics, package drawings and graphs carry instructions the text does not repeat.
- **Headers and footers** interrupt sentences across page breaks.
- **Superscripts and subscripts** (for example a temperature coefficient, a unit power) become plain digits.
- **Unit prefixes change.** A micro sign can come out as an "m" or vanish, so a value reads a thousand times too high.
- **Overbars drop.** The bar that marks an active-low pin is lost, so the pin reads as active-high.

Any unit, pin polarity or limit that a design value rests on is read from the rendered page, never from the extract alone.

When an extract and the rendered page disagree, the rendered page wins. Note the disagreement in the row's evidence if it matters.

## Figures and graphs

Every figure in your scope is read from its page render. That includes the typical application schematic, layout example, package drawing, land pattern, thermal pad and via pattern, and any graph that a design value depends on.

- **Figure rows** (kind `figure`): one row per instruction the figure shows that the text does not state, written in words (an invented example of the wording, not a rule: "<the part> sits <where the figure shows it>, <connected as the figure shows>"). Fill `figure` (Citing a place) and `page`.
- **Renders behind the rows.** The row's `page` names the render the reading came from. `table_check.py compliance` checks that `design/renders/<datasheet>_p<page>.png` exists for every figure and graph row, so the reading can be checked later.
- **Graph rows** (kind `graph`): when a design value depends on a graph (capacitance under DC bias, current limit over temperature, derating, efficiency, safe operating area, thermal derating), read the value from the rendered graph and record it with the figure number, the axis values you read, and how precisely you could read them. Say it was read from a graph.
- **Graphs before a design exists.** At the parts stage there is no operating point yet. Put the readings in `evidence` (for example the curve at the conditions the requirements give, or at a few points across the range), leave `design_value` and `margin` empty, and keep the result open. The schematic stage fills them from its worst-case calculation.
- A value that depends on a graph you did not read is "not verified" in the report (the earlier board never read its derating, pulse and DC-bias graphs).

`table_check.py compliance` flags figure and graph rows with no figure number.

## Delegated documents

Datasheets often send you elsewhere: "see the evaluation module user's guide", "refer to the hardware design guidelines, section ...", "see application note ... for layout". Each is part of the datasheet for your purposes (WR-17).

Two kinds of mention:

- **Delegated:** the datasheet hands part of its own job to the document ("for layout, follow ...", "see ... for the recommended land pattern"), or a row depends on what it says. Fetch it, inventory it and write its rows like the datasheet's own.
- **Referenced:** a general pointer, such as a list of related documents, a packaging standard or a family overview. List it once in `datasheets/README.md` as "referenced, not fetched". It becomes delegated the moment a row or a decision depends on it.

When unsure, treat it as delegated.

1. List every delegated document in the report and in `datasheets/README.md`.
2. Fetch each one and save it with the part's MPN, for example `datasheets/<MPN>_design-guide.pdf`. A pass that finds a delegated document the fetch brief did not save may fetch and render it under that name; it lists it in its report, and the merge adds its README line. Read the parts that apply to this part and this board, with the same inventory and rows (use the document name in the `datasheet` column).
3. If one cannot be found or fetched, do not close the matter as "listed as missing". Report it as a numbered decision: what the document covers, what you looked for and where, and the options (the user supplies it; use a named alternative from the same maker; proceed with the risk recorded).

An earlier board's radio module datasheet delegated antenna placement to a design guide that was never fetched. The keep-out was then the worker's own choice, and the module's certification depended on it.

## Errata

1. Look for the maker's errata or silicon errata sheet, and the part's revision or date-code marking.
2. Each erratum that touches a pin, peripheral, mode or limit the design uses becomes a row of kind `errata`, with its workaround quoted.
3. Record in `design/parts.csv` `errata` the document and revision, or "none published (<date> checked)".
4. At each parts check, look for a newer datasheet or errata revision.

## Reference designs

At the parts stage no schematic exists yet. Write down the datasheet's typical application and, where the maker publishes one, the evaluation board's schematic and BOM, as a list of their parts and values (rows of kind `typical-application`). At the schematic stage, the design is compared with that list and the comparison is closed there.

- Fetch the evaluation board guide as a delegated document.
- At the schematic stage, each difference (a value, a missing optional part, a different topology, a part the evaluation board fits that the typical application omits) gets the reason for it, or "reason needed" if none is known yet.
- Layout differences are recorded now as physical rows where the figures show them, and compared again with the finished board at the board review.
- Optional parts the datasheet shows (snubbers, filters, series resistors) are rows too, so the decision to leave a footprint is a recorded one.
- Read the application text for protection parts it asks for outside the typical circuit (a clamp, a series resistor, a fuse). Each is a row. The part is placed, or its absence is a recorded decision.

## Compliance rows

One row per instruction and per limit, in `design/compliance.csv` (columns and allowed values in `references/project-files.md`).

What counts as an instruction:

- **must:** "must", "shall", "required", "is mandatory", "do not", "never", and plain imperatives with no softening ("place", "connect", "tie", "keep", "route", "use", "avoid", "minimise").
- **should:** "should", "it is good practice".
- **recommend:** "recommended", "preferably", "if possible", "consider", "optional".
- **limit:** every absolute maximum, every recommended operating range, every rated value the design must stay inside (voltage, current, power, temperature, ESD, capacitance on a node, frequency, duty cycle, timing).
- **typical-only:** a value the design depends on that the datasheet gives only as typical, with no minimum or maximum. It is not a guaranteed limit. Say so in the row; the design either keeps a margin from it, with the reason, or the dependence is raised as a decision.
- **calculation:** an equation, a design procedure step or a check the datasheet or the pack asks for, such as a component value from a formula or a worst-case current against a rated limit. One row per calculation. It stays open until a script in `design/calcs/` runs it at the schematic stage; `evidence` then names the script and its result.
- **data:** package and assembly data the design uses but that instructs nothing: pad sizes, pitch, height, moisture level, peak reflow, tape width. Category `package` or `assembly`. The pass leaves it open; package rows close when the footprint and 3D model are checked against the drawing (by the board checkpoint), assembly rows at the order files.

All three kinds of instruction are tracked. "Recommend" is not optional to record; it is the design that may choose not to follow it, and then it needs a recorded decision.

For each row:

- `text`: the datasheet's words, quoted exactly, slips and typos included. Shorten only with "..." and never change meaning. Your reading of a garbled sentence goes after the quote in [brackets], marked as a reading: "[reading: ...]".
- `section`, `page`, `figure`: where it is. For a collapsed list, give the item number as counted on the rendered page. A row not tied to one section (the whole document, the ordering page) uses `section` "general".
- For a limit from a table: which column it is printed in (MIN, TYP or MAX), in `evidence`. A one-sided limit printed in an unexpected column (a maximum under MIN) is a datasheet error (Errors and inconsistencies), not something to settle quietly.
- `mpn`, `revision`: the exact part and document revision the row came from (WR-18). `designator` stays empty until the schematic gives the part one.
- `category`: pin, absolute-maximum, operating, electrical, timing, thermal, protection, decoupling, external-component, configuration, power-up, layout, grounding, package, assembly, errata, typical-application, other. ESD, surge and reverse-polarity ratings are protection. Placement, routing, keep-out and via rules are layout.
- `perspective`: logical, electrical or physical; more than one after a merge.
- `design_value` and `margin`: for limits and values, the design's worst-case value and the margin, from a calculation in `design/calcs/` where one exists.
- `schematic_result`: open, met, not met, does not apply, carried. A layout or grounding row is "carried" before a board exists; it cannot be "met" from the schematic.
- `board_result`: open, met, not met, does not apply. Filled at the board stages.
- `decision`: the DC- ID that closes a "not met" or "does not apply", or "proposed" while the user has not decided.
- `carried_to`: the CN- IDs the row became (filled at the board rules stage).
- `evidence`: the check and its output, or the review and its verdict.
- `found_by`: pass, review or blind review.

**The hard rows (WR-21).** A row in category layout, grounding, protection or absolute-maximum is never set to "does not apply" or "not met" by a worker. Propose it: write "proposed" in `decision`, give the quote and your reason in the report as a numbered decision, and carry on. `table_check.py compliance` flags any hard row closed without a DC- ID. When only one clause of a hard row seems not to apply (a condition this design may not meet, one of several pins), do not split the row or close part of it. Keep the row whole and open, write "proposed", and put that clause to the user with your reason.

**Pack items that do not fit.** A pack item that does not fit this part's topology (a synchronous-rectifier item on a part with an external diode) gets "does not apply" with the reason in the pass report, and no row.

**Habits and silence (WR-20).** If a user habit in `design/status.md` disagrees with a row, the row stands and the difference is a numbered decision quoting both. If the datasheet says nothing about an area a pack names as sensitive (switching loop, grounding, feedback, clock, protection), fetch the evaluation board guide and the maker's layout application note. If they are silent too, add a row:

- `kind` recommend; `category` the area's own (layout, grounding, protection, and so on);
- `text` "no guidance found in <documents checked>: <the area>";
- `evidence`: the documents and sections read, and the words searched for (`table_check.py compliance` fails the row without it);
- `schematic_result` "carried" when the area is layout or grounding, so the board stage still sees it; otherwise open;
- a numbered question to the user in the report.

## What one row holds

- **One instruction per row.** A sentence with two instructions ("place it close and route it on one layer") is two rows, each quoting its own words. A sentence that is one instruction stays one row, however long.
- **A sentence that spans perspectives** (a connection and a value, or a value and where to place it) is quoted whole by each pass that reads it, and each pass writes only its own part: the logical pass the connection, the electrical pass the value, the physical pass the placement. The merge joins rows that say the same thing into one row with both tags, and keeps both when they mean different things.
- **An equation is one calculation row**, with its number, its terms and the limit it is checked against. A design procedure of several numbered steps is one row per step that gives a value or a check.
- **A list item is a row** even when it repeats something said elsewhere; the merge joins true duplicates.
- **Informative notes** that instruct nothing (a description, a reason, a reminder of a law of physics) get no row. Count them in the section's note, with one line why: for example "3 informative notes, no instruction". A note that tells the reader to do something is an instruction, however it is labelled.
- **A sentence about behaviour** (what a pin does in a mode, what happens at a threshold) gets its own row when it bounds a design choice. "Restates the pin table" is not a reason to drop a sentence that adds a condition.
- **Cross-references.** Check that each "see Figure N" or "see section X" lands on matching content. Redo each step of a worked example with the values printed at that step. A mismatch is a datasheet error (Errors and inconsistencies).

## Citing a place

- `page` is always the PDF page number, the one the page render carries, not the number printed on the page.
- `section` uses the datasheet's own numbering. For a list item, add "item <n>" as counted on the render.
- A numbered figure: its number in `figure`. A figure with no number: its caption in `figure`, or "unnumbered, p<n>, <position on the page>".
- A table note: the table number and "note <n>" in `section`.
- A package or land-pattern drawing note: the drawing number (or the drawing's title when it has none) and "note <n>" in `section`, the page in `page`.
- A delegated document: its own file name in `datasheet` and its own section and page.

## Errors and inconsistencies

People write datasheets, and every maker's datasheets have mistakes and places that disagree with each other. Expect them, often (WR-22).

1. **Check the log first.** Look in `design/decisions.md` for the same MPN and datasheet revision. If the user has decided this point already, follow that decision and cite it. Do not ask again.
2. **Quote both places**, each with its section, page and figure or table, in the row's `evidence` and in the report.
3. **Never quietly take the convenient reading.** Not the one that makes the design easier, nor the one you read first.
4. **Decide whether it is material.** It is material if either reading could change a part value, a rating margin, a footprint, the layout or the cost.
   - **Material:** put it to the user as a numbered decision. Give both readings, which one is the cautious one, and your recommendation. Design to the cautious reading meanwhile, and keep the row open. The coordinator logs the user's answer with the MPN and revision, so the question is not asked again when the part is used again.
   - **Not material:** log it in `design/findings.csv` (category risk, the two places quoted) and carry on.
5. **Look for a newer revision or an erratum** that settles it, and say what you found.

Cases seen in practice:

- **Two package drawings that disagree**, for example the drawing and the land pattern give different pad sizes, or two pages give different pin 1 marks. A footprint is always material. Say which reading is the cautious one and use it meanwhile, and recommend the drawing that matches the maker's own land pattern or evaluation board where one does. The footprint is not final until the user decides.
- **An equation or rule that the datasheet's own example breaks**, for example a formula gives one value and the typical application fits another. Quote both, work the equation with the example's numbers in a calculation row, and say which reading leaves more margin.

This is not WR-20. There, a user habit disagrees with the datasheet, and the datasheet wins. Here, the datasheet disagrees with itself, and the user decides.

## Perspective passes

Each pass is its own brief. For a complex or sensitive part (power, microcontroller, radio, interface IC, or any part in a switched-on pack), three workers do one pass each. Simple parts (passives, connectors, jellybean discretes) get one combined pass with the three headings below, and one worker may take several. The setting is in `design/status.md`.

Every pass reads the whole datasheet (or, for a datasheet split by its inventory, the inventory and every section it claims), then writes rows only for its scope. Use the pack for the part's category, from the project's copy `design/checklists/packs.md` (it holds the items the user added), to know which areas are sensitive; the datasheet still gives every rule.

Passes write only their staging files (Merging passes). Where a pass "feeds" a main table below, it puts the data in its staged rows and its report, and the merge writes the main table: `design/pins.csv`, `design/parts.csv` (`msl`, `peak_reflow`, package) and the rest. A combined pass that works alone, with no merge after it, writes the main tables itself.

**Logical pass.** What the part does. Pin functions and alternates, and which the design uses. Modes and how they are entered. Configuration, strapping and boot pins. Interfaces and their exact variants and speeds. Start-up, reset, sleep, wake and fault behaviour: the state of every pin during reset and boot, and every control input's required state. The typical application as a connection list. Feeds: `design/pins.csv` functions and power-up columns, the logical design, the firmware instructions (`design/firmware.md`).

**Electrical pass.** Absolute maximum ratings, in every state, not only steady state. Recommended operating conditions. Thresholds, levels, input impedance and leakage. Timing. Supply current in each mode, power dissipation, thermal resistance and junction limits. Protection and ESD ratings. External component values, their tolerances and the design equations. Graphs that values depend on, read from the renders. Feeds: rows with design values and margins, worst-case scripts in `design/calcs/`, typical-application differences.

**Physical pass.** Package and footprint: land pattern, pin 1, top or bottom view, exposed pad, pad numbering. Layout and grounding guidance, every item. Placement order and distances. Thermal pad, thermal vias, copper area. Keep-outs. Assembly: moisture level, peak reflow, via treatment in pads, stencil and paste notes. Layout example figures, read from the renders. The delegated layout documents (evaluation board layout, layout application notes, module placement guides). Feeds: layout rows carried to constraints at the board rules stage, footprint choice, `design/parts.csv` `msl` and `peak_reflow`.

The physical pass has one job above all: no layout or grounding instruction in this datasheet or its delegated documents is left without a row. Name the hot loop, the ground scheme and every sensitive node the datasheet describes, in its own words.

## Silence sweep

At the end of every pass, go through the areas of your perspective below. For each, cite the row that covers it, or write a "no guidance found" row (Compliance rows, Habits and silence). The list names areas only; the datasheet gives every value. Readers noticed a datasheet's silence mostly where a checklist item pointed at the area, so the sweep is what makes silence visible.

- **Logical:** default state of floating inputs, and the drive of outputs, in every mode (reset, boot, sleep, fault); for every output that can do harm, what it does when the processor hangs, resets or leaves its pins floating: the driver's truth table with floating inputs, the pin states in reset, and whether each kind of reset stops a running timer output (a watchdog reset may not); source or storage types the part does not cover (a cell chemistry, a supply kind); whether the maker publishes a simulation model.
- **Electrical:** current rating of internal switches, and inrush; loading and leakage of setting networks (dividers, timing resistors), where a worst-case threshold counts the leakage and bias currents or its result lists the terms left out, and the rail budget is counted again after such a change; voltage rating, derating and series resistance of the external parts the datasheet specifies; input clamp, reverse connection and ESD.
- **Physical:** soldering profile and inspection (exposed pads, hidden joints); coating, cleaning and humidity; probing of high-impedance nodes (where a probe can touch, and what it loads).

A combined pass sweeps all three lists. Put the sweep in the report as one line per area: the row ID, or the new "no guidance found" row.

**Independence.** You are not given the other passes' rows. Do not read them until your own rows are written. Overlap is expected (an exposed pad is physical and thermal); write the row from your angle and the merge keeps both tags.

## Merging passes

When passes run at the same time, each writes to its own staging files so they do not overwrite each other: `design/passes/<MPN>_<perspective>.csv` for rows (same columns as `design/compliance.csv`, with `id` left as `<perspective>-<n>`), `design/passes/<MPN>_<perspective>_sections.csv` for section claims, and `design/passes/<MPN>_<perspective>_findings.csv` for findings and side remarks (same columns as `design/findings.csv`, with `id` left as `<perspective>-F<n>`). The brief may name other paths. A pass writes nothing else under `design/`: no main table, no render. Workers that run at the same time never append to a shared file; one writer, the merge, does. Each pass checks its own staging files with `table_check.py compliance sections --staged ...` (End-of-pass checks); after the merge, the same checks run on the main tables without `--staged`.

A merge is its own brief, given to one worker after all passes have reported. No pass merges on its own, because a pass cannot know it is the last. The merge worker:

1. Copy every staged row into `design/compliance.csv` with the next free DS- IDs. IDs are never reused.
2. Two rows that quote the same text become one row with both perspective tags. Never drop a row because another pass "covered it" in different words; keep both if the wording differs in meaning.
3. Combine the section claims into `design/sections.csv`: `claimed_by` lists every perspective that claimed the section; the row counts are summed per perspective.
4. Copy every staged finding into `design/findings.csv` with the next free FD- IDs. A row or finding that names a provisional ID gets the new one. List the provisional IDs beside the new ones in the report.
5. Run `table_check.py sections`, `table_check.py compliance` and `table_check.py findings`. Resolve every flag. A section no pass claimed is read in full, from its renders, and claimed: it gets rows, or its "no instructions here" note. A layout, grounding, application or typical-application section gets that note only after you have read it yourself; if you cannot tell, give it a row or raise it as a decision. List in the report every section you claimed this way.
6. Where two passes read the same place differently, or a pass reported a datasheet error, handle it as in Errors and inconsistencies.
7. Add a `datasheets/README.md` line for any delegated document a pass fetched.
8. Keep the renders behind figure and graph rows and delete the others (`table_check.py compliance` lists them).
9. Write the main tables the passes fed: `design/pins.csv` rows from the pass reports and staged rows (unconfirmed until the pin check), and `design/parts.csv` package and assembly fields.
10. Delete the staging files and `design/passes/zoom/` only after both checks pass, and say so in the report.

## End-of-pass checks

Before you report a pass done:

1. Every section in your scope has your claim (in `design/sections.csv`, or your staging file, which holds the whole inventory), and every layout, grounding, application, thermal and typical-application section you claimed has rows or a note.
2. For every numbered or bulleted list in your scope, the item count on the rendered page equals the rows you took from it (or the difference is explained).
3. Every figure in your scope was read from its render, and each figure or graph row's `page` names a render in `design/renders/`; list the figure numbers and pages in the report.
4. Every delegated document was fetched, or raised as a decision.
5. Every hard row you think does not apply is "proposed", not closed.
6. `table_check.py sections` and `table_check.py compliance` ran; give their output. A pass that writes staging files checks them, not the main tables: `table_check.py compliance sections findings --project <project root> --staged design/passes/<MPN>_<perspective>.csv --staged design/passes/<MPN>_<perspective>_sections.csv --staged design/passes/<MPN>_<perspective>_findings.csv`. Relative `--staged` paths are read from the working folder, else from the project root; with no `--project`, the project is found from the first staged file. It checks the ids (`<perspective>-<n>` and `<perspective>-F<n>`), the perspective tags, your own claims, and that your sections file holds the whole inventory; sections your files do not claim are listed, not failed.
7. The silence sweep is done (Silence sweep), one line per area in the report.
8. The report lists rows added by section, sections with no rows and why, informative notes counted, datasheet errors found, rows needing a user decision, and pins needing human confirmation.

## Reading as parts are placed

The up-front pass chain above is the default. The user may choose the short form at setup: the `datasheet reading` line of `design/status.md` then says "as parts are placed". The coordinator offers it with its risk said: an instruction that sits outside the sections read can be missed. Never choose it yourself.

In the short form:

1. Get still applies: the file is saved, extracted, rendered and listed before the part is placed.
2. When a part is placed, read the sections its placement rests on, from the renders: pins, absolute maximum ratings, operating conditions, the typical application, and any section a value on the sheet comes from.
3. Every value and every connection drawn cites its place: datasheet, section and page (Citing a place).
4. The pin rows are still written as the part is placed (Pin tables), so `sch_check.py pins` and the pin check run as in the default.
5. The report names the sections read for each part, so what was not read is visible, and repeats the risk in one line.

## Pin tables

Every part with pins that can be wrong gets rows in `design/pins.csv` (written by the merge from the passes' data, or by a combined pass that works alone): ICs, modules, connectors, and polarised parts (diodes, LEDs, transistors, electrolytic and tantalum capacitors). One row per pin, including exposed pads and mechanical pins.

- `functions`: every function the pin can take, from the authority, not only the one used. `used_function`: the one the design uses.
- `supply`, `levels`, `abs_max`, `current_limit`: from the electrical pass.
- Power-up columns, from the logical pass: `reset_state` (the pin's state while the controlling microcontroller is in reset), `boot_activity` (anything the pin does during boot: toggling, a strapping read, a UART print), `control_input` (yes if this pin controls something: enable, reset, chip select, standby, mode, strap, gate drive), `required_in_reset` (the state it must have before firmware runs), `given_by` (the part that gives that state: a pull, a tie, a driver), `sleep_state`, `fault_state`.
- `source`: configurator export, vendor data or datasheet table, with `source_page`.
- `confirmed`: "yes" only after a human or a second worker checked the row against the source (Pin check, below). Never confirm your own transcription.

The KiCad symbol is not an authority. It is one of the things checked against the table. `sch_check.py pins` compares the table with the symbol pins, the footprint pads and the netlist, checks each used function is supported by that pin, and lists hidden and power pins. `sch_check.py powerup` checks every control input has a pull, tie or driver that gives its required state while the microcontroller is in reset, and names the part that gives it. A floating enable on a converter that a microcontroller controls is the classic failure: the converter can switch on or off before firmware runs.

Library symbols for two-pin protection parts differ in which pin is which. Check the pin numbers of each against its datasheet and its footprint.

Pin numbering at board level (pads against the package drawing of the exact part ordered) is checked in the board review.

## Pin check

A pin-check brief goes to a different worker from the one that wrote the pin table, for every microcontroller, module and connector, and any part the user names.

1. For each row of the part in `design/pins.csv`, open the source named in `source` and `source_page`: the configurator export, the vendor data file, or the datasheet pin table, rendered (never the text extract alone).
2. Check the pin number, name, `functions`, `used_function` and the power-up columns against it.
3. Set `confirmed` to "yes" only for rows you checked yourself and found right. A row that is wrong is a finding, with the source quoted; leave it unconfirmed.
4. List every row you could not confirm (source unreadable, ambiguous, missing), with the source page, under "Data needed from the user". The coordinator puts them to the user as one batch at the schematic checkpoint.

This never holds up other work: open rows are listed, and the engineer decides.

## Vendor pin data

For microcontrollers, prefer the maker's machine-readable pin data over a PDF table where it exists. Version one has one importer: `sch_check.py pins --import <vendor>`; its help lists the vendors it reads. For every other family, transcribe the datasheet's pin table, or a configurator export, into `design/pins.csv`; the pin check (above) or a human confirms it.

Record the data source and its version in `source`. If you find machine-readable pin data the importer does not read, report it as a side remark with its URL and licence.

## Configurator export

The highest-trust source for a microcontroller's pin table is the engineer's own assignment in the maker's configuration tool: it shows that each pin supports the function assigned and that peripherals do not clash.

If the engineer chose this route (asked at the schematic stage):

1. Ask the engineer for the exported pin report or project file, with the tool name and version.
2. Save it in `datasheets/` next to the part's datasheet.
3. Transcribe it into `design/pins.csv` with `source` "configurator export <file>, <tool version>". Version one has no parser; transcription is by hand.
4. A human confirms the rows (`confirmed` = yes).
5. If the schematic and the export disagree, that is a finding. The export wins unless the engineer decides otherwise.

Firmware pin definitions generated from the table are reserved for the firmware stage. Record them in the firmware instructions (`design/firmware.md`) only as a pointer to `design/pins.csv`.
