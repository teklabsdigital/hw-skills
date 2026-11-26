# Requirements and parts

Procedures for the requirements draft (ST1), the logical design (ST4), research (ST2) and part choice (ST3), up to the parts check at the schematic checkpoint (ST6) and again before fabrication (ST12).

## Contents

Requirements; Environment; Logical design; Research; Candidates; Part change; Chosen parts; Parts table; Effective values; Parts check.

## Requirements

Write `design/requirements.md` from the template in `references/project-files.md`.

The file holds the current state only. Each item holds its current text; replaced text goes to the decision log or an archive file, never stays beside the item. Keep the file short enough to read in one sitting. When it grows past that, rewrite it short and archive the long version. Each accepted draft is committed, under the commit setting in `design/status.md`.

1. Start from the user's own words in the brief. Each functional requirement (FR-) and quality characteristic (QC-) gets its source: "user, <date>, <quote>".
2. Write what the board must do, not how. Keep each item testable: a number, a state, an interface variant. Give each item a priority (must have, or wanted), from the user.
3. Quality characteristics include cost, size, operating temperature, supply range, current in each state, service life, and any standard the user names. Ask, never assume, the temperature range.
4. Anything you infer is marked "proposed, to confirm". Never write an inferred item as a requirement (WR-06). A brief that contains a requirement the user did not state is a flag for the coordinator. A figure marked proposed is not designed against until the user confirms it: if your unit rests on an open To confirm line, name the line in the report and do not build on the figure.
5. When the user states a preference ("prefer brand X", "if we need a microcontroller, use family Y"), record it as a preference and note which default or earlier choice it would replace. A preference is not permission to change the architecture.
6. User journey: walk through unbox, plug in, power up, connect or pair, use, fault, unplug, store. For each step list what the user needs: buttons, indicators, connectors, access, labels. Each need maps to an FR- (proposed if new). This is how a missing pairing button or activity indicator is found before the schematic.
7. For each user-visible function, ask: does the user get the feedback they need, and is the button they need there?
8. Misuse cases: what a user could do wrong (wrong supply, reversed connector, hot-plug, short, wrong vehicle, water, dropping it). Each gets a required behaviour and, later, the part that gives it.
9. Off-board interfaces: every connector, cable, control, indicator, source and load the board meets, with what is at the other end.
10. The board's own behaviour over time: its modes, and the sequences between them (start-up, a source change, a fault, shutdown).
11. For each power source, ask: its environment, its misuse cases, what happens with two sources connected at once, and how the user sees which source is in use.
12. Test points: what the user wants for bench work, and for production test and programming.
13. Board profile: which board-type switches are on or off and why (from the first-session table and part choices).
14. Firmware instructions: start `design/firmware.md` now (template in `references/project-files.md`). It is filled sheet by sheet at the schematic stage (`references/firmware-instructions.md`). The skills list what firmware can and must do; they write no firmware.

Report the items to confirm as a numbered list. Each is a To confirm line with its own TC- ID, in the form `references/project-files.md` gives.

**A small change.** A change to a few items needs no new draft. Change only the items touched, give the decision (DC-) behind each, move the replaced text out as above, and leave the rest of the file as it is. The report lists the items changed, each with its decision.

## Environment

Fill the environment profile only for areas the coordinator switched on; mark others "does not apply" with the reason.

