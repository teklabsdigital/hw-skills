# Copyright 2026 Teklabs Digital (hw-skills)
# SPDX-License-Identifier: Apache-2.0
"""Order files from a finished board: Gerber zip, BOM and placement files, not-fitted list.

    python3 fab.py hardware/<name>.kicad_pcb hardware/<manufacturer> [options]

The board may sit in any KiCad folder (hardware/, the project root, or the folder named on the line
"KiCad folder: <folder>" of design/status.md).

    --design DIR          the design/ folder (default: the design/ of the nearest folder at or above
                          the board's folder that has one, else design/ beside the board's folder)
    --assembler SUPPLIER  also write the assembler set: parts whose parts.csv supplier is SUPPLIER
                          are fitted by the assembler, in the format proven on an earlier order
                          (BOM: Comment, Designator, Footprint, <SUPPLIER> Part #; placement:
                          Designator, Mid X, Mid Y, Layer, Rotation)
    --variant NAME        fit the parts whose parts.csv variant names NAME
    --hand                also write a hand-assembly list
    --date YYYY-MM-DD     the date stamped into the Gerber, drill and zip files (default 1980-01-01),
                          so an unchanged board gives byte-identical files
    --waive DC-nnn        go ahead despite the problems reported, under this recorded decision

What it checks first, and reports as violations:
  - KiCad's DRC with zones poured again and schematic parity. The board file is not saved.
    Any violation, unconnected item, or parity item not listed under "Expected DRC notes" in
    design/status.md is a violation.
  - parts.csv against the board: designators on one and not the other, sourcing fields that
    differ, not-fitted marks that differ, duplicate designators.
With violations it writes nothing and exits 1, unless every waiver given is a decision in
design/decisions.md: then it prints the waivers and goes ahead.

Always written into the output folder: <name>_gerbers.zip (no loose Gerber files), bom.csv and
placement.csv (neutral set), not_fitted.csv. A part is not fitted when the board marks it DNP,
when parts.csv variant is "not fitted", or when it names a variant not selected. A footprint
marked board-only or excluded from both BOM and position files (a logo, a mounting hole) is not
a part. Missing sourcing fields are listed, never guessed. A supplier part number with a space or a
question mark in it, or no digit at all, is taken as a placeholder: a warning lists it, and it is
left out of the assembler BOM (listed in assembler_not_fitted.csv). After writing, the files are read
back and compared with the board (FB-01).

Needs kicad-cli (found by kicad_env.py), not pcbnew. Rotations are KiCad's; an assembler's
reel orientation can differ: compare them in the assembler's placement preview.
Exit codes: 0 written; 1 violations, nothing written; 2 bad input; 3 kicad-cli missing or failed;
4 written, but the read-back consistency check failed.

"""
import argparse
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwcommon  # noqa: E402
import kicad_env  # noqa: E402

TECH_LAYERS = ("F.Paste", "B.Paste", "F.SilkS", "B.SilkS", "F.Mask", "B.Mask", "Edge.Cuts")
SOURCING = ("manufacturer", "mpn", "supplier", "supplier_pn")
BOARD_FIELDS = {"manufacturer": "Manufacturer", "mpn": "MPN", "supplier": "Supplier", "supplier_pn": "Supplier PN"}


# ---------------------------------------------------------------- DRC

