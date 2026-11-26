# Copyright 2026 Teklabs Digital (hw-skills)
# SPDX-License-Identifier: Apache-2.0
"""Board library: build a board from the netlist, route it with the grid router, prune, place the
silkscreen labels, and run KiCad's DRC with the zones poured again. Also routes a board someone
placed by hand, into a copy.

Needs KiCad's own Python (it imports pcbnew; KiCad's Python has no numpy, so this file uses the
standard library only). The router is the separate grid router library. It is looked for in
--router, else GRIDROUTER_PATH, else the folder router/ at the project root. A relative path is read
against the project root. No folder above the project root is searched, and the folder loaded is
printed. A path given that holds no router is an error.

Command line (python3 is KiCad's Python here; kicad_env.py prints where it is):

    python3 pcblib.py route BOARD OUT_DIR [--router DIR] [--budget SECONDS] [--no-refine] [--trace]
                                          [--design DIR] [--waive DC-nnn]
        Copies the folder holding BOARD (board, schematic, project and rule files, libraries) into
        OUT_DIR, routes the unrouted connections of the copy on the two outer layers with existing
        tracks, vias and zones kept as they are, saves the copy, and runs DRC with re-pour on it.
        BOARD is never written; its hash is checked afterwards.
    python3 pcblib.py drc BOARD [--design DIR] [--copy DIR] [--waive DC-nnn]
        DRC with zones poured again (kicad-cli pcb drc --refill-zones --save-board). In place only when
        design/ownership.csv records the board, and the .kicad_pro and .kicad_dru beside it, as written
        by a skill generator (with the hash on disk): the tables are read first, and the project and rule
        files are written again from them afterwards (KiCad rewrites them on save). On any other board
        (hand-owned, or written by the project's own build), on a copy: in --copy DIR when given, else a
        temporary folder; the project's own files are never written. Unreadable tables: exit 2.
        Clean means 0 violations, 0 unconnected items, and no schematic parity item other than those
        under "Expected DRC notes" in design/status.md.

Exit codes: 0 clean; 1 violations, unrouted connections or a DRC problem (a waiver given with
--waive is printed and the exit code is 0); 2 bad input; 3 a tool is missing or failed.

For a project's own board generator (scripts/gen_pcb.py), use GenBoard (see its docstring), imported
from the project's copy in hwskills/ as schlib.py shows. GenBoard reads
the netlist, writes the project and rule files through project_settings.py, places from one table with
a 3D-model check, adds outline, zones and keep-outs, routes through the same driver, prunes, places the
labels, saves, patches the stack-up and runs DRC in place. KiCad's ID generator is seeded so that two
builds give the same bytes.

"""
import argparse
import collections
import ctypes
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time

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

try:
    import pcbnew
except ImportError:                     # say where KiCad's Python is, then stop
    kicad_env.require_pcbnew("pcblib.py")
    raise

MM = pcbnew.FromMM
TO = pcbnew.ToMM

G = 0.1                     # router grid, mm
WRONG_WAY = 2.0             # a step against a layer's direction costs this much more (F.Cu across, B.Cu along)
DIAGONAL = 1.5              # a 45-degree step costs this times its length; times 1.414 it must stay above WRONG_WAY
VIA_COST = 400
MAX_RIPS = 600
SILK = (0.7, 0.8, 0.15)     # label character width, height, stroke (mm); GenBoard takes it from the tables
LABEL_GAPS = (0.2, 0.5, 0.8)
LABEL_FAR = 0.1
SKIP_COPY = ("~*.lck", "*.lck", "_autosave-*", "*-backups", "fp-info-cache", ".DS_Store")


class PcbError(Exception):
    pass


# ---------------------------------------------------------------- the router library

ROUTER_FOLDER = "router"    # the one place searched: this folder at the project root


def find_router(hint=None, start=None):
    """Folder holding the gridrouter package: hint (--router), else GRIDROUTER_PATH, else router/ at the
    root of the project that start (a KiCad file or folder) belongs to. A relative path is read against
    that project root. Nothing above the project root is searched. A path given that holds no router is
    an error, never a reason to look elsewhere. None when no path is given and router/ holds none."""
    root = hwcommon.project_root_of(start or os.getcwd())
    for given, name in ((hint, "--router"), (os.environ.get("GRIDROUTER_PATH"), "GRIDROUTER_PATH")):
        if given:
            path = os.path.abspath(os.path.join(root or os.getcwd(), given))
            if not os.path.isfile(os.path.join(path, "gridrouter", "__init__.py")):
                raise PcbError("grid router: %s (%s) holds no gridrouter/ package" % (path, name))
            return path
    if root and os.path.isfile(os.path.join(root, ROUTER_FOLDER, "gridrouter", "__init__.py")):
        return os.path.join(root, ROUTER_FOLDER)
    return None


def load_router(hint=None, start=None):
    """Import gridrouter without writing byte code into the router's folder. Prints the folder loaded."""
    path = find_router(hint, start)
    if not path:
        raise PcbError("grid router not found: clone it into %s/ at the project root (git-ignored), or pass "
                       "--router or set GRIDROUTER_PATH (the folder that holds gridrouter/), at a pinned commit "
                       "or tag (references/tooling.md). Folders above the project root are not searched."
                       % ROUTER_FOLDER)
    print("router: %s" % path, flush=True)
    if path not in sys.path:
        sys.path.insert(0, path)
    old, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        import gridrouter
        import gridrouter.kicad  # noqa: F401
    finally:
        sys.dont_write_bytecode = old
    return gridrouter


# ---------------------------------------------------------------- netlist and rule file

def read_netlist(path):
    """(components, nets, paths). components and nets as hwcommon.read_netlist; paths: ref -> the
    footprint path KiCad gives a footprint updated from the schematic (sheet path + symbol UUID)."""
    comps, nets = hwcommon.read_netlist(path)
    paths = {}
    root = hwcommon.read_sexpr(path)
    for c in hwcommon.find(hwcommon.first(root, "components", []), "comp"):
        sp = hwcommon.first(c, "sheetpath")
        stamps = hwcommon.value(sp, "tstamps", "/") if sp else "/"
        if not stamps.endswith("/"):
            stamps += "/"
        paths[hwcommon.value(c, "ref")] = stamps + hwcommon.value(c, "tstamps")
    return comps, nets, paths


def read_dru(path):
    """What the router must know from a .kicad_dru: {"no_via": set of net names, "clearance": {net: mm},
    "width": {net: mm}, "min_clearance": mm or 0}. Only rules whose condition is a list of
    A.NetName == '...' terms (as project_settings.py writes them) name nets; others are left to DRC."""
    out = {"no_via": set(), "clearance": {}, "width": {}, "min_clearance": 0.0}
    if not path or not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as f:
        text = "\n".join(l for l in f.read().splitlines() if not l.lstrip().startswith("#"))
    root = hwcommon.parse_sexpr("(dru\n" + text + "\n)")
    for rule in hwcommon.find(root, "rule"):
        cond = hwcommon.value(rule, "condition", "")
        nets = re.findall(r"A\.NetName\s*==\s*'([^']*)'", cond)
        if cond and (not nets or re.sub(r"A\.NetName\s*==\s*'[^']*'|\|\||\s", "", cond)):
            nets = None                     # some other condition: not a plain list of nets
        for c in hwcommon.find(rule, "constraint"):
            kind = str(c[1]) if len(c) > 1 else ""
            lim = {str(x[0]): str(x[1]) for x in c[2:] if isinstance(x, list) and len(x) > 1}
            if kind == "via_count" and lim.get("max") == "0" and nets:
                out["no_via"].update(nets)
            elif kind in ("clearance", "track_width") and "min" in lim:
                v = hwcommon.num(lim["min"].replace("mm", ""))
                if not cond and kind == "clearance":
                    out["min_clearance"] = max(out["min_clearance"], v)
                for n in nets or ():
                    d = out["clearance" if kind == "clearance" else "width"]
                    d[n] = max(d.get(n, 0.0), v)
    return out


def _rc(d):
    """Router disc radius in cells for a centre-to-centre distance d mm (cells closer than d are claimed;
    the router claims a cell when its distance is below r + 0.5)."""
    return max(0, int(math.ceil(round(d / G - 0.5, 6))))


