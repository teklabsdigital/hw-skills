# Questions by stage

Read only the section for the stage at hand. The board-type switch table is at the end.

How to ask:

- Ask each stage's questions as one short batch, with a proposed answer for each, so a "yes" or "ok" is enough. An "ok" covers only the numbered items that had one proposed answer. An item marked "to confirm", or one with two options, stays open until the user answers it. Silence is never a yes.
- Search `design/decisions.md` and `design/status.md` before you ask. Do not ask what the user has already answered.
- Ask few questions. Put the ones that block work first, and say what you held back for later.
- Ask only what the stage needs. Environment questions are asked only for the areas the switches turned on.
- When the user states a preference, ask which default it replaces, and record it in `design/status.md`.
- Record every answer with its source (the user, the date) in the file the stage names. A "no" is recorded with its reason, so a reviewer can see it was considered.
- Read back dictated names and numbers before they go into a file.

---

## First session

**The opening.** The greeting in `process.md` ("The greeting"): what you do, the five steps, and one open question. For a folder that holds a KiCad project, it ends with the "Existing project" text instead.

If the user's first message already says what they are building or changing, give the greeting without its question and go straight to the table. Do not ask again. Whatever the message left out (who uses it, sold or not) becomes a "to confirm" row.

**The reply.** One numbered table, filled from the answer and from what is in the folder. Propose; do not ask item by item. Plain names only; no IDs.

```
| #  | Item                          | Proposed                                   | Why |
|----|-------------------------------|--------------------------------------------|-----|
| 1  | Switching converter           | on                                         | <one line from the answer> |
| 2  | Radio                         | off                                        | <one line> |
| .. | (every switch that is on or uncertain, one row each, by its short name) |   |     |
| .. | All other switches            | off: <the remaining short names, in one line> | not mentioned |
| n  | Sold; region of use; market scan | <inferred, or "to confirm">; market scan <none, light or full> if sold | <one line> |
| .. | User interface                | <on the board, in an app, or both; or "to confirm"> | <one line> |
| .. | Suppliers; tool version rule  | to confirm: suppliers in order, preferred makers; tool versions at least 30 days old, pinned | your rule replaces the default |
| n+1| Stop and ask                  | before anything that costs money, changes a requirement or an approved plan, or installs something | default |
| n+2| Model split                   | I coordinate; workers run on <the model set in this tool's worker wrapper, read from it; or "the same model as mine" if none is set> | default: workers cost less than me; your setting, changed in the wrapper |
| n+3| Report length                 | normal: brief, with depth on complex points | default |
| n+4| Assembly                      | all SMD; package size <proposal>; <hand or machine, inferred> | <reason> |
| n+5| Datasheet passes; datasheet reading | three separate workers for complex or sensitive parts, one combined pass for simple parts; read up front (or as parts are placed) | default |
| n+6| Commits; backup commits       | offer a commit at sprint close; backup commits on: a commit before each build, never pushed; saved third-party PDFs <committed or not> | default |
| .. | Log every prompt              | on: each question you ask and its answer goes in the decision log | default; it tracks decisions and helps improve the skills |
| n+7| Setup plan                    | private git repository, no remote; project layout; tool check (KiCad, Python, C compiler, PDF route); clone and build the grid router at a pinned version (needs your approval; the setup worker proposes the exact versions for one more ok); copy the scripts into the project | |
| n+8| Existing project              | adopt it: inventory, state files, checks, ranked findings, a proposed first sprint; no redesign. If it has its own generator scripts: <keep them as the writers of their files, or treat the files as hand-owned> | only if one is in the folder |

Reply ok, or the numbers you want changed.
```

The switch rows use the exact short names in the switch table at the end; the scripts read those names. A "Fast digital" row states the bus speed or edge rate it was tested against, or asks for it. A "to confirm" row is not settled by "ok": ask for it by number.


Package size and form factor are settings, not rules: a size chosen for hand assembly on one board is not a rule for the next. Ask "ultra small, or larger for hand assembly? SMD, through-hole, or mixed?" only if the answer gives no hint; the default is all SMD.

