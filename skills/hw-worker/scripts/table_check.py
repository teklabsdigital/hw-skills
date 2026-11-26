# Copyright 2026 Teklabs Digital (hw-skills)
# SPDX-License-Identifier: Apache-2.0
"""Checks on the project tables in design/, and the confidentiality scan. Python 3 standard library only.

    python3 table_check.py <sub-command> [<sub-command> ...] [--project DIR] [options]
    python3 table_check.py all                       every pass/fail sub-command except scan
    python3 table_check.py impact <ID or designator or MPN>
    python3 table_check.py scan [FILE or FOLDER ...]  default: the staged files, else the project
    python3 table_check.py log-append --statement "..." --kind decision --by user --stage ST5 ...
    python3 table_check.py set-row parts.csv R1 value=10k

Pass or fail (exit 1 when any fails):
  compliance  design/compliance.csv: allowed values; every row has a schematic result; "open" rows are
              counted, and open must and hard rows with no DC- decision are listed, and fail from
              --stage ST6 (the schematic checkpoint; package rows from ST11, assembly rows from ST12;
              kind "data" holds package and assembly values and is not a must row); hard rows (layout, grounding, protection, absolute-maximum)
              "not met" or "does not apply" only with a DC- decision; layout and grounding rows are
              "carried", not "met"; "carried" only on those; carried_to names constraints that exist;
              figure and graph rows have a figure number and a saved render
              design/renders/<datasheet>_p<page>.png (the datasheet file name without .pdf, else the
              MPN); a calculation row closed (met or not met) names its script in design/calcs/; a
              "no guidance found" row says in evidence what was read; staging files in design/passes/
              named <MPN>_<perspective>. --board, or --stage ST11 or later: carried rows also need a board
              result or a DC- decision. A table with no rows fails from --stage ST6 unless a decision in
              design/decisions.md names the file. Prints the
              open violations, and the page renders no figure or graph row cites (listed, not failed).
              --staged FILE: a pass's own staging file <MPN>_<perspective>.csv instead, before the
              merge (ids <perspective>-<n>, the file's perspective in every row).
  sections    design/sections.csv: allowed values; sections no perspective claimed; layout, grounding,
              application, thermal and typical-application sections with zero rows and no note;
              datasheets in compliance.csv with no section inventory; no rows at all, as compliance.
              --staged FILE: a pass's <MPN>_<perspective>_sections.csv instead. It holds the whole
              inventory of its datasheet, copied from design/sections.csv, with this pass's claims
              filled: an empty file, inventory rows missing from it and sections the inventory does
              not have fail; claims of another pass fail; sections it does not claim are listed.
  constraints design/constraints.csv: IDs; `from` exists; enforced_by is dru:, check: or review:; the
              rule is in the .kicad_dru (dru:netclass X: the class in the .kicad_pro, and only the
              rule of the row's own kind: "netclass X clearance" for a clearance row, "netclass X
              width" for a width row; via rows need the class only; with no rule file at all, as in a
              hand-made project, the class in the .kicad_pro counts when its value reaches the limit,
              and the output says so); the check is a
              board_check.py sub-command naming its own row; a review: constraint has a note and, once a
              board review is recorded in status.md, a verdict in that report's section 6; sufficiency
              given; every carried row has a constraint; a row whose words ask for one thing (single
              point, keep-out, one piece) marked whole without that check or a review: enforcer. A
              verdict "not met" in the board review is a violation and fails unless a DC- decision on
              the verdict line, or the decision of the row's DS- source, covers it; "cannot tell" is
              listed and fails from --stage ST11. A row whose kind, objects, limit or enforcer changed
              since the sufficiency review (the baseline in design/constraints-reviewed.csv, written by
              --record-review BR-nn-nn) needs a DC- decision in its note: listed, a fail from --stage
              ST7; with no baseline at all, listed, a fail from --stage ST11.
              Prints how many constraints each kind of enforcer carries.
  fabcap      design/fab-capabilities.csv: value, source (URL or "from user") and date on every row,
              nothing "from memory"; rule_value never tighter than the manufacturer's value; the board
              minimums in the .kicad_pro not below the rule values. A table with no rows is listed, and
              fails with --stage ST11 or later (the board checkpoint).
  parts       design/parts.csv: four sourcing fields on fitted parts; role; a checked date for stock
              and price: a missing date is listed, and fails from --stage ST6 (the schematic checkpoint
              holds the parts check); a date older than --max-age days (default 30) is listed with its
              age, and fails only with --stage ST12 or later (the parts check before ordering); package in the
              footprint name; footprint found; 3D models in
              the board and the table found; MSL and peak reflow against the assembler's limits; errata
              recorded for ICs. Prints the parts cost and the assembler's fee rows.
              Lifecycle, for each fitted row with an MPN, against the makers' product pages saved as
              datasheets/<name>_product-page.txt (only those files are read, not sub-folders). A page
              belongs to a row when a line of it names the row's exact MPN. A fail: the lifecycle cell
              starts with "active", or is empty, and a line that names the exact MPN also says not
              recommended for new designs, NRND, last time buy, end of life, obsolete, discontinued or
              preview. Listed, not failed: such a word on another line of the page; a row with no
              page that names its MPN, with the count, at every stage. A lifecycle cell that does
              not start with "active" fails unless it names a DC- decision made by the user; a row
              whose cell names one is not compared with the page. Prints the pages read, also when 0.
  packs       a part's category names a pack whose switch is off or missing in the board profile of
              design/requirements.md (lines "<switch>; on|off; <reason>"); unknown categories. A part in
              several packs names them all, joined by ";". A profile row that cannot be read (a name
              that is no switch, a state that is not on or off alone) is listed and fails, here and
              in checklists.
  suppress    ERC and board severities in the .kicad_pro lower than project_settings.py raises them,
              exclusions, pin-map changes and rule severities in the .kicad_dru, each without a decision.
              Board severities left at KiCad's own defaults (an adopted project's settings) are listed
              with the recommended value, and fail only with --stage ST11 or later (the board checkpoint).
  stale       rows whose MPN differs from the part now fitted (compliance, pins, parts by designator,
              several joined by ";"; compliance rows with no designator by MPN); parts in the netlist with
              no parts.csv row. A compliance row about another part (a capacitor the regulator's datasheet
              specifies) carries the MPN of the datasheet it came from, and is current while that MPN is
              fitted.
  findings    design/findings.csv: untriaged (empty status) or invalid rows. Prints open violations.
              --staged FILE: a pass's <MPN>_<perspective>_findings.csv instead, before the merge
              (ids <perspective>-F<n>).
  decisions   design/decisions.md, the decision log: each entry "## <statement> (DC-nnn)" with the
              fields Kind, Decided by (user, coordinator or worker; "seen by user: yes|no" when not the
              user), Date, Stage, Options, Reason, Affects and Status; IDs unique and rising in file
              order; "Replaces: DC-nnn" (one ID or several) names earlier entries whose Status is
              "superseded by" this one, and the other way round. An entry a later one ends without
              replacing it is "closed (how, DC-nnn)"; an ID in a Status must be in the log. Prints who decided, and the decisions made on the user's
              behalf that the user has not seen yet.
  netreview   design/net-review.csv: items not closed with a written reason are listed and counted,
              and fail only with --stage ST6 or later (the schematic checkpoint); a closed item needs
              closed_by and a date, and a worker's closing reason must cite a part or a row.
  checklists  items of design/checklists/*.md (logical, electrical, board, packs, fabrication,
              repository) that apply (switch on, --stage; a stage cell "any" or "all" applies at every
              stage) with no result in any
              review report in design/reports/: listed in ID order and counted, and a fail only with
              --stage ST6 or later (then only the items of stages up to that one). A result is the
              ID, then met, not met, does not apply or cannot tell ("BD-07: met", "BD-07, BD-08 met",
              or a table row with the ID in the first cell). Any other mention of the ID is no result.
  text      designators that are not in the netlist, and counts ("N violations", "N parts") that
              differ from the latest tool output, in README.md, docs/ and schematic text (or FILEs).
  writers     design/ownership.csv: rows valid; script-owned files present and not changed since the
              script wrote them; generated artefacts (rule-check reports, caches, locks, backups) committed.
              Design files in the KiCad folder with no ownership row are named (they are hand-owned).
  scan        absolute machine paths, user and host names, email addresses, keys, tokens and passwords,
              supplier account and order numbers, terms in design/.private-terms, and the netlist's
              source path and date. Values are printed masked. Text inside zip files is read too.
              Email addresses in makers' documents in datasheets/ (not its README.md) are counted apart
              and do not fail. A hit listed in design/scan-reviewed.csv with a reason and who decided
              does not fail; a row there that matches nothing does. A scan that read no file fails.
              A kept file that points into the scratch folder (a path below it) is found too. The
              folder's own name, a "Scratch:" line and the skill's copies in the project are not.
  requirements  design/requirements.md against its template. A fault of form fails in every run: an FR-
              or QC- ID used twice or out of order; an item marked withdrawn with no DC- decision, or
              with one that is not in the log; a Priority that is not "must have" or "wanted"; a line
              under "To confirm" that is not "TC-nnn; <state>; <kind>; <question or proposal>; <item>"
              (state: open, answered (DC-nnn), withdrawn (DC-nnn); kind: needs the user's answer, needs
              research, proposed by a worker), a TC- ID used twice or out of order, a DC- ID that is
              not in the log. A gap is listed, and fails from --stage ST1: an item with no Priority or
              no Source; an environment profile row that names no source; a board profile row with no
              reason; a line marked "to confirm" (or under a heading "Open ...") that the To confirm
              list does not hold, by its TC- ID, its item or its section; a decision whose Affects
              names the requirements and that the file does not cite.
  datasheets  datasheets/: every document has a line in datasheets/README.md that names it and a text
              extract <name>.txt that is not empty; an extract belongs to a listed document; a PDF the
              README names is in the folder, unless its line says "not committed"; a "not committed"
              line gives a URL, and git does not track that file. With "Third-party PDFs committed: no"
              in design/status.md, every PDF's line says "not committed" and no PDF is tracked. No
              such line reads as yes. Only the files in datasheets/ itself are read, not sub-folders.
              With no datasheets/ folder there is nothing to check: a pass, and a fail from --stage ST6.
Lists and numbers (exit 0):
  parts-totals  design/parts.csv counted from its rows: rows and designators, fitted and not fitted;
              by role, category and supplier; the cost of one board at unit_price and at qty_price
              (price times designators, fitted rows); rows with no price; designators in two rows.
  impact      every row, report and file line that traces to an ID, designator or MPN.
  summary     checkpoint counts, open violations, open decisions and waivers, decisions made on the
              user's behalf and not yet seen, unconfirmed pin rows by designator, rows reopened, files
              changed since each review baseline, and each stage's Done list as "n of m" where the
              files can count it.
Writers (one file changed; each runs alone, and "all" leaves them out):
  log-append  adds one entry at the end of design/decisions.md, in the log form, with the next free DC-
              number and today's date: --statement, --kind, --by, --stage, --options, --reason,
              --affects, and when needed --seen, --status, --replaces. Kind "question answered" fills
              Options "none", every part of Affects "none" and Status "closed (answered)" itself. An
              earlier entry is never changed: with --replaces, the output names each old entry whose
              Status is still to be set by hand. Bad input writes nothing (exit 2).
  set-row     set-row <table>.csv <key> column=value [...]: changes those columns in the one row of a
              table in design/ that has the key, or adds the row at the end when none has it. The key
              is the first column; for pins.csv "designator,pin", for sections.csv
              "datasheet,section", for scan-reviewed.csv "file,line,kind". Every other line keeps its
              bytes. A key column is never changed. Bad input writes nothing (exit 2).

A check whose table or file is not present prints "<file> not present, check not run" and
"<check>: not run". It is listed, not failed, except with --stage at or after its checkpoint: ST6 (the
schematic checkpoint) for every table but constraints.csv and fab-capabilities.csv, which wait for
ST11 (the board checkpoint), and requirements.md, which fails from ST1. The KiCad files are found in hardware/, or in the folder on the line
"KiCad folder: <folder>" of design/status.md.

A violation is a failed check, or a datasheet instruction worded must, should or recommend, a
requirement, a rule or an absolute maximum, not met and not covered by a recorded decision.
Exit codes: 0 pass (or a list printed), 1 a check failed or the scan found something, 2 missing or
unreadable input.
"""
import argparse
import csv
import datetime
import getpass
import glob
import json
import os
import re
import socket
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwcommon  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PASS_FAIL = ("compliance", "sections", "constraints", "fabcap", "parts", "packs", "suppress", "stale",
             "findings", "decisions", "netreview", "checklists", "text", "writers", "requirements", "datasheets")
LISTS = ("impact", "summary", "parts-totals")
WRITERS = ("log-append", "set-row")     # these change one file; they run alone, and "all" leaves them out
COMMANDS = PASS_FAIL + ("scan",) + LISTS + WRITERS

# packs.md: pack, switch short name, parts.csv category.
PACKS = (("SC", "Switching converter", "switching converter"), ("RM", "Radio", "radio"),
         ("VB", "Vehicle", "vehicle bus"), ("GS-USB", "USB", "USB"), ("GS-ETH", "Ethernet", "Ethernet"),
         ("GS-BAT", "Rechargeable", "battery"), ("GS-MOT", "Motors", "motor"), ("GS-MAINS", "Mains", "mains"),
         ("GS-ANA", "Analog", "analog"), ("GS-FAST", "Fast digital", "fast digital"),
         ("GS-IND", "Industrial", "industrial"), ("GS-RAIL", "Multi-rail", "multi-rail"),
         ("GS-SEC", "Microcontroller", "microcontroller"))
SWITCHES = ("Switching converter", "Battery", "Rechargeable", "Radio", "USB", "Ethernet", "Fast digital",
            "Analog", "Motors", "Mains", "Vehicle", "Industrial", "Cables", "Multi-rail", "Microcontroller",
            "Sold", "Enclosure")
REVIEW_LISTS = ("protect", "domains", "opendrain", "unused", "decouple-list")
# The checklist copies made at setup in design/checklists/ (from the skill's checklist-<name>.md and packs.md).
CHECKLIST_COPIES = ("logical", "electrical", "board", "packs", "fabrication", "repository")
SCHEMATIC_CHECKPOINT = "ST6"       # netreview, checklists: open items fail from here on
RULES_CHECKPOINT = "ST7"           # constraints: a limit or enforcer changed since its sufficiency review
BOARD_CHECKPOINT = "ST11"          # suppress: board severities left at KiCad's defaults fail from here on
ORDER_STAGE = "ST12"               # parts: stock and price older than --max-age fail from here on
# A check whose input is not there is listed as "not run", and fails only from this checkpoint on.
TABLE_CHECKPOINT = {"constraints.csv": BOARD_CHECKPOINT, "fab-capabilities.csv": BOARD_CHECKPOINT}
CALC_KIND, NO_GUIDANCE = "calculation", "no guidance found"
# KiCad's own severities for the board checks project_settings.py raises to errors (as KiCad 10 writes
# them into a new project file). A project file holding these is the user's setting, not a suppression.
KICAD_BOARD_SEVERITIES = {"connection_width": "warning", "copper_sliver": "warning", "isolated_copper": "warning",
                          "track_dangling": "warning", "via_dangling": "warning"}
VIOLATION_KINDS = ("must", "should", "recommend")
ID_RE = re.compile(r"\b(?:FR|QC|DC|DS|CN|FD|NR|SP|BR)-\d+(?:-\d+)?\b")
DESIG_RE = re.compile(r"(?<![\w-])(?:R|C|L|U|D|Q|J|Y|F|FB|TP|SW|K|T|P|X|LED|IC|CN|BT|H|MH|ANT|AE)\d{1,3}(?![\w-])")
ITEM_ROW_RE = re.compile(r"^\|\s*([A-Z]{2,5}(?:-[A-Z]{2,5})?-\d{2,})\s*\|(.*)\|\s*$")
SAFE_RE = re.compile(r"[^A-Za-z0-9._+-]")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STAGED_RE = re.compile(r"^(.+)_(logical|electrical|physical)(_sections|_findings)?\.csv$")
STAGED_TABLE = {None: "compliance.csv", "_sections": "sections.csv", "_findings": "findings.csv"}
# constraints.csv kind -> net-class key in the .kicad_pro (as project_settings.NETCLASS_KINDS).
NETCLASS_KEYS = {"clearance": "clearance", "width": "track_width", "via_diameter": "via_diameter",
                 "via_drill": "via_drill"}
PIN_KEY_RE = re.compile(r"^([A-Za-z]{1,4}\d+)\.[A-Za-z0-9_+~{}-]+$")     # a pin or pad: J2.1, U1.EP
FLAGGED_WORDS = (("single_point", re.compile(r"single[- ]point|one point|star[- ]point|at one place", re.I)),
                 ("keepout", re.compile(r"keep[- ]?out|keep .{0,30}clear|no copper|free of copper", re.I)),
                 ("plane_one_piece", re.compile(r"unbroken|uninterrupted|one piece|not split|no splits?\b", re.I)))
GENERATED_RE = re.compile(r"(^|/)(DRC\.json|ERC\.json|[^/]*\.rpt|fp-info-cache|[^/]*\.lck|[^/]*\.kicad_prl|_autosave-[^/]*"
                          r"|[^/]*-backups/.*|~[^/]*|[^/]*\.bak)$")


class InputError(Exception):
    pass


class NotRun(Exception):
    """A check whose input is not there: listed as not run, and a fail only from its checkpoint on."""

    def __init__(self, what, checkpoint=SCHEMATIC_CHECKPOINT):
        Exception.__init__(self, what)
        self.checkpoint = checkpoint


def need(pr, *names):
    """Raise NotRun when one of these files in design/ is not there."""
    for name in names:
        if not os.path.isfile(os.path.join(pr.design, name)):
            raise NotRun("design/%s not present" % name, TABLE_CHECKPOINT.get(name, SCHEMATIC_CHECKPOINT))


def safe(text):
    """A name for a file: characters a file name cannot hold become "-"."""
    return SAFE_RE.sub("-", text or "")


def render_name(row, page=None):
    """The page render behind a row: <datasheet file name without .pdf>_p<page>.png, so every part that
    shares one datasheet file shares its renders; the MPN when the row names no datasheet file."""
    if isinstance(row, str):
        row = {"mpn": row, "datasheet": ""}
    stem = re.sub(r"\.pdf$", "", (row.get("datasheet") or "").strip(), flags=re.I) or row.get("mpn", "")
    return "%s_p%s.png" % (safe(stem), safe(page if page is not None else row.get("page", "")))


