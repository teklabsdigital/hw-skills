# Copyright 2026 Teklabs Digital (hw-skills)
# SPDX-License-Identifier: Apache-2.0
"""Schematic checks. Python 3 standard library only; no pcbnew, no KiCad needed to run.

    python3 sch_check.py <sub-command> [--project DIR] [options]
    python3 sch_check.py all [--project DIR]          every sub-command, in the order below

Every check reads the KiCad files as they are, in hardware/ or the folder design/status.md names on
its "KiCad folder:" line: the netlist exported by `build.py netlist` (<name>.net), the .kicad_sch (library symbols: pins, hidden and power pins; fields) and
its sub-sheets, footprint pads (the .kicad_pcb when there is one, else the footprint library),
and the project tables in design/. Never a generator's internals. Nothing is written to a
design file.

Pass or fail (exit 1 on a fail):
  pins         symbol pins, footprint pads and netlist against design/pins.csv; MPN of the rows
               against the part; used function among the pin's functions; hidden and power pins
               listed, none joining a net the table does not show; parts with pins that can be wrong
               and no rows; unconfirmed rows by designator (listed, not a fail).
               --import st --data PATH --designator REF [--write]: ST's open pin data (the
               STM32_open_pin_data files, mcu/<RefName>.xml, BSD-3-Clause), compared with the rows,
               or written as new unconfirmed rows with --write. Other families: the datasheet pin
               table or a configurator export, transcribed into pins.csv and confirmed.
  alloc        one signal (peripheral instance, timer or DMA channel) on two pins; debug pins given up
               for another use. Functions blocked while a radio runs are not in any table: by hand.
  powerup      every control input (control_input yes) has a pull, tie or driver giving its
               required_in_reset state while the microcontroller is in reset; fights; the part named
               in given_by is the one found. Reliance on internal pulls and boot-time activity on a
               control net are listed for the reviewer (EL-32, EL-03). So is a pin of an IC (U or IC
               designator) not marked as a control input whose name reads as an enable, reset,
               shutdown or address pin. With no
               control input in pins.csv the check is not run, unless design/status.md has the line
               "Control inputs: none"; then it passes and says so.
  testpoints   nets named under "## Test points" in design/requirements.md (lines "- <net>: <use>",
               or names in backticks) that have no test point (TP designator or TestPoint footprint).
  rails        only a rail in design/rails.csv is drawn with a power symbol, and a rail is drawn with
               nothing else: no label, no sheet pin. A declared rail that is not drawn is named. The
               nets of design/separate-nets.csv are joined by their one link part only. What is read
               from the drawing is compared with KiCad's netlist (<name>.net when it is not older than
               the sheets, else exported by kicad-cli); with neither, the pass line says NOT PROVEN.
  modules      design/modules.csv, design/module-nets.csv and design/separate-nets.csv against the
               sheets: one sheet per module, only the module boxes on the top sheet, every designator
               in its module's block, every net between modules in the table and on its listed modules
               only. A sheet that holds text only is no module. A table net that is drawn with part
               pins on it, and is no net of its own in the netlist, fails: it is joined to another net,
               which is named. A table net on labels with no part pin yet, or on no label, is a note.
               --probe: in a copy under .hwtmp/ (removed afterwards), a test point goes on every
               hierarchical label, so the nets are followed on a skeleton with no parts; then one net
               is cut in the copy, and the check must fail on it. Needs kicad-cli.
  overlap      text over other text, over a wire or over another symbol. Text sizes are estimated.
               No netlist needed. Not part of `all`.
  chosen       every position of a kind in design/chosen-parts.csv carries the chosen MPN and supplier
               number. match is terms joined by ";": value=, role= (from parts.csv), footprint=, with
               * for any text. A position in except_refs needs a user decision that names it.
  fields       every fitted symbol in the BOM has a supplier part number and a datasheet link, both
               agree with design/parts.csv, and neither the link nor the description names another
               part. No netlist needed. Not part of `all`.
  drive        two or more transistor bases on one net with no resistor each. Gates that share a net
               are listed, not failed.
Under `all`, a check whose table is not in design/ is named as not run. Asked for by name, it exits 2.
The same holds for powerup with no control input to check.
Review lists (each item is closed with a written reason in design/net-review.csv; --record adds new
items there as open, and reopens a closed item whose text has changed since). They do not pass or
fail, but for two lines that fail until the item is closed there: an open-drain net with no pull
(opendrain) and supply pins on a net with no capacitor to ground (decouple-list).
  protect      every net that reaches a connector, button, switch, mounting hole or antenna, with the
               parts on its path (through series parts) and any protection part on it. A resistor
               from the signal to a rail or ground is listed under "pulls", not followed.
  domains      nets joining pins whose pins.csv supply differs (levels and back-feed to check).
  opendrain    open-drain and I2C nets with the pulls on each and their rails.
  unused       pins left unconnected, and rows marked unused, with the pins.csv note.
  decouple-list  capacitors on each supply net, with the supply pins on it.
Numbers (never pass or fail):
  currents     current through each pull and divider. Rail voltages come from --rail NET=VOLTS, else
               from the voltage column of supply rows in design/rails.csv (a range such as "3.0 to 4.2"
               is taken at its highest), else from net names (+3V3 is 3.3 V).
  railcap      total capacitance between each supply net and ground.
  netload      resistor load on each rail and each driven net, summed by sheet and in total, with the
               share of --budget NET=AMPS; a share above --level PERCENT (default 80) is marked.
               Supply currents of ICs and transistors are in no table and are not counted.

Exit codes: 0 pass or list printed; 1 a pass/fail check or a review-list line failed; 2 missing or
unreadable input.
"""
import argparse
import contextlib
import csv
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwcommon  # noqa: E402

PASS_FAIL = ("pins", "alloc", "powerup", "testpoints", "rails", "modules", "overlap", "chosen", "fields", "drive")
REVIEW_LISTS = ("protect", "domains", "opendrain", "unused", "decouple-list")
NUMBERS = ("currents", "railcap", "netload")
# `all` leaves out overlap and fields: they are asked for by name.
ORDER = ("rails", "modules", "pins", "alloc", "powerup", "chosen", "drive", "protect", "domains", "opendrain",
         "unused", "testpoints", "currents", "netload", "railcap", "decouple-list")
IMPORTERS = {"st": "ST open pin data (STM32_open_pin_data repository, mcu/<RefName>.xml), BSD-3-Clause"}

GROUND_RE = re.compile(r"^(?:[ADPS]?GND|GND[A-Z]|VSS|0V|EARTH|CHASSIS)\w*$", re.IGNORECASE)
RAIL_RE = re.compile(r"(?:^|[^A-Za-z0-9])\+?(\d+)V(\d*)(?:$|[^A-Za-z0-9])|^\+?(\d+(?:\.\d+)?)V$", re.IGNORECASE)
WITH_PINS_RE = re.compile(r"^(U|IC|J|P|CN|X|D|LED|Q|T|K|SW|Y|M)\d", re.IGNORECASE)
EXPOSED_RE = re.compile(r"^(J|P|CN|X|SW|S|BTN|H|MH|ANT|AE)\d", re.IGNORECASE)
SERIES_RE = re.compile(r"^(R|L|FB|F|FL)\d", re.IGNORECASE)
DEBUG_SIGNALS = ("SWDIO", "SWCLK", "SWO", "JTMS", "JTCK", "JTDI", "JTDO", "NJTRST", "TMS", "TCK", "TDI", "TDO",
                 "TRACESWO", "SWDCLK")
GENERIC_FUNCTIONS = ("", "GPIO", "GPIO_INPUT", "GPIO_OUTPUT", "GPIO_EXTI", "INPUT", "OUTPUT", "UNUSED", "NOT USED",
                     "NC", "POWER", "GROUND", "GND", "SUPPLY", "ANALOG", "CONTACT", "PASSIVE", "RESET", "ENABLE")
UNCONNECTED_WORDS = ("", "nc", "n/c", "no connect", "not connected", "unconnected", "-", "none")


class InputError(Exception):
    pass


# ---------------------------------------------------------------- reading the design

def norm_name(name):
    """Pin names compared without KiCad's overbar markup and case: ~{RST} equals RST."""
    return re.sub(r"[~{}]", "", name or "").strip().upper()


def is_ground(net):
    return bool(GROUND_RE.match(hwcommon.net_key(net).split("/")[-1]))


