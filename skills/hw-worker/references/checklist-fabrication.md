# Fabrication checklist

The starting checklist for the order files (ST12). The procedure is `references/fabrication.md`. The columns work as in the logical checklist (`references/checklist-logical.md`, How to use it). Switch names are in `references/packs.md` (Board-type switches).

Setup copies this file to `design/checklists/fabrication.md`, so `table_check.py checklists` counts its items with the others. Use the project's copy; it may have grown.

## Fabrication items (FB-)

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| FB-01 | BOM, placement file and board agree: every fitted SMD part once in both, not-fitted parts excluded the same way, designators match | assembler's file-format page | ST12 | `fab.py` consistency | always |
| FB-02 | Fabrication and mechanical drawing: outline with dimensions, hole table, stack-up notes (offered) | manufacturer's drawing needs; user | ST12 | none | always |
| FB-03 | Gerbers opened in a viewer (offered) | user | ST12 | none | always |
| FB-04 | Placement rotations compared in the manufacturer's preview (offered) | manufacturer's preview | ST12 | none | always |
| FB-05 | BOM and placement files in the assembler's format and a neutral set, for both paths (assembled or hand-built); order files in the manufacturer's upload format in their own folder; no placeholder supplier part number in the assembler BOM | assembler's file-format page | ST12 | `fab.py` | always |
| FB-06 | Parts check 2: stock and price on the day | supplier pages | ST12 | `table_check.py parts` | always |
| FB-07 | Order options that change the design (thickness, stack-up, finish where it matters, assembled or not) asked early; the rest at order time | user; manufacturer option pages | ST7, ST12 | none | always |
| FB-08 | Panel guidance from the assembler, if panelised: rails, break-off method, fiducials on rails, parts near break lines | assembler pages | ST12 | none | always |
| FB-09 | Revision mark on the board; offer to tag the ordered commit | user | ST8, ST12 | none | always |
| FB-10 | Marks needed if sold (regulatory, recycling, radio module ID) | named regulation, fetched | ST8, ST12 | none | Sold |
| FB-11 | Hand-assembly list (order of placement, polarity, parts needing care) if hand-built | datasheets | ST12 | `fab.py` hand-assembly list | always |
| FB-12 | Coating and cleaning decided where high-impedance or outdoor circuits need it (asked at ST5 for those circuits, recorded at order) | datasheets; coating and flux maker data; user | ST5, ST12 | none | always; more under Analog, Enclosure |
| FB-13 | Files repeatable and free of machine data | build output | ST12 | `build.py --twice`; `table_check.py scan` | always |
| FB-14 | Any unclean check at export reported as a violation; waivers listed in the fab report | `design/decisions.md` | ST12 | `fab.py` | always |
| FB-15 | Release record written at order time (`references/fabrication.md`, Release record): the commit and order folder, the schematic PDF and assembly drawing, every requirement re-checked with its evidence, open waivers and findings, what is not verified and what is provisional | `design/requirements.md`; the reports; `design/decisions.md` | ST12 | none | always |
| FB-16 | Package and assembly rows closed: every `package` row of `design/compliance.csv` has a board result by the board checkpoint, every `assembly` row by the order | `design/compliance.csv` | ST11, ST12 | `table_check.py compliance` | always |
