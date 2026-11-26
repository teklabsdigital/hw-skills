# Packs

A pack names the areas where boards of one type fail. It never gives the rule (WR-19). For every pack item the authority is the part's own datasheet and the documents it delegates to (evaluation board guide, layout application note, module design guide), read now. You write DS- rows from them, carry the layout rows to constraints, and the check in the Script column applies once a row exists. A pack item with no row is a gap in the datasheet pass, not a pass.

Packs are applied with the checklists: `references/checklist-logical.md`, `references/checklist-electrical.md` and `references/checklist-board.md`. The project's copy is `design/checklists/packs.md`; use it, since it may have grown.

## Contents

How a pack switches on; Board-type switches; How to use a pack; Adding and retiring items; SC Switching converter; Worked example: the method on an invented part; RM Radio; VB Vehicle supply and bus; Guide-sourced packs (GS-USB, GS-ETH, GS-BAT, GS-MOT, GS-MAINS, GS-ANA, GS-FAST, GS-IND, GS-RAIL, GS-SEC).

## How a pack switches on

- From the user's answers: the coordinator infers the board-type switches in the first session, and the user confirms them.
- From part choice: a part whose `category` in `design/parts.csv` names a pack switches that pack on, whatever the first answers were. Say so in your report. `table_check.py packs` flags a part whose pack is off.
- A pack that is off is recorded with its reason, so a reviewer can see it was considered.

| Pack | Name | Switch | `category` value in `design/parts.csv` |
|---|---|---|---|
| SC | Switching converter | Switching converter | switching converter |
| RM | Radio | Radio | radio |
| VB | Vehicle supply and bus | Vehicle | vehicle bus |
| GS-USB | USB | USB | USB |
| GS-ETH | Ethernet and isolated interfaces | Ethernet | Ethernet |
| GS-BAT | Battery, charging and coin cells | Rechargeable | battery |
| GS-MOT | Motors and inductive loads | Motors | motor |
| GS-MAINS | Mains and high voltage | Mains | mains |
| GS-ANA | Precision analog and sensors | Analog | analog |
| GS-FAST | Fast digital | Fast digital | fast digital |
| GS-IND | Industrial field I/O | Industrial | industrial |
| GS-RAIL | Multi-rail power | Multi-rail | multi-rail |
| GS-SEC | Microcontroller security and boot | Microcontroller | microcontroller |

## Board-type switches

The Switch column in every item table (the checklists, the packs, the fabrication items and the release items) uses these short names for the coordinator's board-type switches. Each item states its own switch here, in the worker's files; the coordinator's switch table names only the switches and the packs they add. The short names are the exact names the scripts read: write the first-session answers and the board profile with them, so nothing needs translating.

| Short name | The coordinator's switch |
|---|---|
| Switching converter | Switching converter (buck, boost, inverting, charger) |
| Battery | Battery, or very low sleep current |
| Rechargeable | Rechargeable battery or coin cell on the board |
| Radio | Radio (module or chip-down) |
| USB | USB (connector, role, power delivery) |
| Ethernet | Ethernet or an isolated interface |
| Fast digital | Fast digital buses, tested against a figure: the bus speed or edge rate recorded with the switch |
| Analog | Analog measurement (ADC, sensors, references) |
| Motors | Motors, solenoids, relays, high current |
| Mains | Mains, or above the safety extra-low voltage limit |
| Vehicle | Connects to a vehicle |
| Industrial | Industrial (24 V field I/O, long cables) |
| Cables | Cables or connectors a user can touch or plug |
| Multi-rail | More than one supply rail, or a multi-rail chip |
| Microcontroller | Microcontroller with strapping, boot or security features |
| Sold | Sold, and where |
| Enclosure | Enclosure, outdoors, humidity, dust or vibration |

## How to use a pack

1. At the parts stage, every part in a switched-on pack gets three separate datasheet passes (logical, electrical, physical), unless the user changed that setting.
2. Each pack item is a prompt for the physical and electrical passes: find what this part's datasheet says about that area, in its own words, and write the rows. If the datasheet is silent on an area, follow WR-20 (evaluation board guide, then the maker's layout application note, then "no guidance found" and ask).
3. At the board rules stage, carry every layout row to constraints (`references/board.md`, Constraints), with a sufficiency verdict.
4. In a review, give every pack item a result, as for checklist items.
5. A user habit in a pack area (for example "do it the way my last board did") is a prompt to read the datasheet, not a rule. The datasheet wins by default, and any difference is a numbered decision quoting both (WR-20).

