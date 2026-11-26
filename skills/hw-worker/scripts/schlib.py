# Copyright 2026 Teklabs Digital (hw-skills)
# SPDX-License-Identifier: Apache-2.0
"""Schematic generator library: what a project's gen_sch.py is built on. Python 3 standard library only
(no pcbnew).

A generator script (the project's scripts/gen_sch.py) describes the schematic in code and this library
writes the KiCad 10 files. The library is the project's copy in hwskills/:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "hwskills"))
    import schlib
    sch = schlib.Schematic(sys.argv[1])                  # hardware/<name>.kicad_sch, the root sheet
    top = sch.root
    psu = sch.add_sheet("Power", "power.kicad_sch", at=(10, 60), size=(14, 6),
                        pins=[("VOUT", "output", "right", 2)])
    u1 = psu.place("Regulator_Linear:AMS1117-3.3", "U", None, 30, 20)
    psu.wire(u1["VO"], (40, 20))
    psu.hier_label("VOUT", 40, 20, "output")
    top.wire(psu.pins["VOUT"], (40, 62))
    sys.exit(sch.finish())                               # writes the files, or reports violations

Coordinates are in units of 2.54 mm (U); half units stay on KiCad's 1.27 mm grid. y grows downwards.

What it gives:
  - name-based IDs: every UUID comes from what the item is (kind, designator, pin, position, text),
    so the same script gives the same bytes and an edit changes only the edited items;
  - designators from the order of place() calls, per prefix. With design/modules.csv, the numbers
    of a module's sheet come from the module's block (ref_block), for every prefix, so a part added
    to one module renumbers nothing in another. A designator outside its block is refused;
  - power symbols only for the rails declared in design/rails.csv (power()). A rail KiCad's power
    library has no symbol for gets a project symbol named as the rail (make_power_symbol());
  - parts of several units: place() gives the first unit and Sheet.unit() each further one, under
    one designator. A unit left unplaced is a violation;
  - symbol copy from KiCad's symbol libraries (kicad_env.py finds them), derived symbols flattened,
    and project symbols made in code (make_symbol), written to <name>.kicad_sym;
  - fields from design/parts.csv (value, footprint, datasheet, Manufacturer, MPN, Supplier,
    Supplier PN; "not fitted" variant gives do-not-populate). Nothing is typed into the generator.
    The Datasheet field comes from parts.csv. The library symbol's own link is used only when the
    symbol is that part's symbol (a project symbol, or a symbol named as the MPN). A symbol
    borrowed from another part never brings that part's link or description with it;
  - a footprint existence check: a footprint that is in neither KiCad's libraries nor a project
    library is a violation. finish() then writes nothing and exits 1, unless a waiver
    (--waive DC-nnn, recorded in design/decisions.md) is given;
  - several sheets (add_sheet): each child sheet is its own file, joined to its parent by
    hierarchical labels and sheet pins; global labels and power symbols join across all sheets;
  - the skeleton (skeleton()): the top sheet as a drawing of module boxes, and one sub-sheet per
    row of design/modules.csv, each drawn by its own module file;
  - drawing helpers: Sheet.midway() puts a two-pin part midway between two points and wires it,
    and Sheet.centre() moves a finished sheet to the middle of the clear area of its page;
  - the firmware page (firmware_page()): the closing text sheet, written from design/firmware.md,
    each line with its status;
  - the project file and rule file, through project_settings.write_project;
  - every file written is declared to build.py (through the file named by HWSKILLS_OUTPUTS).


"""
import argparse
import csv
import os
import re
import sys
import textwrap
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
while HERE in sys.path:
    sys.path.remove(HERE)
sys.path.insert(0, HERE)
for _name in ("hwcommon", "kicad_env", "project_settings"):    # the skill's own siblings, never a project's
    _mod = sys.modules.get(_name)                               # module of the same name imported earlier
    if _mod is not None and os.path.dirname(os.path.abspath(getattr(_mod, "__file__", None) or "")) != HERE:
        del sys.modules[_name]
import hwcommon  # noqa: E402
import kicad_env  # noqa: E402
import project_settings  # noqa: E402

U = 2.54
NAMESPACE = uuid.UUID("3b0f3c56-1d2e-4a8b-9c41-5e7f2a6d0c19")
SOURCING = (("Manufacturer", "manufacturer"), ("MPN", "mpn"), ("Supplier", "supplier"),
            ("Supplier PN", "supplier_pn"))
PAPERS = {"A4": (297, 210), "A3": (420, 297), "A2": (594, 420), "A1": (841, 594), "A0": (1189, 841)}   # mm
MARGIN = 10                 # mm kept clear inside the page edge, for the border
TITLE_BLOCK = 42            # mm kept clear above the bottom edge, for the title block
OUTPUTS_ENV = "HWSKILLS_OUTPUTS"
FILE_HEAD = '(kicad_sch\n\t(version 20260306)\n\t(generator "eeschema")\n\t(generator_version "10.0")\n'


class SchematicError(Exception):
    """Bad input to the library: a generator mistake, not a design finding."""


def n(v):
    """A number as KiCad writes it: at most 4 decimals, no trailing zeros, never -0."""
    s = ("%.4f" % v).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def mm(v):
    return n(v * U)


def q(text):
    """Text for a quoted S-expression string."""
    return str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


# ---------------------------------------------------------------- KiCad symbol libraries

def balanced(text, start):
    """The S-expression that opens at text[start] ("("), up to its closing bracket."""
    depth, in_str, i = 0, False, start
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise SchematicError("unbalanced S-expression")


_lib_text = {}


def extract(symbol_dir, lib, name):
    """The block of one symbol from <symbol_dir>/<lib>.kicad_sym (KeyError if it is not there)."""
    path = os.path.join(symbol_dir, lib + ".kicad_sym")
    if path not in _lib_text:
        if not os.path.isfile(path):
            raise KeyError("%s:%s (no library %s)" % (lib, name, path))
        with open(path, encoding="utf-8") as f:
            _lib_text[path] = f.read()
    text = _lib_text[path]
    m = re.search(r'\n\t\(symbol "%s"\s' % re.escape(name), text)
    if not m:
        raise KeyError("%s:%s" % (lib, name))
    return balanced(text, m.start() + 2)


def _prop_spans(block):
    """(start, end) of the top-level property blocks of a symbol."""
    spans = []
    for m in re.finditer(r'\n\t\t\(property "', block):
        b = balanced(block, m.start() + 3)
        spans.append((m.start(), m.start() + 3 + len(b)))
    return spans


def flatten(symbol_dir, lib, name):
    """A library symbol with (extends ...) resolved: the parent's drawing, the child's properties."""
    block = extract(symbol_dir, lib, name)
    ext = re.search(r'\(extends "([^"]+)"\)', block)
    if not ext:
        return block
    parent = flatten(symbol_dir, lib, ext.group(1))
    child_props = "".join(block[a:b] for a, b in _prop_spans(block))
    spans = _prop_spans(parent)
    flat = parent[:spans[0][0]] + child_props + parent[spans[-1][1]:]
    return flat.replace('(symbol "%s' % ext.group(1), '(symbol "%s' % name)


def lib_prop(block, name):
    m = re.search(r'\(property "%s" "((?:[^"\\]|\\.)*)"' % re.escape(name), block)
    return m.group(1) if m else ""


def symbol_pins(block, unit=1, body_style=1):
    """Pins of one unit of a symbol: [(number, name, type, x, y, angle, hidden)], library axes (y up).

    Pins of unit 0 (common to all units) are included.
    """
    out = []
    head = re.match(r'\(symbol "([^"]+)"', block).group(1)
    base = head.split(":")[-1]
    for m in re.finditer(r'\(symbol "%s_(\d+)_(\d+)"' % re.escape(base), block):
        u, s = int(m.group(1)), int(m.group(2))
        if u not in (0, unit) or s not in (0, body_style):
            continue
        sub = balanced(block, m.start())
        for p in re.finditer(r"\(pin (\w+) (\w+)\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\)", sub):
            ptext = balanced(sub, p.start())
            nm = re.search(r'\(name "([^"]*)"', ptext).group(1)
            num = re.search(r'\(number "([^"]*)"', ptext).group(1)
            hidden = "(hide yes)" in ptext.split("(name", 1)[0]
            out.append((num, nm, p.group(1), float(p.group(3)), float(p.group(4)), int(p.group(5)), hidden))
    return out


