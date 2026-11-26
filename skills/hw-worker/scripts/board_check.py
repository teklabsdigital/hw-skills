# Copyright 2026 Teklabs Digital (hw-skills)
# SPDX-License-Identifier: Apache-2.0
"""Board checks, driven by design/constraints.csv. Python 3 standard library only; no pcbnew.

    python3 board_check.py [--project DIR]                    every constraint enforced by check:
    python3 board_check.py [--project DIR] CN-031 CN-032      those constraints
    python3 board_check.py <check> [CN-...]                   the constraints that use one check
    python3 board_check.py <check> --objects "..." --limit L  one check, not from the table
    python3 board_check.py <aid> --objects "..."              an aid: numbers for the reviewer

The board file is read as text (S-expressions). By default the zones are poured again first, on a
copy, by `kicad-cli pcb drc --refill-zones --save-board` with the project's rule file beside it, so
the fills checked are KiCad's own with the custom rules; the design file is never written.
--no-repour reads the fills saved in the file. Without kicad-cli the fills in the file are used and
the output says so.

What the text gives: footprints and pads (position, rotation, size, shape, layers, net, drill),
tracks and arcs (arcs as two straight pieces), vias, zones with their outlines and filled polygons,
keep-out areas, board-edge lines and arcs, courtyards, and the stack-up. What it does not give:
copper text and graphics, custom pad shapes (taken as their bounding rectangle), oval pads (taken as
rectangles), fill thermal-spoke detail beyond the polygons, and via tenting or plugging (KiCad stores
these in ways not read here). Distances are in mm, between copper edges.

Checks (each prints PASS or FAIL per CN-; `objects` is read as below, items joined by ";"):
  distance         first item, then items that must sit within `limit` mm of it (edge to edge).
  same_island      pads that must share one copper island on one layer (layer:L, default F.Cu),
                   joined by copper on that layer only (tracks, fills, pads), not through vias.
  single_point     the island holding the first pad (layer:L) joins other layers only at vias or
                   plated holes that sit inside pad in:REF.PIN, or, without in:, within `limit` mm
                   of each other. An island with no join fails.
  plane_one_piece  zone:<name>, or net:<net> with layer:L: every fill is one piece. An unfilled zone fails.
  via_count        pads, within:<mm>: at least `limit` vias of the pad's net within that distance of
                   the pad's copper; each via's offset from the pad centre is printed.
  keepout          area:x1,y1,x2,y2 (board-file mm) or zone:<rule area name>; layer:L (default every
                   copper layer); allow:<net>: no other copper in the area.
  net_length       nets: total track length of each at most `limit` mm (vias counted and printed).
                   A net with no track is "NO TRACK (not measured)", never a pass (ref_plane too).
  noisy_distance   sensitive items (nets, pads, parts), then noisy:<item> items: at least `limit` mm
                   apart on any one layer (the closest pair across layers is printed too).
  decouple_per_pin supply pins, as REF.PIN or REF.PIN=CAP: the named capacitor, or the nearest one
                   between the pin's net and ground, within `limit` mm of the pin.
  edge_distance    parts (REF), dielectric:<value> or role:<role> from design/parts.csv: at least
                   `limit` mm from the board edge (courtyard, else pads).
  ref_plane        signal nets, plane:<net> on <layer>: every track lies over a fill of a plane on
                   another layer; uncovered length at most `limit` mm (default 0).
  via_in_pad       parts (REF), or "all": at most `limit` vias (default 0) overlapping their pads.
  artefacts        power nets for width steps (or none): empty board, unrouted connections,
                   dangling track ends, vias joined on fewer than two layers, width steps,
                   overlapping duplicate tracks, Z joins between aligned pads, turns sharper than
                   90 degrees. Starved thermal connections come from KiCad's DRC (raised to errors).
Aids (numbers only, never pass or fail; a constraint that relies on one is enforced by review:):
  copper_area      nets (layer:L): copper area per layer, fills plus tracks plus pads (an upper figure).
  loop_area        pads in loop order: area of the polygon through their centres.
  node_capacitance a net: parallel-plate estimate to the nearest layer, from the board's stack-up or
                   --er and --h.

A failed check is a violation unless a decision covers it: --waive CN-nnn=DC-nnn (the DC- must be in
design/decisions.md) prints it as waived. A check with nothing to measure yet (NO TRACK) is listed,
not failed. Exit codes: 0 every check passed, waived or not measured; 1 a check failed; 2 missing or
unreadable input. The board is <name>.kicad_pcb in hardware/, or in the folder on the line
"KiCad folder: <folder>" of design/status.md.
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwcommon  # noqa: E402

CHECKS = hwcommon.BOARD_CHECKS
AIDS = hwcommon.BOARD_AIDS
EPS = 0.001
GROUND_RE = re.compile(r"^(?:[ADPS]?GND|GND[A-Z]|VSS|0V|EARTH|CHASSIS)\w*$", re.IGNORECASE)
CLASS2 = ("X5R", "X7R", "X7S", "X6S", "X7T", "X8R", "X8L", "Y5V", "Z5U", "X5S")
DESIGNATOR_RE = re.compile(r"^[A-Za-z]{1,4}\d+[A-Za-z]?$")
PAD_RE = re.compile(r"^([A-Za-z]{1,4}\d+[A-Za-z]?)\.(.+)$")


class InputError(Exception):
    pass


def is_ground(net):
    return bool(GROUND_RE.match(hwcommon.net_key(net).split("/")[-1]))


# ---------------------------------------------------------------- geometry

def rot(x, y, deg):
    """KiCad's rotation (board y points down; a positive angle turns anticlockwise on screen)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return x * c + y * s, -x * s + y * c


def bbox(pts, r=0.0):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs) - r, min(ys) - r, max(xs) + r, max(ys) + r


def boxes_near(a, b, gap):
    return not (a[2] + gap < b[0] or b[2] + gap < a[0] or a[3] + gap < b[1] or b[3] + gap < a[1])


def pt_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def seg_seg(a, b, c, d):
    d1, d2, d3, d4 = _cross(c, d, a), _cross(c, d, b), _cross(a, b, c), _cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 and d2 and d3 and d4:
        return 0.0
    return min(pt_seg(a, c, d), pt_seg(b, c, d), pt_seg(c, a, b), pt_seg(d, a, b))


def inside(p, poly):
    """Even-odd ray test; KiCad's fractured fills (holes joined by zero-width cuts) work with it."""
    x, y = p
    n, hit = len(poly), False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            hit = not hit
        j = i
    return hit


class Shape:
    """A copper or outline shape: a closed polygon, or a polyline (one point for a circle) with a radius."""

    def __init__(self, pts, closed=False, r=0.0):
        self.pts, self.closed, self.r = pts, closed, r
        self.box = bbox(pts, r)

    def edges(self):
        p = self.pts
        if len(p) == 1:
            return [(p[0], p[0])]
        out = list(zip(p, p[1:]))
        if self.closed:
            out.append((p[-1], p[0]))
        return out

    def contains(self, q):
        if self.closed and inside(q, self.pts):
            return True
        return any(pt_seg(q, a, b) <= self.r + EPS for a, b in self.edges())

    def area(self):
        if self.closed:
            p = self.pts
            return abs(sum(p[i][0] * p[i - 1][1] - p[i - 1][0] * p[i][1] for i in range(len(p)))) / 2.0
        if len(self.pts) == 1:
            return math.pi * self.r * self.r
        return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in self.edges()) * 2 * self.r

    def centre(self):
        b = self.box
        return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


