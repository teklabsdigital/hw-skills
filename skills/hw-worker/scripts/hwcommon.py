# Copyright 2026 Teklabs Digital (hw-skills)
# SPDX-License-Identifier: Apache-2.0
"""Shared helpers for the hw-worker scripts. Python 3 standard library only.

Holds, once for every script:
  - the project table formats (columns and allowed values of the CSV files in design/),
    the hard-row categories, and the three enforcer forms of constraints.csv;
  - readers for KiCad files: an S-expression reader, the exported netlist, the board file;
  - small file helpers: repeatable text writes, hashes, the decisions log, status.md fields.

Every check reads the KiCad files and kicad-cli output, never a generator's internals.
None of this needs KiCad's Python module (pcbnew). It runs on KiCad's bundled Python too.


"""
import csv
import hashlib
import io
import os
import re
import subprocess

SKILLS_VERSION = "0.2.0"        # the hw-skills version these scripts belong to

# ---------------------------------------------------------------- project tables
# Columns exactly as in the worker's references/project-files.md. Scripts check them.
TABLES = {
    "compliance.csv": ("id", "designator", "mpn", "datasheet", "revision", "section", "page", "figure",
                       "kind", "category", "perspective", "text", "design_value", "margin",
                       "schematic_result", "board_result", "decision", "carried_to", "evidence", "found_by"),
    "sections.csv": ("datasheet", "revision", "section", "title", "pages", "category", "claimed_by",
                     "rows_logical", "rows_electrical", "rows_physical", "note"),
    "pins.csv": ("designator", "mpn", "pin", "name", "functions", "used_function", "net", "supply", "levels",
                 "abs_max", "current_limit", "reset_state", "boot_activity", "control_input",
                 "required_in_reset", "given_by", "sleep_state", "fault_state", "source", "source_page",
                 "confirmed"),
    "parts.csv": ("refs", "value", "footprint", "package", "manufacturer", "mpn", "supplier", "supplier_pn",
                  "role", "category", "dielectric", "tolerance", "voltage_rating", "unit_price", "qty_price",
                  "stock", "checked", "lifecycle", "temp_grade", "msl", "peak_reflow", "alternate", "variant",
                  "datasheet", "datasheet_revision", "errata", "compliance_done", "pins_done", "model",
                  "model_checked"),
    "fab-capabilities.csv": ("item", "manufacturer_value", "source_url", "read_on", "service_level",
                             "rule_value", "note"),
    "constraints.csv": ("id", "from", "kind", "objects", "limit", "enforced_by", "sufficiency",
                        "standard_or_own", "note"),
    "findings.csv": ("id", "report", "severity", "category", "location", "text", "source", "status",
                     "decision"),
    "net-review.csv": ("id", "list", "net_or_pin", "item", "reason", "closed_by", "date"),
    "ownership.csv": ("path", "owner", "writer", "hash", "commit"),
    # The constraints as the sufficiency review saw them (table_check.py constraints --record-review):
    # the baseline a later change of limit or enforcer is compared with, git or not.
    "constraints-reviewed.csv": ("id", "kind", "objects", "limit", "enforced_by", "review", "date"),
    # Scan hits a person looked at and accepted (table_check.py scan).
    "scan-reviewed.csv": ("file", "line", "kind", "reason", "decided_by"),
}

# Allowed values (compliance.csv, sections.csv, parts.csv, findings.csv).
KINDS = ("must", "should", "recommend", "limit", "typical-only", "calculation", "figure", "graph", "errata",
         "typical-application", "data")
# Rows of these categories close later than the schematic checkpoint: package rows when the footprint
# and 3D model are checked against the drawing (the board checkpoint), assembly rows with the order files.
LATE_CATEGORIES = {"package": "ST11", "assembly": "ST12"}
COMPLIANCE_CATEGORIES = ("pin", "absolute-maximum", "operating", "electrical", "timing", "thermal",
                         "protection", "decoupling", "external-component", "configuration", "power-up",
                         "layout", "grounding", "package", "assembly", "errata", "typical-application",
                         "other")