class Rules:
    """Widths and clearances the router works to, from the board's net classes and the rule file."""

    def __init__(self, board, dru_path=None):
        ds = board.GetDesignSettings()
        ns = ds.m_NetSettings
        dru = read_dru(dru_path)
        self.no_via = dru["no_via"]
        d = ns.GetDefaultNetclass()
        self.track = TO(d.GetTrackWidth())
        self.clear = max(TO(d.GetClearance()), TO(ds.m_MinClearance), dru["min_clearance"])
        self.via_dia, self.via_drill = TO(d.GetViaDiameter()), TO(d.GetViaDrill())
        self.edge = TO(ds.m_CopperEdgeClearance)
        self.hole_to_hole = TO(ds.m_HoleToHoleMin)
        self.net = {}
        names = sorted(str(n) for n in board.GetNetsByName().keys() if str(n))
        for name in names:
            nc = ns.GetEffectiveNetClass(name)
            w = max(TO(nc.GetTrackWidth()), dru["width"].get(name, 0.0))
            c = max(TO(nc.GetClearance()), dru["clearance"].get(name, 0.0), self.clear)
            self.net[name] = (w, c)
            self.via_dia = max(self.via_dia, TO(nc.GetViaDiameter()))
            self.via_drill = max(self.via_drill, TO(nc.GetViaDrill()))
        widest = max([w for w, _ in self.net.values()] + [self.track])
        self.track_wide = max(widest, min(0.5, self.via_dia))

    def wide(self, name):
        return self.net.get(name, (self.track, 0))[0] > self.track + 1e-6

    def extra(self, name):
        """Extra clearance cells for a net whose class asks for more than the router's base clearance."""
        c = self.net.get(name, (0, self.clear))[1]
        return int(math.ceil(round((c - self.clear) / G, 6))) if c > self.clear + 1e-6 else 0

    def radii(self, width, clear=None):
        c = self.clear if clear is None else clear
        big = max(self.track_wide, self.via_dia)
        return _rc(width / 2 + c + self.track / 2), _rc(width / 2 + c + big / 2)

    def router(self, gr, nx, ny):
        c, big = self.clear, max(self.track_wide, self.via_dia)
        return gr.Router(
            nx, ny, G, strict=False, wrong_way=WRONG_WAY, diagonal=DIAGONAL,
            via_cost=VIA_COST, rip_cost=150, max_rips=MAX_RIPS, bend_45=12, bend_90=40,
            track=self.track, track_wide=self.track_wide,
            r_track=self.radii(self.track), r_wide=self.radii(self.track_wide), r_via=self.radii(self.via_dia),
            r_via_space=_rc(max(self.via_dia + c, self.via_drill + self.hole_to_hole)),
            pad_clear=(c + self.track / 2 + G / 2, c + big / 2 + G / 2), pad_novia=self.via_dia / 2 + 0.1,
            edge_margin=(self.edge + self.track / 2 + 0.05, self.edge + big / 2 + 0.05))

    def text(self):
        return ("track %.2f mm (wide %.2f), clearance %.2f mm, via %.2f/%.2f mm, edge %.2f mm; %d nets with more "
                "clearance, %d wide, %d without vias"
                % (self.track, self.track_wide, self.clear, self.via_dia, self.via_drill, self.edge,
                   sum(1 for n in self.net if self.extra(n)), sum(1 for n in self.net if self.wide(n)),
                   len(self.no_via)))


# ---------------------------------------------------------------- the routing driver

def _is_via(t):
    return t.Type() == pcbnew.PCB_VIA_T


def _seg_points(a, b, step):
    """Points from a to b (mm tuples) no more than step apart, ends included."""
    n = max(1, int(math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / step)))
    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]


def _track_points(t):
    s, e = t.GetStart(), t.GetEnd()
    pts = [(TO(s.x), TO(s.y))]
    if t.Type() == pcbnew.PCB_ARC_T:            # an arc as two straight pieces through its middle
        m = t.GetMid()
        pts.append((TO(m.x), TO(m.y)))
    pts.append((TO(e.x), TO(e.y)))
    return pts