def today(a):
    if a.today:
        return datetime.date.fromisoformat(a.today)
    return datetime.date.today()


def stage_at_least(a, stage):
    """True when --stage was given and is at or after `stage` (both written STn)."""
    return bool(a.stage) and int(a.stage[2:]) >= int(stage[2:])


def ref_prefix(ref):
    m = re.match(r"^([A-Za-z]+)", ref or "")
    return m.group(1).upper() if m else ""


# ---------------------------------------------------------------- the project

class Project:
    def __init__(self, a):
        self.a = a
        self.p = hwcommon.find_project(a.project, a.name)
        self.design = self.p["design"]
        self.root = self.p["root"]
        self._t = {}
        self._net = None
        self._sym = None
        self._profile = None

    def table(self, name):
        if name not in self._t:
            self._t[name] = hwcommon.read_table(os.path.join(self.design, name))
        return self._t[name]

    def text(self, rel):
        path = os.path.join(self.root, rel)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()

    def decisions(self):
        return hwcommon.decision_ids(self.design)

    def netlist(self):
        """{ref: {"mpn", "value", "footprint", "fitted"}} from the netlist, else the schematic; {} if neither."""
        if self._net is None:
            self._net = {}
            if self.p["net"] and os.path.isfile(self.p["net"]):
                comps, _ = hwcommon.read_netlist(self.p["net"])
                for ref, c in comps.items():
                    self._net[ref] = {"mpn": c["fields"].get("MPN", ""), "value": c["value"],
                                      "footprint": c["footprint"], "fitted": "dnp" not in c["properties"]}
            elif self.p["sch"] and os.path.isfile(self.p["sch"]):
                for ref, s in self.symbols().items():
                    self._net[ref] = {"mpn": s["fields"].get("MPN", ""), "value": s["fields"].get("Value", ""),
                                      "footprint": s["fields"].get("Footprint", ""), "fitted": s["dnp"] != "yes"}
        return self._net

    def symbols(self):
        if self._sym is None:
            self._sym = {}
            seen = set()

            def read(path):
                if not os.path.isfile(path) or path in seen:
                    return
                seen.add(path)
                root = hwcommon.read_sexpr(path)
                for ref, s in hwcommon.schematic_summary(root)["symbols"].items():
                    if ref and not ref.startswith("#"):
                        self._sym[ref] = s
                for sheet in hwcommon.find(root, "sheet"):
                    for prop in hwcommon.find(sheet, "property"):
                        if len(prop) > 2 and str(prop[1]) in ("Sheetfile", "Sheet file"):
                            read(os.path.join(os.path.dirname(path), str(prop[2])))
            if self.p["sch"]:
                read(self.p["sch"])
        return self._sym

    def section(self, rel, heading):
        """Lines under a heading that starts with <heading>, in a markdown file: up to the next heading of
        the same level or above. The heading may be at any level and may carry a number ("### 3. <heading>").
        None when the file or the heading is not there; [] when the section is empty."""
        text = self.text(rel)
        if text is None:
            return None
        out, level = None, 0
        for line in text.splitlines():
            m = re.match(r"^(#{1,6})\s+(?:\d+(?:\.\d+)*[.)]?\s+)?(.*)$", line)
            if m and level and len(m.group(1)) <= level:
                level = 0
            if m and not level and out is None and m.group(2).strip().lower().startswith(heading.lower()):
                out, level = [], len(m.group(1))
                continue
            if level and line.strip():
                out.append(line)
        return out

    def profile(self):
        """{switch short name: True/False} from the board profile in design/requirements.md, or None."""
        return self.profile_rows()[0]

    def profile_rows(self):
        """(profile, rows not read). A row is a list or table line under "## Board profile", or any line
        there that starts with a switch name: "<switch>; on|off; <reason>". A row with a name that is no
        switch, or a state that is not on, off, yes or no alone, is not guessed at: it is listed, and the
        checks that read the profile fail on it. A table's header and rule lines are passed over."""
        if self._profile is None:
            rel = os.path.join("design", "requirements.md")
            text = self.text(rel)
            if text is None:
                self._profile = (None, [])
                return self._profile
            out, unread, inside = {}, [], False
            for n, line in enumerate(text.splitlines(), 1):
                if line.startswith("## "):
                    inside = line[3:].strip().lower().startswith("board profile")
                    continue
                if not inside or not line.strip():
                    continue
                marked = bool(re.match(r"^\s*[-*|]", line))
                body = re.sub(r"^\s*[-*|]\s*", "", line).strip()
                parts = [x.strip() for x in re.split(r"[;:|]", body) if x.strip()]
                if not parts or not re.search(r"\w", body):
                    continue                                    # the rule line of a table
                name = next((s for s in SWITCHES if s.lower() == parts[0].lower()), None)
                if not name and (not marked or parts[0].lower() == "switch"):
                    continue                                    # prose, or the header line of a table
                state = parts[1].lower().strip(" .,!?*_`\"'()") if len(parts) > 1 else ""
                where = "design/requirements.md line %d: board profile row \"%s\"" % (n, body.rstrip("| ").strip())
                if not name:
                    unread.append("%s: %r is not a switch (the switches: %s)" % (where, parts[0], ", ".join(SWITCHES)))
                elif len(parts) < 2:
                    unread.append("%s: no state; write \"%s; on|off; <reason>\"" % (where, name))
                elif state not in ("on", "off", "yes", "no"):
                    unread.append("%s: state %r must be on or off alone; other words go in the reason" % (where, parts[1]))
                else:
                    out[name] = state in ("on", "yes")
            self._profile = (out, unread)
        return self._profile

    def profile_fails(self, out):
        """The board-profile rows not read, as failures of a check that reads the profile."""
        unread = self.profile_rows()[1]
        if unread:
            out("board profile rows not read: %d (a switch in a row not read counts as missing)" % len(unread))
        return list(unread)

    def status_field(self, key):
        for line in hwcommon.status_lines(self.design):
            if line.startswith(key + ":"):
                return line.split(":", 1)[1].strip()
        return ""

    def baselines(self):
        """[(kind, BR- ID, commit)] from 'Review baselines:' in status.md (placeholders skipped)."""
        out = []
        for m in re.finditer(r"(schematic|board) review (BR-\d+-\d+) at ([0-9a-fA-F]{4,40})",
                             self.status_field("Review baselines")):
            out.append((m.group(1), m.group(2), m.group(3)))
        return out

    def reports(self):
        return sorted(glob.glob(os.path.join(self.design, "reports", "BR-*.md")))


def is_open(status):
    """A findings status that is empty or starts with the word "open", whatever follows ("open; waits on ...")."""
    return bool(re.match(r"^\s*(?:open\b|$)", status, re.I))


def violations(pr, comp_rows=None, findings=True):
    """Open violations from the tables: compliance rows and findings (the definition in the file header).
    comp_rows: other compliance rows to read (staged rows) instead of design/compliance.csv.
    Each line starts with the row's ID, then a space."""
    out = []
    for r in (pr.table("compliance.csv") if comp_rows is None else comp_rows):
        worded = r["kind"] in VIOLATION_KINDS or r["category"] == "absolute-maximum"
        if worded and "not met" in (r["schematic_result"], r["board_result"]) and not hwcommon.decision_closes(r["decision"]):
            out.append("%s %s %s: not met, no decision (%s)" % (r["id"], r["designator"] or r["mpn"], r["section"],
                                                                r["decision"] or "none"))
    for r in (pr.table("findings.csv") if findings else []):
        if r["category"] == "violation" and is_open(r["status"]) and not hwcommon.decision_closes(r["decision"]):
            out.append("%s (%s): %s" % (r["id"], r["location"], r["text"][:80]))
    return out


# ---------------------------------------------------------------- compliance and sections

def empty_table(pr, a, out, name, rows):
    """A table with a header and no rows: listed in an ordinary run; from the schematic checkpoint on a
    fail, unless a decision in design/decisions.md names the file (it is not needed on this board)."""
    if rows:
        return []
    text = "design/%s has no rows (header only): no check reads anything from it" % name
    named = [e["id"] for e in hwcommon.decision_entries(pr.design) if name in e["text"]]
    if named:
        out("  %s; not needed, per %s" % (text, ", ".join(named)))
        return []
    if stage_at_least(a, SCHEMATIC_CHECKPOINT):
        return [text + "; at a checkpoint that needs rows, or a decision that names the file and says why not"]
    out("  %s; listed, a fail from the schematic checkpoint (--stage %s) unless a decision names the file"
             % (text, SCHEMATIC_CHECKPOINT))
    return []


def staged_files(a, kind):
    """[(path, perspective)] of the --staged files of one kind: None (rows), "_sections" or "_findings"."""
    out = []
    for path in getattr(a, "staged", None) or []:
        m = STAGED_RE.match(os.path.basename(path))
        if m and m.group(3) == kind:
            out.append((path, m.group(2)))
    return out


def staged_rows(a, kind):
    """Rows of the --staged files of one kind, each with "_file" and "_persp" added."""
    rows = []
    for path, persp in staged_files(a, kind):
        for r in hwcommon.read_table(path, STAGED_TABLE[kind]):
            r["_file"], r["_persp"] = os.path.basename(path), persp
            rows.append(r)
    return rows


def cmd_compliance(pr, a, out):
    fails = []
    staged = staged_files(a, None)
    if staged:
        rows = staged_rows(a, None)
        out("staged rows checked (before the merge): %s" % ", ".join(os.path.basename(p) for p, _ in staged))
    else:
        need(pr, "compliance.csv")
        rows = pr.table("compliance.csv")
    dcs = pr.decisions()
    have_log = os.path.isfile(os.path.join(pr.design, "decisions.md"))
    cons = dict((r["id"], r) for r in pr.table("constraints.csv"))
    seen, opened, cited, open_hard = set(), 0, set(), []
    board = a.board or stage_at_least(a, BOARD_CHECKPOINT)
    if not staged:
        fails += empty_table(pr, a, out, "compliance.csv", rows)
    for r in rows:
        if staged:
            where = "%s (%s line %d)" % (r["id"] or "row", r["_file"], r["_line"])
            if not re.fullmatch(r"%s-\d+" % r["_persp"], r["id"]):
                fails.append("%s: id must be %s-<n> in a staging file (the merge gives the DS- ID)" % (where, r["_persp"]))
            elif (r["_file"], r["id"]) in seen:
                fails.append("%s: id used twice" % where)
            seen.add((r["_file"], r["id"]))
        else:
            where = "%s (line %d)" % (r["id"] or "row", r["_line"])
            if not re.fullmatch(r"DS-\d{3,}", r["id"]):
                fails.append("%s: id must be DS-nnn" % where)
            elif r["id"] in seen:
                fails.append("%s: id used twice" % where)
            seen.add(r["id"])
        if not r["mpn"]:
            fails.append("%s: no mpn (every row carries the MPN it was taken from)" % where)
        for col, allowed in (("kind", hwcommon.KINDS), ("category", hwcommon.COMPLIANCE_CATEGORIES),
                             ("found_by", hwcommon.FOUND_BY)):
            if r[col] not in allowed:
                fails.append("%s: %s %r is not one of %s" % (where, col, r[col], ", ".join(allowed)))
        persp = hwcommon.split_list(r["perspective"])
        if not persp or any(p not in hwcommon.PERSPECTIVES for p in persp):
            fails.append("%s: perspective %r (logical, electrical, physical, joined by ;)" % (where, r["perspective"]))
        elif staged and r["_persp"] not in persp:
            fails.append("%s: perspective %r lacks %s, the pass this staging file belongs to" % (where, r["perspective"],
                                                                                                r["_persp"]))
        sres, bres, dec = r["schematic_result"], r["board_result"], r["decision"]
        if not sres:
            fails.append("%s: no schematic result" % where)
        elif sres not in hwcommon.SCHEMATIC_RESULTS:
            fails.append("%s: schematic_result %r is not one of %s" % (where, sres, ", ".join(hwcommon.SCHEMATIC_RESULTS)))
        if bres and bres not in hwcommon.BOARD_RESULTS:
            fails.append("%s: board_result %r is not one of %s" % (where, bres, ", ".join(hwcommon.BOARD_RESULTS)))
        if sres == "open":
            opened += 1
            if (r["kind"] == "must" or hwcommon.is_hard(r)) and not hwcommon.decision_closes(dec):
                due = hwcommon.LATE_CATEGORIES.get(r["category"], SCHEMATIC_CHECKPOINT)
                open_hard.append((due, "%s: %s row (%s, %s) is open, with no result and no DC- decision (closes by %s)"
                                  % (where, r["kind"], r["category"], r["designator"] or r["mpn"], due)))
        if dec and dec != hwcommon.PROPOSED and not hwcommon.DC_RE.fullmatch(dec):
            fails.append("%s: decision %r must be a DC- ID or %s" % (where, dec, hwcommon.PROPOSED))
        if hwcommon.DC_RE.fullmatch(dec or "") and have_log and dec not in dcs:
            fails.append("%s: decision %s is not in design/decisions.md" % (where, dec))
        hard = hwcommon.is_hard(r)
        for col, res in (("schematic_result", sres), ("board_result", bres)):
            if hard and res in ("not met", "does not apply") and not hwcommon.decision_closes(dec):
                fails.append("%s: hard row (%s) is %s with no DC- decision (%s)" % (where, r["category"], res,
                                                                                   dec or "none"))
        layoutish = r["category"] in ("layout", "grounding")
        if sres == "carried" and not layoutish:
            fails.append("%s: carried, but category %s (only layout and grounding rows are carried)" % (where, r["category"]))
        if layoutish and sres == "met":
            fails.append("%s: a %s row is carried to constraints, not met in the schematic" % (where, r["category"]))
        if sres == "carried":
            for cn in hwcommon.split_list(r["carried_to"]):
                if cons and cn not in cons:
                    fails.append("%s: carried_to names %s, which is not in constraints.csv" % (where, cn))
            if board and bres in ("", "open") and not hwcommon.decision_closes(dec):
                fails.append("%s: carried row with no board result (from the board checkpoint, --stage %s, "
                             "or with --board)" % (where, BOARD_CHECKPOINT))
        if r["kind"] in ("figure", "graph"):
            if not r["figure"]:
                fails.append("%s: %s row with no figure number" % (where, r["kind"]))
            render = os.path.join(pr.design, "renders", render_name(r))
            cited.add(render_name(r))
            if not r["page"] or not os.path.isfile(render):
                fails.append("%s: %s row has no saved render design/renders/%s" % (where, r["kind"],
                                                                                   render_name(r, r["page"] or "?")))
        if r["kind"] == CALC_KIND and sres in ("met", "not met") and "calcs/" not in r["evidence"]:
            fails.append("%s: calculation row is %s, but its evidence names no script in design/calcs/" % (where, sres))
        if r["text"].strip().lower().startswith(NO_GUIDANCE) and not r["evidence"].strip():
            fails.append("%s: a \"no guidance found\" row needs evidence: the documents and sections read, and what "
                         "was searched for" % where)
    waiting = sorted(glob.glob(os.path.join(pr.design, "passes", "*.csv")))
    for path in waiting:
        base = os.path.basename(path)[:-4]
        m = STAGED_RE.match(base + ".csv")
        if not m:
            fails.append("design/passes/%s.csv: name it <MPN>_<perspective>.csv, <MPN>_<perspective>_sections.csv "
                         "or <MPN>_<perspective>_findings.csv" % base)
            continue
        hwcommon.read_table(path, STAGED_TABLE[m.group(3)])
    if waiting:
        out("staging files in design/passes/ not merged yet: %d" % len(waiting))
    out("rows: %d; open (no result yet): %d" % (len(rows), opened))
    if open_hard and not staged:
        due_now = [line for due, line in open_hard if stage_at_least(a, due)]
        later = [line for due, line in open_hard if not stage_at_least(a, due)]
        fails += due_now
        if later:
            out("open must and hard rows (layout, grounding, protection, absolute-maximum) with no DC- decision: %d; "
                "listed, a fail from the schematic checkpoint (--stage %s; package rows from %s, assembly rows "
                "from %s)" % (len(later), SCHEMATIC_CHECKPOINT, hwcommon.LATE_CATEGORIES["package"],
                              hwcommon.LATE_CATEGORIES["assembly"]))
            for line in later:
                out("  " + line)
    v = violations(pr, rows, findings=False) if staged else violations(pr)
    out("open violations%s: %d" % (" in the staged rows" if staged else "", len(v)))
    for line in v:
        out("  " + line)
    if not staged:
        spare = sorted(os.path.basename(p) for p in glob.glob(os.path.join(pr.design, "renders", "*.png"))
                       if os.path.basename(p) not in cited)
        out("page renders no figure or graph row cites (the merge deletes them; listed, not failed): %d" % len(spare))
    return fails


def staged_against_inventory(pr, staged, rows):
    """A pass's sections staging file holds the whole inventory of its datasheet (every row of
    design/sections.csv for it), with this pass's own claims filled. Rows missing from it, rows the
    inventory does not have, and an empty file are fails."""
    fails = []
    if not os.path.isfile(os.path.join(pr.design, "sections.csv")):
        return ["design/sections.csv not present: the fetch writes the section inventory first, and a staging "
                "file is compared with it"]
    inventory = {}
    for r in pr.table("sections.csv"):
        inventory.setdefault(r["datasheet"], set()).add(r["section"])
    for path, _ in staged:
        name = os.path.basename(path)
        mine = [r for r in rows if r["_file"] == name]
        if not mine:
            fails.append("%s holds no rows: copy every row of the datasheet's inventory from design/sections.csv into "
                         "it, then fill this pass's claims" % name)
            continue
        for ds in sorted(set(r["datasheet"] for r in mine)):
            have = set(r["section"] for r in mine if r["datasheet"] == ds)
            if ds not in inventory:
                fails.append("%s: datasheet %s has no section inventory in design/sections.csv" % (name, ds))
                continue
            missing = sorted(inventory[ds] - have)
            if missing:
                fails.append("%s: %d sections of the %s inventory are missing from the staging file (it holds the "
                             "whole inventory, with this pass's claims filled): %s%s"
                             % (name, len(missing), ds, ", ".join(missing[:15]), " ..." if len(missing) > 15 else ""))
            for sec in sorted(have - inventory[ds]):
                fails.append("%s: section %s of %s is not in the inventory in design/sections.csv" % (name, sec, ds))
    return fails


