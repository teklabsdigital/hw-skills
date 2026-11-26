# Copyright 2026 Teklabs Digital (hw-skills)
# SPDX-License-Identifier: Apache-2.0
"""Simulate one module of the schematic on the circuit simulator library that ships with KiCad (ngspice).

Plain Python 3, standard library only (ctypes). Nothing is installed and nothing is fetched. The
procedure is in references/simulation.md; the table forms are in references/project-files.md.

    python3 spice.py engine-check
        Find and load the library, run small circuits whose answers are known by hand, and fail if
        the simulator disagrees. Says plainly when the library is not found.

    python3 spice.py netlist <module> [--ground NET]
        Write sim/<module>/<module>.cir from the netlist the build exported and design/sim-models.csv.
        Stops on a part with no row in the model table. R, C and L parts with a plain value need no row.

    python3 spice.py model-check [--mpn MPN --points FILE]
        Check every row of design/sim-models.csv: the file is under sim/models/, its sha256 matches,
        the model name is in it, and it holds no simulator commands, no includes of files outside
        sim/models/ and no shell calls. With --mpn and --points, also run that one model alone at the
        points in FILE (the columns of scenarios.csv; each setup instantiates the model) and compare
        each figure with its limits. Results go beside FILE as <FILE stem>.results.csv.

    python3 spice.py run <module> [--again]
        Run each row of sim/<module>/scenarios.csv on the circuit file and write, under
        sim/<module>/results/, one waveform file per row, results.csv with pass or fail per row, and
        run.txt. With --again nothing is written: the run is compared with the files already there.

Common options: --project DIR (project root or a folder inside it), --name NAME, --netlist FILE,
--compat MODE (a compatibility mode some makers' models need; it is written into run.txt).

The library is looked for in the KiCad that kicad_env.py finds. Set KICAD_NGSPICE to the library file
to use another place, and KICAD_NGSPICE_CM to the folder of code models (*.cm). Developed on
macOS. Locations for Windows and Linux are included.

Scenario columns that this script reads as data:

    setup    Lines for the simulator, joined by ";": sources, loads, .temp, .ic, .options and one
             analysis (.op, .tran or .dc). A line ".include <file>" may name a file in sim/models/ only;
             its text is checked and put in line. Commands are refused.
    measure  One of
                 final <vector>                       the last point
                 first <vector>                       the first point
                 value <vector> at <x>                at time (or sweep value) x, between points
                 min|max|avg|rms|pp <vector> [from <a>] [to <b>]
                 cross <vector> <level> rise|fall [from <a>]     the time of the first crossing
             with "scale <k>" allowed at the end. A vector is v(<node>), i(<voltage source>) or a name
             as the simulator gives it. Numbers may carry the usual suffixes (1m, 4u7 is not one; 4.7u is).
    limit_low, limit_high   Numbers; one may be empty. A row with limits and no source fails.

Exit code: 0 all pass, 1 a check or a limit failed, 2 the command could not run.

A model file is data. Its text is read by this script, checked line by line and put in line; the
simulator never opens a file itself.
"""
import argparse
import csv
import ctypes
import hashlib
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import hwcommon  # noqa: E402
import kicad_env  # noqa: E402

MODEL_COLUMNS = ("mpn", "model_file", "model_name", "kind", "pin_order", "source", "fetched", "sha256",
                 "licence", "checked", "evidence")
SCENARIO_COLUMNS = ("id", "scenario", "corner", "setup", "measure", "limit_low", "limit_high", "source")
RESULT_COLUMNS = ("id", "scenario", "corner", "measure", "value", "limit_low", "limit_high", "result", "source")
KINDS = ("maker", "stand-in")
MODELS_DIR = "sim/models"
MODEL_TABLE = "design/sim-models.csv"

# Commands. Outside a command block a line is a model, a subcircuit, an element or a dot card, so
# the cards that open a command block, run a program, or read or write a file are refused.
COMMAND_RE = re.compile(r"^\s*\.(control|endc|exec|shell|system|source|load|write|codemodel|cd|setcs|osdi|hdl|"
                        r"pre_\w*)\b", re.IGNORECASE)
# Analyses and output cards: allowed in a scenario's setup, refused in a model file.
ANALYSIS_RE = re.compile(r"^\s*\.(tran|ac|dc|op|noise|tf|pz|disto|sens|four|print|plot|probe|save|meas|measure)\b",
                         re.IGNORECASE)
RUNNABLE_RE = re.compile(r"^\s*\.(tran|dc|op)\b", re.IGNORECASE)
INCLUDE_RE = re.compile(r"^\s*\.(include|inc|lib)\s+(.*)$", re.IGNORECASE)
ENGINE_FAULT_RE = re.compile(r"error|aborted|singular|too small|no such|unknown|fatal", re.IGNORECASE)


class SpiceError(Exception):
    """The command cannot go on. The message names the file and the row or line."""


# ---------------------------------------------------------------- numbers

SUFFIX = (("meg", 1e6), ("mil", 25.4e-6), ("t", 1e12), ("g", 1e9), ("k", 1e3), ("m", 1e-3), ("u", 1e-6),
          ("n", 1e-9), ("p", 1e-12), ("f", 1e-15))
NUMBER_RE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)([a-z]*)$", re.IGNORECASE)


def number(text):
    """A number as the simulator reads it: 2.5, 1e-3, 10k, 4.7u, 1meg. Letters after the suffix are
    a unit and are ignored (10kohm, 5v). Raises ValueError."""
    m = NUMBER_RE.match((text or "").strip())
    if not m:
        raise ValueError("not a number: %r" % text)
    value, tail = float(m.group(1)), m.group(2).lower()
    for name, mult in SUFFIX:
        if tail.startswith(name):
            return value * mult
    return value


PART_MULT = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3,
             "M": 1e6, "G": 1e9, "R": 1.0}