class MultiShape:
    """Several shapes taken as one: every pad of a part that carries the same number (an exposed pad
    with its thermal-via pads, for example)."""

    def __init__(self, shapes):
        self.parts = list(shapes)
        boxes = [s.box for s in self.parts]
        self.box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
                    max(b[3] for b in boxes))
        self.closed, self.r = True, 0.0

    def contains(self, q):
        return any(s.contains(q) for s in self.parts)

    def area(self):
        return sum(s.area() for s in self.parts)

    def centre(self):
        b = self.box
        return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def distance(s, t, cap=None):
    """Edge-to-edge distance between two shapes; 0 when they touch or overlap."""
    if cap is not None and not boxes_near(s.box, t.box, cap):
        return cap + 1.0
    if isinstance(s, MultiShape) or isinstance(t, MultiShape):
        return min(distance(a, c, cap) for a in getattr(s, "parts", [s]) for c in getattr(t, "parts", [t]))
    if (s.closed and any(inside(p, s.pts) for p in t.pts)) or (t.closed and any(inside(p, t.pts) for p in s.pts)):
        return 0.0
    best = min(seg_seg(a, b, c, d) for a, b in s.edges() for c, d in t.edges())
    return max(0.0, best - s.r - t.r)


def rect_pts(cx, cy, w, h, angle):
    pts = []
    for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        rx, ry = rot(dx, dy, angle)
        pts.append((cx + rx, cy + ry))
    return pts


# ---------------------------------------------------------------- the board, read as text

def xy_list(node):
    pts = []
    for item in hwcommon.first(node, "pts", []) or []:
        if isinstance(item, list) and item and item[0] == "xy":
            pts.append((hwcommon.num(item[1]), hwcommon.num(item[2])))
        elif isinstance(item, list) and item and item[0] == "arc":
            for k in ("start", "mid", "end"):
                n = hwcommon.first(item, k)
                if n:
                    pts.append((hwcommon.num(n[1]), hwcommon.num(n[2])))
    return pts


def pt(node, key):
    n = hwcommon.first(node, key)
    return (hwcommon.num(n[1]), hwcommon.num(n[2])) if n else (0.0, 0.0)