def cmd_sections(pr, a, out):
    fails = []
    staged = staged_files(a, "_sections")
    if staged:
        rows = staged_rows(a, "_sections")
        out("staged section claims checked (before the merge): %s" % ", ".join(os.path.basename(p) for p, _ in staged))
        fails += staged_against_inventory(pr, staged, rows)
    else:
        need(pr, "sections.csv")
        rows = pr.table("sections.csv")
        fails += empty_table(pr, a, out, "sections.csv", rows)
    have, elsewhere = set(), []
    for r in rows:
        where = "%s section %s (%s)%s" % (r["datasheet"], r["section"], r["title"],
                                          " in %s" % r["_file"] if staged else "")
        have.add(r["datasheet"])
        if r["category"] not in hwcommon.SECTION_CATEGORIES:
            fails.append("%s: category %r is not allowed" % (where, r["category"]))
        claimed = hwcommon.split_list(r["claimed_by"])
        if not claimed and staged:
            elsewhere.append(where)
        elif not claimed:
            fails.append("%s: no perspective claimed it" % where)
        elif any(c not in hwcommon.PERSPECTIVES for c in claimed):
            fails.append("%s: claimed_by %r" % (where, r["claimed_by"]))
        elif staged and any(c != r["_persp"] for c in claimed):
            fails.append("%s: claimed_by %r; a staging file holds the claims of its own pass (%s) only"
                         % (where, r["claimed_by"], r["_persp"]))
        counts = []
        for col in ("rows_logical", "rows_electrical", "rows_physical"):
            v = r[col] or "0"
            if not v.isdigit():
                fails.append("%s: %s %r is not a count" % (where, col, r[col]))
                v = "0"
            counts.append(int(v))
        if r["category"] in hwcommon.SECTIONS_NEEDING_ROWS and claimed and sum(counts) == 0 and not r["note"]:
            fails.append("%s: %s section with zero rows and no note" % (where, r["category"]))
    if staged:
        comp, comp_name = staged_rows(a, None), "the staged rows"
    else:
        comp, comp_name = pr.table("compliance.csv"), "compliance.csv"
    for ds in sorted(set(r["datasheet"] for r in comp if r["datasheet"]) - have):
        fails.append("%s: rows in %s, no section inventory in %s" % (ds, comp_name, "the staged claims" if staged
                                                                      else "sections.csv"))
    out("sections: %d in %d datasheets" % (len(rows), len(have)))
    if staged:
        out("inventory sections not claimed in these files (another pass's scope, or still to claim; listed, not "
            "failed): %d" % len(elsewhere))
        for line in elsewhere:
            out("  " + line)
    return fails


# ---------------------------------------------------------------- constraints and the board rules

def dru_rules(pr):
    path = pr.p["dru"]
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return set(m.group(1) or m.group(2) for m in re.finditer(r'\(rule\s+(?:"((?:[^"\\]|\\.)*)"|([^\s()"]+))', text))


def pro_json(pr):
    path = pr.p["pro"]
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def review_verdicts(pr):
    """(report name, {CN-: verdict}) from section 6 of the latest board review in status.md, or (None, {})."""
    boards = [b for b in pr.baselines() if b[0] == "board"]
    if not boards:
        return None, {}
    br = boards[-1][1]
    path = os.path.join(pr.design, "reports", br + ".md")
    if not os.path.isfile(path):
        raise InputError("status.md names board review %s, but design/reports/%s.md is missing" % (br, br))
    verdicts, inside = {}, False
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("## "):
                inside = bool(re.match(r"^## 6\b", line))
                continue
            if inside:
                for cn in hwcommon.CN_RE.findall(line):
                    m = re.search(r"\b(not met|met|cannot tell)\b", line, re.I)
                    if m:
                        verdicts[cn] = (m.group(1).lower(), set(hwcommon.DC_RE.findall(line)))
    return br, verdicts


REVIEWED_COLS = ("kind", "objects", "limit", "enforced_by")


def reviewed_baseline(pr, rows, a, out, dcs):
    """Constraints whose kind, objects, limit or enforcer changed since the sufficiency review recorded
    them in design/constraints-reviewed.csv. A change with no DC- decision in the row's note is listed, and
    a fail from the board rules checkpoint (--stage ST7) on. With no baseline file the changes cannot be
    seen: listed, and a fail from the board checkpoint (--stage ST11)."""
    path = os.path.join(pr.design, "constraints-reviewed.csv")
    if not os.path.isfile(path):
        text = ("no sufficiency-review baseline (design/constraints-reviewed.csv): a limit or enforcer changed after "
                "the review cannot be seen; record it with table_check.py constraints --record-review BR-nn-nn")
        if rows and stage_at_least(a, BOARD_CHECKPOINT):
            return [text]
        if rows:
            out("  " + text + "; listed, a fail from the board checkpoint (--stage %s)" % BOARD_CHECKPOINT)
        return []
    base = dict((r["id"], r) for r in hwcommon.read_table(path))
    changed, decided, added = [], [], []
    for r in rows:
        b = base.get(r["id"])
        if b is None:
            added.append(r["id"])
            continue
        diff = ["%s %r -> %r" % (c, b[c], r[c]) for c in REVIEWED_COLS if b[c] != r[c]]
        if not diff:
            continue
        line = "%s changed since sufficiency review %s: %s" % (r["id"], b["review"] or "?", "; ".join(diff))
        named = [d for d in hwcommon.DC_RE.findall(r["note"]) if d in dcs]
        (decided if named else changed).append(line + (" (under %s)" % ", ".join(named) if named else
                                                       "; no DC- decision in its note"))
    gone = sorted(set(base) - set(r["id"] for r in rows))
    out("changed since the sufficiency review: %d with a decision, %d without; added since: %d; removed: %d"
        % (len(decided), len(changed), len(added), len(gone)))
    for line in decided:
        out("  " + line)
    if added:
        out("  added since the review (they need a sufficiency verdict): %s" % ", ".join(added))
    if gone:
        out("  in the baseline, no longer in constraints.csv: %s" % ", ".join(gone))
    if changed and stage_at_least(a, RULES_CHECKPOINT):
        return changed
    for line in changed:
        out("  " + line + "; a fail from the board rules checkpoint (--stage %s)" % RULES_CHECKPOINT)
    return []


def record_review(pr, rows, review, day):
    """Write design/constraints-reviewed.csv: the constraints as this sufficiency review saw them."""
    recs = [dict([(c, r[c]) for c in ("id",) + REVIEWED_COLS] + [("review", review), ("date", day.isoformat())])
            for r in rows]
    hwcommon.write_table(os.path.join(pr.design, "constraints-reviewed.csv"), "constraints-reviewed.csv", recs)
    return len(recs)


def cmd_constraints(pr, a, out):
    fails = []
    need(pr, "constraints.csv")
    rows = pr.table("constraints.csv")
    comp = dict((r["id"], r) for r in pr.table("compliance.csv"))
    comp_present = os.path.isfile(os.path.join(pr.design, "compliance.csv"))
    if not comp_present:
        out("design/compliance.csv not present: the DS- rows named in from are not checked")
    dcs = pr.decisions()
    rules = dru_rules(pr)
    pro = pro_json(pr)
    classes = set(c.get("name") for c in (pro or {}).get("net_settings", {}).get("classes", []))
    br, verdicts = review_verdicts(pr)
    checks_here = os.path.isfile(os.path.join(HERE, "board_check.py"))
    count = {"dru": 0, "check": 0, "review": 0}
    by_from, seen, from_project, unsure = {}, set(), [], []
    for r in rows:
        where = "%s (line %d)" % (r["id"] or "row", r["_line"])
        if not re.fullmatch(r"CN-\d{3,}", r["id"]):
            fails.append("%s: id must be CN-nnn" % where)
        elif r["id"] in seen:
            fails.append("%s: id used twice" % where)
        seen.add(r["id"])
        src = r["from"]
        if re.fullmatch(r"DS-\d{3,}", src):
            if src not in comp and comp_present:
                fails.append("%s: from %s, which is not in compliance.csv" % (where, src))
        elif hwcommon.DC_RE.fullmatch(src):
            if dcs and src not in dcs:
                fails.append("%s: from %s, which is not in decisions.md" % (where, src))
        elif src != "user":
            fails.append("%s: from %r must be a DS- row, a DC- decision or user" % (where, src))
        by_from.setdefault(src, []).append(r)
        enf = hwcommon.parse_enforcer(r["enforced_by"])
        if not enf:
            fails.append("%s: enforced_by %r is not dru:<rule>, check:<sub-command> <CN-> or review:<ID>"
                         % (where, r["enforced_by"]))
        else:
            count[enf[0]] += 1
            if enf[0] == "dru":
                if rules is None and enf[1].startswith("netclass "):
                    # No rule file (a hand-made project): KiCad's DRC applies the net class from the
                    # project file itself, so the class there counts; its value must reach the limit.
                    cls = enf[1][len("netclass "):].strip()
                    entry = next((c for c in (pro or {}).get("net_settings", {}).get("classes", [])
                                  if c.get("name") == cls), None)
                    key = NETCLASS_KEYS.get(r["kind"])
                    if entry is None:
                        fails.append("%s: net class %s is not in the project file" % (where, cls))
                    elif key and hwcommon.num(entry.get(key), -1.0) < hwcommon.num(r["limit"], 0.0) - 1e-9:
                        fails.append("%s: net class %s has %s %s in the project file, below the limit %s"
                                     % (where, cls, key, entry.get(key), r["limit"]))
                    else:
                        from_project.append(r["id"])
                elif rules is None:
                    fails.append("%s: no rule file %s to hold %s" % (where, os.path.basename(pr.p["dru"] or "<name>.kicad_dru"),
                                                                     enf[1]))
                elif enf[1].startswith("netclass "):
                    cls = enf[1][len("netclass "):].strip()
                    if cls not in classes:
                        fails.append("%s: net class %s is not in the project file" % (where, cls))
                    for kind, rule in (("clearance", "netclass %s clearance" % cls), ("width", "netclass %s width" % cls)):
                        if r["kind"] == kind and rule not in rules:
                            fails.append("%s: rule %r is not in the rule file" % (where, rule))
                elif enf[1] not in rules:
                    fails.append("%s: rule %r is not in the rule file" % (where, enf[1]))
            elif enf[0] == "check":
                if enf[2] != r["id"]:
                    fails.append("%s: enforced_by names %s; it must name its own row" % (where, enf[2]))
                if not checks_here:
                    fails.append("%s: board_check.py is not beside table_check.py (copy the skill scripts into hwskills/)" % where)
            else:
                if not r["note"]:
                    fails.append("%s: review:%s alone needs the reason no script fits in note" % (where, enf[1]))
                if br and r["id"] not in verdicts:
                    fails.append("%s: no verdict in section 6 of board review %s" % (where, br))
        if br and r["id"] in verdicts:
            verdict, line_dcs = verdicts[r["id"]]
            ds = comp.get(src, {})
            cover = sorted(d for d in line_dcs if d in dcs) or ([ds["decision"]] if hwcommon.decision_closes(
                ds.get("decision")) else [])
            if verdict == "not met" and not cover:
                fails.append("%s: violation: board review %s says not met, and no DC- decision covers it (name it on "
                             "the verdict line, or in the decision of %s)" % (where, br, src))
            elif verdict == "cannot tell" and not cover:
                unsure.append("%s: board review %s says cannot tell, with no DC- decision" % (where, br))
            elif verdict != "met":
                out("  %s: %s in %s, covered by %s" % (r["id"], verdict, br, ", ".join(cover)))
        suff = r["sufficiency"].strip().lower()
        if not re.match(r"^(whole|partial|no)\b", suff):
            fails.append("%s: sufficiency %r must start with whole, partial or no" % (where, r["sufficiency"]))
    # every carried row has a constraint; whole claimed where the words ask for a check not present
    for ds, row in sorted(comp.items()):
        if row["schematic_result"] != "carried":
            continue
        mine = by_from.get(ds, []) + [c for c in rows if c["id"] in hwcommon.split_list(row["carried_to"])
                                      and c not in by_from.get(ds, [])]
        if not mine:
            fails.append("%s (%s, %s): carried layout row with no constraint" % (ds, row["designator"] or row["mpn"],
                                                                                 row["section"]))
            continue
        enfs = [hwcommon.parse_enforcer(c["enforced_by"]) for c in mine]
        names = set(e[1] for e in enfs if e and e[0] == "check") | set(c["kind"] for c in mine if hwcommon.parse_enforcer(c["enforced_by"]))
        has_review = any(e and e[0] == "review" for e in enfs)
        whole = [c["id"] for c in mine if c["sufficiency"].strip().lower().startswith("whole")]
        for check, words in FLAGGED_WORDS:
            if words.search(row["text"]) and check not in names and not has_review and whole:
                fails.append("%s: the text asks for %s (%r), but its constraints (%s) have no %s check or review: "
                             "verdict, and %s say whole; the sufficiency is partial at most"
                             % (ds, check.replace("_", " "), words.search(row["text"]).group(0),
                                ", ".join(c["id"] for c in mine), check, ", ".join(whole)))
    alone = [ds for ds in sorted(comp) if comp[ds]["schematic_result"] == "carried" and by_from.get(ds)
             and all((hwcommon.parse_enforcer(c["enforced_by"]) or ("",))[0] == "review" for c in by_from[ds])]
    out("constraints by enforcer: rule (dru:) %d, check (check:) %d, review alone (review:) %d"
        % (count["dru"], count["check"], count["review"]))
    out("carried rows resting on a reviewer's verdict alone: %d%s" % (len(alone), (" (%s)" % ", ".join(alone)) if alone else ""))
    if from_project:
        out("no rule file: net classes taken from the project file for %s (a zone's own clearance setting can "
            "override a net class, so a clearance there is partial for zones)" % ", ".join(from_project))
    if br is None:
        out("no board review recorded in status.md yet: review: constraints have no verdict to check")
    else:
        out("verdicts read from %s section 6: %d" % (br, len(verdicts)))
    if unsure and stage_at_least(a, BOARD_CHECKPOINT):
        fails += unsure
    for line in [] if stage_at_least(a, BOARD_CHECKPOINT) else unsure:
        out("  %s; a fail from the board checkpoint (--stage %s)" % (line, BOARD_CHECKPOINT))
    fails += reviewed_baseline(pr, rows, a, out, dcs)
    if a.record_review:
        if fails:
            out("sufficiency baseline NOT recorded: fix the fails above first")
        else:
            out("sufficiency baseline recorded for %s: %d constraints in design/constraints-reviewed.csv"
                % (a.record_review, record_review(pr, rows, a.record_review, today(a))))
    return fails


def cmd_fabcap(pr, a, out):
    import project_settings
    fails = []
    need(pr, "fab-capabilities.csv")
    rows = pr.table("fab-capabilities.csv")
    pro = pro_json(pr)
    rules = (pro or {}).get("board", {}).get("design_settings", {}).get("rules", {})
    for r in rows:
        where = "%s (line %d)" % (r["item"] or "row", r["_line"])
        if not r["item"]:
            fails.append("%s: no item" % where)
        if not r["manufacturer_value"]:
            fails.append("%s: no manufacturer_value" % where)
        src = r["source_url"]
        if not src or not (re.match(r"^https?://", src) or src.lower() == "from user"):
            fails.append("%s: source_url %r must be the page or \"from user\"" % (where, src))
        if not DATE_RE.match(r["read_on"]):
            fails.append("%s: read_on %r must be the date read (YYYY-MM-DD)" % (where, r["read_on"]))
        if any("memory" in r[c].lower() for c in ("manufacturer_value", "source_url", "note")):
            fails.append("%s: a value from memory is not a source" % where)
        if r["item"] in project_settings.CAPABILITY_ITEMS and r["rule_value"]:
            mv, rv = hwcommon.num(r["manufacturer_value"], None), hwcommon.num(r["rule_value"], None)
            if mv is None or rv is None:
                fails.append("%s: manufacturer_value and rule_value must be numbers in mm" % where)
            elif rv < mv:
                fails.append("%s: rule_value %s is tighter than the manufacturer's %s" % (where, r["rule_value"],
                                                                                          r["manufacturer_value"]))
            key = project_settings.CAPABILITY_ITEMS[r["item"]][0]
            if pro is not None and key and rv is not None and key in rules and rules[key] < rv - 1e-9:
                fails.append("%s: the project file's %s is %s, below the rule value %s" % (where, key, rules[key], rv))
    out("capability rows: %d" % len(rows))
    if not rows:
        empty = "design/fab-capabilities.csv has no rows (header only): no capability is sourced"
        if stage_at_least(a, BOARD_CHECKPOINT):
            fails.append(empty)
        else:
            out("  %s; listed, not failed before the board checkpoint (--stage %s)" % (empty, BOARD_CHECKPOINT))
    return fails


# ---------------------------------------------------------------- parts, packs, suppress, stale

def board_models(pr):
    """[(ref, model path)] from the .kicad_pcb."""
    if not pr.p["pcb"] or not os.path.isfile(pr.p["pcb"]):
        return []
    root = hwcommon.read_sexpr(pr.p["pcb"])
    out = []
    for fp in hwcommon.find(root, "footprint"):
        ref = next((str(p[2]) for p in hwcommon.find(fp, "property") if len(p) > 2 and str(p[1]) == "Reference"), "")
        for m in hwcommon.find(fp, "model"):
            out.append((ref, str(m[1])))
    return out


PAGE_SUFFIX = "_product-page.txt"       # a maker's product page, saved as text in datasheets/
NOT_ACTIVE_RE = re.compile(r"not\s+recommended\s+for\s+new\s+designs?|\bNRND\b|last[\s-]time[\s-]buy|"
                           r"end[\s-]of[\s-]life|\bobsolete\b|\bdiscontinued\b|\bpreview\b", re.I)


def maker_pages(pr):
    """[(name, lines)] of the saved maker pages: the files datasheets/*_product-page.txt, no sub-folders."""
    folder = os.path.join(pr.root, DATASHEET_FOLDER)
    if not os.path.isdir(folder):
        return []
    pages = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if name.lower().endswith(PAGE_SUFFIX) and not name.startswith(".") and os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                pages.append((name, f.read().splitlines()))
    return pages