def part_value(text):
    """A schematic value as KiCad writes it, in base units: 100k, 1k65, 4u7 100V, 2M (mega), 4R7,
    330. Only the first word counts. Raises ValueError."""
    word = (text or "").split()[0] if (text or "").split() else ""
    word = word.replace("Ω", "").replace("Ω", "")
    for i, ch in enumerate(word):
        if ch in PART_MULT:
            a, b = word[:i], word[i + 1:]
            if b and not b.isdigit():
                b = re.sub(r"[A-Za-z]+$", "", b)          # a unit after the suffix: 100nF, 10kR
                if b and not b.isdigit():
                    raise ValueError("value not understood: %r" % text)
            try:
                return float((a or "0") + ("." + b if b else "")) * PART_MULT[ch]
            except ValueError:
                raise ValueError("value not understood: %r" % text)
    try:
        return float(re.sub(r"[A-Za-z]+$", "", word))
    except ValueError:
        raise ValueError("value not understood: %r" % text)


def fmt(x):
    return "%.9g" % x


# ---------------------------------------------------------------- the library

def find_library():
    """(library file, folder of code models or None). Raises SpiceError when the library is not found."""
    own = os.environ.get("KICAD_NGSPICE")
    if own:
        if not os.path.isfile(own):
            raise SpiceError("simulator library not found: KICAD_NGSPICE is set to %r, which is not a file." % own)
        lib, tried = own, []
    else:
        cli = kicad_env.find_kicad_cli()
        tried = []
        if cli:
            top = os.path.dirname(os.path.dirname(os.path.realpath(cli)))
            if sys.platform == "darwin":
                tried = [os.path.join(top, "PlugIns", "sim", "libngspice.0.dylib"),
                         os.path.join(top, "Frameworks", "libngspice.0.dylib")]
            elif sys.platform == "win32":
                tried = [os.path.join(top, "bin", "libngspice-0.dll")]
        if sys.platform not in ("darwin", "win32"):
            tried += [os.path.join(d, "libngspice.so.0") for d in
                      ("/usr/lib", "/usr/lib64", "/usr/lib/x86_64-linux-gnu", "/usr/lib/aarch64-linux-gnu",
                       "/usr/local/lib")]
        lib = next((p for p in tried if os.path.isfile(p)), None)
        if not lib:
            raise SpiceError(
                "simulator library not found. %s\nLooked for: %s\n"
                "Set KICAD_NGSPICE to the library file inside the KiCad the project uses. "
                "Do not install a simulator to get round this: stop and report."
                % ("kicad-cli was found at %s." % cli if cli else "KiCad itself was not found (kicad_env.py).",
                   ", ".join(tried) or "nothing, as KiCad was not found"))
    cm = os.environ.get("KICAD_NGSPICE_CM")
    if cm and not os.path.isdir(cm):
        raise SpiceError("KICAD_NGSPICE_CM is set to %r, which is not a folder." % cm)
    if not cm:
        d = os.path.dirname(lib)
        near = [os.path.join(d, "ngspice"), os.path.join(os.path.dirname(d), "PlugIns", "sim", "ngspice"),
                os.path.join(os.path.dirname(d), "lib", "ngspice")]
        cm = next((p for p in near if os.path.isdir(p) and any(n.endswith(".cm") for n in os.listdir(p))), None)
    return lib, cm


class VectorInfo(ctypes.Structure):
    _fields_ = [("v_name", ctypes.c_char_p), ("v_type", ctypes.c_int), ("v_flags", ctypes.c_short),
                ("v_realdata", ctypes.POINTER(ctypes.c_double)), ("v_compdata", ctypes.c_void_p),
                ("v_length", ctypes.c_int)]


SEND_CHAR = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
SEND_STAT = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
CONTROLLED_EXIT = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool, ctypes.c_int,
                                   ctypes.c_void_p)
BG_RUNNING = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)


class Engine:
    """The loaded library. One per process: the library keeps its state in the process."""

    def __init__(self, lib=None, codemodels=None, compat=None):
        if lib is None:
            lib, codemodels = find_library()
        self.path, self.codemodels, self.compat = lib, codemodels, compat
        self.log, self.exited = [], None
        try:
            self.lib = ctypes.CDLL(lib)
        except OSError as e:
            raise SpiceError("simulator library %s did not load: %s" % (lib, e))
        self.lib.ngSpice_Init.restype = ctypes.c_int
        self.lib.ngSpice_Command.argtypes = [ctypes.c_char_p]
        self.lib.ngSpice_Circ.argtypes = [ctypes.POINTER(ctypes.c_char_p)]
        self.lib.ngSpice_CurPlot.restype = ctypes.c_char_p
        self.lib.ngSpice_AllVecs.argtypes = [ctypes.c_char_p]
        self.lib.ngSpice_AllVecs.restype = ctypes.POINTER(ctypes.c_char_p)
        self.lib.ngGet_Vec_Info.argtypes = [ctypes.c_char_p]
        self.lib.ngGet_Vec_Info.restype = ctypes.POINTER(VectorInfo)
        # The callbacks stay referenced for the life of the engine. No data callback is given: it
        # needs the init-data callback as well, and vectors are read after the run instead.
        self._cb = (SEND_CHAR(self._char), SEND_STAT(self._stat), CONTROLLED_EXIT(self._exit), BG_RUNNING(self._bg))
        # The "no init file" call is not made: made before start-up, it crashed the library. The
        # library may therefore read an init file of its own; init_files() names the ones in reach.
        rc = self.lib.ngSpice_Init(self._cb[0], self._cb[1], self._cb[2], None, None, self._cb[3], None)
        if rc != 0:
            raise SpiceError("simulator library %s did not start (code %d)" % (lib, rc))
        self.command("set nomoremode")
        if compat:
            if not re.match(r"^[a-z0-9]+$", compat):
                raise SpiceError("--compat %r: letters and digits only" % compat)
            self.command("set ngbehavior=%s" % compat)
        for name in sorted(os.listdir(codemodels)) if codemodels else []:
            if name.endswith(".cm"):
                self.command("codemodel %s" % os.path.join(codemodels, name))

    def _char(self, text, ident, user):
        self.log.append((text or b"").decode("utf-8", "replace"))
        return 0

    def _stat(self, text, ident, user):
        return 0

    def _exit(self, status, unload, quit_, ident, user):
        self.exited = status
        return 0

    def _bg(self, running, ident, user):
        return 0

    def command(self, text):
        rc = self.lib.ngSpice_Command(text.encode())
        if self.exited is not None:
            raise SpiceError("the simulator asked to exit (status %s) after: %s" % (self.exited, text))
        return rc

    def version(self):
        n = len(self.log)
        self.command("version -f")
        lines = [x.replace("stdout", "").strip(" *") for x in self.log[n:]]
        keep = [x for x in lines if re.search(r"ngspice-\d|creation date", x, re.IGNORECASE)]
        return " / ".join(keep) or "unknown"

    def faults(self, since):
        return [x.replace("stderr", "").replace("stdout", "").strip() for x in self.log[since:]
                if ENGINE_FAULT_RE.search(x)]

    def load(self, lines):
        """Give the simulator a whole circuit as lines. The first line is the title."""
        self.command("destroy all")
        n = len(self.log)
        arr = (ctypes.c_char_p * (len(lines) + 1))(*([x.encode("utf-8") for x in lines] + [None]))
        rc = self.lib.ngSpice_Circ(arr)
        bad = self.faults(n)
        if rc != 0 or bad:
            raise SpiceError("circuit not loaded: %s" % (" | ".join(bad[:6]) or "code %d" % rc))

    def run(self):
        n = len(self.log)
        self.command("run")
        bad = self.faults(n)
        if bad:
            raise SpiceError("run failed: %s" % " | ".join(bad[:6]))

    def vectors(self):
        """{name: [numbers]} for every real vector of the last run, names in lower case."""
        plot = self.lib.ngSpice_CurPlot()
        names, i = [], 0
        allv = self.lib.ngSpice_AllVecs(plot)
        while allv and allv[i]:
            names.append(allv[i].decode())
            i += 1
        out = {}
        for name in names:
            p = self.lib.ngGet_Vec_Info(("%s.%s" % (plot.decode(), name)).encode())
            if p and p.contents.v_realdata:
                v = p.contents
                out[name.lower()] = [v.v_realdata[k] for k in range(v.v_length)]
        if not out:
            raise SpiceError("the run gave no vectors")
        return out