The items of the guide-sourced packs name areas only; the content comes from the vendor's design guide and the named specification, fetched and read each time.

## Adding and retiring items

- **Adding.** Anyone may propose an item: a worker in report section 12, a reviewer, or the user. A proposal has all six fields. The coordinator puts it to the user. An accepted item goes into the project's copy with the next free number in its pack, and keeps that ID for good. A whole new pack gets a new code. An item or pack that looks useful for every board of that type may be offered to the user as feedback for the skills; it is never sent automatically.
- **Retiring.** An item is never deleted and its ID is never reused, so old reports still resolve. To retire one, keep the row and start its "What to check" cell with "Retired <date>: <reason>; see <new ID>". Retire an item only when another item covers all of it, or its authority no longer exists. In a project copy, the user decides. An item that does not fit one board is not retired; it is marked "does not apply" with a reason in that review.

---

## SC Switching converter

Switch: Switching converter. Applies to every switching regulator, controller or charger on the board, whatever the topology. Each item names an area only. What the part needs in that area comes from this part's datasheet and the documents it delegates to, read every time; converters differ widely, even within one maker's family.

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| SC-00 | The hot loop or loops for this topology: the path where current switches fastest, as this datasheet's layout section and layout figure describe it. Name it in the datasheet's own words in the physical pass report | the converter datasheet's layout section and layout example figure; the evaluation board layout | ST3, ST9 | none | Switching converter |
| SC-01 | The parts in each hot loop: what this datasheet says about their type, where each sits and the size of the loop. Each part it names gets its own row and its own constraint, not only the first one | the converter datasheet layout section; each part's datasheet | ST3, ST9, ST11 | `board_check.py distance` (each part); `loop_area` (aid) | Switching converter |
| SC-02 | The switch node: what this datasheet says about its size, its route, vias on it and copper near it on other layers | the converter datasheet layout section and figure | ST7, ST9, ST10 | `dru:` rules; `board_check.py keepout`; `copper_area` (aid) | Switching converter |
| SC-03 | The grounding scheme, exactly as this datasheet and its delegated documents describe it, quoted in full. Never carry one part's scheme to another | the converter datasheet layout section; the evaluation board layout | ST3, ST7, ST9 | the `board_check.py` checks that fit the quote (`same_island`, `single_point`, `plane_one_piece`) | Switching converter |
| SC-04 | The thermal path: the pins and pads that carry heat, what this datasheet asks for under and around them, and how they link to the planes | the converter datasheet layout and thermal sections; the package drawing | ST9, ST10 | `board_check.py via_count`, `board_check.py same_island` | Switching converter |
| SC-05 | The feedback network and any sense connection: what this datasheet says about where its parts sit and how it is routed. Feedback circuitry is sensitive; read this datasheet every time | the converter datasheet layout section | ST3, ST9, ST10 | `board_check.py net_length`, `board_check.py noisy_distance` | Switching converter |
| SC-06 | The parts that set frequency or timing, and their nodes, including any limit this datasheet states on such a node | the converter datasheet pin description and layout section | ST3, ST9 | `board_check.py distance`; `node_capacitance` (aid) | Switching converter |
| SC-07 | Any bootstrap, flying or charge-pump capacitor the topology has: what this datasheet says about it in the text, the figures and the absolute maximum table | the converter datasheet | ST3, ST9 | `board_check.py net_length` | Switching converter |
| SC-08 | The output parts and their return path, as this datasheet describes them | the converter datasheet layout section | ST9 | `board_check.py distance` | Switching converter |
| SC-09 | Control inputs (enable, lockout, mode, synchronisation, power good): what this datasheet says about their parts, their state at power-up and their routing | the converter datasheet pin descriptions, detailed description and layout section | ST4, ST5, ST9 | `sch_check.py powerup`; `board_check.py noisy_distance` | Switching converter |
| SC-10 | Optional parts this datasheet shows, or a reviewer suggests: a footprint left or not, by recorded decision | the converter datasheet typical application and figures; `design/findings.csv` | ST5 | none (see EL-24) | Switching converter |
| SC-11 | Vias in or near the converter's pads, as the package drawing notes and the layout section say | the package drawing; the layout section | ST9, ST10 | `board_check.py via_in_pad` | Switching converter |
| SC-12 | Component values from this datasheet's design equations, with effective values; and the calculations this pack asks for even where the datasheet states no instruction: at least the peak switch current at the worst case against the part's lowest current limit, and the duty cycle and timing limits over the input range. Each is a row of kind `calculation` from the electrical pass, open until a worst-case script runs at ST5 | the converter datasheet design procedure and electrical characteristics | ST3, ST5 | `worstcase.py` | Switching converter |
| SC-13 | Input filter interaction and damping | the converter datasheet input filter guidance; the maker's application note | ST5 | simulation strongly recommended; `worstcase.py` | Switching converter |
| SC-14 | Effective input and output capacitance under DC bias, and inductor saturation at the highest current limit and hot (EL-11) | capacitor and inductor maker curves, rendered and read | ST3, ST5 | none | Switching converter |
| SC-15 | Thermal estimate after layout, redone after any change to copper near the converter (BD-33) | the converter datasheet thermal information | ST11 | `worstcase.py`; `copper_area` (aid) | Switching converter |
| SC-16 | Copper width of the power paths: what this datasheet says, and the current each path carries | the converter datasheet layout section; the currents from SC-12 | ST7, ST10 | `dru:` width rules | Switching converter |
| SC-17 | Planes under and near the converter: what this datasheet asks for or rules out on each layer | the converter datasheet layout section | ST7, ST10 | `board_check.py plane_one_piece`, `board_check.py keepout` | Switching converter |
| SC-18 | What the datasheet says that is specific to this topology or mode (boost, inverting, charger, multi-phase, light-load modes, spread spectrum): each is a row, never assumed from a buck | the converter datasheet | ST3, ST5 | none | Switching converter |