class Board:
    def __init__(self, path):
        self.path = path
        root = hwcommon.read_sexpr(path)
        self.summary = hwcommon.board_summary(root)
        self.netnames = {}
        for n in hwcommon.find(root, "net"):
            if len(n) > 2:
                self.netnames[str(n[1])] = str(n[2])
        names = [str(l[1]) for l in (hwcommon.first(root, "layers", []) or [])[1:]
                 if isinstance(l, list) and len(l) > 1 and str(l[1]).endswith(".Cu")]
        inner = sorted([n for n in names if n.startswith("In")], key=lambda n: int(re.sub(r"\D", "", n) or 0))
        self.copper = [n for n in ("F.Cu",) if n in names] + inner + [n for n in ("B.Cu",) if n in names]
        self.pads, self.tracks, self.vias, self.zones, self.edges, self.courtyards = [], [], [], [], [], {}
        self.stackup = []
        for fp in hwcommon.find(root, "footprint"):
            self._footprint(fp)
        for s in hwcommon.find(root, "segment"):
            self._track(s, [pt(s, "start"), pt(s, "end")])
        for s in hwcommon.find(root, "arc"):
            self._track(s, [pt(s, "start"), pt(s, "mid"), pt(s, "end")])
        for v in hwcommon.find(root, "via"):
            ls = [str(x) for x in (hwcommon.first(v, "layers", []) or [])[1:]]
            span = self._span(ls[0], ls[-1]) if len(ls) >= 2 else list(self.copper)
            size = hwcommon.num(hwcommon.value(v, "size"))
            at = pt(v, "at")
            self.vias.append({"at": at, "size": size, "drill": hwcommon.num(hwcommon.value(v, "drill")),
                              "layers": span, "net": self._net(v), "shape": Shape([at], False, size / 2),
                              # any settings beyond the basic ones (tenting, filling, capping...), printed as they are
                              "text": " ".join(str(x[0]) for x in v if isinstance(x, list) and x and x[0] not in
                                               ("at", "size", "drill", "layers", "net", "uuid", "tstamp"))})
        for z in hwcommon.find(root, "zone"):
            self._zone(z)
        for kind in ("gr_line", "gr_arc", "gr_rect", "gr_circle", "gr_poly"):
            for g in hwcommon.find(root, kind):
                if hwcommon.value(g, "layer") == "Edge.Cuts":
                    self.edges += self._outline(g, kind, lambda p: p)
        setup = hwcommon.first(root, "setup", []) or []
        for layer in hwcommon.find(hwcommon.first(setup, "stackup", []) or [], "layer"):
            self.stackup.append({"name": str(layer[1]), "type": hwcommon.value(layer, "type"),
                                 "thickness": hwcommon.num(hwcommon.value(layer, "thickness"), 0.0),
                                 "er": hwcommon.num(hwcommon.value(layer, "epsilon_r"), 0.0)})

    def _net(self, node):
        n = hwcommon.first(node, "net")
        if n:
            q = [x for x in n[1:] if isinstance(x, hwcommon.Q)]
            if q:
                return str(q[0])
            if len(n) > 1:
                return self.netnames.get(str(n[1]), "")
        return hwcommon.value(node, "net_name")

    def _span(self, a, b):
        if a not in self.copper or b not in self.copper:
            return list(self.copper)
        i, j = sorted((self.copper.index(a), self.copper.index(b)))
        return self.copper[i:j + 1]

    def _layers(self, names):
        out = []
        for n in names:
            if n in ("*.Cu", "F&B.Cu"):
                return list(self.copper) if n == "*.Cu" else [l for l in ("F.Cu", "B.Cu") if l in self.copper]
            if n in self.copper:
                out.append(n)
        return out

    def _track(self, s, pts):
        w = hwcommon.num(hwcommon.value(s, "width"))
        self.tracks.append({"pts": pts, "width": w, "layer": hwcommon.value(s, "layer"), "net": self._net(s),
                            "shape": Shape(pts, False, w / 2),
                            "length": sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))})

    def _footprint(self, fp):
        fx, fy, fa = hwcommon._at(fp)
        ref = ""
        for p in hwcommon.find(fp, "property"):
            if len(p) > 2 and str(p[1]) == "Reference":
                ref = str(p[2])
        tf = lambda p: (fx + rot(p[0], p[1], fa)[0], fy + rot(p[0], p[1], fa)[1])   # noqa: E731
        for pad in hwcommon.find(fp, "pad"):
            px, py, pa = hwcommon._at(pad)
            cx, cy = tf((px, py))
            size = hwcommon.first(pad, "size", ["size", 0, 0])
            w, h = hwcommon.num(size[1]), hwcommon.num(size[2] if len(size) > 2 else size[1])
            shape = str(pad[3]) if len(pad) > 3 else "rect"
            layers = self._layers([str(l) for l in (hwcommon.first(pad, "layers", []) or [])[1:]])
            drill = hwcommon.first(pad, "drill")
            dval = hwcommon.num(drill[1]) if drill and len(drill) > 1 and not isinstance(drill[1], list) else 0.0
            if shape == "circle":
                sh = Shape([(cx, cy)], False, w / 2)
            else:
                sh = Shape(rect_pts(cx, cy, w, h, pa), True)
            self.pads.append({"ref": ref, "num": str(pad[1]), "net": self._net(pad), "layers": layers,
                              "type": str(pad[2]), "drill": dval, "at": (cx, cy), "shape": sh})
        court = []
        for kind in ("fp_line", "fp_rect", "fp_poly", "fp_circle", "fp_arc"):
            for g in hwcommon.find(fp, kind):
                layer = hwcommon.value(g, "layer")
                if layer.endswith("CrtYd"):
                    court += [p for s in self._outline(g, kind.replace("fp_", "gr_"), tf) for p in s[:2]]
                elif layer == "Edge.Cuts":
                    self.edges += self._outline(g, kind.replace("fp_", "gr_"), tf)
        if court and ref:
            self.courtyards[ref] = court

    def _outline(self, g, kind, tf):
        """Edge or courtyard geometry as straight pieces [(a, b)]."""
        if kind in ("gr_line",):
            return [(tf(pt(g, "start")), tf(pt(g, "end")))]
        if kind == "gr_arc":
            a, m, b = tf(pt(g, "start")), tf(pt(g, "mid")), tf(pt(g, "end"))
            return [(a, m), (m, b)]
        if kind == "gr_rect":
            (x1, y1), (x2, y2) = pt(g, "start"), pt(g, "end")
            c = [tf(p) for p in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
            return list(zip(c, c[1:] + c[:1]))
        if kind == "gr_circle":
            (cx, cy), (ex, ey) = pt(g, "center"), pt(g, "end")
            r = math.hypot(ex - cx, ey - cy)
            c = [tf((cx + r * math.cos(k * math.pi / 18), cy + r * math.sin(k * math.pi / 18))) for k in range(36)]
            return list(zip(c, c[1:] + c[:1]))
        c = [tf(p) for p in xy_list(g)]
        return list(zip(c, c[1:] + c[:1])) if len(c) > 1 else []

    def _zone(self, z):
        layers = [hwcommon.value(z, "layer")] if hwcommon.first(z, "layer") else \
            [str(x) for x in (hwcommon.first(z, "layers", []) or [])[1:]]
        layers = self._layers(layers) or [l for l in layers if l]
        fills = {}
        for fpoly in hwcommon.find(z, "filled_polygon"):
            pts = xy_list(fpoly)
            if len(pts) >= 3:
                fills.setdefault(hwcommon.value(fpoly, "layer") or (layers[0] if layers else ""), []).append(
                    Shape(pts, True))
        outline = []
        for poly in hwcommon.find(z, "polygon"):
            outline += xy_list(poly)
        self.zones.append({"name": hwcommon.value(z, "name"), "net": self._net(z), "layers": layers,
                           "keepout": hwcommon.first(z, "keepout") is not None,
                           "outline": Shape(outline, True) if len(outline) >= 3 else None, "fills": fills})

    # --- queries

    def pad_indices(self, ref, num):
        """Indexes of every pad of ref with this number (a footprint may hold several: an exposed pad
        and its thermal-via pads, for example)."""
        return [i for i, p in enumerate(self.pads) if p["ref"] == ref and p["num"] == num]

    def pad(self, ref, num):
        """The pad REF.NUM, with every pad of that number taken together: layers joined, the shape the
        union of their shapes, the centre that of the largest. None when there is no such pad."""
        found = [self.pads[i] for i in self.pad_indices(ref, num)]
        if len(found) < 2:
            return found[0] if found else None
        main = max(found, key=lambda p: p["shape"].area())
        layers = set(l for p in found for l in p["layers"])
        return {"ref": ref, "num": num, "net": next((p["net"] for p in found if p["net"]), ""),
                "layers": [l for l in self.copper if l in layers], "type": main["type"],
                "drill": max(p["drill"] for p in found), "at": main["at"],
                "shape": MultiShape([p["shape"] for p in found]), "count": len(found)}

    def ref_pads(self, ref):
        return [p for p in self.pads if p["ref"] == ref]

    def has_fills(self):
        return any(z["fills"] for z in self.zones if not z["keepout"])

    def items(self, net, layer):
        """Copper of one net on one layer: [(kind, key, shape)]."""
        out = []
        for i, p in enumerate(self.pads):
            if p["net"] == net and layer in p["layers"]:
                out.append(("pad", i, p["shape"]))
        for i, t in enumerate(self.tracks):
            if t["net"] == net and t["layer"] == layer:
                out.append(("track", i, t["shape"]))
        for i, v in enumerate(self.vias):
            if v["net"] == net and layer in v["layers"]:
                out.append(("via", i, v["shape"]))
        for i, z in enumerate(self.zones):
            if z["net"] == net and not z["keepout"]:
                for j, s in enumerate(z["fills"].get(layer, [])):
                    out.append(("fill", (i, j), s))
        return out

    def connectivity(self, net, layers=None, cross=True):
        """Union-find of a net's copper: {(kind, key, layer): root}. cross joins layers at vias and plated holes."""
        parent = {}

        def find_(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            ra, rb = find_(a), find_(b)
            if ra != rb:
                parent[ra] = rb
        for layer in layers or self.copper:
            its = self.items(net, layer)
            for kind, key, _ in its:
                parent[(kind, key, layer)] = (kind, key, layer)
            for i in range(len(its)):
                for j in range(i + 1, len(its)):
                    a, b = its[i], its[j]
                    if boxes_near(a[2].box, b[2].box, EPS) and distance(a[2], b[2], EPS) <= EPS:
                        union((a[0], a[1], layer), (b[0], b[1], layer))
        if cross:
            for node in list(parent):
                kind, key, layer = node
                if kind in ("via", "pad"):
                    for other in parent:
                        if other[0] == kind and other[1] == key and other != node:
                            union(node, other)
        return dict((n, find_(n)) for n in parent)


# ---------------------------------------------------------------- objects

def parse_objects(text, board):
    """Items of a constraint's objects field: [(key, value)]."""
    out = []
    for raw in hwcommon.split_list(text):
        key, sep, val = raw.partition(":")
        if sep and key in ("net", "zone", "layer", "area", "within", "noisy", "allow", "plane", "dielectric", "role",
                           "in", "ref", "pad"):
            if key == "noisy":
                inner = parse_objects(val, board)
                out += [("noisy", x) for x in inner]
                continue
            if key == "area":
                nums = [hwcommon.num(x, None) for x in val.split(",")]
                if len(nums) != 4 or None in nums:
                    raise InputError("area needs x1,y1,x2,y2 in mm, got %r" % val)
                out.append(("area", nums))
                continue
            if key == "plane":
                pnet, _, players = val.rpartition(" on ")
                if not pnet.strip() or not players.strip():
                    raise InputError("plane needs <net> on <layer>, got %r" % val)
                out.append(("plane", (pnet, players)))
                continue
            if key == "pad":
                m = PAD_RE.match(val)
                if not m:
                    raise InputError("pad needs REF.PIN, got %r" % val)
                out.append(("pad", (m.group(1), m.group(2))))
                continue
            if key in ("within",):
                v = hwcommon.num(val.replace("mm", ""), None)
                if v is None:
                    raise InputError("within needs a number in mm, got %r" % val)
                out.append((key, v))
                continue
            if key == "in":
                m = PAD_RE.match(val)
                if not m:
                    raise InputError("in needs REF.PIN, got %r" % val)
                out.append(("in", (m.group(1), m.group(2))))
                continue
            out.append((key, val))
            continue
        nets = set(p["net"] for p in board.pads) | set(t["net"] for t in board.tracks)
        m = PAD_RE.match(raw)
        if "=" in raw:
            left, _, right = raw.partition("=")
            m2 = PAD_RE.match(left)
            if not m2:
                raise InputError("cannot read %r; write REF.PIN=CAP" % raw)
            out.append(("pin_cap", ((m2.group(1), m2.group(2)), right.strip())))
        elif raw in nets or raw.startswith("/"):
            out.append(("net", raw))
        elif m and board.pad(m.group(1), m.group(2)):
            out.append(("pad", (m.group(1), m.group(2))))
        elif DESIGNATOR_RE.match(raw):
            out.append(("ref", raw))
        elif raw == "all":
            out.append(("all", True))
        else:
            raise InputError("cannot read %r: not a pad (REF.PIN), part, net or key:value" % raw)
    return out


def get(objs, key):
    return [v for k, v in objs if k == key]


def item_shapes(board, key, val):
    """Shapes for a pad, part or net item, with a label: [(label, layer, shape)]."""
    out = []
    if key == "pad":
        idx = board.pad_indices(*val)
        if not idx:
            raise InputError("no pad %s.%s on the board" % val)
        out += [("%s.%s" % val, l, board.pads[i]["shape"]) for i in idx for l in board.pads[i]["layers"]]
    elif key == "ref":
        pads = board.ref_pads(val)
        if not pads:
            raise InputError("no part %s on the board" % val)
        out += [("%s.%s" % (val, p["num"]), l, p["shape"]) for p in pads for l in p["layers"]]
    elif key == "net":
        for l in board.copper:
            out += [("%s (%s on %s)" % (val, k, l), l, s) for k, _, s in board.items(val, l) if k != "fill"]
        if not out:
            raise InputError("no copper of net %s on the board" % val)
    return out


def fmt(v):
    return "%.3f" % v


# ---------------------------------------------------------------- checks: each returns (ok, [lines])

def chk_distance(b, objs, limit, ctx):
    things = [(k, v) for k, v in objs if k in ("pad", "ref", "net")]
    if len(things) < 2 or limit is None:
        raise InputError("distance needs two or more pads or parts and a limit in mm")
    anchor = item_shapes(b, *things[0])
    ok, lines = True, []
    for k, v in things[1:]:
        best = None
        for la, layer_a, sa in anchor:
            for lb, layer_b, sb in item_shapes(b, k, v):
                d = distance(sa, sb)
                if best is None or d < best[0]:
                    best = (d, la, lb)
        good = best[0] <= limit + EPS
        ok &= good
        lines.append("%s to %s: %s mm (limit %s)%s" % (best[1], best[2], fmt(best[0]), limit, "" if good else "  TOO FAR"))
    return ok, lines


def island_of(b, net, layer, ref, num):
    """The island on `layer` holding pad REF.NUM: any pad of that number with copper on the layer."""
    conn = b.connectivity(net, [layer], cross=False)
    for idx in b.pad_indices(ref, num):
        if ("pad", idx, layer) in conn:
            return conn[("pad", idx, layer)], conn
    return None, conn


def chk_same_island(b, objs, limit, ctx):
    pads = get(objs, "pad")
    layer = (get(objs, "layer") or ["F.Cu"])[0]
    if len(pads) < 2:
        raise InputError("same_island needs two or more pads (REF.PIN)")
    nets = set()
    for ref, num in pads:
        p = b.pad(ref, num)
        if p is None:
            raise InputError("no pad %s.%s on the board" % (ref, num))
        nets.add(p["net"])
    if len(nets) != 1:
        return False, ["the pads are on different nets: %s" % ", ".join(sorted(nets))]
    net = nets.pop()
    conn = b.connectivity(net, [layer], cross=False)
    groups = {}
    for ref, num in pads:                   # every pad with this number, so a thermal pad's copies count
        roots = set(conn.get(("pad", i, layer)) for i in b.pad_indices(ref, num))
        if len(roots) > 1:
            roots.discard(None)             # copies with no copper on this layer (back-side via pads)
        for root in roots:
            groups.setdefault(root, []).append("%s.%s" % (ref, num))
    if len(groups) == 1 and None not in groups:
        return True, ["%d pads share one %s island on %s" % (len(pads), net, layer)]
    lines = ["%s pieces on %s:" % (len(groups), layer)] + ["  " + ", ".join(g) if r else "  not on %s: %s" % (layer, ", ".join(g))
                                                         for r, g in groups.items()]
    return False, lines


def chk_single_point(b, objs, limit, ctx):
    pads = get(objs, "pad")
    layer = (get(objs, "layer") or ["F.Cu"])[0]
    if not pads:
        raise InputError("single_point needs a pad of the island (REF.PIN)")
    ref, num = pads[0]
    p = b.pad(ref, num)
    if p is None:
        raise InputError("no pad %s.%s on the board" % (ref, num))
    root, conn = island_of(b, p["net"], layer, ref, num)
    if root is None:
        return False, ["%s.%s has no copper on %s" % (ref, num, layer)]
    joins = []
    for (kind, key, l), r in conn.items():
        if r != root:
            continue
        if kind == "via" and len(b.vias[key]["layers"]) > 1:
            joins.append(("via", b.vias[key]["at"]))
        elif kind == "pad" and len(b.pads[key]["layers"]) > 1 and b.pads[key]["drill"] > 0:
            joins.append(("plated hole %s.%s" % (b.pads[key]["ref"], b.pads[key]["num"]), b.pads[key]["at"]))
    if not joins:
        return False, ["the %s island holding %s.%s does not join any other layer" % (layer, ref, num)]
    where = get(objs, "in")
    lines = ["%d joins to other layers: %s" % (len(joins), ", ".join("%s at (%s, %s)" % (k, fmt(a[0]), fmt(a[1]))
                                                                  for k, a in joins))]
    if where:
        q = b.pad(*where[0])
        if q is None:
            raise InputError("no pad %s.%s on the board" % where[0])
        outside = [(k, a) for k, a in joins if not q["shape"].contains(a)]
        if outside:
            return False, lines + ["joins outside %s.%s: %s" % (where[0] + (", ".join("%s at (%s, %s)" % (k, fmt(a[0]), fmt(a[1]))
                                                                               for k, a in outside),))]
        return True, lines + ["every join is inside %s.%s" % where[0]]
    if limit is None:
        raise InputError("single_point needs in:REF.PIN or a limit (largest spread of the joins, mm)")
    spread = max(math.hypot(a[1][0] - c[1][0], a[1][1] - c[1][1]) for a in joins for c in joins)
    return spread <= limit + EPS, lines + ["spread of the joins %s mm (limit %s)" % (fmt(spread), limit)]


def chk_plane_one_piece(b, objs, limit, ctx):
    names, nets, layers = get(objs, "zone"), get(objs, "net"), get(objs, "layer")
    zones = [z for z in b.zones if not z["keepout"] and (z["name"] in names or z["net"] in nets)]
    if not zones:
        raise InputError("no zone named %s or on net %s" % (names or "-", nets or "-"))
    ok, lines = True, []
    for z in zones:
        for l in z["layers"]:
            if layers and l not in layers:
                continue
            k = len(z["fills"].get(l, []))
            good = k == 1
            ok &= good
            lines.append("zone %r (%s) on %s: %s" % (z["name"], z["net"], l, "one piece" if good else
                                                     ("not filled (pour it, or drop --no-repour)" if k == 0 else
                                                      "%d pieces" % k)))
    return ok, lines


def chk_via_count(b, objs, limit, ctx):
    pads, within = get(objs, "pad"), get(objs, "within")
    if not pads or limit is None:
        raise InputError("via_count needs pads (REF.PIN) and a limit (the least number of vias)")
    if not within:
        raise InputError("via_count needs within:<mm>, the distance from the pad the datasheet allows")
    ok, lines = True, []
    for ref, num in pads:
        p = b.pad(ref, num)
        if p is None:
            raise InputError("no pad %s.%s on the board" % (ref, num))
        found = []
        for v in b.vias:
            if v["net"] == p["net"]:
                d = distance(p["shape"], Shape([v["at"]], False, 0.0))
                if d <= within[0] + EPS:
                    found.append((d, v["at"][0] - p["at"][0], v["at"][1] - p["at"][1]))
        good = len(found) >= limit
        ok &= good
        lines.append("%s.%s (%s): %d vias within %s mm (need %d)%s" % (ref, num, p["net"], len(found), within[0],
                                                                       int(limit), "" if good else "  TOO FEW"))
        for d, dx, dy in sorted(found, key=lambda f: (f[1], f[2])):
            lines.append("    via at offset (%s, %s) from the pad centre, %s mm from its copper" % (fmt(dx), fmt(dy), fmt(d)))
    return ok, lines


def chk_keepout(b, objs, limit, ctx):
    areas = []
    for a in get(objs, "area"):
        x1, y1, x2, y2 = a
        areas.append(("area %s" % ",".join(str(x) for x in a), Shape([(x1, y1), (x2, y1), (x2, y2), (x1, y2)], True), None))
    for name in get(objs, "zone"):
        z = next((z for z in b.zones if z["name"] == name and z["outline"]), None)
        if z is None:
            raise InputError("no zone or rule area named %r" % name)
        areas.append(("zone %r" % name, z["outline"], z["layers"]))
    if not areas:
        raise InputError("keepout needs area:x1,y1,x2,y2 or zone:<name>")
    allow = set(get(objs, "allow"))
    ok, lines = True, []
    for label, area, zlayers in areas:
        layers = get(objs, "layer") or zlayers or b.copper
        hits = []
        for l in layers:
            for net in sorted(set(p["net"] for p in b.pads) | set(t["net"] for t in b.tracks) |
                              set(v["net"] for v in b.vias) | set(z["net"] for z in b.zones)):
                if net in allow:
                    continue
                for kind, key, s in b.items(net, l):
                    if boxes_near(s.box, area.box, 0) and distance(s, area, EPS) <= 0:
                        what = {"pad": lambda k: "pad %s.%s" % (b.pads[k]["ref"], b.pads[k]["num"]),
                                "track": lambda k: "track", "via": lambda k: "via",
                                "fill": lambda k: "fill of zone %r" % b.zones[k[0]]["name"]}[kind](key)
                        hits.append("%s of %s on %s near (%s, %s)" % (what, net or "no net", l,
                                                                     fmt(s.centre()[0]), fmt(s.centre()[1])))
        ok &= not hits
        lines.append("%s on %s: %s" % (label, ", ".join(layers), "clear" if not hits else "%d items inside" % len(hits)))
        lines += ["    " + h for h in hits[:20]] + (["    ... %d more" % (len(hits) - 20)] if len(hits) > 20 else [])
    return ok, lines


def chk_net_length(b, objs, limit, ctx):
    nets = get(objs, "net")
    if not nets or limit is None:
        raise InputError("net_length needs nets and a limit in mm")
    ok, lines, unrouted = True, [], 0
    for n in nets:
        if not any(t["net"] == n for t in b.tracks):
            unrouted += 1
            lines.append("%s: no track (not routed yet): not measured" % n)
            continue
        length = sum(t["length"] for t in b.tracks if t["net"] == n)
        vias = sum(1 for v in b.vias if v["net"] == n)
        good = length <= limit + EPS
        ok &= good
        lines.append("%s: %s mm of track, %d vias (limit %s mm)%s" % (n, fmt(length), vias, limit, "" if good else "  TOO LONG"))
    return measured(ok, unrouted), lines


def measured(ok, unrouted):
    """A check's result when some of its nets have no track: a fail stays a fail; otherwise None, which
    is reported as "NO TRACK" (not measured), never as a pass."""
    return ok if not ok or not unrouted else None


def chk_noisy_distance(b, objs, limit, ctx):
    quiet = [(k, v) for k, v in objs if k in ("pad", "ref", "net")]
    noisy = [v for k, v in objs if k == "noisy"]
    if not quiet or not noisy or limit is None:
        raise InputError("noisy_distance needs sensitive items, noisy:<item> items and a limit in mm")
    qs = [s for k, v in quiet for s in item_shapes(b, k, v)]
    ns = [s for k, v in noisy for s in item_shapes(b, k, v)]
    same, cross = None, None
    for la, l1, s1 in qs:
        for lb, l2, s2 in ns:
            d = distance(s1, s2)
            if l1 == l2 and (same is None or d < same[0]):
                same = (d, la, lb, l1)
            if cross is None or d < cross[0]:
                cross = (d, la, lb, "%s/%s" % (l1, l2))
    lines = []
    ok = same is None or same[0] >= limit - EPS
    if same:
        lines.append("closest on one layer: %s to %s on %s: %s mm (limit at least %s)%s"
                     % (same[1], same[2], same[3], fmt(same[0]), limit, "" if ok else "  TOO CLOSE"))
    else:
        lines.append("no sensitive and noisy copper share a layer")
    if cross:
        lines.append("closest across layers (plan view): %s to %s (%s): %s mm" % (cross[1], cross[2], cross[3], fmt(cross[0])))
    return ok, lines


def chk_decouple_per_pin(b, objs, limit, ctx):
    pins = [(v, None) for v in get(objs, "pad")] + [(v[0], v[1]) for v in get(objs, "pin_cap")]
    if not pins or limit is None:
        raise InputError("decouple_per_pin needs supply pins (REF.PIN or REF.PIN=CAP) and a limit in mm")
    ok, lines, used = True, [], {}
    for (ref, num), cap in pins:
        p = b.pad(ref, num)
        if p is None:
            raise InputError("no pad %s.%s on the board" % (ref, num))
        cands = []
        for q in b.pads:
            if q["net"] != p["net"] or q["ref"] == ref or not re.match(r"^C\d", q["ref"]):
                continue
            if cap and q["ref"] != cap:
                continue
            others = [x for x in b.ref_pads(q["ref"]) if x is not q]
            if not any(is_ground(x["net"]) for x in others):
                continue
            cands.append((distance(p["shape"], q["shape"]), q["ref"]))
        if not cands:
            ok = False
            lines.append("%s.%s (%s): no capacitor %sbetween this net and ground" % (ref, num, p["net"],
                                                                                    "%s " % cap if cap else ""))
            continue
        d, c = min(cands)
        used.setdefault(c, []).append("%s.%s" % (ref, num))
        good = d <= limit + EPS
        ok &= good
        lines.append("%s.%s (%s): %s at %s mm (limit %s)%s" % (ref, num, p["net"], c, fmt(d), limit, "" if good else "  TOO FAR"))
    for c, served in sorted(used.items()):
        if len(served) > 1:
            lines.append("note: %s is the nearest capacitor for %s" % (c, ", ".join(served)))
    return ok, lines


def chk_edge_distance(b, objs, limit, ctx):
    if limit is None:
        raise InputError("edge_distance needs a limit in mm")
    if not b.edges:
        raise InputError("the board has no Edge.Cuts outline")
    refs = list(get(objs, "ref"))
    rows = ctx.get("parts", [])
    for want in get(objs, "dielectric"):
        wanted = CLASS2 if want.lower() in ("class2", "class 2") else (want.upper(),)
        refs += [r for row in rows if row["dielectric"].upper() in wanted for r in hwcommon.split_list(row["refs"])]
    for role in get(objs, "role"):
        refs += [r for row in rows if row["role"] == role for r in hwcommon.split_list(row["refs"])]
    if not refs:
        raise InputError("edge_distance found no parts (name them, or check design/parts.csv dielectric and role)")
    edge = [Shape([a, c]) for a, c in b.edges]
    ok, lines = True, []
    for ref in sorted(set(refs), key=hwcommon.ref_key):
        if ref in b.courtyards:
            pts, what = b.courtyards[ref], "courtyard"
            x1, y1, x2, y2 = bbox(pts)
            body = [Shape([(x1, y1), (x2, y1), (x2, y2), (x1, y2)], True)]
        else:
            body, what = [p["shape"] for p in b.ref_pads(ref)], "pads"
        if not body:
            lines.append("%s: not on the board" % ref)
            ok = False
            continue
        d = min(distance(s, e) for s in body for e in edge)
        good = d >= limit - EPS
        ok &= good
        lines.append("%s (%s): %s mm from the edge (limit at least %s)%s" % (ref, what, fmt(d), limit, "" if good else "  TOO CLOSE"))
    return ok, lines


def chk_ref_plane(b, objs, limit, ctx, step=0.1):
    nets, planes = get(objs, "net"), get(objs, "plane")
    if not nets or not planes:
        raise InputError("ref_plane needs signal nets and plane:<net> on <layer>")
    fills = []
    for pnet, players in planes:
        for z in b.zones:
            if z["net"] == pnet and not z["keepout"]:
                fills += [(players, s) for s in z["fills"].get(players, [])]
        if not any(l == players for l, _ in fills):
            raise InputError("no fill of %s on %s (pour it, or drop --no-repour)" % (pnet, players))
    allowed = limit or 0.0
    ok, lines, unrouted = True, [], 0
    for n in nets:
        if not any(t["net"] == n for t in b.tracks):
            unrouted += 1
            lines.append("%s: no track (not routed yet): not measured" % n)
            continue
        bad, total = 0.0, 0.0
        where = []
        for t in b.tracks:
            if t["net"] != n:
                continue
            under = [s for l, s in fills if l != t["layer"]]
            own_pads = [p for p in b.pads if p["net"] == n]
            for a, c in zip(t["pts"], t["pts"][1:]):
                L = math.hypot(c[0] - a[0], c[1] - a[1])
                k = max(1, int(L / step))
                total += L
                for i in range(k):
                    q = (a[0] + (c[0] - a[0]) * (i + 0.5) / k, a[1] + (c[1] - a[1]) * (i + 0.5) / k)
                    if any(p["net"] == n and p["shape"].contains(q) for p in own_pads):
                        continue                    # the part of the track inside its own pad
                    if not any(s.box[0] <= q[0] <= s.box[2] and s.box[1] <= q[1] <= s.box[3] and inside(q, s.pts)
                               for s in under):
                        bad += L / k
                        if len(where) < 3:
                            where.append("(%s, %s) on %s" % (fmt(q[0]), fmt(q[1]), t["layer"]))
        vias = sum(1 for v in b.vias if v["net"] == n)
        good = bad <= allowed + EPS
        ok &= good
        lines.append("%s: %s of %s mm not over the plane%s; %d layer changes (vias)%s" % (
            n, fmt(bad), fmt(total), " (first at %s)" % "; ".join(where) if where else "", vias, "" if good else "  GAP"))
    return measured(ok, unrouted), lines


def chk_via_in_pad(b, objs, limit, ctx):
    refs = get(objs, "ref")
    every = bool(get(objs, "all"))
    if not refs and not every:
        raise InputError("via_in_pad needs parts (REF) or all")
    allowed = int(limit or 0)
    hits = []
    for p in b.pads:
        if not every and p["ref"] not in refs:
            continue
        for v in b.vias:
            if any(l in p["layers"] for l in v["layers"]) and distance(p["shape"], v["shape"]) <= 0:
                hits.append("via at (%s, %s) in pad %s.%s%s" % (fmt(v["at"][0]), fmt(v["at"][1]), p["ref"], p["num"],
                                                               " [%s]" % v["text"] if v["text"] else ""))
    return len(hits) <= allowed, ["%d vias in pads (allowed %d)" % (len(hits), allowed)] + ["    " + h for h in hits]


def endpoint_touches(b, t, q):
    """Does a track end at q touch other copper of its net on its layer?"""
    pin = Shape([q], False, 0.0)
    for kind, key, s in b.items(t["net"], t["layer"]):
        if kind == "track" and b.tracks[key] is t:
            continue
        if boxes_near(s.box, pin.box, t["width"] / 2 + EPS) and distance(s, pin) <= t["width"] / 2 + EPS:
            return True
    return False


def chk_artefacts(b, objs, limit, ctx):
    power = set(get(objs, "net"))
    problems, lines = [], []
    if not b.tracks and not b.has_fills():
        problems.append("the board has no tracks and no filled zones")
    # unrouted connections
    unrouted = 0
    for net in sorted(set(p["net"] for p in b.pads if p["net"])):
        pads = [i for i, p in enumerate(b.pads) if p["net"] == net]
        if len(pads) < 2:
            continue
        conn = b.connectivity(net)
        roots = set()
        for i in pads:
            rs = [conn.get(("pad", i, l)) for l in b.pads[i]["layers"]]
            roots.add(rs[0] if rs else ("pad", i))
        if len(roots) > 1:
            unrouted += len(roots) - 1
            if len(problems) < 40:
                problems.append("net %s: %d separate pieces" % (net, len(roots)))
    lines.append("unrouted connections (from the file): %d" % unrouted)
    if ctx.get("drc") is not None:
        lines.append("unconnected items (KiCad DRC after the re-pour): %d" % ctx["drc"])
    # dangling ends, width steps, duplicates, sharp turns
    ends = {}
    for t in b.tracks:
        for q in (t["pts"][0], t["pts"][-1]):
            ends.setdefault((t["net"], t["layer"], round(q[0], 3), round(q[1], 3)), []).append(t)
            if not endpoint_touches(b, t, q):
                problems.append("dangling track end of %s on %s at (%s, %s)" % (t["net"] or "no net", t["layer"],
                                                                             fmt(q[0]), fmt(q[1])))
    for (net, layer, x, y), ts in sorted(ends.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3])):
        on_pad = any(p["net"] == net and layer in p["layers"] and p["shape"].contains((x, y)) for p in b.pads)
        if len(ts) == 2 and not on_pad:
            t1, t2 = ts
            if net in power and abs(t1["width"] - t2["width"]) > EPS:
                problems.append("width step on %s at (%s, %s): %s to %s mm" % (net, fmt(x), fmt(y), t1["width"], t2["width"]))
            a = t1["pts"][1] if (round(t1["pts"][0][0], 3), round(t1["pts"][0][1], 3)) == (x, y) else t1["pts"][-2]
            c = t2["pts"][1] if (round(t2["pts"][0][0], 3), round(t2["pts"][0][1], 3)) == (x, y) else t2["pts"][-2]
            v1, v2 = (a[0] - x, a[1] - y), (c[0] - x, c[1] - y)
            n1, n2 = math.hypot(*v1), math.hypot(*v2)
            if n1 > EPS and n2 > EPS:
                angle = math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))))
                if angle < 90 - 0.5:
                    problems.append("turn sharper than 90 degrees on %s at (%s, %s): %.0f degrees between the tracks"
                                    % (net, fmt(x), fmt(y), angle))
    for i, t in enumerate(b.tracks):
        for u in b.tracks[i + 1:]:
            if t["net"] == u["net"] and t["layer"] == u["layer"] and len(t["pts"]) == 2 == len(u["pts"]):
                a, c = t["pts"]
                if all(pt_seg(q, a, c) <= EPS for q in u["pts"]) or all(pt_seg(q, *u["pts"]) <= EPS for q in t["pts"]):
                    problems.append("duplicate track of %s on %s at (%s, %s)" % (t["net"], t["layer"], fmt(a[0]), fmt(a[1])))
    # vias joined on fewer than two layers
    for v in b.vias:
        layers = 0
        for l in v["layers"]:
            if any(not (k == "via" and b.vias[key] is v) and distance(s, v["shape"], EPS) <= EPS
                   for k, key, s in b.items(v["net"], l)):
                layers += 1
        if layers < 2:
            problems.append("via of %s at (%s, %s) joins copper on %d layer%s" % (
                v["net"] or "no net", fmt(v["at"][0]), fmt(v["at"][1]), layers, "" if layers == 1 else "s"))
    # Z joins between aligned pads of a two-pad net
    for net in sorted(set(p["net"] for p in b.pads if p["net"])):
        pads = [p for p in b.pads if p["net"] == net]
        tracks = [t for t in b.tracks if t["net"] == net]
        if len(pads) == 2 and len(tracks) > 1 and not any(v["net"] == net for v in b.vias):
            (x1, y1), (x2, y2) = pads[0]["at"], pads[1]["at"]
            if (abs(x1 - x2) < 0.01 or abs(y1 - y2) < 0.01) and len(set(t["layer"] for t in tracks)) == 1:
                problems.append("Z join on %s: %d tracks between aligned pads %s.%s and %s.%s" % (
                    net, len(tracks), pads[0]["ref"], pads[0]["num"], pads[1]["ref"], pads[1]["num"]))
    lines.append("starved thermal connections: not read from the file; KiCad's DRC reports them (starved_thermal)")
    return not problems, lines + problems