def init_files():
    """Init files the library would read on this machine, in the home and current folders."""
    places = [os.path.join(os.path.expanduser("~"), ".spiceinit"), os.path.join(os.getcwd(), ".spiceinit")]
    return [p for p in places if os.path.isfile(p)]


def print_engine(e):
    print("simulator library: %s" % e.path)
    print("version: %s" % e.version())
    print("code models: %s" % (e.codemodels or "none found (parts that need them will not load)"))
    for p in init_files():
        print("note: the library reads the init file %s; results may differ on a machine without it" % p)


# ---------------------------------------------------------------- model files are data

def sha256_text_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def inside(path, folder):
    a, b = os.path.realpath(path), os.path.realpath(folder)
    return a == b or a.startswith(b + os.sep)


def include_target(rest):
    """(file, section) of an include line's arguments, or (None, None) for a ".lib <name>" line that
    only starts a section inside the same file."""
    args = re.findall(r'"[^"]*"|\'[^\']*\'|\S+', rest.strip())
    if not args:
        return None, None
    first = args[0].strip("\"'")
    section = args[1].strip("\"'") if len(args) > 1 else ""
    return first, section


def checked_lines(lines, label, root, model_file=True, seen=None, depth=0):
    """The lines, with each allowed include put in line, or SpiceError naming the refused line.

    label names the text in messages. Includes are read against sim/models/ of the project root and
    must stay inside it. In a model file an analysis or output card is refused too, and a line
    ".end" is left out, as it would end the whole circuit."""
    models = os.path.join(root, *MODELS_DIR.split("/"))
    seen = seen if seen is not None else set()
    out = []
    for n, line in enumerate(lines, 1):
        where = "%s line %d" % (label, n)
        if any(ord(c) < 9 or 13 < ord(c) < 32 or ord(c) == 127 for c in line):
            raise SpiceError("%s: refused, a control character" % where)
        if COMMAND_RE.match(line):
            raise SpiceError("%s: refused, a simulator command or shell call: %s" % (where, line.strip()[:60]))
        if model_file and ANALYSIS_RE.match(line):
            raise SpiceError("%s: refused, an analysis or output line in a model file: %s" % (where, line.strip()[:60]))
        m = INCLUDE_RE.match(line)
        if m:
            name, section = include_target(m.group(2))
            is_section_start = (m.group(1).lower() == "lib" and not section and name is not None
                                and not re.search(r"[./\\]", name))
            if name is None:
                raise SpiceError("%s: refused, an include with no file" % where)
            if not is_section_start:
                rel = name.replace("\\", "/")
                rel = rel[len(MODELS_DIR) + 1:] if rel.startswith(MODELS_DIR + "/") else rel
                path = os.path.join(models, *rel.split("/"))
                if os.path.isabs(name) or not inside(path, models):
                    raise SpiceError("%s: refused, an include of a file outside %s/: %s" % (where, MODELS_DIR, name))
                if not os.path.isfile(path):
                    raise SpiceError("%s: the included file %s/%s is not there" % (where, MODELS_DIR, rel))
                real = os.path.realpath(path)
                if real in seen or depth > 8:
                    raise SpiceError("%s: refused, includes go round in a loop: %s" % (where, name))
                body = checked_lines(read_lines(path), "%s/%s" % (MODELS_DIR, rel), root, True, seen | {real},
                                     depth + 1)
                if section:
                    body = lib_section(body, section, "%s/%s" % (MODELS_DIR, rel))
                out.append("* begin %s/%s" % (MODELS_DIR, rel))
                out += body
                out.append("* end %s/%s" % (MODELS_DIR, rel))
                continue
        if model_file and line.strip().lower() == ".end":
            continue
        out.append(line)
    return out


def lib_section(lines, name, label):
    out, on = [], False
    for x in lines:
        t = x.strip().lower().split()
        if t[:1] == [".lib"] and len(t) == 2 and t[1] == name.lower():
            on = True
            continue
        if t[:1] == [".endl"]:
            on = False
            continue
        if on:
            out.append(x)
    if not out:
        raise SpiceError("%s: section %s not found" % (label, name))
    return out


