# Board

Procedures for the physical design: board rules (ST7), physical definition (ST8), placement and 3D sign-off (ST9) and routing (ST10). For a board the engineer placed or edited by hand, also read `references/adapting.md`.

The normal order is rules, then physical definition, then placement, then routing. Rules come before any placement, because the datasheet layout rows must be constraints before parts are put down.

## Contents

Rules; Constraints; Constraint sufficiency; Physical definition; Board generator; Placement; 3D sign-off; Routing; Planes and vias; Router; DRC and layout checks; Artefacts; Improvements before done.

## Rules

1. **Manufacturer capabilities.** For the manufacturer and service level the user chose, fill `design/fab-capabilities.csv` from the manufacturer's own published pages: track and space, drill and annular ring for vias and plated holes, via types, board thickness, copper weights, the named stack-up with its dielectric thicknesses and constants, solder mask and silkscreen minimums, edge and slot clearances, and the assembler's limits (moisture level, peak reflow, part classes, fees). Every value has its URL and the date read. If a value cannot be found, ask the user; never fill it from memory (an earlier board's plated-hole ring limit was written from memory and never checked).
2. **Rule values.** Each rule value is at or above the capability, never tighter than the manufacturer can build. Note where the design uses a more generous value and why.
3. **Clearances.** Every clearance and creepage value names its standard (fetched and cited) or says "own figure". A user's "must be compliant" needs the standard named; until it is, the value is "own figure" and an open question.
4. **Generated files.** The rule file (`.kicad_dru`) and the project file (`.kicad_pro`) are written whole by `project_settings.py` from `design/fab-capabilities.csv` and `design/constraints.csv`, starting from `kicad_pro_defaults.json`. A setting changed in the KiCad editor is overwritten by the next build, so every setting the design depends on belongs in the tables.
5. **Severities.** Start from the raised list in `project_settings.py`, where checks such as dangling vias and starved thermal connections are errors, not warnings. Lowering any severity, adding an exclusion or a rule exception is a decision (DC-). `table_check.py suppress` reports any without one. A hand-owned project file left at KiCad's own board severities (an adopted project) is listed with the recommended values, not failed, until the board checkpoint (`--stage ST11`); put the choice to the user as `references/adapting.md` (Adopting an existing project, step 5) says.
6. **Constraints.** Write every carried DS- layout and grounding row into `design/constraints.csv` (Constraints, below) before reporting, with its `carried_to` filled in `design/compliance.csv`.
7. **Checks.** Run `table_check.py fabcap`, `table_check.py constraints` and `table_check.py suppress`; give their output.
8. **Report** the capability table with its sources, the constraints by enforcer (how many by rule, by check, by a reviewer's verdict alone), and the constraint-sufficiency verdicts.

## Constraints

`design/constraints.csv` (template in `references/project-files.md`) holds every placement and routing constraint:

- every carried DS- layout and grounding row, as one or more constraints (`from` = the DS- ID);
- every design-intent rule the user or a decision set (for example no vias on a bus, a clearance class for battery-side nets);
- every user habit from `design/status.md` that the board must keep;
- a default minimum width for plane links (short tracks from a pad to its plane via), so thin links cannot slip through.

Each constraint has exactly one enforcer:

- `dru:<rule name>`: a rule in the generated rule file (clearance, width, length, via count on a net class or net);
- `check:<board_check sub-command> <CN- ID>`: a board check that can fail. Sub-commands: `distance`, `same_island`, `single_point`, `plane_one_piece`, `via_count` (with via position relative to the pad), `keepout`, `net_length`, `noisy_distance`, `decouple_per_pin`, `edge_distance` (by dielectric), `ref_plane`, `via_in_pad`, `artefacts`;
- `review:<checklist ID>`: a verdict the board reviewer must give for this constraint in every board review.

Use a `check:` or `dru:` enforcer wherever a sub-command or rule fits. Use `review:` alone only with a written reason in `note` why no script fits; the sufficiency reviewer checks that reason. If `board_check.py` is not yet in the project's `hwskills/` folder, still write the `check:` enforcer: the check is then done by hand and listed under "Not verified" until the script exists. None of this stops the work. The report says plainly how many constraints rest on a reviewer's verdict alone, and the user decides whether that is enough.

The aids `copper_area`, `loop_area` and `node_capacitance` print numbers for a reviewer. They are never an enforcer on their own: a constraint that relies on one is enforced by `review:`, and the reviewer compares the number with the datasheet.

Design intent must live in constraints, not only in how a generator happens to place and route. On an earlier board, "no vias on the bus", a battery-side minimum width and the converter keep-outs were router behaviour only; a hand edit or a fallback route would not have been caught.

## Constraint sufficiency

A review worker, not the worker who wrote the constraints, judges each carried row:

1. Read the row's quoted text, and the datasheet page it came from.
2. Read the constraints that carry it, with their enforcers.
3. Ask: if every one of these passes, is the whole quoted text met? Verdict: whole, partial or no, with the reason.
4. Watch for constraints that test something nearby instead of the instruction itself. A check that two pads share one copper area says nothing about how that area meets the rest of the board; a check of distance says nothing about which layer or side a part is on. "Within 3 mm" is a proxy for "as close as possible": state the number, its basis (the datasheet's layout example, the package size), and pair it with a `review:` verdict against the datasheet figure.
5. Partial or no: propose more constraints, preferring a `check:` or `dru:` enforcer; a `review:` enforcer only where no script fits, with the reason.
6. A `review:` enforcer with no written reason, where a sub-command could check the text, gets the verdict "partial".
7. Write the verdicts into the `sufficiency` column with your report ID.
8. Record the baseline: `python3 hwskills/table_check.py constraints --project <root> --record-review <your report ID>`. It writes `design/constraints-reviewed.csv` only when the check has no fails. From then on, a constraint whose kind, objects, limit or enforcer changes needs a DC- ID in its `note`, or it is listed, and fails from the board rules checkpoint (`--stage ST7`). A limit loosened after a check failed is exactly what this catches. The baseline is a plain file, so it works with no git.

The user sees the verdicts in plain English, not the raw table.

## Physical definition

From the user's answers (asked by the coordinator) put into the board:

- outline, size, thickness and orientation; which end faces the user;
- mounting holes (keep-out, plating, grounding), slots and cut-outs, edge keep-outs;
- the enclosure, from its drawing or 3D model; light pipes and button caps aligned with its features;
- fixed parts: connectors and their mating parts, headers and their pitch, where power enters, battery holders, LEDs and their sizes and colours, buttons;
- the antenna position and its keep-out, from the module's own placement guide (a delegated document; WR-17);
- fiducials and tooling holes, if the board is machine-assembled, as the assembler's own pages ask (panel rails are FB-08);
- the silkscreen content plan agreed with the user: connector labels, what each LED and button means, polarity and pin-1 marks, the revision mark, anything else the user wants printed. The board review checks the board against it.

If the enclosure is unknown, the shape is provisional: say so in the report. Never give up a keep-out the datasheet or module guide asks for to fit something else without saying so; put the trade-off to the user as a decision (an earlier board gave up an antenna clear zone to fit LEDs and a button, and reported it only in passing).

If the user asked for it, export the outline, holes and part positions as STEP or DXF for whoever designs the enclosure, with `kicad-cli pcb export` (check its help in the installed version for the options). Export again whenever the outline or a user-facing part moves, and say so in the report.

Report with a rendered view (an aid, not a check).

## Board generator

For a new board that will be script-owned, the first board build writes the project's board generator, `gen_pcb.py` in the project's own `scripts` folder, before placement. It builds on the skill's `pcblib.py`, imported from `hwskills/`, where that exists; if it is not there, say so and write only what the brief covers.

1. Inputs: the netlist from `build.py netlist`, `design/parts.csv`, `design/constraints.csv` and the physical definition. Never the schematic generator's internals.
2. Stages that can run alone: rules and project file (through `project_settings.py`), outline and fixed parts, placement (positions in one table in the script, by block), routing, re-pour and checks.
3. Repeatable: a seeded ID generator, so two builds give the same bytes (`references/tooling.md`, Repeatability).
4. Design intent lives in `design/constraints.csv`, not only in the script (Constraints, above).
5. Record the board, rule file and project file in `design/ownership.csv` as script-owned, with `gen_pcb.py` as writer.
6. Verify: build twice and compare the bytes; DRC with re-pour; the board checks. Give the output.

A hand-owned board gets no generator unless the user asks for one in a sprint of its own (`references/adapting.md`).

## Placement

1. Place by functional block. Each block's parts sit together, in the order its datasheet's layout guidance gives.
2. For each switching converter, find the hot loop or loops in its datasheet first and place those parts first, as the datasheet shows them. Then the ground scheme the datasheet describes, then the sensitive nodes it names.
3. Support parts sit at the pins they serve: decoupling at its supply pin, pulls at their pin, the crystal or oscillator and its capacitors as their datasheets say. Do not park pull resistors in a row away from their pins, unless the datasheet or the bus specification places them elsewhere (for example at one end of a bus).
4. Feedback networks and other sensitive nodes: place them as this part's datasheet says, every time (WR-19). There is no general rule here.
5. Apply every placement constraint. The user's own placement habits from `design/status.md` apply too.
6. Every part has its 3D model, checked for height, offset and rotation against the part drawing (`model_checked` in `design/parts.csv`), or a waiver. A render is not a model check: check that the model file exists and its offset and rotation, in code.
7. Run courtyard DRC and `board_check.py` for the placement constraints. Give the output.
8. A rat's nest is fine. Do not route.

## 3D sign-off

The engineer signs off the placement in 3D before routing.

- Render top, bottom and angled views with every model shown.
- List the user-facing and mechanical parts with their positions: LEDs, buttons, antenna, connectors, headers, holes.
- Say what is provisional (shape, enclosure fit).
- After sign-off, changes are still normal; a routing rebuild is cheap. Record a lost sign-off when placement changes.

## Routing

Confirm the routing guidelines in `design/status.md`. The usual set, which "may be bent":

- power paths first, widths sized for the load by a cited calculation method;
- each block routed internally before blocks are joined (except the main input and output power paths);
- then analog and sensitive inputs, crystals and clocks;
- then buses, longest first, with length matching and impedance control where the bus speed needs it, on the named stack-up;
- one direction per outer layer;
- power on inner layers, which here means planes: the router uses only the two outer layers, so inner-layer tracks are a known limit;
- no isolated copper islands;
- few vias, all to the manufacturer's specification;
- return paths checked: an unbroken reference under each fast signal, stitching where it changes layer.

Where you bend a guideline, say where and why in the report's Deviations section. Never let a bend break a constraint without a decision.

## Planes and vias

- Ground and supply planes on inner layers where the stack-up has them. Each plane in one piece (`board_check plane_one_piece`).
- Converter grounding: build exactly what this part's datasheet and the documents it delegates to say. Converters differ widely here, even within one maker's family. Quote the instruction in the constraint. The datasheet decides, not habit (WR-20).
- Plane links: short, at least the default link width, vias placed relative to the pad as the datasheet and assembler allow. Vias may sit under parts unless a datasheet says otherwise.
- Via counts per pad where a datasheet asks (for example "at least two vias" for a bypass capacitor or protection part): a `via_count` constraint.
- Via in pad, tenting and plugging as the package drawing and assembler require (`via_in_pad`).
- Thermal vias under exposed pads as the datasheet asks.
- Inner-plane link tracks are allowed where they make no islands, but the router cannot make them today. If one is needed, propose it to the engineer as a hand edit or report it as a bent guideline.
- A failed plane connection makes the router route the plane net as ordinary tracks, and the board fills with them. If track length jumps, check the plane drops; fix the drop, never accept the result.

## Router

The grid router is the standard method, strongly recommended: it makes re-routing after a change fast. It is a separate library, cloned and built at a pinned commit or tag with the user's approval (`references/tooling.md`). `pcblib.py` is the glue between the board and the router.

- Tracks enter pads at the pad centre, so neighbouring pads join with a straight line, not a Z, unless a datasheet asks for a specific entry (a sense or Kelvin connection); make that a constraint.
- Diagonal steps cost less than wrong-way steps, so 45-degree segments are preferred over dog-legs.
- Clearance classes (for example a wider clearance on the nets a constraint sets apart) are kept by widening the obstacle while those nets route.
- A refine pass lifts each net in turn, routes it again in several ways, and keeps the new route only if it has fewer vias or less track. Run it for a second quality pass instead of ripping everything up.
- A prune step removes dangling stubs and unused vias.
- Long runs: set a time budget and report progress (`references/tooling.md`, Long runs).
- For a board the engineer placed by hand, use the placed-board driver (`references/adapting.md`, Routing a hand-placed board).

## DRC and layout checks

1. Re-pour zones with `kicad-cli pcb drc --refill-zones --save-board`, never with the Python filler alone: the Python filler ignores the custom rules (`references/tooling.md`, Two fill engines). On a hand-owned board, do this on a copy.
2. Expected: 0 violations, 0 unconnected items, and no schematic parity items other than those listed in `design/status.md` with their decisions. Anything else is a violation, or a waiver (DC-).
3. Run `board_check.py` for every `check:` constraint. Each prints pass or fail per CN-. Run the aids for the reviewer. If the script is not in `hwskills/`, check by hand from the board file, give the measurements or coordinates, and list each result under "Not verified".
4. Check the board is not empty and count unrouted nets.
5. Fill `board_result` in `design/compliance.csv` for each carried row whose constraints were all checked; rows with a `review:` enforcer wait for the board review.

## Artefacts

Measure the routed board for routing artefacts before anyone looks at it (`board_check artefacts`):

- track width steps on power nets (a wide track that narrows and widens again);
- dog-legs and needless bends;
- odd joins between neighbouring pads (a Z where a straight line fits);
- dangling track ends and unused vias;
- starved thermal connections;
- doubled stubs on one pad.

Then render the board for the engineer. The render is an aid; the measurement is the check. On an earlier board only the human looked, and found width steps, dog-legs and an empty board in screenshots.

## Improvements before done

A clean DRC is not "done". Before you report done:

1. List every known defect and improvement: thin links, long nets with many vias, a bus with vias where it should have none, an unchecked datasheet row, a bent guideline that could be straightened.
2. Fix those the brief covers.
3. Hand the rest over in the report, each with its cost and benefit.
