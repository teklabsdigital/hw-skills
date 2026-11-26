# Project files

Templates for every project state file. They live in the user's project under `design/`, and the simulation files under `sim/`. A worker writes them from these templates at project setup (ST0), and every worker keeps them current. Scripts read the CSV files, so keep the columns exactly as written here.

Placeholders are in angle brackets. Nothing in the examples comes from a real datasheet.

## Contents

General rules; IDs; requirements.md; decisions.md; status.md; user-rules.md; sprints; compliance.csv; sections.csv; pins.csv; parts.csv; chosen-parts.csv; modules; rails.csv; separate-nets.csv; firmware.md; fab-capabilities.csv; constraints.csv; constraints-reviewed.csv; findings.csv; net-review.csv; checklists; reports; progress files; test-sweep.md; calcs; sim-models.csv; scenarios.csv; build.json; ownership.csv; passes; renders; briefs; .private-terms; scan-reviewed.csv.

## General rules

- Markdown for text people read. CSV for tables scripts check.
- CSV: UTF-8, one header row, comma separated, a field with a comma or quote in double quotes, one record per line. Several values in one field are separated by ";". Dates are YYYY-MM-DD.
- Never delete a row. Change its result, or mark it "reopened (DC-nnn)" or "superseded by <ID>".
- Every row that comes from a part carries the MPN it was taken from, so a part swapped under the same designator is caught (`table_check.py stale`). A compliance row about an external part (a resistor the regulator's datasheet sizes) carries the designator of that part, or several joined by ";", and the MPN of the datasheet it came from; it stays current while that MPN is fitted somewhere. A pin row always carries its own part's MPN.
- A table with a header and no rows is listed in an ordinary run, and fails from the schematic checkpoint (`--stage ST6`) unless a decision names the file and says why it is not needed (`compliance.csv`, `sections.csv`).
- No client names, account details, passwords, keys, machine paths, user names or host names in any file (those terms go only in `.private-terms`). Paths are relative to the project root, and never point into the scratch folder.
- A line a script reads holds only what the script reads, in the form given here. A note goes on a line of its own, unless the template gives it a place.
- Each file holds the current state. History lives in the decision log and in git.

## IDs

IDs are stable, never reused, and use prefixes that cannot be read as a reference designator:

| Prefix | What | Example |
|---|---|---|
| FR- | functional requirement | FR-01 |
| QC- | quality characteristic | QC-01 |
| DC- | decision, waiver or pivot | DC-001 |
| DS- | datasheet row | DS-001 |
| CN- | constraint | CN-001 |
| FD- | finding or side remark | FD-001 |
| NR- | net-review item | NR-001 |
| SP- | sprint | SP-01 |
| BR- | brief and its report (sprint, brief) | BR-01-03 |
| TC- | To confirm line in the requirements | TC-001 |

Take the next free number in the file. When several workers write at once, use the staging files (see passes) and let the merge assign IDs.

Workers that run at the same time never append to a shared file. Each writes its rows to its own rows file, `design/passes/BR-<sprint>-<n>_<table>.csv`, with the table's columns and provisional IDs. The plan names the one writer of each shared file; that writer merges the rows files, assigns the IDs, checks the counts against each report, and deletes the rows files. This holds for research and filing workers too: each writes its own findings rows.

To change or add one row of a table, use `table_check.py set-row <table>.csv <key> column=value`. It writes that one row and leaves every other line as it was, so the diff shows only the change. It never changes a key column. Do not rewrite a whole table to change one row.

## requirements.md

```
# Requirements: <project>
## Functional requirements
FR-01 <what the board does>. Priority: <must have | wanted>. Source: user, <date>, "<quote>".
      Evidence: (filled at the schematic checkpoint) <DS- rows met; check and build>
## Quality characteristics
QC-01 Cost: parts under <budget> at quantity <n>. Priority: <...>. Source: user.
QC-02 Operating ambient <range asked>. Priority: <...>. Source: user. Standard: <named, or none>.
QC-03 Protection against cost: <how the user ranks them>. Priority: <...>. Source: user.
## Market and cost target (only for a board that will be sold; market scan = light or full)
Cost target: <figure at quantity <n>>. Source: <user | market scan BR-nn-nn>.
Comparison: <similar product; price; what it does; source and date>, one line each
## Environment profile    (each item answered or "does not apply", with source)
Supplies it might see: <list, with source>
Temperature, humidity, vibration, water and dust, storage and transport: <...>
Region of use: <...>
## Power sources         (one block per source)
<source>: environment <...>; misuse cases <...>; with another source present at the same time <...>;
  how the source in use is shown <...>; may the product draw from what it supplies <yes | no>
## Off-board interfaces  (connector or link; what is on the other end; signals, levels and limits; source)
## Behaviour over time   (modes and sequences: what the board does by itself, in order, with times)
## Misuse cases          (case; required behaviour; part that gives it)
## User journey          (unbox, plug in, power up, connect, use, fault, unplug, store; FR- per step)
## User interface        (on the board, in an app, or both; what the user sees and presses)
## Logical design        (blocks, interfaces, power tree, states: start-up, shutdown, sleep, wake, fault, removal)
## Board profile         (switch; on or off; reason: user answer or part choice)
## Test points           (bench; production test and programming)
## Firmware instructions (not kept here: see design/firmware.md; pins in design/pins.csv)
## To confirm            (one line per open point, in the form below)
TC-001; open; needs the user's answer; <the question>; <item it belongs to, FR- or QC- or section>
TC-002; open; proposed by a worker; <the proposed figure and its reason>; <item>
TC-003; answered (DC-nnn); needs research; <the question>; <item>
```

Items you infer are marked "proposed, to confirm" and listed again under "To confirm", so the coordinator asks them as one batch at ST1. Never add a requirement the user did not state (WR-06).

A To confirm line is `TC-nnn; <state>; <kind>; <question or proposal>; <item>`. The ID is never reused. The state is open, answered (DC-nnn) or withdrawn (DC-nnn). The kind is one of three: needs the user's answer; needs research; proposed by a worker. A proposal for every open point is welcome, and it is still not a value: a figure on a line that is open is not designed against until the user confirms it (WR-06). An answered or withdrawn line stays, with its decision.

The file holds the current state and stays short enough to read in one sitting. Each item holds its current text only; replaced text goes to the decision log, not into the item. When the file grows long, it is rewritten short and the long version is kept as `design/archive/requirements-<date>.md`. It is committed at each draft the user accepts, as the commit setting allows.

A requirement that no longer holds is never deleted and its ID is never reused. Write it as `FR-03 Withdrawn (DC-nnn): <the old text>`, with the decision that withdrew it. A replaced item is withdrawn the same way, and the new text gets the next free ID. `table_check.py summary` counts withdrawn items apart, not as items that wait for evidence; it names an item marked withdrawn with no DC- ID, and still counts it.

A board profile row is `- <switch>; on|off; <reason>`, with the switch's short name from `packs.md`. The state is "on" or "off" alone; words such as "to confirm" go in the reason. `table_check.py packs` and `checklists` fail on a row they cannot read, and name it.

## decisions.md

The decision log. The coordinator keeps it from the first message and is its only writer; workers report their choices and the coordinator logs them. It holds every decision, not only the user's: the coordinator's own judgement calls, the choices a worker made inside a task, waivers, pivots, and things not done on purpose (a check skipped, a review declined, a guideline bent, a recommendation not taken), each with who decided. One entry per decision, appended at the end:

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

- The statement comes first, in plain English, with the ID in brackets. The ID is the next free DC- number; IDs rise in file order.
- "seen by user" is needed when the coordinator or a worker decided. It stays "no" until the coordinator has listed the entry in a report to the user.
- An entry is never rewritten. Only its `Status` and its "seen by user" may change later. A change of mind is a new entry with `Replaces:` (one ID or several), and each old entry's `Status` becomes "superseded by" the new one. An entry that a later one ends without changing it is "closed (how, DC-nnn)".
- A datasheet error the user decided (WR-22) names the MPN and the datasheet revision in the statement, so a later pass finds it and does not ask again.
- A waiver is a decision of kind waiver. Every later report lists the open waivers.
- "question answered" is the lighter kind for a prompt of the user that settled no design choice. With `log every prompt` on (the default), every prompt gets an entry, of this kind when no other fits.
- `table_check.py decisions` checks the fields, the IDs and their order, and the back-pointers, and lists the entries the user has not seen yet.

## status.md

```
Designs: logical <state>; electrical <state>; physical <state>
Ownership: schematic <script|hand>; board <script|hand> (since DC-nnn); rule file <...> (detail in ownership.csv)
KiCad folder: <hardware/ unless build.py --adopt recorded another folder; . for the project root>
Execution mode: <parallel workers | one worker at a time | single session, briefs run in turn>
Settings: stop-and-ask = <default>; model split = <default>; reports = <normal>;
  datasheet passes = <three for complex and pack parts>; commits = <offer at sprint close>;
  backup commits = <on | off>; datasheet reading = <up-front passes | as parts are placed>;
  log every prompt = <on | off>; market scan = <none | light | full>;
  simulation = <per module; declined: <modules, each with its DC-nnn>>; controller in the loop = <yes | no>;
  sheets = <per block | one sheet>; assembly = <hand | board house>; derating = <policy or none>;
  package size = <...>; form = <all SMD | mixed>
Suppliers: <the user's suppliers, in order>; preferred makers: <list, or none>
Tool version rule: <the user's own rule on versions and automatic updates, or none>
Scratch folder: .hwtmp/
Third-party PDFs committed: <yes | no>
Region of use: <...>
User interface: <on the board | in an app | both>
PDF route: <own PDF reading | macOS scripts | installed tool and version>; figures readable: <yes|no>
Tools: KiCad <version, release date>; Python <version, release date>; compiler <...>; router <commit or tag>
Guidelines (may be bent): <power paths first; one direction per layer; ...>
User's own habits: <placement and routing habits>
Schematic drawing habits: <how the user draws rails, labels, wires and text, and balances a page>
Sequencing: <for example: do not update the board until the schematic is done>
Control inputs: <leave this line out; write "none, DC-nnn" only when no part on the board has a control input>
Expected DRC notes: <none, or empty here with one line per note below>
  - "<text in the note>" on <item, for example Footprint J1>, DC-nnn
Expected ERC items: <none, or empty here with one line per item below>
  - "<text in the violation>" on <item, for example Symbol U1 Pin 3>, DC-nnn
Review baselines: schematic review <BR-> at <commit>; board review <BR-> at <commit>
Checkpoints: <requirements read; schematic checkpoint; 3D sign-off; board checkpoint>
Sheet progress: <one line per sheet below>
  - <module>: <not started | drawn | checked | basics review done | simulated | accepted>
Accepted, not yet drawn: <none, or one line per item below>
  - <the fix or change the user accepted>, DC-nnn, <sheet>
Waiting on the user: <none, or one line per item below; the one standing list>
  - <decision or data needed>, <since date>, <what it holds up>
Next thing to look at: <what the user can next look at, and how many steps away it is>
Next step: <written before every long run, at a pause and at the end of a day; who acts next>
Skills version: hw-skills <version>; scripts copied <date>
```

The supplier order is asked once at setup. Every later part search, price and proposal follows it without asking again. An item leaves "Accepted, not yet drawn" only when the build that draws it has passed its checks.

`fab.py` reads the expected DRC notes in exactly that form, one indented line each. A schematic-parity note that is not listed there is a violation.

`build.py` reads the expected ERC items in the same form. They are for violations that wait on work not yet done, such as a sheet not yet drawn, each under a decision. The ERC stage compares the list, not the count: a violation with no line stops the build, and so does a line whose violation is gone. When the lists agree, the build goes on and exports the netlist. The report is `ERC.json` in the KiCad folder; keep it out of git.

What an expected ERC item may name. The text is a part of the violation's description. The item is the start of one item description in the report, for example `Symbol U1 Pin 3`: the kind, the designator, and the pin if one pin is meant. A designator of a part is compared exactly. The number of a power symbol or power flag reference is ignored on both sides: `#PWR104` and `#PWR106` both read as `#PWR`, and `#FLG01` as `#FLG`. Several power symbols sit on one net, and KiCad names any one of them, not the same one in every run. Write such an item as `Symbol #PWR Pin 1`; a line written with a number still works. So one line covers that text on any power symbol or flag, and two violations of that kind cannot be told apart by the list: say in the decision which nets it covers.

## user-rules.md

`design/user-rules.md`: the user's standing rules, the ones that cut across the whole project. Short. Every brief cites it and every worker reads it. A rule, or a capability the user adds in the middle of the project, is written here in the turn it is given, so it is not lost.

```
# The user's standing rules
1. <the rule, in the user's words where they fit>. Given <date> (DC-nnn).
2. <...>
```

A rule is never renumbered. A rule the user withdraws is marked "withdrawn (DC-nnn)" and stays.

## sprints

One file per sprint: `design/sprints/SP-NN-<slug>.md`.

```
## Plan (approved <date>)
Goal: <one line>. Serves: <FR- and QC- IDs>. Blocks: <list>. Out of scope: <list>.
Steps: 1 <step, worker mode, brief ID> 2 <...>
Exit checks: <checks that can fail, with expected results>
## Close report (<date>)
Where we are; done; verified and how; not verified; violations; decisions; what next.
```

## compliance.csv

One row per datasheet instruction or limit (WR-05). How to fill it: `references/datasheets.md`, Compliance rows.

```
id,designator,mpn,datasheet,revision,section,page,figure,kind,category,perspective,text,design_value,margin,schematic_result,board_result,decision,carried_to,evidence,found_by
DS-031,U1,<mpn>,<mpn>.pdf,<rev>,<layout section> item <n>,<p>,,must,grounding,physical,"<quoted text>",,,carried,met,,CN-031;CN-032,board_check <sub-command> CN-031 pass (build <hash>),pass
DS-032,U1,<mpn>,<mpn>.pdf,<rev>,<layout example>,<p>,<figure>,figure,layout,physical,"<what the figure shows, in words>",,,carried,open,,CN-033,,pass
DS-044,Y1,<mpn>,<mpn>.pdf,<rev>,<application>,<p>,,recommend,decoupling,electrical;physical,"<quoted text>",<value fitted>,,not met,,DC-020,,decision DC-020,pass
```

| Column | Allowed values |
|---|---|
| `kind` | must, should, recommend, limit, typical-only, calculation, figure, graph, errata, typical-application, data |
| `category` | pin, absolute-maximum, operating, electrical, timing, thermal, protection, decoupling, external-component, configuration, power-up, layout, grounding, package, assembly, errata, typical-application, other |
| `perspective` | logical, electrical, physical; several joined by ";" after a merge |
| `schematic_result` | open, met, not met, does not apply, carried (layout and grounding rows only) |
| `board_result` | open, met, not met, does not apply |
| `decision` | a DC- ID, or "proposed" while the user decides |
| `carried_to` | CN- IDs joined by ";" |
| `found_by` | pass, review, blind review |

Hard rows: category layout, grounding, protection or absolute-maximum. Only a DC- decision sets them to "not met" or "does not apply" (WR-21).

Open rows: a `must` row, or a hard row, still "open" with no DC- decision is listed in every ordinary run of `table_check.py compliance` and fails at its checkpoint: from the schematic checkpoint (`--stage ST6`) for most rows, from the board checkpoint (`ST11`) for `package` rows, and before ordering (`ST12`) for `assembly` rows.

Package and assembly data: kind `data` is a value the design uses but no instruction (pad size, pitch, height, moisture level, peak reflow temperature, tape width). Category `package` rows are closed by whoever checks the footprint and 3D model against the drawing (ST9, at the latest the board review, ST11); category `assembly` rows by the fabrication worker against the assembler's limits (ST12). The pass that writes them leaves them "open".

One sentence, two kinds: a sentence that states both a connection and a value (for example "connect a <value> resistor from EN to VIN") gives one row in each pass that reads it: the logical pass the connection, the electrical pass the value. Each writes only its own part; the merge keeps one row with both perspectives and both texts.

Rows not tied to one section (the whole datasheet, the ordering page, a delegated document as a whole) use `section` "general". A pack item that does not fit the board's topology gets "does not apply" with the reason in the pass report, and no row.

`page` is the PDF page number, counted from 1 at the first page of the file, the same number the page render carries. A `calculation` row closed as met or not met names its script in `design/calcs/` in `evidence`. A row whose text starts "no guidance found" says in `evidence` what was read and searched for. A figure read by eye from a graph is marked "read from graph" in `design_value` or `evidence`, and again wherever it is used. What each kind means: `references/datasheets.md`, Compliance rows.

## sections.csv

One row per section and subsection of every datasheet and delegated document.

```
datasheet,revision,section,title,pages,category,claimed_by,rows_logical,rows_electrical,rows_physical,note
<mpn>.pdf,<rev>,<n>,<layout guidelines>,<pages>,layout,physical,0,0,9,
<mpn>.pdf,<rev>,<n>,<layout example>,<page>,layout,physical,0,0,3,figure rows
<mpn>.pdf,<rev>,<n>,<thermal information>,<page>,thermal,electrical;physical,0,2,1,
<mpn>.pdf,<rev>,<n>,<functional modes>,<pages>,functional,logical,0,0,0,no instructions here (<BR->, <date>)
```

`category`: pins, absolute-maximum, operating, electrical, timing, thermal, functional, configuration, application, typical-application, power-supply, layout, grounding, package, assembly, errata, revision-history, ordering, other. A layout, grounding, application, thermal or typical-application section with zero rows needs a `note`.

## pins.csv

Every part with pins that can be wrong, one row per pin, with the power-up columns. How to fill it: `references/datasheets.md`, Pin tables.

```
designator,mpn,pin,name,functions,used_function,net,supply,levels,abs_max,current_limit,reset_state,boot_activity,control_input,required_in_reset,given_by,sleep_state,fault_state,source,source_page,confirmed
U2,<mpn>,<n>,<pin name>,"<all functions>",SPI clock,SPI_SCK,3V3,<>,<>,<>,<>,none,no,,,,,vendor data <version>,,yes
U7,<mpn>,<n>,EN,enable,enable,BOOST_EN,3V3,<>,<>,,,,yes,off,R40 pull-down,off,off,datasheet table,<p>,yes
```

`source`: configurator export (highest trust), vendor data, datasheet table. `confirmed`: yes only after a human or a second worker checked it. `control_input`: yes or no. With no row marked yes, `sch_check.py powerup` is not run and does not pass. A board with no control input at all records that as the line `Control inputs: none` in `design/status.md`.

## parts.csv

The single source of BOM fields. A schematic generator reads it; for a hand-owned schematic the direction reverses and the table is read from the symbol fields.

```
refs,value,footprint,package,manufacturer,mpn,supplier,supplier_pn,role,category,dielectric,tolerance,voltage_rating,unit_price,qty_price,stock,checked,lifecycle,temp_grade,msl,peak_reflow,alternate,variant,datasheet,datasheet_revision,errata,compliance_done,pins_done,model,model_checked
```

| Column | Meaning |
|---|---|
| `refs` | designators, joined by ";" |
| `role` | protection, decoupling, bulk, pull, connector, switch, button, indicator, regulator, clock, interface, radio, sensor, other |
| `category` | the packs the part belongs to, if any (switching converter, radio, vehicle bus, USB, and so on), several joined by ";"; empty if none |
| `supplier`, `supplier_pn` | the first supplier in the `Suppliers:` order of `design/status.md` that stocks the part, and that supplier's own part number. If the first supplier does not stock it, the report says so and gives the next supplier's figures |
| `stock`, `unit_price`, `qty_price`, `checked` | from the supplier page fetched in that run, on the date in `checked`; never from memory or an older report. `qty_price` is the price with its quantity break, as `<price> at <quantity>`; a price is never given without its quantity. A fitted part with no date is listed, and fails from the schematic checkpoint; a date older than 30 days fails only before ordering |
| `lifecycle` | the status of the exact orderable code, starting with the status word: `active`, or the maker's word (for example "not recommended for new designs"), then where and when it was read. A status that is not active also names the user's decision (DC-). `table_check.py parts` compares the cell with the maker's saved page (below) |
| `datasheet` | the link to this part's own datasheet, not a library default or a family page |
| `variant` | empty (fitted in every build), "not fitted", or the variant names that fit it, joined by ";" (fitted only when `fab.py --variant` names one) |
| `compliance_done`, `pins_done` | yes when the datasheet passes and pin table are complete |
| `model`, `model_checked` | the 3D model path; yes when its height, offset and rotation were checked against the drawing |

Four sourcing fields are required for every fitted part: `manufacturer`, `mpn`, `supplier`, `supplier_pn`. Every fitted symbol carries them as fields, `supplier_pn` as the field "Supplier PN", and its "Datasheet" field holds the part's own datasheet link. `sch_check.py fields` checks the symbol fields against this table. The `model` columns here are 3D models; simulation models have their own table (sim-models.csv).

Lifecycle against the saved page. The maker's product page is saved as text, `datasheets/<MPN>_product-page.txt`, with a line in `datasheets/README.md` (`references/requirements-parts.md`, Parts check). `table_check.py parts` reads the files in `datasheets/` whose names end in `_product-page.txt`, and no other file. A page belongs to a fitted row when one of its lines names the row's exact MPN; a longer code that holds the MPN does not count. The words it looks for are: not recommended for new designs, NRND, last time buy, end of life, obsolete, discontinued, preview.

- A fail: the `lifecycle` cell starts with "active", or is empty, and a line that names the exact MPN carries one of the words.
- A fail: the cell does not start with "active" and names no DC- decision made by the user.
- Listed, not failed: one of the words on another line of the part's page. Read the page and confirm the status of the exact code.
- Listed, not failed, at every stage: a fitted row with an MPN that no saved page names, with the count.
- A row whose cell names a decision made by the user is not compared with the page.

The check prints how many pages it read, also when that is 0. It reads the saved text only: it does not fetch the page, and a page saved long ago can be out of date.

## chosen-parts.csv

`design/chosen-parts.csv`: the parts the user chose for a kind of position. A part the user names for a kind of position goes to every position of that kind in the whole design.

```
kind,match,mpn,supplier_pn,decision,except_refs
<kind of position, for example pull resistor>,<how a position of this kind is found: value, role or footprint>,<mpn>,<supplier part number>,DC-nnn,<designators that keep another part, joined by ";", or empty>
```

`match` is one or more terms joined by ";": `value=`, `role=` (the role in parts.csv) or `footprint=`, where `*` stands for any text. `decision` is the DC- entry in which the user chose the part. Each designator in `except_refs` needs a user decision of its own for that position, named in the decision log. `sch_check.py chosen` lists every position of each kind with the part drawn and its supplier number, and fails on a position with another part that is not an exception. The report of a unit that places a chosen part lists the positions it went to and those it did not.

## modules

A module is a sub-sheet under the top sheet. Four tables that scripts read, and one prose file.

`design/modules.csv`, one row per module. `ref_block` is the module's fixed block of designator numbers.

```
module,sheet,ref_block,purpose
<module>,<module>.kicad_sch,100-199,<one line>
```

`design/module-nets.csv`, one row per top-level net between modules. `modules` lists the modules the net joins, joined by ";".

```
net,modules,note
<NET_NAME>,<module a>;<module b>,<what it carries>
```

The other two tables are rails.csv and separate-nets.csv, below. `design/modules.md` holds the prose:

```
# Modules: <project>
## Drawing order
1. <top sheet>
2. <module>
...
n. <processor sheet, drawn last>
## <module>
Purpose: <what it does, and the FR- and QC- IDs it serves>
Edge nets: <each net that enters or leaves, with its direction and what it carries>
Parts: <the main parts, by MPN, and why each is there>
Open points: <none, or each open point with its TC- or FD- ID>
```

The drawing order starts with the top sheet and ends with the processor sheet, so every other module's pin needs are known before the processor's pins are given out. The tables are what the scripts read; where the prose and a table disagree, the table is corrected first and the prose follows. `sch_check.py modules` checks that the tables agree with each other, that there is exactly one sheet per module (a sheet of text only, such as the firmware page, needs no module), that the top sheet holds only the module boxes, that every designator sits in its module's block, and that every net that joins two or more sheets is a net in `module-nets.csv` that joins only the modules listed for it. A net of `module-nets.csv` stays a net of its own: when it is drawn with part pins on it and KiCad has joined it to another net, such as a rail, the check fails and names that net.

Removing a module is a procedure of its own. Handle each of these, and list them in the report: its sheet file; its row in `ownership.csv`; its rows in `modules.csv`, `module-nets.csv`, `rails.csv` and `separate-nets.csv`; its section in `modules.md`; its lines in `firmware.md` and its folder under `sim/`; its rows in the part tables, marked superseded, not deleted; its open findings, each closed with the reason; and its designator block, which is not given to another module. List every file that is now stale; the user agrees before any is removed (`references/repository.md`, Layout).

## rails.csv

`design/rails.csv`: the declared rails. Only a rail in this table may be drawn with a power symbol.

```
rail,kind,voltage,source,note
<+3V3>,supply,3.3,<the regulator or connector that makes it>,
GND,ground,0,,
```

`kind` is supply or ground. `voltage` is one number in volts, or a range written as `<lowest> to <highest>` for a rail that moves, such as a cell. `sch_check.py` takes the voltage of a supply rail from this column, and takes a range at its highest; `sch_check.py currents` prints the values it used and names a voltage it could not read. `sch_check.py rails` reads the KiCad files and this table. It fails on: a power symbol whose name is not a declared rail; a rail that is more than one net; two rails, or a label, on one rail wire; a rail passed as a sheet pin or as a hierarchical or local label; a signal on a global label. A rail may be drawn as a power symbol or as a global label of the same name. Each rail is proven against KiCad's own netlist; a rail that cannot be proven is printed as "not proven". Buses are not followed. It also checks separate-nets.csv.

## separate-nets.csv

`design/separate-nets.csv`: pairs of nets that must stay separate.

```
net_a,net_b,link_part,reason
<AGND>,<GND>,<the one part allowed to join them, or empty>,<why, with its DS- or DC- ID>
```

`sch_check.py rails` fails when the two nets are joined by anything but their one `link_part`.

## firmware.md

`design/firmware.md`: the firmware instructions, the list of what the hardware leaves to firmware. How it is collected: `references/firmware-instructions.md`.

```
# Firmware instructions: <project>
## <module>
can: <signal, net and processor pin>; <meaning>; <range>; <speed>. Source: <sheet, DS-, DC-, calculation or report>. Status: <status>
must: <duty>; reads <the reading it uses>; threshold <value>; respond within <time>. Source: <...>. Status: <status>
## Across modules
must: <a duty that crosses modules>; reads <...>; threshold <...>; respond within <...>. Source: <...>. Status: <status>
```

- One line per item, grouped by module, with one section for duties that cross modules.
- Two kinds of line. "can": a signal the firmware can read or drive, with its meaning, range and speed. "must": a duty, with the reading it uses, its threshold and its response time.
- Each line ends with its source and one of three statuses: `decided with the user (DC-nnn)`; `stated by a worker, not decided`; `missing: <what is missing>`.
- A missing figure is written as missing, never filled in. Where sources disagree, both are listed on the line, each with its place.
- A "must" line that is the only guard of a hardware start-up condition carries the words "only guard at start-up" after its status.

## fab-capabilities.csv

Board house and assembler limits and fees. Every value has a source: a URL and the date read, or "from user". Never from memory.

```
item,manufacturer_value,source_url,read_on,service_level,rule_value,note
min_track,<value>,<page>,<date>,standard,<value>,
pth_annular,<value>,from user,<date>,standard,<value>,
assembly_msl_limit,<value>,<page>,<date>,assembly,,compared with parts.csv msl
assembly_fee_extended_part,<value>,<page>,<date>,assembly,,feeds the cost total
```

`rule_value` is never tighter than the capability allows. `table_check.py fabcap` checks sources and rule values. A table with a header and no rows is listed, and fails from the board checkpoint on (`--stage ST11`).

`project_settings.py` turns the `rule_value` (in mm) of these items into board minimums and rules: min_track, min_clearance, min_via_diameter, min_via_drill, via_annular, pth_annular, min_hole_to_hole, via_hole_clearance, pth_hole_clearance, edge_clearance, silk_clearance, silk_text_height, silk_text_thickness. A missing one keeps KiCad's default and is listed. Other items (assembly limits, fees) are not rules.

## constraints.csv

Placement and routing constraints. Every carried layout row becomes one or more constraints at the board rules stage.

```
id,from,kind,objects,limit,enforced_by,sufficiency,standard_or_own,note
CN-031,DS-031,distance,"<part>; <pin the datasheet names>",<basis stated>,check:distance CN-031,partial; whole with CN-032,datasheet,
CN-032,DS-031,same_island,"<pads the datasheet names>; layer:<layer>",-,check:same_island CN-032,partial; whole with CN-031,datasheet,
CN-040,DC-009,no_vias,"<bus nets>",0,dru:bus-no-vias,whole,own figure,user habit
CN-050,user,clearance,"<battery-side nets>",<value>,dru:netclass Power,whole,own figure,standard not named
CN-060,DS-050,keep_out,"<area the datasheet names, layers>",-,check:keepout CN-060,whole (BR-06-02),datasheet,
CN-070,DS-061,placement,"<parts the datasheet names>",-,review:<checklist ID>,whole with a verdict per row in each board review,datasheet,"no sub-command reads <the datasheet's words>; reviewer measures <what> from the board file"
```

These rows are invented examples of the format, not rules. Which constraints a part needs comes from its own datasheet, read every time; parts differ widely, even within one family.

- `from`: the DS- row, DC- decision, or "user".
- `enforced_by` takes only three forms: `dru:<rule name>` (a rule in the generated rule file), `check:<board_check sub-command> <CN- ID>`, `review:<checklist ID>`. Use `check:` or `dru:` wherever one fits; a `review:` enforcer alone needs the reason in `note`. `table_check.py constraints` checks the rule or check exists, that every `review:` constraint has a verdict in the latest board review report, and that every `review:` constraint has a `note`.
- `sufficiency`: whole, partial or no, with the review that judged it.
- `standard_or_own`: the named standard, "datasheet", or "own figure".
- `objects` of a `dru:` row: net names as in the netlist (a labelled net starts with "/"), joined by ";". `project_settings.py` writes the rules. `dru:netclass <Name>` sets that net class, with kinds clearance, width, via_diameter or via_drill; its objects become the class's net patterns, where wildcards work. `table_check.py constraints` accepts such a row when the class is in the `.kicad_pro` and the rule file holds the class's rule of the row's own kind only: `netclass <Name> clearance` for a clearance row, `netclass <Name> width` for a width row (via rows need the class only). A class that sets a clearance and no width passes. With no rule file (a hand-made project), a `dru:netclass <Name>` row is accepted when the class is in the `.kicad_pro` and its value there reaches the row's limit; the output names these rows, and a clearance carried this way is partial for zones (`references/adapting.md`, Net classes with no rule file). Any other `dru:<rule name>` becomes a rule of that name, with kinds clearance, width, max_length, no_vias, max_vias or creepage, matching exact net names. Another kind with a `dru:` enforcer stops the build: use `check:` or `review:`.
- `objects` of a `check:` row: what the sub-command reads, joined by ";": pads as `U1.3`, parts as `C5`, net names, and keyed items such as `layer:F.Cu`, `zone:<name>`, `area:x1,y1,x2,y2`, `within:<mm>`, `in:U1.3`, `noisy:<net>`, `plane:GND on In1.Cu`. `board_check.py --help` lists which each sub-command takes.

## constraints-reviewed.csv

The sufficiency baseline: each constraint as the last sufficiency review saw it. `table_check.py constraints --record-review BR-nn-nn` writes it, only when the constraints check has no fails. It is a plain file in `design/`, so it works with no git.

```
id,kind,objects,limit,enforced_by,review,date
CN-031,distance,"<part>; <pin>",<value>,check:distance CN-031,BR-07-02,<date>
```

`table_check.py constraints` compares `constraints.csv` with it. A row whose kind, objects, limit or enforcer changed since the review needs a DC- ID in its `note`; without one it is listed, and fails from the board rules checkpoint (`--stage ST7`). Rows added since the review need a sufficiency verdict, and are listed. With no baseline file it says so, and fails from the board checkpoint (`ST11`). Record a new baseline after every sufficiency review.

## findings.csv

Every review finding and side remark.

```
id,report,severity,category,location,text,source,status,decision
FD-017,BR-04-02,3,remark,<block>,"leave a footprint for <the optional part the datasheet shows>",reviewer side remark,open,
FD-021,BR-08-01,2,extraction miss,U1,"<instruction> on page <p> has no DS row",blind board review,rows DS-090 added,
```

`severity`: 1 to 4. `category`: violation, risk, question, improvement, remark, extraction miss. `status`: open, fixed (<build or commit>), decided (DC-), or the action taken. `table_check.py findings` lists any not triaged. The state comes first; a note may follow it ("open; waits on <what>"). A status that starts with "open" is open, and the summary does not count it as triaged. An `extraction miss` is a datasheet instruction with no DS- row: its `location` names the part (designator or MPN) or the datasheet. The summary lists a row of that category that names neither, and does not count it. A side remark is filed with the severity its report gave it, never a guessed one. A finding closed as moot, or as needing no action, says why in `status`.

## net-review.csv

Items from the review lists (`sch_check.py protect`, `opendrain`, `decouple-list`, `unused`, `domains`). Each is closed by a written reason, not pass or fail. Two lines fail in `sch_check.py` until their item is closed here: an open-drain net with no pull, and supply pins with no capacitor to ground.

```
id,list,net_or_pin,item,reason,closed_by,date
NR-004,protect,J2.3,"no protection part between the connector pin and U2","bench-only header (DC-031)",user,<date>
NR-010,decouple-list,+3V3,"U4 supply pins: candidate capacitors on the net",per-pin check on the board (CN-070),worker,<date>
```

## checklists

`design/checklists/logical.md`, `electrical.md`, `board.md`, `packs.md`, `fabrication.md`, `repository.md`: copies of the skill's starting checklists (`references/checklist-*.md`) and packs, made at setup and grown per project. `table_check.py summary` counts the six. Each item keeps its ID, what to check, the authority, the stage, any script and its switch. Each review writes its result per item in its report, as the ID and then the result: `BD-07: met`, `BD-07, BD-08: met`, or a table row with the ID in the first cell and the result in a later one. The results are met, not met, does not apply and cannot tell. `table_check.py checklists` reads only this form; a report that names an item for another reason gives it no result. Accepted checklist additions go in with the same six fields.

## reports

`design/reports/BR-<sprint>-<n>.md`, one per brief, in the format in the skill file (section 6). Never edit an old report; a correction is a new report. An old report is a record, not a source: figures are taken from the current design files.

## progress files

`design/progress/BR-<sprint>-<n>.md`: the short progress file of a long worker job. The worker rewrites it as it goes, so the coordinator can read how far the job is without stopping it, and so an interrupted job can be picked up.

```
# Progress BR-<sprint>-<n>
Updated: <date and time>
Done: <steps finished, one line each>
Now: <the step in hand, and since when>
Left: <steps to come>
Files written so far: <paths>
Stopped by: <nothing, or what stopped the job>
```

It is replaced by the report when the job ends, and may then be deleted.

## test-sweep.md

`design/test-sweep.md`: the output of the test sweep at the end of the schematic stage.

```
# Test sweep: <project>, netlist build <hash or commit>
## <module>
<what must be tested>; <how: test point, signal or fixture>; <pass limit and its source>; <covered | not covered: what is missing>
## Not covered
<each requirement or duty with no test, and why>
```

## calcs

`design/calcs/` is the one calculations folder. Generators and sheet comments read their values from it, so a value is worked out in one place and never typed again on a sheet.

`design/calcs/<block>_<what>.py` and its output `design/calcs/<block>_<what>.txt`. Worst-case scripts, one per threshold, divider, timing network, current limit or budget. Standard library only, so they run anywhere. Use the helpers in `worstcase.py` where present. Every input cites its source.

```python
"""Worst case: <what>. Serves: <FR-/QC- IDs>. Rows: <DS- IDs>."""
import itertools

# name: (min, nominal, max), source
INPUTS = {
    "r_top": (0.99 * 100e3, 100e3, 1.01 * 100e3),   # <part>, 1 %, parts.csv
    "v_ref": (0.788, 0.800, 0.812),                   # <datasheet> <section> <table>, p <n>
}
LIMIT = (<low>, <high>)                               # <source>
LEFT_OUT = ["<each term the equation leaves out, for example a leakage or a temperature drift>"]

def result(v):
    return <equation, with its source in a comment>

corners = [dict(zip(INPUTS, c)) for c in itertools.product(*[(a, c) for a, _, c in INPUTS.values()])]
values = [result(c) for c in corners]
nominal = result({k: n for k, (_, n, _) in INPUTS.items()})
low, high = min(values), max(values)
print("min %.4g  nominal %.4g  max %.4g  limit %s" % (low, nominal, high, LIMIT))
assert LIMIT[0] <= low and high <= LIMIT[1], "outside the limit"
```

The values in the example are placeholders. Extreme-value corners are the default. A seeded Monte Carlo run is added when the user asks, with the seed printed. A `worstcase.py` result lists the terms it left out, which the calc script names in `LEFT_OUT = ["<term>", ...]`; carry that list to wherever the result is used. Simulation files do not go in this folder. They live in `sim/` (`references/simulation.md`, Where files live).

## sim-models.csv

`design/sim-models.csv`: the model table, one row per simulated part. How it is used: `references/simulation.md` (Model table, Models, Model check).

```
mpn,model_file,model_name,kind,pin_order,source,fetched,sha256,licence,checked,evidence
<mpn>,sim/models/<file>,<name of the model in the file>,maker,<symbol pin for each model pin, in the model's order, joined by ";">,<URL>,<date>,<sha256>,<licence terms, in short>,<yes | no>,<model check output file or report>
<mpn>,sim/models/<file>,<name>,stand-in,<...>,written from <datasheet> <sections>,<date>,<sha256>,own,<yes | no>,<...>
```

`kind` is maker or stand-in. `pin_order` maps the model's pins to the symbol's pins. `sha256` is the checksum of the model file as it is used. `spice.py netlist` stops on a simulated part with no row. These are not the `model` columns of `parts.csv`, which are 3D models.

## scenarios.csv

`sim/<module>/scenarios.csv`: the scenarios, corners and pass limits of one module, as data that `spice.py run` reads. How it is used: `references/simulation.md` (Scenarios).

```
id,scenario,corner,setup,measure,limit_low,limit_high,source
<S01>,<normal start-up>,<nominal>,<sources, loads and timing set up>,<what is measured, where and when>,<low>,<high>,<FR-, QC-, DS- or the calculation the limits come from>
```

One row per scenario and corner. A limit with no source is not a pass limit. The module's edge-case list is `sim/<module>/edge-cases.md`, under four headings: what people do by mistake; heat and cold; vibration and loose contacts; harmonics or ringing.

## build.json

`design/build.json`: the project's build settings, read by `build.py`. Nothing is edited inside the copied build script.

```
{
  "project": "<KiCad project name>",
  "order_folder": "<folder for order files>",
  "order_options": [],
  "checks": ["python3 scripts/checks/<check>.py"]
}
```

`checks` is the list of this project's own check commands, kept in the folder `checks` under `scripts` at the project root. The build runs them after the shipped checks, and a check that fails stops the build.

## ownership.csv

Every design file: who owns it, and the hash of the bytes a script last wrote.

```
path,owner,writer,hash,commit
hardware/<project>.kicad_sch,script,gen_sch.py (sch),<sha256>,<commit>
hardware/<project>.kicad_pcb,hand,,,<commit when it became hand-owned>
hardware/<project>.kicad_dru,script,gen_pcb.py (board),<sha256>,<commit>
```

`owner`: script or hand. `writer`: the script and the `build.py` stage that write the file, or `<command> (own build)` for a project's own generator. A design file with no row is hand-owned. Exports (the netlist and the BOM) are not design files: they are written again by every `build.py netlist` and `bom` and never protected. When a generator fails after writing, the files it wrote are still recorded as its output, so the next run is not blocked by them. `build.py` updates `hash` after each script write. How it is used: `references/adapting.md`. `path` is relative to the project root: `hardware/<project>.kicad_pcb`, or `<project>.kicad_pcb` when the KiCad files sit in the root (`KiCad folder: .` in `design/status.md`).

## passes

`design/passes/` holds staging files while datasheet passes run at the same time: `<MPN>_<perspective>.csv` (compliance columns, `id` as `<perspective>-<n>`), `<MPN>_<perspective>_sections.csv` (sections columns) and `<MPN>_<perspective>_findings.csv` (findings columns, `id` as `<perspective>-F<n>`). Files are named by MPN because designators may not exist yet. Each pass writes only its own three files, never `pins.csv`, `parts.csv` or any main table: pin limits and package data go in its report and its staged rows, and the merge writes the main tables. The sections file starts as a copy of the datasheet's whole inventory from `design/sections.csv`; the pass fills its own claims. Zoom renders a pass makes go in `design/passes/zoom/` (below). The merge brief copies them into the main tables with the next free DS- and FD- IDs, lists the provisional IDs beside the new ones in its report, and deletes the staging files (`references/datasheets.md`, Merging passes).

## renders

`design/renders/<datasheet>_p<page>.png`: every page of each datasheet and delegated document, rendered once by the fetch brief (`<datasheet>` is the file name in `datasheets/` without `.pdf`; any character a file name cannot hold replaced by "-"). Passes read them and never write here. A pass that needs a larger render of a small figure makes it in `design/passes/zoom/<datasheet>_p<page>_<perspective>.png`; the merge deletes that folder. The fetch lists the pages with no text layer (scanned pages): passes read those from the renders. After the merge, the pages behind figure and graph rows are kept, so a reviewer can check the reading; the others are deleted, since they can be made again from the saved PDF. `table_check.py compliance` checks that a render exists for every figure and graph row, and lists the renders no row cites.

## briefs

`design/briefs/BR-<sprint>-<n>.md`: one brief per file, written by the coordinator before the worker starts. A brief file holds that worker's brief and nothing else: never another worker's brief, and never the coordinator's notes. Paths in it are relative to the project root; the coordinator gives the project root and the skill's location in the message that starts the worker, never in the file, so the brief passes the confidentiality scan. The sprint file lists the brief IDs.

The allowed-writes list of a brief covers every file the task must produce: the index row and extract that go with a saved document, the table and pin rows that go with a new part or net, every sheet that holds the kind of thing being fixed, and the worker's own rows file. A worker that finds the list too narrow stops and says so; it does not write outside it. Build work on modules is serial. A read-only brief may run beside a build brief; each worker that runs beside another has its own folder in the scratch folder, `.hwtmp/BR-<sprint>-<n>/`.

## .private-terms

`design/.private-terms`: one term per line, words the confidentiality scan must find (client names, project code names, account names). It is git-ignored at setup and never committed. `table_check.py scan` reads it.

## scan-reviewed.csv

`design/scan-reviewed.csv`: scan findings the user looked at and accepted. It is committed.

```
file,line,kind,reason,decided_by
<file as the scan printed it>,<line>,machine path,"<why it may stay>",user
```

`kind` is the kind the scan printed. `table_check.py scan` lists a matching finding as reviewed and does not fail on it. A row with no reason or no `decided_by` fails. So does a row that matches nothing in a file the scan read: remove it, or give the new line.