---

## Problem and user story (ST1)

Ask these first, before any feature.

1. What problem does the product solve, and for whom?
2. One user story: who uses it, where, to do what, and what a good result looks like.

Test every feature against the story before it becomes a requirement. A feature the story does not need is put to the user, not added. A question the user asks is a question; it is not a requirement until the user says so.

## Environment (ST1)

Asked only for the areas switched on. Each item is answered, or recorded as "does not apply" with its source.

1. Every supply the board might see: nominal, lowest, highest, transients, reversed, hot-plugged. Ask about every system it could be plugged into (a 12 V design later needed 24 V once; ask early). For each external input, ask what surge or over-voltage it must survive, and on what basis: a named standard, a measured figure or the user's own figure.
2. How each power source really behaves: its limits, its impedance, and how it responds to load. The answer becomes the source model used before the input block is drawn or simulated.
3. Operating temperature range. Ask; never assume. It is a quality characteristic (QC-).
4. Storage and transport temperature.
5. Humidity, condensation, water and dust.
6. Vibration and shock.
7. Where it is used and by whom: indoors, outdoors, in a vehicle, on a bench. The region of use, recorded on the `Region of use:` line.
8. For high-impedance or outdoor circuits: coating and cleaning (decided at ST5 for those circuits, recorded at order).
9. Named standards for the environment, if the board is sold: fetched and cited by a research worker, never from memory.

## Misuse (ST1)

"What could a user do wrong?" Propose a list from the answer, for example: wrong supply, reversed supply, hot-plug, shorted output, wrong cable, plugged into the wrong port, user ESD, water. For each case, record the required behaviour. The part that gives the behaviour is filled in later.

Ask how protection ranks against cost for this product, and offer the most protective option first. Ask whether the product may ever draw power from something it supplies. Treat a protection trip as an emergency, not a normal state: ask what the user must see and do when one happens.

## Interfaces (ST1)

1. Each interface with its exact variant and speed. Ask the question that separates variants (for example "classic only, or the faster variant too?").
2. Protocols, profiles or apps it must work with.
3. Connectors and what mates with them.
4. Indicators and buttons: what each one tells the user or lets the user do. One indicator per user-visible function is a good starting proposal. Ask whether controls and display are on the board, in an app, or both; record it on the `User interface:` line.
5. Size and enclosure, if known. If not known, the board shape will be provisional. When a later change raises the power level, ask about the enclosure, the heat path and the mounting again.
6. Service life and duty cycle.

## Preferences (ST1, ST2)

1. Budget, and what drives cost for this user: layer count, assembly on one or both sides, assembled by the board house or hand-built, quantity. Ask; do not assume a cost sensitivity.
2. Suppliers and makers: which suppliers to use, in what order, and any preferred makers. Record the answer on the `Suppliers:` line. With no answer, the default is the best fit for the purpose, usually from a leading brand.
3. Part families or ecosystems the user knows well. Familiar is a preference, not a requirement.
4. Jellybean parts by default, except where a sensitive analog circuit needs care with noise and drift.
5. When a stated preference would change a default or the architecture, ask which default it replaces before acting on it.
6. For a board that will be sold: the market scan (none, light or full) and a cost target, before part research.

## Parts and derating (ST3)

1. The derating policy: margins for voltage, current, power and temperature. Ask once; record it. If the user has none, record "none" and the reviewer reports stress without a policy.
2. Approval for any part that raises the cost, with the cost effect stated.
3. Temperature grade and automotive or industrial qualification, where the switches call for it.
4. Whether to fit alternates for parts with a single source or a short lifecycle.

## Schematic (ST5)