- Every supply the board might see: nominal, minimum, maximum, transients, reverse connection, hot-plug. Ask "what else could it be plugged into?" (an earlier board was designed for 12 V and needed a new regulator when 24 V vehicles came up).
- Temperature range in operation and storage, humidity, condensation, vibration and shock, water and dust, altitude if relevant, transport.
- Electromagnetic surroundings: what nearby receivers could be disturbed (an earlier board found its converter frequency sat in the AM radio band).
- Standards: only those the user names or the market requires. Fetch and cite each one (URL and date, or the user's copy). Never quote a standard's levels from memory (WR-01). A standard that must be bought, or cannot be fetched, is written "named, not read", with its price, and no clause of it is quoted; ask the user. Start standards research early, since a standard can change the requirements.

## Logical design

At ST4, add the "Logical design" section to `design/requirements.md`:

- blocks and what each does, each tied to FR- IDs;
- interfaces between blocks and off the board, with exact variants and speeds;
- the power tree: every rail, its source, its loads, and a current budget per rail and per state (sleep, idle, active, radio bursts);
- states: start-up, shutdown, sleep and wake, fault, removal; what each output does in each state, and the safe state if firmware fails;
- programming and debug access, in the enclosure too;
- the hardware needs of field update and stored data;
- assembly variants and not-fitted parts.

The logical design ends in a set of module definitions. Each module maps to exactly one sub-sheet of the schematic. The schematic is hierarchical in KiCad's own form: the top sheet shows the modules as boxes joined by nets, and nothing else (`references/schematic.md`, Sheets). Write each module's purpose, edge nets, parts and open points in `design/modules.md`, and the tables the scripts read: one row per module in `design/modules.csv` and one row per net between modules in `design/module-nets.csv` (columns in `references/project-files.md`).

Derive what the user needs, not only what the brief lists. Every non-obvious connection (for example a wake line to a second pin) is put to the user as a numbered decision with its cost on the board (track length, pins used). Never change the architecture without the user; propose it, and the coordinator asks.

Before the logical design is accepted, show the user every off-board item (connector, cable, control, indicator, source, load) as the physical thing it is: what it looks like, where it sits and what plugs into it. A name in a block list is not enough.

Apply the logical checklist (`references/checklist-logical.md`) and report each item's result.

## Research

For a research brief (protocols, architectures, support chips, standards):

1. Restate the question and quote the requirements in scope by ID.
2. Search broadly first. Do not narrow by one package, brand or family too early; a filter on package size once hid the only part option that met the speed requirement.
3. A part search has two steps. First browse the makers' own ranges, from more than one maker; the user's preferred makers are a preference, not a limit. Then check that each option can be bought at the user's suppliers, in the order given at setup (the `Suppliers:` line of `design/status.md`). Never ask for that order again.
4. For each option: function fit against each requirement, price, stock, ecosystem (tools, libraries, community), risk, and sources.
5. State the reach of the search in the report: which makers' ranges were browsed in full and which were not. Asking the user for a shortlist is a normal step, not a failure.
6. If a site refuses a fetch, try the other legitimate sources once, in the order `references/datasheets.md` (Get) gives, before the document becomes data needed from the user (WR-03). If data is unclear, ask.
7. A brief for one block of several researched at the same time asks for the block's interface figures: the voltage, current and timing at each edge it shares with another block. Report them; a recheck across the blocks follows.
8. End with a short recommendation and its reason, the alternatives it was chosen over and why each lost, and the decisions the user must make.

**Market scan.** When the board will be sold, the user chooses at setup: none, light or full (the `market scan` setting in `design/status.md`). Light is a cost target and one side-by-side table that compares the design with named competing products, with a cost column. Full is a research step of its own, with its own brief. In both, the comparison is one table against named products, each row with its source and date, and cost is always a column.

## Candidates

When parts are proposed for a block:

- Give candidates side by side: function fit against each requirement (including the exact interface variant, for example classic or flexible data rate), key limits, package, price at the project quantity, stock, lifecycle, and the source page with date.
- Before a part is proposed, read its lifecycle status on the maker's own page and check it can be bought at the user's suppliers. State the status and where it was read beside the part. Lifecycle belongs to the exact orderable code, not the family: one package or grade can be active while another is ended. A part that is obsolete, on last-time-buy, in preview or not recommended for new designs is not proposed; if nothing else fits, report it with its status and the user decides.
- A proposal carries the supplier's part number, the stock and the unit price, read from a page fetched in this run. A price is always given with its quantity break. If the first supplier in the user's order does not stock the part, say so and give the next supplier's figures.
- Price and stock are checked when the part is chosen, not later (an earlier board was drawn around a costly module before its price was checked).
- A rating from a distributor's attribute table is a lead only. Read the figure and its conditions from the maker's datasheet before it is used.
- Flag a headline figure that the datasheet gives only as typical. If another package of the same part could be taken, say what changes with it (thermal resistance, ratings, pinout).
- Compare the part's rated temperature range with the ambient limit plus the rise inside the enclosure at full load, not with ambient alone. Write the assumed rise as an assumption.
- A part in series with the main current is reported with its loss in watts at full current, not only its resistance or voltage drop.
- For a node shared by two blocks, give one table of every part on that node: the voltage at normal, at surge and in each named single-fault case, against each part's rating.
- Check the interface variant at selection against the requirement, from the datasheet's own words.
- Look in the datasheet for alternatives that meet the requirement differently (a lower crystal frequency with an internal multiplier, a different package of the same die).
- Prefer common parts from several makers where the circuit allows; use the user's package size, through-hole or SMD, and assembly route from `design/status.md`.
- Show the cost effect of each choice on the running total.
- Any part that raises the cost needs the user's approval (the coordinator asks).

## Part change

When a part changes, including a swap under the same designator:

1. Check the new part against every requirement it touches: speed, voltage, current, temperature, interface variant, package, cost (WR-18). A substitute that "covers the actual job" but breaks a stated requirement is not a substitute; report it.
2. Check stock now. If stock is short, widen the search: other packages, other makers, other frequencies with a multiplier.
3. Run the datasheet passes for the new part (`references/datasheets.md`). Every row carries the new MPN.
4. Run `table_check.py stale` and `table_check.py impact <designator>` to list the rows, pins, constraints and reviews the old part's MPN touches; they are reopened.
5. Report the cost effect and what must be reviewed again.

## Chosen parts

When the user names a part for a kind of position (for example "use this part for every <kind of position>"), it goes to every position of that kind in the whole design, not only the sheet in hand.

- Record it as a row in `design/chosen-parts.csv` (columns in `references/project-files.md`). A position that keeps another part is an exception in that row, and each exception needs the user's decision (DC-).
- `sch_check.py chosen` lists every position of the kind, with the part drawn there and its supplier number. It fails on a position with another part unless a user decision is recorded for that position.
- The report lists the positions the part went to and the positions it did not, with the decision for each of those.

## Parts table

`design/parts.csv` is the single source of BOM fields (template in `references/project-files.md`).

- Every fitted part has the four sourcing fields: manufacturer, manufacturer part number, supplier, supplier part number. They are researched on the supplier's page, fetched in this run, never guessed. Check that the supplier part number really is that MPN, on a date.
- The same base number with a different suffix, or from another maker, is a different part. It gets its own datasheet check and is never treated as the chosen part.
- Research the supplier numbers during design, for the assembler the user plans and for buying parts by hand, so a BOM can be uploaded either way.
- Fill `role` and `category`. A `category` that belongs to a pack switches the pack on; say so in the report.
- Fill `package` from the MPN's ordering information and check the footprint matches it.
- Fill `lifecycle`, `temp_grade`, `msl`, `peak_reflow`, `alternate` from the maker's and supplier's pages. The lifecycle is that of the exact orderable code, and the maker's page it was read on is saved (Parts check, step 2).
- Every part has a footprint that exists and a 3D model, or a waiver (DC-). `table_check.py parts` checks the fields, dates, packages, footprints and models.
- A part drawn as a placeholder is an open item: a To confirm line that says what must be known to close it.
- Keep a running cost total at the project quantity, including the assembler's fees from `design/fab-capabilities.csv` (per-part loading fees, part classes, double-sided and through-hole fees, minimum quantities, attrition).
- Totals and counts are never counted by hand. `table_check.py parts-totals` computes them from the rows; give its output.

## Effective values

Nominal values are not what the circuit sees. For each part where it matters, use the effective value in calculations and record the source:

- class 2 ceramic capacitors: capacitance at the DC bias, temperature and age the design applies, read from the maker's curve or tool (a graph row, rendered and read);
- inductors: saturation current at the highest current limit and at hot temperature; DC resistance at temperature;
- ferrite beads: impedance at the DC current;
- electrolytic, polymer and tantalum capacitors: ripple current, voltage derating, life at temperature, from the maker's guide;
- resistors: power, voltage and pulse rating;
- MOSFETs: on-resistance at the real gate drive and hot; diodes: leakage hot, recovery, surge; LEDs: forward-voltage headroom.

If the curve cannot be read, the value is "not verified" in the report.

## Parts check

Two parts checks: at the schematic checkpoint (ST6) and before fabrication (ST12). A parts check is a look at stock, price and lifecycle on a date, not a freeze: parts can still change afterwards, through Part change.

1. Check stock and price for every fitted part on the supplier's page today. Record them with the date in `design/parts.csv`.
2. Check lifecycle for the exact orderable code, on the maker's own page, and look for a newer datasheet or errata revision. Save the page as text, `datasheets/<MPN>_product-page.txt`, with the table of orderable codes and their status in it, one code to a line, and add its line to `datasheets/README.md` (URL and date read). Codes that share one page share one file, named after the first MPN. Write the status of the exact code in the `lifecycle` column of `design/parts.csv`, with the status word first. A status that is not active needs the user's decision (DC-), named in the cell.
3. Check every footprint matches the package of the MPN ordered.
4. Run `table_check.py parts` and give its output. A stock and price date older than 30 days (`--max-age`) is listed with its age in any run. Before ordering, run `table_check.py parts --stage ST12`: there such a date is a fail. The same run compares the `lifecycle` column with the saved pages: it fails a row that says active when the page's line for the exact code says otherwise, and lists the rows with no saved page (`references/project-files.md`, parts.csv). A listed row is not a checked row: say in the report how its status was read.
5. List, by designator: parts with low or no stock, parts whose price changed, parts with no checked pin table, parts with no 3D model or an unchecked one.
6. A part that must change goes back through Part change. The coordinator puts it to the user.