### Worked example: the method on an invented part

Everything in this example is invented: the part, its maker, its section, table and figure numbers, and every quote. It is not modelled on any real datasheet, and no rule in it applies to a real part. It shows the method only: how what a datasheet says, wherever it says it, becomes a row, then a constraint, then a check. Your part's own datasheet decides what applies.

**The part.** "FX-1000", an invented boost converter, datasheet revision B. Its sections include 4 Pin Functions (Table 4-1), 6 Electrical Characteristics (Table 6-2, with notes), 8 Detailed Description, 11 Application (Equation 5), 12 Layout (a numbered list in 12.1 and a layout example, Figure 12-3), and a package drawing with numbered notes on the last pages.

**Step 1: Inventory and pages.** The fetch brief saves the PDF and its text extract, renders every page once into `design/renders/`, and writes one `sections.csv` row per heading, parent headings and the package drawing included. The passes read those page images; none of them renders again.

**Step 2: Read every page as an image, and write one row per instruction.** Seven places in this invented datasheet hold seven different kinds of instruction:

| # | Where | What it says (invented) | Why it is easy to miss | The row |
|---|---|---|---|---|
| 1 | 12.1, item 3 of a numbered list | "Route SW on the top layer only." | the text extract runs the list numbers together; count the items on the rendered page | must, layout, physical; carried |
| 2 | Figure 12-3, a callout only | "C4 on the same side as pin 6" | no sentence in the text says it | figure, layout, physical; carried; `figure` "Figure 12-3", and the render of its page kept |
| 3 | Table 6-2, note 2 | "For VIN above 20 V, fit RS in series with VDD." | a table note under a limit; the extract detaches it from the row it qualifies | must, external-component, electrical; open until the schematic |
| 4 | the package drawing, note 5 | "No vias in pads 1 and 8." | on the last pages, after the ordering tables; the drawing has no figure number | must, layout, physical; carried; `section` gives the drawing's own number and "note 5" |
| 5 | Table 4-1, the SYNC row; and 8.3 | Table 4-1: "SYNC: internal pull-down". 8.3: "SYNC high when EN rises selects forced PWM." | neither sentence is an instruction alone; read together, the SYNC level at start-up chooses the mode | two rows, one per quote (logical); the pin table's `required_in_reset` for SYNC cites both; which mode the board needs is a question for the logical design, never a sentence the pass makes up |
| 6 | Equation 5 in 11.2, and Table 6-2 | Equation 5 gives the peak switch current. Table 6-2: "Switch current limit: min 1.2 A". | no sentence says "compare them"; pack item SC-12 asks for it | calculation, external-component, electrical; open until a worst-case script runs at ST5 |
| 7 | nowhere | nothing on how the feedback trace passes the switch node; the evaluation board guide is silent too | silence leaves no text to find; pack item SC-05 names the area | recommend, layout, physical; text "no guidance found in <documents checked>"; carried; raised as a decision |

