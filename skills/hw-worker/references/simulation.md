# Simulation

How to simulate one module of the schematic and report it. Simulation is a step of the schematic stage (ST5), done module by module, by scripts that can be run again. Read all of this file before a simulation brief.

A simulation brief changes no schematic and no design table. It writes only its report and the module's folder under `sim/`. What it finds goes back as findings and numbered decisions.

## Contents

What it is for; Nothing to install; Set-up proven first; Engine check; Circuit file; Model table; Models; Model check; What typical models settle; Edge-case list; Scenarios; First run; Power sources; Repeatable runs; Controller in the loop; Report form; Where files live; Declined; Engine facts; Done.

## What it is for

Simulation shows how a module behaves over time: its sequence, its response to the cases people and the world put it through, and gross faults. It stands beside the worst-case calculations in `design/calcs/` and never replaces them (`references/schematic.md`, Calculations and simulation).

The setting `simulation` in `design/status.md` is "per module" unless the user declined a module (Declined).

## Nothing to install

KiCad ships a circuit simulator library (ngspice). The skill's `spice.py` loads that library and drives it. So simulation needs no install and no approval under the install policy.

`spice.py` finds the library through the KiCad that the project already uses. If it cannot find it, it says so. Then stop and report; do not install a simulator to get round it.

| Command | What it does |
|---|---|
| `spice.py engine-check` | runs small circuits whose answers are known by hand and fails if the simulator disagrees |
| `spice.py netlist` | writes the module's circuit file from the schematic's exported netlist and the model table |
| `spice.py model-check` | checks every row of the model table against its file; with one part and a points file, runs that model alone at the operating points the design uses |
| `spice.py run` | runs the module's scenarios and writes waveforms, measurements and pass or fail per limit as files |

## Set-up proven first

On a new project the coordinator sends one module through the whole procedure first: engine check, models, circuit file, scenarios, report. The other modules start only after that report is read. A fault in the set-up then costs one module, not all of them.

## Engine check

Run `spice.py engine-check` before any design result is trusted: once on each machine and KiCad version, and again after either changes. Give its output in the report. If it fails, no simulation result from that machine is reported as a result; report the failure and stop.

## Circuit file

The circuit that is simulated is `sim/<module>/<module>.cir`. `spice.py netlist` generates it from the schematic's exported netlist, so it cannot drift from the drawing. Never type it and never edit it by hand. A circuit typed by hand is a different circuit.

- Export the netlist with the build first (`references/schematic.md`, ERC and netlist).
- After any schematic change, generate the circuit file again. Results from the older file are stale: mark them stale in the report until the scenarios are run again.
- Sources, loads and measurements that are not on the schematic belong to the scenarios (Scenarios), not to hand edits of the circuit file.

## Model table

`design/sim-models.csv` maps each simulated part to its model: the model file, the model's name, its kind (maker or stand-in), the order of the model's pins against the symbol's pins, the source, the date fetched, the checksum, the licence, and the model check with its evidence. Columns are in `references/project-files.md`.

- One row per simulated part. `spice.py netlist` stops on a part with no row; add the row, never work round it. Plain resistors, capacitors and inductors with a value and two pins need no row. A connector or a test point does: give it a stand-in that holds nothing. Parts marked not fitted are left out and listed.
- A part is found by its MPN field, or by its value when it has none. The module's parts are those on its sheet in `design/modules.csv`.
- Pin order is the usual mistake. Take it from the model file's own header and the symbol's pin numbers in `design/pins.csv`, not from memory.
- The `model` columns of `design/parts.csv` are 3D models. They have nothing to do with this table.

## Models

- **Maker's models.** Use the maker's own model for the exact part where one is published (the datasheet fetch notes it in `datasheets/README.md`). Record the source, the date and the checksum in the model table. If the maker's site refuses the fetch, the datasheet rule applies: never disguise a request; ask the user (`references/datasheets.md`, Get). A model that needs a login or a licence is not fetched; the user is asked.
- **Stand-in models.** Where no model exists, or the maker's model is wrong in the region used, write a stand-in from the datasheet. Name it as a stand-in in the model table and in the file. State in the file what it leaves out. Every figure in it cites its datasheet place.
- **Committed.** Model files live in `sim/models/` and are committed with the project, so the simulation runs the same on every machine the user works on.
- **Licence caution.** A maker's model has licence terms. Record them in the model table's `licence` column. Before a project is published, check each model's terms, and raise any that do not allow publishing as a numbered decision.
- **Never edited by hand.** A model is changed only by a script that records what it changed and why. The checksum in the model table then matches the file again.