1. The feature list as it stands. Show it before the first sheet is drawn and ask the user to confirm it.
2. Sheet style. Default: a hierarchical schematic, with a top sheet of module boxes and one sub-sheet per module. The main power path on the top sheet is drawn as wires with the net names visible. Ask how the other nets are shown on the top sheet: as wires or as labels. One sheet with functional frames is the other form. Everyone has their own style.
3. Drawing habits: how the user likes rails, labels, wires, text and page balance. Record them on the `Schematic drawing habits:` line.
4. What testing is planned (see Test points).
5. Simulation. It is a step for each module and needs no install. Say which modules it matters most for (`stages.md`, ST5) and what it can and cannot show. The user may decline it for a module; that is logged as "not done" with the reason. Where firmware closes a control loop, offer controller in the loop, with what it costs in time.
6. Pin assignment: does the user want to assign the microcontroller's pins in the vendor's configuration tool and hand over the export? That is the highest-trust source for the pin table.
7. Sheet comments are on every sheet by default. Do not ask whether they are wanted; ask only about wording, if the user has a preference.
8. Whether any grounding or layout instruction in the datasheet rows needs something in the schematic: its own net, a net tie, a sense connection or a footprint. A worker proposes the list from the carried rows; the user confirms it.
9. Pins a second worker could not confirm against their source: one batch, at the schematic checkpoint, each with the source page to look at.

## Security and boot (ST5)

A research worker first lists the hardware-set features of the chosen microcontroller from its reference manual. Then ask, for each one found:

1. Debug lock and readout protection: used or not.
2. Secure boot.
3. One-time fuses. Flag every irreversible step plainly.
4. Boot-mode and strapping pins: the required level at reset, and how it is set.

Firmware-side settings belong to the later firmware stage.

## Test points (ST1, confirmed at ST5)

At the start of the schematic stage, ask what testing the user plans: bench work, production test, programming. No test access is drawn before the test sweep. The sweep runs after the last module, writes `design/test-sweep.md`, and its pads and links are then added (`stages.md`, ST5).

1. For bench work: which rails, grounds, signals and clocks to probe. Propose: each supply rail, ground, reset, programming and debug pins, and the key signals of each block.
2. For production test and programming: the programming route and fixture, and the pads it needs.
3. Access in the enclosure, if there is one.

## Physical and enclosure (ST1 briefly, ST8 in full)

1. Outline, size, orientation and thickness.
2. The enclosure: drawing or 3D model, mounting holes, openings. If unknown, the shape is provisional.
3. Keep-outs: mechanical, antenna, under connectors.
4. Connectors and their mating parts; header types and pitches.
5. Where power enters; battery on the board or external supply.
6. LEDs: sizes, colours, positions; light pipes.
7. Buttons: positions; button caps.
8. Antenna position, and its trade-offs with user-facing parts.
9. Which end faces the user, and which parts must be visible or reachable from there.
10. Whether to check the fit against the enclosure's 3D model.
11. Whether whoever designs the enclosure wants the board outline and parts as a STEP or DXF file.
12. Silkscreen content: connector labels, what each LED and button means, polarity and pin-1 marks, the revision mark, anything else the user wants printed. Propose a list.
13. For machine assembly: fiducials and tooling holes, as the assembler asks.

## Manufacturer (ST7)

1. Board house and service level (standard or a higher-capability option).
2. Assembler, if different, and its limits: moisture level, reflow profile, part classes, fees.
3. Thickness and copper weights.
4. A named stack-up from the manufacturer.
5. Impedance control, if a bus needs it.
6. The clearance standard, if any. Otherwise the clearance is recorded as "own figure".
7. The user's own rule habits.

Every capability comes from the manufacturer's published pages, with the page and date. If a value cannot be found, ask the user for it.

## User's own habits (ST9 placement, ST10 routing)

1. Placement: functional blocks; support parts at the pins they serve; anything the user always does.
2. Routing: confirm the default guidelines (`stages.md`, ST10) and add the user's own, for example "no vias on the bus".
3. Record each habit in `design/status.md`. A habit that disagrees with a datasheet is put to the user as a numbered decision quoting both; the datasheet wins by default.

## Order (ST12)