SECTION_CATEGORIES = ("pins", "absolute-maximum", "operating", "electrical", "timing", "thermal",
                      "functional", "configuration", "application", "typical-application", "power-supply",
                      "layout", "grounding", "package", "assembly", "errata", "revision-history",
                      "ordering", "other")
# A section in one of these categories with zero rows needs a note.
SECTIONS_NEEDING_ROWS = ("layout", "grounding", "application", "thermal", "typical-application")
# Hard rows (WR-21): only a DC- decision sets them to "not met" or "does not apply".
# ESD, surge and reverse-polarity ratings are protection; placement, routing, keep-out and via
# rules are layout (references/datasheets.md, Compliance rows).
HARD_CATEGORIES = ("layout", "grounding", "protection", "absolute-maximum")
PERSPECTIVES = ("logical", "electrical", "physical")
SCHEMATIC_RESULTS = ("open", "met", "not met", "does not apply", "carried")
BOARD_RESULTS = ("open", "met", "not met", "does not apply")
FOUND_BY = ("pass", "review", "blind review")
ROLES = ("protection", "decoupling", "bulk", "pull", "connector", "switch", "button", "indicator",
         "regulator", "clock", "interface", "radio", "sensor", "other")
FINDING_CATEGORIES = ("violation", "risk", "question", "improvement", "remark", "extraction miss")
OWNERS = ("script", "hand")
PROPOSED = "proposed"           # a decision the user has not made yet: counts as open

DC_RE = re.compile(r"\bDC-\d{3,}\b")
CN_RE = re.compile(r"\bCN-\d{3,}\b")


def decision_closes(value):
    """True only when the decision field names a DC- decision. "proposed" and empty are open."""
    v = (value or "").strip()
    return bool(DC_RE.fullmatch(v))


def is_hard(row):
    return (row.get("category") or "").strip() in HARD_CATEGORIES


# ---------------------------------------------------------------- constraint enforcers
# enforced_by takes exactly one of three forms:
#   dru:<rule name>                       a rule in the generated rule file
#   check:<board_check sub-command> <CN-> a board check that can fail
#   review:<checklist ID>                 a verdict in every board review
BOARD_CHECKS = ("distance", "same_island", "single_point", "plane_one_piece", "via_count", "keepout",
                "net_length", "noisy_distance", "decouple_per_pin", "edge_distance", "ref_plane",
                "via_in_pad", "artefacts")
BOARD_AIDS = ("copper_area", "loop_area", "node_capacitance")     # numbers only, never an enforcer
ENFORCER_RE = re.compile(
    r"^(?:dru:(?P<rule>\S(?:.*\S)?)"
    r"|check:(?P<check>[a-z_]+) (?P<cn>CN-\d{3,})"
    r"|review:(?P<review>[A-Z]{2,4}-\d{2,}))$")


def parse_enforcer(text):
    """(form, name, constraint ID) for a valid enforced_by value, else None.

    form is "dru", "check" or "review"; name is the rule name, the sub-command or the checklist ID.
    """
    m = ENFORCER_RE.match((text or "").strip())
    if not m:
        return None
    if m.group("rule"):
        return ("dru", m.group("rule"), None)
    if m.group("check"):
        if m.group("check") not in BOARD_CHECKS:
            return None
        return ("check", m.group("check"), m.group("cn"))
    return ("review", m.group("review"), None)


# ---------------------------------------------------------------- CSV tables

class TableError(Exception):
    pass


