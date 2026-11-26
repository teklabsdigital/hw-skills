# Review

Procedures for the schematic review (ST6), the basics review of each sheet, the board review (ST11), blind reviews of either, and the thermal review that is part of both. The constraint-sufficiency review at the board rules stage is in `references/board.md`.

A good review finds what would stop the board working to specification or make it fail in the field. It is not a style review.

## Contents

Inputs; Order of work; Pin item one; Schematic review; Basics review; Board review; Blind review; Thermal; Ranking; Side remarks; Re-review; Growing checklists; When to stop.

## Inputs

| Review | You get |
|---|---|
| Schematic | schematic, exported netlist, BOM, `design/parts.csv`, `design/pins.csv`, `design/compliance.csv`, `design/sections.csv`, `design/net-review.csv`, `design/calcs/`, datasheets, requirements, decisions, the checklists and switched-on packs |
| Board | board file, rule file, project file, DRC output, `design/constraints.csv`, the layout and grounding rows of `design/compliance.csv`, the datasheet layout, grounding and application pages, renders, the board checklist and switched-on packs |
| Blind schematic | design files, netlist, BOM, datasheets, requirements. Nothing of the designer's reasoning |
| Blind board | board, rule file, DRC output, renders, datasheets, requirements. Not `design/compliance.csv`, not `design/constraints.csv` |

The project's copies of the checklists are in `design/checklists/`; use them, since they may have grown. If the brief names only part of a checklist, apply all of it anyway and say so under Deviations.

## Order of work

1. Pin assignment first (below).
2. Re-run every check script for your scope: the same standard set that runs after every build (`references/schematic.md`, Scripted checks). Never trust a result from an old report, or one from before the last edit. Give the output. Reading a report's summary block is not a re-run.
3. Read the datasheets for the parts in scope. For a board review, read the layout, grounding and application pages yourself, rendered, not only the rows.
4. Apply every item of every named checklist and switched-on pack. Each item gets: met, not met, does not apply (with reason), or cannot tell (with what would tell). A "does not apply" on a layout, grounding, protection or absolute-maximum item is proposed, not decided (WR-21).
5. Look beyond the checklist: what has been overlooked, what is missing, what would fail in the field.
6. Rank findings and write the report.

## Pin item one

Pin assignment is the first item of every review, at both levels, for every part with pins that can be wrong, not only ICs. A misassigned pin means a board that does not start, bodges and reversed parts.

Schematic level:

- `sch_check.py pins` output: symbol pin numbers and names against `design/pins.csv`, footprint pads against the symbol, every used function supported by that pin, hidden and power pins, limits.
- Rows of `design/pins.csv` with `confirmed` not "yes": list them by designator. A part with an unchecked pin table is reported by designator at every checkpoint.
- For microcontrollers, peripheral allocation (`sch_check.py alloc`) and the source of the pin data (configurator export, vendor data or datasheet table).

Board level:

- footprint pads against the package drawing of the exact part ordered: pin 1 position, top view against bottom view, mirroring, exposed pad, pad numbering;
- land pattern against the datasheet's suggested pad layout, dimension by dimension where the datasheet gives one;
- polarity of diodes, LEDs, electrolytic and tantalum capacitors, and the silkscreen marks that show it;
- pin order of small transistors and regulators, which differs between makers for the same package;
- connector pin numbering against the mating part.

## Schematic review

Scope: the logical and electrical design. The board is out of scope, except that you read every datasheet layout section and check its rows were carried (schematic result "carried").

Apply the logical checklist, the electrical checklist and the switched-on packs in full. In particular, never skip:

- rails, labels and modules (`sch_check.py rails`, `sch_check.py modules`): every rail on its power symbol, no two nets joined by a shared symbol name, one sheet per module;
- power-up states (`sch_check.py powerup`) and the safe state if firmware fails (LG-11);
- every duty left to firmware has a signal the firmware can read, and was decided with the user (EL-44, EL-49);
- protection on every pin that leaves the board (`sch_check.py protect` review list, each item closed with a reason; `table_check.py netreview --stage ST6` fails while any review-list item is open);
- every checklist item that applies has a result in a review report (`table_check.py checklists --stage ST6` at the schematic review, `--stage ST11` at the board review; without `--stage` the items with no result are listed, not failed);
- supply input: reverse polarity, over-voltage and transients against every downstream absolute maximum, over-current, inrush;
- under-voltage and brown-out sensed at the supply of the part that must reset;
- absolute maximums in every state, not only steady state;
- signal integrity on fast or long digital lines (drive strength, edge rate, series termination, track length);
- emissions: switching frequency against sensitive bands, filtering per cable, noise conducted back into the supply;
- every DS- row with a schematic result; every "not met" with a decision;
- every difference from the typical application and the evaluation board with a reason;
- quiescent and leakage current, including current through dividers and pulls, where the board runs from a battery or has a low-current requirement;
- every path by which an energy store can drain back through the board, in every connection state (EL-51), and every case of several sources (EL-52).

## Basics review

Before the schematic is called done, every sheet is read by a worker that did not draw it. The other checks ask whether what was drawn is right. This one asks what is missing that any engineer would expect to see.

1. Read each sheet circuit by circuit, from the plot and the netlist.
2. Name each standard small circuit you meet: a button or switch, an indicator light, a pin of an off-board connector, a logic input, a supply pin, a reset or enable pin, a divider into a converter input, a gate drive.
3. Compare each with what a circuit of that kind ordinarily carries. Examples: a debounce capacitor at a switch read by a processor; a series resistor for a light; protection and a defined state on a connector pin; a pull on an input that can float; decoupling at a supply pin; a pull and a filter on a reset or enable pin; a gate resistor and a turn-off path.
4. For each ordinary part that is absent, give one result: add it, or list it with the reason it is not needed here.