1. Assembled by the board house or hand-built. Asked early where it changes the design; confirmed here.
2. Offered checks: open the Gerbers in a viewer; compare placement rotations in the manufacturer's preview; a fabrication and mechanical drawing. The user decides.
3. If the shape is provisional: "ordering now risks paying twice".
4. Order options: quantity, finish, colour, stencil. The user's choice at order time, usually by price. Record the user's usual choices as defaults (for example, always order the paste stencil).
5. Whether to tag the commit that was ordered.
6. Whether to tidy the designators (renumber them in board order) before ordering. It changes names only; every check is run again.

## Repository (ST13)

1. Licence: the user's choice. Do not pick one.
2. README: which images, what text.
3. Public or private. Before any remote is made: the repository name, the user's naming convention, and the organisation or account it goes under.
4. Whether saved third-party PDFs are committed (`Third-party PDFs committed:`), and whether each simulation model's licence allows it to be published.
5. Never change the visibility of any other repository.

---

## Board-type switches

Every check item exists for every board. Infer the switches from the first answer and show them in the first-session table with a one-line reason each. They also switch on by part choice: a part whose category in `parts.csv` belongs to a pack switches that pack on, and you say so in your next report. `table_check.py packs` flags a part whose pack is off.

This table says only which answer turns a switch on, and which packs that switch adds. It does not say what any check item means. Each checklist and pack item states its own switch in its own file: it applies always, always with more weight under a named switch, or only when a named switch is on. The pack codes in brackets are the hw-worker skill's; its packs reference lists them with the short switch names the items use.

| Short name | Switch: on when the answer or a part choice shows | Packs it adds | Also |
|---|---|---|---|
| Switching converter | Switching converter (buck, boost, inverting, charger) | the switching-converter checks (SC) | |
| Battery | Battery, or very low sleep current | the battery checks (GS-BAT), if the battery is rechargeable | |
| Rechargeable | Rechargeable battery or coin cell on the board | the battery checks (GS-BAT) | |
| Radio | Radio (module or chip-down) | the radio checks (RM) | |
| USB | USB (connector, role, power delivery) | the USB checks (GS-USB) | |
| Ethernet | Ethernet or an isolated interface | the Ethernet and isolated-interface checks (GS-ETH) | |
| Fast digital | Fast digital buses, tested against a figure: the bus speed or edge rate recorded with the switch | the fast-digital checks (GS-FAST) | |
| Analog | Analog measurement (ADC, sensors, references) | the precision-analog checks (GS-ANA) | |
| Motors | Motors, solenoids, relays, high current | the motor and inductive-load checks (GS-MOT) | |
| Mains | Mains, or above the safety extra-low voltage limit (the limit from the safety standard, fetched) | the mains and high-voltage checks (GS-MAINS) | recommend a qualified safety reviewer |
| Vehicle | Connects to a vehicle | the vehicle supply and bus checks (VB) | |
| Industrial | Industrial (24 V field I/O, long cables) | the industrial field I/O checks (GS-IND) | |
| Cables | Cables or connectors a user can touch or plug | none; checklist items only | |
| Multi-rail | More than one supply rail, or a multi-rail chip | the multi-rail power checks (GS-RAIL) | |
| Microcontroller | Microcontroller with strapping, boot or security features | the security and boot checks (GS-SEC) | |
| Sold | Sold, and where | none; checklist items only | ask again when the signs change |
| Enclosure | Enclosure, outdoors, humidity, dust or vibration | none; checklist items only | ask the environment questions in full; offer a 3D fit check against the enclosure model |

Items marked "always" apply to every board, whatever the switches: among them the assembly checks, the protection walk on every pin that leaves the board, the test points, and worst case by script.

A switch kept off on a stated condition records the condition. Test it again at every requirements change. The short names are the exact names the scripts read; use them in the first-session table and the board profile.

Form factor (package size; SMD, through-hole or mixed) and hand or machine assembly are settings in the first-session table, not switches.

Board types the earlier board did not exercise (the GS- packs) take their content from the vendor's design guide and the named specification, fetched and read each time. Say so when one switches on.