def read_table(path, name=None):
    """Rows of a project table as dicts. The header must match TABLES[name] exactly.

    name defaults to the file name. A missing file returns []. Raises TableError on a wrong header.
    """
    name = name or os.path.basename(path)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise TableError("%s is empty; it needs the header row" % path)
        want = TABLES.get(name)
        header = [h.strip() for h in header]
        if want and tuple(header) != want:
            missing = [c for c in want if c not in header]
            extra = [c for c in header if c not in want]
            raise TableError("%s: header differs from the template (missing %s, extra %s, or out of order)"
                             % (path, missing or "none", extra or "none"))
        rows = []
        for n, rec in enumerate(reader, 2):
            if not any(x.strip() for x in rec):
                continue
            if len(rec) != len(header):
                cause = ("likely an unquoted comma inside a value: put that value in double quotes"
                         if len(rec) > len(header) else "a field is missing, or a value holds a line break")
                raise TableError("%s line %d: %d fields, the header has %d (%s)" % (path, n, len(rec), len(header),
                                                                                  cause))
            row = dict(zip(header, (x.strip() for x in rec)))
            row["_line"] = n
            rows.append(row)
    return rows


def write_table(path, name, rows):
    """Write a project table with the template header, rows in the order given, \\n line ends."""
    cols = TABLES[name]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get(c, "") for c in cols])
    write_text(path, buf.getvalue())


def split_list(value):
    """A field holding several values separated by ';'."""
    return [v.strip() for v in (value or "").split(";") if v.strip()]


# ---------------------------------------------------------------- files