An ordinary part needs no figure to justify it. Leaving one out is the user's decision: propose it with the reason, and report it as a decision. The result is one list per sheet in the report, each circuit with what was found and what was absent. Each absent part is a finding.

## Board review

Scope: the physical design, with its own checklist. It gets its own reviewer, separate from the worker who built the board.

1. Pin item one at board level (above).
2. Every carried DS- layout and grounding row has a board result. Check each against the datasheet page, not only against its constraint.
3. For every constraint enforced by `review:`, give a per-row verdict in report section 6: met, not met, or cannot tell. Evidence for a verdict is a measurement or coordinates read from the board file, with the command used, compared with the datasheet's words or figure. A render, or a pointer to the datasheet figure alone, gives "cannot tell". A verdict reached by hand is listed under "Not verified" as well. `table_check.py constraints` fails if a `review:` constraint has no verdict in the latest board review. A "not met" verdict is a violation: it fails unless a DC- decision covers it, named on the verdict line ("CN-014 not met (DC-031): ...") or as the decision of the constraint's DS- row. "cannot tell" with no decision is listed, and fails from the board checkpoint.
4. Run the board checks and the aids (`copper_area`, `loop_area`, `node_capacitance`). Compare each aid's number with what the datasheet says, and say whether it meets it.
5. Compare the layout with the datasheet's layout example and the evaluation board layout. Each difference is a finding with a reason, or a question.
6. Apply the board checklist and switched-on packs in full: return paths, decoupling per pin, via counts and positions, thermal vias, keep-outs, clearances by voltage, protection placement in the signal direction, edges and holes, mechanical stress on ceramic capacitors, assembly access and marks, fiducials and tooling holes, silkscreen against the agreed silkscreen plan, artefacts, copper balance.
7. Thermal at board level (below).

## Blind review

You have not been given the designer's reasoning, on purpose. Notes in the files are the designer's claims, not facts. Find what has been overlooked or forgotten, what features are missing, and what would stop this board working to specification or make it fail in the field.

For a blind board review: read each part's datasheet layout, grounding and application sections yourself and check the board against them. You are not given the designer's list of datasheet rows. List every datasheet instruction you checked, with part, section, page, quote and verdict. Any that has no DS- row is logged afterwards as an extraction miss, with `found_by` "blind review"; the coordinator charges it to the perspective whose scope it was in, and new rows and constraints follow.

Blind reviews have found real errors before (an interface the controller could not support, a supply margin, reset states, missing footprints). Be thorough rather than quick.

## Thermal

Part of both reviews.

Electrical (schematic review):

- For each part that dissipates power, compute junction temperature at rising ambient. Use the steps the user gave (examples: 70, 80 and 90 C) up to and beyond the stated maximum, with the datasheet's thermal resistance and derating curves (rendered and read). Use a script in `design/calcs/`.
- Which part reaches its limit first, and at what ambient.
- Values that drift with temperature: oscillator frequency, capacitance, regulator current limit, leakage, thresholds.
- What the board does beyond a limit: thermal shutdown, restart loop, drift, damage. Is that safe and acceptable?
- The temperature grade of every part against the ambient limit plus the rise inside the enclosure at full load. The assumed rise is written as an assumption.

Physical (board review):

- copper area and thermal vias for each hot part, as its datasheet asks;
- hot parts away from temperature-sensitive parts (references, crystals, sensors, electrolytic capacitors);
- the thermal estimate redone after any layout change near a hot part (an earlier board's estimate predated a ground-area change that reduced copper around the converter).

## Ranking

- Category: violation, risk, question, improvement, remark, extraction miss. A violation is a failed check, or a datasheet instruction worded must, should or recommend, a requirement, a rule or an absolute maximum, not met and not covered by a recorded decision. An unmet "should" or "recommended" is a violation, not a risk.
- Severity: 1 will not work, can damage, or unsafe; 2 not to specification or likely to fail in the field; 3 margin, cost or manufacturability; 4 minor.
- List findings by severity, then category. Each finding has an FD- ID, location, evidence (file, section, quote, measurement) and a recommendation.
- Violations quote their source: "Violation of <part> datasheet <section>: <quote>."
- Every finding goes into `design/findings.csv`.

## Side remarks

Anything you notice outside your scope is a side remark: an optional footprint worth leaving, a loop worth keeping tight, a cheaper part, a test point that would help. Record each in report section 8 and in `design/findings.csv` with category "remark". Never drop one. On an earlier board, two reviewers' advice was lost because remarks were not collected.

## Re-review

Anything changed since the last review is reviewed again. The baseline is the commit recorded for that review in `design/status.md`.

- List the files and blocks changed since the baseline (`table_check.py summary` reports them).
- Re-apply the checklists to every changed block, including the power-up states of any part added since. On an earlier board, an oscillator and a logic gate added after the last round were checked once only, and a missing pull-down was found later by the engineer.
- Record your review's own baseline commit in the report.

## Growing checklists

Report section 12 lists checklist additions you propose: what to check, the authority, the stage, and any script. The coordinator puts them to the user. Accepted items go into the project's checklist copy. Items that look general may be offered to the user as feedback for the skills.

## When to stop

Proposed criteria, for the engineer to decide on:

- no severity 1 or 2 finding open without a decision;
- every block changed since the baseline re-reviewed;
- every checklist item has a result;
- for a board review, every `review:` constraint has a verdict.