CHECK_FUNCS = {"distance": chk_distance, "same_island": chk_same_island, "single_point": chk_single_point,
               "plane_one_piece": chk_plane_one_piece, "via_count": chk_via_count, "keepout": chk_keepout,
               "net_length": chk_net_length, "noisy_distance": chk_noisy_distance,
               "decouple_per_pin": chk_decouple_per_pin, "edge_distance": chk_edge_distance,
               "ref_plane": chk_ref_plane, "via_in_pad": chk_via_in_pad, "artefacts": chk_artefacts}
assert set(CHECK_FUNCS) == set(CHECKS), "board_check.py and hwcommon.BOARD_CHECKS must name the same checks"


# ---------------------------------------------------------------- aids

def aid_copper_area(b, objs, a):
    nets, layers = get(objs, "net"), get(objs, "layer") or b.copper
    if not nets:
        raise InputError("copper_area needs nets")
    out = []
    for n in nets:
        for l in layers:
            parts = {"fill": 0.0, "track": 0.0, "pad": 0.0, "via": 0.0}
            for kind, _, s in b.items(n, l):
                parts[kind] += s.area()
            tot = sum(parts.values())
            if tot:
                out.append("%s on %s: %.2f mm2 (fills %.2f, tracks %.2f, pads %.2f, vias %.2f; overlaps counted twice)"
                           % (n, l, tot, parts["fill"], parts["track"], parts["pad"], parts["via"]))
    return out or ["no copper of %s on %s" % (", ".join(nets), ", ".join(layers))]


