# Copyright 2026 Teklabs Digital (hw-skills)
# SPDX-License-Identifier: Apache-2.0
"""Tiny synthetic fixtures for the script tests. Standard library only.

make_project(dest) writes a small KiCad project the way the setup worker lays one out:

    <dest>/hwskills/             copies of the skill scripts the build uses, and build.py with
                                 FAB_ARGS filled in
    <dest>/scripts/              two fixture generators (gen_sch.py, gen_pcb.py) and their shared
                                 parts module
    <dest>/design/               status.md, decisions.md, parts.csv, pins.csv, fab-capabilities.csv,
                                 constraints.csv
    <dest>/hardware/             empty; the build writes it

The circuit: R1 and R2 (10k, fitted SMD), R3 (10k, not fitted) and J1 (a 2-pin through-hole
header), all in parallel between nets A and B, on a 30 x 20 mm two-layer board, routed. Nothing
here comes from a real part or a real supplier.

Seeded faults (make_project(..., fault=...)):
    "thin_track"   one track of net A is 0.1 mm wide, below the 0.127 mm minimum: a DRC violation.

write_pdf(path) writes a one-page PDF holding the text in PDF_TEXT.
No file outside this repository is read. KiCad itself is needed only by the tests that run it.
"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SKILL_SCRIPTS = os.path.join(REPO, "skills", "hw-worker", "scripts")
COPIED = ("hwcommon.py", "kicad_env.py", "project_settings.py", "kicad_pro_defaults.json", "fab.py")
SKILL_DIR = "hwskills"   # where a project keeps its copies of the skill's scripts
NAME = "fixture"
PDF_TEXT = "FIXTURE TEXT 42"
FAB_ARGS = '["--assembler", "SUPPLIER-A", "--hand", "--date", "2026-01-02"]'

PARTS_CSV = """refs,value,footprint,package,manufacturer,mpn,supplier,supplier_pn,role,category,dielectric,tolerance,voltage_rating,unit_price,qty_price,stock,checked,lifecycle,temp_grade,msl,peak_reflow,alternate,variant,datasheet,datasheet_revision,errata,compliance_done,pins_done,model,model_checked
R1;R2,10k,fixture:R_0603,0603,Maker A,RES-10K-0603,SUPPLIER-A,SA-1001,pull,,,1%,50 V,0.01,0.005,1000,2026-01-02,active,,1,,,,,,,yes,yes,,no
R3,10k,fixture:R_0603,0603,Maker A,RES-10K-0603,SUPPLIER-A,SA-1001,pull,,,1%,50 V,0.01,0.005,1000,2026-01-02,active,,1,,,not fitted,,,,yes,yes,,no
J1,Conn_2,fixture:PinHeader_1x02,THT 2.54 mm,Maker B,HDR-1X02,SUPPLIER-B,SB-2002,connector,,,,,0.10,0.08,500,2026-01-02,active,,1,,,,,,,yes,yes,,no
"""

PINS_CSV = """designator,mpn,pin,name,functions,used_function,net,supply,levels,abs_max,current_limit,reset_state,boot_activity,control_input,required_in_reset,given_by,sleep_state,fault_state,source,source_page,confirmed
J1,HDR-1X02,1,1,contact,contact,/A,,,,,,,no,,,,,datasheet table,1,yes
J1,HDR-1X02,2,2,contact,contact,/B,,,,,,,no,,,,,datasheet table,1,yes
"""

FAB_CSV = """item,manufacturer_value,source_url,read_on,service_level,rule_value,note
min_track,0.09,fixture,2026-01-02,standard,0.127,
min_clearance,0.09,fixture,2026-01-02,standard,0.127,
min_via_diameter,0.25,fixture,2026-01-02,standard,0.45,
min_via_drill,0.15,fixture,2026-01-02,standard,0.2,
via_annular,0.05,fixture,2026-01-02,standard,0.1,
pth_annular,0.15,fixture,2026-01-02,standard,0.15,
min_hole_to_hole,0.2,fixture,2026-01-02,standard,0.25,
via_hole_clearance,0.2,fixture,2026-01-02,standard,0.2,
pth_hole_clearance,0.28,fixture,2026-01-02,standard,0.28,
edge_clearance,0.2,fixture,2026-01-02,standard,0.3,
silk_clearance,0.15,fixture,2026-01-02,standard,0.15,
silk_text_height,0.8,fixture,2026-01-02,standard,0.8,
silk_text_thickness,0.15,fixture,2026-01-02,standard,0.15,
assembly_msl_limit,3,fixture,2026-01-02,assembly,,not a rule
"""

CONSTRAINTS_CSV = """id,from,kind,objects,limit,enforced_by,sufficiency,standard_or_own,note
CN-001,user,clearance,/A;/B,0.2,dru:netclass Signal,whole,own figure,fixture
CN-002,user,width,/A;/B,0.25,dru:netclass Signal,whole,own figure,fixture
CN-003,user,no_vias,/A,0,dru:a-no-vias,whole,own figure,fixture
CN-004,DS-001,single_point,"GND island; join via",-,check:single_point CN-004,partial,datasheet,not a rule
"""

STATUS_MD = """Designs: logical agreed; electrical in review; physical in review
Ownership: schematic script; board script (detail in ownership.csv)
Expected DRC notes: none
Skills version: hw-skills 0.1.0; scripts copied 2026-01-02
"""

DECISIONS_MD = """# Decisions