def read_lines(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read().splitlines()


def joined(lines):
    """Logical lines: each "+" continuation line joined to the line before it, comments dropped."""
    out = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("*"):
            continue
        if s.startswith("+") and out:
            out[-1] += " " + s[1:].strip()
        else:
            out.append(s)
    return out


def find_model(lines, name):
    """("subckt", number of pins) or ("model", element letter) for the model name in the lines; None
    when the name is not defined there."""
    want = name.lower()
    for s in joined(lines):
        t = s.split()
        if len(t) >= 2 and t[0].lower() == ".subckt" and t[1].lower() == want:
            pins = []
            for x in t[2:]:
                if "=" in x or x.lower().rstrip(":") in ("params", "optional", "text"):
                    break
                pins.append(x)
            return "subckt", len(pins)
        if len(t) >= 3 and t[0].lower() == ".model" and t[1].lower() == want:
            kind = re.split(r"[\s(]", t[2].lower())[0]
            letter = {"d": "D", "npn": "Q", "pnp": "Q", "nmos": "M", "pmos": "M", "vdmos": "M", "njf": "J",
                      "pjf": "J"}.get(kind)
            return "model", letter or "?" + kind
    return None


# ---------------------------------------------------------------- the model table

def read_csv(path, columns, label):
    """Rows of a table whose header must be exactly the columns given. Each row carries "_line"."""
    if not os.path.isfile(path):
        raise SpiceError("%s is not there" % label)
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    if not rows or tuple(c.strip() for c in rows[0]) != tuple(columns):
        raise SpiceError("%s: the header must be exactly: %s" % (label, ",".join(columns)))
    out = []
    for n, r in enumerate(rows[1:], 2):
        if not any(c.strip() for c in r):
            continue
        if len(r) != len(columns):
            raise SpiceError("%s line %d: %d fields, expected %d" % (label, n, len(r), len(columns)))
        row = dict((c, v.strip()) for c, v in zip(columns, r))
        row["_line"] = n
        out.append(row)
    return out


def read_models(root):
    return read_csv(os.path.join(root, *MODEL_TABLE.split("/")), MODEL_COLUMNS, MODEL_TABLE)


def model_path(root, row):
    """The model file of a row, or SpiceError when the row does not name a file in sim/models/."""
    where = "%s line %d (%s)" % (MODEL_TABLE, row["_line"], row["mpn"] or "no mpn")
    rel = row["model_file"].replace("\\", "/")
    if not rel:
        raise SpiceError("%s: model_file is empty" % where)
    path = os.path.join(root, *rel.split("/"))
    models = os.path.join(root, *MODELS_DIR.split("/"))
    if os.path.isabs(rel) or not rel.startswith(MODELS_DIR + "/") or not inside(path, models):
        raise SpiceError("%s: model_file %s is not under %s/" % (where, rel, MODELS_DIR))
    if not os.path.isfile(path):
        raise SpiceError("%s: model file %s is not there" % (where, rel))
    return path


def pin_groups(row):
    """pin_order as a list of pin lists. "|" separates the units of a part whose model is one unit."""
    return [[p.strip() for p in g.split(";") if p.strip()] for g in row["pin_order"].split("|") if g.strip()]


def model_row(root, row):
    """Check one row of the model table and return (checked lines of the model, what find_model gave).
    Raises SpiceError with the first fault."""
    where = "%s line %d (%s)" % (MODEL_TABLE, row["_line"], row["mpn"] or "no mpn")
    for col in ("mpn", "model_file", "model_name", "kind", "pin_order", "sha256"):
        if not row[col]:
            raise SpiceError("%s: %s is empty" % (where, col))
    if row["kind"] not in KINDS:
        raise SpiceError("%s: kind %r must be %s" % (where, row["kind"], " or ".join(KINDS)))
    path = model_path(root, row)
    have = sha256_text_file(path)
    if have != row["sha256"].lower():
        raise SpiceError("%s: sha256 of %s is %s, the table says %s. A model is changed only by a script that "
                         "records the change" % (where, row["model_file"], have, row["sha256"]))
    lines = checked_lines(read_lines(path), row["model_file"].replace("\\", "/"), root)
    found = find_model(lines, row["model_name"])
    if not found:
        raise SpiceError("%s: model name %s is not defined in %s" % (where, row["model_name"], row["model_file"]))
    if found[0] == "model" and found[1].startswith("?"):
        raise SpiceError("%s: %s is a model of type %s, which this script cannot place; wrap it in a subcircuit "
                         "by a script that records the change" % (where, row["model_name"], found[1][1:]))
    groups = pin_groups(row)
    if not groups:
        raise SpiceError("%s: pin_order names no pin" % where)
    if found[0] == "subckt":
        for g in groups:
            if len(g) != found[1]:
                raise SpiceError("%s: pin_order has %d pins, the subcircuit %s has %d"
                                 % (where, len(g), row["model_name"], found[1]))
    if row["kind"] == "stand-in" and not any("stand-in" in x.lower() for x in read_lines(path)):
        raise SpiceError("%s: kind is stand-in, but %s does not say \"stand-in\"; name it as a stand-in in the "
                         "file and state what it leaves out" % (where, row["model_file"]))
    return lines, found


def models_by_mpn(root):
    rows, by = read_models(root), {}
    for r in rows:
        if r["mpn"] in by:
            raise SpiceError("%s line %d: a second row for %s (first on line %d)"
                             % (MODEL_TABLE, r["_line"], r["mpn"], by[r["mpn"]]["_line"]))
        by[r["mpn"]] = r
    return rows, by


# ---------------------------------------------------------------- circuit file from the netlist

def read_module_netlist(path):
    """(components, nets) as hwcommon.read_netlist gives them, each component with "sheetname" and
    "sheetfile" added."""
    comps, nets = hwcommon.read_netlist(path)
    for c in comps.values():
        c["sheetname"] = c["properties"].get("Sheetname", "")
        c["sheetfile"] = c["properties"].get("Sheetfile", "")
    return comps, nets


def module_sheet(root, module):
    """The sheet file design/modules.csv gives for the module, or "" when there is no such row."""
    path = os.path.join(root, "design", "modules.csv")
    if not os.path.isfile(path):
        return ""
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if (r.get("module") or "").strip() == module:
                return os.path.basename((r.get("sheet") or "").strip())
    return ""


def node_name(net):
    return re.sub(r"[^A-Za-z0-9_+\-./]", "_", net)


def rel_path(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def build_circuit(root, net_path, module, ground="GND"):
    """(lines of the circuit file, notes to print). Raises SpiceError."""
    if not os.path.isfile(net_path):
        raise SpiceError("netlist %s is not there; export it with the build first" % rel_path(root, net_path))
    comps, nets = read_module_netlist(net_path)
    sheet = module_sheet(root, module)
    mine = sorted((ref for ref, c in comps.items()
                   if (sheet and os.path.basename(c["sheetfile"]) == sheet)
                   or (not sheet and c["sheetname"].lower() == module.lower())), key=hwcommon.ref_key)
    if not mine:
        raise SpiceError("no part of %s is on the sheet of module %s (%s)" % (
            rel_path(root, net_path), module,
            "sheet file %s from design/modules.csv" % sheet if sheet else "no row in design/modules.csv, so the "
            "sheet name was compared"))
    pins = {}
    for net, nodes in nets.items():
        for ref, pin, _fn, _type in nodes:
            pins.setdefault(ref, {})[pin] = net
    rows, by = models_by_mpn(root)
    notes, elements, used_files, missing, node_of = [], [], [], [], {}
    used_nets = set()

    def node(net):
        used_nets.add(net)
        return "0" if net == ground else node_name(net)

    for ref in mine:
        c = comps[ref]
        if "dnp" in c["properties"]:
            notes.append("%s: not fitted, left out" % ref)
            continue
        mpn = c["fields"].get("MPN", "").strip()
        row = by.get(mpn) if mpn else by.get(c["value"])
        prefix = re.match(r"[A-Za-z]*", ref).group(0).upper()
        if row is None and prefix in ("R", "C", "L"):
            try:
                value = part_value(c["value"])
            except ValueError:
                raise SpiceError("%s: value %r is not a plain number; give the part a row in %s"
                                 % (ref, c["value"], MODEL_TABLE))
            have = pins.get(ref, {})
            if sorted(have) != ["1", "2"]:
                raise SpiceError("%s: a plain %s needs pins 1 and 2, the netlist has %s; give the part a row in %s"
                                 % (ref, prefix, ", ".join(sorted(have)) or "none", MODEL_TABLE))
            elements.append("%s %s %s %s" % (ref, node(have["1"]), node(have["2"]), fmt(value)))
            continue
        if row is None:
            missing.append("%s (%s)" % (ref, mpn or "no MPN field, value %s" % c["value"]))
            continue
        lines, found = model_row(root, row)
        if row["model_file"] not in [f for f, _ in used_files]:
            used_files.append((row["model_file"], lines))
        have = pins.get(ref, {})
        groups = pin_groups(row)
        for k, group in enumerate(groups, 1):
            bad = [p for p in group if p not in have]
            if bad:
                raise SpiceError("%s: pin_order of %s names pin %s, which %s does not have in the netlist (it has %s)"
                                 % (ref, row["mpn"], ", ".join(bad), ref, ", ".join(sorted(have)) or "none"))
            letter = "X" if found[0] == "subckt" else found[1]
            name = "%s%s%s" % (letter, ref, "_%d" % k if len(groups) > 1 else "")
            elements.append("%s %s %s" % (name, " ".join(node(have[p]) for p in group), row["model_name"]))
        left = sorted(set(have) - set(p for g in groups for p in g))
        if left:
            notes.append("%s: pins not in the model: %s" % (ref, ", ".join(left)))
    if missing:
        raise SpiceError("no row in %s for: %s\nAdd the row; never work round it." % (MODEL_TABLE, "; ".join(missing)))
    if not elements:
        raise SpiceError("module %s has no fitted part to simulate" % module)
    if ground not in used_nets:
        raise SpiceError("no part of module %s is on the net %s; name the module's reference net with --ground"
                         % (module, ground))
    for net in sorted(used_nets):
        n = node(net).lower()
        if n in node_of and node_of[n] != net:
            raise SpiceError("nets %s and %s would both become the node %s" % (node_of[n], net, n))
        node_of[n] = net
    edge = sorted(node(net) for net in used_nets
                  if net != ground and any(ref not in mine for ref, _p, _f, _t in nets[net]))
    out = ["* %s: circuit file written by spice.py netlist. Never edit it by hand; generate it again." % module,
           "* netlist: %s sha256 %s" % (rel_path(root, net_path), sha256_text_file(net_path)),
           "* model table: %s sha256 %s" % (MODEL_TABLE, sha256_text_file(os.path.join(root, *MODEL_TABLE.split("/")))),
           "* ground: %s" % ground,
           "* edge nodes (nets that join parts on other sheets): %s" % (" ".join(edge) or "none")]
    out += ["* note: %s" % n for n in notes]
    out += elements
    for name, lines in sorted(used_files):
        out.append("* begin model file %s" % name.replace("\\", "/"))
        out += lines
        out.append("* end model file %s" % name.replace("\\", "/"))
    out.append(".end")
    return out, notes + ["edge nodes: %s" % (" ".join(edge) or "none")]


def circuit_path(root, module):
    return os.path.join(root, "sim", module, module + ".cir")


def write_lines(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------- measurements and limits

def vector_name(text):
    t = text.strip().lower()
    m = re.match(r"^v\((.+)\)$", t)
    if m:
        return m.group(1).strip()
    m = re.match(r"^i\((.+)\)$", t)
    if m:
        return m.group(1).strip() + "#branch"
    return t


def axis_of(vecs):
    if "time" in vecs:
        return vecs["time"]
    for name in sorted(vecs):
        if name.endswith("-sweep"):
            return vecs[name]
    return None


def interp(xs, ys, x):
    if x <= xs[0]:
        return ys[0]
    for k in range(1, len(xs)):
        if xs[k] >= x:
            span = xs[k] - xs[k - 1]
            return ys[k] if span == 0 else ys[k - 1] + (x - xs[k - 1]) / span * (ys[k] - ys[k - 1])
    return ys[-1]


def window(xs, ys, a, b):
    """The points between a and b, with the two ends found between points."""
    a = xs[0] if a is None else max(a, xs[0])
    b = xs[-1] if b is None else min(b, xs[-1])
    if b < a:
        raise ValueError("the window from %s to %s holds no point" % (fmt(a), fmt(b)))
    keep = [(x, y) for x, y in zip(xs, ys) if a < x < b]
    pts = [(a, interp(xs, ys, a))] + keep + ([(b, interp(xs, ys, b))] if b > a else [])
    return [p[0] for p in pts], [p[1] for p in pts]


def measure(vecs, text):
    """The number a measure cell asks for, from the vectors of a run. Raises ValueError."""
    words = text.split()
    scale = 1.0
    if len(words) >= 2 and words[-2].lower() == "scale":
        scale, words = number(words[-1]), words[:-2]
    if len(words) < 2:
        raise ValueError("measure %r not understood" % text)
    fn, name = words[0].lower(), vector_name(words[1])
    if name not in vecs:
        raise ValueError("no vector %s in the run (it has: %s)" % (name, ", ".join(sorted(vecs))))
    ys, rest = vecs[name], [w.lower() for w in words[2:]]
    xs = axis_of(vecs)
    if xs is None or len(xs) != len(ys):
        xs = [float(k) for k in range(len(ys))]

    def option(key):
        if key in rest:
            i = rest.index(key)
            if i + 1 >= len(rest):
                raise ValueError("measure %r: %s needs a number" % (text, key))
            v = number(rest[i + 1])
            del rest[i:i + 2]
            return v
        return None

    if fn in ("final", "first"):
        value = ys[-1] if fn == "final" else ys[0]
    elif fn == "value":
        x = option("at")
        if x is None:
            raise ValueError("measure %r: value needs \"at <x>\"" % text)
        if not xs[0] <= x <= xs[-1]:
            raise ValueError("measure %r: %s is outside the run (%s to %s)" % (text, fmt(x), fmt(xs[0]), fmt(xs[-1])))
        value = interp(xs, ys, x)
    elif fn in ("min", "max", "avg", "rms", "pp"):
        wx, wy = window(xs, ys, option("from"), option("to"))
        if fn == "min":
            value = min(wy)
        elif fn == "max":
            value = max(wy)
        elif fn == "pp":
            value = max(wy) - min(wy)
        else:
            sq = [y * y for y in wy] if fn == "rms" else wy
            span = wx[-1] - wx[0]
            if span > 0:
                area = sum((wx[k] - wx[k - 1]) * (sq[k] + sq[k - 1]) / 2.0 for k in range(1, len(wx)))
                value = area / span
            else:
                value = sum(sq) / len(sq)
            value = math.sqrt(value) if fn == "rms" else value
    elif fn == "cross":
        if len(rest) < 2 or rest[1] not in ("rise", "fall"):
            raise ValueError("measure %r: cross needs a level and rise or fall" % text)
        level, way = number(rest[0]), rest[1]
        del rest[:2]
        start = option("from")
        value = None
        for k in range(1, len(xs)):
            if start is not None and xs[k] < start:
                continue
            a, b = ys[k - 1], ys[k]
            if (way == "rise" and a < level <= b) or (way == "fall" and a > level >= b):
                value = xs[k - 1] + (level - a) / (b - a) * (xs[k] - xs[k - 1])
                break
        if value is None:
            raise ValueError("measure %r: no such crossing in the run" % text)
    else:
        raise ValueError("measure %r: %s is not a measure this script knows" % (text, fn))
    if rest:
        raise ValueError("measure %r: %s not understood" % (text, " ".join(rest)))
    return value * scale


def judge(value, low, high, source):
    """"pass", "fail", "no source" (limits with no source: not a pass limit) or "no limit"."""
    lo = number(low) if (low or "").strip() else None
    hi = number(high) if (high or "").strip() else None
    if lo is None and hi is None:
        return "no limit"
    if not (source or "").strip():
        return "no source"
    if value != value:
        return "fail"
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        return "fail"
    return "pass"


# ---------------------------------------------------------------- scenarios

def safe_name(text):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", text)


def read_scenarios(path, label):
    rows, seen = read_csv(path, SCENARIO_COLUMNS, label), {}
    if not rows:
        raise SpiceError("%s holds no row" % label)
    for r in rows:
        where = "%s line %d" % (label, r["_line"])
        if not r["id"] or not r["setup"] or not r["measure"]:
            raise SpiceError("%s: id, setup and measure must be filled" % where)
        key = safe_name("%s_%s" % (r["id"], r["corner"]) if r["corner"] else r["id"]).lower()
        if key in seen:
            raise SpiceError("%s: a second row for %s %s (first on line %d); one row per scenario and corner"
                             % (where, r["id"], r["corner"], seen[key]))
        seen[key] = r["_line"]
        for col in ("limit_low", "limit_high"):
            if r[col]:
                try:
                    number(r[col])
                except ValueError:
                    raise SpiceError("%s: %s %r is not a number" % (where, col, r[col]))
    return rows


def setup_lines(row, label, root):
    where = "%s line %d (%s) setup" % (label, row["_line"], row["id"])
    raw = [x.strip() for x in row["setup"].split(";") if x.strip()]
    lines = checked_lines(raw, where, root, model_file=False)
    runs = [x for x in lines if RUNNABLE_RE.match(x)]
    if len(runs) != 1:
        raise SpiceError("%s: needs exactly one analysis line (.op, .tran or .dc), found %d" % (where, len(runs)))
    if any(x.strip().lower() == ".end" for x in lines):
        raise SpiceError("%s: refused, a line .end" % where)
    return lines


def run_rows(engine, base, rows, label, root):
    """Run each row on the base circuit lines. Returns [(row, value or None, result, message, vectors)]."""
    out = []
    for r in rows:
        deck = list(base) + setup_lines(r, label, root) + [".end"]
        value, vecs, message = None, None, ""
        try:
            engine.load(deck)
            engine.run()
            vecs = engine.vectors()
            value = measure(vecs, r["measure"])
            result = judge(value, r["limit_low"], r["limit_high"], r["source"])
        except (SpiceError, ValueError) as e:
            result, message = "error", str(e)
        out.append((r, value, result, message, vecs))
    return out


def result_table(done):
    lines = [",".join(RESULT_COLUMNS)]
    for r, value, result, _msg, _v in done:
        cells = [r["id"], r["scenario"], r["corner"], r["measure"], "" if value is None else fmt(value),
                 r["limit_low"], r["limit_high"], result, r["source"]]
        lines.append(",".join('"%s"' % c.replace('"', '""') if re.search(r'[",\n]', c) else c for c in cells))
    return lines


def waveform(vecs):
    names = (["time"] if "time" in vecs else []) + sorted(n for n in vecs if n != "time")
    n = max(len(vecs[x]) for x in names)
    lines = [",".join('"%s"' % x if "," in x else x for x in names)]
    for k in range(n):
        lines.append(",".join(fmt(vecs[x][k]) if k < len(vecs[x]) else "" for x in names))
    return lines


def print_rows(done):
    bad = 0
    for r, value, result, message, _v in done:
        what = "%s %s" % (r["id"], r["corner"]) if r["corner"] else r["id"]
        print("%-10s %s: %s = %s, limits %s to %s (%s)%s" % (
            result, what, r["measure"], "none" if value is None else fmt(value), r["limit_low"] or "none",
            r["limit_high"] or "none", r["source"] or "no source", ": " + message if message else ""))
        bad += result in ("fail", "error", "no source")
    counts = {}
    for _r, _v, result, _m, _vecs in done:
        counts[result] = counts.get(result, 0) + 1
    print("%d rows: %s" % (len(done), ", ".join("%d %s" % (counts[k], k) for k in sorted(counts))))
    if counts.get("no source"):
        print("A limit with no source is not a pass limit: give each its FR-, QC- or DS- ID or its calculation.")
    if counts.get("no limit"):
        print("Rows with no limit are measured only; they are not passes.")
    return bad


def base_lines(lines):
    """A circuit file's lines without its closing .end, so a setup can follow."""
    return [x for x in lines if x.strip().lower() != ".end"]


# ---------------------------------------------------------------- commands

ENGINE_CASES = [
    ("divider: 12 V across 10k over 2k (.op)",
     ["* divider", "V1 in 0 12", "R1 in mid 10k", "R2 mid 0 2k", ".op", ".end"],
     [("final v(mid)", 2.0, 1e-6, "12 x 2 / 12 = 2 V"),
      ("final i(v1)", -1e-3, 1e-9, "12 / 12k = 1 mA, into the + terminal")]),
    ("RC step: 5 V into 1k and 1 uF, tau 1 ms (.tran)",
     ["* rc step", "V1 in 0 PULSE(0 5 0 1n 1n 1 2)", "R1 in c 1k", "C1 c 0 1u IC=0", ".tran 1u 5m 0 1u uic",
      ".end"],
     [("value v(c) at 1m", 5 * (1 - math.exp(-1)), 2e-3, "5 (1 - 1/e) V at one tau"),
      ("value v(c) at 5m", 5 * (1 - math.exp(-5)), 2e-3, "5 (1 - e^-5) V at five tau")]),
    ("temperature: 1 mA in 1k with 1000 ppm/K at 75 C, nominal set to 25 C (.op)",
     ["* temperature", "I1 0 a 1m", "R1 a 0 1k tc1=1e-3", ".temp 75", ".options tnom=25", ".op", ".end"],
     [("final v(a)", 1.05, 1e-6, "1k x (1 + 50 K x 0.001) x 1 mA")]),
    ("temperature: the same, nominal left alone (27 C)",
     ["* temperature", "I1 0 a 1m", "R1 a 0 1k tc1=1e-3", ".temp 75", ".op", ".end"],
     [("final v(a)", 1.048, 1e-6, "1k x (1 + 48 K x 0.001) x 1 mA")]),
]


def cmd_engine_check(a):
    e = Engine(compat=a.compat)
    print_engine(e)
    bad = 0
    for title, deck, checks in ENGINE_CASES:
        print(title)
        try:
            e.load(deck)
            e.run()
            vecs = e.vectors()
        except SpiceError as ex:
            print("  fail  %s" % ex)
            bad += 1
            continue
        for text, hand, tol, how in checks:
            got = measure(vecs, text)
            ok = abs(got - hand) <= tol
            bad += not ok
            print("  %s  %s: simulator %s, by hand %s (%s), tolerance %s"
                  % ("pass" if ok else "fail", text, fmt(got), fmt(hand), how, fmt(tol)))
    print("engine-check: %s" % ("pass" if not bad else "FAIL (%d). Report no simulation result from this machine."
                                % bad))
    return 1 if bad else 0


def project(a):
    try:
        return hwcommon.find_project(a.project, a.name)
    except hwcommon.ProjectError as e:
        raise SpiceError(str(e))


def net_file(a, paths):
    path = os.path.abspath(a.netlist) if a.netlist else paths["net"]
    if not path:
        raise SpiceError("no KiCad project found in %s; pass --netlist" % hwcommon.folder_label(paths["kicad_rel"]))
    return path


def check_module_name(module):
    if not re.match(r"^[A-Za-z0-9_-]+$", module):
        raise SpiceError("module name %r: letters, digits, _ and - only" % module)


def cmd_netlist(a):
    paths = project(a)
    root = paths["root"]
    check_module_name(a.module)
    lines, notes = build_circuit(root, net_file(a, paths), a.module, a.ground)
    out = circuit_path(root, a.module)
    write_lines(out, lines)
    for n in notes:
        print("note: %s" % n)
    print("%s" % lines[1].lstrip("* "))
    print("%s written: %d lines, sha256 %s" % (rel_path(root, out), len(lines), sha256_text_file(out)))
    return 0


def cmd_model_check(a):
    paths = project(a)
    root = paths["root"]
    rows, _by = models_by_mpn(root)
    if not rows:
        raise SpiceError("%s holds no row" % MODEL_TABLE)
    bad, kept = 0, {}
    for r in rows:
        try:
            lines, found = model_row(root, r)
            kept[r["mpn"]] = (r, lines)
            print("pass  %s: %s, %s %s, %s%s" % (r["mpn"], r["model_file"], found[0], r["model_name"], r["kind"],
                                               "" if r["checked"].lower() == "yes"
                                               else "; checked is not yes: list it under Not validated"))
        except SpiceError as e:
            bad += 1
            print("fail  %s" % e)
    print("model table: %d rows, %d failed" % (len(rows), bad))
    if bad:
        print("Do not strip lines from a refused file by hand. Report the file and what was refused, and ask.")
    if not a.mpn and not a.points:
        return 1 if bad else 0
    if not (a.mpn and a.points):
        raise SpiceError("model-check: --mpn and --points go together")
    if a.mpn not in kept:
        raise SpiceError("model-check: %s has no row in %s that passed the checks above" % (a.mpn, MODEL_TABLE))
    points = os.path.abspath(a.points)
    label = rel_path(root, points)
    scen = read_scenarios(points, label)
    e = Engine(compat=a.compat)
    print_engine(e)
    base = ["* model check of %s: the model alone" % a.mpn] + kept[a.mpn][1]
    done = run_rows(e, base, scen, label, root)
    out = os.path.splitext(points)[0] + ".results.csv"
    write_lines(out, result_table(done))
    failed = print_rows(done)
    print("%s written. Compare the figures with the datasheet and fill checked and evidence in %s."
          % (rel_path(root, out), MODEL_TABLE))
    return 1 if (bad or failed) else 0


def cmd_run(a):
    paths = project(a)
    root = paths["root"]
    check_module_name(a.module)
    cir = circuit_path(root, a.module)
    cir_label = rel_path(root, cir)
    if not os.path.isfile(cir):
        raise SpiceError("%s is not there; write it with: spice.py netlist %s" % (cir_label, a.module))
    have = read_lines(cir)
    ground = next((x.split(":", 1)[1].strip() for x in have if x.startswith("* ground:")), "GND")
    now, _notes = build_circuit(root, net_file(a, paths), a.module, ground)
    if have != now:
        k = next((i for i, (x, y) in enumerate(zip(have, now)) if x != y), min(len(have), len(now)))
        raise SpiceError("%s is not what spice.py netlist writes now (first difference on line %d). It was edited "
                         "by hand, or the schematic, a model or the model table changed. Generate it again; "
                         "results from the older file are stale." % (cir_label, k + 1))
    label = "sim/%s/scenarios.csv" % a.module
    scen = read_scenarios(os.path.join(root, "sim", a.module, "scenarios.csv"), label)
    e = Engine(compat=a.compat)
    print_engine(e)
    done = run_rows(e, base_lines(have), scen, label, root)
    files = {"results.csv": result_table(done),
             "run.txt": ["circuit file: %s sha256 %s" % (cir_label, sha256_text_file(cir)),
                         "scenarios: %s sha256 %s" % (label, sha256_text_file(os.path.join(root, "sim", a.module,
                                                                                         "scenarios.csv"))),
                         "simulator: %s" % e.version(),
                         "compatibility mode: %s" % (a.compat or "none")]}
    for r, _value, _result, _msg, vecs in done:
        if vecs:
            files[safe_name("%s_%s" % (r["id"], r["corner"]) if r["corner"] else r["id"]) + ".csv"] = waveform(vecs)
    res = os.path.join(root, "sim", a.module, "results")
    res_label = "sim/%s/results" % a.module
    old = sorted(os.listdir(res)) if os.path.isdir(res) else []
    differ = 0
    if a.again:
        for name in sorted(files):
            p = os.path.join(res, name)
            if not os.path.isfile(p):
                print("differs  %s/%s: not there from the first run" % (res_label, name))
                differ += 1
            elif read_lines(p) != files[name]:
                print("differs  %s/%s: this run gave other numbers" % (res_label, name))
                differ += 1
        print("second run: %d files compared with %s/, %d differ: %s"
              % (len(files), res_label, differ, "the run is not repeatable" if differ else "the same files twice"))
    else:
        for name in sorted(files):
            write_lines(os.path.join(res, name), files[name])
        print("%d files written to %s/" % (len(files), res_label))
    stale = [n for n in old if n not in files and not n.startswith(".")]
    if stale:
        print("stale: files in %s/ that this run did not write: %s" % (res_label, ", ".join(stale)))
    failed = print_rows(done)
    return 1 if (failed or differ) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", default=".", help="project root, or a folder inside it (default: here)")
    common.add_argument("--name", help="project name in the KiCad folder when there are several")
    common.add_argument("--netlist", help="netlist file (default <name>.net in the KiCad folder)")
    common.add_argument("--compat", help="compatibility mode some makers' models need; say so in the report")
    sub.add_parser("engine-check", parents=[common], help="circuits with answers known by hand")
    p = sub.add_parser("netlist", parents=[common], help="write sim/<module>/<module>.cir")
    p.add_argument("module")
    p.add_argument("--ground", default="GND", help="the net that becomes node 0 (default GND)")
    p = sub.add_parser("model-check", parents=[common], help="check the model table and the model files")
    p.add_argument("--mpn", help="also run this one model alone at the points in --points")
    p.add_argument("--points", help="a file with the columns of scenarios.csv")
    p = sub.add_parser("run", parents=[common], help="run sim/<module>/scenarios.csv")
    p.add_argument("module")
    p.add_argument("--again", action="store_true", help="write nothing; compare with the results already there")
    a = ap.parse_args(argv)
    cmds = {"engine-check": cmd_engine_check, "netlist": cmd_netlist, "model-check": cmd_model_check, "run": cmd_run}
    if a.command not in cmds:
        ap.print_usage()
        return 2
    try:
        return cmds[a.command](a)
    except SpiceError as e:
        print("spice.py %s: %s" % (a.command, e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