def aid_loop_area(b, objs, a):
    pads = get(objs, "pad")
    if len(pads) < 3:
        raise InputError("loop_area needs three or more pads (REF.PIN) in loop order")
    pts = []
    for ref, num in pads:
        p = b.pad(ref, num)
        if p is None:
            raise InputError("no pad %s.%s on the board" % (ref, num))
        pts.append(p["at"])
    return ["loop through %s: %.2f mm2 (polygon through the pad centres; the real loop also runs through the"
            " parts and the return copper)" % (" > ".join("%s.%s" % x for x in pads), Shape(pts, True).area())]


def aid_node_capacitance(b, objs, a):
    nets = get(objs, "net")
    if not nets:
        raise InputError("node_capacitance needs a net")
    out = []
    for n in nets:
        total = 0.0
        for l in b.copper:
            area = sum(s.area() for kind, _, s in b.items(n, l) if kind != "via")
            if not area:
                continue
            er, h, src = a.er, a.h, "--er and --h"
            if er is None or h is None:
                er, h, src = stack_dielectric(b, l)
            if not er or not h:
                out.append("%s on %s: %.2f mm2; no stack-up in the board file, pass --er and --h" % (n, l, area))
                continue
            c = 8.854e-3 * er * area / h          # pF, with area in mm2 and h in mm
            total += c
            out.append("%s on %s: %.2f mm2 over %.3f mm, er %.2f (%s): %.3f pF" % (n, l, area, h, er, src, c))
        out.append("%s: about %.3f pF in total (parallel plate, no fringing)" % (n, total))
    return out