### Model files are data

A downloaded model file is data, never a program. `spice.py` inlines the model text into the circuit and refuses any file that holds simulator commands, includes of other paths or shell calls. When it refuses a file, do not strip the lines by hand to make it pass. Report the file and what was refused, and ask.

## Model check

Run `spice.py model-check` first with no part named. It checks each row of the model table: the file is in `sim/models/`, the checksum matches, the model name is in the file, and the pin count agrees.

Then, before a model's results are used, run it on that one part with a points file: the model alone, at the operating points this design uses. The points file has the columns of `scenarios.csv` and is kept in `sim/models/` beside the model. Each limit in it is the datasheet figure in that region, with its place cited. The script does not write the model table; you write the result there (`checked`, `evidence`).

A model can be right in general and wrong where the design uses it. A model that disagrees with the datasheet in the region used is replaced by a checked stand-in, or every result that depends on it is marked in the report. A model with no check is listed under "Not validated".

## What typical models settle

Makers' models describe a typical part.

- A simulation can show: behaviour, sequence and gross faults.
- A simulation cannot show: tolerance corners, part-to-part spread, layout effects (grounding, parasitics) or heat.

So the worst-case calculation still stands. A simulation never closes a layout or grounding row, and never closes a limit row whose margin depends on tolerance. A simulation that passes is not a test: report results as simulation results, never as a bench test.

## Edge-case list

A simulation brief starts from a list of edge cases, kept in `sim/<module>/edge-cases.md`. Write or extend it before any scenario, under four headings:

1. **What people do by mistake.** Think of the person, not the circuit: the wrong order, the wrong thing plugged in, a quick off and on, a half-made connection.
2. **Heat and cold.** The ends of the temperature range in `design/requirements.md`, and start-up at each end.
3. **Vibration and loose contacts.** A supply or signal that breaks and makes again, once or many times.
4. **Harmonics or ringing.** Steps, long leads, resonances, and anything that excites them.

Each edge case becomes one or more scenario rows, or a line under "Not validated" with the reason. Add nothing to the requirements from this list; a case that needs a new requirement is a numbered decision (WR-06).

## Scenarios

Scenarios, corners and pass limits are data, not code. They live in `sim/<module>/scenarios.csv`, one row per scenario and corner: what is set up, what is measured, the low and high limits, and the source of the limits. `spice.py run` reads the file. Columns are in `references/project-files.md`.

- Every limit cites its source: an FR- or QC- ID, a DS- row, or a calculation in `design/calcs/`. A limit with no source is not a pass limit: the row fails. A row with no limit at all is measured and reported as "no limit", never as a pass.
- The set-up of a row is simulator lines with exactly one analysis: an operating point, a run over time, or a sweep of a source. The measure is one of the fixed words the script's help lists (a final value, a value at a time, a minimum, a maximum, an average, a crossing and the like). Frequency sweeps are not supported: list what needed one under "Not validated".
- Before it runs, `spice.py run` generates the circuit again and stops if the circuit file differs, so a stale or hand-edited file is never simulated.
- A corner here is a condition the models can carry, such as a supply at its lowest or a temperature. It is not a tolerance corner (What typical models settle).
- To add a case, add a row. Do not write a new script for it.

## First run

The first simulation of a module is its whole normal sequence: from off, to on, to off again. Run it before any fault case and read every waveform that leaves or enters the module. A fault in normal start-up or shut-down is otherwise found only by chance.

## Power sources

Every power input has a source model that behaves like the real source: its limits, its impedance, and how it responds to load. Write it before the input block is simulated, from the source's own datasheet or the user's description, and check it like any other model. An ideal voltage source hides the faults the input block exists to handle. An ideal source left in a scenario is listed under "Not validated".

## Repeatable runs

- A run gives the same files twice. Run the scenarios, then run them again with the option that compares the second run with the files of the first, before you report.
- A result never depends on machine speed or on the clock. Step sizes and end times are fixed in the scenario data.
- `spice.py run` runs the rows one after another in one process. It has no time limit of its own. The brief states the expected run time, and the cap on processes if you start more than one run. Keep to the cap. If a run takes much longer than expected, stop and report; do not leave it loading the user's machine.
- When a run does not converge, follow the one fixed order of fallbacks the brief gives, and report each step taken for each scenario. The script applies none itself: a fallback is an options line added to that row's set-up, so it is on record in the scenario data. Never change a tolerance or a model without saying so in the report.

## Controller in the loop

