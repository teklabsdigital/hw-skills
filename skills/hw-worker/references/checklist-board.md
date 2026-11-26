# Board checklist

The starting checklist for the physical design: rules, placement, routing and the finished board. Apply it while the board is built (ST7 to ST10) and in full in every board review (ST11), with the switched-on packs in `references/packs.md`. The logical and electrical checklists are `references/checklist-logical.md` and `references/checklist-electrical.md`.

## How to use it

- Pin assignment is item one of every review: BD-01 comes first, for every part, not only ICs.
- Apply every item. Give each a result in your report: met, not met, does not apply (with the reason), or cannot tell (with what would tell). A "does not apply" or "not met" on a layout or grounding matter is proposed, never decided by you (WR-21).
- **What to check** names the sensitive area and the question. It never gives the layout rule or a distance. The rule comes from this part's datasheet and the documents it delegates to, quoted, every time (WR-19). Where the datasheet is silent, follow WR-20.
- **Authority**, **Stage**, **Script** and **Switch** work as in the logical checklist. Board checks are `board_check.py` sub-commands, each run against a CN- constraint. The aids (`copper_area`, `loop_area`, `node_capacitance`) print numbers for you to compare with the datasheet; they never pass or fail on their own. Switch names are in `references/packs.md` (Board-type switches).
- A constraint enforced by `review:<ID>` needs your per-row verdict in report section 6: met, not met, or cannot tell, with evidence.
- A render is an aid for the engineer, never a check (WR-02).
- Use the project's copy in `design/checklists/board.md`. It may have grown.

## Living document: adding and retiring items

- **Adding.** Anyone may propose an item: a worker in report section 12, a reviewer, or the user. A proposal has all six fields. The coordinator puts it to the user. An accepted item goes into the project's copy with the next free number in this list, and keeps that ID for good. An item that looks useful for every board may be offered to the user as feedback for the skills; it is never sent automatically. In the skill's own copy, a new item also takes the next free ID.
- **Retiring.** An item is never deleted and its ID is never reused, so old reports still resolve. To retire one, keep the row and start its "What to check" cell with "Retired <date>: <reason>; see <new ID>". Retire an item only when another item covers all of it, or its authority no longer exists. In a project copy, the user decides. An item that does not fit one board is not retired; it is marked "does not apply" with a reason in that review.

## Pins, footprints and models

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| BD-01 | Pin item one at board level. Pads against the package drawing of the exact part ordered: pin 1, top or bottom view, mirroring and rotation, exposed pad, pad numbering. Land pattern against the datasheet's suggested pad layout, dimension by dimension. Polarity of diodes, LEDs and polarised capacitors. Pin order of small transistors and regulators, which differs between makers for one package. Connector numbering and mirroring against the mating part. Fine-pitch and BGA land patterns, and how they will be inspected | the package drawing for the MPN; the mating part's drawing | ST9, ST11 | none | always; more under Fast digital |
| BD-23 | Every part has a 3D model, or a waiver. The engineer signs off the placement in 3D before routing | `design/parts.csv` `model`; `design/decisions.md` | ST9 | `pcblib.py` (model check) | always |
| BD-36 | 3D model correctness: height, offset and rotation against the part drawing, checked in code, not by a render | the package drawing | ST9 | none (`design/parts.csv` `model_checked`) | always |