def stack_dielectric(b, layer):
    names = [s["name"] for s in b.stackup]
    if layer not in names:
        return None, None, "no stack-up"
    i = names.index(layer)
    near = []
    for step in (1, -1):
        j = i + step
        while 0 <= j < len(b.stackup) and b.stackup[j]["type"] in ("core", "prepreg", "dielectric"):
            near.append(b.stackup[j])
            break
    near = [s for s in near if s["thickness"] and s["er"]]
    if not near:
        return None, None, "no dielectric next to %s in the stack-up" % layer
    s = min(near, key=lambda s: s["thickness"])
    return s["er"], s["thickness"], "stack-up %s" % s["name"]


AID_FUNCS = {"copper_area": aid_copper_area, "loop_area": aid_loop_area, "node_capacitance": aid_node_capacitance}
assert set(AID_FUNCS) == set(AIDS)


# ---------------------------------------------------------------- running

def repour(board_path, cli):
    """Pour the zones again on a copy, with the project and rule files beside it. (copy path, DRC unconnected, temp dir)."""
    tmp = tempfile.mkdtemp(prefix="board_check_")
    base = os.path.splitext(os.path.basename(board_path))[0]
    src_dir = os.path.dirname(os.path.abspath(board_path))
    for ext in (".kicad_pcb", ".kicad_pro", ".kicad_dru"):
        src = os.path.join(src_dir, base + ext)
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(tmp, base + ext))
    copy = os.path.join(tmp, base + ".kicad_pcb")
    report = os.path.join(tmp, "drc.json")
    res = subprocess.run([cli, "pcb", "drc", "--format", "json", "--severity-all", "--refill-zones", "--save-board",
                          "-o", report, copy], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.isfile(report):
        shutil.rmtree(tmp, ignore_errors=True)
        raise InputError("kicad-cli pcb drc wrote no report:\n" + (res.stdout + res.stderr)[-800:])
    with open(report, encoding="utf-8") as f:
        drc = json.load(f)
    return copy, len(drc.get("unconnected_items", [])), tmp


def limit_of(text):
    t = (text or "").strip().replace("mm", "").strip()
    if t in ("", "-"):
        return None
    v = hwcommon.num(t, None)
    if v is None:
        raise InputError("limit %r is not a number" % text)
    return v


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("args", nargs="*", help="a check or aid name, and/or CN- IDs")
    ap.add_argument("--project", default=".")
    ap.add_argument("--name")
    ap.add_argument("--board", help="board file (default <name>.kicad_pcb in the KiCad folder)")
    ap.add_argument("--objects", help="objects for one check or aid, not from the table")
    ap.add_argument("--limit", help="limit for --objects")
    ap.add_argument("--no-repour", action="store_true", help="read the fills saved in the file")
    ap.add_argument("--waive", action="append", default=[], metavar="CN-nnn=DC-nnn")
    ap.add_argument("--er", type=float, help="node_capacitance: dielectric constant")
    ap.add_argument("--h", type=float, help="node_capacitance: dielectric thickness, mm")
    a = ap.parse_args(argv)
    sub = a.args[0] if a.args and not hwcommon.CN_RE.fullmatch(a.args[0]) else None
    ids = [x for x in a.args if hwcommon.CN_RE.fullmatch(x)]
    tmp = None
    try:
        if sub and sub not in CHECKS and sub not in AIDS:
            raise InputError("unknown check %r; checks: %s; aids: %s" % (sub, ", ".join(CHECKS), ", ".join(AIDS)))
        paths = hwcommon.find_project(a.project, a.name) if not a.board else None
        board_path = a.board or paths["pcb"]
        if not board_path or not os.path.isfile(board_path):
            raise InputError("no board file at %s (pass --board)" % (
                board_path or os.path.join(paths["hardware"], "<name>.kicad_pcb")))
        design = paths["design"] if paths else hwcommon.design_dir_for(board_path)
        waivers = {}
        for w in a.waive:
            cn, _, dc = w.partition("=")
            waivers[cn] = dc
        problems = hwcommon.check_waivers(list(waivers.values()), design)
        if problems or any(not hwcommon.CN_RE.fullmatch(c) for c in waivers):
            raise InputError("; ".join(problems) or "write each waiver as CN-nnn=DC-nnn")
        ctx = {"parts": hwcommon.read_table(os.path.join(design, "parts.csv")), "drc": None}
        b = Board(board_path)
        note = "fills as saved in the file"
        if not a.no_repour and b.zones:
            cli = None
            try:
                import kicad_env
                cli = kicad_env.find_kicad_cli()
            except ImportError:
                pass
            if cli:
                copy, ctx["drc"], tmp = repour(board_path, cli)
                b = Board(copy)
                note = "zones poured again on a copy by kicad-cli (the board file is not changed)"
            else:
                note = "kicad-cli not found: fills as saved in the file, which may be stale"
        print("board: %s; %s" % (os.path.basename(board_path), note))
        if sub in AIDS:
            if not a.objects:
                raise InputError("%s needs --objects" % sub)
            for line in AID_FUNCS[sub](b, parse_objects(a.objects, b), a):
                print(line)
            print("(an aid: numbers for the reviewer to compare with the datasheet, not a pass or fail)")
            return 0
        jobs = []
        if a.objects is not None:
            if not sub:
                raise InputError("--objects needs a check name")
            jobs.append(("ad hoc", sub, a.objects, a.limit, ""))
        else:
            rows = hwcommon.read_table(os.path.join(design, "constraints.csv"))
            for r in rows:
                enf = hwcommon.parse_enforcer(r["enforced_by"])
                if not enf or enf[0] != "check":
                    continue
                if (ids and r["id"] not in ids) or (sub and enf[1] != sub):
                    continue
                if enf[2] != r["id"]:
                    jobs.append((r["id"], enf[1], None, None, "enforced_by names %s, the row is %s" % (enf[2], r["id"])))
                    continue
                jobs.append((r["id"], enf[1], r["objects"], r["limit"], ""))
            missing = [i for i in ids if i not in [j[0] for j in jobs]]
            if missing:
                raise InputError("not found as check: constraints in design/constraints.csv: %s" % ", ".join(missing))
            if not jobs:
                print("no constraint enforced by check:%s in design/constraints.csv" % (sub or ""))
                return 0
        passed = failed = waived = untracked = 0
        for cid, check, objects, limit, err in jobs:
            try:
                if err:
                    raise InputError(err)
                ok, lines = CHECK_FUNCS[check](b, parse_objects(objects, b), limit_of(limit), ctx)
            except InputError as e:
                ok, lines = False, ["cannot run: %s" % e]
            if ok is None:
                untracked += 1
                verdict = "NO TRACK (not measured)"
            elif ok:
                passed += 1
                verdict = "PASS"
            elif cid in waivers:
                waived += 1
                verdict = "WAIVED by %s" % waivers[cid]
            else:
                failed += 1
                verdict = "FAIL"
            print("%s %s %s" % (verdict, cid, check))
            for line in lines:
                print("    " + line)
        print("board_check: %d passed, %d failed, %d waived%s" % (
            passed, failed, waived, ", %d not measured (no track)" % untracked if untracked else ""))
        return 1 if failed else 0
    except (InputError, hwcommon.ProjectError, hwcommon.TableError, ValueError, OSError) as e:
        print("board_check: %s" % e, file=sys.stderr)
        return 2
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