def write_text(path, text):
    """UTF-8 with \\n line ends on every OS, so the same input gives the same bytes anywhere."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    """Output of a git command in root, or None when git or the repository is not there."""
    try:
        res = subprocess.run(["git", "-C", root] + list(args), capture_output=True)
    except OSError:
        return None
    if res.returncode:
        return None
    return res.stdout


def git_head(root):
    out = git(root, "rev-parse", "--short", "HEAD")
    return out.decode().strip() if out else ""


# ---------------------------------------------------------------- design/ text files

# design/decisions.md, the decision log (references/project-files.md, decisions.md). An entry opens with
# "## <plain statement> (DC-nnn)" and holds one "Field: value" line per field. A line that starts with
# the ID ("DC-nnn <date> ...") is the older one-line form: still read for its ID, and listed by
# table_check.py decisions as needing the log form.
DECISION_HEAD_RE = re.compile(r"^##\s+(?P<title>.*?)\s*\((?P<id>DC-\d+)\)\s*$")
DECISION_OLD_RE = re.compile(r"^(?P<id>DC-\d+)\b(?P<title>.*)$")
DECISION_FIELDS = ("Kind", "Decided by", "Date", "Stage", "Options", "Reason", "Affects", "Status")
DECISION_KINDS = ("decision", "waiver", "pivot", "not done", "question answered")
ANSWERED_KIND = "question answered"     # the lighter entry: nothing chosen, nothing changed
ANSWERED_STATUS = "closed (answered)"
AFFECTS_PARTS = ("requirements", "parts", "schematic", "board", "cost")
DECISION_WHO = ("user", "coordinator", "worker")
DECISION_STATUS = ("in force", "open", "closed", "superseded by")


def decision_entries(design_dir):
    """[{id, title, old, line, fields: {name: value}, text}] from design/decisions.md, in file order
    ([] if the file is missing). `fields` holds the "Name: value" lines of a log-form entry."""
    path = os.path.join(design_dir, "decisions.md")
    if not os.path.isfile(path):
        return []
    entries, cur = [], None
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\n")
            head, old = DECISION_HEAD_RE.match(line), DECISION_OLD_RE.match(line)
            if head or old or line.startswith("## ") or line.startswith("# "):
                cur = None
                m = head or old
                if m:
                    cur = {"id": m.group("id"), "title": m.group("title").strip(), "old": bool(old and not head),
                           "line": n, "fields": {}, "text": line}
                    entries.append(cur)
                continue
            if cur is None:
                continue
            cur["text"] += "\n" + line
            fm = re.match(r"^\s*(?:[-*]\s+)?([A-Z][A-Za-z ]{1,20}):\s*(.*)$", line)
            if fm and not cur["old"]:
                cur["fields"].setdefault(fm.group(1).strip(), fm.group(2).strip())
    return entries


def decision_ids(design_dir):
    """DC- IDs that start an entry in design/decisions.md (empty set if the file is missing)."""
    return set(e["id"] for e in decision_entries(design_dir) if DC_RE.fullmatch(e["id"]))


def check_waivers(waivers, design_dir):
    """Problems with waiver IDs: wrong form, or not in design/decisions.md when that file exists."""
    out = []
    known = decision_ids(design_dir)
    have_log = os.path.isfile(os.path.join(design_dir, "decisions.md"))
    for w in waivers:
        if not DC_RE.fullmatch(w):
            out.append("waiver %r is not a decision ID (DC-nnn)" % w)
        elif have_log and w not in known:
            out.append("waiver %s is not in design/decisions.md; record the decision first" % w)
    return out


def status_lines(design_dir):
    path = os.path.join(design_dir, "status.md")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


EXPECTED_NOTE_RE = re.compile(r'^\s*-\s*"(?P<text>[^"]+)"\s+on\s+(?P<item>.+?),\s*(?P<dc>DC-\d{3,})\s*$')


def expected_drc_notes(design_dir):
    """Expected schematic-parity notes from design/status.md, as (text, item, DC-) tuples.

    Format (references/project-files.md, status.md):
        Expected DRC notes: none
    or
        Expected DRC notes:
          - "<text in the note>" on <item, for example Footprint J1>, DC-nnn
    Returns (notes, errors).
    """
    return expected_list(design_dir, "Expected DRC notes", "DRC note")


def expected_erc_items(design_dir):
    """Expected ERC items from design/status.md, as (text, item, DC-) tuples, in the same form:
        Expected ERC items:
          - "<text in the violation>" on <item, for example Symbol U1 Pin 3>, DC-nnn
    No such line means none. Returns (items, errors)."""
    return expected_list(design_dir, "Expected ERC items", "ERC item")


def expected_list(design_dir, heading, what):
    lines = status_lines(design_dir)
    notes, errors = [], []
    for i, line in enumerate(lines):
        if not line.startswith(heading + ":"):
            continue
        rest = line.split(":", 1)[1].strip()
        if rest and rest.lower() not in ("none", "(one per line below)"):
            errors.append("status.md: put each expected %s on its own '  - ' line below the heading" % what)
        for follow in lines[i + 1:]:
            if not follow.startswith((" ", "\t")) or not follow.strip():
                break
            m = EXPECTED_NOTE_RE.match(follow)
            if m:
                notes.append((m.group("text"), m.group("item").strip(), m.group("dc")))
            else:
                errors.append('status.md: cannot read expected %s %r; write  - "<text>" on <item>, DC-nnn'
                              % (what, follow.strip()))
        break
    return notes, errors


# ---------------------------------------------------------------- S-expressions

class Q(str):
    """A quoted string atom (an unquoted atom is a plain str)."""


_TOKEN_RE = re.compile(r'"(?:[^"\\]|\\.)*"|[()]|[^\s()"]+')


def _unescape(s):
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def parse_sexpr(text):
    """Parse a KiCad S-expression file into nested lists. Quoted atoms come back as Q."""
    stack = [[]]
    for tok in _TOKEN_RE.findall(text):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            if len(stack) < 2:
                raise ValueError("unbalanced ')' in S-expression")
            node = stack.pop()
            stack[-1].append(node)
        elif tok.startswith('"'):
            stack[-1].append(Q(_unescape(tok[1:-1])))
        else:
            stack[-1].append(tok)
    if len(stack) != 1 or len(stack[0]) != 1:
        raise ValueError("unbalanced S-expression")
    return stack[0][0]


def read_sexpr(path):
    with open(path, encoding="utf-8") as f:
        return parse_sexpr(f.read())


def find(node, key):
    """Child lists of node whose first atom is key."""
    return [n for n in node if isinstance(n, list) and n and n[0] == key]


def first(node, key, default=None):
    found = find(node, key)
    return found[0] if found else default


def value(node, key, default=""):
    """The first atom after key in the first child (key ...), for example (layer "F.Cu")."""
    n = first(node, key)
    if n is None or len(n) < 2 or isinstance(n[1], list):
        return default
    return str(n[1])


def num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- netlist (kicad-cli, kicadsexpr)

def read_netlist(path):
    """(components, nets) from a netlist exported by kicad-cli in kicadsexpr form.

    components: ref -> {"value", "footprint", "datasheet", "description", "fields": {name: text}}
    nets: net name -> sorted list of (ref, pin, pinfunction, pintype)
    """
    root = read_sexpr(path)
    comps = {}
    for c in find(first(root, "components", []), "comp"):
        ref = value(c, "ref")
        fields = {}
        for f in find(first(c, "fields", []), "field"):
            name = value(f, "name")
            texts = [str(x) for x in f[1:] if not isinstance(x, list)]
            fields[name] = texts[0] if texts else ""
        props = {value(p, "name"): value(p, "value") for p in find(c, "property")}
        comps[ref] = {"value": value(c, "value"), "footprint": value(c, "footprint"),
                      "datasheet": value(c, "datasheet"), "description": value(c, "description"),
                      "uuid": value(c, "tstamps"), "fields": fields, "properties": props}
    nets = {}
    for n in find(first(root, "nets", []), "net"):
        nodes = [(value(nd, "ref"), value(nd, "pin"), value(nd, "pinfunction"), value(nd, "pintype"))
                 for nd in find(n, "node")]
        nets[value(n, "name")] = sorted(nodes)
    return comps, nets


# ---------------------------------------------------------------- board file (.kicad_pcb)

def _at(node):
    a = first(node, "at")
    if not a:
        return 0.0, 0.0, 0.0
    vals = [num(x) for x in a[1:] if not isinstance(x, list)]
    vals += [0.0] * (3 - len(vals))
    return vals[0], vals[1], vals[2]


def _pad_net(pad):
    n = first(pad, "net")
    if not n:
        return ""
    names = [x for x in n[1:] if isinstance(x, Q)]     # (net "/A") in KiCad 10, (net 1 "/A") before
    return str(names[0]) if names else ""


def read_board(path):
    """A plain summary of a .kicad_pcb, read as text (no pcbnew). See board_summary."""
    return board_summary(read_sexpr(path))


def board_summary(root):
    """Summary of a parsed .kicad_pcb.

    Returns {"version", "copper_layers", "aux_origin", "footprints", "counts", "nets"}.
    Each footprint: ref, value, lib_id, layer, x, y, rot, attrs (set), fields (dict), pads (list of
    number, type, x, y (relative to the footprint), w, h, layers, net, drill).
    """
    layers = first(root, "layers", [])
    copper = [str(l[1]) for l in layers[1:] if isinstance(l, list) and len(l) > 2 and str(l[1]).endswith(".Cu")]
    setup = first(root, "setup", [])
    ao = first(setup, "aux_axis_origin")
    origin = (num(ao[1]), num(ao[2])) if ao else (0.0, 0.0)
    fps = []
    for fp in find(root, "footprint"):
        x, y, rot = _at(fp)
        fields = {}
        for p in find(fp, "property"):
            if len(p) > 2:
                fields[str(p[1])] = str(p[2])
        attr = first(fp, "attr", [])
        attrs = set(str(a) for a in attr[1:] if not isinstance(a, list))
        if value(fp, "dnp") == "yes":
            attrs.add("dnp")
        pads = []
        for pad in find(fp, "pad"):
            px, py, _ = _at(pad)
            size = first(pad, "size", ["size", 0, 0])
            lay = first(pad, "layers", ["layers"])
            drill = first(pad, "drill")
            pads.append({"number": str(pad[1]), "type": str(pad[2]), "shape": str(pad[3]) if len(pad) > 3 else "",
                         "x": px, "y": py, "w": num(size[1]), "h": num(size[2]),
                         "layers": [str(l) for l in lay[1:]], "net": _pad_net(pad),
                         "drill": num(drill[1]) if drill and len(drill) > 1 and not isinstance(drill[1], list)
                         else 0.0})
        fps.append({"ref": fields.get("Reference", ""), "value": fields.get("Value", ""),
                    "lib_id": str(fp[1]) if len(fp) > 1 and not isinstance(fp[1], list) else "",
                    "layer": value(fp, "layer"), "x": x, "y": y, "rot": rot, "attrs": attrs,
                    "fields": fields, "pads": pads})
    nets = set()
    for fp in fps:
        nets.update(p["net"] for p in fp["pads"] if p["net"])
    counts = {k: len(find(root, k)) for k in ("segment", "arc", "via", "zone", "gr_line", "gr_rect")}
    return {"version": value(root, "version"), "copper_layers": copper, "aux_origin": origin,
            "footprints": fps, "counts": counts, "nets": sorted(nets)}


def schematic_summary(root):
    """Summary of a parsed .kicad_sch: symbols by reference, and counts of drawn items.

    Returns {"symbols": {ref: {"lib_id", "x", "y", "rot", "fields"}}, "counts": {...}}.
    Hierarchical sheets keep their own files; this reads one file.
    """
    symbols = {}
    for s in find(root, "symbol"):
        fields = {}
        for p in find(s, "property"):
            if len(p) > 2:
                fields[str(p[1])] = str(p[2])
        x, y, rot = _at(s)
        ref = fields.get("Reference", "")
        for inst in find(first(s, "instances", []), "project"):
            for path in find(inst, "path"):
                ref = value(path, "reference") or ref
        symbols[ref] = {"lib_id": value(s, "lib_id"), "x": x, "y": y, "rot": rot, "fields": fields,
                        "dnp": value(s, "dnp")}
    counts = {k: len(find(root, k)) for k in ("wire", "junction", "label", "global_label",
                                              "hierarchical_label", "no_connect", "sheet", "text")}
    return {"symbols": symbols, "counts": counts}


def ref_key(ref):
    """Sort designators as people read them: C2 before C10."""
    m = re.match(r"([^0-9]*)(\d*)(.*)", ref)
    return (m.group(1), int(m.group(2) or 0), m.group(3))


# ---------------------------------------------------------------- project paths (the check scripts)

class ProjectError(Exception):
    pass


# The folder that holds the KiCad project: hardware/ by default. An existing project keeps its own
# layout; `build.py --adopt` records where its KiCad files are as one line in design/status.md:
#     KiCad folder: hardware/
#     KiCad folder: . (the project root)
# Every script finds the KiCad files through kicad_folder() and find_project().
KICAD_FOLDER_KEY = "KiCad folder"
DEFAULT_KICAD_FOLDER = "hardware"
# The folder at the project root that holds the copies of the skill scripts (build.py too). Its own
# name, so the copies never land on a project's own build.py, scripts/ or modules of the same name.
SKILL_FOLDER = "hwskills"
# Top-level folders of the skills' layout. When the KiCad files sit in the project root, these are
# never searched or copied as part of the KiCad project.
LAYOUT_FOLDERS = ("design", "scripts", SKILL_FOLDER, "datasheets", "docs", "firmware")
# Design files: what the ownership record covers (exports such as the netlist and BOM are not).
DESIGN_EXT = (".kicad_sch", ".kicad_pcb", ".kicad_pro", ".kicad_dru", ".kicad_sym", ".kicad_mod",
              ".wrl", ".step", ".stp")
DESIGN_NAMES = ("fp-lib-table", "sym-lib-table")


def is_design_file(path):
    name = os.path.basename(path)
    return name in DESIGN_NAMES or name.endswith(DESIGN_EXT)


def recorded_kicad_folder(design_dir):
    """The folder on the 'KiCad folder:' line of design/status.md, relative to the project root as a
    posix path ("." for the root itself); None when there is no such line or it holds a <placeholder>."""
    for line in status_lines(design_dir):
        if not line.startswith(KICAD_FOLDER_KEY + ":"):
            continue
        v = re.split(r"\s+\(", line.split(":", 1)[1].strip())[0].strip().strip("`").replace("\\", "/")
        if v.startswith("<"):
            return None
        v = v.rstrip("/") or "."
        if v.startswith("/") or re.match(r"^[A-Za-z]:", v) or ".." in v.split("/"):
            raise ProjectError("design/status.md: 'KiCad folder: %s' must name a folder inside the project root" % v)
        return os.path.normpath(v).replace(os.sep, "/")
    return None


def kicad_folder(root, design_dir=None):
    """(absolute path, relative name) of the folder that holds the KiCad project: the folder recorded in
    design/status.md, else hardware/. The folder may not exist yet."""
    rel = recorded_kicad_folder(design_dir or os.path.join(root, "design")) or DEFAULT_KICAD_FOLDER
    return os.path.normpath(os.path.join(root, rel)), rel


def folder_label(rel):
    """A KiCad folder as messages name it: "hardware/", or "the project root"."""
    return "the project root" if rel in (".", "") else rel.rstrip("/") + "/"


def kicad_project_folders(root, depth=3):
    """Folders at or under root that hold a .kicad_pro, as relative posix paths ("." for the root), sorted.
    Hidden folders, KiCad backups and the skills' own top-level folders (LAYOUT_FOLDERS) are skipped."""
    out = []
    for d, dirs, names in os.walk(root):
        rel = os.path.relpath(d, root).replace(os.sep, "/")
        level = 0 if rel == "." else rel.count("/") + 1
        dirs[:] = sorted(x for x in dirs if level < depth and not x.startswith(".") and not x.endswith("-backups")
                         and not (rel == "." and x in LAYOUT_FOLDERS))
        if any(n.endswith(".kicad_pro") for n in names):
            out.append(rel)
    return sorted(out)