def lifecycle_check(pr, rows, out):
    """The lifecycle cell of each fitted row with an MPN against the saved maker pages that name that
    exact MPN. Returns the failures; prints what was read and what is listed for review."""
    fails = []
    pages = maker_pages(pr)
    by_user = set(e["id"] for e in hwcommon.decision_entries(pr.design) if decided_by(e)[0] == "user")
    checked = with_page = decided = 0
    no_page = []
    for r in rows:
        if r["variant"].strip().lower() == "not fitted" or not r["mpn"]:
            continue
        checked += 1
        where = "%s (%s)" % (r["refs"] or "line %d" % r["_line"], r["mpn"])
        cell = " ".join(r["lifecycle"].split())
        active = cell.lower().startswith("active")
        named_dcs = hwcommon.DC_RE.findall(cell)
        covered = any(d in by_user for d in named_dcs)
        decided += covered
        if cell and not active and not covered:
            fails.append("%s: lifecycle %r is not active, and names no decision by the user (DC-nnn)%s"
                         % (where, cell, "; %s is not a decision by the user in design/decisions.md"
                            % ", ".join(named_dcs) if named_dcs else ""))
        # the exact code: not a longer code that starts or ends with it
        rx = re.compile(r"(?<![\w+#/-])%s(?![\w+#/-])" % re.escape(r["mpn"]), re.I)
        mine = [(name, lines) for name, lines in pages if any(rx.search(line) for line in lines)]
        if not mine:
            no_page.append(r["refs"] or r["mpn"])
            continue
        with_page += 1
        if covered or (cell and not active):
            continue
        for name, lines in mine:
            words = [(n, m.group(0), bool(rx.search(line))) for n, line in enumerate(lines, 1)
                     for m in [NOT_ACTIVE_RE.search(line)] if m]
            on_code = [w for w in words if w[2]]
            if on_code:
                fails.append('%s: lifecycle %s, and %s/%s line %d, which names %s, says "%s"'
                             % (where, "says active" if active else "is empty", DATASHEET_FOLDER, name, on_code[0][0],
                                r["mpn"], " ".join(on_code[0][1].split())))
            elif words:
                out('  %s: %s/%s line %d says "%s", not on a line that names %s (%d such lines); read the page for the '
                    'status of that code; listed, not failed' % (where, DATASHEET_FOLDER, name, words[0][0],
                                                                 " ".join(words[0][1].split()), r["mpn"], len(words)))
    out("lifecycle: fitted rows with an MPN: %d; maker pages read (%s/*%s): %d; rows with a page that names the exact "
        "code: %d; rows under a decision by the user: %d" % (checked, DATASHEET_FOLDER, PAGE_SUFFIX, len(pages), with_page,
                                                             decided))
    if no_page:
        out("  no saved maker page names the exact code: %d of %d fitted rows with an MPN (listed, not failed): %s"
            % (len(no_page), checked, ", ".join(no_page)))
    return fails


def cmd_parts(pr, a, out):
    fails = []
    need(pr, "parts.csv")
    rows = pr.table("parts.csv")
    caps = dict((r["item"], r) for r in pr.table("fab-capabilities.csv"))
    day = today(a)
    waived = dict(w.split("=", 1) for w in a.waive if "=" in w)
    problems = hwcommon.check_waivers(list(waived.values()), pr.design)
    if problems:
        raise InputError("; ".join(problems))
    before_ordering = stage_at_least(a, ORDER_STAGE)
    msl_limit = hwcommon.num(caps.get("assembly_msl_limit", {}).get("manufacturer_value"), None)
    reflow = hwcommon.num(caps.get("assembly_peak_reflow", {}).get("manufacturer_value"), None)
    total, priced = 0.0, 0
    kd = hwcommon.kicad_dir("footprints")
    for r in rows:
        refs = hwcommon.split_list(r["refs"])
        where = "%s (%s)" % (r["refs"] or "line %d" % r["_line"], r["mpn"] or r["value"])
        fitted = r["variant"].strip().lower() != "not fitted"
        if fitted:
            for col in ("manufacturer", "mpn", "supplier", "supplier_pn"):
                if not r[col]:
                    fails.append("%s: no %s" % (where, col))
        if r["role"] not in hwcommon.ROLES:
            fails.append("%s: role %r is not one of %s" % (where, r["role"], ", ".join(hwcommon.ROLES)))
        if fitted:
            if not DATE_RE.match(r["checked"]):
                text = "%s: stock and price have no checked date" % where
                if stage_at_least(a, SCHEMATIC_CHECKPOINT):
                    fails.append(text)
                else:
                    out("  " + text + "; a fail from the schematic checkpoint, which holds the parts check "
                        "(--stage %s)" % SCHEMATIC_CHECKPOINT)
            else:
                age = (day - datetime.date.fromisoformat(r["checked"])).days
                if age > a.max_age:
                    text = "%s: stock and price checked %s, %d days ago (more than %d)" % (where, r["checked"], age,
                                                                                          a.max_age)
                    if before_ordering:
                        fails.append(text)
                    else:
                        out("  " + text + "; a fail only at the parts check before ordering (--stage ST12)")
            price = hwcommon.num(r["unit_price"], None)
            if price is not None:
                total += price * max(1, len(refs))
                priced += 1
        pkg = re.sub(r"[^A-Z0-9]", "", r["package"].upper())
        fpname = re.sub(r"[^A-Z0-9]", "", r["footprint"].split(":")[-1].upper())
        if pkg and fpname and pkg not in fpname:
            fails.append("%s: package %s is not in the footprint name %s; check the footprint against the drawing"
                         % (where, r["package"], r["footprint"]))
        if r["footprint"]:
            path, why = hwcommon.resolve_footprint(r["footprint"], pr.p["hardware"])
            if not path:
                lib = r["footprint"].split(":")[0]
                if kd is None and lib not in hwcommon.lib_table(pr.p["hardware"]):
                    out("  %s: footprint %s not checked (KiCad's library folder not found)" % (where, r["footprint"]))
                elif not any(ref in waived for ref in refs):
                    fails.append("%s: footprint %s not found (%s)" % (where, r["footprint"], why))
        elif fitted:
            fails.append("%s: no footprint" % where)
        if r["model"]:
            mp, ok = hwcommon.resolve_model(r["model"], pr.p["hardware"])
            if not ok and not any(ref in waived for ref in refs):
                fails.append("%s: 3D model %s not found" % (where, r["model"]))
        if msl_limit is not None and r["msl"]:
            m = hwcommon.num(re.sub(r"[^0-9.]", "", r["msl"]), None)
            if m is not None and m > msl_limit:
                fails.append("%s: moisture level %s is above the assembler's limit %s" % (where, r["msl"], msl_limit))
        if reflow is not None and r["peak_reflow"]:
            pk = hwcommon.num(re.sub(r"[^0-9.]", "", r["peak_reflow"]), None)
            if pk is not None and pk < reflow:
                fails.append("%s: peak reflow %s is below the assembler's profile peak %s" % (where, r["peak_reflow"], reflow))
        if any(ref_prefix(x) in ("U", "IC") for x in refs) and fitted and not r["errata"]:
            fails.append("%s: errata not recorded (a file, or \"none published\" with the date checked)" % where)
    for ref, model in board_models(pr):
        mp, ok = hwcommon.resolve_model(model, pr.p["hardware"])
        if not ok:
            if ref in waived:
                out("  %s: 3D model %s missing, WAIVED by %s" % (ref, model, waived[ref]))
            else:
                fails.append("%s: the board names 3D model %s, which is not found" % (ref, model))
    fails += lifecycle_check(pr, rows, out)
    out("parts rows: %d; parts cost per board %.4g from %d priced rows (unit_price times designators)" % (len(rows), total, priced))
    fees = [(k, v) for k, v in sorted(caps.items()) if k.startswith("assembly_fee")]
    for k, v in fees:
        out("  assembler fee %s: %s (%s), add per the assembler's terms" % (k, v["manufacturer_value"], v["note"] or "no note"))
    if not fees:
        out("  no assembly_fee rows in fab-capabilities.csv: the cost total has no assembly fees")
    return fails


def pack_of(category):
    for code, switch, cat in PACKS:
        if category.strip().lower() == cat.lower():
            return code, switch
    return None, None


def cmd_packs(pr, a, out):
    fails = []
    profile = pr.profile()
    if profile is None:
        raise NotRun("design/requirements.md not present (it holds the board profile)")
    fails += pr.profile_fails(out)
    on = sorted(s for s, v in profile.items() if v)
    for r in pr.table("parts.csv"):
        where = "%s (%s)" % (r["refs"], r["mpn"] or r["value"])
        for cat in hwcommon.split_list(r["category"]):      # a part may belong to several packs, joined by ";"
            code, switch = pack_of(cat)
            if code is None:
                fails.append("%s: category %r names no pack (allowed: %s; several joined by \";\")"
                             % (where, cat, ", ".join(c for _, _, c in PACKS)))
            elif switch not in profile:
                fails.append("%s: category %s switches pack %s on; switch %s is not in the board profile"
                             % (where, cat, code, switch))
            elif not profile[switch]:
                fails.append("%s: category %s switches pack %s on, but the board profile has %s off"
                             % (where, cat, code, switch))
    out("switches on in the board profile: %s" % (", ".join(on) or "none"))
    return fails


SEV_ORDER = {"ignore": 0, "warning": 1, "error": 2}


def cmd_suppress(pr, a, out):
    import project_settings
    fails = []
    pro = pro_json(pr)
    if pro is None:
        raise NotRun("KiCad project file %s not present" % (pr.p["pro"] or os.path.join(pr.p["hardware"], "<name>.kicad_pro")))
    blocks = [e["text"] for e in hwcommon.decision_entries(pr.design)]
    dcs = pr.decisions()
    for name, (sev, dc) in sorted(project_settings.SEVERITY_CHANGES.items()):
        if dc not in dcs:
            fails.append("project_settings.py lowers %s to %s under %s, which is not in decisions.md" % (name, sev, dc))
    erc_want, board_want = project_settings.severities()
    with open(project_settings.DEFAULTS, encoding="utf-8") as f:
        defaults = json.load(f)
    board_default = defaults.get("board", {}).get("design_settings", {}).get("rule_severities", {})

    def decided(word):
        return any(word in block for block in blocks)
    for name, sev in sorted(pro.get("erc", {}).get("rule_severities", {}).items()):
        want = erc_want.get(name)
        if want and SEV_ORDER.get(sev, 2) < SEV_ORDER[want] and not decided(name):
            fails.append("ERC %s is %s, raised list says %s; no decision names it" % (name, sev, want))
    at_default = []
    for name, sev in sorted(pro.get("board", {}).get("design_settings", {}).get("rule_severities", {}).items()):
        want = board_want.get(name) or board_default.get(name)
        if want in SEV_ORDER and SEV_ORDER.get(sev, 2) < SEV_ORDER[want] and not decided(name):
            if KICAD_BOARD_SEVERITIES.get(name) == sev:
                at_default.append("board check %s is %s, KiCad's default; recommended: %s" % (name, sev, want))
            else:
                fails.append("board check %s is %s, should be %s; no decision names it" % (name, sev, want))
    if at_default and stage_at_least(a, BOARD_CHECKPOINT):
        fails += [x + "; no decision names it" for x in at_default]
    elif at_default:
        out("board severities left at KiCad's defaults (the project's own settings): %d" % len(at_default))
        for line in at_default:
            out("  " + line)
        out("  propose raising them, or a decision that keeps them; listed, not failed before the board checkpoint "
            "(--stage %s)" % BOARD_CHECKPOINT)
    for key, label in ((("erc", "erc_exclusions"), "ERC exclusion"), (("board", "design_settings", "drc_exclusions"),
                                                                         "DRC exclusion")):
        node = pro
        for k in key:
            node = node.get(k, {}) if isinstance(node, dict) else {}
        for ex in node or []:
            text = ex if isinstance(ex, str) else json.dumps(ex)
            first = re.split(r"[|\s]", text.strip())[0] if text.strip() else text
            if not decided(first):
                fails.append("%s %r with no decision naming %s" % (label, text[:80], first))
    pin_map = pro.get("erc", {}).get("pin_map")
    if pin_map:
        lowered = [(i, j) for i, row in enumerate(pin_map) for j, v in enumerate(row)
                   if i < len(project_settings.ERC_PIN_MAP) and j < len(project_settings.ERC_PIN_MAP[i])
                   and v < project_settings.ERC_PIN_MAP[i][j]]
        if lowered and not decided("pin map"):
            fails.append("ERC pin map lowered at %d places with no decision naming the pin map" % len(lowered))
    if pr.p["dru"] and os.path.isfile(pr.p["dru"]):
        with open(pr.p["dru"], encoding="utf-8") as f:
            dru = f.read()
        for m in re.finditer(r'\(rule\s+"([^"]+)"(?:(?!\(rule\s).)*?\(severity\s+(ignore|warning|exclusion)\)', dru, re.S):
            if not decided(m.group(1)):
                fails.append("rule %r sets severity %s with no decision naming it" % (m.group(1), m.group(2)))
    out("checked: ERC severities, board severities, exclusions, pin map, rule-file severities")
    return fails


def cmd_stale(pr, a, out):
    fails = []
    need(pr, "parts.csv")
    fitted = pr.netlist()
    if not fitted:
        raise NotRun("no netlist or schematic in %s (nothing to compare)" % hwcommon.folder_label(pr.p["kicad_rel"]))
    mpns = set(c["mpn"] for c in fitted.values() if c["fitted"] and c["mpn"])
    other_part = 0
    for name in ("compliance.csv", "pins.csv"):
        for r in pr.table(name):
            refs = hwcommon.split_list(r["designator"])
            rid = r.get("id") or "%s pin %s" % (r["designator"], r.get("pin", ""))
            for ref in refs:
                if ref not in fitted:
                    fails.append("%s %s: designator %s is not in the design" % (name, rid, ref))
                elif fitted[ref]["mpn"] and r["mpn"] and r["mpn"] != fitted[ref]["mpn"]:
                    # A row about an external part (C4) carries the MPN of the datasheet it came from (U1's):
                    # it is current while that part is still fitted. Pin rows are always about their own part.
                    if name == "compliance.csv" and r["mpn"] in mpns:
                        other_part += 1
                        continue
                    fails.append("%s %s: taken from %s, but %s is now %s%s"
                                 % (name, rid, r["mpn"], ref, fitted[ref]["mpn"],
                                    "" if name == "pins.csv" else ", and %s is not fitted" % r["mpn"]))
            if not refs and r["mpn"] and r["mpn"] not in mpns:
                fails.append("%s %s: MPN %s is not fitted in the design" % (name, rid, r["mpn"]))
    if other_part:
        out("compliance rows about another part, taken from a fitted part's datasheet: %d (current)" % other_part)
    covered = set()
    for r in pr.table("parts.csv"):
        for ref in hwcommon.split_list(r["refs"]):
            covered.add(ref)
            if ref not in fitted:
                fails.append("parts.csv %s: not in the design" % ref)
            elif fitted[ref]["mpn"] and r["mpn"] and r["mpn"] != fitted[ref]["mpn"]:
                fails.append("parts.csv %s: MPN %s, the symbol says %s" % (ref, r["mpn"], fitted[ref]["mpn"]))
    for ref in sorted(set(fitted) - covered, key=hwcommon.ref_key):
        if fitted[ref]["fitted"]:
            fails.append("%s (%s): in the design, no parts.csv row" % (ref, fitted[ref]["mpn"] or fitted[ref]["value"]))
    out("compared with %s: %d parts" % ("the netlist" if pr.p["net"] and os.path.isfile(pr.p["net"]) else "the schematic",
                                        len(fitted)))
    return fails


# ---------------------------------------------------------------- findings, net review, checklists

def cmd_findings(pr, a, out):
    fails = []
    staged = staged_files(a, "_findings")
    if staged:
        rows = staged_rows(a, "_findings")
        out("staged findings checked (before the merge): %s" % ", ".join(os.path.basename(p) for p, _ in staged))
    else:
        need(pr, "findings.csv")
        rows = pr.table("findings.csv")
    seen = set()
    for r in rows:
        if staged:
            where = "%s (%s line %d)" % (r["id"] or "row", r["_file"], r["_line"])
            if not re.fullmatch(r"%s-F\d+" % r["_persp"], r["id"]) or (r["_file"], r["id"]) in seen:
                fails.append("%s: id must be a new %s-F<n> in a staging file (the merge gives the FD- ID)"
                             % (where, r["_persp"]))
            seen.add((r["_file"], r["id"]))
        else:
            where = "%s (line %d)" % (r["id"] or "row", r["_line"])
            if not re.fullmatch(r"FD-\d{3,}", r["id"]) or r["id"] in seen:
                fails.append("%s: id must be a new FD-nnn" % where)
            seen.add(r["id"])
        if r["severity"] not in ("1", "2", "3", "4"):
            fails.append("%s: severity %r must be 1 to 4" % (where, r["severity"]))
        if r["category"] not in hwcommon.FINDING_CATEGORIES:
            fails.append("%s: category %r" % (where, r["category"]))
        if not r["status"]:
            fails.append("%s: not triaged (status empty)" % where)
        if r["status"].startswith("decided") and not hwcommon.decision_closes(r["decision"]):
            fails.append("%s: status decided, but decision %r is not a DC- ID" % (where, r["decision"]))
    if staged:
        out("staged findings: %d, of which violations: %d" % (len(rows), sum(r["category"] == "violation" for r in rows)))
        return fails
    v = violations(pr)
    out("open violations: %d" % len(v))
    for line in v:
        out("  " + line)
    out("open findings: %d of %d" % (sum(is_open(r["status"]) for r in rows), len(rows)))
    return fails


def decided_by(entry):
    """(who, seen) from an entry's "Decided by" field: who is user, coordinator, worker or None;
    seen is True, False or None (not stated)."""
    value = entry["fields"].get("Decided by", "")
    m = re.match(r"^\s*(user|coordinator|worker)\b", value, re.I)
    s = re.search(r"seen by user:\s*(yes|no)\b", value, re.I)
    return (m.group(1).lower() if m else None), (s.group(1).lower() == "yes" if s else None)


def unseen_decisions(entries):
    """IDs of log entries made on the user's behalf (coordinator or worker) the user has not seen yet."""
    return [e["id"] for e in entries if not e["old"] and decided_by(e)[0] in ("coordinator", "worker")
            and decided_by(e)[1] is not True]


def affects_parts(value):
    """{part: text} of an entry's Affects field, "requirements <...>; parts <...>; ...". A piece that
    starts with none of the five part names is kept under its own text."""
    out = {}
    for piece in value.split(";"):
        piece = piece.strip()
        if not piece:
            continue
        name = next((p for p in hwcommon.AFFECTS_PARTS if re.match(r"%s\b" % p, piece, re.I)), None)
        out[name or piece] = piece[len(name):].strip(" :") if name else piece
    return out