## Waive the seeded DRC violation in the test fixture (DC-001)
Kind: waiver
Decided by: user
Date: 2026-01-02
Stage: ST12
Options: waive it (chosen); fix the board first
Reason: the test checks that a waiver lets the export go ahead
Affects: requirements none; parts none; schematic none; board the seeded violation; cost none
Status: in force
"""

# Shared by the two fixture generators: symbol and footprint text, and the placement.
PARTS_MODULE = r'''"""Fixture parts (test only): symbols, footprints, placement."""
import uuid

NS = uuid.UUID("6f1c2a0e-5b1d-4c39-9a51-0d6c1f00a001")


def uid(*key):
    return str(uuid.uuid5(NS, "/".join(str(k) for k in key)))


def font(size=1.27, thickness=None):
    t = " (thickness %s)" % thickness if thickness else ""
    return "(effects (font (size %s %s)%s))" % (size, size, t)


def symbol_def(name, base):
    """A two-pin vertical symbol: pin 1 at the top, pin 2 at the bottom (like KiCad's Device:R)."""
    prefix = "R" if base == "R" else "J"
    return (
        '(symbol "%s" (pin_numbers (hide yes)) (pin_names (offset 0)) (exclude_from_sim no) (in_bom yes) '
        "(on_board yes) (in_pos_files yes) (duplicate_pin_numbers_are_jumpers no)\n"
        '  (property "Reference" "%s" (at 2.032 0 90) (show_name no) (do_not_autoplace no) %s)\n'
        '  (property "Value" "%s" (at 0 0 90) (show_name no) (do_not_autoplace no) %s)\n'
        '  (property "Footprint" "" (at -1.778 0 90) (show_name no) (do_not_autoplace no) (hide yes) %s)\n'
        '  (property "Datasheet" "" (at 0 0 0) (show_name no) (do_not_autoplace no) (hide yes) %s)\n'
        '  (property "Description" "fixture part" (at 0 0 0) (show_name no) (do_not_autoplace no) (hide yes) %s)\n'
        '  (symbol "%s_0_1" (rectangle (start -1.016 -2.54) (end 1.016 2.54) (stroke (width 0.254) (type default)) '
        "(fill (type none))))\n"
        '  (symbol "%s_1_1"\n'
        '    (pin passive line (at 0 3.81 270) (length 1.27) (name "" %s) (number "1" %s))\n'
        '    (pin passive line (at 0 -3.81 90) (length 1.27) (name "" %s) (number "2" %s)))\n'
        "  (embedded_fonts no))"
        % (name, prefix, font(), base, font(), font(), font(), font(), base, base,
           font(), font(), font(), font()))


SYMBOLS = {"R": "R", "Conn_2": "Conn_2"}


def footprint_body(name):
    """Graphics and pads of a footprint, as (attr, lines, pads); pads are (number, kind, x, y)."""
    if name == "R_0603":
        lines = ['(fp_rect (start -1.5 -0.75) (end 1.5 0.75) (stroke (width 0.05) (type default)) (fill no) '
                 '(layer "F.CrtYd") (uuid "%s"))',
                 '(fp_rect (start -0.8 -0.4) (end 0.8 0.4) (stroke (width 0.1) (type default)) (fill no) '
                 '(layer "F.Fab") (uuid "%s"))']
        pads = [("1", "smd", -0.8, 0.0), ("2", "smd", 0.8, 0.0)]
        return "smd", lines, pads
    lines = ['(fp_rect (start -1.3 -1.3) (end 1.3 3.84) (stroke (width 0.05) (type default)) (fill no) '
             '(layer "F.CrtYd") (uuid "%s"))',
             '(fp_rect (start -1.27 -1.27) (end 1.27 3.81) (stroke (width 0.1) (type default)) (fill no) '
             '(layer "F.Fab") (uuid "%s"))']
    pads = [("1", "thru_hole", 0.0, 0.0), ("2", "thru_hole", 0.0, 2.54)]
    return "through_hole", lines, pads


def pad_text(name, number, kind, x, y, key, net=None):
    netpart = ' (net "%s")' % net if net else ""
    if kind == "smd":
        return ('(pad "%s" smd roundrect (at %s %s) (size 0.9 0.95) (layers "F.Cu" "F.Mask" "F.Paste") '
                '(roundrect_rratio 0.25)%s (uuid "%s"))' % (number, x, y, netpart, uid(key, "pad", number)))
    shape = "rect" if number == "1" else "oval"
    return ('(pad "%s" thru_hole %s (at %s %s) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask")%s '
            '(uuid "%s"))' % (number, shape, x, y, netpart, uid(key, "pad", number)))


def footprint(name, ref, value, at=None, key=None, fields=(), nets=None, path=None, dnp=False, version=True):
    """Footprint text for the library (at=None) or for the board."""
    key = key or name
    attr, lines, pads = footprint_body(name)
    head = ['(footprint "%s"' % (name if at is None else "fixture:" + name)]
    if version:
        head.append('(version 20260206) (generator "pcbnew") (generator_version "10.0")')
    head.append('(layer "F.Cu")')
    if at is not None:
        head.append('(uuid "%s") (at %s %s)' % (uid(key, "fp"), at[0], at[1]))
    out = [" ".join(head)]
    out.append('(property "Reference" "%s" (at 0 -1.4 0) (layer "F.SilkS") (uuid "%s") %s)'
               % (ref, uid(key, "ref"), font(0.8, 0.15)))
    out.append('(property "Value" "%s" (at 0 1.4 0) (layer "F.Fab") (uuid "%s") %s)'
               % (value, uid(key, "val"), font(0.8, 0.12)))
    out.append('(property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "%s") %s)'
               % (uid(key, "ds"), font()))
    out.append('(property "Description" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "%s") %s)'
               % (uid(key, "desc"), font()))
    for i, (fname, ftext) in enumerate(fields):
        out.append('(property "%s" "%s" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "%s") %s)'
                   % (fname, ftext, uid(key, "field", i), font()))
    if path:
        out.append('(path "/%s") (sheetname "/") (sheetfile "fixture.kicad_sch")' % path)
    out.append("(attr %s%s)" % (attr, " dnp" if dnp else ""))
    for i, l in enumerate(lines):
        out.append(l % uid(key, "line", i))
    for number, kind, x, y in pads:
        out.append(pad_text(name, number, kind, x, y, key, (nets or {}).get(number)))
    out.append("(embedded_fonts no))")
    return "\n  ".join(out) + "\n"


# Board placement: ref -> (x, y); the board is 100..130 x 100..120 mm, origin at its lower left.
PLACE = {"R1": (110, 105), "R2": (110, 110), "R3": (110, 115), "J1": (104, 106.73)}
'''

GEN_SCH = r'''"""Fixture schematic generator (test only). Writes the schematic, the project symbol and
footprint libraries, the library tables, and the project and rule files."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "hwskills"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture_parts as fx  # noqa: E402
import hwcommon  # noqa: E402
import project_settings  # noqa: E402

OUT = os.path.abspath(sys.argv[1])
HW = os.path.dirname(OUT)
NAME = os.path.splitext(os.path.basename(OUT))[0]
DESIGN = os.path.join(os.path.dirname(HW), "design")
ROOT = fx.uid("root")
U = 2.54

parts = {}
for row in hwcommon.read_table(os.path.join(DESIGN, "parts.csv")):
    for ref in hwcommon.split_list(row["refs"]):
        parts[ref] = row

items = []
# ref, symbol, x, y (mm); pins at y - 3.81 (pin 1) and y + 3.81 (pin 2)
PLACED = [("R1", "R", 50.8, 50.8), ("R2", "R", 60.96, 50.8), ("R3", "R", 71.12, 50.8), ("J1", "Conn_2", 81.28, 50.8)]


def prop(name, text, x, y, hide=False, justify=None):
    j = " (justify %s)" % justify if justify else ""
    h = " (hide yes)" if hide else ""
    return ('    (property "%s" "%s" (at %s %s 0)%s (show_name no) (do_not_autoplace no) '
            "(effects (font (size 1.27 1.27))%s))\n" % (name, text, x, y, h, j))


for ref, sym, x, y in PLACED:
    row = parts[ref]
    dnp = "not fitted" in row["variant"]
    s = ('  (symbol (lib_id "fixture:%s") (at %s %s 0) (unit 1) (body_style 1) (exclude_from_sim no) '
         "(in_bom yes) (on_board yes) (in_pos_files yes) (dnp %s) (uuid \"%s\")\n"
         % (sym, x, y, "yes" if dnp else "no", fx.uid("symbol", ref)))
    s += prop("Reference", ref, round(x + 2.54, 2), round(y - 1.27, 2), justify="left")
    s += prop("Value", row["value"], round(x + 2.54, 2), round(y + 1.27, 2), justify="left")
    s += prop("Footprint", row["footprint"], x, y, hide=True)
    s += prop("Datasheet", "", x, y, hide=True)
    s += prop("Description", "", x, y, hide=True)
    for field, col in (("Manufacturer", "manufacturer"), ("MPN", "mpn"), ("Supplier", "supplier"),
                       ("Supplier PN", "supplier_pn")):
        s += prop(field, row[col], x, y, hide=True)
    for pin in ("1", "2"):
        s += '    (pin "%s" (uuid "%s"))\n' % (pin, fx.uid("pin", ref, pin))
    s += ('    (instances (project "%s" (path "/%s" (reference "%s") (unit 1)))))\n' % (NAME, ROOT, ref))
    items.append(s)

for y, net in ((47.0, "A"), (54.6, "B")):
    ys = 46.99 if net == "A" else 54.61
    xs = [p[2] for p in PLACED]
    for x1, x2 in zip(xs, xs[1:]):
        items.append('  (wire (pts (xy %s %s) (xy %s %s)) (stroke (width 0) (type default)) (uuid "%s"))\n'
                     % (x1, ys, x2, ys, fx.uid("wire", net, x1)))
    items.append('  (label "%s" (at %s %s 0) (effects (font (size 1.27 1.27)) (justify left bottom)) (uuid "%s"))\n'
                 % (net, xs[0], ys, fx.uid("label", net)))

lib_symbols = "".join("    " + fx.symbol_def("fixture:" + n, b).replace("\n", "\n    ") + "\n"
                      for n, b in sorted(fx.SYMBOLS.items()))
doc = ('(kicad_sch (version 20260306) (generator "eeschema") (generator_version "10.0")\n'
       '  (uuid "%s")\n  (paper "A4")\n  (lib_symbols\n%s  )\n%s'
       '  (sheet_instances (path "/" (page "1")))\n  (embedded_fonts no)\n)\n'
       % (ROOT, lib_symbols, "".join(items)))
hwcommon.write_text(OUT, doc)
hwcommon.write_text(os.path.join(HW, "fixture.kicad_sym"),
                    '(kicad_symbol_lib (version 20251024) (generator "kicad_symbol_editor") (generator_version "10.0")\n'
                    + "".join("  " + fx.symbol_def(n, b) + "\n" for n, b in sorted(fx.SYMBOLS.items())) + ")\n")
hwcommon.write_text(os.path.join(HW, "sym-lib-table"),
                    '(sym_lib_table\n\t(version 7)\n\t(lib (name "fixture")(type "KiCad")'
                    '(uri "${KIPRJMOD}/fixture.kicad_sym")(options "")(descr "fixture symbols"))\n)\n')
hwcommon.write_text(os.path.join(HW, "fp-lib-table"),
                    '(fp_lib_table\n\t(version 7)\n\t(lib (name "fixture")(type "KiCad")'
                    '(uri "${KIPRJMOD}/fixture.pretty")(options "")(descr "fixture footprints"))\n)\n')
for fp_name in ("R_0603", "PinHeader_1x02"):
    hwcommon.write_text(os.path.join(HW, "fixture.pretty", fp_name + ".kicad_mod"),
                        fx.footprint(fp_name, "REF**", fp_name))
project_settings.write_project(os.path.join(HW, NAME + ".kicad_pro"), DESIGN)
print("wrote", os.path.basename(OUT))
'''

GEN_PCB = r'''"""Fixture board generator (test only): places and routes the fixture from the netlist.
Plain Python; the real generators use pcbnew."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "hwskills"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture_parts as fx  # noqa: E402
import hwcommon  # noqa: E402
import project_settings  # noqa: E402

FAULT = "@@FAULT@@"
NET, OUT = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
HW = os.path.dirname(OUT)
NAME = os.path.splitext(os.path.basename(OUT))[0]
DESIGN = os.path.join(os.path.dirname(HW), "design")

comps, nets = hwcommon.read_netlist(NET)
if "/A" not in nets or "/B" not in nets:
    sys.exit("fixture board: the netlist has no nets /A and /B")
pad_net = {}
for name, nodes in nets.items():
    for ref, pin, _, _ in nodes:
        pad_net[(ref, pin)] = name

fps = []
for ref in sorted(comps, key=hwcommon.ref_key):
    c = comps[ref]
    fp_name = c["footprint"].split(":")[-1]
    fields = [(k, c["fields"].get(k, "")) for k in ("Footprint", "Manufacturer", "MPN", "Supplier", "Supplier PN")]
    fps.append("  " + fx.footprint(fp_name, ref, c["value"], at=fx.PLACE[ref], key=ref, fields=fields,
                                   nets={p: pad_net.get((ref, p)) for p in ("1", "2")}, path=c["uuid"],
                                   dnp="dnp" in c["properties"], version=False))

W = 0.25
segments = [  # (x1, y1, x2, y2, layer, net, width)
    (109.2, 105, 109.2, 106.73, "F.Cu", "/A", W), (109.2, 106.73, 109.2, 110, "F.Cu", "/A", W),
    (109.2, 110, 109.2, 115, "F.Cu", "/A", 0.1 if FAULT == "thin_track" else W),
    (104, 106.73, 109.2, 106.73, "F.Cu", "/A", W),
    (110.8, 105, 110.8, 109.27, "F.Cu", "/B", W), (110.8, 109.27, 110.8, 110, "F.Cu", "/B", W),
    (110.8, 110, 110.8, 115, "F.Cu", "/B", W), (110.8, 109.27, 112.5, 109.27, "F.Cu", "/B", W),
    (104, 109.27, 112.5, 109.27, "B.Cu", "/B", W),
]
tracks = "".join('  (segment (start %s %s) (end %s %s) (width %s) (layer "%s") (net "%s") (uuid "%s"))\n'
                 % (x1, y1, x2, y2, w, layer, net, fx.uid("seg", i))
                 for i, (x1, y1, x2, y2, layer, net, w) in enumerate(segments))
tracks += ('  (via (at 112.5 109.27) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "/B") (uuid "%s"))\n'
           % fx.uid("via", 0))
layers = ('  (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (9 "F.Adhes" user "F.Adhesive") '
          '(11 "B.Adhes" user "B.Adhesive") (13 "F.Paste" user) (15 "B.Paste" user) '
          '(5 "F.SilkS" user "F.Silkscreen") (7 "B.SilkS" user "B.Silkscreen") (1 "F.Mask" user) '
          '(3 "B.Mask" user) (25 "Edge.Cuts" user) (27 "Margin" user) (31 "F.CrtYd" user "F.Courtyard") '
          '(29 "B.CrtYd" user "B.Courtyard") (35 "F.Fab" user) (33 "B.Fab" user))\n')
doc = ('(kicad_pcb (version 20260206) (generator "pcbnew") (generator_version "10.0")\n'
       '  (general (thickness 1.6) (legacy_teardrops no))\n  (paper "A4")\n' + layers +
       '  (setup (pad_to_mask_clearance 0) (allow_soldermask_bridges_in_footprints no) (aux_axis_origin 100 120))\n'
       + "".join(fps) + tracks +
       '  (gr_rect (start 100 100) (end 130 120) (stroke (width 0.1) (type default)) (fill no) '
       '(layer "Edge.Cuts") (uuid "%s"))\n  (embedded_fonts no)\n)\n' % fx.uid("edge"))
hwcommon.write_text(OUT, doc)
project_settings.write_project(os.path.join(HW, NAME + ".kicad_pro"), DESIGN)
print("wrote", os.path.basename(OUT), "fault:", FAULT or "none")
'''


def make_project(dest, fault=""):
    """Write the fixture project into dest (created) and return dest."""
    scripts = os.path.join(dest, "scripts")
    design = os.path.join(dest, "design")
    os.makedirs(scripts)
    os.makedirs(os.path.join(dest, SKILL_DIR))
    os.makedirs(design)
    os.makedirs(os.path.join(dest, "hardware"))
    for name in COPIED:
        shutil.copy(os.path.join(SKILL_SCRIPTS, name), os.path.join(dest, SKILL_DIR, name))
    with open(os.path.join(SKILL_SCRIPTS, "build.py"), encoding="utf-8") as f:
        build = f.read()
    for marker, filled in (("FAB_ARGS = []", "FAB_ARGS = " + FAB_ARGS), ('NAME = ""', 'NAME = "%s"' % NAME)):
        assert marker in build, "build.py has no %r line to fill" % marker
        build = build.replace(marker, filled, 1)
    files = {
        SKILL_DIR + "/build.py": build,
        "scripts/fixture_parts.py": PARTS_MODULE,
        "scripts/gen_sch.py": GEN_SCH,
        "scripts/gen_pcb.py": GEN_PCB.replace("@@FAULT@@", fault),
        "design/parts.csv": PARTS_CSV,
        "design/pins.csv": PINS_CSV,
        "design/fab-capabilities.csv": FAB_CSV,
        "design/constraints.csv": CONSTRAINTS_CSV,
        "design/status.md": STATUS_MD,
        "design/decisions.md": DECISIONS_MD,
    }
    for rel, text in files.items():
        with open(os.path.join(dest, rel), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return dest


def write_pdf(path, text=PDF_TEXT):
    """A one-page PDF with `text` on it, built by hand (no library). Empty text: a page with a drawn line
    and no text layer."""
    stream = "BT /F1 18 Tf 20 50 Td (%s) Tj ET" % text if text else "10 10 m 200 80 l S"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 100] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        "<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = "%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += "%d 0 obj\n%s\nendobj\n" % (i, body)
    xref = len(out)
    out += "xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += "".join("%010d 00000 n \n" % o for o in offsets)
    out += "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    with open(path, "w", encoding="latin-1", newline="\n") as f:
        f.write(out)
    return path


# ======================================================================== HB-5 section (generator libraries)
# make_lib_project(dest) writes a second fixture project, built with the skill's own libraries:
# scripts/gen_sch.py uses schlib.py (two sheets: J1, R1 and LED D1 on the root sheet; regulator U1,
# C1, C2 and pull-up R2 on a child sheet "Power"), scripts/gen_pcb.py uses pcblib.GenBoard (a 30 x 20
# mm two-layer board with a GND zone on B.Cu, routed by the grid router). Symbols and footprints are
# KiCad's own library parts; makers and suppliers are invented.
# make_placed_board(dest, ...) (in the test, with KiCad's Python) builds a hand-style placed board.

LIB_NAME = "libfix"
LIB_COPIED = COPIED + ("schlib.py", "pcblib.py")

LIB_PARTS_CSV = """refs,value,footprint,package,manufacturer,mpn,supplier,supplier_pn,role,category,dielectric,tolerance,voltage_rating,unit_price,qty_price,stock,checked,lifecycle,temp_grade,msl,peak_reflow,alternate,variant,datasheet,datasheet_revision,errata,compliance_done,pins_done,model,model_checked
J1,Conn_01x03,Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical,THT 2.54 mm,Maker B,HDR-1X03,SUPPLIER-B,SB-3003,connector,,,,,0.10,0.08,500,2026-01-02,active,,1,,,,,,,yes,yes,,no
R1,1k,Resistor_SMD:R_0603_1608Metric,0603,Maker A,RES-1K-0603,SUPPLIER-A,SA-1002,other,,,1%,50 V,0.01,0.005,1000,2026-01-02,active,,1,,,,,,,yes,yes,,no
D1,GREEN,LED_SMD:LED_0603_1608Metric,0603,Maker C,LED-G-0603,SUPPLIER-A,SA-3001,indicator,,,,,0.02,0.01,1000,2026-01-02,active,,1,,,,,,,yes,yes,,no
U1,AMS1117-3.3,Package_TO_SOT_SMD:SOT-223-3_TabPin2,SOT-223,Maker D,REG-3V3-SOT223,SUPPLIER-A,SA-4001,regulator,,,,,0.10,0.08,1000,2026-01-02,active,,1,,,,,,,yes,yes,,no
C1;C2,10u,Capacitor_SMD:C_0805_2012Metric,0805,Maker A,CAP-10U-0805,SUPPLIER-A,SA-2001,bulk,,X7R,10%,16 V,0.02,0.01,1000,2026-01-02,active,,1,,,,,,,yes,yes,,no
R2,10k,Resistor_SMD:R_0603_1608Metric,0603,Maker A,RES-10K-0603,SUPPLIER-A,SA-1001,pull,,,1%,50 V,0.01,0.005,1000,2026-01-02,active,,1,,,,,,,yes,yes,,no
"""

LIB_CONSTRAINTS_CSV = """id,from,kind,objects,limit,enforced_by,sufficiency,standard_or_own,note
CN-001,user,width,+3V3;/Power/VIN,0.4,dru:netclass Power,whole,own figure,fixture
CN-002,user,clearance,+3V3;/Power/VIN,0.3,dru:netclass Power,whole,own figure,fixture
CN-003,user,no_vias,SENSE,0,dru:sense-no-vias,whole,own figure,fixture
"""

LIB_GEN_SCH = r'''"""Two-sheet fixture schematic (test only), written with schlib.py."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "hwskills"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import schlib  # noqa: E402

sch = schlib.Schematic(sys.argv[1], title="Two-sheet fixture", revision="A", date="2026-01-02")
top = sch.root
psu = sch.add_sheet("Power", "power.kicad_sch", at=(24, 27), size=(14, 6), pins=[("VIN", "input", "left", 2)])

# root: J1 (VIN, SENSE, GND) and the LED
j1 = top.place("Connector_Generic:Conn_01x03", "J", None, 10, 30, mirror="y")
top.wire(j1["1"], (17, 29))
top.power("PWR_FLAG", 17, 29)
top.wire((17, 29), psu.pins["VIN"])
top.wire(j1["2"], (16, 30))
top.global_label("SENSE", 16, 30, "input")
top.wire(j1["3"], (14, 31))
top.power("PWR_FLAG", 14, 31)
top.wire((14, 31), (14, 33))
top.power("GND", 14, 33)
top.power("+3V3", 50, 26)
top.wire((50, 26), (50, 27))
r1 = top.place("Device:R", "R", None, 50, 28.5)
top.wire(r1["2"], (50, 31))
d1 = top.place("Device:LED", "D", None, 50, 32.5, rot=90)
top.wire(d1["K"], (50, 35))
top.power("GND", 50, 35)
top.frame("CONNECTOR AND INDICATOR", 4, 22, 60, 40)

# child sheet: the regulator
psu.hier_label("VIN", 10, 20, "input", right=True)
psu.wire((10, 20), (16, 20), (20, 20))
psu.junction(16, 20)
u1 = psu.place("Regulator_Linear:AMS1117-3.3", "U", None, 23, 20, fields="lib")
c1 = psu.place("Device:C", "C", None, 16, 21.5)
psu.wire(c1["2"], (16, 24))
psu.power("GND", 16, 24)
psu.wire(u1["GND"], (23, 24))
psu.power("GND", 23, 24)
psu.wire(u1["VO"], (30, 20))
c2 = psu.place("Device:C", "C", None, 30, 21.5)
psu.wire((30, 20), (30, 18))
psu.junction(30, 20)
psu.power("+3V3", 30, 18)
psu.wire(c2["2"], (30, 24))
psu.power("GND", 30, 24)
psu.power("+3V3", 36, 17)
psu.wire((36, 17), (36, 18))
r2 = psu.place("Device:R", "R", None, 36, 19.5)
psu.wire(r2["2"], (36, 22), (39, 22))
psu.global_label("SENSE", 39, 22, "input")
psu.frame("POWER", 6, 14, 44, 27)
@@SCH_FAULT@@
sys.exit(sch.finish())
'''

LIB_GEN_PCB = r'''"""Fixture board generator (test only), written with pcblib.py: place, route, label, DRC."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "hwskills"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcblib  # noqa: E402

PLACE = {                                   # mm from the outline's top-left corner
    "J1": (3, 5, 0), "C1": (8, 9, 90), "U1": (14, 9, 0), "C2": (20, 9, 90),
    "R1": (25, 5, 90), "D1": (25, 11, 90), "R2": (9, 16, 0),
}
b = pcblib.GenBoard(sys.argv[2], sys.argv[1], seed=20260102, title="Two-sheet fixture", revision="A",
                    date="2026-01-02")
b.outline(0, 0, 30, 20)
b.place_table(PLACE)
b.zone("GND", "B.Cu", [(0.5, 0.5), (29.5, 0.5), (29.5, 19.5), (0.5, 19.5)], name="GND plane")
@@PCB_FAULT@@
b.route()
sys.exit(b.finish())
'''

LIB_STATUS_MD = """Designs: logical agreed; electrical in review; physical in review
Ownership: schematic script; board script (detail in ownership.csv)
Expected DRC notes: none
Skills version: hw-skills 0.1.0; scripts copied 2026-01-02
"""


def make_lib_project(dest, sch_fault="", pcb_fault=""):
    """Write the library fixture project into dest (created) and return dest. The faults are lines of
    Python put into the generators (empty: none)."""
    scripts = os.path.join(dest, "scripts")
    design = os.path.join(dest, "design")
    os.makedirs(scripts)
    os.makedirs(os.path.join(dest, SKILL_DIR))
    os.makedirs(design)
    os.makedirs(os.path.join(dest, "hardware"))
    for name in LIB_COPIED:
        shutil.copy(os.path.join(SKILL_SCRIPTS, name), os.path.join(dest, SKILL_DIR, name))
    with open(os.path.join(SKILL_SCRIPTS, "build.py"), encoding="utf-8") as f:
        build = f.read()
    fab_args = '["--date", "2026-01-02"]'
    for marker, filled in (("FAB_ARGS = []", "FAB_ARGS = " + fab_args), ('NAME = ""', 'NAME = "%s"' % LIB_NAME)):
        assert marker in build, "build.py has no %r line to fill" % marker
        build = build.replace(marker, filled, 1)
    files = {
        SKILL_DIR + "/build.py": build,
        "scripts/gen_sch.py": LIB_GEN_SCH.replace("@@SCH_FAULT@@", sch_fault),
        "scripts/gen_pcb.py": LIB_GEN_PCB.replace("@@PCB_FAULT@@", pcb_fault),
        "design/parts.csv": LIB_PARTS_CSV,
        "design/pins.csv": PINS_CSV.splitlines()[0] + "\n",
        "design/fab-capabilities.csv": FAB_CSV,
        "design/constraints.csv": LIB_CONSTRAINTS_CSV,
        "design/status.md": LIB_STATUS_MD,
        "design/decisions.md": DECISIONS_MD,
    }
    for rel, text in files.items():
        with open(os.path.join(dest, rel), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return dest
# ======================================================================== end of HB-5 section


# ======================================================================== HB-6 section (check scripts)
# make_check_project(dest, fault="") writes a project for sch_check.py, table_check.py and board_check.py
# as KiCad files written directly (netlist, schematic library symbols, board with zones and fills), so
# the fixture-only tests need no KiCad. Every part, supplier and number is invented.
#
# The circuit: U1 buck (VIN, SW, GND exposed pad, FB, EN) with C1, C2, L1, R1/R2 feedback and R3 enable
# pull-up; U2 microcontroller (SWD, UART, I2C, GPIO); U3 boost whose EN (control input) is pulled down
# by R4; U4 sensor with an open-drain interrupt pulled up by R5 and I2C pulls R6/R7; J1 power input with
# D1 across it; J2 debug and UART header with no protection; TP1 on +3V3.
#
# Seeded faults (make_check_project(..., fault=...)):
#   pin_swap               U2 pins 6 and 7 (TX, RX) swapped in the netlist.
#   floating_enable        R4, the pull-down on U3's enable, removed.
#   no_int_pull            R5, the pull-up on the interrupt line, removed.
#   layout_no_constraint   a carried layout row (DS-019) with no constraint.
#   same_island_only       DS-010 (single point) enforced only by same_island CN-001, marked whole.
#   rule_no_source         the min_track capability row has no source.
#   pad_off_island         C2 moved, so its ground pad is off U1's ground island.
#   part_swapped           U1 now has MPN BUCK-2 in the schematic and netlist; the rows say BUCK-1.

CHECK_NAME = "check"
CHECK_SCRIPTS = ("hwcommon.py", "kicad_env.py", "project_settings.py", "kicad_pro_defaults.json",
                 "sch_check.py", "table_check.py", "board_check.py", "worstcase.py")

# footprint name -> pads (number, kind, x, y, w, h); kind smd or thru_hole
CHECK_FOOTPRINTS = {
    "R_0603": [("1", "smd", -0.8, 0, 0.9, 0.95), ("2", "smd", 0.8, 0, 0.9, 0.95)],
    "C_0603": [("1", "smd", -0.8, 0, 0.9, 0.95), ("2", "smd", 0.8, 0, 0.9, 0.95)],
    "C_1206": [("1", "smd", -1.4, 0, 1.0, 1.6), ("2", "smd", 1.4, 0, 1.0, 1.6)],
    "L_4x4": [("1", "smd", -1.6, 0, 1.2, 3.4), ("2", "smd", 1.6, 0, 1.2, 3.4)],
    "D_SMB": [("1", "smd", -2.0, 0, 1.6, 2.2), ("2", "smd", 2.0, 0, 1.6, 2.2)],
    "BUCK5_EP": [("1", "smd", -1.5, -1.0, 0.6, 0.5), ("2", "smd", -1.5, 0, 0.6, 0.5), ("3", "smd", 0, 0, 1.6, 1.6),
                 ("4", "smd", 1.5, -1.0, 0.6, 0.5), ("5", "smd", 1.5, 0, 0.6, 0.5)],
    "SOT23_4": [("1", "smd", -1.1, -0.95, 0.9, 0.6), ("2", "smd", -1.1, 0.95, 0.9, 0.6),
                ("3", "smd", 1.1, 0.95, 0.9, 0.6), ("4", "smd", 1.1, -0.95, 0.9, 0.6)],
    "SENS5": [("%d" % (i + 1), "smd", -1.5 + 0.75 * i, 0, 0.45, 1.0) for i in range(5)],
    "MCU12": [("%d" % (i + 1), "smd", -2.0, -2.5 + i, 1.0, 0.5) for i in range(6)]
    + [("%d" % (i + 7), "smd", 2.0, 2.5 - i, 1.0, 0.5) for i in range(6)],
    "PinHeader_1x02": [("1", "thru_hole", 0, 0, 1.7, 1.7), ("2", "thru_hole", 0, 2.54, 1.7, 1.7)],
    "PinHeader_1x06_P1.27": [("%d" % (i + 1), "thru_hole", 0, 1.27 * i, 1.0, 1.0) for i in range(6)],
    "TestPoint_1": [("1", "smd", 0, 0, 1.5, 1.5)],
}

# ref, value, footprint, MPN, symbol, place (x, y, rotation), pins [(number, name, type, net)]
CHECK_PARTS = [
    ("C1", "10u", "C_1206", "CAP-10U-1206", "C", (106, 113, 0), [("1", "", "passive", "+VIN"), ("2", "", "passive", "GND")]),
    ("C2", "22u", "C_1206", "CAP-22U-1206", "C", (114, 113, 180), [("1", "", "passive", "+3V3"), ("2", "", "passive", "GND")]),
    ("C3", "100n", "C_0603", "CAP-100N-0603", "C", (121, 107.5, 180), [("1", "", "passive", "+3V3"),
                                                                     ("2", "", "passive", "GND")]),
    ("D1", "TVS", "D_SMB", "TVS-SMB-1", "D", (104, 120, 0), [("1", "K", "passive", "+VIN"), ("2", "A", "passive", "GND")]),
    ("J1", "PWR", "PinHeader_1x02", "HDR-1X02", "Conn_2", (101.5, 112, 0), [("1", "", "passive", "+VIN"),
                                                                          ("2", "", "passive", "GND")]),
    ("J2", "DEBUG", "PinHeader_1x06_P1.27", "HDR-1X06-127", "Conn_6", (137, 103, 0),
     [("1", "", "passive", "+3V3"), ("2", "", "passive", "/SWDIO"), ("3", "", "passive", "/SWCLK"),
      ("4", "", "passive", "/TX"), ("5", "", "passive", "/RX"), ("6", "", "passive", "GND")]),
    ("L1", "4.7u", "L_4x4", "IND-4U7", "L", (106, 106, 0), [("1", "", "passive", "/SW"), ("2", "", "passive", "+3V3")]),
    ("R1", "100k", "R_0603", "RES-100K-0603", "R", (113.5, 105, 0), [("1", "", "passive", "+3V3"), ("2", "", "passive", "/FB")]),
    ("R2", "22k", "R_0603", "RES-22K-0603", "R", (113.5, 107, 0), [("1", "", "passive", "/FB"), ("2", "", "passive", "GND")]),
    ("R3", "100k", "R_0603", "RES-100K-0603", "R", (116, 110, 90), [("1", "", "passive", "+VIN"), ("2", "", "passive", "/EN")]),
    ("R4", "100k", "R_0603", "RES-100K-0603", "R", (132, 124, 0), [("1", "", "passive", "/BOOST_EN"),
                                                                  ("2", "", "passive", "GND")]),
    ("R5", "10k", "R_0603", "RES-10K-0603", "R", (128, 124, 0), [("1", "", "passive", "+3V3"), ("2", "", "passive", "/INT")]),
    ("R6", "4k7", "R_0603", "RES-4K7-0603", "R", (121, 124, 0), [("1", "", "passive", "+3V3"), ("2", "", "passive", "/SCL")]),
    ("R7", "4k7", "R_0603", "RES-4K7-0603", "R", (121, 126, 0), [("1", "", "passive", "+3V3"), ("2", "", "passive", "/SDA")]),
    ("TP1", "TP", "TestPoint_1", "TP-PAD", "TP", (118, 118, 0), [("1", "1", "passive", "+3V3")]),
    ("U1", "BUCK-1", "BUCK5_EP", "BUCK-1", "BUCK", (110, 110, 0),
     [("1", "VIN", "power_in", "+VIN"), ("2", "SW", "output", "/SW"), ("3", "GND", "power_in", "GND"),
      ("4", "FB", "input", "/FB"), ("5", "EN", "input", "/EN")]),
    ("U2", "MCU", "MCU12", "STM32X001AXT6", "MCU", (125, 110, 0),
     [("1", "VDD", "power_in", "+3V3"), ("2", "VSS", "power_in", "GND"), ("3", "NRST", "input", ""),
      ("4", "PA0", "bidirectional", "/BOOST_EN"), ("5", "PA1", "bidirectional", "/INT"),
      ("6", "PA2", "bidirectional", "/TX"), ("7", "PA3", "bidirectional", "/RX"),
      ("8", "PA13", "bidirectional", "/SWDIO"), ("9", "PA14", "bidirectional", "/SWCLK"),
      ("10", "PB6", "bidirectional", "/SCL"), ("11", "PB7", "bidirectional", "/SDA"), ("12", "PA4", "bidirectional", "")]),
    ("U3", "BOOST-1", "SOT23_4", "BOOST-1", "BOOST", (132, 120, 0),
     [("1", "IN", "power_in", "+3V3"), ("2", "GND", "power_in", "GND"), ("3", "EN", "input", "/BOOST_EN"),
      ("4", "OUT", "power_out", "+5V")]),
    ("U4", "SENSE-1", "SENS5", "SENSE-1", "SENSE", (125, 120, 0),
     [("1", "VDD", "power_in", "+3V3"), ("2", "GND", "power_in", "GND"), ("3", "SCL", "input", "/SCL"),
      ("4", "SDA", "bidirectional", "/SDA"), ("5", "INT", "open_collector", "/INT")]),
]
CHECK_HIDDEN = {("U4", "2")}       # a hidden ground pin on the sensor symbol

CHECK_PARTS_CSV = """refs,value,footprint,package,manufacturer,mpn,supplier,supplier_pn,role,category,dielectric,tolerance,voltage_rating,unit_price,qty_price,stock,checked,lifecycle,temp_grade,msl,peak_reflow,alternate,variant,datasheet,datasheet_revision,errata,compliance_done,pins_done,model,model_checked
C1,10u,fixture:C_1206,1206,Maker C,CAP-10U-1206,SUPPLIER-A,SA-3001,bulk,,X7R,10%,50 V,0.05,0.04,900,2026-01-02,active,,1,260,,,,,,yes,yes,,no
C2,22u,fixture:C_1206,1206,Maker C,CAP-22U-1206,SUPPLIER-A,SA-3002,bulk,,X5R,10%,10 V,0.06,0.05,900,2026-01-02,active,,1,260,,,,,,yes,yes,,no
C3,100n,fixture:C_0603,0603,Maker C,CAP-100N-0603,SUPPLIER-A,SA-3003,decoupling,,X7R,10%,16 V,0.01,0.01,900,2026-01-02,active,,1,260,,,,,,yes,yes,,no
D1,TVS,fixture:D_SMB,SMB,Maker D,TVS-SMB-1,SUPPLIER-A,SA-3004,protection,,,,58 V,0.20,0.15,900,2026-01-02,active,,1,260,,,,,,yes,yes,,no
J1,PWR,fixture:PinHeader_1x02,1x02,Maker B,HDR-1X02,SUPPLIER-B,SB-2002,connector,,,,,0.10,0.08,500,2026-01-02,active,,1,260,,,,,,yes,yes,,no
J2,DEBUG,fixture:PinHeader_1x06_P1.27,1x06,Maker B,HDR-1X06-127,SUPPLIER-B,SB-2006,connector,,,,,0.20,0.15,500,2026-01-02,active,,1,260,,,,,,yes,yes,,no
L1,4.7u,fixture:L_4x4,4x4,Maker E,IND-4U7,SUPPLIER-A,SA-3005,other,,,20%,,0.15,0.12,900,2026-01-02,active,,1,260,,,,,,yes,yes,,no
R1;R3;R4,100k,fixture:R_0603,0603,Maker A,RES-100K-0603,SUPPLIER-A,SA-1100,pull,,,1%,50 V,0.01,0.005,1000,2026-01-02,active,,1,260,,,,,,yes,yes,,no
R2,22k,fixture:R_0603,0603,Maker A,RES-22K-0603,SUPPLIER-A,SA-1022,other,,,1%,50 V,0.01,0.005,1000,2026-01-02,active,,1,260,,,,,,yes,yes,,no
R5,10k,fixture:R_0603,0603,Maker A,RES-10K-0603,SUPPLIER-A,SA-1001,pull,,,1%,50 V,0.01,0.005,1000,2026-01-02,active,,1,260,,,,,,yes,yes,,no
R6;R7,4k7,fixture:R_0603,0603,Maker A,RES-4K7-0603,SUPPLIER-A,SA-1047,pull,,,1%,50 V,0.01,0.005,1000,2026-01-02,active,,1,260,,,,,,yes,yes,,no
TP1,TP,fixture:TestPoint_1,,Maker F,TP-PAD,SUPPLIER-A,SA-3006,other,,,,,0.00,0.00,900,2026-01-02,active,,1,260,,,,,,yes,yes,,no
U1,BUCK-1,fixture:BUCK5_EP,BUCK5,Maker G,BUCK-1,SUPPLIER-A,SA-4001,regulator,switching converter,,,60 V,0.90,0.80,300,2026-01-02,active,,3,260,,,,A,none published (2026-01-02),yes,yes,,no
U2,MCU,fixture:MCU12,MCU12,Maker H,STM32X001AXT6,SUPPLIER-A,SA-4002,other,microcontroller,,,3.6 V,1.10,0.95,300,2026-01-02,active,,3,260,,,,B,errata sheet 2 (2026-01-02),yes,yes,,no
U3,BOOST-1,fixture:SOT23_4,SOT-23,Maker G,BOOST-1,SUPPLIER-A,SA-4003,regulator,switching converter,,,6 V,0.40,0.35,300,2026-01-02,active,,3,260,,,,A,none published (2026-01-02),yes,yes,,no
U4,SENSE-1,fixture:SENS5,SENS5,Maker J,SENSE-1,SUPPLIER-A,SA-4004,sensor,,,,3.6 V,0.70,0.60,300,2026-01-02,active,,3,260,,,,A,none published (2026-01-02),yes,yes,,no
"""

CHECK_PINS_CSV = """designator,mpn,pin,name,functions,used_function,net,supply,levels,abs_max,current_limit,reset_state,boot_activity,control_input,required_in_reset,given_by,sleep_state,fault_state,source,source_page,confirmed
D1,TVS-SMB-1,1,K,cathode,cathode,+VIN,,,,,,,no,,,,,datasheet table,1,yes
D1,TVS-SMB-1,2,A,anode,anode,GND,,,,,,,no,,,,,datasheet table,1,yes
J1,HDR-1X02,1,1,contact,contact,+VIN,,,,,,,no,,,,,datasheet table,1,yes
J1,HDR-1X02,2,2,contact,contact,GND,,,,,,,no,,,,,datasheet table,1,yes
J2,HDR-1X06-127,1,1,contact,contact,+3V3,,,,,,,no,,,,,datasheet table,1,yes
J2,HDR-1X06-127,2,2,contact,contact,/SWDIO,,,,,,,no,,,,,datasheet table,1,yes
J2,HDR-1X06-127,3,3,contact,contact,/SWCLK,,,,,,,no,,,,,datasheet table,1,yes
J2,HDR-1X06-127,4,4,contact,contact,/TX,,,,,,,no,,,,,datasheet table,1,no
J2,HDR-1X06-127,5,5,contact,contact,/RX,,,,,,,no,,,,,datasheet table,1,no
J2,HDR-1X06-127,6,6,contact,contact,GND,,,,,,,no,,,,,datasheet table,1,yes
U1,BUCK-1,1,VIN,supply,supply,+VIN,VIN,,65 V,,,,no,,,,,datasheet table,3,yes
U1,BUCK-1,2,SW,switch node,switch node,/SW,VIN,,65 V,,,,no,,,,,datasheet table,3,yes
U1,BUCK-1,3,GND,ground,ground,GND,,,,,,,no,,,,,datasheet table,3,yes
U1,BUCK-1,4,FB,feedback,feedback,/FB,,,,,,,no,,,,,datasheet table,3,yes
U1,BUCK-1,5,EN,enable,enable,/EN,VIN,,65 V,,,,yes,on,R3 pull-up,on,on,datasheet table,3,yes
U2,STM32X001AXT6,1,VDD,power,power,+3V3,3V3,,4 V,,,,no,,,,,vendor data,,yes
U2,STM32X001AXT6,2,VSS,ground,ground,GND,,,,,,,no,,,,,vendor data,,yes
U2,STM32X001AXT6,3,NRST,reset,reset,,3V3,,,,internal pull-up,,no,,,,,vendor data,,yes
U2,STM32X001AXT6,4,PA0,GPIO;TIM2_CH1;ADC_IN0,GPIO,/BOOST_EN,3V3,,4 V,,input floating,none,no,,,,,vendor data,,yes
U2,STM32X001AXT6,5,PA1,GPIO;GPIO_EXTI1;ADC_IN1,GPIO_EXTI1,/INT,3V3,,4 V,,input floating,none,no,,,,,vendor data,,yes
U2,STM32X001AXT6,6,PA2,GPIO;USART2_TX;ADC_IN2,USART2_TX,/TX,3V3,,4 V,,input floating,none,no,,,,,vendor data,,no
U2,STM32X001AXT6,7,PA3,GPIO;USART2_RX;ADC_IN3,USART2_RX,/RX,3V3,,4 V,,input floating,none,no,,,,,vendor data,,no
U2,STM32X001AXT6,8,PA13,GPIO;SWDIO,SWDIO,/SWDIO,3V3,,4 V,,internal pull-up,none,no,,,,,vendor data,,yes
U2,STM32X001AXT6,9,PA14,GPIO;SWCLK,SWCLK,/SWCLK,3V3,,4 V,,internal pull-down,none,no,,,,,vendor data,,yes
U2,STM32X001AXT6,10,PB6,GPIO;I2C1_SCL;USART1_TX,I2C1_SCL,/SCL,3V3,open-drain,4 V,,input floating,none,no,,,,,vendor data,,yes
U2,STM32X001AXT6,11,PB7,GPIO;I2C1_SDA;USART1_RX,I2C1_SDA,/SDA,3V3,open-drain,4 V,,input floating,none,no,,,,,vendor data,,yes
U2,STM32X001AXT6,12,PA4,GPIO;ADC_IN4,unused,,3V3,,4 V,,input floating,none,no,,,,,vendor data,,yes
U3,BOOST-1,1,IN,supply,supply,+3V3,3V3,,6 V,,,,no,,,,,datasheet table,2,yes
U3,BOOST-1,2,GND,ground,ground,GND,,,,,,,no,,,,,datasheet table,2,yes
U3,BOOST-1,3,EN,enable,enable,/BOOST_EN,3V3,,6 V,,,,yes,off,R4 pull-down,off,off,datasheet table,2,yes
U3,BOOST-1,4,OUT,output,output,+5V,5V,,6 V,,,,no,,,,,datasheet table,2,yes
U4,SENSE-1,1,VDD,supply,supply,+3V3,3V3,,4 V,,,,no,,,,,datasheet table,4,yes
U4,SENSE-1,2,GND,ground,ground,GND,,,,,,,no,,,,,datasheet table,4,yes
U4,SENSE-1,3,SCL,I2C clock,I2C clock,/SCL,3V3,open-drain,4 V,,,,no,,,,,datasheet table,4,yes
U4,SENSE-1,4,SDA,I2C data,I2C data,/SDA,3V3,open-drain,4 V,,,,no,,,,,datasheet table,4,yes
U4,SENSE-1,5,INT,interrupt,interrupt,/INT,3V3,open-drain,4 V,,,,no,,,,,datasheet table,4,yes
"""

CHECK_COMPLIANCE_CSV = """id,designator,mpn,datasheet,revision,section,page,figure,kind,category,perspective,text,design_value,margin,schematic_result,board_result,decision,carried_to,evidence,found_by
DS-001,U1,BUCK-1,BUCK-1.pdf,A,6 Absolute maximum ratings,2,,limit,absolute-maximum,electrical,"VIN to GND: 65 V maximum",58 V clamp,7 V,met,,,,D1 clamps at 58 V,pass
DS-002,U1,BUCK-1,BUCK-1.pdf,A,8 Typical application,12,Figure 7,graph,typical-application,electrical,"Efficiency against load current",,,met,,,,read from the rendered page,pass
DS-003,,BUCK-1,BUCK-1.pdf,A,8 Typical application,12,,should,protection,electrical,"An input fuse should be fitted",none,,not met,,DC-001,,decision DC-001,pass
DS-010,U1,BUCK-1,BUCK-1.pdf,A,7.4 Layout guidelines,10,,must,grounding,physical,"Connect the capacitor grounds and the exposed pad on one top-layer island; join it to the ground plane at a single point under the device",,,carried,open,,CN-001;CN-002,,pass
DS-011,U1,BUCK-1,BUCK-1.pdf,A,7.4 Layout guidelines,10,,should,layout,physical,"Keep the ground plane unbroken under the converter",,,carried,open,,CN-003,,pass
DS-012,U1,BUCK-1,BUCK-1.pdf,A,7.4 Layout guidelines,10,,recommend,layout,physical,"Place a thermal via in the exposed pad",,,carried,open,,CN-004;CN-012,,pass
DS-013,U1,BUCK-1,BUCK-1.pdf,A,7.4 Layout guidelines,10,,must,layout,physical,"Place the input capacitor close to VIN",,,carried,open,,CN-005,,pass
DS-014,U1,BUCK-1,BUCK-1.pdf,A,7.4 Layout guidelines,11,,should,layout,physical,"Route the feedback trace away from the switch node",,,carried,open,,CN-006,,pass
DS-015,U2,STM32X001AXT6,STM32X001AXT6.pdf,B,5 Power supply,30,,must,layout,physical,"Place a 100 nF capacitor at each VDD pin",,,carried,open,,CN-007,,pass
DS-016,U4,SENSE-1,SENSE-1.pdf,A,9 Layout,8,,should,layout,physical,"Keep the area at the board corner free of copper",,,carried,open,,CN-008,,pass
DS-017,C3,CAP-100N-0603,CAP-100N-0603.pdf,A,4 Mounting,2,,recommend,layout,physical,"Keep class 2 ceramic capacitors away from the board edge",,,carried,open,,CN-011,,pass
DS-018,U4,SENSE-1,SENSE-1.pdf,A,9 Layout,8,,should,layout,physical,"Orient the sensor so its port faces the board edge",,,carried,open,,CN-014,,pass
"""

CHECK_SECTIONS_CSV = """datasheet,revision,section,title,pages,category,claimed_by,rows_logical,rows_electrical,rows_physical,note
BUCK-1.pdf,A,6,Absolute maximum ratings,2,absolute-maximum,electrical,0,1,0,
BUCK-1.pdf,A,7.4,Layout guidelines,10-11,layout,physical,0,0,5,
BUCK-1.pdf,A,8,Typical application,12,typical-application,electrical,0,2,0,
BUCK-1.pdf,A,9,Thermal information,13,thermal,electrical;physical,0,0,0,no instructions here (BR-01-01; 2026-01-02)
STM32X001AXT6.pdf,B,5,Power supply,30,power-supply,electrical;physical,0,0,1,
SENSE-1.pdf,A,9,Layout,8,layout,physical,0,0,2,
CAP-100N-0603.pdf,A,4,Mounting,2,assembly,physical,0,0,1,
"""

CHECK_CONSTRAINTS_CSV = """id,from,kind,objects,limit,enforced_by,sufficiency,standard_or_own,note
CN-001,DS-010,same_island,"C1.2; C2.2; U1.3; layer:F.Cu",-,check:same_island CN-001,partial; whole with CN-002,datasheet,
CN-002,DS-010,single_point,"U1.3; layer:F.Cu; in:U1.3",-,check:single_point CN-002,whole (BR-01-01),datasheet,
CN-003,DS-011,plane_one_piece,zone:GND_PLANE,-,check:plane_one_piece CN-003,whole,datasheet,
CN-004,DS-012,via_count,"U1.3; within:0.5",1,check:via_count CN-004,whole,datasheet,
CN-005,DS-013,distance,"U1.1; C1.1",5,check:distance CN-005,whole,datasheet,
CN-006,DS-014,noisy_distance,"U1.4; R2; noisy:/SW",1.5,check:noisy_distance CN-006,whole,datasheet,
CN-007,DS-015,decouple_per_pin,U2.1=C3,1,check:decouple_per_pin CN-007,whole,datasheet,
CN-008,DS-016,keepout,"area:134,124,140,130; layer:F.Cu",-,check:keepout CN-008,whole,datasheet,
CN-009,user,net_length,/SWDIO,20,check:net_length CN-009,whole,own figure,
CN-010,user,ref_plane,"/SWDIO; plane:GND on B.Cu",0.5,check:ref_plane CN-010,whole,own figure,plane cut-out at the header pad
CN-011,DS-017,edge_distance,dielectric:class2,1,check:edge_distance CN-011,whole,datasheet,
CN-012,DS-012,via_in_pad,U1,1,check:via_in_pad CN-012,whole,datasheet,
CN-013,user,clearance,+VIN,0.4,dru:netclass Power,whole,own figure,battery side
CN-014,DS-018,placement,U4,-,review:BD-07,whole with a verdict per row,datasheet,no sub-command reads the port direction
"""

CHECK_FAB_CSV = """item,manufacturer_value,source_url,read_on,service_level,rule_value,note
min_track,0.09,from user,2026-01-02,standard,0.127,
min_clearance,0.09,from user,2026-01-02,standard,0.127,
min_via_diameter,0.25,from user,2026-01-02,standard,0.45,
min_via_drill,0.15,from user,2026-01-02,standard,0.2,
edge_clearance,0.2,from user,2026-01-02,standard,0.3,
assembly_msl_limit,3,from user,2026-01-02,assembly,,
assembly_peak_reflow,250,from user,2026-01-02,assembly,,
assembly_fee_extended_part,3,from user,2026-01-02,assembly,,per extended part
"""

CHECK_REQUIREMENTS_MD = """# Requirements: check fixture
## Functional requirements
FR-01 Convert the input to 3.3 V. Source: user, 2026-01-02, "3.3 V out".
      Evidence: DS-001 met; sch_check powerup pass
## Quality characteristics
QC-01 Cost: parts under 10 at quantity 10. Source: user.
## Environment profile
Supplies it might see: 12 V bench supply (user)
## Misuse cases
Reverse input: D1 clamps (proposed, to confirm)
## User journey
power up: FR-01
## Board profile
- Switching converter; on; part choice (U1, U3)
- Microcontroller; on; part choice (U2)
- Radio; off; user answer
## Test points
- +3V3: bench
"""

CHECK_STATUS_MD = """Designs: logical agreed; electrical in review; physical in review
Ownership: schematic hand; board hand
Tools: KiCad 10.0; Python 3
Expected DRC notes: none
Review baselines: schematic review BR-01-01 at 0000000; board review BR-02-01 at 0000000
Skills version: hw-skills 0.1.0; scripts copied 2026-01-02
"""

CHECK_DECISIONS_MD = """# Decisions

## No input fuse on the bench board (DC-001)
Kind: decision
Decided by: user
Date: 2026-01-02
Stage: ST5
Options: no fuse (chosen); a fuse at the input
Reason: the bench supply is current limited (DS-003, proposed by a worker)
Affects: requirements none; parts no fuse; schematic input; board none; cost lower
Status: in force

## Waive nothing yet, kept for the summary count (DC-002)
Kind: waiver
Decided by: coordinator; seen by user: yes, 2026-01-02
Date: 2026-01-02
Stage: ST11
Options: keep it open (chosen)
Reason: the summary test counts one open waiver
Affects: requirements none; parts none; schematic none; board none; cost none
Status: in force
"""

CHECK_REPORT_MD = """# Report BR-02-01: board review
## 6 Per-row verdicts (board reviews): each review-enforced CN- with met / not met / cannot tell, and evidence
CN-014 met: U4 at (125, 120), rotation 0, port side towards the board edge (board file)
## 12 Checklist additions proposed
Results: BD-07 met; SC-01 met
"""

CHECK_CHECKLIST_MD = """# Board checklist (project copy)
| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| BD-07 | Placement per the datasheet | datasheets | ST9, ST11 | none | always |
| SC-01 | Switch node small | converter datasheet | ST10 | board_check.py | Switching converter |
| RM-01 | Antenna keep-out | module guide | ST8 | board_check.py | Radio |
"""

CHECK_FINDINGS_CSV = """id,report,severity,category,location,text,source,status,decision
FD-001,BR-02-01,4,remark,U4,"label the sensor port on the silkscreen",reviewer side remark,open,
"""

CHECK_ST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Mcu xmlns="urn:fixture:mcu" RefName="STM32X001AXTx" Package="TEST12" Family="STM32X0" DBVersion="V9.9">
  <Pin Name="VDD" Position="1" Type="Power"/>
  <Pin Name="VSS" Position="2" Type="Power"/>
  <Pin Name="NRST" Position="3" Type="Reset"/>
  <Pin Name="PA0" Position="4" Type="I/O"><Signal Name="TIM2_CH1"/><Signal Name="ADC_IN0"/><Signal Name="GPIO"/></Pin>
  <Pin Name="PA1" Position="5" Type="I/O"><Signal Name="ADC_IN1"/><Signal Name="GPIO"/></Pin>
  <Pin Name="PA2" Position="6" Type="I/O"><Signal Name="USART2_TX"/><Signal Name="ADC_IN2"/><Signal Name="GPIO"/></Pin>
  <Pin Name="PA3" Position="7" Type="I/O"><Signal Name="USART2_RX"/><Signal Name="ADC_IN3"/><Signal Name="GPIO"/></Pin>
  <Pin Name="PA13" Position="8" Type="I/O"><Signal Name="SYS_SWDIO"/><Signal Name="SWDIO"/><Signal Name="GPIO"/></Pin>
  <Pin Name="PA14" Position="9" Type="I/O"><Signal Name="SYS_SWCLK"/><Signal Name="SWCLK"/><Signal Name="GPIO"/></Pin>
  <Pin Name="PB6" Position="10" Type="I/O"><Signal Name="I2C1_SCL"/><Signal Name="USART1_TX"/><Signal Name="GPIO"/></Pin>
  <Pin Name="PB7" Position="11" Type="I/O"><Signal Name="I2C1_SDA"/><Signal Name="USART1_RX"/><Signal Name="GPIO"/></Pin>
  <Pin Name="PA4" Position="12" Type="I/O"><Signal Name="ADC_IN4"/><Signal Name="GPIO"/></Pin>
</Mcu>
"""

# Copper the fixture board carries besides the pads: tracks (x1, y1, x2, y2, layer, net, width) and vias.
CHECK_TRACKS = [
    (127, 111.5, 130, 111.5, "F.Cu", "/SWDIO", 0.2), (130, 111.5, 130, 104.27, "F.Cu", "/SWDIO", 0.2),
    (130, 104.27, 137, 104.27, "F.Cu", "/SWDIO", 0.2),
    (104.4, 106, 104.4, 108.6, "F.Cu", "/SW", 0.4), (104.4, 108.6, 106.8, 110, "F.Cu", "/SW", 0.4),
    (106.8, 110, 108.5, 110, "F.Cu", "/SW", 0.4),
]
CHECK_VIAS = [(110, 110, "GND")]
# U1's top-layer ground island, and the bottom ground plane (outline = fill, so the fixture needs no pour).
CHECK_ISLAND = [(106.5, 112.4), (109.4, 112.4), (109.4, 110.0), (110.6, 110.0), (110.6, 112.4), (113.5, 112.4),
                (113.5, 113.6), (106.5, 113.6)]
CHECK_PLANE = [(100.5, 100.5), (139.5, 100.5), (139.5, 129.5), (100.5, 129.5)]


def _uid(*key):
    import uuid
    return str(uuid.uuid5(uuid.UUID("6f1c2a0e-5b1d-4c39-9a51-0d6c1f00a006"), "/".join(str(k) for k in key)))


def _check_parts(fault):
    parts = []
    for ref, value, fp, mpn, sym, place, pins in CHECK_PARTS:
        if (fault == "floating_enable" and ref == "R4") or (fault == "no_int_pull" and ref == "R5"):
            continue
        if fault == "part_swapped" and ref == "U1":
            mpn = "BUCK-2"
        if fault == "pad_off_island" and ref == "C2":
            place = (114, 118, 180)
        if fault == "pin_swap" and ref == "U2":
            pins = [(n, name, t, {"6": "/RX", "7": "/TX"}.get(n, net)) for n, name, t, net in pins]
        parts.append((ref, value, fp, mpn, sym, place, pins))
    return parts


def _q(text):
    return '"%s"' % text.replace("\\", "\\\\").replace('"', '\\"')


def _check_netlist(parts):
    comps, libparts, nets = [], {}, {}
    for ref, value, fp, mpn, sym, place, pins in parts:
        fields = [("Manufacturer", "Maker"), ("MPN", mpn), ("Supplier", "SUPPLIER-A"), ("Supplier PN", "SA-0")]
        comps.append(
            "    (comp (ref %s) (value %s) (footprint %s)\n      (fields %s)\n      (libsource (lib \"fx\") (part %s) "
            "(description \"fixture part\"))\n%s      (sheetpath (names \"/\") (tstamps \"/\")) (tstamps %s)\n"
            "      (units (unit (name \"A\") (pins %s))))\n"
            % (_q(ref), _q(value), _q("fixture:" + fp), " ".join("(field (name %s) %s)" % (_q(k), _q(v)) for k, v in fields),
               _q(sym), "".join("      (property (name %s) (value %s))\n" % (_q(k), _q(v)) for k, v in fields),
               _q(_uid("sym", ref)), " ".join("(pin (num %s))" % _q(p[0]) for p in pins)))
        libparts[sym] = pins
        for num, name, ptype, net in pins:
            nets.setdefault(net or "unconnected-(%s-Pad%s)" % (ref, num), []).append((ref, num, name, ptype))
    lp = "".join("    (libpart (lib \"fx\") (part %s) (pins %s))\n"
                 % (_q(sym), " ".join("(pin (num %s) (name %s) (type %s))" % (_q(n), _q(nm), _q(t)) for n, nm, t, _ in pins))
                 for sym, pins in sorted(libparts.items()))
    ns = "".join("    (net (code \"%d\") (name %s) (class \"Default\") %s)\n"
                 % (i + 1, _q(name), " ".join("(node (ref %s) (pin %s) (pinfunction %s) (pintype %s))"
                                               % (_q(r), _q(p), _q(f), _q(t)) for r, p, f, t in sorted(nodes)))
                 for i, (name, nodes) in enumerate(sorted(nets.items())))
    return ('(export (version "E")\n  (design (source "check.kicad_sch") (date "") (tool "Eeschema 10.0"))\n'
            "  (components\n%s  )\n  (libparts\n%s  )\n  (nets\n%s  )\n)\n" % ("".join(comps), lp, ns))


def _check_schematic(parts):
    syms, placed = {}, []
    for ref, value, fp, mpn, sym, place, pins in parts:
        syms[sym] = [(n, nm, t, (ref, n) in CHECK_HIDDEN) for n, nm, t, _ in pins]
        props = [("Reference", ref), ("Value", value), ("Footprint", "fixture:" + fp), ("MPN", mpn)]
        placed.append('  (symbol (lib_id "fx:%s") (at 50 50 0) (unit 1) (uuid "%s")\n%s'
                      '    (instances (project "check" (path "/%s" (reference "%s") (unit 1)))))\n'
                      % (sym, _uid("s", ref), "".join('    (property "%s" %s (at 0 0 0))\n' % (k, _q(v)) for k, v in props),
                         _uid("root"), ref))
    lib = "".join('    (symbol "fx:%s"\n      (symbol "%s_1_1"\n%s      ))\n'
                  % (s, s, "".join('        (pin %s line (at 0 0 0) (length 2.54)%s (name %s) (number %s))\n'
                                   % (t, " (hide yes)" if hid else "", _q(nm), _q(n)) for n, nm, t, hid in pins))
                  for s, pins in sorted(syms.items()))
    return ('(kicad_sch (version 20260306) (generator "eeschema") (uuid "%s")\n  (lib_symbols\n%s  )\n%s'
            '  (text "Board check fixture: U1 to U4, 0 violations" (at 10 10 0))\n)\n' % (_uid("root"), lib, "".join(placed)))


def _pts(points):
    return "(pts %s)" % " ".join("(xy %s %s)" % p for p in points)


def _check_board(parts, fault):
    out = []
    netnames = set()
    for ref, value, fp, mpn, sym, (x, y, rot), pins in parts:
        pinnet = dict((n, net) for n, _, _, net in pins)
        body = ['  (footprint "fixture:%s" (layer "F.Cu") (uuid "%s") (at %s %s%s)' % (fp, _uid("fp", ref), x, y,
                                                                                       " %s" % rot if rot else ""),
                '    (property "Reference" "%s" (at 0 -2 0) (layer "F.SilkS") (uuid "%s") (effects (font (size 0.8 0.8) (thickness 0.15))))'
                % (ref, _uid("ref", ref)),
                '    (property "Value" "%s" (at 0 2 0) (layer "F.Fab") (uuid "%s") (effects (font (size 0.8 0.8) (thickness 0.12))))'
                % (value, _uid("val", ref)),
                '    (property "MPN" "%s" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "%s") (effects (font (size 1 1))))'
                % (mpn, _uid("mpn", ref)),
                "    (attr %s)" % ("through_hole" if fp.startswith("PinHeader") else "smd")]
        pads = CHECK_FOOTPRINTS[fp]
        xs = [p[2] - p[4] / 2 for p in pads] + [p[2] + p[4] / 2 for p in pads]
        ys = [p[3] - p[5] / 2 for p in pads] + [p[3] + p[5] / 2 for p in pads]
        body.append('    (fp_rect (start %.2f %.2f) (end %.2f %.2f) (stroke (width 0.05) (type default)) (fill no) '
                    '(layer "F.CrtYd") (uuid "%s"))' % (min(xs) - 0.25, min(ys) - 0.25, max(xs) + 0.25, max(ys) + 0.25,
                                                         _uid("crt", ref)))
        for num, kind, px, py, w, h in pads:
            net = pinnet.get(num, "")
            netnames.add(net)
            netpart = ' (net "%s")' % net if net else ""
            if kind == "smd":
                body.append('    (pad "%s" smd rect (at %s %s%s) (size %s %s) (layers "F.Cu" "F.Mask" "F.Paste")%s (uuid "%s"))'
                            % (num, px, py, " %s" % rot if rot else "", w, h, netpart, _uid("pad", ref, num)))
            else:
                body.append('    (pad "%s" thru_hole circle (at %s %s%s) (size %s %s) (drill %s) (layers "*.Cu" "*.Mask")%s (uuid "%s"))'
                            % (num, px, py, " %s" % rot if rot else "", w, h, round(w * 0.6, 2), netpart,
                               _uid("pad", ref, num)))
        out.append("\n".join(body) + ")\n")
    for i, (x1, y1, x2, y2, layer, net, w) in enumerate(CHECK_TRACKS):
        out.append('  (segment (start %s %s) (end %s %s) (width %s) (layer "%s") (net "%s") (uuid "%s"))\n'
                   % (x1, y1, x2, y2, w, layer, net, _uid("seg", i)))
    for i, (x, y, net) in enumerate(CHECK_VIAS):
        out.append('  (via (at %s %s) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "%s") (uuid "%s"))\n'
                   % (x, y, net, _uid("via", i)))
    for name, layer, poly, pieces in (("BUCK_GND", "F.Cu", CHECK_ISLAND, [CHECK_ISLAND]),
                                      ("GND_PLANE", "B.Cu", CHECK_PLANE, [CHECK_PLANE])):
        fills = "".join('    (filled_polygon (layer "%s") %s)\n' % (layer, _pts(p)) for p in pieces)
        out.append('  (zone (net "GND") (layer "%s") (uuid "%s") (name "%s") (hatch edge 0.5)\n'
                   '    (connect_pads yes (clearance 0.2)) (min_thickness 0.2) (filled_areas_thickness no)\n'
                   '    (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.3))\n    (polygon %s)\n%s  )\n'
                   % (layer, _uid("zone", name), name, _pts(poly), fills))
    layers = ('  (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (13 "F.Paste" user) (15 "B.Paste" user) '
              '(5 "F.SilkS" user "F.Silkscreen") (7 "B.SilkS" user "B.Silkscreen") (1 "F.Mask" user) (3 "B.Mask" user) '
              '(25 "Edge.Cuts" user) (31 "F.CrtYd" user "F.Courtyard") (29 "B.CrtYd" user "B.Courtyard") '
              '(35 "F.Fab" user) (33 "B.Fab" user))\n')
    return ('(kicad_pcb (version 20260206) (generator "pcbnew") (generator_version "10.0")\n'
            '  (general (thickness 1.6) (legacy_teardrops no))\n  (paper "A4")\n' + layers +
            '  (setup (pad_to_mask_clearance 0) (aux_axis_origin 100 130))\n' + "".join(out) +
            '  (gr_rect (start 100 100) (end 140 130) (stroke (width 0.1) (type default)) (fill no) (layer "Edge.Cuts") '
            '(uuid "%s"))\n  (embedded_fonts no)\n)\n' % _uid("edge"))


def _check_mod(name):
    pads = "".join('  (pad "%s" %s rect (at %s %s) (size %s %s)%s (layers %s))\n'
                   % (n, k, x, y, w, h, " (drill %s)" % round(w * 0.6, 2) if k == "thru_hole" else "",
                      '"*.Cu" "*.Mask"' if k == "thru_hole" else '"F.Cu" "F.Mask" "F.Paste"')
                   for n, k, x, y, w, h in CHECK_FOOTPRINTS[name])
    return '(footprint "%s" (version 20260206) (generator "pcbnew") (layer "F.Cu")\n%s)\n' % (name, pads)


def make_check_project(dest, fault=""):
    """Write the check fixture into dest (created) and return dest. See the section header for faults."""
    import sys as _sys
    parts = _check_parts(fault)
    hw = os.path.join(dest, "hardware")
    design = os.path.join(dest, "design")
    for d in (hw, os.path.join(hw, "fixture.pretty"), os.path.join(design, "renders"), os.path.join(design, "reports"),
              os.path.join(design, "checklists"), os.path.join(dest, SKILL_DIR)):
        os.makedirs(d, exist_ok=True)
    for name in CHECK_SCRIPTS:
        shutil.copy(os.path.join(SKILL_SCRIPTS, name), os.path.join(dest, SKILL_DIR, name))
    comp = CHECK_COMPLIANCE_CSV
    cons = CHECK_CONSTRAINTS_CSV
    fab = CHECK_FAB_CSV
    if fault == "layout_no_constraint":
        comp += ('DS-019,U1,BUCK-1,BUCK-1.pdf,A,7.4 Layout guidelines,11,,must,layout,physical,'
                 '"Keep the switch node area small",,,carried,open,,,,pass\n')
    if fault == "same_island_only":
        cons = "\n".join(l for l in cons.splitlines() if not l.startswith("CN-002")) + "\n"
        cons = cons.replace("partial; whole with CN-002", "whole (BR-01-01)")
        comp = comp.replace("CN-001;CN-002", "CN-001")
    if fault == "rule_no_source":
        fab = fab.replace("min_track,0.09,from user,", "min_track,0.09,,")
    files = {
        "hardware/%s.net" % CHECK_NAME: _check_netlist(parts),
        "hardware/%s.kicad_sch" % CHECK_NAME: _check_schematic(parts),
        "hardware/%s.kicad_pcb" % CHECK_NAME: _check_board(parts, fault),
        "hardware/fp-lib-table": '(fp_lib_table\n\t(version 7)\n\t(lib (name "fixture")(type "KiCad")'
                                 '(uri "${KIPRJMOD}/fixture.pretty")(options "")(descr "fixture footprints"))\n)\n',
        "design/parts.csv": CHECK_PARTS_CSV,
        "design/pins.csv": CHECK_PINS_CSV,
        "design/compliance.csv": comp,
        "design/sections.csv": CHECK_SECTIONS_CSV,
        "design/constraints.csv": cons,
        "design/fab-capabilities.csv": fab,
        "design/requirements.md": CHECK_REQUIREMENTS_MD,
        "design/status.md": CHECK_STATUS_MD,
        "design/decisions.md": CHECK_DECISIONS_MD,
        "design/findings.csv": CHECK_FINDINGS_CSV,
        "design/net-review.csv": "id,list,net_or_pin,item,reason,closed_by,date\n",
        "design/ownership.csv": "path,owner,writer,hash,commit\nhardware/%s.kicad_pcb,hand,,,\n" % CHECK_NAME,
        "design/reports/BR-02-01.md": CHECK_REPORT_MD,
        "design/checklists/board.md": CHECK_CHECKLIST_MD,
        "README.md": "# Check fixture\n\nU1 converts the input to 3.3 V for U2.\n",
    }
    for name in CHECK_FOOTPRINTS:
        files["hardware/fixture.pretty/%s.kicad_mod" % name] = _check_mod(name)
    for rel, text in files.items():
        with open(os.path.join(dest, rel), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    with open(os.path.join(design, "renders", "BUCK-1_p12.png"), "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
    _sys.path.insert(0, SKILL_SCRIPTS)
    try:
        import project_settings
        project_settings.write_project(os.path.join(hw, CHECK_NAME + ".kicad_pro"), design)
    finally:
        _sys.path.remove(SKILL_SCRIPTS)
    return dest


def write_st_data(folder, rename_pin6=False):
    """A tiny invented file in the format of ST's open pin data (mcu/<RefName>.xml). Returns the folder."""
    os.makedirs(os.path.join(folder, "mcu"), exist_ok=True)
    text = CHECK_ST_XML.replace('Name="PA2" Position="6"', 'Name="PA9" Position="6"') if rename_pin6 else CHECK_ST_XML
    with open(os.path.join(folder, "mcu", "STM32X001AXTx.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return folder
# ======================================================================== end of HB-6 section