def run_drc(cli, board_path):
    """KiCad's DRC as JSON, zones poured again in memory (the board file is not saved)."""
    tmp = tempfile.mkdtemp()
    try:
        report = os.path.join(tmp, "drc.json")
        res = subprocess.run([cli, "pcb", "drc", "--format", "json", "--severity-all", "--schematic-parity",
                              "--refill-zones", "-o", report, board_path],
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not os.path.isfile(report):
            raise RuntimeError("kicad-cli pcb drc wrote no report:\n" + res.stdout + res.stderr)
        with open(report, encoding="utf-8") as f:
            return json.load(f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def drc_problems(report, expected):
    """(problems, expected notes found). expected: (text, item, DC-) tuples from status.md."""
    found, other = [], []
    for v in report.get("schematic_parity", []):
        items = [i.get("description", "") for i in v.get("items", [])]
        hit = [e for e in expected if e[0] in v.get("description", "") and e[1] in items]
        (found if hit else other).append(v)
    problems = report.get("violations", []) + report.get("unconnected_items", []) + other
    return problems, found


def describe(v):
    where = "; ".join(i.get("description", "")[:60] for i in v.get("items", []))
    return "%s %s: %s%s" % (v.get("severity", ""), v.get("type", ""), v.get("description", ""),
                            " (%s)" % where if where else "")


# ---------------------------------------------------------------- parts

def is_part(fp):
    a = fp["attrs"]
    if "board_only" in a or ("exclude_from_bom" in a and "exclude_from_pos_files" in a):
        return False
    return bool(fp["ref"]) and not fp["ref"].startswith(("#", "REF*"))


def technology(fp):
    if "smd" in fp["attrs"]:
        return "SMD"
    if "through_hole" in fp["attrs"]:
        return "THT"
    types = set(p["type"] for p in fp["pads"])
    return "THT" if "thru_hole" in types else ("SMD" if "smd" in types else "other")


def collect_parts(board, parts_rows, variant):
    """Parts on the board with their fields and fitted state. Returns (parts, problems, notes)."""
    problems, notes = [], []
    by_ref = {}
    for row in parts_rows:
        for ref in hwcommon.split_list(row["refs"]):
            if ref in by_ref:
                problems.append("parts.csv: %s appears in more than one row" % ref)
            by_ref[ref] = row
    have_table = bool(parts_rows)
    if not have_table:
        notes.append("design/parts.csv not found or empty: sourcing fields come from the board footprints")
    seen, parts = set(), []
    for fp in board["footprints"]:
        if not is_part(fp):
            continue
        ref = fp["ref"]
        if ref in seen:
            problems.append("board: designator %s is used by more than one footprint" % ref)
            continue
        seen.add(ref)
        row = by_ref.get(ref)
        p = {"ref": ref, "value": fp["value"], "footprint": fp["lib_id"].split(":")[-1],
             "side": "Bottom" if fp["layer"].startswith("B.") else "Top", "tech": technology(fp), "fp": fp}
        for k, field in BOARD_FIELDS.items():
            on_board = fp["fields"].get(field, "")
            if row is not None:
                p[k] = row[k]
                if on_board and row[k] and on_board != row[k]:
                    problems.append("%s %s: board says %r, parts.csv says %r (rebuild the schematic and board, "
                                    "or correct parts.csv)" % (ref, field, on_board, row[k]))
            else:
                p[k] = on_board
        if have_table and row is None:
            problems.append("%s is on the board but not in parts.csv" % ref)
        p["msl"] = row["msl"] if row else ""
        p["role"] = row["role"] if row else ""
        why = ""
        names = [v.lower() for v in hwcommon.split_list(row["variant"])] if row else []
        board_dnp = "dnp" in fp["attrs"]
        if names == ["not fitted"]:
            why = "not fitted (parts.csv)"
        elif names and (variant or "").lower() not in names:
            why = "variant %s only" % ", ".join(hwcommon.split_list(row["variant"]))
        if board_dnp:
            if row is not None and not names:
                problems.append("%s: the board marks it do-not-populate, parts.csv says fitted" % ref)
            why = why or "do not populate (board)"
        elif names == ["not fitted"]:
            problems.append("%s: parts.csv says not fitted, the board does not mark it do-not-populate" % ref)
        p["fitted"] = not why
        p["why"] = why
        parts.append(p)
    for ref in sorted(set(by_ref) - seen, key=hwcommon.ref_key):
        problems.append("%s is in parts.csv but not on the board" % ref)
    parts.sort(key=lambda p: hwcommon.ref_key(p["ref"]))
    return parts, problems, notes


def position(board, fp):
    ox, oy = board["aux_origin"]
    return fp["x"] - ox, -(fp["y"] - oy), fp["rot"] % 360


def _csv(rows, header):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def neutral_files(board, parts):
    fitted = [p for p in parts if p["fitted"]]
    groups = {}
    for p in fitted:
        key = (p["value"], p["footprint"], p["manufacturer"], p["mpn"], p["supplier"], p["supplier_pn"])
        groups.setdefault(key, []).append(p["ref"])
    bom = [[";".join(refs), len(refs)] + list(key)
           for key, refs in sorted(groups.items(), key=lambda kv: hwcommon.ref_key(kv[1][0]))]
    place = []
    for p in fitted:
        x, y, r = position(board, p["fp"])
        place.append([p["ref"], p["value"], p["footprint"], "%.4f" % x, "%.4f" % y, "%.0f" % r, p["side"], p["tech"]])
    nf = [[p["ref"], p["value"], p["footprint"], p["why"]] for p in parts if not p["fitted"]]
    return {
        "bom.csv": _csv(bom, ["Designators", "Qty", "Value", "Footprint", "Manufacturer", "MPN", "Supplier",
                              "Supplier PN"]),
        "placement.csv": _csv(place, ["Designator", "Value", "Footprint", "X (mm)", "Y (mm)", "Rotation",
                                      "Side", "Type"]),
        "not_fitted.csv": _csv(nf, ["Designator", "Value", "Footprint", "Reason"]),
    }


def placeholder_pn(value):
    """True for a supplier part number that is not one: words with spaces ("not checked yet"), no digit
    at all ("TBD", "none"), or a question mark. Such a value is listed, never sent to an assembler."""
    v = (value or "").strip()
    return bool(v) and (bool(re.search(r"\s|\?", v)) or not re.search(r"\d", v))


def assembler_files(board, parts, supplier):
    mine, other = [], []
    for p in parts:
        if not p["fitted"]:
            continue
        if p["tech"] != "SMD":
            other.append((p, "through-hole" if p["tech"] == "THT" else "not an SMD part"))
        elif p["supplier"] != supplier:
            other.append((p, "supplier is %s" % (p["supplier"] or "not set")))
        elif not p["supplier_pn"]:
            other.append((p, "no supplier part number"))
        elif placeholder_pn(p["supplier_pn"]):
            other.append((p, "supplier part number %r is not a part number (a placeholder?)" % p["supplier_pn"]))
        else:
            mine.append(p)
    groups = {}
    for p in mine:
        groups.setdefault((p["supplier_pn"], p["value"], p["footprint"]), []).append(p)
    bom = [[ps[0]["value"], ",".join(p["ref"] for p in ps), fpname, pn, ps[0]["manufacturer"], ps[0]["mpn"]]
           for (pn, _, fpname), ps in sorted(groups.items(), key=lambda kv: hwcommon.ref_key(kv[1][0]["ref"]))]
    cpl = []
    for p in mine:
        x, y, r = position(board, p["fp"])
        cpl.append([p["ref"], "%.4fmm" % x, "%.4fmm" % y, p["side"], "%.0f" % r])
    nf = [[p["ref"], p["value"], p["footprint"], p["manufacturer"], p["mpn"], p["supplier"], p["supplier_pn"], why]
          for p, why in other]
    return {
        "assembler_bom.csv": _csv(bom, ["Comment", "Designator", "Footprint", "%s Part #" % supplier,
                                        "Manufacturer", "MPN"]),
        "assembler_cpl.csv": _csv(cpl, ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"]),
        "assembler_not_fitted.csv": _csv(nf, ["Designator", "Value", "Footprint", "Manufacturer", "MPN",
                                              "Supplier", "Supplier PN", "Reason"]),
    }


def hand_notes(p, pin_refs):
    fp = p["fp"]
    pads = fp["pads"]
    notes = []
    if p["ref"] in pin_refs or len(pads) > 2 or any(not re.fullmatch(r"\d+", q["number"]) for q in pads if q["number"]):
        notes.append("orientation: match pin 1 or the polarity mark")
    pitch = min([((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5
                 for i, a in enumerate(pads) for b in pads[i + 1:] if a["number"] != b["number"]] or [0])
    if 0 < pitch <= 0.65:
        notes.append("fine pitch %.2f mm" % pitch)
    areas = sorted(q["w"] * q["h"] for q in pads)
    if len(pads) >= 3 and areas and areas[-1] >= 4 * areas[len(areas) // 2]:
        notes.append("exposed pad: solder it, check for voids")
    msl = re.match(r"\d+", p["msl"] or "")
    if msl and int(msl.group(0)) > 1:
        notes.append("moisture level %s: keep dry, bake if exposed" % msl.group(0))
    if p["tech"] == "THT":
        notes.append("solder after the SMD parts")
    return notes


def hand_file(parts, pin_refs):
    def size(p):
        pads = p["fp"]["pads"]
        if not pads:
            return 0.0
        xs = [q["x"] for q in pads]
        ys = [q["y"] for q in pads]
        return (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1)
    fitted = [p for p in parts if p["fitted"]]
    order = sorted(fitted, key=lambda p: (p["tech"] != "SMD", round(size(p), 3), hwcommon.ref_key(p["ref"])))
    rows = []
    for i, p in enumerate(order, 1):
        stencil = "yes" if p["tech"] == "SMD" and any(
            l.endswith(".Paste") for q in p["fp"]["pads"] for l in q["layers"]) else "no"
        rows.append([i, p["ref"], p["value"], p["footprint"], p["side"], p["tech"], stencil,
                     "; ".join(hand_notes(p, pin_refs))])
    return {"hand_assembly.csv": _csv(rows, ["Step", "Designator", "Value", "Footprint", "Side", "Type",
                                             "Stencil", "Notes"])}


# ---------------------------------------------------------------- Gerbers

STAMPS = (
    (re.compile(r"(TF\.CreationDate,)[0-9T:+-]+"), "{d}T00:00:00+00:00"),
    (re.compile(r"(\) date )\d{4}-\d\d-\d\d \d\d:\d\d:\d\d"), "{d} 00:00:00"),
    (re.compile(r"(DRILL file .* date )[0-9T:+-]+"), "{d}T00:00:00"),
)


def fix_stamps(path, date):
    """KiCad stamps every Gerber and drill file with the export time; set the fixed date instead."""
    with open(path, encoding="latin-1", newline="") as f:
        text = f.read()
    for pat, rep in STAMPS:
        text = pat.sub(lambda m: m.group(1) + rep.format(d=date), text)
    with open(path, "w", encoding="latin-1", newline="") as f:
        f.write(text)


def gerber_zip(cli, board_path, board, zpath, date):
    layers = ",".join(list(board["copper_layers"]) + list(TECH_LAYERS))
    gdir = tempfile.mkdtemp()
    try:
        for args in (["pcb", "export", "gerbers", "--layers", layers, "--subtract-soldermask", "--check-zones",
                      "--no-x2", "--no-netlist", "-o", gdir + os.sep, board_path],
                     ["pcb", "export", "drill", "--format", "excellon", "--excellon-units", "mm",
                      "--excellon-separate-th", "--excellon-oval-format", "alternate", "-o", gdir + os.sep,
                      board_path]):
            res = subprocess.run([cli] + args, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if res.returncode:
                raise RuntimeError("kicad-cli %s failed:\n%s%s" % (" ".join(args[:3]), res.stdout, res.stderr))
        files = sorted(f for f in os.listdir(gdir) if not f.endswith(".gbrjob"))
        stamp = (int(date[:4]), int(date[5:7]), int(date[8:10]), 0, 0, 0)
        tmpzip = zpath + ".tmp"
        with zipfile.ZipFile(tmpzip, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                fix_stamps(os.path.join(gdir, f), date)
                info = zipfile.ZipInfo(f, date_time=stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(os.path.join(gdir, f), "rb") as src:
                    z.writestr(info, src.read())
        os.replace(tmpzip, zpath)
        return files
    finally:
        shutil.rmtree(gdir, ignore_errors=True)


# ---------------------------------------------------------------- read-back check (FB-01)

def read_csv_text(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def consistency(out, board, parts, assembler):
    """Read the written files back and compare them with the board. Returns problems."""
    problems = []
    board_refs = [fp["ref"] for fp in board["footprints"] if is_part(fp)]
    fitted = set(p["ref"] for p in parts if p["fitted"])
    not_fitted = set(p["ref"] for p in parts if not p["fitted"])
    smd = set(p["ref"] for p in parts if p["fitted"] and p["tech"] == "SMD")

    def refs_of(rows, col, sep):
        out_refs = []
        for r in rows[1:]:
            out_refs += [x for x in r[col].split(sep) if x]
        return out_refs

    bom = refs_of(read_csv_text(os.path.join(out, "bom.csv")), 0, ";")
    place = refs_of(read_csv_text(os.path.join(out, "placement.csv")), 0, ";")
    nf = refs_of(read_csv_text(os.path.join(out, "not_fitted.csv")), 0, ";")
    for name, got in (("bom.csv", bom), ("placement.csv", place)):
        dup = sorted(set(r for r in got if got.count(r) > 1))
        if dup:
            problems.append("%s lists %s more than once" % (name, ", ".join(dup)))
        if set(got) != fitted:
            problems.append("%s differs from the fitted parts: missing %s, extra %s" % (
                name, sorted(fitted - set(got)) or "none", sorted(set(got) - fitted) or "none"))
    if set(nf) != not_fitted:
        problems.append("not_fitted.csv differs from the not-fitted parts")
    if set(bom) & set(nf) or set(place) & set(nf):
        problems.append("a not-fitted part appears in the BOM or placement file")
    unknown = sorted(set(bom + place + nf) - set(board_refs))
    if unknown:
        problems.append("designators not on the board: %s" % ", ".join(unknown))
    if assembler:
        ab = refs_of(read_csv_text(os.path.join(out, "assembler_bom.csv")), 1, ",")
        ac = refs_of(read_csv_text(os.path.join(out, "assembler_cpl.csv")), 0, ",")
        an = refs_of(read_csv_text(os.path.join(out, "assembler_not_fitted.csv")), 0, ",")
        if sorted(ab) != sorted(ac):
            problems.append("assembler BOM and placement list different parts")
        if len(ab) != len(set(ab)):
            problems.append("assembler BOM lists a part more than once")
        if set(ab) & set(an):
            problems.append("a part is both fitted and not fitted by the assembler")
        if set(ab) | set(an) != fitted:
            problems.append("assembler files do not cover every fitted part exactly once")
        if not set(ab) <= smd:
            problems.append("assembler BOM holds a part that is not a fitted SMD part")
    return problems


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--design")
    ap.add_argument("--assembler", metavar="SUPPLIER")
    ap.add_argument("--variant")
    ap.add_argument("--hand", action="store_true")
    ap.add_argument("--date", default="1980-01-01")
    ap.add_argument("--waive", action="append", default=[], metavar="DC-nnn")
    a = ap.parse_args(argv)

    board_path = os.path.abspath(a.board)
    if not os.path.isfile(board_path):
        print("fab: %s does not exist" % a.board, file=sys.stderr)
        return 2
    if not re.fullmatch(r"\d{4}-\d\d-\d\d", a.date) or a.date < "1980-01-01":
        print("fab: --date must be YYYY-MM-DD, 1980-01-01 or later", file=sys.stderr)
        return 2
    hw = os.path.dirname(board_path)
    out = os.path.abspath(a.out or os.path.join(hw, "fab"))
    design = a.design or hwcommon.design_dir_for(board_path)
    name = os.path.splitext(os.path.basename(board_path))[0]

    bad_waivers = hwcommon.check_waivers(a.waive, design)
    if bad_waivers:
        for w in bad_waivers:
            print("fab: " + w, file=sys.stderr)
        return 2
    try:
        parts_rows = hwcommon.read_table(os.path.join(design, "parts.csv"))
        pin_rows = hwcommon.read_table(os.path.join(design, "pins.csv"))
    except hwcommon.TableError as e:
        print("fab: %s" % e, file=sys.stderr)
        return 2
    expected, status_errors = hwcommon.expected_drc_notes(design)
    if status_errors:
        for e in status_errors:
            print("fab: " + e, file=sys.stderr)
        return 2
    cli = kicad_env.find_kicad_cli()
    if not cli:
        print("fab: kicad-cli not found; set KICAD_CLI (python3 kicad_env.py shows the search)", file=sys.stderr)
        return 3

    board = hwcommon.read_board(board_path)
    before = hwcommon.sha256_file(board_path)
    try:
        drc = run_drc(cli, board_path)
    except RuntimeError as e:
        print("fab: %s" % e, file=sys.stderr)
        return 3
    if hwcommon.sha256_file(board_path) != before:
        print("fab: the board file changed during DRC; it should not have. Stop and report this.", file=sys.stderr)
        return 3
    problems, found = drc_problems(drc, expected)
    parts, part_problems, notes = collect_parts(board, parts_rows, a.variant)

    print("DRC (zones poured again, board not saved): %d violations, %d unconnected, %d parity items, "
          "%d of them expected" % (len(drc.get("violations", [])), len(drc.get("unconnected_items", [])),
                                   len(drc.get("schematic_parity", [])), len(found)))
    for n in notes:
        print("note: " + n)
    all_problems = ["DRC " + describe(v) for v in problems] + part_problems
    if all_problems:
        print("Violation: %d problems:" % len(all_problems))
        for p in all_problems:
            print("    " + p)
        if not a.waive:
            print("Nothing written. Fix the cause, or record a waiver (DC-nnn) and pass --waive DC-nnn.")
            return 1
        print("WAIVED by %s: going ahead with the %d problems above." % (", ".join(a.waive), len(all_problems)))
    elif a.waive:
        print("note: nothing to waive; %s not used" % ", ".join(a.waive))

    os.makedirs(out, exist_ok=True)
    try:
        files = gerber_zip(cli, board_path, board, os.path.join(out, name + "_gerbers.zip"), a.date)
    except RuntimeError as e:
        print("fab: %s" % e, file=sys.stderr)
        return 3
    written = {name + "_gerbers.zip": None}
    texts = neutral_files(board, parts)
    if a.assembler:
        texts.update(assembler_files(board, parts, a.assembler))
    if a.hand:
        pin_refs = set(r["designator"] for r in pin_rows)
        texts.update(hand_file(parts, pin_refs))
    for fname, text in sorted(texts.items()):
        hwcommon.write_text(os.path.join(out, fname), text)
        written[fname] = text

    missing = [(p["ref"], [k for k in SOURCING if not p[k]]) for p in parts if p["fitted"]]
    missing = [(r, ks) for r, ks in missing if ks]
    fitted = [p for p in parts if p["fitted"]]
    print("Gerber and drill files: %d, in %s_gerbers.zip (%s)" % (len(files), name, ", ".join(files)))
    print("Copper layers: %d (%s)" % (len(board["copper_layers"]), ", ".join(board["copper_layers"])))
    print("Parts: %d fitted (%d SMD), %d not fitted: %s" % (
        len(fitted), sum(1 for p in fitted if p["tech"] == "SMD"), len(parts) - len(fitted),
        ", ".join("%s (%s)" % (p["ref"], p["why"]) for p in parts if not p["fitted"]) or "none"))
    if missing:
        print("Missing sourcing fields (not guessed): " + "; ".join("%s: %s" % (r, ", ".join(ks)) for r, ks in missing))
    odd = [(p["ref"], p["supplier_pn"]) for p in fitted if placeholder_pn(p["supplier_pn"])]
    if odd:
        print("WARNING: supplier part numbers that are not part numbers (placeholders?): %s. They stay in the "
              "neutral bom.csv as written%s; fill parts.csv with the real numbers before ordering."
              % ("; ".join("%s %r" % x for x in odd),
                 ", and are left out of the assembler BOM (listed in assembler_not_fitted.csv)" if a.assembler else ""))
    if a.hand:
        print("Hand-assembly list: ordered by technology and footprint size; part heights are not read, "
              "so check tall and heat-sensitive parts go last.")
    loose = sorted(set(os.listdir(out)) - set(written))
    if loose:
        print("Loose files in %s not written by this run (remove them before upload): %s"
              % (os.path.basename(out), ", ".join(loose)))
    for w in a.waive:
        print("Waiver in force: %s" % w)
    check = consistency(out, board, parts, a.assembler)
    if check:
        print("Consistency (FB-01): FAIL")
        for c in check:
            print("    " + c)
        return 4
    print("Consistency (FB-01): pass. BOM, placement and not-fitted files agree with the board.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