def cmd_decisions(pr, a, out):
    fails = []
    need(pr, "decisions.md")
    entries = hwcommon.decision_entries(pr.design)
    by_id, last, who_count = {}, 0, {}
    for e in entries:
        where = "%s (decisions.md line %d)" % (e["id"], e["line"])
        if not hwcommon.DC_RE.fullmatch(e["id"]):
            fails.append("%s: the ID must be DC-nnn" % where)
        num = int(e["id"][3:])
        if e["id"] in by_id:
            fails.append("%s: ID used twice (first at line %d)" % (where, by_id[e["id"]]["line"]))
        elif num <= last:
            fails.append("%s: IDs rise in file order; a new entry goes at the end with the next number" % where)
        by_id.setdefault(e["id"], e)
        last = max(last, num)
        if e["old"]:
            fails.append("%s: the one-line form; write it as \"## <what was decided> (%s)\" with the fields %s"
                         % (where, e["id"], ", ".join(hwcommon.DECISION_FIELDS)))
            continue
        if not e["title"]:
            fails.append("%s: no plain statement before the ID" % where)
        f = e["fields"]
        for name in hwcommon.DECISION_FIELDS:
            if not f.get(name):
                fails.append("%s: no %s" % (where, name))
        kind = f.get("Kind", "").lower()
        if kind and kind not in hwcommon.DECISION_KINDS:
            fails.append("%s: Kind %r is not one of %s" % (where, f["Kind"], ", ".join(hwcommon.DECISION_KINDS)))
        who, seen = decided_by(e)
        if f.get("Decided by"):
            if who is None:
                fails.append("%s: Decided by %r must start with %s" % (where, f["Decided by"],
                                                                     ", ".join(hwcommon.DECISION_WHO)))
            elif who != "user" and seen is None:
                fails.append("%s: decided by the %s; say \"seen by user: yes\" or \"no\"" % (where, who))
            who_count[who] = who_count.get(who, 0) + 1
        if f.get("Date") and not DATE_RE.match(f["Date"]):
            fails.append("%s: Date %r must be YYYY-MM-DD" % (where, f["Date"]))
        if f.get("Stage") and not re.search(r"\bST\d+\b", f["Stage"]):
            fails.append("%s: Stage %r names no stage (ST0 to ST13)" % (where, f["Stage"]))
        status = f.get("Status", "").lower()
        if status and not any(status.startswith(s) for s in hwcommon.DECISION_STATUS):
            fails.append("%s: Status %r must start with %s" % (where, f["Status"], ", ".join(hwcommon.DECISION_STATUS)))
        if kind == hwcommon.ANSWERED_KIND:
            # the lighter entry: an answer that chooses or changes something is a full decision entry
            hint = "; an answer that decides something is a full decision entry"
            if f.get("Options") and f["Options"].strip(" .").lower() != "none":
                fails.append("%s: kind \"%s\": Options must be \"none\"%s" % (where, kind, hint))
            changed = [p for p, v in affects_parts(f.get("Affects", "")).items() if v.strip(" .").lower() != "none"]
            if f.get("Affects") and changed:
                fails.append("%s: kind \"%s\": each part of Affects must say \"none\" (%s does not)%s"
                             % (where, kind, ", ".join(sorted(changed)), hint))
            if status and not status.startswith("closed"):
                fails.append("%s: kind \"%s\": Status must be \"%s\"" % (where, kind, hwcommon.ANSWERED_STATUS))
    # change of mind: a new entry points back; the old one says it is superseded by the new one
    for e in entries:
        if e["old"]:
            continue
        where = "%s (decisions.md line %d)" % (e["id"], e["line"])
        for back in hwcommon.DC_RE.findall(e["fields"].get("Replaces", "")):
            old = by_id.get(back)
            if old is None:
                fails.append("%s: Replaces %s, which is not in the log" % (where, back))
            elif old["line"] >= e["line"]:
                fails.append("%s: Replaces %s, which comes after it; a change of mind is a new entry" % (where, back))
            elif not re.search(r"superseded by\s+%s\b" % e["id"], old["fields"].get("Status", ""), re.I):
                fails.append("%s: Replaces %s, but the Status of %s does not say \"superseded by %s\""
                             % (where, back, back, e["id"]))
        m = re.match(r"^superseded by\s+(DC-\d+)", e["fields"].get("Status", ""), re.I)
        if m:
            new = by_id.get(m.group(1))
            if new is None:
                fails.append("%s: superseded by %s, which is not in the log" % (where, m.group(1)))
            elif e["id"] not in hwcommon.DC_RE.findall(new["fields"].get("Replaces", "")):
                fails.append("%s: superseded by %s, but %s has no \"Replaces: %s\"; if %s changes this decision, "
                             "add %s to its Replaces line; if it only ends it, write the Status as "
                             "\"closed (<how>, %s)\"" % (where, m.group(1), m.group(1), e["id"], m.group(1),
                                                         e["id"], m.group(1)))
        else:
            # an entry a later one ends without replacing it: "closed (how, DC-nnn)"; the entry named must exist
            for other in hwcommon.DC_RE.findall(e["fields"].get("Status", "")):
                if other not in by_id:
                    fails.append("%s: Status names %s, which is not in the log" % (where, other))
    unseen = unseen_decisions(entries)
    out("decisions: %d; decided by %s" % (len(entries), ", ".join("%s %d" % (w, who_count.get(w, 0))
                                                                  for w in hwcommon.DECISION_WHO)))
    out("decided on the user's behalf, not yet seen by the user: %d%s" % (len(unseen),
                                                                         (" (%s)" % ", ".join(unseen)) if unseen else ""))
    if unseen:
        out("  list them in the next report to the user, then mark them seen")
    return fails


def cmd_netreview(pr, a, out):
    fails = []
    need(pr, "net-review.csv")
    rows = pr.table("net-review.csv")
    cite = re.compile(r"%s|%s" % (ID_RE.pattern, DESIG_RE.pattern))
    checkpoint = stage_at_least(a, SCHEMATIC_CHECKPOINT)
    still_open = []
    for r in rows:
        where = "%s %s %s" % (r["id"], r["list"], r["net_or_pin"])
        if r["list"] not in REVIEW_LISTS:
            fails.append("%s: list %r is not one of %s" % (where, r["list"], ", ".join(REVIEW_LISTS)))
        if not r["reason"]:
            still_open.append("%s: open (no written reason)" % where)
            continue
        if not r["closed_by"]:
            fails.append("%s: reason given, closed_by empty" % where)
        elif r["closed_by"].lower() not in ("user", "engineer") and not cite.search(r["reason"]):
            fails.append("%s: closed by %s without citing a part or row; a risk judgement is the user's" % (where, r["closed_by"]))
        if not r["date"]:
            fails.append("%s: closed with no date" % where)
    out("net-review items: %d, open: %d" % (len(rows), len(still_open)))
    if checkpoint:
        return fails + still_open
    for line in still_open:
        out("  " + line)
    if still_open:
        out("  open items are listed, not failed, before the schematic checkpoint (--stage %s or later fails them)"
            % SCHEMATIC_CHECKPOINT)
    return fails


ANY_STAGE_RE = re.compile(r"\b(?:any|all|every)\b", re.I)     # a stage cell "any", "all" or "every stage"


def stage_numbers(cell):
    nums = [int(n) for n in re.findall(r"ST(\d+)", cell)]
    return nums, "onward" in cell or bool(ANY_STAGE_RE.search(cell))