def record_kicad_folder(design_dir, rel):
    """Write the 'KiCad folder:' line into design/status.md (replaced if there, else put after the
    Ownership line, else at the end; the file is made if missing). Returns the line written."""
    line = "%s: %s" % (KICAD_FOLDER_KEY, ". (the project root)" if rel in (".", "") else rel.rstrip("/") + "/")
    lines = status_lines(design_dir)
    for i, old in enumerate(lines):
        if old.startswith(KICAD_FOLDER_KEY + ":"):
            lines[i] = line
            break
    else:
        at = next((i + 1 for i, old in enumerate(lines) if old.startswith("Ownership:")), len(lines))
        while at < len(lines) and lines[at].startswith((" ", "\t")) and lines[at].strip():
            at += 1                     # after the Ownership line's indented continuation lines
        lines.insert(at, line)
    write_text(os.path.join(design_dir, "status.md"), "\n".join(lines) + "\n")
    return line


def project_root_of(path):
    """The project root a KiCad file or folder belongs to: the nearest folder at or above it that holds
    design/; None when there is none."""
    here = os.path.abspath(path)
    if not os.path.isdir(here):
        here = os.path.dirname(here)
    d = here
    while True:
        if os.path.isdir(os.path.join(d, "design")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def design_dir_for(path):
    """design/ of the project a KiCad file or folder belongs to (project_root_of); with no project root
    found, design/ beside the file's folder, which may not exist."""
    root = project_root_of(path)
    if root:
        return os.path.join(root, "design")
    here = os.path.abspath(path)
    if not os.path.isdir(here):
        here = os.path.dirname(here)
    return os.path.join(os.path.dirname(here), "design")


def find_project(start=".", name=None, design=None, hardware=None):
    """Paths of a project laid out as references/repository.md says: design/ under one root, and the
    KiCad files in the folder kicad_folder() names (hardware/ unless design/status.md records another).

    start may be the root or any folder or file inside it; the root is the nearest folder upwards that
    holds design/ or hardware/. Returns a dict: root, design, hardware (the KiCad folder), kicad_rel (its
    name relative to the root), name, and the paths sch, net, pcb, pro, dru (each may not exist yet).
    Raises ProjectError when no root is found or the KiCad folder holds several projects and no name
    is given.
    """
    here = os.path.abspath(start)
    if os.path.isfile(here):
        here = os.path.dirname(here)
    root = here
    while not (os.path.isdir(os.path.join(root, "design")) or os.path.isdir(os.path.join(root, "hardware"))):
        parent = os.path.dirname(root)
        if parent == root:
            raise ProjectError("no design/ or hardware/ folder in %s or above it; pass --project" % here)
        root = parent
    design = os.path.abspath(design) if design else os.path.join(root, "design")
    if hardware:
        hw = os.path.abspath(hardware)
        rel = os.path.relpath(hw, root).replace(os.sep, "/")
    else:
        hw, rel = kicad_folder(root, design)
    if not name and os.path.isdir(hw):
        for ext in (".kicad_pro", ".kicad_sch", ".kicad_pcb"):
            found = sorted(f[:-len(ext)] for f in os.listdir(hw) if f.endswith(ext))
            if len(found) == 1:
                name = found[0]
                break
            if len(found) > 1 and ext == ".kicad_pro":
                raise ProjectError("%s holds several projects (%s); pass --name" % (folder_label(rel), ", ".join(found)))
    p = {"root": root, "design": design, "hardware": hw, "kicad_rel": rel, "name": name or ""}
    for key, ext in (("sch", ".kicad_sch"), ("net", ".net"), ("pcb", ".kicad_pcb"), ("pro", ".kicad_pro"),
                     ("dru", ".kicad_dru")):
        p[key] = os.path.join(hw, name + ext) if name else ""
    return p


def net_key(name):
    """A net name compared without the leading "/" of a root-sheet label: "/SPI_SCK" equals "SPI_SCK"."""
    return (name or "").strip().lstrip("/")


def kicad_dir(kind):
    """KiCad's own library folder ("footprints", "symbols" or "3dmodels"), or None when not found."""
    try:
        import kicad_env
        return {"footprints": kicad_env.footprint_dir, "symbols": kicad_env.symbol_dir,
                "3dmodels": kicad_env.model_dir}[kind]()
    except (ImportError, SystemExit):
        return None


def lib_table(hw_dir, table="fp-lib-table"):
    """{library name: folder or file} from a project library table, with ${KIPRJMOD} filled in."""
    path = os.path.join(hw_dir, table)
    if not os.path.isfile(path):
        return {}
    out = {}
    for lib in find(read_sexpr(path), "lib"):
        uri = value(lib, "uri").replace("${KIPRJMOD}", hw_dir)
        out[value(lib, "name")] = os.path.normpath(uri) if "${" not in uri else uri
    return out


def resolve_footprint(lib_id, hw_dir):
    """Path of the .kicad_mod for "lib:name": the project's fp-lib-table first, then KiCad's own folder.

    Returns (path or None, where it looked)."""
    lib, _, name = (lib_id or "").partition(":")
    if not name:
        return None, "footprint %r has no library prefix" % lib_id
    places = []
    folder = lib_table(hw_dir).get(lib)
    if folder:
        places.append(os.path.join(folder, name + ".kicad_mod"))
    kd = kicad_dir("footprints")
    if kd:
        places.append(os.path.join(kd, lib + ".pretty", name + ".kicad_mod"))
    for p in places:
        if os.path.isfile(p):
            return p, ""
    return None, "looked in " + (", ".join(places) if places else "no library folder (KiCad's not found)")


MODEL_VARS = ("KICAD10_3DMODEL_DIR", "KICAD9_3DMODEL_DIR", "KICAD8_3DMODEL_DIR", "KICAD7_3DMODEL_DIR",
              "KICAD6_3DMODEL_DIR", "KISYS3DMOD")


def resolve_model(path, hw_dir):
    """Path of a 3D model file named in a footprint, with ${KIPRJMOD} and KiCad's model variables filled in.

    Returns (path, exists)."""
    p = path.replace("${KIPRJMOD}", hw_dir)
    for var in MODEL_VARS:
        placeholder = "${%s}" % var
        if placeholder in p:
            base = os.environ.get(var) or kicad_dir("3dmodels") or ""
            p = p.replace(placeholder, base)
    if not os.path.isabs(p) and "${" not in p:
        p = os.path.join(hw_dir, p)
    return p, "${" not in p and os.path.isfile(p)
