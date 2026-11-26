# Firmware instructions

How to collect what the hardware leaves to firmware, and how the schematic closes with the firmware page. The skills list what firmware must do and write none.

## Contents

Purpose; Collecting; Line form; The collector never designs; A signal for every duty; Moving a duty to firmware; The firmware page; Done.

## Purpose

A board is finished only when its firmware knows what the hardware expects of it: which signals it can read and drive, and which duties the hardware leaves to it. `design/firmware.md` holds that list, the firmware instructions. It is kept in that one place, and it is the hand-over to whoever writes the firmware. No worker writes firmware, pseudo-code or register settings.

## Collecting

Collection starts with the first sheet and runs while the schematic is drawn. It is not left to the end.

1. For each sheet, read its sheet comments: the theory of operation, the paragraph for each important part of the circuit, and the thresholds.
2. Read the design files for the same module: `design/pins.csv` (used functions and power-up columns), the compliance rows of its parts, `design/decisions.md`, the calculations in `design/calcs/`, and any simulation report (`references/simulation.md`).
3. Write one line for each thing the firmware can do with the hardware and each thing it must do, under the module's heading in `design/firmware.md`. A duty that crosses modules goes in the cross-module section.
4. When a sheet or a part changes, go through that module's lines again. A line whose source changed is checked against the new source, never left as it was.

A collection brief changes no schematic and no other design table. It writes `design/firmware.md` and its report.

## Line form

The template is in `references/project-files.md`. In short, one line per item:

- **can:** a signal the firmware can read or drive, with its meaning, range and speed.
- **must:** a duty, with the reading it uses, its threshold and its response time.

Each line ends with its source (a sheet, a DS- row, a DC- decision, a calculation or a report) and one of three statuses:

- decided with the user;
- stated by a worker, not decided;
- missing: <what is missing>.

## The collector never designs

- A missing figure is not filled in. The line is written with the status "missing" and what is missing: a threshold, a response time, a range.
- Where two sources disagree, both are listed, each with its place. The collector does not choose between them.
- The collector adds no duty of its own. A duty it thinks is needed and finds in no source is a finding in its report.
- Every "missing" line and every disagreement goes in the report, so the coordinator can put them to the user as one batch.

## A signal for every duty

For every "must" line, check that the firmware can do it:

- every reading the rule needs reaches a processor pin (name the net and the pin from `design/pins.csv`);
- the reading arrives fast enough for the response time the duty states;
- the firmware has a way to act: an output that reaches the thing it must control.

A duty with no signal to read, or no way to act, is a hardware finding, not a note for the firmware writer. Check again when a part or a pin assignment changes.

## Moving a duty to firmware

A worker never settles a hardware question by writing "firmware will handle it". Sometimes firmware will, but that is a decision made with the user.

- Each duty moved to firmware is reported as a numbered decision, with what the hardware would need to do the job itself.
- Until the user answers, the line's status is "stated by a worker, not decided".
- Flag any "must" line that is the only guard of a hardware start-up condition: before firmware runs, nothing holds that condition. Check it against the power-up columns of `design/pins.csv` and `sch_check.py powerup`.

## The firmware page

The schematic closes with the firmware page: a text sheet, the last sheet of the schematic, so the list travels with the drawing. It lists all the work the hardware leaves to firmware.

- Generate the page from `design/firmware.md` with the schematic build. Never type it on the sheet.
- It shows each line's status. Lines not decided and lines with something missing are shown as such, not hidden.
- Like every notes page, it holds no value that is not in its source (`references/schematic.md`, Notes pages).

## Done

Every sheet's comments and every module's design files read; every line in the template's form with its source and one status; no figure filled in by the collector; disagreeing sources both listed; every "must" line checked for a signal, its speed and a way to act; each duty moved to firmware reported as a numbered decision; start-up conditions guarded only by firmware flagged; the firmware page generated as the closing sheet; "missing" and "not decided" lines listed in the report.