def checklist_items(pr):
    """[(ID, what, stage cell, switch cell, file)] from design/checklists/*.md, retired items left out."""
    items = []
    for path in sorted(glob.glob(os.path.join(pr.design, "checklists", "*.md"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = ITEM_ROW_RE.match(line.rstrip("\n"))
                if not m:
                    continue
                cells = [c.strip() for c in m.group(2).split("|")]
                if len(cells) < 5 or cells[0].startswith("Retired"):
                    continue
                items.append((m.group(1), cells[0], cells[2], cells[4], os.path.basename(path)))
    return sorted(items, key=lambda it: item_key(it[0]))


def item_key(iid):
    """Checklist IDs in reading order: BD-02 before BD-10, GS-USB-01 after GS-SEC-05."""
    m = re.match(r"^(.*?)-(\d+)$", iid)
    return (m.group(1), int(m.group(2))) if m else (iid, 0)


def applies(switch_cell, profile):
    cell = switch_cell.strip().lower()
    if cell.startswith("always"):
        return True
    name = next((s for s in SWITCHES if s.lower() == cell), None)
    return bool(name and profile.get(name))


# The result form of a checklist item in a report: the ID, then its result. Between the two there may be
# other IDs that share the result ("BD-07, BD-08: met"), a note in brackets, and marks such as ":" or "**".
# In a table row the ID is the first cell and the result starts a later cell.
ITEM_RESULTS = ("not met", "met", "does not apply", "cannot tell")
RESULT_WORDS = r"(?:%s)\b" % "|".join(ITEM_RESULTS)
ITEM_ID = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+"
RESULT_FORM = (r"(?<![\w-])%%s(?![\w-])[*_`]*(?:\s*(?:,|and|&)\s*[*_`]*%s[*_`]*)*\s*(?:\([^()\n]*\))?[\s:=*_`-]*%s"
               % (ITEM_ID, RESULT_WORDS))


def items_with_result(text, ids):
    """The IDs in ids that the report text gives a result for, in the result form."""
    got = set()
    for line in text.splitlines():
        if not re.search(RESULT_WORDS, line, re.I):
            continue
        cells = [c.strip().strip("*_`").strip() for c in line.strip().strip("|").split("|")]
        row = line.lstrip().startswith("|") and any(re.match(RESULT_WORDS, c, re.I) for c in cells[1:])
        for iid in ids:
            if iid in got or iid not in line:
                continue
            if (row and cells[0] == iid) or re.search(RESULT_FORM % re.escape(iid), line, re.I):
                got.add(iid)
    return got


def cmd_checklists(pr, a, out):
    profile = pr.profile() or {}
    items = checklist_items(pr)
    if not items:
        raise NotRun("no checklist items in design/checklists/*.md (the checklist copies are not present)")
    unread = pr.profile_fails(out)      # a row not read would switch its checklist items off without a word
    text = ""
    for path in pr.reports():
        with open(path, encoding="utf-8") as f:
            text += f.read() + "\n"
    stage = int(a.stage[2:]) if a.stage else None
    answered = items_with_result(text, [it[0] for it in items])
    active, still_open = 0, []
    for iid, what, stage_cell, switch, fname in items:
        if not applies(switch, profile):
            continue
        if stage is not None:
            nums, onward = stage_numbers(stage_cell)
            if nums and min(nums) > stage and not ANY_STAGE_RE.search(stage_cell):
                continue
            if not nums and not onward:
                continue
        active += 1
        if iid not in answered:
            still_open.append("%s (%s): no result in any review report" % (iid, fname))
    out("checklist items that apply%s: %d, with no result yet: %d; review reports read: %d"
        % (" up to %s" % a.stage if a.stage else "", active, len(still_open), len(pr.reports())))
    if stage_at_least(a, SCHEMATIC_CHECKPOINT):
        return unread + still_open
    for line in still_open:
        out("  " + line)
    if still_open:
        out("  items with no result are listed, not failed, before the schematic checkpoint (--stage %s or later "
            "fails those of the stages up to it)" % SCHEMATIC_CHECKPOINT)
    return unread


# ---------------------------------------------------------------- text, writers

def schematic_texts(pr):
    out = []
    for path in sorted(glob.glob(os.path.join(pr.p["hardware"], "*.kicad_sch"))):
        root = hwcommon.read_sexpr(path)
        stack = [root]
        while stack:
            node = stack.pop()
            for child in node:
                if isinstance(child, list) and child:
                    if child[0] in ("text", "text_box") and len(child) > 1 and isinstance(child[1], str):
                        out.append((os.path.relpath(path, pr.root), str(child[1])))
                    else:
                        stack.append(child)
    return out


def drc_counts(pr):
    path = os.path.join(pr.p["hardware"], "DRC.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return {"violations": len(d.get("violations", [])), "unconnected": len(d.get("unconnected_items", []))}


def cmd_text(pr, a, out):
    fails = []
    design = pr.netlist()
    sources = []
    if a.targets:
        for t in a.targets:
            with open(t, encoding="utf-8", errors="replace") as f:
                sources.append((t, f.read()))
    else:
        for rel in ["README.md"] + sorted(os.path.relpath(p, pr.root) for p in glob.glob(os.path.join(pr.root, "docs", "**", "*.md"),
                                                                                        recursive=True)):
            t = pr.text(rel)
            if t is not None:
                sources.append((rel, t))
        sources += schematic_texts(pr)
    drc = drc_counts(pr)
    fitted = sum(1 for c in design.values() if c["fitted"])
    for name, text in sources:
        for n, line in enumerate(text.splitlines(), 1):
            if design:
                for m in DESIG_RE.finditer(line):
                    if m.group(0) not in design:
                        fails.append("%s:%d: %s is not a designator in the design" % (name, n, m.group(0)))
            for m in re.finditer(r"\b(\d+)\s+(violations?|unconnected(?: items)?)\b", line, re.I):
                key = "unconnected" if m.group(2).lower().startswith("unconnected") else "violations"
                if drc is not None and int(m.group(1)) != drc[key]:
                    fails.append("%s:%d: says %s %s, the latest DRC.json has %d" % (name, n, m.group(1), m.group(2), drc[key]))
            for m in re.finditer(r"\b(\d+)\s+parts\b", line):
                if design and int(m.group(1)) != fitted:
                    fails.append("%s:%d: says %s parts, the design has %d fitted" % (name, n, m.group(1), fitted))
    out("text read: %d sources; designators %s; counts against %s" % (
        len(sources), "checked" if design else "not checked (no netlist)", "DRC.json" if drc else "the netlist only"))
    return fails


def project_files(pr):
    """(files relative to the root, committed?) from git, else a walk."""
    raw = hwcommon.git(pr.root, "ls-files", "-z")
    if raw is not None:
        return sorted(x for x in raw.decode("utf-8", "replace").split("\0") if x), True
    files = []
    for d, dirs, names in os.walk(pr.root):
        dirs[:] = [x for x in dirs if x != ".git"]
        files += [os.path.relpath(os.path.join(d, n), pr.root).replace(os.sep, "/") for n in names]
    return sorted(files), False


def cmd_writers(pr, a, out):
    fails = []
    need(pr, "ownership.csv")
    rows = pr.table("ownership.csv")
    for r in rows:
        where = "ownership.csv %s" % r["path"]
        if r["owner"] not in hwcommon.OWNERS:
            fails.append("%s: owner %r must be script or hand" % (where, r["owner"]))
        path = os.path.join(pr.root, r["path"])
        if not os.path.isfile(path):
            fails.append("%s: the file does not exist" % where)
            continue
        if r["owner"] == "script":
            if not r["writer"]:
                fails.append("%s: script-owned with no writer" % where)
            if r["hash"] and hwcommon.sha256_file(path) != r["hash"]:
                fails.append("%s: changed since the script wrote it (an edit by hand or another tool)" % where)
    files, committed = project_files(pr)
    listed = set(r["path"] for r in rows)
    for f in files:
        if GENERATED_RE.search(f):
            if committed:
                fails.append("%s: a generated artefact is committed (add it to .gitignore)" % f)
            else:
                out("  %s: generated artefact present (not a git repository: cannot tell if committed)" % f)
    rel = pr.p.get("kicad_rel", "hardware")
    prefix = "" if rel == "." else rel.rstrip("/") + "/"

    def in_kicad_folder(f):
        top = f.split("/")[0]
        return f.startswith(prefix) and not (rel == "." and "/" in f and (top in hwcommon.LAYOUT_FOLDERS or
                                                                          top.startswith(".")))
    hand = [f for f in files if in_kicad_folder(f) and hwcommon.is_design_file(f) and f not in listed
            and not GENERATED_RE.search(f)]
    out("design files with no ownership row (hand-owned): %d" % len(hand))
    for f in hand:
        out("  " + f)
    return fails


# ---------------------------------------------------------------- scan

# The path patterns are joined from pieces so that this file, copied into every project, does not
# match its own scan.
HOME = "/" + "Users/|/" + "home/|[A-Za-z]:\\\\" + "Users\\\\"
TEMP = "/" + "private/" + "var/folders/|/" + "var/folders/"
SCAN_PATTERNS = (
    ("machine path", re.compile(r"(?:%s)[^\s\"'<>|:;,)]+|(?:%s)\S+" % (HOME, TEMP))),
    ("email address", re.compile(r"\b[A-Za-z0-9._%+-]+" + "@" + r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bsk-[A-Za-z0-9_-]{20,}\b"
                              r"|\bxox[abpr]-[A-Za-z0-9-]{10,}\b|\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("password or token", re.compile(r"(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|token)\b"
                                     r"\s*[:=]\s*[\"']?([^\s\"']{4,})")),
    ("account or order number", re.compile(r"(?i)\b(?:account|acct|customer|order)\s*(?:no\.?|number|num|id|#)\s*"
                                           r"[:#]?\s*([A-Z0-9][A-Z0-9-]{4,})")),
)
# A kept file that points into the scratch folder names a file that will not be there. The folder's own
# name (the ignore line, the status line) is no pointer, and neither is a brief's "Scratch:" line.
SCRATCH_KIND = "scratch folder path"
SCRATCH_RE = re.compile(r"(?<![\w-])\." + "hwtmp" + r"/[\w<][^\s\"'`<>|;,)]*")
SCRATCH_LINE_RE = re.compile(r"^\s*(?:[-*]\s*)?Scratch(?: folder)?:", re.I)


def in_skill_copy(name):
    """True for a file of the skill's own copy in the project; its text names the scratch folder as a rule."""
    return ("/" + name.replace(os.sep, "/")).find("/%s/" % hwcommon.SKILL_FOLDER) >= 0


def mask(value):
    v = value.strip()
    if len(v) <= 6:
        return "*" * len(v)
    return "%s%s%s" % (v[:2], "*" * min(12, len(v) - 4), v[-2:])


def private_terms(pr):
    path = os.path.join(pr.design, ".private-terms") if pr else None
    if not path or not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [t.strip() for t in f if t.strip() and not t.startswith("#")]


PUBLISHED = "datasheets/"            # makers' documents, saved as published
REVIEWED = "scan-reviewed.csv"       # in design/: hits a person looked at and accepted


def in_published(name):
    """True for a maker's document in datasheets/. The README there is the project's own list."""
    return name.startswith(PUBLISHED) and name.split("!")[0] != PUBLISHED + "README.md"


def scan_text(name, text, terms, people):
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        for kind, rx in SCAN_PATTERNS:
            for m in rx.finditer(line):
                val = m.group(m.lastindex) if m.lastindex else m.group(0)
                if kind == "account or order number" and not re.search(r"\d", val):
                    continue
                found.append((name, n, kind, mask(val)))
        if not SCRATCH_LINE_RE.match(line) and not in_skill_copy(name):
            for m in SCRATCH_RE.finditer(line):
                found.append((name, n, SCRATCH_KIND, mask(m.group(0))))
        low = line.lower()
        for kind, words in (("private term", terms), ("user or host name", people)):
            for t in words:
                if re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(t.lower()), low):
                    found.append((name, n, kind, mask(t)))
        if name.endswith(".net"):
            for m in re.finditer(r'\((source|date)\s+"([^"]+)"', line):
                if m.group(1) == "date" or os.path.isabs(m.group(2)) or re.match(r"^[A-Za-z]:\\", m.group(2)):
                    found.append((name, n, "netlist %s" % m.group(1), mask(m.group(2))))
    return found


def scan_bytes(name, data, terms, people):
    if data[:4] == b"PK\x03\x04":
        import io
        found = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for info in z.infolist():
                    found += scan_bytes("%s!%s" % (name, info.filename), z.read(info), terms, people)
        except zipfile.BadZipFile:
            pass
        return found
    if b"\0" in data[:4096]:
        return []
    return scan_text(name, data.decode("utf-8", "replace"), terms, people)


def cmd_scan(pr, a, out):
    terms = private_terms(pr)
    people = []
    for who in (getpass.getuser(), socket.gethostname().split(".")[0]):
        if who and len(who) >= 3 and who.lower() not in ("root", "user", "runner", "localhost", "admin"):
            people.append(who)
    targets = []
    root = pr.root if pr else os.getcwd()
    if a.targets:
        for t in a.targets:
            if os.path.isdir(t):
                for d, dirs, names in os.walk(t):
                    dirs[:] = sorted(x for x in dirs if x != ".git")
                    targets += [os.path.join(d, n) for n in sorted(names)]
            elif os.path.isfile(t):
                targets.append(t)
            else:
                raise InputError("nothing to scan at %s" % t)
        what = "the files named"
        items = [(os.path.relpath(t, root) if t.startswith(root) else t, None) for t in targets]
    else:
        staged = hwcommon.git(root, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR")
        names = [x for x in (staged or b"").decode("utf-8", "replace").split("\0") if x]
        if names:
            what = "the staged files"
            items = [(n, "index") for n in names]
        else:
            files, _ = project_files(pr)
            what = "the project files"
            items = [(f, None) for f in files]
    found = []
    for name, src in items:
        if name.replace(os.sep, "/").endswith("design/.private-terms"):
            continue
        if src == "index":
            data = hwcommon.git(root, "show", ":" + name)
            if data is None:
                continue
        else:
            path = name if os.path.isabs(name) or not pr else os.path.join(root, name)
            if not os.path.isfile(path):
                path = name
            with open(path, "rb") as f:
                data = f.read()
        found += scan_bytes(name.replace(os.sep, "/"), data, terms, people)
    fails = []
    # An address a maker printed in a saved document is public: counted apart, never a finding.
    published = [x for x in found if x[2] == "email address" and in_published(x[0])]
    found = [x for x in found if x not in published]
    # A hit a person looked at and accepted, recorded in design/scan-reviewed.csv.
    reviewed, accepted = {}, []
    scanned = set(name.replace(os.sep, "/") for name, _ in items)
    for r in (pr.table(REVIEWED) if pr else []):
        where = "design/%s line %d" % (REVIEWED, r["_line"])
        if not r["reason"] or not r["decided_by"]:
            fails.append("%s: the row needs a reason and who decided" % where)
        elif not r["line"].isdigit():
            fails.append("%s: line %r is not a number" % (where, r["line"]))
        else:
            reviewed[(r["file"].replace("\\", "/"), int(r["line"]), r["kind"])] = (r, where)
    for key, (r, where) in sorted(reviewed.items()):
        hits = [x for x in found if x[:3] == key]
        if hits:
            accepted += hits
            out("REVIEWED %s:%d: %s (%s; decided by %s)" % (key + (r["reason"], r["decided_by"])))
        elif key[0].split("!")[0] in scanned:
            fails.append("%s: %s line %d, %s: nothing is found there now (remove the row, or give the new line)"
                         % ((where,) + key))
    found = [x for x in found if x not in accepted]
    for name, n, kind, val in found:
        out("FOUND %s:%d: %s %s" % (name, n, kind, val))
    for x in fails:
        out("FOUND " + x)
    if not items:
        fails.append("no file was scanned")
        out("FOUND no file was scanned: nothing is staged and git tracks no file here, or the folder named is empty "
            "(name the files or the folder to scan)")
    out("scanned %s: %d files; private terms %d; findings %d (values masked)" % (what, len(items), len(terms), len(found)))
    if accepted or reviewed:
        out("reviewed and accepted: %d (design/%s)" % (len(accepted), REVIEWED))
    if published:
        out("in published documents (%s), not counted: %d email address%s" % (
            PUBLISHED, len(published), "" if len(published) == 1 else "es"))
        for name in sorted(set(x[0] for x in published)):
            out("  %s: %d" % (name, sum(x[0] == name for x in published)))
    return fails + ["%s:%d %s" % (x[0], x[1], x[2]) for x in found]


# ---------------------------------------------------------------- impact

def cmd_impact(pr, a, out):
    if not a.targets:
        raise InputError("impact needs an ID, designator or MPN")
    seeds = set(a.targets)
    for t in list(seeds):
        for r in pr.table("parts.csv"):
            if t in hwcommon.split_list(r["refs"]) and r["mpn"]:
                seeds.add(r["mpn"])
        for ref, c in pr.netlist().items():
            if ref == t and c["mpn"]:
                seeds.add(c["mpn"])
    found, frontier = set(), set(seeds)
    for depth in range(3):
        nxt = set()
        for name in ("compliance.csv", "pins.csv", "parts.csv", "constraints.csv", "findings.csv", "net-review.csv",
                     "sections.csv"):
            for r in pr.table(name):
                cells = " ; ".join(str(v) for k, v in r.items() if k != "_line")
                toks = set(re.split(r"[\s;,()\"']+", cells))
                toks |= set(t[:-4] for t in toks if t.lower().endswith(".pdf"))
                toks |= set(m.group(1) for m in map(PIN_KEY_RE.match, toks) if m)     # J2.1 traces to J2
                if frontier & toks:
                    key = (name, r.get("id") or ("%s %s" % (r.get("designator", r.get("refs", r.get("datasheet", ""))),
                                                            r.get("pin", r.get("section", "")))).strip())
                    if key not in found:
                        found.add(key)
                        rid = r.get("id")
                        if rid and depth < 2:
                            nxt.add(rid)
        frontier = nxt - seeds
        seeds |= nxt
    for name, key in sorted(found):
        out("  %s: %s" % (name, key))
    files = [os.path.join("design", f) for f in ("requirements.md", "decisions.md", "status.md")]
    files += [os.path.relpath(p, pr.root) for p in pr.reports()]
    files += [os.path.relpath(p, pr.root) for p in sorted(glob.glob(os.path.join(pr.design, "checklists", "*.md")))]
    for rel in files:
        t = pr.text(rel)
        if not t:
            continue
        for n, line in enumerate(t.splitlines(), 1):
            if any(re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(s), line) for s in a.targets):
                out("  %s:%d: %s" % (rel, n, line.strip()[:120]))
    out("traced from %s (%s): %d table rows" % (", ".join(a.targets), ", ".join(sorted(seeds - set(a.targets))[:12]) or "nothing more",
                                               len(found)))
    return []


# ---------------------------------------------------------------- summary

def unconfirmed_by_kind(pr):
    """{kind: {designator: (unconfirmed, total)}} for microcontrollers, modules and connectors."""
    parts = {}
    for r in pr.table("parts.csv"):
        for ref in hwcommon.split_list(r["refs"]):
            parts[ref] = r
    out = {"microcontroller": {}, "module": {}, "connector": {}}
    for row in pr.table("pins.csv"):
        ref = row["designator"]
        p = parts.get(ref, {})
        text = " ".join([p.get("package", ""), p.get("footprint", ""), p.get("value", "")]).lower()
        if "microcontroller" in [c.lower() for c in hwcommon.split_list(p.get("category", ""))]:
            kind = "microcontroller"
        elif p.get("role") == "radio" or "module" in text:
            kind = "module"
        elif p.get("role") == "connector" or ref_prefix(ref) in ("J", "P", "CN", "X"):
            kind = "connector"
        else:
            continue
        n, t = out[kind].get(ref, (0, 0))
        out[kind][ref] = (n + (row["confirmed"].lower() != "yes"), t + 1)
    return out


WITHDRAWN = "withdrawn"


def requirement_items(pr, prefix, withdrawn=None):
    """{ID: evidence or result text} of the items in force. A withdrawn item, "<ID> Withdrawn (DC-nnn): <old
    text>", is left out and its ID added to the list withdrawn[0]. One marked withdrawn with no DC- ID stays
    in, and its ID is added to withdrawn[1]."""
    text = pr.text(os.path.join("design", "requirements.md")) or ""
    items, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^(%s-\d+)\b[\s:*_]*(.*)$" % prefix, line.strip())
        if m:
            cur = m.group(1)
            w = re.match(r"^%s\b\s*(\(\s*DC-\d{3,}[^)]*\))?" % WITHDRAWN, m.group(2), re.I)
            if w and w.group(1):
                items.pop(cur, None)
                if withdrawn is not None:
                    withdrawn[0].append(cur)
                cur = None
                continue
            if w and withdrawn is not None:
                withdrawn[1].append(cur)
            items[cur] = ""
        elif cur and re.match(r"^\s+(Evidence|Result):", line):
            items[cur] = line.split(":", 1)[1].strip()
        elif not line.startswith(" "):
            cur = None
    return items


def done_lists(pr):
    """[(stage, [(item, n, m)], [items not countable from the files])]."""
    exists = lambda rel: os.path.exists(os.path.join(pr.root, rel))  # noqa: E731
    stages = []
    layout = ["README.md", os.path.join(hwcommon.SKILL_FOLDER, "build.py"), ".gitignore", ".gitattributes",
              pr.p.get("kicad_rel", "hardware"), "datasheets", "design", "docs", "firmware"]
    dfiles = ["requirements.md", "decisions.md", "status.md", "compliance.csv", "sections.csv", "pins.csv", "parts.csv",
              "fab-capabilities.csv", "constraints.csv", "findings.csv", "net-review.csv", "ownership.csv"]
    gi = pr.text(".gitignore") or ""
    stages.append(("ST0", [
        ("git repository", int(exists(".git")), 1),
        ("project layout", sum(exists(x) for x in layout), len(layout)),
        (".gitignore holds design/.private-terms", int(".private-terms" in gi), 1),
        (".gitignore holds KiCad's local settings (*.kicad_prl)", int("kicad_prl" in gi), 1),
        ("design/ files from the templates", sum(exists(os.path.join("design", x)) for x in dfiles), len(dfiles)),
        ("checklists copied", sum(exists(os.path.join("design", "checklists", x + ".md")) for x in CHECKLIST_COPIES),
         len(CHECKLIST_COPIES)),
        ("tool check recorded in status.md", int(bool(re.search(r"KiCad \d", pr.status_field("Tools")))), 1),
        ("skills version recorded", int(bool(re.search(r"\d+\.\d+", pr.status_field("Skills version")))), 1),
    ], ["router cloned and tested", "adoption report (existing projects)"]))
    fr, qc = requirement_items(pr, "FR"), requirement_items(pr, "QC")
    heads = ["Environment profile", "Misuse cases", "User journey", "Board profile", "Test points"]
    found = [(h, pr.section(os.path.join("design", "requirements.md"), h)) for h in heads]
    gone, empty = [h for h, s in found if s is None], [h for h, s in found if s == []]
    note = "; ".join(x for x in ("not found: " + ", ".join(gone) if gone else "",
                                 "empty: " + ", ".join(empty) if empty else "") if x)
    stages.append(("ST1", [
        ("FR- and QC- items present", int(bool(fr)) + int(bool(qc)), 2),
        ("requirements sections filled", sum(bool(s) for _, s in found), len(heads), note),
    ], ["each item's source quoted"]))
    parts = [r for r in pr.table("parts.csv") if r["mpn"]]
    comp_mpns = set(r["mpn"] for r in pr.table("compliance.csv"))
    sec = pr.table("sections.csv")
    pin_refs = set(r["designator"] for r in pr.table("pins.csv"))
    st3 = [
        ("datasheet saved (datasheets/<MPN>.pdf)", sum(exists(os.path.join("datasheets", safe(r["mpn"]) + ".pdf")) for r in parts)),
        ("parts row complete (role)", sum(bool(r["role"]) for r in parts)),
        ("section inventory, none unclaimed", sum(bool([s for s in sec if s["datasheet"].startswith(safe(r["mpn"]))])
                                                  and not [s for s in sec if s["datasheet"].startswith(safe(r["mpn"]))
                                                           and not s["claimed_by"]] for r in parts)),
        ("compliance rows", sum(r["mpn"] in comp_mpns for r in parts)),
        ("compliance_done yes", sum(r["compliance_done"].lower() == "yes" for r in parts)),
        ("pin table (pins_done yes)", sum(r["pins_done"].lower() == "yes" for r in parts)),
        ("pins.csv rows for parts with pins", sum(any(x in pin_refs for x in hwcommon.split_list(r["refs"])) for r in parts
                                                 if ref_prefix(hwcommon.split_list(r["refs"])[0] if r["refs"] else "")
                                                 in ("U", "IC", "J", "P", "CN", "X", "Q", "D", "Y", "SW"))),
    ]
    with_pins = sum(1 for r in parts if ref_prefix(hwcommon.split_list(r["refs"])[0] if r["refs"] else "")
                    in ("U", "IC", "J", "P", "CN", "X", "Q", "D", "Y", "SW"))
    stages.append(("ST3", [(t, n, with_pins if t.startswith("pins.csv") else len(parts)) for t, n in st3],
                   ["errata and delegated documents fetched", "passes per the setting", "typical application listed",
                    "pin check by a second worker"]))
    nr = pr.table("net-review.csv")
    calcs = glob.glob(os.path.join(pr.design, "calcs", "*.py"))
    fitted = [r for r in pr.table("parts.csv") if r["variant"].strip().lower() != "not fitted"]
    stages.append(("ST5", [
        ("four sourcing fields", sum(all(r[c] for c in ("manufacturer", "mpn", "supplier", "supplier_pn")) for r in fitted),
         len(fitted)),
        ("review-list items closed with a reason", sum(bool(r["reason"]) for r in nr), len(nr)),
        ("calc scripts with output", sum(os.path.isfile(p[:-3] + ".txt") for p in calcs), len(calcs)),
    ], ["ERC clean (run build.py)", "netlist read back", "footprints and models (table_check.py parts)",
        "typical application compared", "user-journey walk-through", "notes pages"]))
    fd = pr.table("findings.csv")
    still = sum(is_open(r["status"]) for r in fd)
    stages.append(("ST6", [("findings triaged", len(fd) - still, len(fd)), ("findings still open", still, len(fd))],
                   ["review reports", "checklist results (table_check.py checklists)"]))
    caps = pr.table("fab-capabilities.csv")
    cons = pr.table("constraints.csv")
    carried = [r for r in pr.table("compliance.csv") if r["schematic_result"] == "carried"]
    froms = set(c["from"] for c in cons) | set(x for r in carried for x in hwcommon.split_list(r["carried_to"])
                                               if x in set(c["id"] for c in cons))
    stages.append(("ST7", [
        ("capabilities sourced", sum(bool(r["source_url"]) and bool(DATE_RE.match(r["read_on"])) for r in caps), len(caps)),
        ("carried rows with a constraint", sum(r["id"] in froms or bool(set(hwcommon.split_list(r["carried_to"])) & froms)
                                               for r in carried), len(carried)),
        ("constraints with a sufficiency verdict", sum(bool(re.match(r"^(whole|partial|no)\b", c["sufficiency"].lower()))
                                                       for c in cons), len(cons)),
    ], ["rule and project files generated", "fabcap, constraints, suppress clean (run them)"]))
    stages.append(("ST11", [("carried rows with a board result", sum(r["board_result"] not in ("", "open") for r in carried),
                             len(carried))],
                   ["DRC clean", "review verdicts (table_check.py constraints)", "findings triaged"]))
    stages.append(("ST2, ST4, ST8 to ST10, ST12, ST13", [], ["their Done items are reports, renders and order files; "
                                                            "count them from the reports"]))
    return stages


def cmd_summary(pr, a, out):
    comp = pr.table("compliance.csv")
    wd = ([], [])
    fr, qc = requirement_items(pr, "FR", wd), requirement_items(pr, "QC", wd)
    ev = lambda d: sum(1 for v in d.values() if v and not v.startswith("("))  # noqa: E731
    out("requirements: FR- %d of %d with evidence; QC- %d of %d with results%s%s" % (
        ev(fr), len(fr), ev(qc), len(qc), "; withdrawn: " + ", ".join(wd[0]) if wd[0] else "",
        "; marked withdrawn with no DC- decision (still counted): " + ", ".join(wd[1]) if wd[1] else ""))
    by = {}
    for r in comp:
        by[r["schematic_result"] or "(empty)"] = by.get(r["schematic_result"] or "(empty)", 0) + 1
    out("datasheet rows by schematic result: %s" % (", ".join("%s %d" % kv for kv in sorted(by.items())) or "none"))
    cons_ids = set(c["id"] for c in pr.table("constraints.csv"))
    carried = [r for r in comp if r["schematic_result"] == "carried"]
    with_c = sum(1 for r in carried if set(hwcommon.split_list(r["carried_to"])) & cons_ids
                 or any(c["from"] == r["id"] for c in pr.table("constraints.csv")))
    out("layout rows carried: %d, with constraints: %d" % (len(carried), with_c))
    sec = pr.table("sections.csv")
    zero = [s for s in sec if s["category"] in hwcommon.SECTIONS_NEEDING_ROWS and not any(
        (s[c] or "0") not in ("0", "") for c in ("rows_logical", "rows_electrical", "rows_physical"))]
    out("sections: %d; sensitive with no rows: %d (%d without a note); claimed by no pass: %d"
        % (len(sec), len(zero), sum(1 for s in zero if not s["note"]), sum(1 for s in sec if not s["claimed_by"])))
    fd = pr.table("findings.csv")
    # An extraction miss is a datasheet instruction with no DS- row, so its location names a part or a
    # datasheet. A row of that category about anything else is listed, not counted.
    named = set(x for r in pr.table("parts.csv") for x in hwcommon.split_list(r["refs"]) + [r["mpn"], r["datasheet"]] if x)
    named |= set(x for r in comp for x in (r["designator"], r["mpn"], r["datasheet"]) if x)
    misses = [r for r in fd if r["category"] == "extraction miss"]
    other = [r["id"] for r in misses if not any(re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(x), r["location"])
                                                 for x in named)]
    out("extraction misses found: %d%s" % (len(misses) - len(other), (
        " (rows of that category that name no part or datasheet: %d: %s)" % (len(other), ", ".join(other[:12]))) if other else ""))
    uc = unconfirmed_by_kind(pr)
    for kind in ("microcontroller", "module", "connector"):
        d = uc[kind]
        out("unconfirmed pin rows, %ss: %s" % (kind, ", ".join("%s %d of %d" % (r, n, t) for r, (n, t) in
                                                              sorted(d.items(), key=lambda kv: hwcommon.ref_key(kv[0])))
                                               or "none with pin rows"))
    parts = pr.table("parts.csv")
    have_pins = set(r["designator"] for r in pr.table("pins.csv"))
    nopins = [ref for r in parts for ref in hwcommon.split_list(r["refs"])
              if ref_prefix(ref) in ("U", "IC", "J", "P", "CN", "X") and (ref not in have_pins or r["pins_done"].lower() != "yes")]
    out("parts with no checked pin table: %s" % (", ".join(sorted(nopins, key=hwcommon.ref_key)) or "none"))
    dates = sorted(r["checked"] for r in parts if DATE_RE.match(r["checked"]))
    out("parts check: stock and price checked %s" % ("from %s to %s" % (dates[0], dates[-1]) if dates else "never"))
    v = violations(pr)
    out("open violations: %d%s" % (len(v), (" (%s)" % "; ".join(x.split()[0] for x in v[:10])) if v else ""))
    proposed = [r["id"] for r in comp + fd if r["decision"] == hwcommon.PROPOSED]
    out("open decisions (proposed): %d%s" % (len(proposed), (" (%s)" % ", ".join(proposed[:12])) if proposed else ""))
    entries = hwcommon.decision_entries(pr.design)
    waivers = [e["id"] for e in entries if (e["fields"].get("Kind", "").lower() == "waiver" if not e["old"]
                                            else "waiver" in e["text"].split("\n")[0].lower())]
    closed = set(e["id"] for e in entries if re.match(r"^(closed|superseded)", e["fields"].get("Status", ""), re.I)
                 or (e["old"] and re.search(r"\b(closes|closed)\b", e["text"].split("\n")[0])))
    out("open waivers: %d%s" % (len([w for w in waivers if w not in closed]),
                                (" (%s)" % ", ".join(w for w in waivers if w not in closed)) if waivers else ""))
    unseen = unseen_decisions(entries)
    out("decided on the user's behalf, not yet seen by the user: %d%s" % (len(unseen),
                                                                         (" (%s)" % ", ".join(unseen)) if unseen else ""))
    reopened = [r["id"] for r in comp if r["schematic_result"] == "open" and r["evidence"]]
    out("rows reopened (open with earlier evidence): %d%s" % (len(reopened), (" (%s)" % ", ".join(reopened[:12])) if reopened else ""))
    bl = pr.baselines()
    if not bl:
        out("review baselines: none recorded in status.md")
    for kind, br, commit in bl:
        diff = hwcommon.git(pr.root, "diff", "--name-only", commit, "--")
        if diff is None:
            out("files changed since %s review %s (%s): cannot tell (no git or unknown commit)" % (kind, br, commit))
            continue
        new = hwcommon.git(pr.root, "ls-files", "--others", "--exclude-standard") or b""
        names = sorted(set(diff.decode().split()) | set(new.decode().split()))
        out("files changed since %s review %s (%s): %d%s" % (kind, br, commit, len(names),
                                                              "".join("\n    " + n for n in names[:40])))
    out("Done lists (n of m where the files can count it):")
    for stage, items, other in done_lists(pr):
        out("  %s: %s" % (stage, "; ".join("%s %d of %d%s" % (it[0], it[1], it[2], " (%s)" % it[3] if it[3:] and it[3] else "")
                                           for it in items) or "none counted"))
        if other:
            out("      not counted: %s" % "; ".join(other))
    return []


# ---------------------------------------------------------------- requirements

REQUIREMENTS_CHECKPOINT = "ST1"    # requirements: gaps in the structure fail from here on
PRIORITIES = ("must have", "wanted")
TC_KINDS = ("needs the user's answer", "needs research", "proposed by a worker")
TC_FORM = "TC-nnn; <state>; <kind>; <question or proposal>; <item>"
TC_STATE_RE = re.compile(r"^(?:open|(?:answered|withdrawn)\s*\(\s*(DC-\d{3,})\s*\))$", re.I)
REQ_ITEM_RE = re.compile(r"^[-*\s]*((FR|QC)-(\d+))\b[\s:*_]*(.*)$")
TO_CONFIRM_RE = re.compile(r"\bto (?:be )?confirm(?:ed)?\b|\bTBC\b|\bTBD\b|\bopen (?:question|point)s?\b", re.I)
SOURCE_RE = re.compile(r"\bsource\b|\buser\b|\bworker\b|\bproposed\b|does not apply|\bstandard\b|datasheet|https?://"
                       r"|\b(?:DC|BR|DS|TC)-\d", re.I)


def cmd_requirements(pr, a, out):
    """The structure of design/requirements.md. A fault of form fails in every run. A gap (a part of the
    template not filled) is listed, and fails from --stage ST1."""
    rel = "design/requirements.md"
    text = pr.text(os.path.join("design", "requirements.md"))
    if text is None:
        raise NotRun("%s not present" % rel, REQUIREMENTS_CHECKPOINT)
    dcs = pr.decisions()
    fails, gaps = [], []
    at = lambda n: "%s line %d" % (rel, n)  # noqa: E731
    section, item = "", None
    items, order, last = {}, [], {}             # ID -> {"line", "text", "withdrawn"}
    tcs, tc_first, tc_last = [], {}, 0
    marked, env = [], []                        # (line, section, item ID, text); [line, name, text]
    for n, line in enumerate(text.splitlines(), 1):
        h = re.match(r"^(#{1,6})\s+(.*)$", line)
        if h:
            item = None
            if len(h.group(1)) <= 2:
                section = re.sub(r"\s*\(.*$", "", h.group(2)).strip()
            continue
        if not line.strip():
            continue
        low = section.lower()
        if low.startswith("to confirm"):
            body = re.sub(r"^\s*[-*]\s*", "", line).strip()
            if body.strip(" .").lower() == "none":
                continue
            m = re.match(r"^(TC-(\d+))\b", body)
            if not m or line[:1] in " \t":
                fails.append("%s: not a To confirm line; each line there is %s" % (at(n), TC_FORM))
                continue
            tid, num = m.group(1), int(m.group(2))
            if tid in tc_first:
                fails.append("%s: %s is used twice (first at line %d); an ID is never reused" % (at(n), tid, tc_first[tid]))
            elif num <= tc_last:
                fails.append("%s: %s comes after TC-%03d; IDs rise in file order" % (at(n), tid, tc_last))
            tc_first.setdefault(tid, n)
            tc_last = max(tc_last, num)
            parts = [x.strip() for x in body.split(";")]
            if len(parts) < 5:
                fails.append("%s: %s: a To confirm line is %s" % (at(n), tid, TC_FORM))
                tcs.append({"id": tid, "state": "", "item": ""})
                continue
            state, kind, question, where = parts[1], parts[2], "; ".join(parts[3:-1]).strip(), parts[-1]
            s = TC_STATE_RE.match(state)
            if not s:
                fails.append("%s: %s state %r must be open, answered (DC-nnn) or withdrawn (DC-nnn)" % (at(n), tid, state))
            elif s.group(1) and s.group(1) not in dcs:
                fails.append("%s: %s names %s, which is not in the decision log" % (at(n), tid, s.group(1)))
            if kind.lower() not in TC_KINDS:
                fails.append("%s: %s kind %r must be one of: %s" % (at(n), tid, kind, ", ".join(TC_KINDS)))
            if not question:
                fails.append("%s: %s has no question or proposal" % (at(n), tid))
            if not where:
                fails.append("%s: %s names no item (an FR- or QC- ID, or a section)" % (at(n), tid))
            tcs.append({"id": tid, "state": state.split("(")[0].strip().lower() if s else "", "item": where})
            continue
        m = REQ_ITEM_RE.match(line) if line[:1] not in " \t" else None
        if m:
            iid, prefix, num = m.group(1), m.group(2), int(m.group(3))
            if iid in items:
                fails.append("%s: %s is used twice (first at line %d); an ID is never reused" % (at(n), iid, items[iid]["line"]))
                item = None
            else:
                if num <= last.get(prefix, 0):
                    fails.append("%s: %s comes after %s-%02d; IDs rise in file order" % (at(n), iid, prefix, last[prefix]))
                w = re.match(r"^%s\b\s*(?:\(\s*(DC-\d{3,})[^)]*\))?" % WITHDRAWN, m.group(4), re.I)
                items[iid] = {"line": n, "text": line, "withdrawn": bool(w)}
                order.append(iid)
                item = iid
                if w and not w.group(1):
                    fails.append("%s: %s is marked withdrawn with no decision; write \"%s Withdrawn (DC-nnn): <the old text>\""
                                 % (at(n), iid, iid))
                elif w and w.group(1) not in dcs:
                    fails.append("%s: %s is withdrawn by %s, which is not in the decision log" % (at(n), iid, w.group(1)))
            last[prefix] = max(last.get(prefix, 0), num)
        elif line[:1] in " \t" and item:
            items[item]["text"] += "\n" + line
        else:
            item = None
        if low.startswith("environment profile"):
            if line[:1] in " \t" and env:
                env[-1][2] += " " + line.strip()
            else:
                body = re.sub(r"^\s*[-*]\s*", "", line).strip()
                env.append([n, body.split(":")[0].strip(), body])
        if low.startswith("board profile") and re.match(r"^\s*[-*|]", line):
            parts = [x.strip() for x in re.split(r"[;:|]", re.sub(r"^\s*[-*|]\s*", "", line)) if x.strip()]
            name = next((s for s in SWITCHES if parts and s.lower() == parts[0].lower()), None)
            if name and len(parts) == 2:
                gaps.append("%s: board profile row \"%s\" has no reason; write \"%s; on|off; <reason>\"" % (at(n), name, name))
        covered_item = item if item and not items[item]["withdrawn"] else None
        if (TO_CONFIRM_RE.search(line) or low.startswith("open")) and not (item and items[item]["withdrawn"]):
            marked.append((n, section, covered_item, line))
    # every item in force has a priority and a source
    for iid in order:
        it = items[iid]
        if it["withdrawn"]:
            continue
        p = re.search(r"\bPriority:\s*([^.;\n]*)", it["text"])
        if not p:
            gaps.append("%s: %s has no Priority (%s)" % (at(it["line"]), iid, " or ".join(PRIORITIES)))
        elif p.group(1).strip().lower() not in PRIORITIES:
            fails.append("%s: %s Priority %r must be %s" % (at(it["line"]), iid, p.group(1).strip(), " or ".join(PRIORITIES)))
        if not re.search(r"\bSource:\s*\S", it["text"]):
            gaps.append("%s: %s has no Source (who asked for it, and when)" % (at(it["line"]), iid))
    for n, name, body in env:
        if not SOURCE_RE.search(body):
            gaps.append("%s: environment profile row \"%s\" names no source; answer it with its source, or write "
                        "\"does not apply\"" % (at(n), name))
    # a line marked to confirm is in the To confirm list: by its TC- ID, by its item, or by its section
    listed = set(t["id"] for t in tcs)
    by_section = {}
    for n, sec, iid, line in marked:
        if set(re.findall(r"\bTC-\d+\b", line)) & listed:
            continue
        if iid:
            if not any(re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(iid), t["item"]) for t in tcs):
                gaps.append("%s: marked to confirm, and not in the To confirm list (no line there names %s)" % (at(n), iid))
            continue
        by_section.setdefault(sec, []).append(n)
    for sec, lines in sorted(by_section.items(), key=lambda kv: kv[1][0]):
        have = sum(1 for t in tcs if sec and sec.lower() in t["item"].lower())
        for n in lines[have:]:
            gaps.append("%s: marked to confirm, and not in the To confirm list (give the line its TC- ID, or add a line "
                        "that names \"%s\")" % (at(n), sec or "the file"))
    # a decision that says it changes the requirements is cited where it changed them
    for e in hwcommon.decision_entries(pr.design):
        if e["old"] or e["fields"].get("Status", "").lower().startswith("superseded"):
            continue
        what = affects_parts(e["fields"].get("Affects", "")).get("requirements", "").strip(" .")
        if what and what.lower() != "none" and not re.search(r"\b%s\b" % re.escape(e["id"]), text):
            gaps.append("design/decisions.md: %s says it affects the requirements (%s), and %s does not cite %s"
                        % (e["id"], what, rel, e["id"]))
    live = [i for i in order if not items[i]["withdrawn"]]
    out("items: FR %d, QC %d in force; withdrawn %d" % (sum(i.startswith("FR") for i in live),
                                                         sum(i.startswith("QC") for i in live), len(order) - len(live)))
    out("To confirm lines: %d (open %d, answered %d, withdrawn %d)" % (
        len(tcs), sum(t["state"] == "open" for t in tcs), sum(t["state"] == "answered" for t in tcs),
        sum(t["state"] == "withdrawn" for t in tcs)))
    if stage_at_least(a, REQUIREMENTS_CHECKPOINT):
        out("gaps: %d" % len(gaps))
        return fails + gaps
    out("gaps: %d%s" % (len(gaps), " (listed; a fail from --stage %s on)" % REQUIREMENTS_CHECKPOINT if gaps else ""))
    for g in gaps:
        out("  " + g)
    return fails


# ---------------------------------------------------------------- datasheets

DATASHEET_FOLDER = "datasheets"
DATASHEET_CHECKPOINT = "ST6"       # datasheets: a folder that is not there fails from here on
PDF_SETTING = "Third-party PDFs committed"
NOT_COMMITTED = "not committed"


def cmd_datasheets(pr, a, out):
    """Every document in datasheets/ has a line in its README.md and a text extract beside it."""
    folder = os.path.join(pr.root, DATASHEET_FOLDER)
    if not os.path.isdir(folder):
        # no folder holds no document: nothing to check, until the schematic checkpoint asks for the folder
        out("%s/ not present: no document to check" % DATASHEET_FOLDER)
        if stage_at_least(a, DATASHEET_CHECKPOINT):
            return ["%s/ not present (a fail from --stage %s on)" % (DATASHEET_FOLDER, DATASHEET_CHECKPOINT)]
        return []
    fails = []
    names = sorted(n for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n)) and not n.startswith("."))
    docs = [n for n in names if n != "README.md" and not n.lower().endswith(".txt")]
    texts = [n for n in names if n.lower().endswith(".txt")]
    setting = pr.status_field(PDF_SETTING).strip().lower()
    keep_out = setting.startswith("no")
    out("%s: %s" % (PDF_SETTING, "no (a PDF is listed with its URL, and stays out of git)" if keep_out else
                    "yes" if setting.startswith("yes") else "not set in design/status.md, read as yes"))
    readme = pr.text(os.path.join(DATASHEET_FOLDER, "README.md"))
    if readme is None:
        fails.append("%s/README.md is not there; it lists every document with its source" % DATASHEET_FOLDER)
    lines = [(n, line) for n, line in enumerate((readme or "").splitlines(), 1) if line.strip() and not line.startswith("#")]

    def line_of(name):
        rx = re.compile(r"(?<![\w.+-])%s(?![\w+-])(?!\.\w)" % re.escape(name), re.I)
        return next(((n, line) for n, line in lines if rx.search(re.sub(r"https?://\S+", " ", line))), None)

    not_committed = []
    for doc in docs:
        hit = line_of(doc)
        where = "%s/%s" % (DATASHEET_FOLDER, doc)
        if readme is not None and not hit:
            fails.append("%s: no line in %s/README.md names it" % (where, DATASHEET_FOLDER))
        stem = os.path.splitext(doc)[0]
        extract = next((t for t in texts if os.path.splitext(t)[0].lower() == stem.lower()), None)
        if not extract:
            fails.append("%s: no text extract (%s.txt) beside it" % (where, stem))
        elif os.path.getsize(os.path.join(folder, extract)) == 0:
            fails.append("%s/%s: the text extract is empty" % (DATASHEET_FOLDER, extract))
        is_pdf = doc.lower().endswith(".pdf")
        says = bool(hit) and NOT_COMMITTED in hit[1].lower()
        if keep_out and is_pdf and hit and not says:
            fails.append("%s/README.md line %d: %s: the setting \"%s: no\" is in force; the line says \"%s\" and gives "
                         "the URL" % (DATASHEET_FOLDER, hit[0], doc, PDF_SETTING, NOT_COMMITTED))
        if says or (keep_out and is_pdf):
            not_committed.append(doc)
    for n, line in lines:
        low = line.lower()
        if NOT_COMMITTED in low and not re.search(r"https?://\S+", line):
            fails.append("%s/README.md line %d: says \"%s\" and gives no URL to fetch the document from"
                         % (DATASHEET_FOLDER, n, NOT_COMMITTED))
        for m in re.finditer(r"(?<![\w./+-])([\w+-][\w.+-]*\.pdf)\b", re.sub(r"https?://\S+", " ", line), re.I):
            if m.group(1).lower() not in [d.lower() for d in docs] and NOT_COMMITTED not in low and not keep_out:
                fails.append("%s/README.md line %d: names %s, which is not in %s/ (fetch it, or say \"%s\" with its URL)"
                             % (DATASHEET_FOLDER, n, m.group(1), DATASHEET_FOLDER, NOT_COMMITTED))
    for t in texts:
        stem = os.path.splitext(t)[0]
        if readme is not None and not any(os.path.splitext(d)[0].lower() == stem.lower() for d in docs) \
                and not any(re.search(r"(?<![\w.+-])%s(?![\w+-])" % re.escape(stem), line, re.I) for _, line in lines):
            fails.append("%s/%s: a text extract of a document no line in %s/README.md names"
                         % (DATASHEET_FOLDER, t, DATASHEET_FOLDER))
    tracked = hwcommon.git(pr.root, "ls-files", "-z", "--", DATASHEET_FOLDER)
    if tracked is None:
        out("not a git repository: what git tracks was not checked")
    else:
        held = set(x.split("/")[-1] for x in tracked.decode("utf-8", "replace").split("\0") if x)
        for doc in not_committed:
            if doc in held:
                fails.append("%s/%s: git tracks it, and it is not to be committed (remove it from git, keep the file)"
                             % (DATASHEET_FOLDER, doc))
    out("documents: %d; text extracts: %d; not committed: %d" % (len(docs), len(texts), len(not_committed)))
    return fails