Three of them as they look in the physical pass's staging file:

```
id,designator,mpn,datasheet,revision,section,page,figure,kind,category,perspective,text,design_value,margin,schematic_result,board_result,decision,carried_to,evidence,found_by
physical-2,,FX-1000,FX-1000.pdf,B,12.2,32,Figure 12-3,figure,layout,physical,"C4 on the same side as pin 6 (callout)",,,carried,open,,,,pass
physical-9,,FX-1000,FX-1000.pdf,B,<drawing number> note 5,40,,must,layout,physical,"No vias in pads 1 and 8.",,,carried,open,,,,pass
physical-14,,FX-1000,FX-1000.pdf,B,12 (whole section),,,recommend,layout,physical,"no guidance found in FX-1000.pdf rev B and FX-1000_eval-guide.pdf rev A on routing the feedback trace near SW",,,carried,open,,,"read 8, 11 and 12 and the guide's layout pages; searched for FB, feedback, SW",pass
```

And the electrical pass's calculation row:

```
electrical-21,,FX-1000,FX-1000.pdf,B,11.2 Equation 5,27,,calculation,external-component,electrical,"Peak switch current (Equation 5) at the worst case, against the switch current limit (Table 6-2 p9, min 1.2 A)",,,open,,,,,pass
```

**Step 3: Carry the layout rows to constraints (ST7), before any placement.** The shape, with placeholders:

```
id,from,kind,objects,limit,enforced_by,sufficiency,standard_or_own,note
CN-011,DS-<row 1>,no_vias,"<the SW net>",0,dru:sw-no-vias,whole (BR-<n>),datasheet,
CN-012,DS-<row 2>,placement,"<C4>; <pin 6>",-,review:<pack item>,whole with a verdict in each board review,datasheet,"no sub-command reads ""same side""; the reviewer checks it on the board file"
CN-013,DS-<row 4>,via_in_pad,"<pad 1>; <pad 8>",0,check:via_in_pad CN-013,whole (BR-<n>),datasheet,
```

The sufficiency review asks of every row: if these constraints all pass, is the whole quoted text met? Row 1: a net with no vias cannot leave the layer of its pads, and here every pad is on the top, so the verdict is whole; on a board with parts on both sides it would be partial. Row 2: a distance check would test something near the instruction, not the instruction, so a `review:` verdict reads the words themselves. Row 7 gets a constraint only after the user's decision gives an own figure (`standard_or_own` "own figure").

**Step 4: Verify.** After placement and after routing, `board_check.py` runs every `check:` constraint, and the board review gives a verdict for each `review:` one. `board_result` is filled from a check or a verdict, never from a picture. The calculation row closes at ST5, with its script output as evidence. Any row the board does not meet is reported as "Violation of FX-1000 datasheet <section>: <quote>", with a recommended fix, never as a question about what the engineer meant.

**What the example is not.** It is not a list of rules for converters, and not a guide to where a real datasheet keeps its instructions. Read your part's datasheet, every page, every time.

---

## RM Radio

Switch: Radio. For a radio module or a chip-down radio.

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| RM-01 | The module's land pattern against the module drawing (BD-01) | the module datasheet's land pattern figure | ST3, ST9 | none | Radio |
| RM-02 | The module's own placement and layout guide is fetched and read, as a delegated document (WR-17). If it cannot be found, that is a decision for the user, never "listed as missing" | the module datasheet's pointer to its design guide; the guide | ST3 | none | Radio |
| RM-03 | Module position and antenna keep-out on every layer as the guide says, and the certification conditions that depend on them. Any trade-off against user-facing parts (indicators, buttons at the outer end) is a numbered decision | the module design guide; the certification grant conditions | ST8, ST9 | `board_check.py keepout` | Radio |
| RM-04 | Matching network footprints and an RF test point, if the guide asks; the antenna type is one the certification covers | the module design guide; the certification grant | ST5 | none | Radio |
| RM-05 | Functions blocked while the radio runs (for example pins or converter channels the radio stack takes), in the allocation (EL-02) | the module or chip reference manual | ST5 | `sch_check.py alloc` | Radio |
| RM-06 | Ground stitching, edge stitching and via fences as the guide says | the module design guide | ST10 | none (`review:` verdict) | Radio |
| RM-07 | Radio rules where the board is used, sold or not: which certification or licence-free rules apply, their conditions, and the module ID marking (FB-10). Each named regulation fetched | the published radio regulations for each market, fetched | ST1, ST12 | none | Radio |
| RM-08 | Burst current in the power budget (LG-10); supply decoupling and bulk at the module as the guide says | the module datasheet supply-current table; the design guide | ST4, ST5 | `worstcase.py` | Radio |
| RM-09 | Harmonics of on-board clocks and switchers against the radio band (EL-39) | the module design guide; the converter's frequency options | ST5 | `worstcase.py` | Radio |
| RM-10 | Chip-down radio: RF track impedance on the named stack-up, the matching network and RF layout as the chip's reference design shows, the radio crystal's requirements; every difference from the reference layout is a row with a reason | the chip's hardware design guide and reference layout | ST5, ST10 | `board_check.py net_length` | Radio |