## Rules and constraints

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| BD-39 | Every rule value comes from the manufacturer's published capabilities for the chosen service level, with its page and date; none is tighter than the manufacturer can build; none is from memory | the manufacturer's capability pages, fetched; the user if a value cannot be found | ST7 | `table_check.py fabcap` | always |
| BD-19 | Every design-intent constraint (datasheet rows, user habits, decisions) is enforced by a rule, a check or a review verdict. Design intent never lives only in how a generator places and routes | `design/constraints.csv` | ST7, ST11 | `table_check.py constraints` | always |
| BD-02 | Every carried DS- layout and grounding row has a board result, checked against the datasheet page itself, not only against its constraint | `design/compliance.csv`; the datasheet layout pages | ST11 | `table_check.py compliance` | always |
| BD-10 | Clearance and creepage for each voltage pair, with the named standard, pollution degree and coating, or recorded as "own figure" and an open question | the named standard, fetched; the product safety standard where one applies | ST7 | none (`dru:` rules in the rule file) | always; more under Ethernet, Mains |
| BD-26 | Plane links (a pad's short track to its plane via) have a default minimum width rule, so thin links cannot slip through | datasheets; the user | ST7, ST10 | none (`dru:` rule) | always |
| BD-35 | No DRC check suppressed without a decision: lowered severities, exclusions, rule exceptions | the KiCad defaults file; `design/decisions.md` | ST7, ST11 | `table_check.py suppress` | always |
| BD-28 | DRC: 0 violations and 0 unconnected items, or each waived. Zones re-poured by the tool that applies the custom rules. Schematic parity items only those listed with a decision | the rule file; `design/status.md` | ST10 | `pcblib.py` (DRC with re-pour) | always |

## Placement

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| BD-32 | Placement by functional block. Support parts sit at the pins they serve (decoupling, pulls, filters), never parked in rows away from them. The user's own placement habits kept | the user; datasheets | ST9 | `board_check.py distance` | always |
| BD-03 | Each switching converter laid out as its datasheet says: apply pack SC, row by row | the converter's datasheet and its delegated layout documents | ST9 to ST11 | `board_check.py` per CN- | Switching converter |
| BD-04 | Feedback networks and other sensitive nodes placed and routed as this part's datasheet says, every time. There is no general rule | datasheets | ST9, ST10 | `board_check.py net_length`, `board_check.py noisy_distance` | always |
| BD-05 | Crystal or oscillator and its capacitors placed and routed as the crystal, oscillator and controller datasheets say; the clock net length carried to a constraint | datasheets; the vendor's crystal application note | ST9 | `board_check.py distance`, `board_check.py net_length` | always |
| BD-06 | Decoupling per supply pin: capacitor distance and via count as each datasheet asks (some ask for a minimum number of vias on bypass and protection parts) | datasheets | ST9 to ST11 | `board_check.py decouple_per_pin`, `board_check.py via_count` | always |
| BD-15 | Protection parts as their datasheets say: at the connector, in the direction of the signal path so the transient reaches the protection first, short path to the protected line, small loop and short transient return, no protected conductor running parallel to an unprotected one, the via count the datasheet asks | protection and interface datasheets, layout sections | ST9, ST10 | `board_check.py distance`, `board_check.py via_count`; `loop_area` (aid) | always |
| BD-16 | Analog and sensitive areas kept apart from switching and digital areas; their ground return arranged as the datasheets say | ADC, reference and sensor datasheets | ST9 | `board_check.py noisy_distance` | always; more under Analog |
| BD-14 | Antenna position, keep-out on every layer and ground stitching as the module guide says, and the certification conditions that depend on them. Any trade-off with user-facing parts is a decision | the module's hardware design guide; the certification grant conditions | ST8, ST9 | `board_check.py keepout` | Radio |
| BD-12 | Heat: thermal vias under exposed pads (count, drill, treatment) as the datasheet says; thermal relief where hand soldering needs it, solid where current or heat needs it; equal heat paths on both pads of small passives so they do not tombstone; hot parts away from temperature-sensitive parts (crystals, references, electrolytic capacitors, batteries, sensors) | datasheet thermal and package sections; assembler guidance | ST9, ST10 | `board_check.py via_count`; `copper_area` (aid) | always; more under Switching converter, Analog, Enclosure |
| BD-22 | Assembly: rework and iron access; tall parts shadowing small ones; access for hand-soldered through-hole parts; polarised parts in one direction where possible; pin 1, cathode, plus and connector pin 1 marks visible after assembly, not under the body; global and local fiducials and tooling holes as the assembler requires; test point access (probe side, spacing, clearance from tall parts) | the assembler's capability pages; test-house guidance; the user's tools | ST8, ST9, ST11 | none | always |

## Mechanical

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| BD-20 | Copper and parts clear of edges, break lines, slots and holes. Mounting holes: keep-out for screw heads and standoffs, plated or not, grounded or not. Finished hole sizes against lead sizes as the part drawing recommends, with the drill tolerance | the manufacturer's capabilities; part and fastener drawings; the enclosure drawing | ST8 | `board_check.py edge_distance`; `dru:` rules | always; more under Enclosure |
| BD-21 | Mechanical stress and fit: ceramic capacitors away from edges, break lines, screws and connectors that take force, and oriented along the bend line; support for heavy parts under vibration; connector overhang, mating clearance and height limits; a 3D fit check against the enclosure model offered | the capacitor maker's handling notes; connector drawings; the enclosure model | ST8, ST9 | `board_check.py edge_distance` (by dielectric) | always; more under Vehicle, Cables, Enclosure |
| BD-37 | Light pipes and button caps line up with the enclosure's features | the enclosure model; the light pipe or cap drawing | ST8, ST9 | none | Enclosure |
| BD-38 | Copper balance and warp on thin or large boards | the manufacturer's guidance | ST10, ST11 | `copper_area` (aid) | always |
| BD-42 | Outline export for whoever designs the enclosure, if the user asked for one: the outline, holes and user-facing part positions exported again whenever any of them moves, and the report says which export is current | the user's request at the physical definition; the enclosure designer's stated needs | ST8, ST9, ST11 | none | always; more under Enclosure |

## Routing, planes and vias

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| BD-18 | Routing guidelines kept or bent with the reason given: power paths first, each block routed internally before blocks are joined, one direction per layer, power on inner layers (planes; inner-layer tracks are a known router limit), few vias, the user's habits (for example no vias on a bus) | the user's guidelines in `design/status.md` | ST10 | none | always |
| BD-09 | Track and via current by calculation: temperature rise, copper weight, inner against outer layers, via current, plane necks, with the method named and fetched. Power paths routed first with those widths. No width steps on power nets | a published calculation method or the manufacturer's calculator, fetched | ST7, ST10 | `board_check.py artefacts`; `dru:` width rules | always; more under Motors |
| BD-07 | Return paths: no signal crosses a gap in its reference plane; a return via or capacitor near each layer change between different references; no shared return path where a datasheet says to avoid one | datasheets; interface and vendor layout guides | ST10 | `board_check.py ref_plane` | always; more under Fast digital |
| BD-08 | No isolated copper islands or slivers; each plane in one piece | the manufacturer's minimum copper feature | ST10 | `board_check.py plane_one_piece` | always |
| BD-11 | Vias: in pad, tented, plugged or filled as the package drawing and the assembler require; via position relative to the pad; every via to the manufacturer's specification, and as few as the design allows | package drawing notes; the assembler's and manufacturer's via options | ST10 | `board_check.py via_in_pad`, `board_check.py via_count` | always |
| BD-13 | Paste and mask: paste on exposed pads split as the package drawing says; reduced paste on large pads; no paste over open vias; stencil thickness suits the finest pitch; mask webs between fine-pitch pads; mask expansion; mask-defined pads where the package asks | package land-pattern notes; the manufacturer's and assembler's stencil guidance | ST10 | none | always |
| BD-17 | Fast interfaces: length matching, pairs (spacing, matching within and between pairs, symmetric vias), impedance per interface with geometry from the manufacturer's calculator for the named stack-up, impedance control on the order, crosstalk spacing and parallel length between aggressors and victims | the interface specification; the chip vendor's layout guide; the manufacturer's stack-up page and calculator | ST7, ST10 | `board_check.py net_length` | always; more under USB, Ethernet, Fast digital |
| BD-29 | Kelvin and remote sense: sense tracks leave the shunt or load pads at the points the datasheet shows. High-voltage and isolation routing: spacing on every layer, slots under the barrier, no copper across it | current-sense and regulator datasheets; the product safety standard, fetched | ST10 | none | always; more under Ethernet, Motors, Mains |
| BD-27 | EMC layout: loop areas, fast signals near edges, slots under fast signals, filters at the connector entry, cable shields, plane and board-edge stitching | datasheets; the vendors' EMC guidance; the market's EMC standard if sold, fetched | ST11 | `loop_area` (aid) | always |
| BD-24 | Silkscreen: no overlap with pads or other text, size at or above the manufacturer's minimum, each label clearly next to its part, all on the board | the manufacturer's minimums | ST10 | `pcblib.py` (labels) | always |
| BD-41 | Silkscreen content against the plan agreed at the physical definition: connector labels, what each LED and button means, polarity and pin-1 marks, the revision mark, and anything else the user asked to print. Each planned item is on the board, next to what it names, and readable after assembly. Size and overlap are BD-24 | the silkscreen content plan the user agreed; the user | ST8, ST11 | none | always |
| BD-25 | Routing artefacts measured, not only looked at: width steps on power nets, dog-legs, odd joins between neighbouring pads, dangling ends and unused vias, starved thermal connections, doubled stubs; the board not empty and unrouted nets counted | the rule file; the user's routing guidelines in `design/status.md` | ST10 | `board_check.py artefacts` | always |

## Review and done

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| BD-40 | The board gets its own review by a worker who did not build it. A blind board review is offered, with the datasheets and without `design/compliance.csv`; anything it finds with no DS- row is logged as an extraction miss | `references/review.md` | ST11 | none | always |
| BD-34 | Layout differences from the evaluation board's layout and the datasheet's layout example, each a row with a reason | the evaluation board guide; the datasheet layout example | ST11 | none | always |
| BD-33 | Thermal estimate redone after any layout change near a hot part | datasheet thermal information | ST11 | `worstcase.py`; `copper_area` (aid) | always |
| BD-31 | Anything changed since the review baseline re-reviewed | the baselines in `design/status.md` | ST11 | `table_check.py summary` | always |
| BD-30 | Known improvements listed before "done"; a clean DRC is not done | the worker's list of known defects and improvements (WR-08) | ST10 | none | always |