# ---------------------------------------------------------------- parts-totals

def cmd_parts_totals(pr, a, out):
    """Counts and cost of design/parts.csv, from the rows."""
    need(pr, "parts.csv")
    rows = pr.table("parts.csv")
    refs = lambda r: hwcommon.split_list(r["refs"])  # noqa: E731
    is_fitted = lambda r: r["variant"].strip().lower() != "not fitted"  # noqa: E731
    fitted = [r for r in rows if is_fitted(r)]
    n = lambda rs: sum(len(refs(r)) for r in rs)  # noqa: E731
    out("parts rows: %d (fitted %d, not fitted %d)" % (len(rows), len(fitted), len(rows) - len(fitted)))
    out("designators: %d (fitted %d, not fitted %d)" % (n(rows), n(fitted), n(rows) - n(fitted)))
    for col in ("role", "category", "supplier"):
        groups = {}
        for r in rows:
            for key in (hwcommon.split_list(r[col]) if col == "category" else [r[col]]) or [""]:
                groups.setdefault(key or "(none)", []).append(r)
        out("by %s:" % col)
        for key in sorted(groups, key=lambda k: (k == "(none)", k.lower())):
            out("  %s: %d rows, %d designators" % (key, len(groups[key]), n(groups[key])))
    for col in ("unit_price", "qty_price"):
        total, priced, without = 0.0, 0, []
        for r in fitted:
            name = ";".join(refs(r)) or "line %d" % r["_line"]
            try:
                total += float(r[col]) * len(refs(r))
                priced += 1
            except ValueError:
                without.append(name)
                if r[col]:
                    out("  %s: %s %r is not a number" % (name, col, r[col]))
        out("cost per board, %s: %.4g from %d priced rows (price times designators, fitted rows)" % (col, total, priced))
        out("fitted rows with no %s: %d%s" % (col, len(without), " (%s)" % ", ".join(without) if without else ""))
    seen = {}
    for r in rows:
        for ref in refs(r):
            seen[ref] = seen.get(ref, 0) + 1
    twice = sorted((ref for ref, c in seen.items() if c > 1), key=hwcommon.ref_key)
    out("designators in more than one row: %d" % len(twice))
    for ref in twice:
        out("  %s is in %d rows" % (ref, seen[ref]))
    return []