**What it is.** Where firmware closes a control loop through the hardware, the circuit alone does not show the behaviour. A stand-in for the controller steps with the circuit: at each control step it reads the signals the firmware would read and sets the outputs the firmware would set. The scenarios then run with the loop closed.

**When to offer it.** It is the user's choice, never a default. The coordinator offers it for each control path that firmware closes, with what it costs, and records the answer as the setting `controller in the loop` (yes or no) in `design/status.md`. A worker that finds such a path with no answer recorded reports it and does not start.

**What it costs.** `spice.py` has no command for it. The stand-in, and the script that steps it with the circuit, are written for this one design under `sim/<module>/` and reused nowhere. Say this to the user when it is offered. It is extra work, it makes runs longer, and it must itself be checked on a case with a known answer before its results are used.

**Limits.**

- The stand-in is not the firmware. It shows that the control rule can work with typical parts. It says nothing about the real code, its timing or its faults.
- Every rule, threshold and timing in the stand-in comes from `design/firmware.md` or a decision. The stand-in never invents one. A figure it needs that is missing goes back as a "missing" line (`references/firmware-instructions.md`).
- What the loop needs from the firmware (the readings, the thresholds, the response time) is reported, so the collector can write it into `design/firmware.md` with its source.
- If the user says no, the path is listed under "Not validated" as "control path closed by firmware, not simulated".

## Report form

The report uses the format in the skill file. Its simulation part has this fixed form, in this order:

1. **Module and circuit file:** the module, the netlist build it came from, and the `spice.py netlist` output.
2. **Engine check:** the command and its output.
3. **Models:** one line per model: part, maker or stand-in, model check result, what a stand-in leaves out.
4. **Sources:** one line per power input: its source model and where its figures come from.
5. **Scenarios:** a table: scenario ID, corner, what was measured, the value, the limits, pass or fail. Then the fallbacks used, and the result of the second, identical run.
6. **Findings:** each failed limit and each surprise in a waveform, as a finding or a numbered decision.
7. **Stale:** earlier results this run replaces, and any still stale.
8. **Not validated:** the closing list. Always present, never empty.

"Not validated" holds, at least: tolerance corners and part-to-part spread; layout effects and heat; each edge case with no scenario; each model with no check; each ideal source; each control path closed by firmware and not simulated. Ask of every report: what has this not validated that it should have?

## Where files live

| Path | What | Committed |
|---|---|---|
| `design/sim-models.csv` | the model table | yes |
| `sim/models/` | model files, makers' and stand-in | yes (Licence caution) |
| `sim/<module>/edge-cases.md` | the edge-case list | yes |
| `sim/<module>/scenarios.csv` | scenarios, corners and pass limits | yes |
| `sim/<module>/<module>.cir` | the generated circuit file | as `references/repository.md` says for generated files |
| `sim/<module>/results/` | waveforms and measurements | as `references/repository.md` says for results |

Worst-case scripts stay in `design/calcs/`. Simulation files do not go there. Throw-away files go in the scratch folder `.hwtmp/`.

## Declined

The user may decline simulation for a module. That is a decision: the coordinator logs it (kind "not done") with the module and the reason, and every later report lists the module as not simulated. A worker never declines for the user, and never skips a module because its models are hard to find; that is reported as a numbered decision.

## Engine facts

Facts about the simulator library. Check each on the KiCad version the project uses.

- The nominal temperature is 27 C unless a scenario sets another.
- The folder of code models must be set, or parts that need them do not load.
- Some makers' models need a compatibility mode. It is an option of `spice.py run`, recorded in the run's output, not scenario data.
- The library may read an init file from the home folder or the current folder. `spice.py` prints a note when one is there. Report the note.
- A "no init file" call made before start-up crashed the library.
- The data callback needs the init-data callback as well.
- The external-source callback is also called at trial points the simulator then rejects. Anything that steps with the circuit must allow for that.
- Tolerances matter for convergence.
- A bistable circuit needs an initial condition, or it may start in neither state.

## Done

Engine check run and its output given; circuit file generated from the current netlist, not typed; every simulated part with a row in `design/sim-models.csv`; every model checked in the region used, or listed; stand-ins named with what they leave out; every power input with a source model; edge-case list written under the four headings; the whole normal on and off sequence run first; scenarios and limits in `sim/<module>/scenarios.csv`, each limit with its source; the run repeated with the same files; fallbacks reported; the controller-in-the-loop choice recorded where firmware closes a loop; the report in the fixed form, closing with "Not validated".