def lib_table(path):
    """{library name: uri} of a KiCad fp-lib-table or sym-lib-table ({} if missing)."""
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return dict(re.findall(r'\(lib \(name "([^"]+)"\)\s*\(type "[^"]*"\)\s*\(uri "([^"]+)"\)', text))


def unit_count(block):
    """How many units a library symbol has (1 for a symbol drawn only as unit 0)."""
    base = re.match(r'\(symbol "([^"]+)"', block).group(1).split(":")[-1]
    units = [int(u) for u in re.findall(r'\(symbol "%s_(\d+)_\d+"' % re.escape(base), block)]
    return max(units + [1])


def turned(px, py, rot, mirror=None):
    """A library point (U, y up) as an offset on the page from the symbol's position, for a symbol
    turned by rot and then mirrored, as KiCad does it."""
    dx, dy = {0: (px, -py), 90: (-py, -px), 180: (-px, py), 270: (py, px)}[rot]
    if mirror == "y":
        dx = -dx
    if mirror == "x":
        dy = -dy
    return dx, dy


def read_rows(path, label, columns):
    """The rows of a small design table as [(line number, {column: text})]; None when there is no file."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    head = [h.strip() for h in rows[0]] if rows else []
    missing = [c for c in columns if c not in head]
    if missing:
        raise SchematicError("%s: no column %s in its first line" % (label, ", ".join(missing)))
    out = []
    for i, row in enumerate(rows[1:], 2):
        if any(c.strip() for c in row):
            out.append((i, dict((h, row[k].strip() if k < len(row) else "") for k, h in enumerate(head))))
    return out


_COORD = re.compile(r"\((at|xy|start|end) (-?[\d.]+) (-?[\d.]+)")
_STRING = re.compile(r'("(?:[^"\\]|\\.)*")')


def coordinates(text):
    """Every (x, y) in mm of the items in text; quoted strings are not read."""
    return [(float(m.group(2)), float(m.group(3)))
            for part in _STRING.split(text)[::2] for m in _COORD.finditer(part)]


def shifted(text, dx, dy):
    """The items in text moved by (dx, dy) mm; quoted strings are left as they are."""
    parts = _STRING.split(text)
    move = lambda m: "(%s %s %s" % (m.group(1), n(float(m.group(2)) + dx), n(float(m.group(3)) + dy))
    parts[::2] = [_COORD.sub(move, part) for part in parts[::2]]
    return "".join(parts)


FIRMWARE_STATUS = (
    (re.compile(r"decided with the user \(DC-\d+\)$"), "DECIDED"),
    (re.compile(r"stated by a worker, not decided$"), "NOT DECIDED"),
    (re.compile(r"missing:\s*\S"), "MISSING"))


def firmware_line(line):
    """(tag, problem) of one can: or must: line of design/firmware.md. The tag is DECIDED, NOT DECIDED
    or MISSING; it is None, and the problem says why, when the line is not in the form."""
    if not re.match(r"(can|must):\s*\S", line):
        return None, "is not a heading, a can: line or a must: line"
    head, sep, status = line.rpartition("Status:")
    if not sep:
        return None, "has no Status:"
    source = re.search(r"Source:\s*(.*)$", head)
    if not source or not source.group(1).strip(" .;"):
        return None, "has no Source:"
    status = re.sub(r"[;,. ]*\bonly guard at start-up[. ]*$", "", status.strip()).rstrip(". ")
    for pattern, tag in FIRMWARE_STATUS:
        if pattern.match(status):
            return tag, None
    return None, ("status %r is none of: decided with the user (DC-nnn); stated by a worker, not decided; "
                  "missing: <what is missing>" % status)


# ---------------------------------------------------------------- the schematic

class Part(dict):
    """Pin positions of a placed symbol, by pin number and by pin name: {key: (x, y)} in U."""

    def __init__(self, ref, pins, unit=1):
        dict.__init__(self, pins)
        self.ref = ref
        self.unit = unit


class Sheet:
    """One schematic file. Get one from Schematic.root or Schematic.add_sheet; never directly."""

    def __init__(self, sch, name, file, parent, uid_, page, paper):
        self.sch, self.name, self.file, self.parent = sch, name, file, parent
        self.sheet_uuid = uid_                      # uuid of the sheet symbol on the parent (None for root)
        self.page, self.paper = page, paper
        self.items = []
        self.lib_ids = []                           # library symbols used on this sheet, first use first
        self.pins = {}                              # sheet pin name -> (x, y) on the parent
        self.shift = (0, 0)                         # centre(): the whole drawing moved by this, in U
        self.file_uuid = sch.root_uuid if parent is None else sch.uid("file", file)

    # ---- paths
    def path(self):
        """The instance path of symbols on this sheet: /<root>[/<sheet symbol>...]."""
        chain, s = [], self
        while s.parent is not None:
            chain.append(s.sheet_uuid)
            s = s.parent
        return "/" + "/".join([self.sch.root_uuid] + chain[::-1])

    # ---- symbols
    def place(self, lib_id, prefix, value, x, y, rot=0, mirror=None, unit=1, footprint=None, ref=None,
              val=None, above=None, fields=None, hide_ref=False, hide_value=False, dnp=None, designator=None,
              _of=None):
        """Place a symbol at (x, y) and return its pins as a Part ({pin number or name: (x, y)}).

        prefix: the designator prefix ("R", "U", "#PWR"); the number comes from the order of calls,
        inside the block of the sheet's module when design/modules.csv gives one.
        designator: a designator chosen by the generator ("R105"). It must fit the prefix, lie in the
        module's block and be free.
        unit: the unit placed, of a part of several units; place the others with unit().
        value: None takes the value from design/parts.csv (or the library). A value that differs
        from parts.csv stops the generator: parts.csv is the single source.
        Field placement: default right of a vertical part; above=d puts the value d units above
        the centre and the reference one unit higher; fields="lib" keeps the library positions;
        ref=/val= give (x, y, justify). justify ("left" or "right") is as seen on the page, at any
        rotation and mirror.
        """
        if rot not in (0, 90, 180, 270):
            raise SchematicError("%s: rotation %r; use 0, 90, 180 or 270" % (lib_id, rot))
        block = self.sch.symbol(lib_id)
        if _of is not None:
            refdes = _of["ref"]
        elif designator is not None:
            refdes = self.sch.claim_ref(prefix, designator, self)
        else:
            refdes = self.sch.next_ref(prefix, self)
        if not 1 <= unit <= unit_count(block):
            raise SchematicError("%s: unit %s; %s has %d unit(s)" % (refdes, unit, lib_id, unit_count(block)))
        row = self.sch.parts.get(refdes)
        power = lib_id.startswith("power:") or prefix.startswith("#")
        lib_value = lib_prop(block, "Value")
        if row is not None and row["value"]:
            if value is not None and value != row["value"]:
                raise SchematicError("%s: the generator says value %r, design/parts.csv says %r; parts.csv is "
                                     "the single source, so change one of them" % (refdes, value, row["value"]))
            value = row["value"]
        if value is None:
            value = lib_value
        if row is None and not power and _of is None:
            self.sch.notes.append("%s (%s) has no row in design/parts.csv: no sourcing fields written"
                                  % (refdes, value))
        fp = _of["fp"] if _of is not None else self.sch.footprint_for(refdes, lib_id, block, row, footprint, power)
        if dnp is None:
            dnp = bool(row) and "not fitted" in [v.lower() for v in hwcommon.split_list(row["variant"])]
        if lib_id not in self.lib_ids:
            self.lib_ids.append(lib_id)

        r = (x + 1, y - 0.5, "left")
        v = (x + 1, y + 0.5, "left")
        if above is not None:
            r, v = (x, y - above - 1, None), (x, y - above, None)
        if fields == "lib":
            r, v = self._lib_fields(block, x, y, rot)
        r, v = ref or r, val or v
        s = '\t(symbol\n\t\t(lib_id "%s")\n\t\t(at %s %s %d)\n' % (q(lib_id), mm(x), mm(y), rot)
        if mirror:
            s += "\t\t(mirror %s)\n" % mirror
        s += ("\t\t(unit %d)\n\t\t(body_style 1)\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n"
              "\t\t(on_board yes)\n\t\t(in_pos_files yes)\n\t\t(dnp %s)\n\t\t(uuid \"%s\")\n"
              % (unit, "yes" if dnp else "no",
                 self.sch.uid("symbol", refdes) if _of is None else self.sch.uid("symbol", refdes, "unit", unit)))
        frot = 90 if rot in (90, 270) else 0       # field angles are relative to the symbol
        # KiCad draws a field's left and right swapped on a symbol turned 90 or 180, and swaps them once
        # more on a symbol mirrored about y (checked against its plot); write the justification so that
        # the text lands on the side the generator asked for
        if (rot in (90, 180)) != (mirror == "y"):
            flip = {"left": "right", "right": "left", None: None}
            r, v = (r[0], r[1], flip[r[2]]), (v[0], v[1], flip[v[2]])
        s += _prop("Reference", refdes, r[0], r[1], frot, hide_ref, r[2])
        s += _prop("Value", value, v[0], v[1], frot, hide_value, v[2])
        s += _prop("Footprint", fp, x, y, 0, True)
        datasheet, description = self.sch.document_fields(refdes, lib_id, block, row, power, _of is None)
        s += _prop("Datasheet", datasheet, x, y, 0, True)
        s += _prop("Description", description, x, y, 0, True)
        if row is not None and not power:
            for field, col in SOURCING:
                s += _prop(field, row[col], x, y, 0, True)
        pos = {}
        for num, name, _, px, py, _, _ in symbol_pins(block, unit):
            s += '\t\t(pin "%s"\n\t\t\t(uuid "%s")\n\t\t)\n' % (q(num), self.sch.uid("pin", refdes, num))
            dx, dy = turned(px / U, py / U, rot, mirror)     # KiCad turns the symbol first, then mirrors it
            pt = (round(x + dx, 3), round(y + dy, 3))
            pos.setdefault(num, pt)
            if name and name != "~":
                pos.setdefault(name, pt)
        s += ('\t\t(instances\n\t\t\t(project "%s"\n\t\t\t\t(path "%s"\n\t\t\t\t\t(reference "%s")\n'
              "\t\t\t\t\t(unit %d)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n" % (q(self.sch.project), self.path(), refdes, unit))
        self.items.append(s)
        if _of is None:
            self.sch.placed.append((refdes, value, fp, self.name))
            self.sch.units[refdes] = {"ref": refdes, "lib_id": lib_id, "prefix": prefix, "value": value, "fp": fp,
                                      "count": unit_count(block), "placed": set([unit])}
        else:
            _of["placed"].add(unit)
        return Part(refdes, pos, unit)

    def unit(self, part, unit, x, y, rot=0, mirror=None, **kw):
        """Place another unit of a part of several units, under the same designator. part is what
        place() returned for its first unit; the other arguments are as for place(). Every unit of
        a part must be placed, the power unit too."""
        rec = self.sch.units.get(getattr(part, "ref", None))
        if rec is None:
            raise SchematicError("unit(): give the Part that place() returned for the first unit")
        if unit in rec["placed"]:
            raise SchematicError("%s: unit %s is placed already" % (rec["ref"], unit))
        for key in ("footprint", "designator", "unit"):
            if key in kw:
                raise SchematicError("%s: unit() takes no %s; it comes from the first unit" % (rec["ref"], key))
        return self.place(rec["lib_id"], rec["prefix"], rec["value"], x, y, rot=rot, mirror=mirror, unit=unit,
                          _of=rec, **kw)

    def midway(self, lib_id, prefix, value, a, b, **kw):
        """Place a two-pin part midway between the points a and b and wire it to both. The part is
        turned to lie on the line from a to b, its lower pin number towards a, and stays on the
        1.27 mm grid. a and b must be on one horizontal or vertical line, at least as far apart as
        the part's two pins. The other arguments are as for place(), without rot."""
        (ax, ay), (bx, by) = a, b
        if (ax != bx) == (ay != by):
            raise SchematicError("midway(%s): the points %r and %r are not two points in line; give two points "
                                 "on one horizontal or vertical line" % (lib_id, a, b))
        if "rot" in kw:
            raise SchematicError("midway(%s): the helper turns the part itself; give no rot" % lib_id)
        pins = sorted(symbol_pins(self.sch.symbol(lib_id), kw.get("unit", 1)), key=lambda p: p[0])
        if len(pins) != 2:
            raise SchematicError("midway(%s): the symbol has %d pins; midway() is for a part of two pins"
                                 % (lib_id, len(pins)))
        sign = lambda v: (v > 0) - (v < 0)
        for rot in (0, 90, 180, 270):
            o1, o2 = [turned(p[3] / U, p[4] / U, rot, kw.get("mirror")) for p in pins]
            dx, dy = o2[0] - o1[0], o2[1] - o1[1]
            if (sign(dx), sign(dy)) == (sign(bx - ax), sign(by - ay)):
                break
        else:
            raise SchematicError("midway(%s): the two pins of the symbol are not on one line through it" % lib_id)
        span, gap = abs(dx) + abs(dy), abs(bx - ax) + abs(by - ay)
        if span > gap:
            raise SchematicError("midway(%s): the gap from %r to %r is too short: %s U, and the part is %s U "
                                 "between its pins" % (lib_id, a, b, n(gap), n(span)))
        half = lambda v: round(v * 2) / 2.0
        if ax == bx:
            x, y = ax - o1[0], half((ay + by) / 2.0 - (o1[1] + o2[1]) / 2.0)
        else:
            x, y = half((ax + bx) / 2.0 - (o1[0] + o2[0]) / 2.0), ay - o1[1]
        part = self.place(lib_id, prefix, value, x, y, rot=rot, **kw)
        p1, p2 = part[pins[0][0]], part[pins[1][0]]
        if p1 != tuple(a):
            self.wire(a, p1)
        if p2 != tuple(b):
            self.wire(p2, b)
        return part

    def _lib_fields(self, block, x, y, rot):
        out = []
        for name in ("Reference", "Value"):
            blk = balanced(block, block.index('(property "%s"' % name))
            px, py = re.search(r"\(at ([-\d.]+) ([-\d.]+)", blk).groups()
            j = re.search(r"\(justify (\w+)", blk)
            px, py = float(px) / U, float(py) / U
            dx, dy = {0: (px, -py), 90: (-py, -px), 180: (-px, py), 270: (py, px)}[rot]
            out.append((x + dx, y + dy, j.group(1) if j and j.group(1) in ("left", "right") else None))
        return out

    def power(self, name, x, y, rot=0):
        """A power symbol with its pin at (x, y), for a rail declared in design/rails.csv; any other
        name is refused. The symbol is power:<name>, or the project symbol made for the rail by
        make_power_symbol(). PWR_FLAG is no rail: it is always allowed and gets the #FLG prefix."""
        prefix = "#FLG" if name == "PWR_FLAG" else "#PWR"
        return self.place(self.sch.power_symbol(name), prefix, name, x, y, rot=rot, fields="lib", hide_ref=True)

    # ---- connections and drawing
    def wire(self, *pts):
        """Wires through the points, each piece horizontal or vertical."""
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if x1 != x2 and y1 != y2:
                raise SchematicError("diagonal wire %r on sheet %s" % (pts, self.name))
            self.items.append(
                "\t(wire\n\t\t(pts\n\t\t\t(xy %s %s) (xy %s %s)\n\t\t)\n\t\t(stroke\n\t\t\t(width 0)\n"
                "\t\t\t(type default)\n\t\t)\n\t\t(uuid \"%s\")\n\t)\n"
                % (mm(x1), mm(y1), mm(x2), mm(y2), self.sch.uid("wire", self.file, x1, y1, x2, y2)))

    def junction(self, x, y):
        self.items.append("\t(junction\n\t\t(at %s %s)\n\t\t(diameter 0)\n\t\t(color 0 0 0 0)\n"
                          "\t\t(uuid \"%s\")\n\t)\n" % (mm(x), mm(y), self.sch.uid("junction", self.file, x, y)))

    def nc(self, pt):
        """No-connect mark on a pin left open as its datasheet allows."""
        self.items.append('\t(no_connect\n\t\t(at %s %s)\n\t\t(uuid "%s")\n\t)\n'
                          % (mm(pt[0]), mm(pt[1]), self.sch.uid("nc", self.file, pt[0], pt[1])))

    def label(self, name, x, y, right=False):
        """Local net label; right=True right-aligns the text so it ends at (x, y)."""
        if name in (self.sch.rails or {}):
            raise SchematicError("label %s on sheet %s: %s is a rail in design/rails.csv; draw a rail with "
                                 "power(), never with a label" % (name, self.name, name))
        ang, just = (180, "right") if right else (0, "left")
        self.items.append(
            '\t(label "%s"\n\t\t(at %s %s %d)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n'
            "\t\t\t(justify %s bottom)\n\t\t)\n\t\t(uuid \"%s\")\n\t)\n"
            % (q(name), mm(x), mm(y), ang, just, self.sch.uid("label", self.file, name, x, y)))

    def global_label(self, name, x, y, shape="bidirectional", right=False):
        """Global label: joins every label of this name on every sheet."""
        ang, just = (180, "right") if right else (0, "left")
        self.items.append(
            '\t(global_label "%s"\n\t\t(shape %s)\n\t\t(at %s %s %d)\n\t\t(fields_autoplaced yes)\n'
            "\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify %s)\n\t\t)\n"
            '\t\t(uuid "%s")\n\t\t(property "Intersheetrefs" "${INTERSHEET_REFS}"\n\t\t\t(at %s %s %d)\n'
            "\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(hide yes)\n\t\t\t(effects\n\t\t\t\t(font\n"
            "\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify %s)\n\t\t\t)\n\t\t)\n\t)\n"
            % (q(name), shape, mm(x), mm(y), ang, just, self.sch.uid("global_label", self.file, name, x, y),
               mm(x), mm(y), ang, just))

    def hier_label(self, name, x, y, shape="input", right=False):
        """Hierarchical label on a child sheet; it joins the sheet pin of the same name on the parent."""
        if self.parent is None:
            raise SchematicError("hierarchical label %s on the root sheet; use a global label there" % name)
        if name not in self.pins:
            raise SchematicError("hierarchical label %s on sheet %s has no sheet pin; declare it in "
                                 "add_sheet(pins=...)" % (name, self.name))
        ang, just = (180, "right") if right else (0, "left")
        self.items.append(
            '\t(hierarchical_label "%s"\n\t\t(shape %s)\n\t\t(at %s %s %d)\n\t\t(effects\n\t\t\t(font\n'
            "\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify %s)\n\t\t)\n\t\t(uuid \"%s\")\n\t)\n"
            % (q(name), shape, mm(x), mm(y), ang, just, self.sch.uid("hier_label", self.file, name)))
        self.sch.hier_used.add((self.file, name))

    def text(self, s, x, y, size=1.27):
        self.items.append(
            '\t(text "%s"\n\t\t(exclude_from_sim no)\n\t\t(at %s %s 0)\n\t\t(effects\n\t\t\t(font\n'
            "\t\t\t\t(size %s %s)\n\t\t\t)\n\t\t\t(justify left bottom)\n\t\t)\n\t\t(uuid \"%s\")\n\t)\n"
            % (q(s), mm(x), mm(y), n(size), n(size), self.sch.uid("text", self.file, s, x, y)))

    def frame(self, title, x0, y0, x1, y1):
        """A titled border around a functional block."""
        self.items.append(
            "\t(rectangle\n\t\t(start %s %s)\n\t\t(end %s %s)\n\t\t(stroke\n\t\t\t(width 0.25)\n"
            "\t\t\t(type default)\n\t\t)\n\t\t(fill\n\t\t\t(type none)\n\t\t)\n\t\t(uuid \"%s\")\n\t)\n"
            % (mm(x0), mm(y0), mm(x1), mm(y1), self.sch.uid("frame", self.file, title)))
        self.text(title, x0 + 1.5, y0 + 2.2, 2)

    def stub(self, pt, name, length=5):
        """A labelled wire stub leaving a pin to the right (length > 0) or left (< 0); the label sits
        on the free end and its text runs back over the wire towards the pin."""
        x, y = pt
        self.wire((x, y), (x + length, y))
        self.label(name, x + length, y, right=length > 0)

    def centre(self):
        """Move the whole drawing of this sheet to the middle of the clear area of its page: inside
        the border and above the title block. Call it last, when the sheet is drawn. The move is a
        whole number of U and is made when the file is written: the positions the generator works
        with stay as they are. Returns the move (dx, dy) in U. A drawing larger than the clear area
        is refused."""
        if self.paper not in PAPERS:
            raise SchematicError("centre(): sheet %s is on paper %r; the page sizes known are %s"
                                 % (self.name, self.paper, ", ".join(sorted(PAPERS))))
        pts = coordinates("".join(self.items) + "".join(self._sheet_symbols()))
        for child in self.sch.sheets:
            if child.parent is self:
                pts.append(((child.at[0] + child.size[0]) * U, (child.at[1] + child.size[1]) * U))
        if not pts:
            raise SchematicError("centre(): there is nothing on sheet %s to centre" % self.name)
        x0, x1 = min(x for x, _ in pts), max(x for x, _ in pts)
        y0, y1 = min(y for _, y in pts), max(y for _, y in pts)
        width, height = PAPERS[self.paper]
        right, bottom = width - MARGIN, height - TITLE_BLOCK
        if x1 - x0 > right - MARGIN or y1 - y0 > bottom - MARGIN:
            raise SchematicError("centre(): the drawing of sheet %s is %s by %s mm, and the clear area of %s is "
                                 "%s by %s mm; use a larger page (paper=) or split the sheet"
                                 % (self.name, n(x1 - x0), n(y1 - y0), self.paper, right - MARGIN, bottom - MARGIN))
        dx = int(round(((MARGIN + right) / 2.0 - (x0 + x1) / 2.0) / U))
        dy = int(round(((MARGIN + bottom) / 2.0 - (y0 + y1) / 2.0) / U))
        dx += (x0 + dx * U < MARGIN) - (x1 + dx * U > right)       # rounding to whole U never crosses the edge
        dy += (y0 + dy * U < MARGIN) - (y1 + dy * U > bottom)
        self.shift = (dx, dy)
        return self.shift

    # ---- output
    def _sheet_symbols(self):
        out = []
        for child in self.sch.sheets:
            if child.parent is not self:
                continue
            (x, y), (w, h) = child.at, child.size
            s = ("\t(sheet\n\t\t(at %s %s)\n\t\t(size %s %s)\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n"
                 "\t\t(on_board yes)\n\t\t(dnp no)\n\t\t(stroke\n\t\t\t(width 0.1524)\n\t\t\t(type solid)\n\t\t)\n"
                 "\t\t(fill\n\t\t\t(color 0 0 0 0.0000)\n\t\t)\n\t\t(uuid \"%s\")\n"
                 % (mm(x), mm(y), mm(w), mm(h), child.sheet_uuid))
            s += ('\t\t(property "Sheetname" "%s"\n\t\t\t(at %s %s 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n'
                  "\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify left bottom)\n"
                  "\t\t\t)\n\t\t)\n" % (q(child.name), mm(x), n(y * U - 0.7)))
            s += ('\t\t(property "Sheetfile" "%s"\n\t\t\t(at %s %s 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n'
                  "\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify left top)\n"
                  "\t\t\t)\n\t\t)\n" % (q(child.file), mm(x), n((y + h) * U + 0.6)))
            for pname, shape, side, _ in child.pin_specs:
                px, py = child.pins[pname]
                ang, just = (180, "left") if side == "left" else (0, "right")
                s += ('\t\t(pin "%s" %s\n\t\t\t(at %s %s %d)\n\t\t\t(uuid "%s")\n\t\t\t(effects\n\t\t\t\t(font\n'
                      "\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify %s)\n\t\t\t)\n\t\t)\n"
                      % (q(pname), shape, mm(px), mm(py), ang, self.sch.uid("sheet_pin", child.file, pname), just))
            s += ('\t\t(instances\n\t\t\t(project "%s"\n\t\t\t\t(path "%s"\n\t\t\t\t\t(page "%s")\n\t\t\t\t)\n'
                  "\t\t\t)\n\t\t)\n\t)\n" % (q(self.sch.project), self.path(), child.page))
            out.append(s)
        return out

    def text_of(self):
        lib = "".join("\t\t" + self.sch.lib_block(i).replace("\n", "\n\t") + "\n" for i in self.lib_ids)
        out = FILE_HEAD + '\t(uuid "%s")\n\t(paper "%s")\n' % (self.file_uuid, self.paper)
        out += self.sch.title_block()
        out += "\t(lib_symbols\n%s\t)\n" % lib if lib else "\t(lib_symbols)\n"
        body = "".join(self.items) + "".join(self._sheet_symbols())
        out += shifted(body, self.shift[0] * U, self.shift[1] * U) if self.shift != (0, 0) else body
        if self.parent is None:
            out += '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n'
        out += "\t(embedded_fonts no)\n)\n"
        return out