def parse_value(text, unit):
    """A component value in base units (ohms or farads): 10k, 4k7, 4.7u, 100nF/50V, 0R. None if unreadable."""
    t = (text or "").replace("µ", "u").replace("μ", "u").replace(" ", "")
    m = re.match(r"^(\d+(?:\.\d+)?)([pnumkKMGR]?)(\d*)", t)
    if not m:
        return None
    letter, tail = m.group(2), m.group(3)
    if tail and "." in m.group(1):
        return None                                                   # "4.7k7" is not a value
    num = float(m.group(1) + ("." + tail if tail else ""))
    if unit == "F":
        if letter == "":                                              # a bare number: only "10F" is read
            return num if t[len(m.group(0)):].upper().startswith("F") else None
        mult = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3}.get(letter)
    else:
        mult = {"": 1.0, "R": 1.0, "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}.get(letter)
    return None if mult is None else num * mult


def fmt_si(v, unit):
    for div, prefix in ((1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "u"), (1e-9, "n"), (1e-12, "p")):
        if abs(v) >= div:
            return "%.3g %s%s" % (v / div, prefix, unit)
    return "0 %s" % unit


class Design:
    """The netlist, schematic symbols, footprint pads and project tables of one project."""

    def __init__(self, paths, netlist=None, sch=None, board=None, need_netlist=True):
        self.p = paths
        net = netlist or paths["net"]
        if need_netlist and (not net or not os.path.isfile(net)):
            raise InputError("no netlist at %s; export it with `python3 hwskills/build.py netlist` (or pass --netlist)"
                             % (net or os.path.join(paths["hardware"], "<name>.net")))
        self.comps, self.nets, self.libparts = {}, {}, {}
        if net and os.path.isfile(net):
            self._read_netlist(net)
        self.pin_net = {}
        for name, nodes in self.nets.items():
            for ref, pin, func, ptype in nodes:
                self.pin_net[(ref, pin)] = name
        self.pin_type = dict(((r, p), t) for nodes in self.nets.values() for r, p, _, t in nodes)
        self.symbols = {}
        self.sch_path, self.net_path = sch or paths["sch"], net
        self.pass_note = {}                         # check name -> text added to its pass line
        self._drawing = self._kn = None             # the drawing and KiCad's netlist of it, each read once
        self._read_schematic(sch or paths["sch"])
        self.board = None
        b = board or paths["pcb"]
        if b and os.path.isfile(b):
            self.board = hwcommon.read_board(b)
        d = paths["design"]
        try:
            self.pins = hwcommon.read_table(os.path.join(d, "pins.csv"))
            self.parts_rows = hwcommon.read_table(os.path.join(d, "parts.csv"))
            self.review = hwcommon.read_table(os.path.join(d, "net-review.csv"))
        except hwcommon.TableError as e:
            raise InputError(str(e))
        self.parts = {}
        for row in self.parts_rows:
            for ref in hwcommon.split_list(row["refs"]):
                self.parts[ref] = row
        self.rows = {}
        for row in self.pins:
            self.rows.setdefault(row["designator"], {})[row["pin"]] = row
        self.rails, self.table_rails, self.rails_unread = {}, {}, []
        self._read_rails(os.path.join(d, "rails.csv"))

    def _read_rails(self, path):
        """The voltage of each supply rail of design/rails.csv: a number, or a range, taken at its highest.
        Ground rows are left to their names. A --rail option is set after this, so it wins."""
        if not os.path.isfile(path):
            return
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        number = r"(\d+(?:\.\d+)?)\s*V?"
        for row in rows:
            rail, kind, text = [(row.get(k) or "").strip() for k in ("rail", "kind", "voltage")]
            if not rail or kind.lower() != "supply":
                continue
            one = re.fullmatch(r"([+-]?)" + number, text, re.IGNORECASE)
            span = re.fullmatch(number + r"\s*(?:to|-|\.\.+)\s*" + number, text, re.IGNORECASE)
            if one:
                v, how = float(one.group(1) + one.group(2)), ""
            elif span:
                v, how = max(float(span.group(1)), float(span.group(2))), " (the highest of %s)" % text
            else:
                self.rails_unread.append((rail, text))
                continue
            self.rails[rail] = v
            self.table_rails[rail] = (v, "%s %g V%s" % (rail, v, how))

    def _read_netlist(self, path):
        root = hwcommon.read_sexpr(path)
        self.comps, self.nets = hwcommon.read_netlist(path)
        for c in hwcommon.find(hwcommon.first(root, "components", []), "comp"):
            ref = hwcommon.value(c, "ref")
            src = hwcommon.first(c, "libsource", [])
            pins = []
            for unit in hwcommon.find(hwcommon.first(c, "units", []), "unit"):
                for pin in hwcommon.find(hwcommon.first(unit, "pins", []), "pin"):
                    pins.append(hwcommon.value(pin, "num"))
            self.comps[ref]["libsource"] = (hwcommon.value(src, "lib"), hwcommon.value(src, "part"))
            self.comps[ref]["pins"] = pins
        for lp in hwcommon.find(hwcommon.first(root, "libparts", []), "libpart"):
            key = (hwcommon.value(lp, "lib"), hwcommon.value(lp, "part"))
            self.libparts[key] = dict((hwcommon.value(pin, "num"), (hwcommon.value(pin, "name"),
                                                                    hwcommon.value(pin, "type")))
                                      for pin in hwcommon.find(hwcommon.first(lp, "pins", []), "pin"))

    def _read_schematic(self, path, seen=None):
        """Placed symbols with their library symbol's pins: ref -> {lib_id, fields, pins {num: (name, type, hidden)}}."""
        seen = seen if seen is not None else set()
        if not path or not os.path.isfile(path) or path in seen:
            return
        seen.add(path)
        root = hwcommon.read_sexpr(path)
        libs = {}
        for s in hwcommon.find(hwcommon.first(root, "lib_symbols", []), "symbol"):
            libs[str(s[1])] = s
        for s in hwcommon.find(root, "symbol"):
            lib_id = hwcommon.value(s, "lib_id")
            fields = dict((str(p[1]), str(p[2])) for p in hwcommon.find(s, "property") if len(p) > 2)
            refs = [fields.get("Reference", "")]
            for inst in hwcommon.find(hwcommon.first(s, "instances", []), "project"):
                refs += [hwcommon.value(pth, "reference") for pth in hwcommon.find(inst, "path")]
            pins = self._lib_pins(libs, lib_id)
            for ref in set(r for r in refs if r and not r.startswith("#")):
                entry = self.symbols.setdefault(ref, {"lib_id": lib_id, "fields": fields, "pins": {}})
                entry["pins"].update(pins)
        for sheet in hwcommon.find(root, "sheet"):
            for p in hwcommon.find(sheet, "property"):
                if len(p) > 2 and str(p[1]) in ("Sheetfile", "Sheet file"):
                    self._read_schematic(os.path.join(os.path.dirname(path), str(p[2])), seen)

    def _lib_pins(self, libs, lib_id, depth=0):
        node = libs.get(lib_id)
        if node is None or depth > 3:
            return {}
        pins = {}
        ext = hwcommon.value(node, "extends")
        if ext:
            pins.update(self._lib_pins(libs, (lib_id.split(":")[0] + ":" + ext) if ":" in lib_id else ext, depth + 1))

        def walk(n):
            for child in n:
                if not isinstance(child, list) or not child:
                    continue
                if child[0] == "pin" and len(child) > 2 and not isinstance(child[1], list):
                    hidden = "hide" in [x for x in child if not isinstance(x, list)] or \
                        hwcommon.value(child, "hide") == "yes"
                    pins[hwcommon.value(child, "number")] = (hwcommon.value(child, "name"), str(child[1]), hidden)
                elif child[0] == "symbol":
                    walk(child)
        walk(node)
        return pins

    # --- questions the checks ask

    def mpn(self, ref):
        c = self.comps.get(ref)
        if c and c["fields"].get("MPN"):
            return c["fields"]["MPN"]
        s = self.symbols.get(ref)
        if s and s["fields"].get("MPN"):
            return s["fields"]["MPN"]
        return self.parts.get(ref, {}).get("mpn", "")

    def symbol_pins(self, ref):
        """{number: (name, type, hidden)} from the schematic library symbol, else from the netlist."""
        s = self.symbols.get(ref)
        if s and s["pins"]:
            return s["pins"]
        c = self.comps.get(ref)
        if not c:
            return {}
        lp = self.libparts.get(c.get("libsource"), {})
        return dict((n, (lp.get(n, ("", ""))[0], lp.get(n, ("", ""))[1], False)) for n in c.get("pins", []))

    def pads(self, ref):
        """Pad numbers of the part's footprint, and where they were read; (None, why) when unreadable."""
        if self.board:
            for fp in self.board["footprints"]:
                if fp["ref"] == ref:
                    return set(p["number"] for p in fp["pads"] if p["number"]), "the board file"
        c = self.comps.get(ref)
        fpid = c["footprint"] if c else ""
        if not fpid:
            return None, "no footprint assigned"
        path, why = hwcommon.resolve_footprint(fpid, self.p["hardware"])
        if not path:
            return None, "footprint %s not found (%s)" % (fpid, why)
        fp = hwcommon.read_sexpr(path)
        return set(str(p[1]) for p in hwcommon.find(fp, "pad") if len(p) > 1 and str(p[1])), "library " + fpid

    def net_of(self, ref, pin):
        n = self.pin_net.get((ref, pin), "")
        return "" if n.startswith("unconnected-") else n

    def voltage(self, net):
        if net in self.rails:
            return self.rails[net]
        if is_ground(net):
            return 0.0
        key = hwcommon.net_key(net).split("/")[-1]
        m = RAIL_RE.search(key)
        if m:
            if m.group(3):
                return float(m.group(3))
            return float(m.group(1) + ("." + m.group(2) if m.group(2) else ""))
        return None

    def is_supply(self, net):
        if not net or is_ground(net):
            return False
        if self.voltage(net) is not None:
            return True
        return any(t in ("power_in", "power_out") for _, _, _, t in self.nets.get(net, []))

    def two_pin(self, ref):
        """(net of pin 1, net of pin 2) for a two-pin part, else None."""
        c = self.comps.get(ref)
        if not c:
            return None
        pins = sorted(set(c.get("pins") or [p for (r, p) in self.pin_net if r == ref]))
        if len(pins) != 2:
            return None
        return self.net_of(ref, pins[0]), self.net_of(ref, pins[1])

    def kind(self, ref):
        role = self.parts.get(ref, {}).get("role", "")
        if role:
            return role
        m = re.match(r"^([A-Za-z]+)", ref)
        return {"R": "resistor", "C": "capacitor", "L": "inductor", "D": "diode", "TP": "test point"}.get(
            m.group(1).upper() if m else "", "")

    def is_resistor(self, ref):
        return bool(re.match(r"^R\d", ref, re.IGNORECASE)) and self.two_pin(ref) is not None

    def is_capacitor(self, ref):
        return bool(re.match(r"^C\d", ref, re.IGNORECASE)) and self.two_pin(ref) is not None

    def fitted(self, ref):
        c = self.comps.get(ref, {})
        return "dnp" not in c.get("properties", {}) and "not fitted" not in self.parts.get(ref, {}).get("variant", "")

    def review_status(self, lst, key, text=None):
        """(NR- ID or None, status): "new", "open", "closed by ...", or "changed" when the item's text is
        no longer what was closed (a closed item whose circuit changed is open again)."""
        for r in self.review:
            if r["list"] == lst and r["net_or_pin"] == key:
                if text is not None and r["item"] and r["item"] != text:
                    return r["id"], "changed"
                closed = r["reason"] and r["closed_by"]
                return r["id"], ("closed by %s: %s" % (r["closed_by"], r["reason"])) if closed else "open"
        return None, "new"


def refs_sorted(refs):
    return sorted(refs, key=hwcommon.ref_key)


# ---------------------------------------------------------------- pins

def st_refname_re(refname):
    """ST RefName to a regex: x is any character, (A-B-C) is one of the listed options."""
    out = ""
    i = 0
    while i < len(refname):
        ch = refname[i]
        if ch == "(":
            j = refname.index(")", i)
            out += "(?:" + "|".join(re.escape(o) for o in refname[i + 1:j].split("-")) + ")"
            i = j + 1
            continue
        out += "." if ch == "x" else re.escape(ch)
        i += 1
    return re.compile(out, re.IGNORECASE)


def st_read(path):
    """(RefName, DBVersion, {position: (name, type, [signals])}) from one ST open pin data MCU file."""
    root = ET.parse(path).getroot()
    tag = lambda e: e.tag.split("}")[-1]                                           # noqa: E731
    if tag(root) != "Mcu":
        raise InputError("%s is not an ST MCU file (root element %s)" % (path, tag(root)))
    pins = {}
    for e in root:
        if tag(e) == "Pin":
            sig = [s.get("Name", "") for s in e if tag(s) == "Signal"]
            pins[e.get("Position", "")] = (e.get("Name", ""), e.get("Type", ""), sig)
    return root.get("RefName", ""), root.get("DBVersion", ""), pins


def st_find(data, mpn):
    if os.path.isfile(data):
        return data
    cands = []
    for folder in (data, os.path.join(data, "mcu")):
        if os.path.isdir(folder):
            cands += [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith(".xml")]
    for path in cands:
        ref = os.path.splitext(os.path.basename(path))[0]
        if st_refname_re(ref).match(mpn or ""):
            return path
    raise InputError("no ST MCU file in %s matches MPN %r (file names are ST RefNames such as STM32F030F4Px)"
                     % (data, mpn))


def st_name_ok(table_name, st_name):
    a, b = norm_name(table_name), norm_name(st_name)
    return a == b or a == re.split(r"[-( ]", b)[0]


def st_function_ok(used, signals, ptype):
    u = norm_name(used)
    sigs = [norm_name(s) for s in signals]
    if u in sigs or not u or u in ("UNUSED", "NOT USED", "NC"):
        return True
    if u.startswith("GPIO") and "GPIO" in sigs:
        return True
    return u in ("POWER", "GROUND", "SUPPLY", "RESET", "BOOT") and ptype in ("Power", "Reset", "Boot")


def import_st(d, a, out):
    """Compare a designator's rows with ST's open pin data, or write new unconfirmed rows."""
    fails = []
    ref = a.designator
    if not ref:
        raise InputError("--import st needs --designator REF")
    mpn = a.mpn or d.mpn(ref)
    path = st_find(a.data, mpn)
    refname, db, vendor = st_read(path)
    source = "vendor data ST open pin data %s, DBVersion %s" % (os.path.basename(path), db or "?")
    out("vendor data: %s (RefName %s) for %s, MPN %s" % (os.path.basename(path), refname, ref, mpn or "unknown"))
    have = d.rows.get(ref, {})
    for pos, (name, ptype, sig) in sorted(vendor.items(), key=lambda kv: hwcommon.ref_key(kv[0])):
        row = have.get(pos)
        if row is None:
            if have:
                fails.append("%s pin %s (%s): in the vendor data, not in pins.csv" % (ref, pos, name))
            continue
        if not st_name_ok(row["name"], name):
            fails.append("%s pin %s: pins.csv name %r, vendor data %r" % (ref, pos, row["name"], name))
        if not st_function_ok(row["used_function"], sig, ptype):
            fails.append("%s pin %s (%s): used function %r is not among the vendor's signals (%s)"
                         % (ref, pos, name, row["used_function"], ", ".join(sig) or ptype))
    for pos in sorted(set(have) - set(vendor), key=hwcommon.ref_key):
        fails.append("%s pin %s: in pins.csv, not in the vendor data" % (ref, pos))
    if not have:
        new = [{"designator": ref, "mpn": mpn, "pin": pos, "name": name, "functions": ";".join(sig) or ptype,
                "source": source, "confirmed": ""}
               for pos, (name, ptype, sig) in sorted(vendor.items(), key=lambda kv: hwcommon.ref_key(kv[0]))]
        out("%d rows for %s from the vendor data (unconfirmed; used_function, net and power-up columns to fill)"
            % (len(new), ref))
        if a.write:
            rows = [dict((k, v) for k, v in r.items() if k != "_line") for r in d.pins] + new
            hwcommon.write_table(os.path.join(d.p["design"], "pins.csv"), "pins.csv", rows)
            out("wrote %d rows to design/pins.csv" % len(new))
        else:
            for r in new[:8]:
                out("  %s,%s,%s,%s" % (r["designator"], r["pin"], r["name"], r["functions"]))
            if len(new) > 8:
                out("  ... %d more; pass --write to add them" % (len(new) - 8))
    return fails


def cmd_pins(d, a, out):
    if a.import_vendor:
        if a.import_vendor not in IMPORTERS:
            raise InputError("no importer for %r; this version reads: %s" % (
                a.import_vendor, "; ".join("%s = %s" % kv for kv in sorted(IMPORTERS.items()))))
        if not a.data:
            raise InputError("--import %s needs --data PATH (the local copy of the vendor's files)" % a.import_vendor)
        return import_st(d, a, out)
    fails = []
    for ref in refs_sorted(d.rows):
        rows = d.rows[ref]
        if ref not in d.comps:
            fails.append("%s: pins.csv has %d rows for it, but it is not in the netlist" % (ref, len(rows)))
            continue
        part_mpn = d.mpn(ref)
        for m in sorted(set(r["mpn"] for r in rows.values())):
            if m and part_mpn and m != part_mpn:
                fails.append("%s: pins.csv rows are for MPN %s, the part fitted is %s (table_check.py stale)"
                             % (ref, m, part_mpn))
        sym = d.symbol_pins(ref)
        for num in sorted(set(sym) - set(rows), key=hwcommon.ref_key):
            fails.append("%s pin %s (%s): on the symbol, not in pins.csv" % (ref, num, sym[num][0]))
        for num in sorted(set(rows) - set(sym), key=hwcommon.ref_key):
            fails.append("%s pin %s (%s): in pins.csv, not on the symbol" % (ref, num, rows[num]["name"]))
        for num in sorted(set(rows) & set(sym), key=hwcommon.ref_key):
            sname, row = sym[num][0], rows[num]
            if sname and sname != "~" and norm_name(sname) != norm_name(row["name"]):
                fails.append("%s pin %s: symbol name %r, pins.csv name %r" % (ref, num, sname, row["name"]))
        pads, where = d.pads(ref)
        if pads is None:
            out("  %s: footprint pads not checked (%s)" % (ref, where))
        else:
            for num in sorted(set(sym) - pads, key=hwcommon.ref_key):
                fails.append("%s pin %s: no pad %s on the footprint (%s)" % (ref, num, num, where))
            for num in sorted(pads - set(sym), key=hwcommon.ref_key):
                fails.append("%s: footprint pad %s has no symbol pin (%s)" % (ref, num, where))
        for num in sorted(rows, key=hwcommon.ref_key):
            row = rows[num]
            actual = d.net_of(ref, num)
            want = row["net"]
            if want.lower() in UNCONNECTED_WORDS:
                if actual:
                    fails.append("%s pin %s (%s): connected to %s, pins.csv says no net" % (ref, num, row["name"], actual))
            elif hwcommon.net_key(want) != hwcommon.net_key(actual):
                fails.append("%s pin %s (%s): on net %s, pins.csv says %s" % (ref, num, row["name"],
                                                                             actual or "nothing", want))
            funcs = [norm_name(f) for f in hwcommon.split_list(row["functions"])]
            used = norm_name(row["used_function"])
            if used and funcs and used not in funcs and used not in ("UNUSED", "NOT USED", "NC"):
                fails.append("%s pin %s (%s): used function %r is not among its functions (%s)"
                             % (ref, num, row["name"], row["used_function"], row["functions"]))
    # parts with pins that can be wrong and no rows
    for ref in refs_sorted(d.comps):
        if ref not in d.rows and WITH_PINS_RE.match(ref) and d.fitted(ref):
            sym = d.symbol_pins(ref)                # no pin table: the symbol and the footprint are still compared
            pads, where = d.pads(ref)
            if pads is None:
                out("  %s: no pin table, and footprint pads not checked (%s)" % (ref, where))
            else:
                out("  %s: checked without a pin table: %d symbol pins, %d footprint pads (%s)"
                    % (ref, len(sym), len(pads), where))
                for num in sorted(set(sym) - pads, key=hwcommon.ref_key):
                    fails.append("%s pin %s: no pad %s on the footprint (%s)" % (ref, num, num, where))
                for num in sorted(pads - set(sym), key=hwcommon.ref_key):
                    fails.append("%s: footprint pad %s has no symbol pin (%s)" % (ref, num, where))
            fails.append("%s (%s): no rows in pins.csv; every part with pins that can be wrong needs a pin table"
                         % (ref, d.mpn(ref) or d.comps[ref]["value"]))
    # hidden and power pins
    listed = 0
    for ref in refs_sorted(d.symbols):
        for num, (name, ptype, hidden) in sorted(d.symbols[ref]["pins"].items(), key=lambda kv: hwcommon.ref_key(kv[0])):
            if not hidden and ptype not in ("power_in", "power_out"):
                continue
            listed += 1
            net = d.net_of(ref, num)
            row = d.rows.get(ref, {}).get(num)
            out("  %s pin %s %s: %s%s, net %s" % (ref, num, name, ptype, " hidden" if hidden else "", net or "none"))
            if hidden and net and (row is None or hwcommon.net_key(row["net"]) != hwcommon.net_key(net)):
                fails.append("%s pin %s (%s): hidden pin joins net %s, which pins.csv does not show for it"
                             % (ref, num, name, net))
    out("hidden and power pins listed: %d" % listed)
    # unconfirmed rows and missing limits: reported, not a fail
    unconf = {}
    for row in d.pins:
        if row["confirmed"].lower() != "yes":
            unconf[row["designator"]] = unconf.get(row["designator"], 0) + 1
    if unconf:
        out("unconfirmed rows: " + ", ".join("%s %d of %d" % (r, unconf[r], len(d.rows.get(r, {})))
                                             for r in refs_sorted(unconf)))
    else:
        out("unconfirmed rows: none")
    nolimit = [r for r in d.pins if r["used_function"] and not r["abs_max"] and WITH_PINS_RE.match(r["designator"])
               and r["designator"][0].upper() == "U"]
    if nolimit:
        out("rows of ICs with no abs_max recorded: %d (limits are compared by hand with the currents)" % len(nolimit))
    sources = {}
    for row in d.pins:
        sources.setdefault(row["designator"], set()).add(row["source"].split(" ")[0] if row["source"] else "none")
    out("source of the rows: " + ", ".join("%s %s" % (r, "/".join(sorted(s))) for r, s in
                                           sorted(sources.items(), key=lambda kv: hwcommon.ref_key(kv[0]))))
    return fails


# ---------------------------------------------------------------- alloc

def cmd_alloc(d, a, out):
    fails = []
    for ref in refs_sorted(d.rows):
        uses = {}
        for num, row in d.rows[ref].items():
            u = norm_name(row["used_function"])
            if u in GENERIC_FUNCTIONS or u.startswith("GPIO"):
                pass
            else:
                uses.setdefault(u, []).append(num)
            funcs = [norm_name(f) for f in hwcommon.split_list(row["functions"])]
            debug = [f for f in funcs if any(f == s or f.endswith("-" + s) or f.endswith("_" + s) for s in DEBUG_SIGNALS)]
            if debug and u and u not in ("UNUSED", "NOT USED", "NC") and not any(s in u for s in DEBUG_SIGNALS):
                fails.append("%s pin %s (%s): debug function %s given up for %s" % (ref, num, row["name"], debug[0],
                                                                                   row["used_function"]))
        for u, nums in sorted(uses.items()):
            if len(nums) > 1:
                fails.append("%s: %s used on %d pins (%s)" % (ref, u, len(nums), ", ".join(sorted(nums, key=hwcommon.ref_key))))
    out("functions blocked while a radio runs: no table column holds them; check the reference manual by hand")
    return fails


# ---------------------------------------------------------------- powerup

def active_low(name):
    n = name or ""
    return bool(re.match(r"^(~\{|/|!|n[A-Z])", n) or re.search(r"(_N|_B|_L|#)$", n.upper()))


def wanted_level(row):
    """'low', 'high', 'defined', or None (unreadable), and how it was read."""
    w = row["required_in_reset"].strip().lower()
    if w in ("low", "0", "l"):
        return "low", ""
    if w in ("high", "1", "h"):
        return "high", ""
    if w in ("defined", "any", "any defined", "either"):
        return "defined", ""
    off = w in ("off", "disabled", "inactive", "deasserted", "not asserted", "released")
    on = w in ("on", "enabled", "active", "asserted", "held in reset", "held")
    if off or on:
        low = active_low(row["name"])
        level = ("high" if low else "low") if off else ("low" if low else "high")
        return level, " (%s read as %s: pin %s taken as active %s)" % (w, level, row["name"], "low" if low else "high")
    return None, ""


def givers(d, net, skip):
    """[(class, level, text, ref)]: what sets this net's level while the microcontroller is in reset."""
    out = []
    v = d.voltage(net)
    if is_ground(net):
        out.append((3, "low", "tied to %s" % net, ""))
    elif v is not None or d.is_supply(net):
        out.append((3, "high", "tied to %s" % net, ""))
    for ref, pin, _, _ in d.nets.get(net, []):
        if (ref, pin) == skip or not d.fitted(ref):
            continue
        if d.is_resistor(ref):
            a, b = d.two_pin(ref)
            other = b if a == net else a
            if is_ground(other):
                out.append((1, "low", "%s pull-down to %s" % (ref, other), ref))
            elif d.voltage(other) is not None or d.is_supply(other):
                out.append((1, "high", "%s pull-up to %s" % (ref, other), ref))
            continue
        row = d.rows.get(ref, {}).get(pin)
        rs = (row["reset_state"] if row else "").lower()
        if not rs:
            continue
        internal = "internal" in rs or "weak" in rs
        if "pull-up" in rs or "pullup" in rs or "pull up" in rs:
            out.append((0 if internal else 1, "high", "%s.%s %s" % (ref, pin, row["reset_state"]), ref))
        elif "pull-down" in rs or "pulldown" in rs or "pull down" in rs:
            out.append((0 if internal else 1, "low", "%s.%s %s" % (ref, pin, row["reset_state"]), ref))
        elif re.search(r"\b(high|low)\b", rs) and not re.search(r"hi-?z|high[- ]impedance|float|input", rs):
            out.append((2, "high" if re.search(r"\bhigh\b", rs) else "low", "%s.%s %s in reset" % (ref, pin, row["reset_state"]), ref))
    return out


CONTROL_NAME_RE = re.compile(r"^N?(EN|ENA|ENABLE|CE|RST|RESET|SHDN|SHUTDOWN|STBY|STANDBY)[NB]?\d*$"
                             r"|^(ADDR|ADR|ADD|AD|A|SA)\d$|^ADDR$")
NO_CONTROL_RE = re.compile(r"^\s*Control inputs:\s*none\b", re.IGNORECASE)


def cmd_powerup(d, a, out):
    fails = []
    rows = [r for r in d.pins if r["control_input"].lower() == "yes"]
    for row in sorted(d.pins, key=lambda r: (hwcommon.ref_key(r["designator"]), hwcommon.ref_key(r["pin"]))):
        if row in rows or not re.match(r"^(U|IC)\d", row["designator"], re.IGNORECASE):
            continue                                # the name is read only on an IC: a diode's A1 is no address pin
        if any(CONTROL_NAME_RE.match(t) for t in re.split(r"[^A-Z0-9]+", norm_name(row["name"]))):
            out("  review: %s pin %s (%s): control_input is %s, and the name reads as an enable, reset, shutdown "
                "or address pin; check it against the datasheet"
                % (row["designator"], row["pin"], row["name"], row["control_input"] or "empty"))
    if not rows:
        if any(NO_CONTROL_RE.match(line) for line in hwcommon.status_lines(d.p["design"])):
            out("control inputs checked: 0 (design/status.md says the board has none)")
            return []
        raise NotRun("no row of design/pins.csv has control_input yes, so nothing was checked; mark each control "
                     "input, or write the line \"Control inputs: none\" in design/status.md")
    for row in sorted(rows, key=lambda r: (hwcommon.ref_key(r["designator"]), hwcommon.ref_key(r["pin"]))):
        ref, pin = row["designator"], row["pin"]
        where = "%s pin %s (%s)" % (ref, pin, row["name"])
        if not d.fitted(ref):
            continue
        want, note = wanted_level(row)
        if want is None:
            fails.append("%s: cannot read required_in_reset %r; write low, high, off, on or defined"
                         % (where, row["required_in_reset"]))
            continue
        net = d.net_of(ref, pin)
        if not net:
            fails.append("%s: not connected, so nothing gives it a state in reset (wanted %s)" % (where, want))
            continue
        g = givers(d, net, (ref, pin))
        if not g:
            fails.append("%s, net %s: must be %s in reset; nothing gives it (no pull, tie or driver)%s"
                         % (where, net, want, note))
            continue
        top = max(x[0] for x in g)
        strongest = [x for x in g if x[0] == top]
        levels = set(x[1] for x in strongest)
        if len(levels) > 1:
            fails.append("%s, net %s: fight in reset: %s" % (where, net, "; ".join(x[2] for x in strongest)))
            continue
        level = levels.pop()
        found = "; ".join(x[2] for x in strongest)
        if want != "defined" and level != want:
            fails.append("%s, net %s: must be %s in reset, but %s gives %s%s" % (where, net, want, found, level, note))
            continue
        refs = [x[3] for x in strongest if x[3]]
        if row["given_by"] and refs and not any(re.search(r"\b%s\b" % re.escape(r), row["given_by"]) for r in refs):
            fails.append("%s: given_by says %r, but the state comes from %s" % (where, row["given_by"], found))
            continue
        out("  %s, net %s: %s in reset, given by %s%s" % (where, net, level, found, note))
        if top == 0:
            out("    review: relies on an internal pull (EL-32): check the datasheet allows it")
        for r2, p2, _, _ in d.nets.get(net, []):
            other = d.rows.get(r2, {}).get(p2)
            if other and other["boot_activity"] and other["boot_activity"].lower() not in ("none", "no", "-"):
                out("    review: %s.%s %s during boot (%s)" % (r2, p2, other["boot_activity"], other["name"]))
        if not row["fault_state"] or not row["sleep_state"]:
            out("    review: sleep_state or fault_state not recorded (LG-11)")
    out("control inputs checked: %d" % len(rows))
    return fails


# ---------------------------------------------------------------- review lists

def path_from(d, net, start_ref, depth=3):
    """Parts reached from a net through two-pin series parts: (series parts, pulls, protection parts,
    end pins).

    From a signal net the walk goes through resistors, inductors, ferrites and fuses; from a supply net
    only through fuses, ferrites and filters. A resistor from a signal net to a supply or to ground is a
    pull, listed as such: it is not in the connector's path, and the walk does not follow it onto the rail."""
    series, pulls_, protection, ends = [], [], [], []
    seen_nets, frontier, seen = {net}, [net], {start_ref}
    for _ in range(depth):
        nxt = []
        for n in frontier:
            supply = d.is_supply(n)
            through = re.compile(r"^(F|FB|FL)\d", re.IGNORECASE) if supply else SERIES_RE
            for ref, pin, _, _ in d.nets.get(n, []):
                if ref in seen or not d.fitted(ref):
                    continue
                seen.add(ref)
                role = d.parts.get(ref, {}).get("role", "")
                tp = d.two_pin(ref)
                other = (tp[1] if tp[0] == n else tp[0]) if tp else ""
                if role == "protection" or (re.match(r"^D\d", ref) and tp and any(is_ground(x) for x in tp)):
                    protection.append("%s on %s" % (ref, n))
                elif d.is_resistor(ref) and not supply and other and (is_ground(other) or d.is_supply(other)):
                    pulls_.append("%s to %s" % (ref, other))
                elif through.match(ref) and tp and not any(is_ground(x) for x in tp):
                    series.append("%s to %s" % (ref, other or "nothing"))
                    if other and other not in seen_nets:
                        seen_nets.add(other)
                        nxt.append(other)
                elif not d.is_capacitor(ref) and not (d.is_resistor(ref) and supply):
                    ends.append("%s.%s" % (ref, pin))
        frontier = nxt
    if len(ends) > 8:
        ends = ends[:8] + ["and %d more" % (len(ends) - 8)]
    return series, pulls_, protection, ends


def emit(d, a, out, lst, items, must=None):
    """Print a review list and, with --record, add new items to design/net-review.csv. must is
    {key: fail text} for the items that fail until they are closed with a reason there."""
    new, changed = [], {}
    for key, text in items:
        nid, status = d.review_status(lst, key, text)
        if status == "changed":
            old = next(r["item"] for r in d.review if r["id"] == nid)
            status = "CHANGED since it was closed; was: %s" % old
            changed[nid] = text
        out("  %s %s: %s [%s]" % (nid or "--", key, text, status))
        if nid is None:
            new.append((key, text))
    still_open = sum(1 for key, text in items if d.review_status(lst, key, text)[1] in ("open", "new", "changed"))
    out("review list %s: %d items, %d not closed with a reason" % (lst, len(items), still_open))
    if a.record and (new or changed):
        ids = [int(r["id"][3:]) for r in d.review if re.match(r"^NR-\d+$", r["id"])]
        n = max(ids) if ids else 0
        rows = [dict((k, v) for k, v in r.items() if k != "_line") for r in d.review]
        for r in rows:
            if r["id"] in changed:                       # reopened: the closing reason no longer applies
                r.update({"item": changed[r["id"]], "reason": "", "closed_by": "", "date": ""})
        for key, text in new:
            n += 1
            rows.append({"id": "NR-%03d" % n, "list": lst, "net_or_pin": key, "item": text})
        hwcommon.write_table(os.path.join(d.p["design"], "net-review.csv"), "net-review.csv", rows)
        d.review = hwcommon.read_table(os.path.join(d.p["design"], "net-review.csv"))
        out("recorded %d new and %d reopened items in design/net-review.csv (open until closed with a reason)"
            % (len(new), len(changed)))
    return [(must or {})[key] for key, text in items
            if key in (must or {}) and not d.review_status(lst, key, text)[1].startswith("closed by")]


CLOSE_IT = "or close the item with a reason in design/net-review.csv"


def cmd_protect(d, a, out):
    items = []
    for ref in refs_sorted(d.comps):
        role = d.parts.get(ref, {}).get("role", "")
        if not (role in ("connector", "button", "switch") or EXPOSED_RE.match(ref)) or not d.fitted(ref):
            continue
        pins = sorted(set(d.comps[ref].get("pins") or []) | set(p for (r, p) in d.pin_net if r == ref),
                      key=hwcommon.ref_key)
        for pin in pins:
            net = d.net_of(ref, pin)
            if not net or is_ground(net):
                continue
            series, pulled, prot, ends = path_from(d, net, ref)
            items.append(("%s.%s" % (ref, pin), "net %s; series: %s; %sprotection: %s; reaches: %s" % (
                net, ", ".join(series) or "none", "pulls: %s; " % ", ".join(pulled) if pulled else "",
                ", ".join(prot) or "NONE", ", ".join(ends) or "nothing")))
    return emit(d, a, out, "protect", items)


def cmd_domains(d, a, out):
    items = []
    for net in sorted(d.nets):
        if is_ground(net) or d.is_supply(net) or net.startswith("unconnected-"):
            continue
        sup = []
        for ref, pin, _, _ in d.nets[net]:
            row = d.rows.get(ref, {}).get(pin)
            if row and row["supply"]:
                sup.append((row["supply"], "%s.%s" % (ref, pin)))
        if len(set(s for s, _ in sup)) > 1:
            items.append((net, "pins on different supplies: %s; check levels in every power state and back-feed"
                          % ", ".join("%s (%s)" % (p, s) for s, p in sorted(sup))))
    return emit(d, a, out, "domains", items)


def is_open_drain(d, net):
    for ref, pin, func, ptype in d.nets.get(net, []):
        row = d.rows.get(ref, {}).get(pin)
        text = " ".join([func or "", row["levels"] if row else "", row["used_function"] if row else "",
                         row["name"] if row else ""]).upper()
        if ptype == "open_collector" or re.search(r"OPEN[- ]?DRAIN|OPEN[- ]?COLLECTOR|\bOD\b|\bSDA|\bSCL|I2C|SMB", text):
            return True
    return False


def pulls(d, net):
    out = []
    for ref, pin, _, _ in d.nets.get(net, []):
        if d.is_resistor(ref) and d.fitted(ref):
            a_, b_ = d.two_pin(ref)
            other = b_ if a_ == net else a_
            if d.is_supply(other):
                out.append((ref, d.comps[ref]["value"], other))
    return out


def cmd_opendrain(d, a, out):
    items, must = [], {}
    for net in sorted(d.nets):
        if is_ground(net) or d.is_supply(net) or not is_open_drain(d, net):
            continue
        p = pulls(d, net)
        items.append((net, "%d pull%s: %s" % (len(p), "" if len(p) == 1 else "s",
                                               ", ".join("%s %s to %s" % x for x in p) or "NONE")))
        if not p and not net.startswith("unconnected-"):        # a pin left open is in the unused list
            must[net] = "open-drain net %s has no pull; fit one, %s" % (net, CLOSE_IT)
    return emit(d, a, out, "opendrain", items, must)


def cmd_unused(d, a, out):
    items = []
    for ref in refs_sorted(d.comps):
        pins = set(d.comps[ref].get("pins") or []) | set(d.rows.get(ref, {}))
        for pin in sorted(pins, key=hwcommon.ref_key):
            row = d.rows.get(ref, {}).get(pin)
            unused_row = row and norm_name(row["used_function"]) in ("UNUSED", "NOT USED", "NC")
            if d.net_of(ref, pin) and not unused_row:
                continue
            note = ("pins.csv: %s; functions %s" % (row["used_function"] or "no use given", row["functions"] or "?")) \
                if row else "no pins.csv row"
            items.append(("%s.%s" % (ref, pin), "%s, %s; %s" % (
                row["name"] if row else d.symbol_pins(ref).get(pin, ("",))[0] or "pin",
                "connected to " + d.net_of(ref, pin) if d.net_of(ref, pin) else "unconnected", note)))
    return emit(d, a, out, "unused", items)


def cmd_decouple(d, a, out):
    items, must = [], {}
    for net in sorted(d.nets):
        if not d.is_supply(net):
            continue
        sup = ["%s.%s" % (r, p) for r, p, _, t in d.nets[net] if t == "power_in"]
        caps = []
        for ref, pin, _, _ in d.nets[net]:
            if d.is_capacitor(ref) and d.fitted(ref):
                tp = d.two_pin(ref)
                if any(is_ground(x) for x in tp):
                    caps.append("%s %s" % (ref, d.comps[ref]["value"]))
        items.append((net, "supply pins: %s; capacitors to ground: %s" % (", ".join(sup) or "none",
                                                                        ", ".join(caps) or "NONE")))
        if sup and not caps:
            must[net] = "supply net %s has supply pins (%s) and no capacitor to ground; fit one, %s" % (
                net, ", ".join(sup), CLOSE_IT)
    return emit(d, a, out, "decouple-list", items, must)


# ---------------------------------------------------------------- testpoints

def requested_testpoints(path):
    if not os.path.isfile(path):
        return None
    names, inside = [], False
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("## "):
                inside = line[3:].strip().lower().startswith("test points")
                continue
            if not inside:
                continue
            names += re.findall(r"`([^`]+)`", line)
            m = re.match(r"^\s*[-*]\s+([^\s:,;`]+)", line)
            if m and m.group(1) not in names:
                names.append(m.group(1))
    return names


def cmd_testpoints(d, a, out):
    req = requested_testpoints(os.path.join(d.p["design"], "requirements.md"))
    if req is None:
        raise InputError("no design/requirements.md, so no test points are requested")
    fails = []
    by_key = dict((hwcommon.net_key(n), n) for n in d.nets)
    for name in req:
        net = by_key.get(hwcommon.net_key(name))
        if net is None:
            fails.append("test point requested on %r, which is not a net in the netlist" % name)
            continue
        tps = [r for r, _, _, _ in d.nets[net] if re.match(r"^TP\d", r, re.IGNORECASE)
               or "testpoint" in d.comps.get(r, {}).get("footprint", "").lower()]
        if tps:
            out("  %s: %s" % (net, ", ".join(refs_sorted(set(tps)))))
        else:
            fails.append("net %s has no test point (requested in requirements.md)" % net)
    out("test points requested: %d" % len(req))
    return fails


# ---------------------------------------------------------------- numbers

def node_voltage(d, net):
    v = d.voltage(net)
    if v is not None:
        return v
    known = []
    for ref, pin, _, _ in d.nets.get(net, []):
        if d.is_resistor(ref) and d.fitted(ref):
            a_, b_ = d.two_pin(ref)
            other = b_ if a_ == net else a_
            r = parse_value(d.comps[ref]["value"], "ohm")
            vo = d.voltage(other)
            if vo is None or not r:
                return None
            known.append((vo, r))
        elif not d.is_capacitor(ref):
            continue                                        # IC pins taken as high impedance
    if len(known) < 2:
        return None
    return sum(v / r for v, r in known) / sum(1 / r for _, r in known)


def cmd_currents(d, a, out):
    total = {}
    used = [text for rail, (v, text) in sorted(d.table_rails.items()) if d.rails.get(rail) == v]
    if used:
        out("rail voltages from design/rails.csv: %s" % ", ".join(used))
    for rail, text in d.rails_unread:
        if rail not in d.rails:
            out("  %s: voltage %r not read from design/rails.csv; write one number, or pass --rail %s=VOLTS"
                % (rail, text, rail))
    for ref in refs_sorted(d.comps):
        if not d.is_resistor(ref) or not d.fitted(ref):
            continue
        r = parse_value(d.comps[ref]["value"], "ohm")
        n1, n2 = d.two_pin(ref)
        if not r:
            out("  %s %s: value not read" % (ref, d.comps[ref]["value"]))
            continue
        v1, v2 = node_voltage(d, n1), node_voltage(d, n2)
        if v1 is not None and v2 is not None:
            i = abs(v1 - v2) / r
            out("  %s %s between %s (%.3g V) and %s (%.3g V): %s, %s" % (ref, d.comps[ref]["value"], n1, v1, n2, v2,
                                                                       fmt_si(i, "A"), fmt_si(i * i * r, "W")))
            rail = n1 if d.voltage(n1) and d.voltage(n1) >= (d.voltage(n2) or 0) else n2
            if d.voltage(rail):
                total[rail] = total.get(rail, 0) + i
        elif v1 is not None or v2 is not None:
            v = v1 if v1 is not None else v2
            rail, sig = (n1, n2) if v1 is not None else (n2, n1)
            if v:
                out("  %s %s pull-up to %s: up to %s when %s is held low" % (ref, d.comps[ref]["value"], rail,
                                                                           fmt_si(abs(v) / r, "A"), sig))
            else:
                out("  %s %s pull-down to %s: current set by the level driven on %s (pass --rail %s=VOLTS)"
                    % (ref, d.comps[ref]["value"], rail, sig, sig))
        else:
            out("  %s %s: neither end at a known voltage (pass --rail NET=VOLTS)" % (ref, d.comps[ref]["value"]))
    for rail, i in sorted(total.items()):
        out("always-on current through resistors from %s: %s" % (rail, fmt_si(i, "A")))
    return []


def cmd_railcap(d, a, out):
    for net in sorted(d.nets):
        if not d.is_supply(net):
            continue
        tot, parts = 0.0, []
        for ref, pin, _, _ in d.nets[net]:
            if d.is_capacitor(ref) and d.fitted(ref) and any(is_ground(x) for x in d.two_pin(ref)):
                c = parse_value(d.comps[ref]["value"], "F")
                if c is None:
                    parts.append("%s %s (value not read)" % (ref, d.comps[ref]["value"]))
                    continue
                tot += c
                rating = d.parts.get(ref, {}).get("voltage_rating", "")
                parts.append("%s %s%s" % (ref, d.comps[ref]["value"], " (%s)" % rating if rating else ""))
        out("  %s: %s nominal, from %s" % (net, fmt_si(tot, "F"), ", ".join(parts) or "no capacitors"))
    out("nominal values: derate class 2 ceramics for DC bias from their graph rows (EL-11)")
    return []


# ---------------------------------------------------------------- the drawing (sheet files)
#
# The checks below read the sheet files themselves, because the netlist does not say how a net was
# drawn: with a power symbol or a label, on which sheet, with what text where. Shared helpers of this
# file: own_table, read_drawing, connect, drawing, pin_groups, scratch, find_cli, export_netlist,
# kicad_netlist.

NEW_TABLES = {
    "rails.csv": ("rail", "kind", "voltage", "source", "note"),
    "modules.csv": ("module", "sheet", "ref_block", "purpose"),
    "module-nets.csv": ("net", "modules", "note"),
    "separate-nets.csv": ("net_a", "net_b", "link_part", "reason"),
    "chosen-parts.csv": ("kind", "match", "mpn", "supplier_pn", "decision", "except_refs"),
}
NO_NETLIST = ("rails", "modules", "overlap", "chosen", "fields")       # these read the drawing, or find the netlist themselves
JOINER_RE = re.compile(r"^(R|L|FB|F|FL|NT|JP|SB)\d", re.IGNORECASE)     # two-pin parts that join their two nets
PROBE_REF = "TPP"
PROBE_LIB = '''    (symbol "hwprobe:TP" (pin_numbers (hide yes)) (pin_names (hide yes)) (exclude_from_sim no) (in_bom yes) (on_board yes)
      (property "Reference" "TPP" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Value" "probe" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "TP_0_1" (circle (center 0 1.27) (radius 0.635) (stroke (width 0) (type default)) (fill (type none))))
      (symbol "TP_1_1" (pin passive line (at 0 0 90) (length 0.635) (name "1" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27))))))
      (embedded_fonts no))
'''
PROBE_PLACED = '''  (symbol (lib_id "hwprobe:TP") (at %(x)s %(y)s 0) (unit 1) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (uuid "%(uuid)s")
    (property "Reference" "%(ref)s" (at %(x)s %(y)s 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Value" "probe" (at %(x)s %(y)s 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (pin "1" (uuid "%(pin)s"))
    (instances (project %(project)s (path "%(path)s" (reference "%(ref)s") (unit 1)))))
'''


class NotRun(InputError):
    """The table a check reads is not in the project."""


def own_table(d, name, needed=True):
    """Rows of one of the tables in NEW_TABLES, each with its line number as _line. The header must be
    exact. A missing file raises NotRun, or returns None when the check can go on without it."""
    path = os.path.join(d.p["design"], name)
    if not os.path.isfile(path):
        if needed:
            raise NotRun("no design/%s" % name)
        return None
    want = list(hwcommon.TABLES.get(name) or NEW_TABLES[name])
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None or [h.strip() for h in header] != want:
            raise InputError("design/%s: the header row must be %s" % (name, ",".join(want)))
        for cells in reader:
            if any(c.strip() for c in cells):
                row = dict((k, cells[i].strip() if i < len(cells) else "") for i, k in enumerate(want))
                row["_line"] = reader.line_num
                rows.append(row)
    return rows


def turn(x, y, rot, mirror):
    """An offset in a symbol's own frame (y down) as it lies on the sheet, turned and mirrored as the symbol is."""
    x, y = {0: (x, y), 90: (y, -x), 180: (-x, -y), 270: (-y, x)}.get(rot, (x, y))
    return (-x if mirror == "y" else x), (-y if mirror == "x" else y)


def at_of(node):
    a = hwcommon.first(node, "at", [])
    return (hwcommon.num(a[1]) if len(a) > 1 else 0.0, hwcommon.num(a[2]) if len(a) > 2 else 0.0,
            int(round(hwcommon.num(a[3]))) % 360 if len(a) > 3 else 0)


def bare(node, word):
    """True when the node holds the unquoted word, as in (pin ... hide) of older files."""
    return any(x == word and not isinstance(x, (list, hwcommon.Q)) for x in node[1:])


def text_style(node):
    """(size, justify words, hidden) of a property, label or text."""
    eff = hwcommon.first(node, "effects", [])
    size = hwcommon.first(hwcommon.first(eff, "font", []), "size", [])
    just = tuple(str(x) for x in hwcommon.first(eff, "justify", [])[1:])
    hidden = hwcommon.value(node, "hide") == "yes" or hwcommon.value(eff, "hide") == "yes" or (bool(eff) and bare(eff, "hide"))
    return (hwcommon.num(size[1], 1.27) if len(size) > 1 else 1.27), just, hidden


def lib_symbol(libs, lib_id, unit, depth=0):
    """{"power", "pins": [(number, name, type, x, y, hidden)], "pts": [...]} of one unit of a library
    symbol, in library axes (y up). pts are the corners of its drawn body."""
    node = libs.get(lib_id)
    info = {"power": False, "pins": [], "pts": []}
    if node is None or depth > 3:
        return info
    ext = hwcommon.value(node, "extends")
    if ext:
        info = lib_symbol(libs, (lib_id.split(":")[0] + ":" + ext) if ":" in lib_id else ext, unit, depth + 1)
    if hwcommon.first(node, "power") is not None:
        info["power"] = True

    def walk(n):
        for child in n:
            if not isinstance(child, list) or not child:
                continue
            kind = child[0]
            if kind == "symbol":
                m = re.search(r"_(\d+)_(\d+)$", str(child[1]) if len(child) > 1 else "")
                if m and (int(m.group(1)) not in (0, unit) or int(m.group(2)) > 1):
                    continue                                          # another unit, or the other body style
                walk(child)
            elif kind == "pin" and len(child) > 2 and not isinstance(child[1], list):
                x, y, _ = at_of(child)
                hidden = bare(child, "hide") or hwcommon.value(child, "hide") == "yes"
                info["pins"].append((hwcommon.value(child, "number"), hwcommon.value(child, "name"), str(child[1]),
                                     x, y, hidden))
            elif kind == "rectangle":
                for key in ("start", "end"):
                    p = hwcommon.first(child, key, [])
                    if len(p) > 2:
                        info["pts"].append((hwcommon.num(p[1]), hwcommon.num(p[2])))
            elif kind in ("polyline", "bezier"):
                for p in hwcommon.find(hwcommon.first(child, "pts", []), "xy"):
                    info["pts"].append((hwcommon.num(p[1]), hwcommon.num(p[2])))
            elif kind == "arc":
                for key in ("start", "mid", "end"):
                    p = hwcommon.first(child, key, [])
                    if len(p) > 2:
                        info["pts"].append((hwcommon.num(p[1]), hwcommon.num(p[2])))
            elif kind == "circle":
                c, r = hwcommon.first(child, "center", []), hwcommon.num(hwcommon.value(child, "radius"))
                if len(c) > 2:
                    info["pts"] += [(hwcommon.num(c[1]) - r, hwcommon.num(c[2]) - r),
                                    (hwcommon.num(c[1]) + r, hwcommon.num(c[2]) + r)]
    walk(node)
    return info


def read_drawing(root_path):
    """The sheets of a drawing, the top sheet first. Each sheet is a dict: file, rel (its path from the
    top sheet's folder), name, inst (its instance path), index, symbols, wires, junctions, labels, boxes
    (the sheets drawn on it), texts, bus (True when it holds a bus). A sheet file drawn twice is refused:
    these checks read one sheet per file."""
    sheets, seen = [], set()
    base = os.path.dirname(os.path.abspath(root_path))

    def load(path, inst, name):
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            raise InputError("sheet file %s is drawn more than once; these checks read one sheet per file"
                             % os.path.relpath(path, base))
        if not os.path.isfile(path):
            raise InputError("no sheet file at %s" % path)
        seen.add(key)
        root = hwcommon.read_sexpr(path)
        if inst is None:
            inst = "/" + hwcommon.value(root, "uuid")
        sh = {"file": path, "rel": os.path.relpath(os.path.abspath(path), base).replace(os.sep, "/"), "name": name,
              "inst": inst, "index": len(sheets), "symbols": [], "wires": [], "junctions": [], "labels": [],
              "boxes": [], "texts": [], "bus": bool(hwcommon.find(root, "bus") or hwcommon.find(root, "bus_entry"))}
        sheets.append(sh)
        libs = dict((str(s[1]), s) for s in hwcommon.find(hwcommon.first(root, "lib_symbols", []), "symbol")
                    if len(s) > 1)
        for s in hwcommon.find(root, "symbol"):
            x, y, rot = at_of(s)
            mirror = hwcommon.value(s, "mirror")
            unit = int(hwcommon.num(hwcommon.value(s, "unit"), 1)) or 1
            fields = {}
            for p in hwcommon.find(s, "property"):
                if len(p) > 2 and not isinstance(p[1], list) and not isinstance(p[2], list):
                    fx, fy, fa = at_of(p)
                    size, just, hidden = text_style(p)
                    fields[str(p[1])] = {"text": str(p[2]), "at": (fx, fy), "angle": fa, "size": size, "just": just,
                                         "hidden": hidden}
            ref = fields.get("Reference", {}).get("text", "")
            for proj in hwcommon.find(hwcommon.first(s, "instances", []), "project"):
                for pth in hwcommon.find(proj, "path"):
                    if len(pth) > 1 and str(pth[1]) == inst:
                        ref = hwcommon.value(pth, "reference") or ref
                        unit = int(hwcommon.num(hwcommon.value(pth, "unit"), unit)) or unit
            lib_id = hwcommon.value(s, "lib_id")
            lib = lib_symbol(libs, hwcommon.value(s, "lib_name") or lib_id, unit)
            pins = {}
            for number, pname, ptype, px, py, hidden in lib["pins"]:
                dx, dy = turn(px, -py, rot, mirror)
                pins[number] = {"name": pname, "type": ptype, "hidden": hidden, "at": (x + dx, y + dy)}
            corners = [turn(px, -py, rot, mirror) for px, py in lib["pts"]]
            box = None
            if corners:
                box = (x + min(c[0] for c in corners), y + min(c[1] for c in corners),
                       x + max(c[0] for c in corners), y + max(c[1] for c in corners))
            sh["symbols"].append({
                "ref": ref, "value": fields.get("Value", {}).get("text", ""), "lib_id": lib_id, "at": (x, y),
                "rot": rot, "mirror": mirror, "unit": unit, "power": lib["power"], "fields": fields, "pins": pins,
                "box": box, "dnp": hwcommon.value(s, "dnp") == "yes", "in_bom": hwcommon.value(s, "in_bom") != "no",
                "on_board": hwcommon.value(s, "on_board") != "no", "sheet": sh["index"]})
        for w in hwcommon.find(root, "wire"):
            pts = [(hwcommon.num(p[1]), hwcommon.num(p[2])) for p in hwcommon.find(hwcommon.first(w, "pts", []), "xy")
                   if len(p) > 2]
            sh["wires"] += list(zip(pts, pts[1:]))
        for j in hwcommon.find(root, "junction"):
            sh["junctions"].append(at_of(j)[:2])
        for kind, word in (("local", "label"), ("hierarchical", "hierarchical_label"), ("global", "global_label")):
            for n in hwcommon.find(root, word):
                if len(n) > 1 and not isinstance(n[1], list):
                    x, y, ang = at_of(n)
                    sh["labels"].append({"kind": kind, "name": str(n[1]), "at": (x, y), "angle": ang,
                                         "size": text_style(n)[0]})
        for n in hwcommon.find(root, "text"):
            if len(n) > 1 and not isinstance(n[1], list):
                x, y, ang = at_of(n)
                size, just, hidden = text_style(n)
                if not hidden:
                    sh["texts"].append({"text": str(n[1]).replace("\\n", "\n"), "at": (x, y), "angle": ang,
                                        "size": size, "just": just})
        kids = []
        for b in hwcommon.find(root, "sheet"):
            props = {}
            for p in hwcommon.find(b, "property"):
                if len(p) > 2:
                    fx, fy, fa = at_of(p)
                    size, just, hidden = text_style(p)
                    props[str(p[1]).replace(" ", "").lower()] = {"text": str(p[2]), "at": (fx, fy), "angle": fa,
                                                                 "size": size, "just": just, "hidden": hidden}
            box = {"name": props.get("sheetname", {}).get("text", ""), "file": props.get("sheetfile", {}).get("text", ""),
                   "uuid": hwcommon.value(b, "uuid"), "props": props, "child": None,
                   "pins": [(str(p[1]), at_of(p)[:2]) for p in hwcommon.find(b, "pin") if len(p) > 1]}
            sh["boxes"].append(box)
            kids.append(box)
        for box in kids:
            if box["file"]:
                box["child"] = len(sheets)
                load(os.path.join(os.path.dirname(path), box["file"]), inst + "/" + box["uuid"], box["name"])

    load(root_path, None, "")
    return sheets


class Groups:
    """Things joined together (union-find)."""

    def __init__(self, up=None):
        self.up = dict(up or {})

    def top(self, k):
        path = []
        while self.up.setdefault(k, k) != k:
            path.append(k)
            k = self.up[k]
        for p in path:
            self.up[p] = k
        return k

    def join(self, a, b):
        a, b = self.top(a), self.top(b)
        if a != b:
            self.up[a] = b


def point(sheet, at):
    return ("p", sheet, int(round(at[0] * 1000)), int(round(at[1] * 1000)))


def on_run(pt, a, b):
    """True when the point lies on the wire from a to b."""
    eps = 0.002
    if pt[0] < min(a[0], b[0]) - eps or pt[0] > max(a[0], b[0]) + eps:
        return False
    if pt[1] < min(a[1], b[1]) - eps or pt[1] > max(a[1], b[1]) + eps:
        return False
    cross = (b[0] - a[0]) * (pt[1] - a[1]) - (b[1] - a[1]) * (pt[0] - a[0])
    length = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
    return abs(cross) <= eps * max(length, eps)


def names_net(sym):
    """True for a power symbol that names the net it sits on (a supply flag does not)."""
    return sym["power"] and sym["value"] != "PWR_FLAG" and any(p["type"] == "power_in" for p in sym["pins"].values())


def connect(sheets):
    """(wires, nets): two Groups over the points of the drawing. In `wires`, points are joined only by
    wires, sheet by sheet. In `nets`, they are also joined by name, as KiCad joins them: ("g", name) for a
    power symbol, a global label or a hidden supply pin; ("l", sheet, name) for a local label;
    ("h", sheet, name) for a hierarchical label and the sheet pin of its box."""
    wires = Groups()
    for sh in sheets:
        i = sh["index"]
        pts = set(sh["junctions"])
        for a, b in sh["wires"]:
            wires.join(point(i, a), point(i, b))
            pts.update((a, b))
        for s in sh["symbols"]:
            pts.update(p["at"] for p in s["pins"].values())
        pts.update(l["at"] for l in sh["labels"])
        for box in sh["boxes"]:
            pts.update(at for _, at in box["pins"])
        for pt in pts:
            wires.top(point(i, pt))
            for a, b in sh["wires"]:
                if on_run(pt, a, b):
                    wires.join(point(i, pt), point(i, a))
    nets = Groups(wires.up)
    for sh in sheets:
        i = sh["index"]
        whole = set()                               # names that reach every sheet, drawn on this sheet
        for s in sh["symbols"]:
            for p in s["pins"].values():
                if names_net(s) and p["type"] == "power_in":
                    nets.join(point(i, p["at"]), ("g", s["value"]))
                    whole.add(s["value"])
                elif not s["power"] and p["hidden"] and p["type"] == "power_in" and p["name"] not in ("", "~"):
                    nets.join(point(i, p["at"]), ("g", p["name"]))
                    whole.add(p["name"])
        whole.update(l["name"] for l in sh["labels"] if l["kind"] == "global")
        for l in sh["labels"]:
            token = ("g", l["name"]) if l["kind"] == "global" else (l["kind"][0], i, l["name"])
            nets.join(point(i, l["at"]), token)
            if l["name"] in whole:
                nets.join(token, ("g", l["name"]))  # KiCad joins a label to a power symbol of its name on its sheet
        for box in sh["boxes"]:
            for name, at in box["pins"]:
                if box["child"] is not None:
                    nets.join(point(i, at), ("h", box["child"], name))
    return wires, nets


def drawing(d):
    """(sheets, wires, nets) of the project's drawing, read once."""
    if d._drawing is None:
        if not d.sch_path or not os.path.isfile(d.sch_path):
            raise InputError("no schematic at %s" % (d.sch_path or os.path.join(d.p["hardware"], "<name>.kicad_sch")))
        sheets = read_drawing(d.sch_path)
        d._drawing = (sheets,) + connect(sheets)
    return d._drawing


def parts_drawn(sheets):
    """Every placed symbol that is a part: no power symbols, no # designators."""
    return [s for sh in sheets for s in sh["symbols"] if not s["power"] and s["ref"] and not s["ref"].startswith("#")]


def pin_groups(sheets, nets):
    """{(designator, pin number): group} for every pin of every part on the board, as drawn."""
    out = {}
    for s in parts_drawn(sheets):
        if s["on_board"]:
            for number, p in s["pins"].items():
                out[(s["ref"], number)] = nets.top(point(s["sheet"], p["at"]))
    return out


@contextlib.contextmanager
def scratch(root, what):
    """A throw-away folder under .hwtmp/ in the project, removed afterwards whatever happens."""
    base = os.path.join(root, ".hwtmp")
    path = os.path.join(base, "%s-%d" % (what, os.getpid()))
    os.makedirs(path)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
        try:
            os.rmdir(base)
        except OSError:
            pass


def find_cli():
    try:
        import kicad_env
        return kicad_env.find_kicad_cli()
    except (ImportError, SystemExit):
        return None


def copy_sheets(d, sheets, folder):
    """Copy the sheet files (and the project file) into folder; returns the copies' paths, top sheet first."""
    base = os.path.dirname(os.path.abspath(sheets[0]["file"]))
    copies = []
    for sh in sheets:
        if sh["rel"].startswith(".."):
            raise InputError("sheet file %s is outside the folder of the top sheet, so no copy can be made" % sh["rel"])
        dest = os.path.join(folder, *sh["rel"].split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(sh["file"], dest)
        copies.append(dest)
    pro = os.path.splitext(sheets[0]["file"])[0] + ".kicad_pro"
    if os.path.isfile(pro):
        shutil.copyfile(pro, os.path.join(folder, os.path.basename(pro)))
    return copies


def export_netlist(cli, root_sheet, out_path):
    """(components, nets) of the netlist kicad-cli exports for a top sheet."""
    res = subprocess.run([cli, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", out_path, root_sheet],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    if not os.path.isfile(out_path):
        raise InputError("kicad-cli exported no netlist (exit %d): %s"
                         % (res.returncode, " ".join((res.stdout + res.stderr).split())[-300:]))
    return hwcommon.read_netlist(out_path)


def kicad_netlist(d, a, out):
    """(components, nets, where it came from) of KiCad's netlist of the drawing as it is now, or None.

    --netlist if given; else <name>.net when it is not older than any sheet file; else a fresh export by
    kicad-cli from a copy under .hwtmp/; else the older <name>.net, said to be older; else None."""
    if d._kn is None:
        sheets = drawing(d)[0]
        newest = max(os.path.getmtime(sh["file"]) for sh in sheets)
        net = d.net_path
        have = bool(net and os.path.isfile(net))
        rel = os.path.relpath(net, d.p["root"]).replace(os.sep, "/") if have else ""
        if a.netlist:
            if not have:
                raise InputError("no netlist at %s" % a.netlist)
            d._kn = (hwcommon.read_netlist(net) + ("the --netlist file",),)
        elif have and os.path.getmtime(net) >= newest:
            d._kn = (hwcommon.read_netlist(net) + (rel,),)
        else:
            cli = find_cli()
            if cli:
                with scratch(d.p["root"], "netlist") as folder:
                    copies = copy_sheets(d, sheets, folder)
                    d._kn = (export_netlist(cli, copies[0], os.path.join(folder, "export.net"))
                             + ("exported by kicad-cli for this run",),)
            elif have:
                out("%s is OLDER than the drawing, and kicad-cli was not found to export it again" % rel)
                d._kn = (hwcommon.read_netlist(net) + (rel + ", OLDER than the drawing",),)
            else:
                d._kn = (None,)
    return d._kn[0]


def pin_text(key):
    return "%s.%s" % key


def prove(d, a, out, fails):
    """Compare what is drawn joined with KiCad's netlist. Returns (netlist or None, proved or not).
    A difference is a fail: either this check reads the drawing wrongly, or the netlist is stale."""
    sheets, _, nets = drawing(d)
    kn = kicad_netlist(d, a, out)
    if kn is None:
        out("NOT PROVEN against KiCad's netlist: there is no netlist, and no kicad-cli to export one "
            "(`build.py netlist` exports it)")
        return None, False
    comps, listed_nets, where = kn
    if any(sh["bus"] for sh in sheets):
        out("NOT PROVEN against KiCad's netlist: the drawing has buses, which this check does not follow")
        return kn, False
    drawn = pin_groups(sheets, nets)
    listed = dict(((ref, pin), name) for name, nodes in listed_nets.items() for ref, pin, _, _ in nodes)
    bad = []
    drawn_refs = set(s["ref"] for s in parts_drawn(sheets) if s["on_board"])
    for ref in refs_sorted(drawn_refs - set(comps)):
        bad.append("%s is drawn and is not in the netlist" % ref)
    for ref in refs_sorted(set(comps) - set(s["ref"] for s in parts_drawn(sheets))):
        bad.append("%s is in the netlist and is not drawn" % ref)
    by_group, by_net = {}, {}
    for key in sorted(set(drawn) & set(listed), key=lambda k: (hwcommon.ref_key(k[0]), hwcommon.ref_key(k[1]))):
        by_group.setdefault(drawn[key], []).append(key)
        by_net.setdefault(listed[key], []).append(key)
    for keys in by_group.values():
        other = [k for k in keys if listed[k] != listed[keys[0]]]
        if other:
            bad.append("%s and %s are drawn joined; the netlist has them on %s and %s"
                       % (pin_text(keys[0]), pin_text(other[0]), listed[keys[0]], listed[other[0]]))
    for name, keys in sorted(by_net.items()):
        other = [k for k in keys if drawn[k] != drawn[keys[0]]]
        if other:
            bad.append("%s and %s are on net %s in the netlist and are not drawn joined"
                       % (pin_text(keys[0]), pin_text(other[0]), name))
    for text in bad[:8]:
        fails.append("drawing and netlist disagree (%s): %s" % (where, text))
    if len(bad) > 8:
        fails.append("drawing and netlist disagree (%s): %d more differences" % (where, len(bad) - 8))
    if bad:
        out("the netlist may be older than the drawing: export it again with `build.py netlist`")
        return kn, False
    out("proved: %d pins in %d nets, as this check reads the drawing, agree with the netlist (%s)"
        % (len(by_net and [k for v in by_net.values() for k in v]), len(by_net), where))
    return kn, True


# ---------------------------------------------------------------- rails, separate nets

def separate_fails(d, rows, out):
    """design/separate-nets.csv: two nets that are joined by nothing but their one link part."""
    sheets, _, nets = drawing(d)
    fails = []
    groups = {}
    for token in list(nets.up):
        if token[0] in ("g", "l", "h"):
            groups.setdefault(token[-1], set()).add(nets.top(token))
    two_pin = []
    for s in parts_drawn(sheets):
        if len(s["pins"]) == 2:
            a, b = [nets.top(point(s["sheet"], p["at"])) for p in s["pins"].values()]
            two_pin.append((s["ref"], a, b))
    for row in rows:
        where = "design/separate-nets.csv line %d" % row["_line"]
        na, nb, link = hwcommon.net_key(row["net_a"]), hwcommon.net_key(row["net_b"]), row["link_part"]
        if not na or not nb or na == nb:
            fails.append("%s: net_a and net_b must name two nets" % where)
            continue
        ga, gb = groups.get(na, set()), groups.get(nb, set())
        missing = [n for n, g in ((na, ga), (nb, gb)) if not g]
        if missing:
            out("  %s and %s: %s not drawn yet" % (na, nb, " and ".join(missing)))
            continue
        if ga & gb:
            fails.append("%s and %s are joined by a wire (%s says they stay separate)" % (na, nb, where))
            continue
        joiners = [ref for ref, a, b in two_pin if (a in ga and b in gb) or (a in gb and b in ga)]
        for ref in refs_sorted(joiners):
            if ref != link and JOINER_RE.match(ref):
                fails.append("%s joins %s and %s; %s (%s)" % (ref, na, nb, "only %s may" % link if link else
                                                               "no part may", where))
        if link and link not in joiners:
            fails.append("%s and %s: link part %s is not drawn between them (%s)" % (na, nb, link, where))
        elif link:
            out("  %s and %s: joined by %s only" % (na, nb, link))
        else:
            out("  %s and %s: kept apart, no link part" % (na, nb))
    return fails


def counted(found):
    """Fail texts from {text: count}, each once, with the number of places when there are several."""
    return ["%s%s" % (t, " (%d places)" % n if n > 1 else "") for t, n in sorted(found.items())]


def cmd_rails(d, a, out):
    rows = own_table(d, "rails.csv")
    seps = own_table(d, "separate-nets.csv", needed=False)
    sheets, wires, nets = drawing(d)
    fails, declared = [], {}
    for row in rows:
        if not row["rail"]:
            fails.append("design/rails.csv line %d: no rail name" % row["_line"])
        elif row["rail"] in declared:
            fails.append("design/rails.csv line %d: rail %s is listed twice" % (row["_line"], row["rail"]))
        else:
            declared[row["rail"]] = row
    found, drawn = {}, set()

    def add(text):
        found[text] = found.get(text, 0) + 1
    for sh in sheets:
        f = sh["rel"]
        i = sh["index"]
        on_wire, labels_on = {}, {}
        for s in sh["symbols"]:
            if not names_net(s):
                continue
            if s["value"] in declared:
                drawn.add(s["value"])
            else:
                add("%s: power symbol %s names no rail in design/rails.csv" % (f, s["value"]))
            for p in s["pins"].values():
                on_wire.setdefault(wires.top(point(i, p["at"])), set()).add(s["value"])
        for l in sh["labels"]:
            word = {"local": "a local label", "hierarchical": "a hierarchical label", "global": "a global label"}[l["kind"]]
            if l["name"] in declared:
                add("%s: rail %s is on %s; a rail is drawn with its power symbol only" % (f, l["name"], word))
            elif l["kind"] == "global":
                add("%s: signal %s is on a global label; a net between sheets goes through sheet pins" % (f, l["name"]))
            labels_on.setdefault(wires.top(point(i, l["at"])), []).append(("label", l["name"]))
        for box in sh["boxes"]:
            for name, at in box["pins"]:
                if name in declared:
                    add("%s: rail %s is on a sheet pin of box %s; a rail is drawn with its power symbol only"
                        % (f, name, box["name"]))
                labels_on.setdefault(wires.top(point(i, at)), []).append(("sheet pin", name))
        for grp, names in sorted(on_wire.items(), key=lambda kv: sorted(kv[1])):
            if len(names) > 1:
                add("%s: two rails on one wire: %s" % (f, ", ".join(sorted(names))))
            for kind, name in labels_on.get(grp, []):
                if name not in names:
                    add("%s: %s %s is on the wire of rail %s" % (f, kind, name, ", ".join(sorted(names))))
    fails += counted(found)
    out("rails declared: %d; drawn with a power symbol: %s" % (len(declared), ", ".join(sorted(drawn)) or "none"))
    idle = sorted(set(declared) - drawn)
    if idle:
        out("declared and not drawn: %s" % ", ".join(idle))
    kn, proved = prove(d, a, out, fails)
    if kn:
        listed = kn[1]
        pin_net = dict(((ref, pin), name) for name, nodes in listed.items() for ref, pin, _, _ in nodes)
        groups = pin_groups(sheets, nets)
        for rail in sorted(declared):
            others = sorted(n for n in listed if n != rail and n.split("/")[-1] == rail)
            if others and rail in listed:
                fails.append("rail %s is more than one net: %s" % (rail, ", ".join([rail] + others)))
            elif others:
                fails.append("rail %s is net %s in the netlist, not %s" % (rail, ", ".join(others), rail))
            if ("g", rail) not in nets.up:
                continue
            grp = nets.top(("g", rail))
            off = sorted((k for k, g in groups.items() if g == grp and pin_net.get(k, rail) != rail),
                         key=lambda k: (hwcommon.ref_key(k[0]), hwcommon.ref_key(k[1])))
            if off:
                fails.append("rail %s: %s%s drawn on it, and on net %s in the netlist"
                             % (rail, pin_text(off[0]), " and %d more pins are" % (len(off) - 1) if len(off) > 1
                                else " is", pin_net[off[0]]))
    if seps is None:
        out("no design/separate-nets.csv: no nets are named as kept separate")
    else:
        fails += separate_fails(d, seps, out)
    if not proved:
        d.pass_note["rails"] = " (NOT PROVEN against KiCad's netlist)"
    return fails


# ---------------------------------------------------------------- modules

def drawn_as(d, key, listed):
    """For a net name that is no net in the netlist: where it is drawn (labels and sheet pins of that
    name), how many part pins are drawn on it, and the netlist nets those pins are on."""
    sheets, _, nets = drawing(d)
    where, tops = [], set()
    for sh in sheets:
        for l in sh["labels"]:
            if l["name"] == key:
                where.append("%s label on %s" % (l["kind"], sh["rel"]))
                tops.add(nets.top(point(sh["index"], l["at"])))
        for box in sh["boxes"]:
            for name, at in box["pins"]:
                if name == key:
                    where.append("sheet pin on %s" % sh["rel"])
                    tops.add(nets.top(point(sh["index"], at)))
    where = sorted(set(where))
    if len(where) > 3:
        where = where[:3] + ["and %d more" % (len(where) - 3)]
    pin_net = dict(((ref, pin), name) for name, nodes in listed.items() for ref, pin, _, _ in nodes)
    on = [k for k, g in pin_groups(sheets, nets).items() if g in tops]
    return ", ".join(where), len(on), sorted(set(pin_net[k] for k in on if k in pin_net))


def module_net_fails(d, listed, ref_module, mnets, rail_keys, out, strict):
    """Nets between modules against design/module-nets.csv. With strict, a net that does not reach a
    module listed for it is a fail (the probe); without, it is said to be not reached yet."""
    fails = []

    def is_rail(name):
        key = hwcommon.net_key(name)
        if rail_keys is not None:
            return key in rail_keys
        return is_ground(name) or d.voltage(name) is not None

    def modules_on(name):
        return sorted(set(ref_module[r] for r, _, _, _ in listed[name] if r in ref_module))
    rows = dict((hwcommon.net_key(r["net"]), r) for r in mnets if r["net"])
    exact = set(hwcommon.net_key(n) for n in listed)

    def row_key(name):
        key = hwcommon.net_key(name)
        if key in rows:
            return key
        last = key.split("/")[-1]                       # a net with no label on the top sheet is named from a sheet
        return last if last in rows and last not in exact else None
    found = {}
    for name in sorted(listed):
        if name.startswith("unconnected-") or is_rail(name):
            continue
        mods, key = modules_on(name), row_key(name)
        if key is not None:
            found.setdefault(key, []).append((name, mods))
        if len(mods) < 2:
            continue
        if key is None:
            fails.append("net %s joins modules %s and is not in design/module-nets.csv"
                         % (hwcommon.net_key(name), ", ".join(mods)))
            continue
        for m in mods:
            if m not in hwcommon.split_list(rows[key]["modules"]):
                fails.append("net %s joins module %s, which design/module-nets.csv does not list for it" % (key, m))
    for key in sorted(rows):
        want = hwcommon.split_list(rows[key]["modules"])
        got = found.get(key, [])
        if not got:
            if strict:
                fails.append("net %s is not in the drawing; it does not reach module %s" % (key, ", ".join(want)))
                continue
            where, pins, joined = drawn_as(d, key, listed)
            if pins:
                fails.append("net %s is drawn (%s) and is not a net of its own in the netlist: it is joined to %s"
                             % (key, where, "net " + ", ".join(joined) if joined else
                                "another net, which the netlist does not name"))
            elif where:
                out("  %s: drawn, with no part pin on it yet" % key)
            else:
                out("  %s: not drawn yet" % key)
            continue
        if len(got) > 1:
            text = "net %s is %d nets in the drawing (%s)" % (key, len(got), ", ".join(n for n, _ in got))
            if strict:
                fails.append(text)
            else:
                out("  %s: %s" % (key, text))
            continue
        reached = got[0][1]
        missing = [m for m in want if m not in reached]
        out("  %s: %s%s" % (key, ", ".join(reached) or "no module",
                            " (not reached%s: %s)" % ("" if strict else " yet", ", ".join(missing)) if missing else ""))
        if strict:
            fails += ["net %s does not reach module %s" % (key, m) for m in missing]
    return fails


def close_paren(text, start):
    """Index of the ')' that closes the '(' at start. Quoted text is skipped."""
    depth, i = 0, start
    while i < len(text):
        c = text[i]
        if c == '"':
            i += 1
            while i < len(text) and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise InputError("unbalanced brackets in a sheet file")


def quoted(text):
    return '"%s"' % str(text).replace("\\", "\\\\").replace('"', '\\"')


def add_probes(text, placed):
    """The sheet file's text with the probe symbol in its library and the placed probes after it."""
    m = re.search(r"\(lib_symbols\b", text)
    if not m:
        raise InputError("a sheet file has no (lib_symbols ...) block, so no probe can be added")
    end = close_paren(text, m.start())
    lib = "" if '"hwprobe:TP"' in text[m.start():end] else "\n" + PROBE_LIB + "  "
    return text[:end] + lib + ")\n" + "".join(placed) + text[end + 1:]


def probe_modules(d, cli, out, mnets, ref_module, module_of, rail_keys):
    """A throw-away copy with one test point on every hierarchical label: KiCad's netlist of it shows
    which modules each net between sheets reaches, even on a skeleton with no parts. Then one net is cut
    in the copy, and the check must fail on it."""
    sheets = drawing(d)[0]
    fails = []
    with open(sheets[0]["file"], encoding="utf-8") as f:
        m = re.search(r'\(instances\s*\(project\s+("(?:[^"\\]|\\.)*")', f.read())
    project = m.group(1) if m else quoted(os.path.splitext(os.path.basename(sheets[0]["file"]))[0])
    with scratch(d.p["root"], "probe") as folder:
        copies = copy_sheets(d, sheets, folder)
        probes = {}
        for sh in sheets[1:]:
            placed = []
            for l in sh["labels"]:
                if l["kind"] != "hierarchical":
                    continue
                ref = "%s%d" % (PROBE_REF, len(probes) + 1)
                probes[ref] = (module_of.get(sh["index"], sh["rel"]), l["name"])
                placed.append(PROBE_PLACED % {"x": "%.4f" % l["at"][0], "y": "%.4f" % l["at"][1], "ref": ref,
                                              "uuid": uuid.uuid4(), "pin": uuid.uuid4(), "project": project,
                                              "path": sh["inst"]})
            if placed:
                with open(copies[sh["index"]], encoding="utf-8") as f:
                    text = f.read()
                hwcommon.write_text(copies[sh["index"]], add_probes(text, placed))
        out("probe: %d test points, one on every hierarchical label, in a copy under .hwtmp/ (removed afterwards)"
            % len(probes))
        listed = export_netlist(cli, copies[0], os.path.join(folder, "probe.net"))[1]
        where = dict(ref_module)
        where.update((ref, pm[0]) for ref, pm in probes.items())
        fails += module_net_fails(d, listed, where, mnets, rail_keys, out, True)
        net_of = dict((ref, name) for name, nodes in listed.items() for ref, _, _, _ in nodes)
        said = set()
        for ref in refs_sorted(probes):
            mods = set(where[r] for r, _, _, _ in listed.get(net_of.get(ref, ""), []) if r in where)
            if len(mods) < 2 and probes[ref] not in said:
                said.add(probes[ref])
                fails.append("hierarchical label %s of module %s reaches no other module" % (probes[ref][1], probes[ref][0]))
        target = None
        for row in mnets:
            for module in reversed(hwcommon.split_list(row["modules"])):
                for sh in sheets[1:]:
                    if target is None and module_of.get(sh["index"]) == module and any(
                            l["kind"] == "hierarchical" and l["name"] == hwcommon.net_key(row["net"]) for l in sh["labels"]):
                        target = (hwcommon.net_key(row["net"]), module, sh)
        if fails:
            out("planted fault: not tried, because the copy already fails")
        elif target is None:
            out("planted fault: not tried, because no net of design/module-nets.csv is on a hierarchical label")
        else:
            key, module, sh = target
            with open(copies[sh["index"]], encoding="utf-8") as f:
                text = f.read()
            cut, n = re.subn(r"\(hierarchical_label\s+%s" % re.escape(quoted(key)),
                             lambda _: '(hierarchical_label "HWPROBE_CUT"', text)
            hwcommon.write_text(copies[sh["index"]], cut)
            again = export_netlist(cli, copies[0], os.path.join(folder, "probe-fault.net"))[1]
            want = "net %s does not reach module %s" % (key, module)
            got = module_net_fails(d, again, where, mnets, rail_keys, lambda text: None, True)
            if n and want in got:
                out("planted fault caught: with %s cut from module %s in the copy, the check failed (%s)"
                    % (key, module, want))
            else:
                fails.append("the planted fault was not caught: %s was cut from module %s in the copy, and the check "
                             "did not fail on it" % (key, module))
    return fails


def cmd_modules(d, a, out):
    mods = own_table(d, "modules.csv")
    mnets = own_table(d, "module-nets.csv")
    rails = own_table(d, "rails.csv", needed=False)
    seps = own_table(d, "separate-nets.csv", needed=False)
    cli = None
    if a.probe:
        cli = find_cli()
        if not cli:
            raise InputError("modules --probe needs kicad-cli to export the netlist of its copy, and kicad-cli "
                             "was not found")
    sheets = drawing(d)[0]
    fails = []
    # the tables
    blocks, by_sheet, names = {}, {}, set()
    for r in mods:
        where = "design/modules.csv line %d" % r["_line"]
        if not r["module"] or not r["sheet"]:
            fails.append("%s: a row needs its module and its sheet" % where)
            continue
        if r["module"] in names:
            fails.append("%s: module %s is listed twice" % (where, r["module"]))
            continue
        names.add(r["module"])
        sheet = r["sheet"].replace("\\", "/")
        if sheet in by_sheet:
            fails.append("%s: sheet %s is already the sheet of module %s" % (where, sheet, by_sheet[sheet]))
        else:
            by_sheet[sheet] = r["module"]
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", r["ref_block"])
        if not m or int(m.group(1)) > int(m.group(2)):
            fails.append("%s: ref_block %r is not a block of numbers such as 100-199" % (where, r["ref_block"]))
        else:
            blocks[r["module"]] = (int(m.group(1)), int(m.group(2)))
    order = sorted(blocks.items(), key=lambda kv: kv[1])
    for (m1, b1), (m2, b2) in zip(order, order[1:]):
        if b2[0] <= b1[1]:
            fails.append("design/modules.csv: blocks overlap: %s %d-%d and %s %d-%d" % (m1, b1[0], b1[1], m2, b2[0], b2[1]))
    rail_keys = None if rails is None else set(hwcommon.net_key(r["rail"]) for r in rails)
    seen = set()
    for r in mnets:
        where = "design/module-nets.csv line %d" % r["_line"]
        key = hwcommon.net_key(r["net"])
        if not key:
            fails.append("%s: no net name" % where)
            continue
        if key in seen:
            fails.append("%s: net %s is listed twice" % (where, key))
        seen.add(key)
        if rail_keys and key in rail_keys:
            fails.append("%s: %s is a rail in design/rails.csv; rails reach every sheet and are not listed here"
                         % (where, key))
        listed = hwcommon.split_list(r["modules"])
        for m in listed:
            if m not in names:
                fails.append("%s: net %s names module %s, which is not in design/modules.csv" % (where, key, m))
        if len(set(listed)) < 2:
            fails.append("%s: net %s lists fewer than two modules" % (where, key))
    # one sheet per module, and nothing but the module boxes on the top sheet
    module_of = {}
    for sh in sheets[1:]:
        if sh["rel"] in by_sheet:
            module_of[sh["index"]] = by_sheet[sh["rel"]]
        elif not (sh["symbols"] or sh["wires"] or sh["labels"] or sh["boxes"]):
            out("sheet %s holds text only, so it is no module (a closing page such as the firmware page)" % sh["rel"])
        else:
            fails.append("sheet %s is in the drawing and has no row in design/modules.csv" % sh["rel"])
    drawn = set(sh["rel"] for sh in sheets[1:])
    for sheet, module in sorted(by_sheet.items(), key=lambda kv: kv[1]):
        if sheet not in drawn:
            fails.append("module %s: sheet %s is not in the drawing" % (module, sheet))
    held = [s["ref"] if not s["power"] else "power symbol %s" % s["value"] for s in sheets[0]["symbols"]]
    if held:
        fails.append("top sheet %s holds %s; it may hold only the module boxes and the nets between them"
                     % (sheets[0]["rel"], ", ".join(sorted(set(held)))))
    # designators in the module's block, for every prefix
    ref_module = {}
    for sh in sheets[1:]:
        module = module_of.get(sh["index"])
        for s in parts_drawn([sh]):
            if module is None:
                continue
            ref_module[s["ref"]] = module
            if module not in blocks:
                continue
            m = re.match(r"^[^0-9]*(\d+)", s["ref"])
            lo, hi = blocks[module]
            if not m:
                fails.append("%s: %s has no number; module %s uses the block %d-%d" % (sh["rel"], s["ref"], module, lo, hi))
            elif not lo <= int(m.group(1)) <= hi:
                fails.append("%s: %s is outside the block %d-%d of module %s" % (sh["rel"], s["ref"], lo, hi, module))
    out("modules: %d; sheets drawn under the top sheet: %d; parts: %d" % (len(names), len(sheets) - 1, len(ref_module)))
    # nets between modules
    if a.probe:
        fails += probe_modules(d, cli, out, mnets, ref_module, module_of, rail_keys)
    else:
        kn = kicad_netlist(d, a, out)
        if kn is None:
            raise InputError("modules follows nets between sheets in the netlist: there is no netlist, and no "
                             "kicad-cli to export one (`build.py netlist` exports it)")
        out("nets between modules, from the netlist (%s):" % kn[2])
        fails += module_net_fails(d, kn[1], ref_module, mnets, rail_keys, out, False)
    if seps is not None:
        fails += separate_fails(d, seps, out)
    return fails


# ---------------------------------------------------------------- overlap

def text_width(text, size):
    """Estimated width of a line of text in KiCad's own font: this file holds no font, so it is a guess
    on the wide side."""
    t = re.sub(r"[~^_]\{([^}]*)\}", r"\1", text)
    return sum(0.94 if (c.isupper() or c.isdigit()) else 0.78 for c in t) * size


def rel_box(text, size, just, upright=False, extra=0.0, tall=1.0):
    """Two opposite corners of a text's box, from the point it is placed at (y down)."""
    lines = text.split("\n")
    w = max(text_width(line, size) for line in lines) + extra
    h = size * tall * (1 + 1.6 * (len(lines) - 1))
    x0 = 0.0 if "left" in just else (-w if "right" in just else -w / 2)
    y0 = 0.0 if "top" in just else (-h if "bottom" in just else -h / 2)
    pts = [(x0, y0), (x0 + w, y0 + h)]
    return [(y, -x) for x, y in pts] if upright else pts


def box_at(pts, at, by=0.15):
    """The box on the sheet, drawn in a little so that things that only touch do not count."""
    xs, ys = sorted(at[0] + p[0] for p in pts), sorted(at[1] + p[1] for p in pts)
    bx, by_ = min(by, (xs[1] - xs[0]) / 2), min(by, (ys[1] - ys[0]) / 2)
    return (xs[0] + bx, ys[0] + by_, xs[1] - bx, ys[1] - by_)


def boxes_meet(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def wire_meets(b, p, q):
    """True when the wire from p to q passes through the box."""
    t0, t1 = 0.0, 1.0
    dx, dy = q[0] - p[0], q[1] - p[1]
    for step, room in ((-dx, p[0] - b[0]), (dx, b[2] - p[0]), (-dy, p[1] - b[1]), (dy, b[3] - p[1])):
        if step == 0:
            if room <= 0:
                return False
        elif step < 0:
            t0 = max(t0, room / step)
        else:
            t1 = min(t1, room / step)
    return t0 < t1


def sheet_texts(sh):
    """[(what it is, box, owner)] for every text shown on a sheet; owner is the symbol it belongs to."""
    out = []
    for n, s in enumerate(sh["symbols"]):
        owner = ("power symbol %s" % s["value"]) if s["power"] or s["ref"].startswith("#") else s["ref"]
        for name, f in s["fields"].items():
            if f["hidden"] or f["text"] in ("", "~"):
                continue
            pts = rel_box(f["text"], f["size"], f["just"], f["angle"] in (90, 270))
            pts = [turn(x, y, s["rot"], s["mirror"]) for x, y in pts]
            out.append(('%s %s "%s"' % (owner, name, f["text"]), box_at(pts, f["at"]), n))
    for l in sh["labels"]:
        just = ("left",) if l["angle"] in (0, 90) else ("right",)
        if l["kind"] == "local":
            pts = rel_box(l["name"], l["size"], just + ("bottom",), l["angle"] in (90, 270))
            what = 'label "%s"' % l["name"]
        else:
            pts = rel_box(l["name"], l["size"], just, l["angle"] in (90, 270), extra=1.5 * l["size"], tall=1.3)
            what = '%s label "%s"' % (l["kind"], l["name"])
        out.append((what, box_at(pts, l["at"]), None))
    for t in sh["texts"]:
        first = t["text"].split("\n")[0]
        pts = rel_box(t["text"], t["size"], t["just"], t["angle"] in (90, 270))
        out.append(('text "%s"' % (first if len(first) <= 30 else first[:27] + "..."), box_at(pts, t["at"]), None))
    for box in sh["boxes"]:
        for key, word in (("sheetname", "sheet name"), ("sheetfile", "sheet file")):
            f = box["props"].get(key)
            if f and not f["hidden"] and f["text"]:
                pts = rel_box(f["text"], f["size"], f["just"], f["angle"] in (90, 270))
                out.append(('%s "%s"' % (word, f["text"]), box_at(pts, f["at"]), None))
    return out


def cmd_overlap(d, a, out):
    sheets = drawing(d)[0]
    fails, count = [], 0
    for sh in sheets:
        texts = sheet_texts(sh)
        count += len(texts)
        for i, (what, box, owner) in enumerate(texts):
            where = "(%.2f, %.2f)" % ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            for other, obox, _ in texts[i + 1:]:
                if boxes_meet(box, obox):
                    fails.append("%s: %s overlaps %s at %s" % (sh["rel"], what, other, where))
            for n, s in enumerate(sh["symbols"]):
                if n != owner and s["box"] and boxes_meet(box, s["box"]):
                    name = ("power symbol %s" % s["value"]) if s["power"] or s["ref"].startswith("#") else "symbol " + s["ref"]
                    fails.append("%s: %s overlaps %s at %s" % (sh["rel"], what, name, where))
            if any(wire_meets(box, p, q) for p, q in sh["wires"]):
                fails.append("%s: %s overlaps a wire at %s" % (sh["rel"], what, where))
    out("texts checked: %d on %d sheets (text sizes are estimated: KiCad's font is not read)" % (count, len(sheets)))
    return fails


# ---------------------------------------------------------------- chosen, fields

def field(sym, *names):
    for name in names:
        f = sym["fields"].get(name)
        if f and f["text"].strip() not in ("", "~"):
            return f["text"].strip()
    return ""


def parse_match(text):
    """[(key, pattern)] from a match such as "role=pull;value=10k", or None when it cannot be read."""
    terms = []
    for part in hwcommon.split_list(text):
        key, sep, want = part.partition("=")
        if not sep or key.strip().lower() not in ("value", "role", "footprint") or not want.strip():
            return None
        terms.append((key.strip().lower(), want.strip().lower()))
    return terms or None


def names_token(text, token):
    return bool(token) and re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(token), text or "", re.IGNORECASE) is not None


def cmd_chosen(d, a, out):
    rows = own_table(d, "chosen-parts.csv")
    parts = parts_drawn(drawing(d)[0])
    entries = dict((e["id"], e) for e in hwcommon.decision_entries(d.p["design"]))
    by_user = [e for e in entries.values() if e["fields"].get("Decided by", "").strip().lower().startswith("user")]
    fails = []
    for row in rows:
        where = "design/chosen-parts.csv line %d" % row["_line"]
        kind = row["kind"] or "?"
        terms = parse_match(row["match"])
        if terms is None:
            fails.append("%s: cannot read match %r; write value=, role= or footprint= terms joined by ';' "
                         "(* stands for any text)" % (where, row["match"]))
            continue
        if not re.match(r"^DC-\d+$", row["decision"]):
            fails.append("%s: decision %r is not the ID of the DC- entry in which the user chose the part"
                         % (where, row["decision"]))
        elif row["decision"] not in entries:
            fails.append("%s: decision %s is not an entry in design/decisions.md" % (where, row["decision"]))
        elif entries[row["decision"]] not in by_user:
            fails.append("%s: decision %s is not decided by the user" % (where, row["decision"]))
        if not row["mpn"]:
            fails.append("%s: no mpn" % where)
        excepted = hwcommon.split_list(row["except_refs"])
        found = []
        for s in parts:
            have = {"value": s["value"], "role": d.parts.get(s["ref"], {}).get("role", ""),
                    "footprint": field(s, "Footprint")}
            if all(fnmatch.fnmatchcase(have[k].lower(), want) for k, want in terms):
                found.append(s)
        out("  %s: %d positions; chosen %s, supplier number %s (%s)" % (kind, len(found), row["mpn"] or "none",
                                                                      row["supplier_pn"] or "none", row["decision"] or "no decision"))
        for s in sorted(found, key=lambda s: hwcommon.ref_key(s["ref"])):
            ref = s["ref"]
            mpn, spn = field(s, "MPN"), field(s, "Supplier PN")
            note = ""
            if ref in excepted:
                named = [e["id"] for e in by_user if names_token(e["text"], ref)]
                if named:
                    note = " (exception, %s)" % ", ".join(sorted(named))
                else:
                    fails.append("%s is in except_refs of kind %s, and no user decision in design/decisions.md names it"
                                 % (ref, kind))
            elif mpn != row["mpn"] or (row["supplier_pn"] and spn != row["supplier_pn"]):
                fails.append("%s (kind %s): drawn with MPN %s, supplier number %s; the part chosen in %s is %s, "
                             "supplier number %s; %s is not in except_refs"
                             % (ref, kind, mpn or "none", spn or "none", row["decision"] or "no decision",
                                row["mpn"] or "none", row["supplier_pn"] or "none", ref))
            out("    %s: %s, supplier number %s%s%s" % (ref, mpn or "no MPN", spn or "none", note,
                                                       ", not fitted" if s["dnp"] else ""))
        for ref in excepted:
            if ref not in [s["ref"] for s in found]:
                out("    %s is in except_refs and is not a position of this kind" % ref)
    return fails


def cmd_fields(d, a, out):
    sheets = drawing(d)[0]
    parts = [s for s in parts_drawn(sheets) if s["in_bom"] and not s["dnp"]
             and "not fitted" not in d.parts.get(s["ref"], {}).get("variant", "")]
    known = set(r["mpn"] for r in d.parts_rows if len(r["mpn"]) >= 3) | set(m for m in (field(s, "MPN") for s in parts)
                                                                             if len(m) >= 3)
    fails, done = [], set()
    for s in sorted(parts, key=lambda s: hwcommon.ref_key(s["ref"])):
        ref = s["ref"]
        if (ref, s["sheet"]) in done:                     # another unit of the same part: same fields
            continue
        done.add((ref, s["sheet"]))
        where = "%s: %s" % (sheets[s["sheet"]]["rel"], ref)
        row = d.parts.get(ref, {})
        mpn, spn, link, desc = field(s, "MPN"), field(s, "Supplier PN"), field(s, "Datasheet"), field(s, "Description")
        if not spn:
            fails.append("%s: no supplier part number" % where)
        elif row.get("supplier_pn") and spn != row["supplier_pn"]:
            fails.append("%s: supplier part number %s on the symbol, %s in design/parts.csv" % (where, spn, row["supplier_pn"]))
        if mpn and row.get("mpn") and mpn != row["mpn"]:
            fails.append("%s: MPN %s on the symbol, %s in design/parts.csv" % (where, mpn, row["mpn"]))
        if not link:
            fails.append("%s: no datasheet link" % where)
        own = [m for m in (mpn, row.get("mpn", "")) if m]
        for word, text in (("datasheet link", link), ("description", desc)):
            if not text or any(names_token(text, m) for m in own):
                continue
            other = [m for m in sorted(known) if m not in own and names_token(text, m)]
            if other:
                fails.append("%s: %s %s names another part (%s)" % (where, word, text, other[0]))
    out("symbols checked: %d (fitted, in the BOM)" % len(done))
    return fails


# ---------------------------------------------------------------- netload, drive

def part_sheets(d):
    sheets = drawing(d)[0]
    return dict((s["ref"], sheets[s["sheet"]]["rel"]) for s in parts_drawn(sheets))


def load_text(per_sheet):
    """"alpha.kicad_sch 5 mA firm, up to 500 uA more; ..." and the two totals, from {sheet: [firm, up to]}."""
    bits, firm, upto = [], 0.0, 0.0
    for sheet in sorted(per_sheet):
        f, u = per_sheet[sheet]
        firm, upto = firm + f, upto + u
        if f and u:
            bits.append("%s %s firm, up to %s more" % (sheet, fmt_si(f, "A"), fmt_si(u, "A")))
        elif f:
            bits.append("%s %s firm" % (sheet, fmt_si(f, "A")))
        elif u:
            bits.append("%s up to %s" % (sheet, fmt_si(u, "A")))
    return "; ".join(bits), firm, upto


def cmd_netload(d, a, out):
    budgets = {}
    for item in a.budget:
        net, sep, amps = item.partition("=")
        try:
            budgets[hwcommon.net_key(net)] = float(amps)
        except ValueError:
            sep = ""
        if not sep or not net or budgets.get(hwcommon.net_key(net), 0) <= 0:
            raise InputError("--budget needs NET=AMPS, for example --budget +5V=0.5; got %r" % item)
    for row in own_table(d, "rails.csv", needed=False) or []:
        try:
            if row["rail"] not in d.rails and not is_ground(row["rail"]):
                d.rails[row["rail"]] = float(row["voltage"].upper().replace("V", "").strip())
        except ValueError:
            pass
    sheet_of = part_sheets(d)
    out("load through resistors, by sheet (firm: both ends at a known voltage; up to: the other end is a signal):")
    for net in sorted(d.nets):
        v = d.voltage(net)
        if not v or is_ground(net) or net.startswith("unconnected-"):
            continue
        per, others = {}, []
        for ref, pin, _, _ in d.nets[net]:
            if not d.fitted(ref) or d.is_capacitor(ref):
                continue
            if not d.is_resistor(ref):
                others.append("%s.%s" % (ref, pin))
                continue
            r = parse_value(d.comps[ref]["value"], "ohm")
            n1, n2 = d.two_pin(ref)
            other = n2 if n1 == net else n1
            if not r or not other or other == net:
                continue
            slot = per.setdefault(sheet_of.get(ref, "sheet not known"), [0.0, 0.0])
            vo = d.voltage(other)
            if vo is None:
                slot[1] += v / r
            elif vo < v:
                slot[0] += (v - vo) / r
        text, firm, upto = load_text(per)
        out("  %s (%g V): %s" % (net, v, text or "no resistor loads"))
        total = "%s firm%s" % (fmt_si(firm, "A"), ", up to %s more" % fmt_si(upto, "A") if upto else "")
        key = hwcommon.net_key(net)
        if key in budgets:
            share = 100.0 * (firm + upto) / budgets[key]
            total += "; %.0f%% of the budget %s%s" % (share, fmt_si(budgets[key], "A"),
                                                      " ABOVE the level %g%%" % a.level if share > a.level else "")
        else:
            total += "; no budget given (--budget %s=AMPS)" % key
        out("  %s total: %s" % (net, total))
        if others:
            out("    not counted, their currents are in no table: %s" % ", ".join(others[:12])
                + (" and %d more" % (len(others) - 12) if len(others) > 12 else ""))
    out("load on driven nets (each resistor at the driver's supply voltage):")
    for net in sorted(d.nets):
        if is_ground(net) or d.is_supply(net) or net.startswith("unconnected-"):
            continue
        drivers = [(ref, pin) for ref, pin, _, ptype in d.nets[net]
                   if ptype == "output" or d.rows.get(ref, {}).get(pin, {}).get("current_limit")]
        loads = [ref for ref, _, _, _ in d.nets[net] if d.is_resistor(ref) and d.fitted(ref)]
        if not drivers or not loads:
            continue
        ref, pin = drivers[0]
        row = d.rows.get(ref, {}).get(pin, {})
        volts = [d.voltage(row["supply"])] if row.get("supply") else [
            d.voltage(d.net_of(ref, n)) for n, p in d.symbol_pins(ref).items() if p[1] == "power_in" and d.net_of(ref, n)]
        volts = [x for x in volts if x]
        who = "driven by %s" % ", ".join("%s.%s" % k for k in drivers)
        if not volts:
            out("  %s (%s): the driver's supply voltage is not known (pass --rail NET=VOLTS); resistors on it: %s"
                % (net, who, ", ".join("%s %s" % (r, d.comps[r]["value"]) for r in refs_sorted(loads))))
            continue
        v = max(volts)
        per = {}
        for load in loads:
            r = parse_value(d.comps[load]["value"], "ohm")
            n1, n2 = d.two_pin(load)
            other = n2 if n1 == net else n1
            if not r or not other or other == net:
                continue
            vo = d.voltage(other)
            per.setdefault(sheet_of.get(load, "sheet not known"), [0.0, 0.0])[1] += (
                v if vo is None else max(abs(v - vo), abs(vo))) / r
        text, _, upto = load_text(per)
        limit = "; current_limit in pins.csv: %s" % row["current_limit"] if row.get("current_limit") else ""
        out("  %s (%s, %g V): %s; total up to %s%s" % (net, who, v, text, fmt_si(upto, "A"), limit))
    out("supply currents of ICs and transistors are in no table: add them from the datasheets by hand")
    return []


def pin_name(d, ref, pin, func):
    """A pin's name from the library symbol, else from the netlist (which may write NAME_number)."""
    name = d.symbol_pins(ref).get(pin, ("",))[0]
    if not name or name == "~":
        name = re.sub(r"_%s$" % re.escape(pin), "", func or "")
    return norm_name(name)


def cmd_drive(d, a, out):
    fails, nets = [], 0
    for net in sorted(d.nets):
        if is_ground(net) or d.is_supply(net) or net.startswith("unconnected-"):
            continue
        nets += 1
        bases, gates = [], []
        for ref, pin, func, _ in d.nets[net]:
            if re.match(r"^(Q|T)\d", ref, re.IGNORECASE) and d.fitted(ref):
                name = pin_name(d, ref, pin, func)
                if name in ("B", "BASE"):
                    bases.append("%s.%s" % (ref, pin))
                elif name in ("G", "GATE"):
                    gates.append("%s.%s" % (ref, pin))
        if len(bases) > 1:
            fails.append("net %s feeds %d transistor bases (%s) with no resistor each; one base can take most of "
                         "the drive: give each base its own resistor" % (net, len(bases), ", ".join(bases)))
        if len(gates) > 1:
            out("  %d gates share net %s (%s): gates take no steady current, so this is not a fail" % (
                len(gates), net, ", ".join(gates)))
    out("signal nets checked: %d" % nets)
    return fails


COMMANDS = {"pins": cmd_pins, "alloc": cmd_alloc, "powerup": cmd_powerup, "protect": cmd_protect,
            "domains": cmd_domains, "opendrain": cmd_opendrain, "unused": cmd_unused,
            "decouple-list": cmd_decouple, "testpoints": cmd_testpoints, "currents": cmd_currents,
            "railcap": cmd_railcap, "rails": cmd_rails, "modules": cmd_modules, "overlap": cmd_overlap,
            "chosen": cmd_chosen, "fields": cmd_fields, "netload": cmd_netload, "drive": cmd_drive}


def run_one(d, a, name, out, alone=True):
    out("== sch_check %s" % name)
    try:
        fails = COMMANDS[name](d, a, out)
    except NotRun as e:
        if alone:
            raise
        out("%s: not run (%s)" % (name, e))         # under `all`, a check whose table is not there is left out
        return []
    if name in PASS_FAIL:
        for f in fails:
            out("FAIL  " + f)
        out("%s: %s" % (name, "pass%s" % d.pass_note.get(name, "") if not fails else "FAIL (%d)" % len(fails)))
    elif fails:                                     # a review list: only its lines that say NONE can fail
        for f in fails:
            out("FAIL  " + f)
        out("%s: FAIL (%d)" % (name, len(fails)))
    return fails


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=sorted(COMMANDS) + ["all"])
    ap.add_argument("--project", default=".", help="project root, or a folder inside it (default: here)")
    ap.add_argument("--name", help="project name in the KiCad folder when there are several")
    ap.add_argument("--netlist", help="netlist file (default <name>.net in the KiCad folder)")
    ap.add_argument("--sch", help="root schematic (default <name>.kicad_sch in the KiCad folder)")
    ap.add_argument("--board", help="board file for footprint pads (default <name>.kicad_pcb in the KiCad folder)")
    ap.add_argument("--import", dest="import_vendor", metavar="VENDOR",
                    help="pins: read vendor pin data; vendors: %s" % "; ".join("%s = %s" % kv for kv in sorted(IMPORTERS.items())))
    ap.add_argument("--data", help="pins --import: the local copy of the vendor's file or folder")
    ap.add_argument("--designator", help="pins --import: the part to compare or fill")
    ap.add_argument("--mpn", help="pins --import: the MPN to look up (default: the part's MPN field)")
    ap.add_argument("--write", action="store_true", help="pins --import: add the vendor rows to pins.csv")
    ap.add_argument("--record", action="store_true", help="review lists: add new items to design/net-review.csv")
    ap.add_argument("--rail", action="append", default=[], metavar="NET=VOLTS", help="currents: a rail voltage")
    ap.add_argument("--probe", action="store_true",
                    help="modules: follow the nets between sheets with test points in a throw-away copy, and "
                         "plant a fault in it to show the check fails (needs kicad-cli)")
    ap.add_argument("--budget", action="append", default=[], metavar="NET=AMPS",
                    help="netload: the current a rail's source can give")
    ap.add_argument("--level", type=float, default=80.0, metavar="PERCENT",
                    help="netload: the share of a budget that is marked (default 80)")
    a = ap.parse_args(argv)
    try:
        paths = hwcommon.find_project(a.project, a.name)
        d = Design(paths, a.netlist, a.sch, a.board, need_netlist=a.command not in NO_NETLIST)
        for item in a.rail:
            net, _, v = item.partition("=")
            d.rails[net] = float(v)
        names = ORDER if a.command == "all" else (a.command,)
        failed = []
        for name in names:
            failed += run_one(d, a, name, print, alone=a.command != "all")
    except (InputError, hwcommon.ProjectError, hwcommon.TableError, ValueError, OSError, ET.ParseError) as e:
        print("sch_check: %s" % e, file=sys.stderr)
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
