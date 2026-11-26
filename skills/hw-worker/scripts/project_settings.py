# Copyright 2026 Teklabs Digital (hw-skills)
# SPDX-License-Identifier: Apache-2.0
"""Write the whole KiCad project file (.kicad_pro) and rule file (.kicad_dru) from the project tables.

    python3 project_settings.py hardware/<name>.kicad_pro [--design design]

The build owns both files. Nothing on disk is read back: the .kicad_pro starts from
kicad_pro_defaults.json (KiCad's editor defaults and everything else this project does not set),
gets the values below on top, and is written in the form KiCad itself saves (keys sorted,
two-space indent). The same tables give the same bytes, whether the build starts from the
committed file, from a file the KiCad editor saved, or from no file. A setting changed in the
editor is lost at the next build: put it in the tables.

Where the values come from:
  design/fab-capabilities.csv  rule_value of the items in CAPABILITY_ITEMS: board minimums in the
                               .kicad_pro and the manufacturer rules in the .kicad_dru. An item with
                               no rule_value is left out and listed.
  design/constraints.csv       rows enforced by "dru:netclass <Name>": net classes (clearance,
                               width, via_diameter, via_drill; objects are net names or patterns);
                               rows enforced by "dru:<rule name>": a custom rule of that name
                               (kinds in DRU_KINDS).
  this file                    the raised ERC and DRC severities and the ERC pin map. Lowering one is
                               a decision: add it to SEVERITY_CHANGES with its DC- ID.

Plain Python, no pcbnew. Exit code 0 when both files are written, 2 when a table cannot be used.

"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwcommon  # noqa: E402

DEFAULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kicad_pro_defaults.json")

# fab-capabilities.csv item -> (key in board.design_settings.rules or None, rule-file text or None).
# {v} is the rule_value in mm.
CAPABILITY_ITEMS = {
    "min_track": ("min_track_width",
                  '(rule "fab: track width"\n\t(condition "A.Type == \'track\'")\n'
                  "\t(constraint track_width (min {v}mm)))"),
    "min_clearance": ("min_clearance", '(rule "fab: copper clearance"\n\t(constraint clearance (min {v}mm)))'),
    "min_via_diameter": ("min_via_diameter",
                         '(rule "fab: via diameter"\n\t(condition "A.Type == \'via\'")\n'
                         "\t(constraint via_diameter (min {v}mm)))"),
    "min_via_drill": ("min_through_hole_diameter",
                      '(rule "fab: via drill"\n\t(condition "A.Type == \'via\'")\n'
                      "\t(constraint hole_size (min {v}mm)))"),
    "via_annular": ("min_via_annular_width",
                    '(rule "fab: via annular ring"\n\t(condition "A.Type == \'via\'")\n'
                    "\t(constraint annular_width (min {v}mm)))"),
    "pth_annular": (None,
                    '(rule "fab: plated hole annular ring"\n'
                    "\t(condition \"A.Type == 'pad' && A.Pad_Type == 'Through-hole'\")\n"
                    "\t(constraint annular_width (min {v}mm)))"),
    "min_hole_to_hole": ("min_hole_to_hole", '(rule "fab: hole to hole"\n\t(constraint hole_to_hole (min {v}mm)))'),
    "via_hole_clearance": ("min_hole_clearance",
                           '(rule "fab: via hole to copper"\n\t(condition "A.Type == \'via\'")\n'
                           "\t(constraint hole_clearance (min {v}mm)))"),
    "pth_hole_clearance": (None,
                           '(rule "fab: plated hole to copper"\n'
                           "\t(condition \"A.Type == 'pad' && A.Pad_Type == 'Through-hole'\")\n"
                           "\t(constraint hole_clearance (min {v}mm)))"),
    "edge_clearance": ("min_copper_edge_clearance",
                       '(rule "fab: copper to board edge"\n\t(constraint edge_clearance (min {v}mm)))'),
    "silk_clearance": ("min_silk_clearance", None),
    "silk_text_height": ("min_text_height",
                         '(rule "fab: silkscreen text height"\n\t(layer outer)\n\t(condition "A.Type == \'text\'")\n'
                         "\t(constraint text_height (min {v}mm)))"),
    "silk_text_thickness": ("min_text_thickness",
                            '(rule "fab: silkscreen text thickness"\n\t(layer outer)\n'
                            "\t(condition \"A.Type == 'text'\")\n\t(constraint text_thickness (min {v}mm)))"),
}

# constraints.csv kind -> rule-file constraint, for rows enforced by "dru:<rule name>".
DRU_KINDS = {
    "clearance": "(constraint clearance (min {v}mm))",
    "width": "(constraint track_width (min {v}mm))",
    "max_length": "(constraint length (max {v}mm))",
    "no_vias": "(constraint via_count (max 0))",
    "max_vias": "(constraint via_count (max {v}))",
    "creepage": "(constraint creepage (min {v}mm))",
}
# constraints.csv kind -> net-class key, for rows enforced by "dru:netclass <Name>".
NETCLASS_KINDS = {"clearance": "clearance", "width": "track_width",
                  "via_diameter": "via_diameter", "via_drill": "via_drill"}
# KiCad's own net-class defaults, used where no constraint sets a value.
KICAD_NETCLASS = {"clearance": 0.2, "track_width": 0.2, "via_diameter": 0.6, "via_drill": 0.3}

# ERC rule severities (KiCad 10 names, written out so that a KiCad upgrade cannot change them) and
# the pin conflict map (0 ok, 1 warning, 2 error; rows and columns: input, output, bidi,
# tri-state, passive, free, unspecified, power in, power out, open collector, open emitter,
# not connected).
ERC_SEVERITIES = {
    "error": ("bus_definition_conflict", "bus_entry_needed", "bus_to_bus_conflict",
              "bus_to_net_conflict", "different_unit_footprint", "different_unit_net",
              "duplicate_reference", "duplicate_sheet_names", "extra_units", "hier_label_mismatch",
              "label_dangling", "missing_power_pin", "pin_not_connected", "pin_not_driven",
              "power_pin_not_driven", "unannotated", "undefined_netclass", "unit_value_mismatch",
              "unresolved_variable", "wire_dangling"),
    "warning": ("endpoint_off_grid", "field_name_whitespace", "footprint_link_issues",
                "ground_pin_not_ground", "isolated_pin_label", "label_multiple_wires",
                "lib_symbol_issues", "lib_symbol_mismatch", "missing_bidi_pin", "missing_input_pin",
                "missing_unit", "multiple_net_names", "net_not_bus_member", "no_connect_connected",
                "no_connect_dangling", "pin_to_pin", "same_local_global_label",
                "same_local_global_power", "similar_label_and_power", "similar_labels",
                "similar_power", "stacked_pin_name", "unconnected_wire_endpoint"),
    "ignore": ("footprint_filter", "four_way_junction", "simulation_model_issue",
               "single_global_label"),
}
ERC_PIN_MAP = [
    [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 2], [0, 2, 0, 1, 0, 0, 1, 0, 2, 2, 2, 2],
    [0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 2], [0, 1, 0, 0, 0, 0, 1, 1, 2, 1, 1, 2],
    [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 2], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2],
    [1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 2], [0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 2],
    [0, 2, 1, 2, 0, 0, 1, 0, 2, 2, 2, 2], [0, 2, 0, 1, 0, 0, 1, 0, 2, 0, 0, 2],
    [0, 2, 1, 1, 0, 0, 1, 0, 2, 0, 0, 2], [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
]
# Board checks that are errors, not warnings: leftovers and weak copper.
BOARD_ERRORS = ("connection_width", "copper_sliver", "isolated_copper", "track_dangling",
                "via_dangling", "starved_thermal", "creepage", "items_not_allowed",
                "length_out_of_range", "too_many_vias")
# Lowered or changed severities, each with the decision that allows it:
#   {"<erc or board check name>": ("<error|warning|ignore>", "DC-nnn")}
SEVERITY_CHANGES = {}


class SettingsError(Exception):
    pass


def _mm(text, what):
    try:
        v = float(text)
    except (TypeError, ValueError):
        raise SettingsError("%s: %r is not a number in mm" % (what, text))
    if v < 0:
        raise SettingsError("%s: %r is negative" % (what, text))
    return v


def _fmt(v):
    s = ("%.4f" % v).rstrip("0").rstrip(".")
    return s or "0"


def _q(text):
    """Text for a quoted rule-file string (KiCad's rule language uses single quotes inside)."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def load_tables(design_dir):
    """(capabilities {item: mm}, netclasses {name: {...}}, custom rules [(name, lines)], notes)."""
    notes = []
    try:
        caps = hwcommon.read_table(os.path.join(design_dir, "fab-capabilities.csv"))
        cons = hwcommon.read_table(os.path.join(design_dir, "constraints.csv"))
    except hwcommon.TableError as e:
        raise SettingsError(str(e))
    capabilities = {}
    for row in caps:
        item = row["item"]
        if item not in CAPABILITY_ITEMS:
            continue
        if not row["rule_value"]:
            notes.append("fab-capabilities.csv: %s has no rule_value; left out" % item)
            continue
        capabilities[item] = _mm(row["rule_value"], "fab-capabilities.csv %s rule_value" % item)
    for item in sorted(CAPABILITY_ITEMS):
        if item not in capabilities and not any(n.startswith("fab-capabilities.csv: %s " % item) for n in notes):
            notes.append("fab-capabilities.csv: no %s row; KiCad's default is kept" % item)

    netclasses = {}
    rules = {}
    for row in cons:
        enf = hwcommon.parse_enforcer(row["enforced_by"])
        if not enf or enf[0] != "dru":
            continue
        cid, kind, objects = row["id"], row["kind"], hwcommon.split_list(row["objects"])
        name = enf[1]
        if name.startswith("netclass "):
            cls = name[len("netclass "):].strip()
            if kind not in NETCLASS_KINDS:
                raise SettingsError("constraints.csv %s: kind %r cannot set a net class (allowed: %s)"
                                    % (cid, kind, ", ".join(sorted(NETCLASS_KINDS))))
            entry = netclasses.setdefault(cls, {"values": {}, "patterns": set(), "ids": []})
            entry["values"][NETCLASS_KINDS[kind]] = _mm(row["limit"], "constraints.csv %s limit" % cid)
            entry["patterns"].update(objects)
            entry["ids"].append(cid)
            continue
        if kind not in DRU_KINDS:
            raise SettingsError("constraints.csv %s: kind %r cannot be written as a rule (allowed: %s); "
                                "use a check: or review: enforcer" % (cid, kind, ", ".join(sorted(DRU_KINDS))))
        if not objects:
            raise SettingsError("constraints.csv %s: objects is empty; name the nets" % cid)
        v = 0 if kind == "no_vias" else _mm(row["limit"], "constraints.csv %s limit" % cid)
        if kind == "max_vias":
            v = int(v)
        rule = rules.setdefault(name, {"objects": objects, "lines": [], "ids": []})
        if rule["objects"] != objects:
            raise SettingsError("constraints.csv %s: rule %r is used with different objects in %s"
                                % (cid, name, ", ".join(rule["ids"])))
        rule["lines"].append(DRU_KINDS[kind].format(v=_fmt(v) if isinstance(v, float) else v))
        rule["ids"].append(cid)
    return capabilities, netclasses, rules, notes


def _net_condition(objects):
    return " || ".join("A.NetName == '%s'" % o.replace("'", "") for o in objects)


def rules_text(capabilities, netclasses, rules):
    out = ["(version 1)",
           "# Written by project_settings.py from design/fab-capabilities.csv and design/constraints.csv.",
           "# Do not edit: change the tables and rebuild.",
           ""]
    if capabilities:
        out.append("# ---- Manufacturer capabilities (rule_value in fab-capabilities.csv) ----")
        for item in sorted(capabilities):
            text = CAPABILITY_ITEMS[item][1]
            if text:
                out.append(text.format(v=_fmt(capabilities[item])))
        out.append("")
    if netclasses:
        out.append("# ---- Net classes (constraints.csv, dru:netclass <name>) ----")
        out.append("# Written as rules too: a zone's own clearance setting otherwise overrides the net class.")
        for cls in sorted(netclasses):
            entry = netclasses[cls]
            out.append("# %s" % ", ".join(entry["ids"]))
            if "clearance" in entry["values"]:
                out.append('(rule "netclass %s clearance"\n\t(condition "A.hasNetclass(\'%s\')")\n'
                           "\t(constraint clearance (min %smm)))"
                           % (_q(cls), _q(cls), _fmt(entry["values"]["clearance"])))
            if "track_width" in entry["values"]:
                out.append('(rule "netclass %s width"\n'
                           "\t(condition \"A.Type == 'track' && A.hasNetclass('%s')\")\n"
                           "\t(constraint track_width (min %smm)))"
                           % (_q(cls), _q(cls), _fmt(entry["values"]["track_width"])))
        out.append("")
    if rules:
        out.append("# ---- Design constraints (constraints.csv, dru:<rule name>) ----")
        for name in sorted(rules):
            r = rules[name]
            out.append("# %s" % ", ".join(r["ids"]))
            out.append('(rule "%s"\n\t(condition "%s")\n%s)'
                       % (_q(name), _q(_net_condition(r["objects"])),
                          "\n".join("\t" + l for l in r["lines"])))
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def severities():
    """ERC and board severities after SEVERITY_CHANGES, which must each name a decision."""
    erc = dict((k, sev) for sev, keys in ERC_SEVERITIES.items() for k in keys)
    board = dict((k, "error") for k in BOARD_ERRORS)
    for name, change in sorted(SEVERITY_CHANGES.items()):
        sev, dc = change
        if sev not in ("error", "warning", "ignore") or not hwcommon.DC_RE.fullmatch(dc or ""):
            raise SettingsError("SEVERITY_CHANGES %r needs (severity, DC-nnn), got %r" % (name, change))
        if name in erc:
            erc[name] = sev
        else:
            board[name] = sev
    return erc, board


def project_text(name, capabilities, netclasses):
    with open(DEFAULTS, encoding="utf-8") as f:
        d = json.load(f)
    d["meta"] = {"filename": name + ".kicad_pro", "version": 3}
    d.setdefault("schematic", {})["top_level_sheets"] = [
        {"filename": name + ".kicad_sch", "name": name, "uuid": "00000000-0000-0000-0000-000000000000"}]
    erc, board = severities()
    d["erc"] = {"erc_exclusions": [], "meta": {"version": 0}, "pin_map": ERC_PIN_MAP,
                "rule_severities": dict(sorted(erc.items()))}
    ds = d.setdefault("board", {}).setdefault("design_settings", {})
    ds.setdefault("rules", {})["solder_mask_to_copper_clearance"] = 0.0
    for item, v in capabilities.items():
        key = CAPABILITY_ITEMS[item][0]
        if key:
            ds["rules"][key] = v
    ds.setdefault("rule_severities", {}).update(board)

    def cls(cname, values, prio):
        v = dict(KICAD_NETCLASS)
        v.update(values)
        return {"name": cname, "clearance": v["clearance"], "track_width": v["track_width"],
                "via_diameter": v["via_diameter"], "via_drill": v["via_drill"], "priority": prio,
                "bus_width": 12, "wire_width": 6, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
                "schematic_color": "rgba(0, 0, 0, 0.000)", "microvia_diameter": 0.3, "microvia_drill": 0.1,
                "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2, "tuning_profile": ""}
    others = sorted(c for c in netclasses if c != "Default")
    classes = [cls("Default", netclasses.get("Default", {}).get("values", {}), 2147483647)]
    # KiCad's order: Default, then the others by name; a lower number is a higher priority.
    classes += [cls(c, netclasses[c]["values"], i) for i, c in enumerate(others)]
    patterns = []
    for c in others:
        patterns += [{"netclass": c, "pattern": p} for p in sorted(netclasses[c]["patterns"])]
    d["net_settings"] = {"classes": classes, "meta": {"version": 5}, "net_colors": {},
                         "netclass_assignments": {}, "netclass_patterns": patterns}
    return json.dumps(d, indent=2, sort_keys=True) + "\n"


def write_project(pro_path, design_dir):
    """Write <name>.kicad_pro and <name>.kicad_dru beside each other. Returns the notes to print."""
    name = os.path.splitext(os.path.basename(pro_path))[0]
    capabilities, netclasses, rules, notes = load_tables(design_dir)
    hwcommon.write_text(pro_path, project_text(name, capabilities, netclasses))
    hwcommon.write_text(os.path.splitext(pro_path)[0] + ".kicad_dru", rules_text(capabilities, netclasses, rules))
    return notes


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("project", help="path of the .kicad_pro to write (the .kicad_dru goes beside it)")
    p.add_argument("--design", help="the design/ folder (default: the design/ of the nearest folder at or above "
                                    "the project's folder that has one, else design/ beside the project's folder)")
    a = p.parse_args(argv)
    pro = os.path.abspath(a.project)
    if not pro.endswith(".kicad_pro"):
        print("project_settings: the output must be a .kicad_pro file", file=sys.stderr)
        return 2
    design = a.design or hwcommon.design_dir_for(pro)
    try:
        notes = write_project(pro, design)
    except SettingsError as e:
        print("project_settings: %s" % e, file=sys.stderr)
        return 2
    for n in notes:
        print("note: " + n)
    print("wrote %s and %s" % (os.path.basename(pro), os.path.basename(os.path.splitext(pro)[0] + ".kicad_dru")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