## VB Vehicle supply and bus

Switch: Vehicle. For a board that connects to a vehicle's supply or data bus. The `category` value stays "vehicle bus".

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| VB-01 | Environment profile: which vehicles and supply systems (ask about every system it could be plugged into), where it is mounted, temperature range. Named vehicle standards fetched, never from memory | the user; the vehicle environment and electrical standards for the market, fetched | ST1 | none | Vehicle |
| VB-02 | Transients and load dump: whether the vehicle limits load dump centrally, the test pulses that apply, and the clamp voltage at the pulse current and hot against every downstream absolute maximum (EL-05) | the vehicle transient standard, fetched; TVS and regulator datasheets | ST5 | `worstcase.py` | Vehicle |
| VB-03 | Reverse battery and jump-start conditions, and what the board does in each | the user; the vehicle electrical standard, fetched; protection datasheets | ST5 | none | Vehicle |
| VB-04 | Bus protection part chosen and placed as its datasheet and the transceiver datasheet say (BD-15) | protection and transceiver datasheets, layout sections | ST5, ST9 | `board_check.py distance`, `board_check.py via_count` | Vehicle |
| VB-05 | Bus variant and speed against the controller, transceiver and clock: the clock the controller needs for the bit rate, and its tolerance (EL-16) | controller and transceiver datasheets; the bus specification, fetched | ST3, ST5 | `worstcase.py` | Vehicle |
| VB-06 | The bus is never held: what keeps the transmitter in its idle state while the controller is in reset, hung or browned out (a pull, a logic part, the transceiver's own time-out), and the safe state (LG-11) | transceiver and controller datasheets | ST5 | `sch_check.py powerup` | Vehicle |
| VB-07 | Sleep current drawn from the vehicle battery, and the wake strategy, against the allowance the user or the vehicle maker gives (EL-14) | the user; datasheets | ST4, ST5 | `sch_check.py currents` | Vehicle |
| VB-08 | Bus clearance: the standard named, or recorded as "own figure" and an open question (BD-10) | the named standard, fetched | ST7 | none (`dru:` rules) | Vehicle |
| VB-09 | Vias on the bus lines: ask the user. Some engineers avoid them entirely; if so it is a constraint with an enforcer | the user | ST7, ST10 | none (`dru:` rule) | Vehicle |
| VB-10 | Termination decided from the bus topology and the transceiver datasheet, and recorded as a decision (fitted, split, or none) | the transceiver datasheet; the bus specification, fetched | ST5 | none | Vehicle |
| VB-11 | Automotive qualification grades for the parts, if sold (EL-13) | each part's qualification statement | ST3 | `table_check.py parts` | Vehicle |
| VB-12 | The vehicle EMC standard for the market, if sold, and what it asks of filtering and layout (EL-22, BD-27) | the vehicle EMC standard, fetched | ST5, ST11 | none | Vehicle |
| VB-13 | Vibration: heavy parts supported, connector retention, ceramic capacitors placed against flexing (BD-21) | the vehicle environment standard, fetched; connector and capacitor maker notes | ST8, ST9 | `board_check.py edge_distance` | Vehicle |
| VB-14 | The vehicle connector's pinout and which pins this board uses, from the published connector standard; a bench header's pins traced back to it | the vehicle connector standard, fetched | ST5 | `sch_check.py pins` | Vehicle |

---

## Guide-sourced packs

Each pack names areas only. When one switches on: fetch the vendor's design guide and the named specification; list every requirement as DS- rows; the three perspective passes apply. Say to the user that this pack's content comes from those documents, read now. A named specification that must be bought and was not read is "named, not read", with its price (`references/requirements-parts.md`, Environment); no row quotes a clause of it.

### GS-USB USB

Switch: USB. Fetch the USB specifications for the connector, role and power level from the standards body, and the USB hardware design guide of the PHY or microcontroller; list every requirement as DS- rows; the three perspective passes apply.

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| GS-USB-01 | Connector type and role: the configuration parts the role needs on a reversible connector, and what happens with each cable type the user may plug in | the USB specifications, fetched; the connector datasheet | ST5 | `sch_check.py protect` | USB |
| GS-USB-02 | VBUS: protection, capacitance at plug-in against the specification's limit (EL-09), inrush (EL-05), current available and how it is negotiated | the USB specifications, fetched; protection and regulator datasheets | ST5 | `sch_check.py railcap` | USB |
| GS-USB-03 | Data lines: low-capacitance ESD protection at the connector (EL-04, BD-15); the series or common-mode parts the PHY asks for | the PHY or microcontroller USB guide; protection datasheet | ST5, ST9 | `sch_check.py protect` | USB |
| GS-USB-04 | Shield connection to ground or chassis as the specification and the design guide say | the USB specifications, fetched; the design guide | ST5 | none | USB |
| GS-USB-05 | Back-feed between host and board when either side is unpowered (EL-07) | the USB specifications; datasheet powered-off notes | ST5 | `sch_check.py domains` | USB |
| GS-USB-06 | Data pair routing: impedance on the named stack-up, matching, no plane gaps under the pair (BD-17, BD-07) | the USB specifications; the design guide; the manufacturer's stack-up | ST7, ST10 | `board_check.py net_length`, `board_check.py ref_plane` | USB |

### GS-ETH Ethernet and isolated interfaces

Switch: Ethernet. Fetch the PHY's reference design and layout guide, the isolator's datasheet and the named specification; list every requirement as DS- rows; the three perspective passes apply.

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| GS-ETH-01 | Magnetics, or transformer-less coupling, and termination as the PHY reference design shows | the PHY datasheet and reference design | ST5 | none | Ethernet |
| GS-ETH-02 | PHY strap pins and their states at reset (EL-03) | the PHY datasheet | ST5 | `sch_check.py powerup` | Ethernet |
| GS-ETH-03 | Isolation rating of the magnetics or isolator against the requirement; creepage and clearance across the barrier (BD-10, BD-29) | isolator and magnetics datasheets; the named safety or interface standard, fetched | ST5, ST7 | none (`dru:` rules) | Ethernet |
| GS-ETH-04 | Optocoupler transfer-ratio ageing over the life target (EL-42); the isolated supply's rating | optocoupler and isolated supply datasheets | ST5 | `worstcase.py` | Ethernet |
| GS-ETH-05 | Pair routing and impedance (BD-17); keep-outs under the magnetics as the reference layout shows | the PHY layout guide; the manufacturer's stack-up | ST9, ST10 | `board_check.py net_length`, `board_check.py keepout` | Ethernet |
| GS-ETH-06 | Surge and ESD on the cable (EL-04) | the PHY guide; the market's immunity standards, fetched | ST5 | `sch_check.py protect` | Ethernet |

### GS-BAT Battery, charging and coin cells

Switch: Rechargeable (and Battery, when the battery is rechargeable). Fetch the cell, charger and protector datasheets, the charger's design guide and the battery safety and transport rules for the market; list every requirement as DS- rows; the three perspective passes apply.

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| GS-BAT-01 | The charger matches the cell chemistry and its charge profile; temperature sensing of the cell | cell and charger datasheets | ST3, ST5 | none | Rechargeable |
| GS-BAT-02 | Protection against over-charge, over-discharge, over-current and short, and which part gives each | cell, charger and protector datasheets | ST5 | none | Rechargeable |
| GS-BAT-03 | Shipping mode, and the sleep current against the shelf life (EL-14) | charger and protector datasheets; the user | ST4, ST5 | `sch_check.py currents` | Rechargeable |
| GS-BAT-04 | Cell safety and transport rules for the market (LG-17) | the battery safety and transport rules, fetched | ST1, ST3 | none | Rechargeable |
| GS-BAT-05 | Coin cells: the holder, reverse insertion, and the market's coin-cell rules | the holder datasheet; the coin-cell rules for the market, fetched | ST5, ST8 | none | Rechargeable |
| GS-BAT-06 | Cells and holders that cannot be reflowed, and the assembly order that follows (EL-27) | cell and holder datasheets; the assembler | ST3, ST12 | `table_check.py parts` | Rechargeable |
| GS-BAT-07 | Paths between several sources and a store: each source alone, each pair together, a source change while a stage runs, back-feed from one source into another, a divider into an unpowered part, and the case where firmware has stopped (EL-07) | charger, power-path and protector datasheets; the requirements | ST4, ST5 | `sch_check.py domains` | Rechargeable |

### GS-MOT Motors and inductive loads

Switch: Motors. Fetch the driver's datasheet and design guide and the motor or load data; list every requirement as DS- rows; the three perspective passes apply.

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| GS-MOT-01 | A flyback or freewheel path for every inductive load | the driver datasheet; the load data | ST5 | none | Motors |
| GS-MOT-02 | Gate drive and dead time; bootstrap refresh at the duty-cycle extremes. A half-bridge gets a hardware interlock against both switches on, by default; leaving it out is the user's decision | the driver datasheet | ST5 | `worstcase.py` | Motors |
| GS-MOT-03 | Current sense: the shunt and its Kelvin routing (BD-29) | the driver and sense amplifier datasheets | ST5, ST10 | none | Motors |
| GS-MOT-04 | Start and stall current against the supply, the fuse and the tracks (EL-05, BD-09) | the motor data; fuse and driver datasheets | ST5, ST7 | `worstcase.py` | Motors |
| GS-MOT-05 | Energy returned to the supply on braking or switch-off, and what absorbs it | the driver datasheet and design guide | ST5 | `worstcase.py` | Motors |
| GS-MOT-06 | Safe state for every drive output when the processor hangs, resets or leaves its pins floating (LG-11): the driver's truth table with floating inputs, the pin states in reset, and whether the chosen reset stops a running timer output (a watchdog reset may not) | the driver datasheet; requirements | ST4, ST5 | `sch_check.py powerup` | Motors |
| GS-MOT-07 | Emissions from motor leads and switching edges (EL-22, BD-27) | the driver design guide; the market's EMC standards, fetched | ST5, ST11 | none | Motors |

### GS-MAINS Mains and high voltage

Switch: Mains. Recommend a qualified safety reviewer to the user before any order. Fetch the product safety standard for the product type and the datasheets of every part across the barrier; list every requirement as DS- rows; the three perspective passes apply.

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| GS-MAINS-01 | The insulation class and the product safety standard that applies to this product type | the product safety standard, fetched | ST1 | none | Mains |
| GS-MAINS-02 | Fusing and its ratings | the safety standard; fuse datasheets | ST5 | none | Mains |
| GS-MAINS-03 | Suppression capacitors and varistors; safety-approved parts across the barrier, each recorded in `design/parts.csv` | the safety standard; part datasheets and approvals | ST3, ST5 | `table_check.py parts` | Mains |
| GS-MAINS-04 | Capacitor discharge after unplugging; touch-safe parts and openings | the safety standard | ST5, ST8 | none | Mains |
| GS-MAINS-05 | Creepage and clearance per voltage pair (BD-10); slots under the barrier and no copper across it (BD-29) | the safety standard | ST7, ST10 | none (`dru:` rules) | Mains |
| GS-MAINS-06 | A qualified safety reviewer offered before order, and the user's answer recorded | the user | ST11 | none | Mains |

### GS-ANA Precision analog and sensors

Switch: Analog. Fetch the ADC, amplifier, reference and sensor datasheets and their application notes; list every requirement as DS- rows; the three perspective passes apply.

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| GS-ANA-01 | Error budget from sensor to code (EL-28) | ADC, amplifier, reference and sensor datasheets | ST5 | `worstcase.py` | Analog |
| GS-ANA-02 | The reference: noise, drift, decoupling and load | the reference datasheet | ST5 | `worstcase.py` | Analog |
| GS-ANA-03 | Supply rejection at the frequencies on the rail, and the filtering it needs (EL-10) | amplifier and ADC datasheet graphs | ST5 | none | Analog |
| GS-ANA-04 | High-impedance nodes: guard rings, leakage through board and flux, cleaning and coating (FB-12) | sensor and amplifier datasheets and application notes | ST5, ST10 | none | Analog |
| GS-ANA-05 | Placement apart from switching and digital areas; the ground return (BD-16) | the datasheets' layout sections | ST9 | `board_check.py noisy_distance` | Analog |
| GS-ANA-06 | Hot parts kept from sensors and references (BD-12) | sensor and reference datasheets | ST9 | `board_check.py distance` | Analog |

### GS-FAST Fast digital

Switch: Fast digital. Fetch the interface specification, the chip vendor's layout guide and the manufacturer's stack-up; list every requirement as DS- rows; the three perspective passes apply.

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| GS-FAST-01 | The named stack-up and the impedance each interface needs (BD-17) | the interface specification; the manufacturer's stack-up and calculator | ST7 | none (`dru:` rules) | Fast digital |
| GS-FAST-02 | Length matching and crosstalk spacing as the guide says | the chip vendor's layout guide | ST10 | `board_check.py net_length` | Fast digital |
| GS-FAST-03 | Return paths under every fast signal (BD-07) | the layout guide | ST10 | `board_check.py ref_plane` | Fast digital |
| GS-FAST-04 | Termination and drive strength (EL-17) | the datasheets; the interface specification | ST5 | none | Fast digital |
| GS-FAST-05 | BGA or fine-pitch fanout, via in pad, and the inspection route (BD-01, BD-11, EL-27) | the package drawing; the assembler's capability pages | ST7, ST10 | `board_check.py via_in_pad` | Fast digital |
| GS-FAST-06 | Power sequencing and decoupling of the fast parts (EL-20, BD-06) | the datasheets | ST5, ST9 | `board_check.py decouple_per_pin` | Fast digital |

### GS-IND Industrial field I/O

Switch: Industrial. Fetch the interface parts' datasheets and design guides and the market's immunity standards; list every requirement as DS- rows; the three perspective passes apply.

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| GS-IND-01 | Surge and burst on field wiring (EL-04) | the market's immunity standards, fetched; protection datasheets | ST5 | `sch_check.py protect` | Industrial |
| GS-IND-02 | Field supply transients, reverse connection and miswiring (EL-05) | the field supply's specification; protection datasheets | ST5 | `worstcase.py` | Industrial |
| GS-IND-03 | Isolation where field and logic grounds differ | isolator datasheets; the named standard, fetched | ST5, ST7 | none | Industrial |
| GS-IND-04 | Connector contact order and wiring errors (EL-23) | connector datasheets | ST5 | none | Industrial |
| GS-IND-05 | Long-cable emissions and immunity (EL-22) | the market's EMC standards, fetched | ST5 | none | Industrial |
| GS-IND-06 | Shorted outputs and inductive loads on outputs (GS-MOT where it applies) | driver datasheets | ST5 | none | Industrial |

### GS-RAIL Multi-rail power

Switch: Multi-rail. Fetch the power-sequencing sections of every multi-rail part and the supervisor and regulator datasheets; list every requirement as DS- rows; the three perspective passes apply.

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| GS-RAIL-01 | Sequencing order and timing each multi-rail part needs (EL-20) | the power-sequencing sections | ST5 | `worstcase.py` | Multi-rail |
| GS-RAIL-02 | No input above its own supply while rails rise or fall (EL-07) | datasheet absolute maximums and powered-off notes | ST5 | `sch_check.py domains` | Multi-rail |
| GS-RAIL-03 | Rail discharge and a quick off and on | supervisor and microcontroller reset requirements | ST5 | none (simulation) | Multi-rail |
| GS-RAIL-04 | The power-good and reset chain at worst case | supervisor and regulator datasheets | ST5 | `worstcase.py` | Multi-rail |
| GS-RAIL-05 | Rail tracking or ratio limits where a part asks for them | the multi-rail part's datasheet | ST5 | none | Multi-rail |

### GS-SEC Microcontroller security and boot

Switch: Microcontroller. Fetch the reference manual's security and boot chapters and the maker's security application notes; list every requirement as DS- rows; the three perspective passes apply.

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| GS-SEC-01 | Debug lock and readout protection: how each is set, and whether it can be undone (LG-14) | the reference manual | ST5 | none | Microcontroller |
| GS-SEC-02 | Secure boot and key storage: what the hardware needs | the reference manual; security application notes | ST5 | none | Microcontroller |
| GS-SEC-03 | One-time fuses and option bytes; every irreversible step is a decision | the reference manual | ST5 | none | Microcontroller |
| GS-SEC-04 | Boot-mode and strap pins: the level at reset and what drives it (EL-30, EL-03) | the reference manual; the datasheet strapping table | ST5 | `sch_check.py powerup` | Microcontroller |
| GS-SEC-05 | Production programming order: when locks and fuses are set, and what the fixture needs (LG-22) | the reference manual; programmer documentation | ST4, ST5 | none | Microcontroller |