# ---------------------------------------------------------------- log-append, set-row

def one_line(name, value):
    if "\n" in value or "\r" in value:
        raise InputError("%s must be one line" % name)
    return value.strip()


def cmd_log_append(pr, a, out):
    """Append one entry to design/decisions.md with the next free DC- number. Earlier entries keep
    their bytes: the file is only added to."""
    if a.targets:
        raise InputError("log-append takes no other word (%s); give the entry with its options" % ", ".join(a.targets))
    kind = one_line("--kind", a.kind or "").lower()
    if kind not in hwcommon.DECISION_KINDS:
        raise InputError("--kind must be one of: %s" % ", ".join(hwcommon.DECISION_KINDS))
    answered = kind == hwcommon.ANSWERED_KIND
    none_all = "; ".join("%s none" % p for p in hwcommon.AFFECTS_PARTS)
    f = {"statement": one_line("--statement", a.statement or ""), "by": one_line("--by", a.by or ""),
         "stage": one_line("--stage", a.stage or ""), "reason": one_line("--reason", a.reason or ""),
         "options": one_line("--options", a.options or ("none" if answered else "")),
         "affects": one_line("--affects", a.affects or (none_all if answered else "")),
         "status": one_line("--status", a.status or (hwcommon.ANSWERED_STATUS if answered else "in force"))}
    for name in ("statement", "by", "stage", "options", "reason", "affects"):
        if not f[name]:
            raise InputError("log-append needs --%s" % name)
    if hwcommon.DC_RE.search(f["statement"]) and re.search(r"\(DC-\d+\)\s*$", f["statement"]):
        raise InputError("--statement: leave the ID out; log-append gives the entry its number")
    if not re.fullmatch(r"user|coordinator|worker BR-\d+-\d+", f["by"]):
        raise InputError("--by must be user, coordinator or \"worker BR-nn-nn\"")
    if not re.fullmatch(r"ST\d+(?:\s*(?:,|and|to)\s*ST\d+)*", f["stage"]):
        raise InputError("--stage takes a stage such as ST6, or several: \"ST5, ST6\"")
    parts = affects_parts(f["affects"])
    missing = [p for p in hwcommon.AFFECTS_PARTS if not parts.get(p)]
    if missing:
        raise InputError("--affects must hold all of: %s, each with its effect or \"none\" (missing: %s)"
                         % (none_all.replace(" none", " <...>"), ", ".join(missing)))
    if not any(f["status"].lower().startswith(s) for s in hwcommon.DECISION_STATUS):
        raise InputError("--status must start with one of: %s" % ", ".join(hwcommon.DECISION_STATUS))
    seen = one_line("--seen", a.seen or "no").lower()
    if seen not in ("yes", "no"):
        raise InputError("--seen must be yes or no")
    path = os.path.join(pr.design, "decisions.md")
    data = b""
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            data = fh.read()
    known = [int(x) for x in re.findall(r"\bDC-(\d{3,})\b", data.decode("utf-8", "replace"))]
    have = hwcommon.decision_ids(pr.design)
    back = hwcommon.DC_RE.findall(one_line("--replaces", a.replaces or ""))
    if a.replaces and not back:
        raise InputError("--replaces takes the DC- IDs this entry changes")
    gone = [x for x in back if x not in have]
    if gone:
        raise InputError("--replaces names %s, which is not in the log" % ", ".join(gone))
    new = "DC-%03d" % (max(known or [0]) + 1)
    day = datetime.date.today().isoformat()
    who = f["by"] if f["by"] == "user" else "%s; seen by user: %s" % (f["by"], "yes, " + day if seen == "yes" else "no")
    lines = ["## %s (%s)" % (f["statement"], new), "Kind: %s" % kind, "Decided by: %s" % who, "Date: %s" % day,
             "Stage: %s" % f["stage"], "Options: %s" % f["options"], "Reason: %s" % f["reason"],
             "Affects: %s" % f["affects"], "Status: %s" % f["status"]]
    if back:
        lines.append("Replaces: %s" % ", ".join(back))
    lead = b"# Decisions\n\n" if not data.strip() else b"\n" if data.endswith(b"\n") else b"\n\n"
    os.makedirs(pr.design, exist_ok=True)
    with open(path, "ab") as fh:
        fh.write(lead + ("\n".join(lines) + "\n").encode("utf-8"))
    out("appended %s to design/decisions.md" % new)
    for old in back:
        out("  now set the Status of %s to \"superseded by %s\" (log-append does not change an earlier entry)" % (old, new))
    return []


# Tables whose first column alone does not name one row.
ROW_KEYS = {"pins.csv": ("designator", "pin"), "sections.csv": ("datasheet", "section"),
            "scan-reviewed.csv": ("file", "line", "kind")}


def csv_line(values):
    import io
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(values)
    return buf.getvalue()


def cmd_set_row(pr, a, out):
    """Change the named columns of one row of a table in design/, or add the row when no row has the
    key. Every other line of the file keeps its bytes."""
    usage = "set-row <table>.csv <key> column=value [column=value ...]"
    if len(a.targets) < 3 or not all("=" in x for x in a.targets[2:]):
        raise InputError("%s: give at least one column=value" % usage)
    name, key = os.path.basename(a.targets[0]), one_line("the key", a.targets[1])
    if not name.endswith(".csv"):
        raise InputError("%s: %s is no table; a table in design/ ends in .csv" % (usage, a.targets[0]))
    path = os.path.join(pr.design, name)
    rel = "design/%s" % name
    if not os.path.isfile(path) and name not in hwcommon.TABLES:
        raise InputError("%s is not there, and no template names its columns" % rel)
    rows = hwcommon.read_table(path)            # stops on a wrong header or a row that does not parse
    data = b""
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            data = fh.read()
    text = data.decode("utf-8")
    phys = text.splitlines(keepends=True)
    cols = tuple(h.strip() for h in next(csv.reader([phys[0]]))) if phys else hwcommon.TABLES[name]
    key_cols = ROW_KEYS.get(name, cols[:1])
    key_vals = [x.strip() for x in key.split(",")] if len(key_cols) > 1 else [key]
    if len(key_vals) != len(key_cols) or not all(key_vals):
        raise InputError("%s: the key of a row is %s; give it as \"%s\"" % (rel, ",".join(key_cols), ",".join(
            "<%s>" % c for c in key_cols)))
    change = {}
    for pair in a.targets[2:]:
        col, value = pair.split("=", 1)
        col = col.strip()
        if col not in cols:
            raise InputError("%s has no column %r (the columns: %s)" % (rel, col, ", ".join(cols)))
        if col in key_cols:
            raise InputError("%s: %s is the key of the row; set-row does not change a key (add the new row, and "
                             "remove the old one by hand)" % (rel, col))
        change[col] = one_line("the value of %s" % col, value)
    hits = [r for r in rows if [r[c] for c in key_cols] == key_vals]
    if len(hits) > 1:
        raise InputError("%s: %d rows have the key %s (lines %s); set-row changes one row" % (
            rel, len(hits), key, ", ".join(str(r["_line"]) for r in hits)))
    eol = "\r\n" if phys and phys[0].endswith("\r\n") else "\n"
    if not hits:
        row = dict((c, "") for c in cols)
        row.update(zip(key_cols, key_vals))
        row.update(change)
        lead = "" if not text or text.endswith("\n") else eol
        if not phys:
            lead = csv_line(cols) + eol
        os.makedirs(pr.design, exist_ok=True)
        with open(path, "ab") as fh:
            fh.write((lead + csv_line([row[c] for c in cols]) + eol).encode("utf-8"))
        out("%s line %d: %s: added" % (rel, len(phys) + (1 if phys else 2), key))
        return []
    row, n = hits[0], hits[0]["_line"]
    try:
        alone = [x.strip() for x in next(csv.reader([phys[n - 1]]))]
    except (IndexError, StopIteration):
        alone = None
    if alone != [row[c] for c in cols]:
        raise InputError("%s line %d: the row does not sit on one line of the file; change it by hand" % (rel, n))
    diff = [(c, row[c], v) for c, v in change.items() if row[c] != v]
    if not diff:
        out("%s line %d: %s: no change" % (rel, n, key))
        return []
    new = dict(row)
    new.update(change)
    end = phys[n - 1][len(phys[n - 1].rstrip("\r\n")):]
    phys[n - 1] = csv_line([new[c] for c in cols]) + end
    with open(path, "wb") as fh:
        fh.write("".join(phys).encode("utf-8"))
    out("%s line %d: %s: changed" % (rel, n, key))
    for c, old, v in diff:
        out("  %s: %s -> %s" % (c, old or "(empty)", v or "(empty)"))
    return []


# ---------------------------------------------------------------- main

FUNCS = {"compliance": cmd_compliance, "sections": cmd_sections, "constraints": cmd_constraints, "fabcap": cmd_fabcap,
         "parts": cmd_parts, "packs": cmd_packs, "suppress": cmd_suppress, "stale": cmd_stale, "findings": cmd_findings,
         "decisions": cmd_decisions, "netreview": cmd_netreview, "checklists": cmd_checklists, "text": cmd_text, "writers": cmd_writers,
         "requirements": cmd_requirements, "datasheets": cmd_datasheets,
         "scan": cmd_scan, "impact": cmd_impact, "summary": cmd_summary, "parts-totals": cmd_parts_totals,
         "log-append": cmd_log_append, "set-row": cmd_set_row}
assert set(FUNCS) == set(COMMANDS)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("args", nargs="+", help="sub-commands (%s, or all), then any targets" % ", ".join(COMMANDS))
    ap.add_argument("--project", help="project root, or a folder inside it (default: the project of the first "
                                      "--staged file, else the working folder). Pass it whenever the shell may "
                                      "start in another folder")
    ap.add_argument("--name", help="project name in the KiCad folder when there are several")
    ap.add_argument("--board", action="store_true", help="compliance: carried rows need a board result")
    ap.add_argument("--max-age", type=int, default=30,
                    help="parts: days since stock and price were checked; older dates are listed, and fail "
                         "only with --stage ST12 or later")
    ap.add_argument("--today", help="parts: the date to count from (YYYY-MM-DD; default today)")
    ap.add_argument("--stage", help="the checkpoint this run is for (for example ST6). checklists: only items "
                                    "whose stage is at or before it, and those with no result fail from ST6; "
                                    "netreview: open items fail from ST6; suppress: board severities at KiCad's "
                                    "defaults fail from ST11; compliance: open must and hard rows fail from "
                                    "ST6, carried rows with no board result from ST11; compliance and sections: "
                                    "a table with no rows fails from ST6; constraints: a changed limit or "
                                    "enforcer with no decision fails from ST7, a cannot-tell verdict from ST11; "
                                    "parts: a missing stock date fails from ST6, old dates from ST12; "
                                    "requirements: gaps in the structure fail from ST1; "
                                    "a check whose input is not present fails from ST6 (ST11 for constraints "
                                    "and fabcap, ST1 for requirements). log-append: the stage of the decision, "
                                    "or several (\"ST5, ST6\")")
    ap.add_argument("--waive", action="append", default=[], metavar="REF=DC-nnn",
                    help="parts: a missing footprint or 3D model covered by a decision")
    ap.add_argument("--staged", action="append", default=[], metavar="FILE",
                    help="compliance, sections and findings: check a pass's staging file before the merge "
                         "(<MPN>_<perspective>.csv rows, <MPN>_<perspective>_sections.csv claims, "
                         "<MPN>_<perspective>_findings.csv findings) instead of the main tables. A relative path "
                         "is read from the working folder, else from the --project root")
    ap.add_argument("--record-review", metavar="BR-nn-nn",
                    help="constraints: after the sufficiency review, record every constraint's kind, objects, limit "
                         "and enforcer in design/constraints-reviewed.csv, the baseline later changes are compared "
                         "with (only when the constraints check passes)")
    for flag, text in (("--statement", "what was decided, in one plain sentence, with no ID"),
                       ("--kind", "one of: %s" % ", ".join(hwcommon.DECISION_KINDS)),
                       ("--by", "who decided: user, coordinator or \"worker BR-nn-nn\""),
                       ("--seen", "yes or no: has the user seen it (default no; not written for the user's own decision)"),
                       ("--options", "each option considered, the chosen one marked"),
                       ("--reason", "why, with the IDs it rests on"),
                       ("--affects", "\"requirements <IDs or none>; parts <...>; schematic <...>; board <...>; "
                                     "cost <effect or none>\""),
                       ("--status", "default \"in force\""),
                       ("--replaces", "the DC- IDs of the earlier entries this one changes")):
        ap.add_argument(flag, help="log-append: " + text)
    a = ap.parse_args(argv)
    resolved = []
    for path in a.staged:
        if not STAGED_RE.match(os.path.basename(path)):
            print("table_check: --staged %s: name it <MPN>_<perspective>.csv, <MPN>_<perspective>_sections.csv or "
                  "<MPN>_<perspective>_findings.csv" % path, file=sys.stderr)
            return 2
        tried = [path] if os.path.isabs(path) else [os.path.abspath(path)]
        if not os.path.isabs(path) and a.project:
            try:
                tried.append(os.path.join(hwcommon.find_project(a.project, a.name)["root"], path))
            except hwcommon.ProjectError:
                pass
        found = next((p for p in tried if os.path.isfile(p)), None)
        if not found:
            print("table_check: --staged %s: no such file (looked at %s)" % (path, ", ".join(tried)), file=sys.stderr)
            return 2
        resolved.append(found)
    a.staged = resolved
    if not a.project:
        a.project = os.path.dirname(resolved[0]) if resolved else "."
    if a.record_review and not re.fullmatch(r"BR-\d+-\d+", a.record_review):
        print("table_check: --record-review takes the sufficiency review's brief ID, such as BR-03-02", file=sys.stderr)
        return 2
    cmds = [x for x in a.args if x in COMMANDS or x == "all"]
    a.targets = [x for x in a.args if x not in COMMANDS and x != "all"]
    if not cmds or a.args[0] not in cmds:
        print("table_check: start with a sub-command: %s, or all" % ", ".join(COMMANDS), file=sys.stderr)
        return 2
    if "all" in cmds:
        cmds = list(PASS_FAIL)
    if a.args[0] in WRITERS:
        # a command that changes a file runs alone; every word after it is its own
        cmds, a.targets = [a.args[0]], a.args[1:]
    elif set(cmds) & set(WRITERS):
        print("table_check: %s runs alone, as the first word" % " and ".join(sorted(set(cmds) & set(WRITERS))),
              file=sys.stderr)
        return 2
    if a.stage and cmds != ["log-append"] and not re.fullmatch(r"ST\d+", a.stage):
        print("table_check: --stage takes a stage such as ST6", file=sys.stderr)
        return 2
    failed = 0
    try:
        try:
            pr = Project(a)
        except hwcommon.ProjectError:
            if cmds == ["scan"] and a.targets:
                pr = None
            else:
                raise
        not_run = []
        for name in cmds:
            print("== table_check %s" % name)
            try:
                fails = FUNCS[name](pr, a, print)
            except NotRun as e:
                if not stage_at_least(a, e.checkpoint):
                    print("%s, check not run" % e)
                    print("%s: not run (listed, not failed before --stage %s)" % (name, e.checkpoint))
                    not_run.append(name)
                    continue
                fails = ["%s, check not run (a fail from --stage %s on)" % (e, e.checkpoint)]
            if name in PASS_FAIL or name == "scan":
                for f in fails:
                    if name != "scan":
                        print("FAIL  " + f)
                print("%s: %s" % (name, "pass" if not fails else "FAIL (%d)" % len(fails)))
            failed += bool(fails)
        if not_run and len(cmds) > 1:
            print("not run (input not present): %s" % ", ".join(not_run))
    except (InputError, hwcommon.ProjectError, hwcommon.TableError, ValueError, OSError) as e:
        print("table_check: %s" % e, file=sys.stderr)
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