class Driver:
    """Routes the unrouted connections of a board on F.Cu and B.Cu with the grid router.

    Reads the board as it is: outline, pads (any net, or none), existing tracks, vias and arcs (kept,
    as fixed copper of their net), copper zones (a net with a zone is a plane net: its pads that do
    not touch the zone get a short stub and a via), rule areas (keep-outs), net classes and the rule
    file (wider clearance, wider track, no vias). Connections already made by existing copper are not
    routed again. Only the items the router adds are pruned; nothing that was there is changed."""

    def __init__(self, board, gr, dru_path=None, blocks=(), log=print, trace=False):
        self.board, self.gr, self.log, self.trace = board, gr, log, trace
        self.rules = Rules(board, dru_path)
        poly = pcbnew.SHAPE_POLY_SET()
        if not board.GetBoardPolygonOutlines(poly, False) or poly.OutlineCount() == 0:
            raise PcbError("the board has no closed outline on Edge.Cuts")
        bb = poly.BBox()
        self.ox, self.oy = TO(bb.GetLeft()), TO(bb.GetTop())
        self.bw, self.bh = TO(bb.GetWidth()), TO(bb.GetHeight())
        self.nx, self.ny = int(round(self.bw / G)) + 1, int(round(self.bh / G)) + 1
        self.nc = self.nx * self.ny
        self.r = r = self.rules.router(gr, self.nx, self.ny)
        r.skip_joined_stubs = True
        self.outline = poly
        names = set()
        for fp in board.GetFootprints():
            names.update(p.GetNetname() for p in fp.Pads())
        names.update(t.GetNetname() for t in board.GetTracks())
        names.discard("")
        self.codes = dict((n, k + 1) for k, n in enumerate(sorted(names)))
        self.names = dict((v, k) for k, v in self.codes.items())
        self.free = len(self.codes) + 1
        self.netinfo = dict((n, board.FindNet(n)) for n in self.codes)
        self.notes = []
        self._outside(poly)
        self.planes = self._zones()
        for x0, y0, x1, y1 in blocks:
            r.block_rect(x0 - self.ox, y0 - self.oy, x1 - self.ox, y1 - self.oy)
        self.pads_of, self.clusters = {}, {}
        self._pads()
        self._existing()
        self._clusters()

    # -- reading the board
    def cell(self, x, y):
        """Grid (i, j) of a board position in mm."""
        return int(round((x - self.ox) / G)), int(round((y - self.oy) / G))

    def _outside(self, poly):
        """Cells outside a non-rectangular outline are blocked (the router's own frame covers the box)."""
        if abs(poly.Area() / 1e12 - self.bw * self.bh) < 0.01 * self.bw * self.bh:
            return
        r, nx = self.r, self.nx
        m = [_rc(self.rules.edge + self.rules.track / 2), _rc(self.rules.edge + max(self.rules.track_wide,
                                                                                    self.rules.via_dia) / 2)]
        out = []
        for j in range(self.ny):
            row = [not poly.Contains(pcbnew.VECTOR2I(MM(self.ox + i * G), MM(self.oy + j * G)))
                   for i in range(nx)]
            out.append(row)
            i = 0
            while i < nx:
                if row[i]:
                    k = i
                    while k + 1 < nx and row[k + 1]:
                        k += 1
                    for layer in (0, 1):
                        r.block_cells(layer, i, j, k, j)
                    i = k + 1
                else:
                    i += 1
        for j in range(self.ny):
            for i in range(nx):
                if out[j][i] and any(0 <= j + dj < self.ny and 0 <= i + di < nx and not out[j + dj][i + di]
                                     for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    for layer in (0, 1):
                        r.claim_disc(self.gr.BLOCK, layer, i, j, m[0], m[1])
                    r.novia[j * nx + i] = 1

    def _zones(self):
        """Copper zones by net (plane nets), and rule-area keep-outs blocked in the grid."""
        planes = {}
        r = self.r
        for z in self.board.Zones():
            layers = list(z.GetLayerSet().CuStack())
            if z.GetIsRuleArea():
                bb = z.GetBoundingBox()
                i0, j0 = self.cell(TO(bb.GetLeft()), TO(bb.GetTop()))
                i1, j1 = self.cell(TO(bb.GetRight()), TO(bb.GetBottom()))
                ol = z.Outline()
                for j in range(max(0, j0), min(self.ny - 1, j1) + 1):
                    for i in range(max(0, i0), min(self.nx - 1, i1) + 1):
                        if not ol.Contains(pcbnew.VECTOR2I(MM(self.ox + i * G), MM(self.oy + j * G))):
                            continue
                        if z.GetDoNotAllowTracks():
                            for k, l in enumerate((pcbnew.F_Cu, pcbnew.B_Cu)):
                                if l in layers:
                                    r.block_cells(k, i, j, i, j)
                        if z.GetDoNotAllowVias():
                            r.novia[j * self.nx + i] = 1
                continue
            name = z.GetNetname()
            if name in self.codes:
                planes.setdefault(name, []).append(z)
        return planes

    def _on_plane(self, name, layer_ids, pos):
        """True when copper on these layers at pos (VECTOR2I) lies inside a zone of the net."""
        return any(l in z.GetLayerSet().CuStack() and z.Outline().Contains(pos)
                   for z in self.planes.get(name, ()) for l in layer_ids)

    def _pads(self):
        r, rules = self.r, self.rules
        self.pad_info = []          # (name, code, layers, cx, cy, bbox, label, pad)
        for fp in self.board.GetFootprints():
            ref = fp.GetReference()
            for pad in fp.Pads():
                name = pad.GetNetname()
                layers = tuple(k for k, l in enumerate((pcbnew.F_Cu, pcbnew.B_Cu)) if pad.IsOnLayer(l))
                b = pad.GetBoundingBox()
                x0, y0 = TO(b.GetLeft()) - self.ox, TO(b.GetTop()) - self.oy
                x1, y1 = TO(b.GetRight()) - self.ox, TO(b.GetBottom()) - self.oy
                c = pad.GetPosition()
                cx, cy = TO(c.x) - self.ox, TO(c.y) - self.oy
                if not layers:
                    if pad.GetDrillSize().x > 0:            # a bare hole: no via or track over it
                        d = rules.clear
                        r.block_rect(x0 - d, y0 - d, x1 + d, y1 + d)
                    continue
                code = self.codes.get(name) if name else None
                if code is None:
                    code, self.free = self.free, self.free + 1
                r.add_pad(code, layers, cx, cy, x0, y0, x1, y1, rules.extra(name) if name else 0)
                self.pad_info.append((name, code, layers, cx, cy, (x0, y0, x1, y1),
                                      "%s.%s" % (ref, pad.GetNumber()), pad))

    def _existing(self):
        """Existing tracks and vias: fixed copper of their net. Their cells join their clusters."""
        r, rules, nx = self.r, self.rules, self.nx
        self.track_cells = collections.defaultdict(set)     # id(item) -> {(layer, idx)}
        self.existing = []
        for t in self.board.GetTracks():
            name = t.GetNetname()
            code = self.codes.get(name)
            if code is None:
                code, self.free = self.free, self.free + 1
            w, c = rules.net.get(name, (rules.track, rules.clear))
            c = max(c, rules.clear)
            self.existing.append(t)
            if _is_via(t):
                p = t.GetPosition()
                i, j = self.cell(TO(p.x), TO(p.y))
                rt, rw = rules.radii(TO(t.GetWidth(pcbnew.F_Cu)), c)
                for layer in (0, 1):
                    r.claim_disc(code, layer, i, j, rt, rw)
                    self.track_cells[id(t)].add((layer, j * nx + i))
                rs = r.r_via_space
                for dj in range(-rs, rs + 1):
                    for di in range(-rs, rs + 1):
                        if di * di + dj * dj < (rs + 0.5) ** 2 and 0 <= i + di < nx and 0 <= j + dj < self.ny:
                            r.novia[(j + dj) * nx + i + di] = 1
                continue
            layer = {pcbnew.F_Cu: 0, pcbnew.B_Cu: 1}.get(t.GetLayer())
            pts = _track_points(t)
            tw = TO(t.GetWidth())
            if layer is None:       # inner-layer track: no via of another net through it
                rv = _rc(tw / 2 + c + rules.via_dia / 2)
                for a, b in zip(pts, pts[1:]):
                    for x, y in _seg_points(a, b, G / 2):
                        i, j = self.cell(x, y)
                        for dj in range(-rv, rv + 1):
                            for di in range(-rv, rv + 1):
                                if di * di + dj * dj < (rv + 0.5) ** 2 and 0 <= i + di < nx and 0 <= j + dj < self.ny:
                                    r.novia[(j + dj) * nx + i + di] = 1
                continue
            rt, rw = rules.radii(tw, c)
            for a, b in zip(pts, pts[1:]):
                for x, y in _seg_points(a, b, G / 2):
                    i, j = self.cell(x, y)
                    if 0 <= i < nx and 0 <= j < self.ny:
                        r.claim_disc(code, layer, i, j, rt, rw)
                        self.track_cells[id(t)].add((layer, j * nx + i))

    def _clusters(self):
        """Pads of a net already joined by existing copper form one cluster (KiCad's connectivity)."""
        self.board.BuildConnectivity()
        conn = self.board.GetConnectivity()
        uuid_of = dict((pi[7].m_Uuid.AsString(), k) for k, pi in enumerate(self.pad_info))
        parent = list(range(len(self.pad_info)))

        def root(k):
            while parent[k] != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k
        cells_of = collections.defaultdict(set)
        tracks_by_uuid = dict((t.m_Uuid.AsString(), t) for t in self.existing)
        for k, pi in enumerate(self.pad_info):
            if not pi[0] or pi[0] not in self.codes:
                continue
            for item in conn.GetConnectedItems(pi[7]):
                cls = type(item).__name__
                if cls == "PAD":
                    k2 = uuid_of.get(item.m_Uuid.AsString())
                    if k2 is not None:
                        parent[root(k2)] = root(k)
                elif cls in ("PCB_TRACK", "PCB_VIA", "PCB_ARC"):
                    t = tracks_by_uuid.get(item.m_Uuid.AsString())
                    if t is not None:
                        cells_of[k] |= self.track_cells[id(t)]
        groups = collections.OrderedDict()
        for k, pi in enumerate(self.pad_info):
            if pi[0] and pi[0] in self.codes:
                groups.setdefault(root(k), []).append(k)
        for g, members in groups.items():
            name = self.pad_info[members[0]][0]
            cells = set()
            for k in members:
                cells |= cells_of.get(k, set())
            self.clusters.setdefault(name, []).append((members, cells))

    def _pad_cells(self, pi):
        """Usable cells of a pad: inside it and not in a neighbour's clearance; the centre when usable."""
        r, nx = self.r, self.nx
        code, layers, cx, cy, (x0, y0, x1, y1) = pi[1], pi[2], pi[3], pi[4], pi[5]
        cells = []
        for j in range(int(y0 / G) + 1, int(y1 / G) + 1):
            for i in range(int(x0 / G) + 1, int(x1 / G) + 1):
                if x0 < i * G < x1 and y0 < j * G < y1:
                    for layer in layers:
                        if r.T[layer][j * nx + i] in (0, code):
                            cells.append((layer, j * nx + i))
        mid = [c for c in cells if abs((c[1] % nx) * G - cx) < G * 0.75 and abs((c[1] // nx) * G - cy) < G * 0.75]
        return mid or cells

    # -- routing
    def run(self, budget=None, refine=True, polish=3):
        t0 = time.time()
        r, rules, nx = self.r, self.rules, self.nx
        pads_of = self.pads_of
        drops = []
        for name in sorted(self.clusters):
            groups = self.clusters[name]
            code = self.codes[name]
            entries = []
            for members, tcells in groups:
                cells = set(tcells)
                for k in members:
                    cells.update(self._pad_cells(self.pad_info[k]))
                for layer, idx in tcells:   # existing copper is an anchor: a path may end on it
                    r.padcell.setdefault(code, {})[(layer, idx)] = ((idx % nx) * G, (idx // nx) * G)
                p0 = self.pad_info[members[0]]
                boxes = [self.pad_info[k][5] for k in members]
                bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                        max(b[2] for b in boxes), max(b[3] for b in boxes))
                layers = tuple(sorted(set(l for k in members for l in self.pad_info[k][2])))
                entries.append([p0[3], p0[4], layers, sorted(cells), p0[6], bbox, members])
            if name in self.planes:
                for e in entries:
                    on = any(self._on_plane(name, list(self.pad_info[k][7].GetLayerSet().CuStack()),
                                            self.pad_info[k][7].GetPosition()) for k in e[6])
                    on = on or any(_is_via(t) and t.GetNetname() == name and
                                   self._on_plane(name, list(self.board.GetEnabledLayers().CuStack()),
                                                  t.GetPosition())
                                   for t in self.existing if self.track_cells[id(t)] & set(e[3]))
                    if not on:
                        drops.append((name, e))
                continue
            if len(entries) > 1:
                pads_of[name] = entries
        # 1. plane nets: a stub and a via from each piece that does not touch its zone
        for name, e in sorted(drops, key=lambda d: (d[0], d[1][0], d[1][1])):
            joined = set()
            mask = self._plane_mask(name)
            saved = bytes(r.novia) if mask else None
            if mask:
                for idx in mask:
                    r.novia[idx] = 1
            if not r.drop_to_plane(self.codes[name], name, e, joined):
                r.failed.pop()
                r.drop_to_plane(self.codes[name], name, e, joined, max_cost=4000)
            if saved is not None:
                ctypes.memmove(r.novia, saved, self.nc)
        r.snapshot()
        drop_fail = list(r.failed)
        r.failed = []
        self.feud, self.via_allowed = {}, set()

        def span(name):
            ps = pads_of[name]
            return max(p[0] for p in ps) - min(p[0] for p in ps) + max(p[1] for p in ps) - min(p[1] for p in ps)
        self.span = span
        special = lambda n: n in rules.no_via or rules.wide(n) or rules.extra(n)
        queue = sorted((n for n in pads_of if n in rules.no_via), key=lambda n: -span(n))
        queue += sorted((n for n in pads_of if n not in rules.no_via and special(n)), key=lambda n: -span(n))
        queue += sorted((n for n in pads_of if not special(n)), key=lambda n: (-span(n), n))
        self.log("routing: %d nets to route, %d plane pieces to drop to their zone; %s"
                 % (len(queue), len(drops), rules.text()))
        stopped = False
        while queue:
            name = queue.pop(0)
            if budget and time.time() - t0 > budget:
                r.failed.append(("time budget", name))
                stopped = True
                break
            if self.trace:
                print("  %5.0f s  rips %3d  queue %3d  %s" % (time.time() - t0, r.rips, len(queue), name),
                      file=sys.stderr, flush=True)
            for v in self.route(name):
                if v not in queue:
                    queue.append(v)
        if not stopped:
            self.settle()
            for _ in range(polish):
                if r.failed:
                    break
                for name in sorted((n for n in r.log if n in pads_of), key=lambda n: (-span(n), n)):
                    saved, r.rips = r.rips, r.MAX_RIPS
                    r.rip(self.codes[name])
                    r.log.pop(name, None)
                    self.route(name)
                    r.rips = saved
                self.settle()
            if refine and not r.failed:
                self.refine()
        r.failed = drop_fail + r.failed
        return time.time() - t0

    def _plane_mask(self, name):
        """Cells where a via of this plane net would miss every zone of the net (only for zones that do
        not cover the whole board)."""
        zs = self.planes.get(name, [])
        area = self.bw * self.bh
        if any(z.Outline().Area() / 1e12 >= 0.98 * area for z in zs):
            return []
        out = []
        for j in range(self.ny):
            for i in range(self.nx):
                p = pcbnew.VECTOR2I(MM(self.ox + i * G), MM(self.oy + j * G))
                if not any(z.Outline().Contains(p) for z in zs):
                    out.append(j * self.nx + i)
        return out

    def widen(self, name):
        """Copper of other nets already near this net's area grows by the net's extra clearance while it
        is laid (the router's extra clearance only keeps later nets away). Returns cells to free again."""
        r, nx, ny, px = self.r, self.nx, self.ny, self.rules.extra(name)
        net = self.codes[name]
        ps = self.pads_of[name]
        m = int(6 / G)
        i0, i1 = max(0, int(min(q[0] for q in ps) / G) - m), min(nx - 1, int(max(q[0] for q in ps) / G) + m)
        j0, j1 = max(0, int(min(q[1] for q in ps) / G) - m), min(ny - 1, int(max(q[1] for q in ps) / G) + m)
        w, h = i1 - i0 + 1, j1 - j0 + 1
        own = [tuple(int(round(v / G)) for v in q[5]) for q in ps]
        on_pad = lambda i, j: any(a <= i <= c and b <= j <= d for a, b, c, d in own)
        changed = []
        block = self.gr.BLOCK
        for grid in (r.T[0], r.T[1], r.W[0], r.W[1]):
            rows = [grid[j * nx + i0:j * nx + i1 + 1] for j in range(j0, j1 + 1)]
            near = []
            for row in rows:
                f = [v != 0 and v != net for v in row]
                near.append([any(f[max(0, i - px):i + px + 1]) for i in range(w)] if any(f) else None)
            for j in range(h):
                band = [n for n in near[max(0, j - px):j + px + 1] if n is not None]
                if not band:
                    continue
                row, base = rows[j], (j0 + j) * nx + i0
                for i in range(w):
                    if (row[i] == 0 or row[i] == net) and any(n[i] for n in band) \
                            and not (row[i] == net and on_pad(i0 + i, j0 + j)):
                        grid[base + i] = block
                        changed.append((grid, base + i, row[i]))
        return changed

    def protect(self, victims):
        r, marked = self.r, []
        for v in victims:
            code = self.codes[v]
            for lev, hard in ((r.T, r.hardT), (r.W, r.hardW)):
                for layer in (0, 1):
                    cur, hd = lev[layer], hard[layer]
                    for idx, val in enumerate(list(cur)):
                        if val == code and hd[idx] == 0:
                            hd[idx] = code
                            marked.append((hd, idx))
        return marked

    def route(self, name, novia=None):
        r, rules = self.r, self.rules
        extra = rules.extra(name)
        grown = self.widen(name) if extra else []
        marked = self.protect([v for (n, v), k in self.feud.items() if n == name and k >= 2])
        top_only = (name in rules.no_via and name not in self.via_allowed) if novia is None else novia
        wide = rules.wide(name)
        if top_only:
            saved = bytes(r.novia)
            ctypes.memset(r.novia, 2, self.nc)
            ripped = r.route_net(self.codes[name], name, self.pads_of[name], wide, extra)
            live = bytes(r.novia)
            ctypes.memmove(r.novia, bytes(o if v == 2 else v for v, o in zip(live, saved)), self.nc)
            if novia is None and any(f[0] == name for f in r.failed):
                self.log("  %s: no route without vias; vias allowed (the rule file will report them)" % name)
                self.via_allowed.add(name)
        else:
            ripped = r.route_net(self.codes[name], name, self.pads_of[name], wide, extra)
        for hd, idx in marked:
            hd[idx] = 0
        for grid, idx, was in grown:
            if grid[idx] == self.gr.BLOCK:
                grid[idx] = was
        for v in ripped:
            self.feud[(name, v)] = self.feud.get((name, v), 0) + 1
        return ripped

    def settle(self):
        r = self.r
        for _ in range(3):
            again = sorted(set(f[0] for f in r.failed if f[0] in self.pads_of))
            if not again:
                break
            queue = list(again)
            for key in [k for k in self.feud if k[0] in again]:
                del self.feud[key]
            while queue:
                name = queue.pop(0)
                r.rip(self.codes[name])
                r.log.pop(name, None)
                for v in self.route(name):
                    if v not in queue:
                        queue.append(v)

    def measure(self, name):
        """(vias in use, track length mm) of a net as it lies in the router now."""
        r, nx = self.r, self.nx
        code = self.codes[name]
        edges = r.edges.get(code, {0: set(), 1: set()})
        ends = [set(c for e in edges[layer] for c in e) for layer in (0, 1)]
        cells = r.padcell.get(code, {})
        used = sum(all((i, j) in ends[layer] or (layer, j * nx + i) in cells for layer in (0, 1))
                   for i, j in r.vias.get(code, ()))
        length = sum(G * math.hypot(a[0] - b[0], a[1] - b[1]) for layer in (0, 1) for a, b in edges[layer])
        return used, round(length, 6)

    def refine(self):
        """Second look: each net in turn is lifted and laid again in several ways (one layer, vias allowed,
        from another pad) with the others left in place; kept only with fewer vias, or the same vias and
        less track. Then group moves: a net with vias takes a one-layer path through up to three others,
        which are laid again round it; kept only if the group as a whole is better."""
        r, pads_of, rules = self.r, self.pads_of, self.rules

        def better(new, old):
            return (new[0] < old[0] and new[1] <= old[1] + 8.0 * (old[0] - new[0])) \
                or (new[0] == old[0] and new[1] < old[1] - 0.3)
        nets = [n for n in sorted(r.log) if n in pads_of]
        before = [sum(self.measure(n)[k] for n in nets) for k in (0, 1)]
        improved, groups = {}, 0
        for _ in range(3):
            changed = False
            for name in sorted(nets, key=lambda n: (self.measure(n), n), reverse=True):
                code, start = self.codes[name], self.measure(name)
                best = (start, list(r.log[name]), list(pads_of[name]))
                pads = list(pads_of[name])
                fixed = name in rules.no_via and name not in self.via_allowed
                saved, r.rips = r.rips, r.MAX_RIPS
                for k in range(min(len(pads), 4)):
                    for top_only in ((True,) if fixed else (True, False)):
                        r.rip(code)
                        r.log.pop(name, None)
                        pads_of[name] = pads[k:] + pads[:k]
                        self.route(name, novia=top_only)
                        if any(f[0] == name for f in r.failed):
                            r.failed = [f for f in r.failed if f[0] != name]
                            continue
                        got = self.measure(name)
                        if better(got, best[0]):
                            best = (got, list(r.log[name]), list(pads_of[name]))
                r.rip(code)
                for item in best[1]:
                    r.commit(*item)
                r.log[name] = best[1]
                pads_of[name] = best[2]
                r.rips = saved
                if best[0] != start:
                    improved[name] = (improved.get(name, (start,))[0], best[0])
                    changed = True
            if not changed:
                break
        for _ in range(2):
            changed = False
            for name in sorted((n for n in nets if self.measure(n)[0] > 0), key=lambda n: (self.measure(n), n),
                               reverse=True):
                old_log = dict((n, list(items)) for n, items in r.log.items())
                old_pads = dict((n, list(ps)) for n, ps in pads_of.items())
                old_feud, old_rips = dict(self.feud), r.rips
                old_m = dict((n, self.measure(n)) for n in nets)
                self.feud.clear()
                r.rips = 0
                r.rip(self.codes[name])
                r.log.pop(name, None)
                victims = list(collections.OrderedDict.fromkeys(self.route(name, novia=True)))
                group = [name] + victims
                ok = not any(f[0] == name for f in r.failed) and 0 < len(victims) <= 3 \
                    and all(v in nets and v not in rules.no_via for v in victims)
                r.rips = r.MAX_RIPS
                for v in victims if ok else ():
                    self.route(v)
                    ok = ok and not any(f[0] == v for f in r.failed)
                r.failed = [f for f in r.failed if f[0] not in group]
                was = (sum(old_m[n][0] for n in group), sum(old_m[n][1] for n in group))
                now = (sum(self.measure(n)[0] for n in group), sum(self.measure(n)[1] for n in group)) if ok else None
                if ok and better(now, was):
                    groups += 1
                    changed = True
                    for n in group:
                        improved[n] = (improved.get(n, (old_m[n],))[0], self.measure(n))
                else:
                    for n in group:
                        r.rip(self.codes[n])
                    for n in group:
                        for item in old_log.get(n, []):
                            r.commit(*item)
                        if n in old_log:
                            r.log[n] = old_log[n]
                        pads_of[n] = old_pads[n]
                self.feud.clear()
                self.feud.update(old_feud)
                r.rips = old_rips
            if not changed:
                break
        after = [sum(self.measure(n)[k] for n in nets) for k in (0, 1)]
        self.log("second look: %d nets improved (%d group moves), vias in use %d -> %d, track %.0f -> %.0f mm"
                 % (len(improved), groups, before[0], after[0], before[1], after[1]))

    # -- writing the result
    def emit(self):
        """Add the router's tracks and vias to the board. Returns the new items."""
        old = set(t.m_Uuid.AsString() for t in self.board.GetTracks())
        n_seg, n_via = self.gr.kicad.emit(self.board, self.r, self.netinfo, self.names, pcbnew,
                                          origin=(self.ox, self.oy), via_dia=self.rules.via_dia,
                                          via_drill=self.rules.via_drill)
        new = [t for t in self.board.GetTracks() if t.m_Uuid.AsString() not in old]
        self.log("routed: %d segments, %d vias, %d rip-ups" % (n_seg, n_via, self.r.rips))
        return new


def prune(board, new_items, plane_nets, log=print):
    """Remove what the router added and nothing uses: vias with copper on one side only (a plane net's
    via is kept: it joins the zone), dead-end track pieces (cut back to the last join). Items that were
    on the board before routing are never touched. Returns (vias removed, tracks removed, cut back)."""
    new = set(t.m_Uuid.AsString() for t in new_items)

    def on_segment(t, q, slack=2000):
        a, b = t.GetStart(), t.GetEnd()
        dx, dy = b.x - a.x, b.y - a.y
        n2 = dx * dx + dy * dy
        u = 0.0 if n2 == 0 else max(0.0, min(1.0, ((q.x - a.x) * dx + (q.y - a.y) * dy) / n2))
        ex, ey = a.x + u * dx - q.x, a.y + u * dy - q.y
        return ex * ex + ey * ey <= slack * slack
    pads = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pads.setdefault(pad.GetNetname(), []).append(pad)
    n_via = n_trk = n_cut = 0
    while True:
        tracks, vias, changed = {}, {}, False
        for t in board.GetTracks():
            (vias if _is_via(t) else tracks).setdefault(t.GetNetname(), []).append(t)
        dead = []
        for name, vs in vias.items():
            for v in vs:
                if v.m_Uuid.AsString() not in new or name in plane_nets:
                    continue
                q = v.GetPosition()
                sides = [any(t.GetLayer() == layer and on_segment(t, q) for t in tracks.get(name, []))
                         or any(pd.IsOnLayer(layer) and pd.HitTest(q) for pd in pads.get(name, []))
                         for layer in (pcbnew.F_Cu, pcbnew.B_Cu)]
                if not all(sides):
                    dead.append(v)
        gone = set((v.GetNetname(), v.GetPosition().x, v.GetPosition().y) for v in dead)
        for name, ts in tracks.items():
            for t in ts:
                if t.m_Uuid.AsString() not in new:
                    continue
                for q in (t.GetStart(), t.GetEnd()):
                    if name in plane_nets and (name, q.x, q.y) not in gone and \
                            any(on_segment(t, v.GetPosition()) for v in vias.get(name, []) if v not in dead):
                        continue
                    held = any(pd.IsOnLayer(t.GetLayer()) and pd.HitTest(q) for pd in pads.get(name, [])) \
                        or any(v not in dead and (v.GetPosition().x - q.x) ** 2 + (v.GetPosition().y - q.y) ** 2 < 4e6
                               for v in vias.get(name, [])) \
                        or any(o is not t and o.GetLayer() == t.GetLayer() and on_segment(o, q) for o in ts)
                    if held:
                        continue
                    joins = [oq for o in ts if o is not t and o.GetLayer() == t.GetLayer()
                             for oq in (o.GetStart(), o.GetEnd())]
                    joins += [v.GetPosition() for v in vias.get(name, []) if v not in dead]
                    joins += [pd.GetPosition() for pd in pads.get(name, []) if pd.IsOnLayer(t.GetLayer())]
                    joins = [j for j in joins if on_segment(t, j) and (j.x - q.x) ** 2 + (j.y - q.y) ** 2 > 4e6]
                    far = t.GetEnd() if q == t.GetStart() else t.GetStart()
                    j = min(joins, key=lambda j: (j.x - q.x) ** 2 + (j.y - q.y) ** 2) if joins else far
                    if (j.x - far.x) ** 2 + (j.y - far.y) ** 2 > 4e6:
                        if q == t.GetStart():
                            t.SetStart(pcbnew.VECTOR2I(j.x, j.y))
                        else:
                            t.SetEnd(pcbnew.VECTOR2I(j.x, j.y))
                        n_cut += 1
                        changed = True
                    else:
                        dead.append(t)
                    break
        if not dead and not changed:
            break
        for item in dead:
            n_via += _is_via(item)
            n_trk += not _is_via(item)
            board.Remove(item)
    log("pruned: %d unused vias, %d dead-end track pieces, %d tracks cut back" % (n_via, n_trk, n_cut))
    return n_via, n_trk, n_cut


def route_board(board, gr, dru_path=None, budget=None, refine=True, polish=3, blocks=(), log=print, trace=False):
    """Route a board in memory with the grid router, then prune. Returns a dict of results:
    failed (list of (net, where)), segments, vias, seconds, existing (tracks and vias kept)."""
    d = Driver(board, gr, dru_path, blocks, log, trace)
    seconds = d.run(budget, refine, polish)
    new = d.emit()
    pruned = prune(board, new, set(d.planes), log)
    segs = sum(1 for t in board.GetTracks() if not _is_via(t))
    vias = sum(1 for t in board.GetTracks() if _is_via(t))
    length = sum(TO(t.GetLength()) for t in board.GetTracks() if not _is_via(t))
    res = {"failed": list(d.r.failed), "segments": segs, "vias": vias, "length": length,
           "seconds": seconds, "existing": len(d.existing), "pruned": pruned, "nets": len(d.pads_of)}
    log("board copper: %d track pieces (%.0f mm), %d vias, %d kept from before routing; %.1f s"
        % (segs, length, vias, len(d.existing), seconds))
    if d.r.failed:
        log("NOT ROUTED: " + "; ".join("%s at %s" % (f[0], f[1]) for f in d.r.failed))
    return res


# ---------------------------------------------------------------- silkscreen labels

def place_labels(board, refs=None, silk=SILK, silk_clearance=0.15, edge=0.4, log=print):
    """Reference designators on F.SilkS at the given size, each at the best free spot beside its part:
    touching it, clearly nearer to it than to any neighbour, off pads, other silk and other labels.
    A part with no such spot keeps its designator on F.Fab only. Only for generated boards: a
    hand-placed board's labels are the engineer's. Returns (placed refs, refs on F.Fab only)."""
    cw, chh, ct = silk
    poly = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(poly, False)
    ob = poly.BBox()
    BX0, BY0, BX1, BY1 = TO(ob.GetLeft()), TO(ob.GetTop()), TO(ob.GetRight()), TO(ob.GetBottom())
    fps = dict((f.GetReference(), f) for f in board.GetFootprints()
               if refs is None or f.GetReference() in refs)

    def bb(item, d=0.0):
        b = item.GetBoundingBox()
        return (TO(b.GetLeft()) - d, TO(b.GetTop()) - d, TO(b.GetRight()) + d, TO(b.GetBottom()) + d)

    def hit(a, b):
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

    def gap(a, b):
        return math.hypot(max(a[0] - b[2], b[0] - a[2], 0.0), max(a[1] - b[3], b[1] - a[3], 0.0))
    pads, silkb, body, size = [], [], {}, {}
    for ref, fp in sorted(fps.items()):
        own = []
        for pad in fp.Pads():
            if pad.IsOnLayer(pcbnew.F_Cu):
                pads.append(bb(pad, silk_clearance + 0.05))
                own.append(bb(pad))
        for g in fp.GraphicalItems():
            if g.GetLayer() == pcbnew.F_SilkS:
                silkb.append(bb(g, 0.25))
            elif g.GetLayer() == pcbnew.F_Fab and g.Type() == pcbnew.PCB_SHAPE_T:
                own.append(bb(g))
        if not own:
            own = [bb(fp)]
        body[ref] = (min(b[0] for b in own), min(b[1] for b in own), max(b[2] for b in own), max(b[3] for b in own))
        fp.Value().SetVisible(False)
        t = fp.Reference()
        t.SetLayer(pcbnew.F_SilkS)
        t.SetTextSize(pcbnew.VECTOR2I(MM(cw), MM(chh)))
        t.SetTextThickness(MM(ct))
        t.SetKeepUpright(True)
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        t.SetTextAngleDegrees(0)
        size[ref] = (len(ref) * cw * 0.95 + ct, chh + ct + 0.05)
    vias = [bb(t, 0.05) for t in board.GetTracks() if _is_via(t)]
    area = lambda r: (body[r][2] - body[r][0]) * (body[r][3] - body[r][1])

    def attempt(order):
        placed, chosen, hidden = [], {}, []
        for ref in order:
            x0, y0, x1, y1 = body[ref]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            w, h = size[ref]
            cand = []
            slides = [k * 0.2 for k in range(-8, 9)]
            for g_ in LABEL_GAPS:
                for rot, tw, th in ((0, w, h), (90, h, w)):
                    base = 0.3 * (rot != 0) + 2.5 * (g_ - LABEL_GAPS[0])
                    for s_ in slides:
                        if abs(s_) <= max(0.0, (x1 - x0) / 2 + tw / 2 - 0.4):
                            cand += [(cx + s_, y0 - g_ - th / 2, rot, abs(s_) + base, g_),
                                     (cx + s_, y1 + g_ + th / 2, rot, abs(s_) + base + 0.05, g_)]
                        if abs(s_) <= max(0.0, (y1 - y0) / 2 + th / 2 - 0.4):
                            cand += [(x0 - g_ - tw / 2, cy + s_, rot, abs(s_) + base + 0.1, g_),
                                     (x1 + g_ + tw / 2, cy + s_, rot, abs(s_) + base + 0.15, g_)]
            if area(ref) > 30:
                for dx, dy in ((0, 0), (0, -1.5), (0, 1.5), (-3, 0), (3, 0)):
                    cand += [(cx + dx, cy + dy, 0, 9.0 + abs(dx) / 10, 0), (cx + dx, cy + dy, 90, 9.3 + abs(dx) / 10, 0)]
            best = None
            for tx, ty, rot, pref, g_ in cand:
                tw, th = (w, h) if rot == 0 else (h, w)
                box = (tx - tw / 2, ty - th / 2, tx + tw / 2, ty + th / 2)
                inside = pref >= 9.0
                if box[0] < BX0 + edge or box[1] < BY0 + edge or box[2] > BX1 - edge or box[3] > BY1 - edge:
                    continue
                if inside and not (x0 < box[0] and box[2] < x1 and y0 < box[1] and box[3] < y1):
                    continue
                if any(hit(box, o) for o in pads + silkb + placed):
                    continue
                others = [gap(box, b) for r2, b in body.items() if r2 != ref] or [9.9]
                if not inside and min(others) < g_ + LABEL_FAR:
                    continue
                if inside and any(hit(box, b) for r2, b in body.items() if r2 != ref):
                    continue
                n_via = sum(hit(box, v) for v in vias)
                cost = pref + 1.5 * n_via - 0.1 * min(min(others), 1.5)
                if best is None or cost < best[0]:
                    best = (cost, tx, ty, rot, box)
            if best is None:
                hidden.append(ref)
            else:
                box = best[4]
                placed.append((box[0] - 0.35, box[1] - 0.2, box[2] + 0.35, box[3] + 0.2) if best[3] == 0 else
                              (box[0] - 0.2, box[1] - 0.35, box[2] + 0.2, box[3] + 0.35))
                chosen[ref] = best[1:]
        return chosen, hidden
    small = sorted(fps, key=lambda r: (area(r), hwcommon.ref_key(r)))
    key_parts = [r for r in small if r[0] in "UJ" or r.startswith("SW")]
    orders = [small, small[::-1], key_parts + [r for r in small if r not in key_parts]]
    for seed in (1, 2, 3):
        mixed = list(small)
        random.Random(seed).shuffle(mixed)
        orders.append(key_parts + [r for r in mixed if r not in key_parts])
    score = lambda res: len(res[0]) + sum(r in res[0] for r in key_parts)
    picked, hidden = max((attempt(o) for o in orders), key=score)
    for ref, fp in fps.items():
        t = fp.Reference()
        t.SetVisible(True)
        if ref not in picked:
            t.SetLayer(pcbnew.F_Fab)
            continue
        tx, ty, rot, box = picked[ref]
        t.SetTextAngleDegrees(rot)
        t.SetPosition(pcbnew.VECTOR2I(MM(tx), MM(ty)))
    log("silk labels: %.2f mm high, %d of %d placed; on F.Fab only: %s"
        % (chh, len(picked), len(fps), ", ".join(sorted(hidden, key=hwcommon.ref_key)) or "none"))
    return sorted(picked), sorted(hidden)


# ---------------------------------------------------------------- DRC

def run_drc(board_path, save=False, cli=None):
    """kicad-cli DRC as JSON with zones poured again; save=True writes the poured board back."""
    cli = cli or kicad_env.find_kicad_cli()
    if not cli:
        raise PcbError("kicad-cli not found; set KICAD_CLI (python3 kicad_env.py shows the search)")
    tmp = tempfile.mkdtemp()
    try:
        report = os.path.join(tmp, "drc.json")
        cmd = [cli, "pcb", "drc", "--format", "json", "--severity-all", "--schematic-parity", "--refill-zones"]
        if save:
            cmd.append("--save-board")
        res = subprocess.run(cmd + ["-o", report, board_path], capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if not os.path.isfile(report):
            raise PcbError("kicad-cli pcb drc wrote no report:\n" + res.stdout + res.stderr)
        with open(report, encoding="utf-8") as f:
            return json.load(f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def drc_problems(report, expected):
    """(problems, expected notes found). The clean-report test: every violation and unconnected item
    is a problem, and every schematic parity item not matched by an expected note (text, item, DC-)."""
    found, other = [], []
    for v in report.get("schematic_parity", []):
        items = [i.get("description", "") for i in v.get("items", [])]
        hit = [e for e in expected if e[0] in v.get("description", "") and e[1] in items]
        (found if hit else other).append(v)
    return report.get("violations", []) + report.get("unconnected_items", []) + other, found


def describe(v):
    where = "; ".join(i.get("description", "")[:60] for i in v.get("items", []))
    return "%s %s: %s%s" % (v.get("severity", ""), v.get("type", ""), v.get("description", ""),
                            " (%s)" % where if where else "")


def board_owner(board_path, design_dir=None):
    """("script", writer) when design/ownership.csv records the file (the board, or any design file) as
    script-owned with the hash on disk; else ("hand", reason). A file with no record is hand-owned."""
    design = design_dir or hwcommon.design_dir_for(board_path)
    path = os.path.join(design, "ownership.csv")
    if not os.path.isfile(path):
        return "hand", "no design/ownership.csv"
    rel = os.path.relpath(os.path.abspath(board_path), os.path.dirname(os.path.abspath(design))).replace(os.sep, "/")
    for r in hwcommon.read_table(path):
        if r["path"] == rel:
            if r["owner"] != "script":
                return "hand", "recorded as hand-owned"
            if r["hash"] != hwcommon.sha256_file(board_path):
                return "hand", "changed since the last script write"
            return "script", r["writer"]
    return "hand", "no ownership record"


OWN_BUILD = "(own build)"       # the writer build.py --adopt --reproduce records for a project's own build


def in_place_refusal(board_path, design_dir=None):
    """None when DRC may save this board in place and write its project and rule files again from the
    tables; else the reason it runs on a copy. In place needs the board, and the .kicad_pro and .kicad_dru
    beside it, all recorded as written by a skill generator, never by the project's own build or by hand."""
    stem = os.path.splitext(board_path)[0]
    for path in (board_path, stem + ".kicad_pro", stem + ".kicad_dru"):
        if path != board_path and not os.path.isfile(path):
            continue
        owner, why = board_owner(path, design_dir)
        name = os.path.basename(path)
        if owner != "script":
            return "%s: %s" % (name, why)
        if why.endswith(OWN_BUILD):
            return "%s: written by the project's own build (%s), not by a skill generator" % (name, why)
    return None


def _ignore(folder, names):
    import fnmatch
    return [n for n in names if any(fnmatch.fnmatch(n, p) for p in SKIP_COPY)]


def copy_project(board_path, dest):
    """Copy the folder holding the board (and its sub-folders: sheets, libraries) into dest, which must
    not exist yet or be empty. Lock files, backups and autosaves are left out. When the board sits in
    the project root, the skills' own folders (design/, scripts/, datasheets/, docs/, firmware/) and
    hidden folders are left out too. Returns the copied board."""
    src = os.path.dirname(os.path.abspath(board_path))
    dest = os.path.abspath(dest)
    if dest == src or dest.startswith(src + os.sep):
        raise PcbError("the copy must go outside the project folder %s" % src)
    if os.path.isdir(dest) and os.listdir(dest):
        raise PcbError("%s is not empty; give a new or empty folder" % dest)
    if os.path.isdir(dest):
        os.rmdir(dest)
    is_root = os.path.isdir(os.path.join(src, "design"))

    def ignore(folder, names):
        out = _ignore(folder, names)
        if is_root and os.path.abspath(folder) == src:
            out += [n for n in names if (n in hwcommon.LAYOUT_FOLDERS or n.startswith("."))
                    and os.path.isdir(os.path.join(folder, n))]
        return out
    shutil.copytree(src, dest, ignore=ignore)
    return os.path.join(dest, os.path.basename(board_path))


def project_tables(board_path, design_dir=None):
    """The design/ folder of a project laid out as references/repository.md says, when it holds the
    tables project_settings.py reads; else None."""
    design = design_dir or hwcommon.design_dir_for(board_path)
    if os.path.isfile(os.path.join(design, "fab-capabilities.csv")) and \
            os.path.isfile(os.path.join(design, "constraints.csv")):
        return design
    return None


def rewrite_project(board_path, design_dir):
    """KiCad rewrites the project file when it saves a board: write it (and the rule file) again."""
    return project_settings.write_project(os.path.splitext(board_path)[0] + ".kicad_pro", design_dir)


def drc(board_path, design_dir=None, copy_dir=None, log=print):
    """DRC with re-pour: in place on a script-owned board (then the project files are written again),
    on a copy otherwise. Returns (problems, expected found, report, path checked, where)."""
    owner, why = board_owner(board_path, design_dir)
    refusal = in_place_refusal(board_path, design_dir)
    design = design_dir or hwcommon.design_dir_for(board_path)
    expected, errors = hwcommon.expected_drc_notes(design) if os.path.isdir(design) else ([], [])
    if errors:
        raise PcbError("; ".join(errors))
    if refusal is None:
        tables = project_tables(board_path, design_dir)
        if tables:
            project_settings.load_tables(tables)    # unreadable tables stop here, before anything is written
        report = run_drc(board_path, save=True)
        if tables:
            rewrite_project(board_path, tables)
        where = "in place (script-owned, writer %s); zones poured again and saved" % why
        checked = board_path
    else:
        before = hwcommon.sha256_file(board_path)
        tmp = None
        if copy_dir is None:
            tmp = tempfile.mkdtemp()
            copy_dir = os.path.join(tmp, "copy")
        try:
            checked = copy_project(board_path, copy_dir)
            report = run_drc(checked, save=True)
        finally:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
                checked = None
        if hwcommon.sha256_file(board_path) != before:
            raise PcbError("the board changed during DRC on a copy; it must not. Stop and report this.")
        where = "on a copy (%s); zones poured again in the copy%s" % (
            refusal, "" if checked is None else ", kept in " + copy_dir)
    problems, found = drc_problems(report, expected)
    log("DRC %s: %d violations, %d unconnected, %d parity items (%d expected)"
        % (where, len(report.get("violations", [])), len(report.get("unconnected_items", [])),
           len(report.get("schematic_parity", [])), len(found)))
    for v in problems:
        log("    " + describe(v))
    return problems, found, report, checked, where


# ---------------------------------------------------------------- a generated board

def patch_stackup(path, layers, finish="HAL lead-free"):
    """Write a stack-up into a saved board file. layers: [("F.Cu", thickness), ("prepreg"|"core",
    thickness, epsilon_r), ("In1.Cu", thickness), ...] from top to bottom."""
    with open(path, encoding="utf-8") as f:
        s = f.read()
    lay = ['\t\t(stackup',
           '\t\t\t(layer "F.SilkS"\n\t\t\t\t(type "Top Silk Screen")\n\t\t\t)',
           '\t\t\t(layer "F.Paste"\n\t\t\t\t(type "Top Solder Paste")\n\t\t\t)',
           '\t\t\t(layer "F.Mask"\n\t\t\t\t(type "Top Solder Mask")\n\t\t\t\t(thickness 0.01)\n\t\t\t)']
    d = 0
    for item in layers:
        if len(item) == 2:
            lay.append('\t\t\t(layer "%s"\n\t\t\t\t(type "copper")\n\t\t\t\t(thickness %s)\n\t\t\t)' % item)
        else:
            d += 1
            lay.append('\t\t\t(layer "dielectric %d"\n\t\t\t\t(type "%s")\n\t\t\t\t(thickness %s)\n'
                       '\t\t\t\t(material "FR4")\n\t\t\t\t(epsilon_r %s)\n\t\t\t\t(loss_tangent 0.02)\n\t\t\t)'
                       % (d, "core" if item[0] == "core" else "prepreg", item[1], item[2]))
    lay += ['\t\t\t(layer "B.Mask"\n\t\t\t\t(type "Bottom Solder Mask")\n\t\t\t\t(thickness 0.01)\n\t\t\t)',
            '\t\t\t(layer "B.Paste"\n\t\t\t\t(type "Bottom Solder Paste")\n\t\t\t)',
            '\t\t\t(layer "B.SilkS"\n\t\t\t\t(type "Bottom Silk Screen")\n\t\t\t)',
            '\t\t\t(copper_finish "%s")\n\t\t\t(dielectric_constraints no)\n\t\t)' % finish]
    block = "\n".join(lay) + "\n"
    if "(stackup" in s:
        a = s.index("(stackup")
        depth, i = 0, a
        while True:
            depth += s[i] == "("
            depth -= s[i] == ")"
            i += 1
            if depth == 0:
                break
        a = s.rfind("\n", 0, a) + 1
        s = s[:a] + block + s[i:].lstrip("\n")
    else:
        m = re.search(r"\n\t\(setup\n", s)
        if not m:
            raise PcbError("no (setup ...) in the board file")
        s = s[:m.end()] + block + s[m.end():]
    hwcommon.write_text(path, s)


class GenBoard:
    """A board built by a project's gen_pcb.py. Typical use:

        b = pcblib.GenBoard(sys.argv[2], sys.argv[1], seed=1)       # netlist, board
        b.outline(0, 0, 40, 30)
        b.place_table({"U1": (10, 10, 0), "C1": (14, 10, 90), ...})  # every part, by block
        b.zone("GND", "B.Cu", [(0.5, 0.5), (39.5, 0.5), (39.5, 29.5), (0.5, 29.5)])
        b.route()
        sys.exit(b.finish())        # labels, save, stack-up, DRC in place; exit code as pcblib's

    Positions are mm from the outline's top-left corner. The project and rule files come from
    design/ through project_settings.py (before placement, after saving and after DRC). Missing 3D
    models and unrouted connections are violations; --waive DC-nnn on the command line lets the
    board be written anyway, and the waiver is printed."""

    def __init__(self, board_path, netlist, design_dir=None, seed=1, copper_layers=2, origin=(100.0, 100.0),
                 title=None, revision=None, date=None, log=print):
        self.log = log
        self.path = os.path.abspath(board_path)
        self.hw = os.path.dirname(self.path)
        self.design = design_dir or hwcommon.design_dir_for(self.path)
        self.ox, self.oy = origin
        self.problems, self.notes = [], []
        self.ps = project_settings
        caps, self.netclasses, _, _ = project_settings.load_tables(self.design)
        self.caps = caps
        self.notes += rewrite_project(self.path, self.design)
        pcbnew.KIID.SeedGenerator(seed)         # same input, same UUIDs, same bytes
        if os.path.exists(self.path):
            os.remove(self.path)
        self.board = b = pcbnew.NewBoard(self.path)
        b.SetCopperLayerCount(copper_layers)
        tb = b.GetTitleBlock()
        for setter, v in ((tb.SetTitle, title), (tb.SetRevision, revision), (tb.SetDate, date)):
            if v:
                setter(v)
        self._rules()
        self.comps, self.nets, self.paths = read_netlist(netlist)
        self.netinfo = {}
        for name in sorted(self.nets):
            ni = pcbnew.NETINFO_ITEM(b, name)
            b.Add(ni)
            self.netinfo[name] = ni
        self.padnet = dict(((ref, pin), name) for name, nodes in self.nets.items() for ref, pin, _, _ in nodes)
        self.fps = {}
        self.blocks = []

    def _rules(self):
        """Board minimums and net classes in memory, the same values project_settings.py writes."""
        ds = self.board.GetDesignSettings()
        c = self.caps
        for item, attr in (("min_clearance", "m_MinClearance"), ("min_track", "m_TrackMinWidth"),
                           ("min_via_diameter", "m_ViasMinSize"), ("via_annular", "m_ViasMinAnnularWidth"),
                           ("min_via_drill", "m_MinThroughDrill"), ("min_hole_to_hole", "m_HoleToHoleMin"),
                           ("via_hole_clearance", "m_HoleClearance"), ("edge_clearance", "m_CopperEdgeClearance")):
            if item in c:
                setattr(ds, attr, MM(c[item]))
        ns = ds.m_NetSettings
        k = self.ps.KICAD_NETCLASS

        def fill(nc, values):
            v = dict(k)
            v.update(values)
            nc.SetClearance(MM(v["clearance"]))
            nc.SetTrackWidth(MM(v["track_width"]))
            nc.SetViaDiameter(MM(v["via_diameter"]))
            nc.SetViaDrill(MM(v["via_drill"]))
        fill(ns.GetDefaultNetclass(), self.netclasses.get("Default", {}).get("values", {}))
        for name in sorted(c for c in self.netclasses if c != "Default"):
            nc = pcbnew.NETCLASS(name)
            fill(nc, self.netclasses[name]["values"])
            ns.SetNetclass(name, nc)
            for p in sorted(self.netclasses[name]["patterns"]):
                ns.SetNetclassPatternAssignment(p, name)

    def pt(self, x, y):
        return pcbnew.VECTOR2I(MM(self.ox + x), MM(self.oy + y))

    def outline(self, x, y, w, h):
        s = pcbnew.PCB_SHAPE(self.board)
        s.SetShape(pcbnew.SHAPE_T_RECT)
        s.SetStart(self.pt(x, y))
        s.SetEnd(self.pt(x + w, y + h))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.1))
        self.board.Add(s)

    def place(self, ref, x, y, rot=0, back=False):
        """Place one part from the netlist, with its fields; checks its 3D model (a violation if missing)."""
        c = self.comps.get(ref)
        if c is None:
            raise PcbError("%s is not in the netlist" % ref)
        path, where = hwcommon.resolve_footprint(c["footprint"], self.hw)
        if not path:
            raise PcbError("%s: footprint %s not found (%s)" % (ref, c["footprint"], where))
        lib, name = c["footprint"].split(":", 1)
        fp = pcbnew.FootprintLoad(os.path.dirname(path), name)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        for k, v in sorted(c["fields"].items()):
            if k in ("Footprint", "Reference", "Value"):
                continue
            fp.SetField(k, v)
            fp.GetField(k).SetVisible(False)
        if c.get("datasheet"):
            fp.SetField("Datasheet", c["datasheet"])
        fp.SetPath(pcbnew.KIID_PATH(self.paths[ref]))
        self.board.Add(fp)
        fp.SetPosition(self.pt(x, y))
        fp.SetOrientationDegrees(rot)
        if back:
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        for pad in fp.Pads():
            n = self.padnet.get((ref, pad.GetNumber()))
            if n:
                pad.SetNet(self.netinfo[n])
        self.check_models(fp)
        self.fps[ref] = fp
        return fp

    def check_models(self, fp):
        ref = fp.GetReference()
        models = list(fp.Models())
        if not models:
            self.problems.append("%s: footprint has no 3D model (BD-23)" % ref)
        for m in models:
            p, ok = hwcommon.resolve_model(m.m_Filename, self.hw)
            alt = [os.path.splitext(p)[0] + e for e in (".step", ".stp", ".wrl")]
            if not ok and not any(os.path.isfile(a) for a in alt):
                self.problems.append("%s: 3D model file missing: %s (BD-23)" % (ref, m.m_Filename))

    def place_table(self, table):
        """{ref: (x, y, rotation) or (x, y, rotation, "back")}; every part in the netlist must be in it."""
        missing = sorted(set(self.comps) - set(table), key=hwcommon.ref_key)
        extra = sorted(set(table) - set(self.comps), key=hwcommon.ref_key)
        if missing or extra:
            raise PcbError("placement table: no position for %s; not in the netlist: %s"
                           % (", ".join(missing) or "none", ", ".join(extra) or "none"))
        for ref in sorted(table, key=hwcommon.ref_key):
            v = table[ref]
            self.place(ref, v[0], v[1], v[2] if len(v) > 2 else 0, len(v) > 3 and v[3] == "back")

    def zone(self, net, layer, pts, clearance=None, min_width=0.25, priority=0, name=""):
        z = pcbnew.ZONE(self.board)
        z.SetLayer(self.board.GetLayerID(layer))
        z.SetNet(self.netinfo[net])
        ol = z.Outline()
        ol.NewOutline()
        for x, y in pts:
            ol.Append(MM(self.ox + x), MM(self.oy + y))
        z.SetMinThickness(MM(min_width))
        if clearance is not None:
            z.SetLocalClearance(MM(clearance))
        z.SetAssignedPriority(priority)
        if name:
            z.SetZoneName(name)
        self.board.Add(z)
        return z

    def keepout(self, x0, y0, x1, y1, layers=("F.Cu", "B.Cu"), tracks=True, vias=True):
        z = pcbnew.ZONE(self.board)
        z.SetIsRuleArea(True)
        ls = pcbnew.LSET()
        for l in layers:
            ls.AddLayer(self.board.GetLayerID(l))
        z.SetLayerSet(ls)
        z.SetDoNotAllowTracks(tracks)
        z.SetDoNotAllowVias(vias)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.SetDoNotAllowZoneFills(True)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            ol.Append(MM(self.ox + x), MM(self.oy + y))
        self.board.Add(z)

    def route(self, router=None, budget=None, refine=True, trace=False):
        gr = load_router(router, self.hw)
        dru = os.path.splitext(self.path)[0] + ".kicad_dru"
        res = route_board(self.board, gr, dru, budget, refine, blocks=self.blocks, log=self.log, trace=trace)
        for f in res["failed"]:
            self.problems.append("not routed: %s at %s" % (f[0], f[1]))
        return res

    def labels(self):
        h = self.caps.get("silk_text_height", SILK[1])
        t = self.caps.get("silk_text_thickness", SILK[2])
        return place_labels(self.board, silk=(h * 0.875, h, t),
                            silk_clearance=self.caps.get("silk_clearance", 0.15), log=self.log)

    def save(self, stackup=None):
        pcbnew.SaveBoard(self.path, self.board)
        rewrite_project(self.path, self.design)
        if stackup:
            patch_stackup(self.path, stackup)

    def finish(self, argv=None, stackup=None, labels=True, drc_check=True):
        """Labels, save, stack-up, DRC in place. Prints the violations; returns the exit code."""
        a = argparse.ArgumentParser()
        a.add_argument("--waive", action="append", default=[])
        a.add_argument("rest", nargs="*")
        args = a.parse_args(sys.argv[1:] if argv is None else argv)
        bad = hwcommon.check_waivers(args.waive, self.design)
        if bad:
            for b in bad:
                self.log("gen_pcb: " + b)
            return 2
        if labels:
            self.labels()
        self.save(stackup)
        for n in self.notes:
            self.log("note: " + n)
        problems = list(self.problems)
        if drc_check:
            report = run_drc(self.path, save=True)
            rewrite_project(self.path, self.design)
            expected, _ = hwcommon.expected_drc_notes(self.design)
            dp, found = drc_problems(report, expected)
            self.log("DRC in place, zones poured again and saved: %d violations, %d unconnected, %d parity items "
                     "(%d expected)" % (len(report.get("violations", [])), len(report.get("unconnected_items", [])),
                                        len(report.get("schematic_parity", [])), len(found)))
            problems += ["DRC " + describe(v) for v in dp]
        self.log("wrote %s" % os.path.basename(self.path))
        if problems:
            self.log("Violation: %d problems:" % len(problems))
            for p in problems:
                self.log("    " + p)
            if not args.waive:
                return 1
            self.log("WAIVED by %s" % ", ".join(args.waive))
        return 0


# ---------------------------------------------------------------- command line

def cmd_route(a):
    src = os.path.abspath(a.board)
    if not os.path.isfile(src) or not src.endswith(".kicad_pcb"):
        print("pcblib route: %s is not a .kicad_pcb file" % a.board, file=sys.stderr)
        return 2
    before = hwcommon.sha256_file(src)
    try:
        gr = load_router(a.router, os.path.dirname(src))
        out = copy_project(src, a.out_dir)
    except PcbError as e:
        print("pcblib route: %s" % e, file=sys.stderr)
        return 2 if "copy" in str(e) or "empty" in str(e) else 3
    print("routing a copy: %s (the board given is not written)" % out)
    print("note: review the routed copy before using it")
    board = pcbnew.LoadBoard(out)
    dru = os.path.splitext(out)[0] + ".kicad_dru"
    res = route_board(board, gr, dru, a.budget, not a.no_refine, trace=a.trace)
    pcbnew.SaveBoard(out, board)
    design = a.design or hwcommon.design_dir_for(src)
    try:
        report = run_drc(out, save=True)        # the copy: poured again and saved
        expected, errors = hwcommon.expected_drc_notes(design) if os.path.isdir(design) else ([], [])
        if errors:
            raise PcbError("; ".join(errors))
        problems, found = drc_problems(report, expected)
    except PcbError as e:
        print("pcblib route: %s" % e, file=sys.stderr)
        return 3
    print("DRC on the routed copy, zones poured again and saved: %d violations, %d unconnected, %d parity items"
          % (len(report.get("violations", [])), len(report.get("unconnected_items", [])),
             len(report.get("schematic_parity", []))))
    for v in problems:
        print("    " + describe(v))
    if hwcommon.sha256_file(src) != before:
        print("pcblib route: the input board changed; it must not. Stop and report this.", file=sys.stderr)
        return 3
    print("input board unchanged (sha256 %s)" % before[:12])
    bad = bool(res["failed"] or problems)
    if bad and a.waive:
        print("WAIVED by %s" % ", ".join(a.waive))
        return 0
    return 1 if bad else 0


def cmd_drc(a):
    path = os.path.abspath(a.board)
    if not os.path.isfile(path):
        print("pcblib drc: %s does not exist" % a.board, file=sys.stderr)
        return 2
    try:
        problems, _, _, _, _ = drc(path, a.design, a.copy)
    except (hwcommon.TableError, project_settings.SettingsError) as e:     # unreadable tables: bad input
        print("pcblib drc: %s. Nothing was written." % e, file=sys.stderr)
        return 2
    except PcbError as e:
        print("pcblib drc: %s" % e, file=sys.stderr)
        return 3
    if problems:
        if a.waive:
            print("WAIVED by %s" % ", ".join(a.waive))
            return 0
        print("Violation: %d DRC problems." % len(problems))
        return 1
    print("DRC clean")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("route")
    r.add_argument("board")
    r.add_argument("out_dir")
    r.add_argument("--router")
    r.add_argument("--budget", type=float)
    r.add_argument("--no-refine", action="store_true")
    r.add_argument("--trace", action="store_true")
    r.add_argument("--design")
    r.add_argument("--waive", action="append", default=[])
    d = sub.add_parser("drc")
    d.add_argument("board")
    d.add_argument("--design")
    d.add_argument("--copy")
    d.add_argument("--waive", action="append", default=[])
    a = p.parse_args(argv)
    if a.cmd is None:
        p.print_help()
        return 2
    design = a.design or None
    if a.waive:
        bad = hwcommon.check_waivers(a.waive, design or hwcommon.design_dir_for(a.board))
        if bad:
            for b in bad:
                print("pcblib: " + b, file=sys.stderr)
            return 2
    return cmd_route(a) if a.cmd == "route" else cmd_drc(a)


if __name__ == "__main__":
    sys.exit(main())
