# Fabrication files

Procedure for the order files (ST12). The manufacturer checks only whether the board can be made. It never checks pin assignment or whether the circuit is right; that is ours, done before this stage.

## Contents

Pre-checks; Export; Waivers; BOM and placement files; Consistency; Hand assembly; Offered checks; Alternative export; Order; Tag; Release record; Fabrication items (FB-).

## Pre-checks

If the user asked to tidy the designators (renumber them in board order so they read well), do that first. For a script-owned design, change the order in the generator and rebuild; for a hand-owned one, propose it, since KiCad's own annotation tool is the engineer's to run. Then export the netlist and show it is unchanged apart from the names, update every table that names a designator (`design/parts.csv`, `design/pins.csv`, `design/compliance.csv`, `design/constraints.csv`, `datasheets/README.md`), and re-run every check. A renumbering that changes a connection is a finding.

Before any export:

1. **Ownership.** `build.py` checks the board against its last recorded write. A script-owned board saved from the KiCad editor shows up here: stop and report it with what changed in meaning (`references/adapting.md`); the user chooses keep, carry into the script, or overwrite.
2. **Parts check 2.** Stock and price for every fitted part on the supplier's page today; lifecycle; newer datasheet or errata revisions (`references/requirements-parts.md`, Parts check). Run `table_check.py parts --stage ST12`: a stock and price date older than 30 days fails here.
3. **Checkpoint lists, by designator:** parts with no checked pin table; carried rows and constraints with no board result; open waivers; open severity 1 and 2 findings.
4. **Capabilities restated.** The capability table the rules were built from, with its sources and dates, and the service level. The user checks it matches the service being ordered.
5. **Shape.** If the board shape is provisional (enclosure unknown), say: "ordering now risks paying twice".

## Export

`fab.py` makes the order files, in the manufacturer's own upload format, into their own folder `hardware/<manufacturer>/` (in an adopted project, `<manufacturer>/` inside the KiCad folder that `design/status.md` names):

- Gerber and drill files, zipped as the manufacturer requires, with no loose copies beside the zip;
- BOM and placement files (below);
- not-fitted and variant lists;
- fixed dates inside the files, so two builds give the same bytes.

The files: `<name>_gerbers.zip`; the neutral set `bom.csv`, `placement.csv` and `not_fitted.csv`; with `--assembler <supplier>`, the assembler set `assembler_bom.csv`, `assembler_cpl.csv` and `assembler_not_fitted.csv`, in a column format to compare with the assembler's file-format page; with `--hand`, `hand_assembly.csv`. `--variant <name>` fits that variant's parts; `--date` sets the date stamped into the files. Exit codes: 0 written; 1 violations, nothing written; 2 bad input; 3 `kicad-cli` missing or failed; 4 written, but the read-back check failed.

It runs DRC with re-pour first (zones poured in memory; the board file is not saved, though `kicad-cli` creates the project's `.kicad_prl` if it is missing). Any violation, unconnected item, or schematic parity item not listed as expected in `design/status.md` stops the export (see Waivers).

Then build twice and compare: `python3 hwskills/build.py --twice` (proven so far on the two test fixtures only, one with a two-sheet schematic and a routed board; not yet on a real project). Where the project's own build writes the files instead, build twice yourself and compare checksums. Give the result: the order files must be byte-identical between two builds. Run `table_check.py scan` on the folder: no machine paths, user names or private terms.

## Waivers

A failed check at export is a violation. Report it plainly: "Violation: DRC reports <n> errors: <list>." Recommend a fix.

The export goes ahead only if the engineer fixes it or records a waiver (DC-). Offer the waiver as a numbered decision in the same report, so one reply records it. Pass the waiver to the script (`--waive DC-nnn`); the script prints it in its output. List every waiver in the report and in every later report until it is closed.

## BOM and placement files

- Two sets: the assembler's own format, and a neutral set (designators, value, footprint, manufacturer, MPN, supplier, supplier part number, quantity; placement with designator, X, Y, rotation, side).
- Both paths are covered: assembled by the board house (their format, their part numbers) and parts bought and hand-assembled (distributor part numbers).
- Fields come from `design/parts.csv` (or the symbol fields for a hand-owned schematic). Missing fields are listed, never guessed.
- Not-fitted parts are excluded the same way from BOM and placement. Variant BOMs where the project has variants.
- Placement rotations follow the assembler's convention; differences between KiCad's footprint zero and the assembler's are a known source of error. Offer the preview check (below).

## Consistency

`fab.py` checks that the BOM, the placement file and the board agree: every fitted SMD part appears once in both, not-fitted parts are excluded the same way, designators match. Give the output.

## Hand assembly

If the board is hand-built, `fab.py` writes a hand-assembly list: placement order (SMD parts by footprint size, then through-hole; part heights are not read, so check that tall and heat-sensitive parts go last), polarity and pin-1 marks, parts that need care (moisture-sensitive, fine pitch, exposed pads, heat-sensitive), and which parts use the stencil. The user's habit of ordering the stencil is recorded in `design/status.md`.

## Offered checks

Offer these; the user decides:

- the Gerbers opened in a viewer (KiCad's own viewer needs no new install);
- placement rotations compared in the manufacturer's online preview;
- a fabrication and mechanical drawing (outline with dimensions, hole table, stack-up notes);
- the KiCad 3D view, then the manufacturer's preview and quote on upload (the user's usual final look).

## Alternative export

Some manufacturers publish their own KiCad fabrication plugin. It is an alternative export path, not used so far. `fab.py` stays the tested route; if the user prefers the plugin, compare its output with `fab.py`'s and report the differences.

## Order

Order options are the user's choice at order time, usually by price: quantity, finish, colour, stencil, assembly. Options that change the design (thickness, stack-up, finish for fine pitch or exposed pads, via plugging, impedance control, assembled or hand-built) should have been asked earlier; if one changed, say what it affects.

## Tag

Offer to tag the commit the order was made from, so the ordered files can always be found. A revision mark on the board itself is item FB-09.

## Release record

At order time, write `docs/release-<revision>.md` (or where the user keeps such records), so the ordered board can be understood later without the conversation:

- the commit and the order files' folder;
- the schematic as a PDF (`kicad-cli sch export pdf`) and an assembly drawing (part outlines and designators per side), saved beside the record;
- every FR- re-checked now with its evidence, and every QC- with its result; anything not ticked, said plainly;
- open waivers and open findings of severity 1 and 2;
- what is not verified, copied from the reports, and what is provisional (shape, enclosure fit);
- the parts check 2 date, and the capability table's service level.

The user decides what goes into any public README; this record is the plain account.

## Fabrication items (FB-)

The FB- items are in `references/checklist-fabrication.md`. Setup copies them to `design/checklists/fabrication.md`, where `table_check.py checklists` counts them.

## Report

File list; checks run, with output; checks offered and the user's answers; waivers listed; the checkpoint lists by designator; what is provisional; the release record's path.