def _prop(name, value, x, y, rot=0, hide=False, justify=None):
    h = "\n\t\t\t(hide yes)" if hide else ""
    j = "\n\t\t\t\t(justify %s)" % justify if justify else ""
    return ('\t\t(property "%s" "%s"\n\t\t\t(at %s %s %d)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)%s\n'
            "\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)%s\n\t\t\t)\n\t\t)\n"
            % (q(name), q(value), mm(x), mm(y), rot, h, j))


class Schematic:
    """A schematic of one or more sheets, written by finish() (or write())."""

    def __init__(self, path, design_dir=None, title="", revision="", company="", date="", comment="",
                 paper="A4", symbol_dir=None, footprint_dir=None, project_footprints=None):
        """path: the root sheet, <name>.kicad_sch in the KiCad folder (hardware/ by default). design_dir:
        default the project's design/ (hwcommon.design_dir_for). project_footprints: {library name:
        folder} of project footprint libraries (written to the fp-lib-table); libraries already in the
        KiCad folder's fp-lib-table are found too."""
        self.path = os.path.abspath(path)
        self.hw = os.path.dirname(self.path)
        self.project = os.path.splitext(os.path.basename(self.path))[0]
        self.design = design_dir or hwcommon.design_dir_for(self.path)
        self.ns = uuid.uuid5(NAMESPACE, self.project)
        self.root_uuid = str(uuid.uuid5(self.ns, "root"))
        self._seen = {}
        self.counters = {}
        self.lib_cache = {}
        self.custom = {}                    # project symbols: name -> block (library form)
        self.tb = (title, revision, company, date, comment)
        self.symbol_dir = symbol_dir
        self.footprint_dir = footprint_dir
        self.project_fp = dict(project_footprints or {})
        for name, uri in lib_table(os.path.join(self.hw, "fp-lib-table")).items():
            self.project_fp.setdefault(name, uri.replace("${KIPRJMOD}", self.hw))
        self.parts = {}
        for row in hwcommon.read_table(os.path.join(self.design, "parts.csv")):
            for ref in hwcommon.split_list(row["refs"]):
                if ref in self.parts:
                    raise SchematicError("design/parts.csv: %s is in more than one row" % ref)
                self.parts[ref] = row
        self.notes, self.problems, self.placed = [], [], []
        self.hier_used = set()
        self.sheets = []
        self.used_refs, self.units = set(), {}      # designators given out; parts by designator
        self.power_made = set()                     # rails with a project power symbol
        self.closing = None                         # the firmware page, once added: the last sheet
        self.rails = self.read_rails()              # {rail: kind}, or None with no design/rails.csv
        self.modules = self.read_modules()          # rows of design/modules.csv in order, or None
        self.block_of = dict((m["sheet"], m) for m in self.modules or ())
        self.root = Sheet(self, self.project, os.path.basename(self.path), None, None, "1", paper)

    # ---- IDs
    def uid(self, *key):
        """Name-based UUID: the same key gives the same UUID; repeats are numbered in order."""
        k = "/".join(str(x) for x in key)
        self._seen[k] = self._seen.get(k, 0) + 1
        if self._seen[k] > 1:
            k += "#%d" % self._seen[k]
        return str(uuid.uuid5(self.ns, k))

    # ---- the design tables
    def read_rails(self):
        rows = read_rows(os.path.join(self.design, "rails.csv"), "design/rails.csv", ("rail", "kind"))
        if rows is None:
            return None
        rails = {}
        for line, row in rows:
            if not row["rail"]:
                raise SchematicError("design/rails.csv line %d: no rail name" % line)
            if row["rail"] in rails:
                raise SchematicError("design/rails.csv line %d: rail %s is in more than one row" % (line, row["rail"]))
            rails[row["rail"]] = row["kind"]
        return rails

    def read_modules(self):
        rows = read_rows(os.path.join(self.design, "modules.csv"), "design/modules.csv",
                         ("module", "sheet", "ref_block"))
        if rows is None:
            return None
        out = []
        for line, row in rows:
            where = "design/modules.csv line %d" % line
            m = re.match(r"(\d+)\s*-\s*(\d+)$", row["ref_block"])
            if not m or not 0 < int(m.group(1)) <= int(m.group(2)):
                raise SchematicError("%s: ref_block %r of module %s; give it as first-last, such as 100-199"
                                     % (where, row["ref_block"], row["module"]))
            new = {"module": row["module"], "sheet": row["sheet"], "lo": int(m.group(1)), "hi": int(m.group(2)),
                   "line": line}
            if not new["module"] or not new["sheet"]:
                raise SchematicError("%s: a row needs a module and a sheet" % where)
            for old in out:
                if old["module"] == new["module"]:
                    raise SchematicError("%s: module %s is in more than one row" % (where, new["module"]))
                if old["sheet"] == new["sheet"]:
                    raise SchematicError("%s: sheet %s is given to modules %s and %s; one sheet per module"
                                         % (where, new["sheet"], old["module"], new["module"]))
                if old["lo"] <= new["hi"] and new["lo"] <= old["hi"]:
                    raise SchematicError("%s: the blocks of modules %s (%d-%d) and %s (%d-%d) overlap"
                                         % (where, old["module"], old["lo"], old["hi"], new["module"], new["lo"],
                                            new["hi"]))
            out.append(new)
        return out

    def module_nets(self):
        """{module: [net, ...]} from design/module-nets.csv, in row order ({} with no file)."""
        rows = read_rows(os.path.join(self.design, "module-nets.csv"), "design/module-nets.csv", ("net", "modules"))
        known = [m["module"] for m in self.modules or ()]
        out = {}
        for line, row in rows or ():
            where = "design/module-nets.csv line %d" % line
            if row["net"] in (self.rails or {}):
                raise SchematicError("%s: %s is a rail in design/rails.csv; a rail is drawn with power() on each "
                                     "sheet and is no net between modules" % (where, row["net"]))
            for name in [x.strip() for x in row["modules"].split(";") if x.strip()]:
                if name not in known:
                    raise SchematicError("%s: module %s is not in design/modules.csv" % (where, name))
                if row["net"] in out.setdefault(name, []):
                    raise SchematicError("%s: net %s is listed twice for module %s" % (where, row["net"], name))
                out[name].append(row["net"])
        return out

    # ---- designators
    def next_ref(self, prefix, sheet=None):
        """The next free designator for a prefix: from the block of the sheet's module, or, for a
        sheet with no block, in order from 1 and clear of every block."""
        fmt = "%s%02d" if prefix.startswith("#") else "%s%d"
        block = self.block_of.get(sheet.file) if sheet is not None else None
        key = (prefix, block["module"]) if block else prefix
        num = self.counters.get(key, block["lo"] - 1 if block else 0)
        while True:
            num += 1
            if block and num > block["hi"]:
                raise SchematicError("sheet %s: no number is left for prefix %s in the block %d-%d of module %s "
                                     "(design/modules.csv line %d); the block is full"
                                     % (sheet.name, prefix, block["lo"], block["hi"], block["module"], block["line"]))
            if fmt % (prefix, num) in self.used_refs:
                continue
            if block or not any(m["lo"] <= num <= m["hi"] for m in self.modules or ()):
                break
        self.counters[key] = num
        self.used_refs.add(fmt % (prefix, num))
        return fmt % (prefix, num)

    def claim_ref(self, prefix, designator, sheet):
        """A designator chosen by the generator: checked against the prefix and the module's block."""
        m = re.match(r"%s(\d+)$" % re.escape(prefix), designator)
        if not m:
            raise SchematicError("designator %s does not fit the prefix %s (prefix, then a number)"
                                 % (designator, prefix))
        num, block = int(m.group(1)), self.block_of.get(sheet.file)
        if block and not block["lo"] <= num <= block["hi"]:
            raise SchematicError("designator %s on sheet %s is outside the block %d-%d of module %s "
                                 "(design/modules.csv line %d)"
                                 % (designator, sheet.name, block["lo"], block["hi"], block["module"], block["line"]))
        for other in self.modules or ():
            if not block and other["lo"] <= num <= other["hi"]:
                raise SchematicError("designator %s on sheet %s is in the block %d-%d of module %s, and this sheet "
                                     "is not that module's sheet (design/modules.csv line %d)"
                                     % (designator, sheet.name, other["lo"], other["hi"], other["module"],
                                        other["line"]))
        if designator in self.used_refs:
            raise SchematicError("designator %s is used twice" % designator)
        self.used_refs.add(designator)
        return designator

    # ---- rails
    def need_rail(self, name, what):
        if self.rails is None:
            note = "design/rails.csv is missing: the rail names given to power() were not checked against it"
            if note not in self.notes:
                self.notes.append(note)
        elif name not in self.rails:
            raise SchematicError("%s: %s is not a rail in design/rails.csv (declared: %s); a power symbol is only "
                                 "for a declared rail. Add the rail's row there first, or correct the name"
                                 % (what, name, ", ".join(sorted(self.rails)) or "none"))

    def power_symbol(self, name):
        """The symbol to draw a rail with: the project's own when one was made, else KiCad's."""
        if name == "PWR_FLAG":
            return "power:PWR_FLAG"
        self.need_rail(name, "power(%s)" % name)
        if name in self.power_made:
            return "%s:%s" % (self.project, name)
        try:
            self.symbol("power:" + name)
        except SchematicError:
            raise SchematicError("power(%s): KiCad's power library has no symbol of that name. Make the project's "
                                 "own with make_power_symbol(%r) before the first power() call; never draw the "
                                 "rail with a symbol of another name" % (name, name))
        return "power:" + name

    def make_power_symbol(self, name, like=None):
        """A project power symbol named as the rail, for a rail KiCad's power library has no symbol
        for. It is a copy of power:<like> (default: GND for a ground rail, +5V for a supply), with
        the symbol, its value and its net all named as the rail. power() then draws the rail with
        it. Returns its library ID."""
        self.need_rail(name, "make_power_symbol(%s)" % name)
        if like is None:
            like = "GND" if (self.rails or {}).get(name) == "ground" else "+5V"
        try:
            block = flatten(self.symbol_dir or kicad_env.symbol_dir(), "power", like)
        except KeyError:
            raise SchematicError("make_power_symbol(%s): there is no symbol power:%s in KiCad's power library to "
                                 "copy; give another with like=" % (name, like))
        self.custom[name] = block.replace(like, name)
        self.power_made.add(name)
        self.lib_cache.pop("%s:%s" % (self.project, name), None)
        return "%s:%s" % (self.project, name)

    def document_fields(self, ref, lib_id, block, row, power, note):
        """(Datasheet, Description) of a placed symbol. With a row in design/parts.csv, the link comes
        from the row. The library symbol's own link is used only when the symbol is this part's own:
        a project symbol, or a symbol named as the MPN. A symbol that carries another part's link
        is borrowed: its link is dropped and its description is written from the row."""
        link, text = lib_prop(block, "Datasheet"), lib_prop(block, "Description")
        if row is None or power:
            return link, text
        real = link not in ("", "~")
        lib, name = lib_id.split(":", 1)
        own = (lib == self.project and name in self.custom) or name.lower() == row["mpn"].strip().lower()
        datasheet = row.get("datasheet") or (link if own and real else "")
        if real and not own:
            text = " ".join(x for x in (row["manufacturer"], row["mpn"]) if x)
            if note:
                self.notes.append("%s: symbol %s is another part's symbol (MPN %s in design/parts.csv), so its "
                                  "library datasheet link and description are not used. Datasheet: %s"
                                  % (ref, lib_id, row["mpn"] or "not given",
                                     "from design/parts.csv" if row.get("datasheet") else
                                     "left empty; put the link in the datasheet column of design/parts.csv"))
        return datasheet, text

    # ---- sheets
    def add_sheet(self, name, file, at=(10, 10), size=(14, 6), pins=(), parent=None, paper="A4"):
        """A child sheet in its own file, shown on its parent (default: the root) as a box at `at`
        of `size` (U). pins: [(name, shape, side, offset)]: shape input, output, bidirectional,
        tri_state or passive; side "left" or "right"; offset in U down from the top edge. The pin
        positions on the parent are in sheet.pins, for wiring there."""
        parent = parent or self.root
        if self.closing is not None:
            raise SchematicError("sheet %s: the firmware page is the last sheet of the schematic; add every "
                                 "other sheet before firmware_page()" % name)
        if any(s.file == file for s in self.sheets) or file == self.root.file:
            raise SchematicError("sheet file %s is used twice" % file)
        if not file.endswith(".kicad_sch") or os.sep in file or "/" in file:
            raise SchematicError("sheet file %r: give a file name ending .kicad_sch, beside the root" % file)
        s = Sheet(self, name, file, parent, self.uid("sheet", file), str(len(self.sheets) + 2), paper)
        s.at, s.size = tuple(at), tuple(size)
        s.pin_specs = list(pins)
        for pname, shape, side, offset in s.pin_specs:
            if side not in ("left", "right") or shape not in ("input", "output", "bidirectional", "tri_state",
                                                             "passive"):
                raise SchematicError("sheet %s pin %s: shape %r side %r" % (name, pname, shape, side))
            if pname in (self.rails or {}):
                raise SchematicError("sheet %s pin %s: %s is a rail in design/rails.csv; a rail never crosses a "
                                     "sheet edge as a pin, draw it with power() on each sheet" % (name, pname, pname))
            if not 0 < offset < size[1]:
                raise SchematicError("sheet %s pin %s: offset %r is not inside the box" % (name, pname, offset))
            s.pins[pname] = (at[0] if side == "left" else at[0] + size[0], at[1] + offset)
        self.sheets.append(s)
        return s

    def skeleton(self, modules=None, labels=True):
        """The multi-sheet skeleton: one sub-sheet per row of design/modules.csv, in row order, each a
        box on the top sheet. Returns {module: Sheet}.

        modules: the module files, one per module that has something to say. Each is a dict, or an
        imported module file or object, with name (the module in modules.csv) and any of: at and
        size of its box (U), pins (as for add_sheet), paper, and draw, a function draw(sheet) that
        draws the sub-sheet. An object may spell them in capitals (NAME, PINS). A module with no
        entry gets a box in a grid, and its edge pins from design/module-nets.csv. Every box is
        made before the first draw function runs. A module with no draw function gets its
        hierarchical labels only, so the empty skeleton can be checked.
        labels: True puts a labelled wire stub on every box pin of the top sheet, so pins of one
        name join; False leaves the top sheet's wiring to the generator.
        """
        if self.modules is None:
            raise SchematicError("skeleton(): design/modules.csv is missing; the modules and their sheets come "
                                 "from it")
        table = dict((m["module"], m) for m in self.modules)
        specs = {}
        for given in modules or ():
            if isinstance(given, dict):
                spec = dict(given)
            else:
                spec = dict((k, getattr(given, k, None) or getattr(given, k.upper(), None))
                            for k in ("name", "file", "at", "size", "pins", "paper", "draw"))
            name = spec.get("name")
            if not name:
                raise SchematicError("skeleton(): a module file gives no name; it must name its module")
            if name not in table:
                raise SchematicError("skeleton(): module %s is not in design/modules.csv; add its row there "
                                     "first" % name)
            if name in specs:
                raise SchematicError("skeleton(): module %s is given twice" % name)
            if spec.get("file") and spec["file"] != table[name]["sheet"]:
                raise SchematicError("skeleton(): module %s: its module file says sheet %s, design/modules.csv "
                                     "says %s" % (name, spec["file"], table[name]["sheet"]))
            specs[name] = spec
        nets = self.module_nets()
        out, x, y, row_height = {}, 10, 10, 0
        for i, m in enumerate(self.modules):
            spec = specs.get(m["module"], {})
            pins = spec.get("pins")
            if pins is None:
                pins = [(net, "bidirectional", "left", k + 1) for k, net in enumerate(nets.get(m["module"], []))]
            size = spec.get("size") or (14, max(6, len(pins) + 1))
            if i and i % 3 == 0:
                x, y, row_height = 10, y + row_height + 6, 0
            out[m["module"]] = self.add_sheet(m["module"], m["sheet"], at=spec.get("at") or (x, y), size=size,
                                              pins=pins, paper=spec.get("paper") or "A4")
            x, row_height = x + 30, max(row_height, size[1])
        for m in self.modules:
            sheet, draw = out[m["module"]], specs.get(m["module"], {}).get("draw")
            if draw:
                draw(sheet)
            else:
                for k, (pname, shape, _, _) in enumerate(sheet.pin_specs):
                    sheet.hier_label(pname, 10, 10 + 2 * k, shape)
            for pname, _, side, _ in sheet.pin_specs if labels else ():
                self.root.stub(sheet.pins[pname], pname, -4 if side == "left" else 4)
        return out

    def firmware_page(self, file="firmware.kicad_sch", name="Firmware", at=None, size=(14, 4)):
        """The firmware page: a text sheet, the last sheet of the schematic, written from
        design/firmware.md. Call it after every other sheet is added. It shows the headings and
        every can: and must: line with its status in front (DECIDED, NOT DECIDED or MISSING), and
        a count of each. Nothing is typed here: the text is the file's. A line that is not in the
        form of design/firmware.md is a violation, named with its line number. The page takes the
        smallest of A4 to A0 that holds the list. at, size: its box on the top sheet (default:
        below the other boxes)."""
        path = os.path.join(self.design, "firmware.md")
        if not os.path.isfile(path):
            raise SchematicError("firmware_page(): design/firmware.md is missing; the page is written from it")
        with open(path, encoding="utf-8") as f:
            source = f.read().splitlines()
        rows, counts = [], {"DECIDED": 0, "NOT DECIDED": 0, "MISSING": 0, None: 0}   # rows: (text, size, pitches)
        for number, line in enumerate(source, 1):
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                top = not line.startswith("##")
                rows.append((line.lstrip("#").strip(), 2.5 if top else 1.8, 2))
                if top:
                    rows.append(None)           # the count line goes here
                continue
            tag, problem = firmware_line(line)
            counts[tag] += 1
            if problem:
                self.problems.append("design/firmware.md line %d: the line %s" % (number, problem))
            for piece in textwrap.wrap("[%s] %s" % (tag or "NOT IN THE FORM", line), 200,
                                       subsequent_indent="        ", break_long_words=False,
                                       break_on_hyphens=False):
                rows.append((piece, 1.27, 1))
        total = sum(counts.values())
        count = "%d line%s: %d decided, %d not decided, %d missing" % (
            total, "" if total == 1 else "s", counts["DECIDED"], counts["NOT DECIDED"], counts["MISSING"])
        if counts[None]:
            count += ", %d not in the form" % counts[None]
        if None not in rows:
            rows.insert(0, None)
        rows = [(count, 1.27, 2) if r is None else r for r in rows]
        last = 5 + 0.75 * sum(r[2] for r in rows)                   # y of the last line, in U
        fits = [p for p in ("A4", "A3", "A2", "A1", "A0") if last * U <= PAPERS[p][1] - TITLE_BLOCK - 4]
        if not fits:
            raise SchematicError("firmware_page(): design/firmware.md has %d lines, more than one A0 page holds"
                                 % total)
        if at is None:
            boxes = [s.at[1] + s.size[1] for s in self.sheets if s.parent is self.root]
            at = (10, max(boxes) + 4 if boxes else 10)
        page = self.add_sheet(name, file, at=at, size=size, paper=fits[0])
        y = 5
        for text, height, pitches in rows:
            y += 0.75 * pitches
            page.text(text, 5, y, height)
        self.closing = page
        return page

    # ---- symbols
    def symbol(self, lib_id):
        """Library block of a symbol, renamed to lib_id, with derived symbols flattened."""
        if lib_id not in self.lib_cache:
            if ":" not in lib_id:
                raise SchematicError("symbol %r: give it as library:name" % lib_id)
            lib, name = lib_id.split(":", 1)
            if lib == self.project and name in self.custom:
                block = self.custom[name]
            else:
                try:
                    block = flatten(self.symbol_dir or kicad_env.symbol_dir(), lib, name)
                except KeyError as e:
                    raise SchematicError("symbol %s is not in the KiCad libraries (%s); make it with "
                                         "make_symbol() or copy it into the project library" % (lib_id, e))
            self.lib_cache[lib_id] = block.replace('(symbol "%s"' % name, '(symbol "%s"' % lib_id, 1)
        return self.lib_cache[lib_id]

    def lib_block(self, lib_id):
        return self.lib_cache[lib_id]

    def make_symbol(self, name, footprint, datasheet, description, rect, pins, reference="U"):
        """A box symbol in the project library <project>.kicad_sym, used as "<project>:<name>".

        rect: ((x0, y0), (x1, y1)) in mm, library axes (y up). pins: [(number, name, type, x, y,
        angle)] in mm; the pin's (x, y) is its connection point and angle points into the body
        (0: pin on the left side, 180: right, 90: bottom, 270: top). Make it from the datasheet's
        pin table and check it against design/pins.csv.
        """
        (x0, y0), (x1, y1) = rect
        fx = "\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t)\n\t\t\t\t\t"
        s = ('(symbol "%s"\n\t\t(pin_names\n\t\t\t(offset 0.254)\n\t\t)\n\t\t(exclude_from_sim no)\n'
             "\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(in_pos_files yes)\n"
             "\t\t(duplicate_pin_numbers_are_jumpers no)\n" % q(name))
        s += _lib_prop("Reference", reference, x0, y0 + 2.54, False, "left")
        s += _lib_prop("Value", name, x0, y0 + 1.27, False, "left")
        s += _lib_prop("Footprint", footprint, 0, 0, True)
        s += _lib_prop("Datasheet", datasheet, 0, 0, True)
        s += _lib_prop("Description", description, 0, 0, True)
        s += ('\t\t(symbol "%s_0_1"\n\t\t\t(rectangle\n\t\t\t\t(start %s %s)\n\t\t\t\t(end %s %s)\n'
              "\t\t\t\t(stroke\n\t\t\t\t\t(width 0.254)\n\t\t\t\t\t(type default)\n\t\t\t\t)\n"
              "\t\t\t\t(fill\n\t\t\t\t\t(type background)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t\t(symbol \"%s_1_1\"\n"
              % (q(name), n(x0), n(y0), n(x1), n(y1), q(name)))
        for num, nm, typ, x, y, ang in pins:
            s += ("\t\t\t(pin %s line\n\t\t\t\t(at %s %s %d)\n\t\t\t\t(length 2.54)\n"
                  '\t\t\t\t(name "%s"\n\t\t\t\t\t(effects%s)\n\t\t\t\t)\n'
                  '\t\t\t\t(number "%s"\n\t\t\t\t\t(effects%s)\n\t\t\t\t)\n\t\t\t)\n'
                  % (typ, n(x), n(y), ang, q(nm), fx, q(num), fx))
        s += "\t\t)\n\t\t(embedded_fonts no)\n\t)"
        self.custom[name] = s
        self.lib_cache.pop("%s:%s" % (self.project, name), None)
        return "%s:%s" % (self.project, name)

    # ---- footprints
    def footprint_exists(self, fp):
        lib, _, name = fp.partition(":")
        if not lib or not name:
            return False
        if lib in self.project_fp:
            return os.path.isfile(os.path.join(self.project_fp[lib], name + ".kicad_mod"))
        root = self.footprint_dir or kicad_env.footprint_dir()
        return os.path.isfile(os.path.join(root, lib + ".pretty", name + ".kicad_mod"))

    def footprint_for(self, ref, lib_id, block, row, explicit, power):
        if power:
            return ""
        table = (row or {}).get("footprint", "")
        if table and explicit and table != explicit:
            raise SchematicError("%s: the generator says footprint %r, design/parts.csv says %r; parts.csv is "
                                 "the single source" % (ref, explicit, table))
        fp = table or explicit or lib_prop(block, "Footprint")
        if not fp:
            self.problems.append("%s (%s): no footprint" % (ref, lib_id))
        elif not self.footprint_exists(fp):
            self.problems.append("%s: footprint %s is in no KiCad or project library" % (ref, fp))
        return fp

    # ---- output
    def title_block(self):
        title, rev, company, date, comment = self.tb
        if not any(self.tb):
            return ""
        out = "\t(title_block\n"
        for key, value in (("title", title), ("date", date), ("rev", rev), ("company", company)):
            if value:
                out += '\t\t(%s "%s")\n' % (key, q(value))
        if comment:
            out += '\t\t(comment 1 "%s")\n' % q(comment)
        return out + "\t)\n"

    def check(self):
        """Problems found so far, plus sheet pins with no hierarchical label (ERC would flag them)."""
        out = list(self.problems)
        for s in self.sheets:
            for pname in s.pins:
                if (s.file, pname) not in self.hier_used:
                    out.append("sheet %s: pin %s has no hierarchical label on the sheet" % (s.name, pname))
        for ref, rec in self.units.items():
            missing = [u for u in range(1, rec["count"] + 1) if u not in rec["placed"]]
            if missing:
                out.append("%s (%s): %s of %d not placed; place every unit of a part (Sheet.unit)"
                           % (ref, rec["lib_id"], ", ".join("unit %d" % u for u in missing), rec["count"]))
        return out

    def files(self):
        """{file name: text} for every file this schematic writes into hardware/."""
        out = {s.file: s.text_of() for s in [self.root] + self.sheets}
        if self.custom:
            lib = ('(kicad_symbol_lib\n\t(version 20251024)\n\t(generator "kicad_symbol_editor")\n'
                   '\t(generator_version "10.0")\n'
                   + "".join("\t" + self.custom[k] + "\n" for k in sorted(self.custom)) + ")\n")
            out[self.project + ".kicad_sym"] = lib
            out["sym-lib-table"] = ('(sym_lib_table\n\t(version 7)\n\t(lib (name "%s")(type "KiCad")'
                                    '(uri "${KIPRJMOD}/%s.kicad_sym")(options "")(descr "project symbols"))\n)\n'
                                    % (self.project, self.project))
        if self.project_fp:
            libs = "".join('\t(lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s")(options "")(descr "project '
                           'footprints"))\n' % (name, os.path.relpath(path, self.hw).replace(os.sep, "/"))
                           for name, path in sorted(self.project_fp.items()))
            out["fp-lib-table"] = "(fp_lib_table\n\t(version 7)\n%s)\n" % libs
        return out

    def write(self, waive=()):
        """Write every file, or nothing. Returns (exit code, messages): 0 written; 1 violations and no
        waiver, nothing written; 2 a waiver that is not a recorded decision."""
        msgs = []
        bad = hwcommon.check_waivers(list(waive), self.design)
        if bad:
            return 2, bad
        problems = self.check()
        if problems:
            msgs.append("Violation: %d schematic problems:" % len(problems))
            msgs += ["    " + p for p in problems]
            if not waive:
                msgs.append("Nothing written. Fix the cause, or record a waiver (DC-nnn) and pass --waive DC-nnn.")
                return 1, msgs
            msgs.append("WAIVED by %s: going ahead with the %d problems above." % (", ".join(waive), len(problems)))
        written = sorted(self.files().items())
        for name, text in written:
            hwcommon.write_text(os.path.join(self.hw, name), text)
        try:
            notes = project_settings.write_project(os.path.join(self.hw, self.project + ".kicad_pro"), self.design)
        except project_settings.SettingsError as e:
            return 2, msgs + ["project_settings: %s" % e]
        if os.environ.get(OUTPUTS_ENV):     # tell build.py which files are this generator's, also when a
            with open(os.environ[OUTPUTS_ENV], "a", encoding="utf-8") as f:     # file was left as it was
                for name in [k for k, _ in written] + [self.project + ".kicad_pro", self.project + ".kicad_dru"]:
                    f.write(os.path.join(self.hw, name) + "\n")
        msgs += ["note: " + x for x in self.notes + notes]
        msgs.append("wrote %s: %d sheets, %d symbols" % (os.path.basename(self.path), 1 + len(self.sheets),
                                                         sum(1 for p in self.placed if not p[0].startswith("#"))))
        return 0, msgs

    def finish(self, argv=None):
        """Write the files and print what happened; returns the exit code for sys.exit().
        Takes --waive DC-nnn from the command line (build.py passes its waivers on)."""
        ap = argparse.ArgumentParser(add_help=False)
        ap.add_argument("--waive", action="append", default=[])
        a, _ = ap.parse_known_args(sys.argv[1:] if argv is None else argv)
        code, msgs = self.write(a.waive)
        for m in msgs:
            print(m, file=sys.stderr if code else sys.stdout)
        return code


def _lib_prop(name, value, x, y, hide, justify=None):
    h = "\n\t\t\t(hide yes)" if hide else ""
    j = "\n\t\t\t\t(justify %s)" % justify if justify else ""
    return ('\t\t(property "%s" "%s"\n\t\t\t(at %s %s 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)%s\n'
            "\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)%s\n\t\t\t)\n\t\t)\n"
            % (q(name), q(value), n(x), n(y), h, j))


def main(argv=None):
    """python3 schlib.py LIB:NAME ...  prints a library symbol's pins (number, name, type, position)."""
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(main.__doc__)
        return 2
    for spec in args:
        lib, _, name = spec.partition(":")
        try:
            block = flatten(kicad_env.symbol_dir(), lib, name)
        except KeyError as e:
            print("not found: %s" % e, file=sys.stderr)
            return 1
        print(spec, "footprint", lib_prop(block, "Footprint") or "(none)")
        for p in symbol_pins(block):
            print("    pin %-4s %-12s %-14s at %s, %s (U: %s, %s)%s" % (
                p[0], p[1], p[2], n(p[3]), n(p[4]), n(p[3] / U), n(-p[4] / U), " hidden" if p[6] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
