# Copyright 2026 Teklabs Digital (hw-skills)
# SPDX-License-Identifier: Apache-2.0
"""Build the project from its generator scripts, in order, without overwriting hand edits.

At setup every skill script, this one included, is copied into the project's own folder hwskills/
at the project root, never into scripts/ or the root, so no file of the project is overwritten:

    python3 <skill>/scripts/build.py --copy-skill-scripts <project root>

It copies only files that are not there yet. A file already there with other bytes stops it (exit
2) with the list, and nothing is copied. Then, from the project root:

    python3 hwskills/build.py                        all stages
    python3 hwskills/build.py sch erc netlist bom    only these (they always run in the order below)
    python3 hwskills/build.py --twice [stages]       build twice and compare every output byte for byte

    python3 hwskills/build.py checks                 only the project's own checks (below)

The project's own generators stay in scripts/ (gen_sch.py, gen_pcb.py). The build runs them with
hwskills/ on PYTHONPATH, so they import schlib and pcblib from there; the skill scripts import their
own siblings (hwcommon, kicad_env, project_settings) from hwskills/, whatever the project holds.

Settings are read from design/build.json. Nothing is edited inside the copied script:
    {
      "project": "<KiCad project name>",          empty or left out: found in the KiCad folder
      "order_folder": "<folder for order files>",  in the KiCad folder; empty or left out: fab
      "order_options": [],                         more fab.py options, one word per entry
      "checks": ["python3 scripts/checks/<check>.py"]
    }
A key that is not one of these four, a value of the wrong kind, text that is not JSON, or template
text in angle brackets left in a value is refused (exit 2) before any stage runs.

Project checks. Each entry of "checks" is one command. Its script must be a file in scripts/checks/
at the project root; any other command is refused (exit 2) before any stage runs. The checks run
from the project root, with hwskills/ on PYTHONPATH, after the stages asked for (and after the
second build of --twice). Every check runs; each prints its own lines and gets a pass or FAIL line.
One that fails fails the build (exit 1).

Scratch files go only in .hwtmp/ at the project root. The build makes the folder, adds the line
/.hwtmp/ to the root .gitignore when it is not there, and removes what it put in the folder. No
system temporary folder is used.

The KiCad files are in hardware/, or in the folder named on the line "KiCad folder: <folder>" in
design/status.md ("KiCad folder: ." for the project root). --adopt writes that line when an existing
project keeps its KiCad files somewhere else. Below, "the KiCad folder" is that folder.

Stages (cwd is the KiCad folder):
    sch      scripts/gen_sch.py <name>.kicad_sch           skipped when there is no gen_sch.py
    erc      kicad-cli sch erc -> ERC.json                  stops on any violation, warnings included,
                                                            that is not an expected item (below)
    netlist  kicad-cli sch export netlist -> <name>.net     machine path and export time stripped
    bom      kicad-cli sch export bom -> <name>_bom.csv     grouped, with the four sourcing fields
    board    scripts/gen_pcb.py <name>.net <name>.kicad_pcb run with a Python that can import pcbnew;
                                                            skipped when there is no gen_pcb.py
    fab      fab.py <name>.kicad_pcb <order_folder> <order_options>
                                                            order files (see fab.py)

Exports (the netlist and the BOM) and the order files are not design files: every run writes them
again, and they are not protected. A hand edit to an export is lost; make it in the schematic.

Expected ERC items. A violation that waits on work not yet done (a sheet not yet drawn, for
example) is recorded under a decision and listed in design/status.md:
    Expected ERC items:
      - "<text in the violation>" on <item, for example Symbol U1 Pin 3>, DC-nnn
The ERC stage compares the list, not the count. A violation with no line is new and stops the build
(exit 1). A line whose violation is gone stops it too, until the line is removed. When the two lists
agree the build goes on, so the netlist is exported. A line that cannot be read, or a DC- that is not
in design/decisions.md, is exit 2. The report is ERC.json in the KiCad folder; --twice leaves it out.
The number of a power symbol or power flag reference is ignored on both sides: #PWR104 and #PWR106
both read as #PWR, and #FLG01 as #FLG. KiCad names any one of the power symbols on a net, and not
the same one in every run. So one line covers that text on any power symbol or flag.

Options:
    --root DIR             project root (default: the folder above hwskills/ when this file sits in
                           it, else the folder holding this file)
    --copy-skill-scripts DIR
                           copy the skill scripts into DIR/hwskills/ (above), then stop
    --name NAME            KiCad project name (default: "project" in design/build.json, else the
                           one .kicad_pro or .kicad_sch in the KiCad folder)
    --waive DC-nnn         a recorded decision that waives violations; used by the ERC stage and passed
                           on to the generators (gen_sch.py, gen_pcb.py) and to fab.py
    --keep-hand PATH       record PATH as hand-owned (choice 1 below); its stage is skipped from now on
    --overwrite PATH=DC-n  let this build overwrite PATH, under that recorded decision (choice 3)
    --ignore-lock          build although a KiCad lock file is present
    --adopt                adopting an existing project: record every design file in the KiCad folder
                           that has no ownership record as hand-owned, then stop (no stage runs). When
                           status.md names no KiCad folder and hardware/ holds no KiCad project, the
                           one folder (the root included) holding a .kicad_pro is found and recorded
                           in design/status.md; the project's layout is kept as it is.
    --adopt --reproduce "COMMAND"
                           the same, but first run the project's own build COMMAND (run by the shell,
                           from the root of a temporary copy of the project in .hwtmp/). Each design file the
                           command writes again byte for byte is recorded as script-owned, with
                           "COMMAND (own build)" as writer and the hash on disk; every other file stays
                           hand-owned, and the reason is printed. The project itself is not written,
                           except design/ownership.csv.

Ownership step (design/ownership.csv). Before a generator stage runs, every design file in the
KiCad folder is hashed and compared with the hash of the last script write:
  - equal: the stage may write it; the new hash is recorded afterwards;
  - different, or no record (a file with no record is hand-owned): the file is protected. If the
    stage is known to write it, the stage does not run and the build stops (exit 3) with a report
    of what changed in meaning. If the stage writes it anyway, the bytes on disk are put back, the
    report says so, and the build stops;
  - hand-owned (owner "hand"): a stage known to write it is skipped, with a note.
The three choices for a changed file: 1 keep the edit (--keep-hand), 2 carry it into the
generator and rebuild (when the generator, run in a temporary copy, now writes the bytes on disk,
the file is recorded and the stage runs), 3 overwrite (--overwrite PATH=DC-nnn). No design file is
overwritten silently.
A generator that fails still has its output recorded: every file it wrote, and every unrecorded
file it wrote again with the same bytes, is recorded as its output, so the next run is not blocked
by a file nobody edited. The failure is printed and the build stops (exit 1). When the generator is
run in a temporary copy and fails there, its exit code and last lines are printed.
A file a generator wrote before and no longer writes is listed and the build stops (exit 3): remove
the file, make the generator write it again, or keep it by hand. The build never deletes it. A
generator that leaves an unchanged file alone is not stopped by this rule. A file with the same time
stamp and bytes after the run is checked in two steps:
  - the generator may declare its files: the build passes the path of an empty file in the
    environment variable HWSKILLS_OUTPUTS, and the generator appends one path per line, absolute or
    relative to the KiCad folder (schlib does this for the files it writes). A declared file is the
    generator's and is not checked further;
  - for a file not declared, the generator is run in a temporary copy in .hwtmp/ with that file taken
    away. When it writes the file there, the file is still its output and the build goes on, with a
    note. When it does not, or it fails there, the build stops as above.
When such a file is gone from disk, its ownership row is dropped, with a note.

Exit codes: 0 done; 1 a stage failed or a check found violations; 2 bad setup or arguments;
3 a protected file was not written, or a generator stopped writing one of its files (decision
needed); 4 --twice found differences;
5 a KiCad lock file is present.
Plain Python 3.
"""
import argparse
import difflib
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# Defaults only. A project's settings are in design/build.json (read_settings below); these lines are
# not edited in a project's copy.
NAME = ""            # KiCad project name; empty: found in the KiCad folder
FAB_DIR = "fab"      # order folder in the KiCad folder
FAB_ARGS = []        # more fab.py options

SETTINGS = "design/build.json"
CHECKS_FOLDER = "scripts/checks"
SCRATCH = ".hwtmp"              # the one scratch folder, at the project root, git-ignored
OUTPUTS_ENV = "HWSKILLS_OUTPUTS"

STAGES = ("sch", "erc", "netlist", "bom", "board", "fab")
ERC_REPORT = "ERC.json"     # the ERC stage's report, in the KiCad folder; it holds the run's time, so git-ignore it
BOM_FIELDS = ("Reference", "${QUANTITY}", "Value", "Manufacturer", "MPN", "Supplier", "Supplier PN",
              "Footprint", "Datasheet")
BOM_LABELS = ("Reference", "Qty", "Value", "Manufacturer", "MPN", "Supplier", "Supplier PN",
              "Footprint", "Datasheet")
# Design files (what the ownership record covers): hwcommon.DESIGN_EXT and DESIGN_NAMES.


class Stop(Exception):
    def __init__(self, code, message=""):
        Exception.__init__(self, message)
        self.code = code


SKILL_FOLDER = "hwskills"      # as hwcommon.SKILL_FOLDER (read before hwcommon can be imported)


def default_root():
    """The project root: the folder above hwskills/ when this file sits in it, else this file's folder."""
    return os.path.dirname(HERE) if os.path.basename(HERE) == SKILL_FOLDER else HERE


def setup_paths(root):
    """The skill's own modules, from this file's folder, first: never a project's module of the same name
    (a project with its own scripts/kicad_env.py or project_settings.py, for example)."""
    while HERE in sys.path:
        sys.path.remove(HERE)
    sys.path.insert(0, HERE)


def generator_env():
    """The environment for a generator: the skill scripts (schlib, pcblib) on PYTHONPATH."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([HERE] + [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p])
    return env


def read_settings(root):
    """The project's build settings from design/build.json, checked. A missing file gives the defaults."""
    out = {"project": NAME, "order_folder": FAB_DIR, "order_options": list(FAB_ARGS), "checks": []}
    path = os.path.join(root, "design", "build.json")
    if not os.path.isfile(path):
        return out
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        raise Stop(2, "%s: not valid JSON (%s)" % (SETTINGS, e))
    if not isinstance(data, dict):
        raise Stop(2, "%s: must be one JSON object with the keys %s" % (SETTINGS, ", ".join(sorted(out))))
    unknown = sorted(k for k in data if k not in out)
    if unknown:
        raise Stop(2, "%s: unknown key %s; the keys are %s" % (SETTINGS, ", ".join(unknown), ", ".join(sorted(out))))
    for key, value in data.items():
        if key in ("project", "order_folder"):
            if not isinstance(value, str):
                raise Stop(2, "%s: %s must be text in double quotes" % (SETTINGS, key))
            texts = [value]
        else:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise Stop(2, "%s: %s must be a list of texts, for example [] or [\"one\", \"two\"]"
                           % (SETTINGS, key))
            texts = value
        for t in texts:
            if re.search(r"<[^<>]*>", t):
                raise Stop(2, "%s: %s still holds the template text %s; write the project's own value"
                           % (SETTINGS, key, t))
        out[key] = value
    out["project"] = out["project"].strip()
    folder = out["order_folder"].strip().replace("\\", "/")
    if os.path.isabs(folder) or re.match(r"[A-Za-z]:", folder) or ".." in folder.split("/"):
        raise Stop(2, "%s: order_folder must be a folder inside the KiCad folder, not %s"
                   % (SETTINGS, out["order_folder"]))
    out["order_folder"] = folder or FAB_DIR
    out["checks"] = [check_command(root, n + 1, text) for n, text in enumerate(out["checks"])]
    return out


def check_command(root, number, text):
    """One entry of the checks list as (text, argument list). Its script must be a file in scripts/checks/."""
    where = "%s: checks entry %d (%s)" % (SETTINGS, number, text)
    try:
        words = shlex.split(text)
    except ValueError as e:
        raise Stop(2, "%s: cannot be read as a command (%s)" % (where, e))
    python = bool(words) and words[0] in ("python3", "python")
    if python:
        words = [sys.executable] + words[1:]
    at = 1 if python else 0
    if len(words) <= at:
        raise Stop(2, "%s: names no script; a check is a file in %s/" % (where, CHECKS_FOLDER))
    script = posixpath.normpath(words[at].replace(os.sep, "/"))
    if not script.startswith(CHECKS_FOLDER + "/"):
        raise Stop(2, "%s: %s is not in %s/ at the project root. A project check lives there; a generator or "
                      "another command is not run from this list." % (where, words[at], CHECKS_FOLDER))
    if not os.path.isfile(os.path.join(root, script)):
        raise Stop(2, "%s: there is no file %s" % (where, script))
    if not python and script.endswith(".py"):
        words = [sys.executable] + words
    return text, words


def run_checks(root, checks):
    """Run the project's own checks from the project root. All run; one that fails fails the build."""
    if not checks:
        print("checks: no project checks in %s" % SETTINGS)
        return
    failed = 0
    for text, words in checks:
        print("--- project check: " + text, flush=True)
        try:
            code = subprocess.run(words, cwd=root, env=generator_env()).returncode
        except OSError as e:
            print("    %s" % e)
            code = 127
        if code:
            failed += 1
            print("FAIL  %s (exit code %d)" % (text, code), flush=True)
        else:
            print("pass  %s" % text, flush=True)
    if failed:
        raise Stop(1, "project checks: %d of %d failed (the checks list in %s)" % (failed, len(checks), SETTINGS))


def scratch_dir(root):
    """A new folder of this run in .hwtmp/ at the project root. The folder .hwtmp/ is made when it is not
    there, and git is told to ignore it. The caller removes the new folder."""
    top = os.path.join(root, SCRATCH)
    os.makedirs(top, exist_ok=True)
    ignore = os.path.join(root, ".gitignore")
    text = ""
    if os.path.isfile(ignore):
        with open(ignore, encoding="utf-8") as f:
            text = f.read()
    if not any(l.strip().strip("/") == SCRATCH for l in text.splitlines()):
        with open(ignore, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + ("" if not text or text.endswith("\n") else "\n") + "/%s/\n" % SCRATCH)
        print("    note: the line /%s/ was added to .gitignore, so the scratch folder is never committed" % SCRATCH)
    return tempfile.mkdtemp(prefix="build-", dir=top)


def copy_skill_scripts(root):
    """Copy every skill script into <root>/hwskills/. Files already there with the same bytes are left;
    a file there with other bytes stops the copy before anything is written."""
    import hwcommon
    dest = os.path.join(os.path.abspath(root), SKILL_FOLDER)
    if os.path.exists(dest) and not os.path.isdir(dest):
        raise Stop(2, "NOT COPIED: %s exists and is not a folder" % dest)
    names = sorted(n for n in os.listdir(HERE) if os.path.isfile(os.path.join(HERE, n))
                   and not n.startswith(".") and not n.endswith((".pyc", ".pyo")))
    clash, same = [], []
    for n in names:
        d = os.path.join(dest, n)
        if os.path.exists(d):
            if os.path.isfile(d) and hwcommon.sha256_file(d) == hwcommon.sha256_file(os.path.join(HERE, n)):
                same.append(n)
            else:
                clash.append(os.path.join(SKILL_FOLDER, n))
    if clash:
        raise Stop(2, "NOT COPIED. These files already exist with other bytes, and nothing was copied:\n    %s\n"
                      "Ask the user. An older copy of the skill scripts is replaced only on the user's word (move "
                      "it aside first); a file of the project's own is never overwritten." % "\n    ".join(clash))
    os.makedirs(dest, exist_ok=True)
    for n in names:
        if n not in same:
            shutil.copyfile(os.path.join(HERE, n), os.path.join(dest, n))
    print("copied %d skill scripts into %s/ (%d already there, same bytes); skills version %s"
          % (len(names) - len(same), SKILL_FOLDER, len(same), hwcommon.SKILLS_VERSION))
    return 0


# ---------------------------------------------------------------- files in the KiCad folder

def skipped_name(name):
    return (name.startswith(("~", "_autosave", "#")) or name.endswith((".lck", ".kicad_prl", ".bak"))
            or name in (".DS_Store", ERC_REPORT))


def walk_kicad(hw):
    """os.walk of the KiCad folder without backups and hidden folders. When the KiCad folder is the
    project root, the skills' own folders (design/, scripts/, datasheets/, docs/, firmware/) are left out."""
    import hwcommon
    is_root = os.path.isdir(os.path.join(hw, "design"))
    for dirpath, dirnames, filenames in os.walk(hw):
        dirnames[:] = sorted(d for d in dirnames if not d.endswith("-backups") and not d.startswith(".")
                             and not (is_root and dirpath == hw and d in hwcommon.LAYOUT_FOLDERS))
        yield dirpath, dirnames, filenames


def all_files(hw):
    """Every file in the KiCad folder except backups, lock files and editor state, as posix paths."""
    out = []
    for dirpath, _, filenames in walk_kicad(hw):
        for n in sorted(filenames):
            if not skipped_name(n):
                out.append(os.path.join(dirpath, n))
    return out


def design_files(root, hw):
    import hwcommon
    out = {}
    for p in all_files(hw):
        if hwcommon.is_design_file(p):
            out[os.path.relpath(p, root).replace(os.sep, "/")] = hwcommon.sha256_file(p)
    return out


def lock_files(hw):
    out = []
    for dirpath, _, filenames in walk_kicad(hw):
        out += [os.path.join(dirpath, n) for n in filenames if n.endswith(".lck")]
    return sorted(out)


# ---------------------------------------------------------------- ownership record

class Ownership:
    def __init__(self, root):
        import hwcommon
        self.h = hwcommon
        self.root = root
        self.path = os.path.join(root, "design", "ownership.csv")
        self.rows = {}
        for r in hwcommon.read_table(self.path):
            r.pop("_line", None)
            self.rows[r["path"]] = r

    def save(self):
        self.h.write_table(self.path, "ownership.csv", [self.rows[k] for k in sorted(self.rows)])

    def set(self, path, owner, writer, digest):
        self.rows[path] = {"path": path, "owner": owner, "writer": writer, "hash": digest,
                           "commit": self.h.git_head(self.root)}

    def status(self, path, digest):
        """None when a script may write the file, else the reason it is protected."""
        r = self.rows.get(path)
        if r is None:
            return "no ownership record, so hand-owned"
        if r["owner"] == "hand":
            return "hand-owned"
        if r["hash"] != digest:
            return "changed since the last script write"
        return None


def last_written(root, path, digest_recorded):
    """The bytes of the last script write, from git HEAD when its hash matches the record."""
    import hwcommon
    data = hwcommon.git(root, "show", "HEAD:" + path)
    if data is not None and digest_recorded and hwcommon.sha256_bytes(data) == digest_recorded:
        return data
    return None


def meaning_diff(path, old, new, note=""):
    """Plain lines saying what changed in meaning between two versions of a design file."""
    import hwcommon
    if old is None:
        return ["no version to compare with: the last script write is not in git at the recorded hash, and "
                "the generator, run in a temporary copy, did not write this file; compare by hand"] + \
            ([note] if note else [])
    if old == new:
        return ["the bytes are the same"]
    out = []
    try:
        if path.endswith(".kicad_pcb"):
            a = hwcommon.board_summary(hwcommon.parse_sexpr(old.decode("utf-8")))
            b = hwcommon.board_summary(hwcommon.parse_sexpr(new.decode("utf-8")))
            fa = dict((f["ref"], f) for f in a["footprints"])
            fb = dict((f["ref"], f) for f in b["footprints"])
            for ref in sorted(set(fa) | set(fb), key=hwcommon.ref_key):
                if ref not in fb:
                    out.append("footprint %s removed" % ref)
                elif ref not in fa:
                    out.append("footprint %s added" % ref)
                else:
                    for k in ("lib_id", "value", "layer", "x", "y", "rot"):
                        if fa[ref][k] != fb[ref][k]:
                            out.append("footprint %s %s: %s -> %s" % (ref, k, fa[ref][k], fb[ref][k]))
                    if sorted((p["number"], p["net"]) for p in fa[ref]["pads"]) != \
                            sorted((p["number"], p["net"]) for p in fb[ref]["pads"]):
                        out.append("footprint %s pad nets changed" % ref)
            for k in sorted(a["counts"]):
                if a["counts"][k] != b["counts"][k]:
                    out.append("%s count: %d -> %d" % (k, a["counts"][k], b["counts"][k]))
            if a["nets"] != b["nets"]:
                out.append("nets added %s, removed %s" % (sorted(set(b["nets"]) - set(a["nets"])) or "none",
                                                          sorted(set(a["nets"]) - set(b["nets"])) or "none"))
        elif path.endswith(".kicad_sch"):
            a = hwcommon.schematic_summary(hwcommon.parse_sexpr(old.decode("utf-8")))
            b = hwcommon.schematic_summary(hwcommon.parse_sexpr(new.decode("utf-8")))
            sa, sb = a["symbols"], b["symbols"]
            for ref in sorted(set(sa) | set(sb), key=hwcommon.ref_key):
                if ref not in sb:
                    out.append("symbol %s removed" % ref)
                elif ref not in sa:
                    out.append("symbol %s added" % ref)
                else:
                    for k in ("lib_id", "x", "y", "rot", "dnp"):
                        if sa[ref][k] != sb[ref][k]:
                            out.append("symbol %s %s: %s -> %s" % (ref, k, sa[ref][k], sb[ref][k]))
                    for f in sorted(set(sa[ref]["fields"]) | set(sb[ref]["fields"])):
                        va, vb = sa[ref]["fields"].get(f), sb[ref]["fields"].get(f)
                        if va != vb:
                            out.append("symbol %s field %s: %r -> %r" % (ref, f, va, vb))
            for k in sorted(a["counts"]):
                if a["counts"][k] != b["counts"][k]:
                    out.append("%s count: %d -> %d" % (k, a["counts"][k], b["counts"][k]))
            if out:
                out.append("export the netlist from the file on disk and compare it with <name>.net in the "
                           "KiCad folder for the nets")
        elif path.endswith(".kicad_pro"):
            a, b = json.loads(old.decode("utf-8")), json.loads(new.decode("utf-8"))
            keys = sorted(set(a) | set(b))
            for k in keys:
                if a.get(k) == b.get(k):
                    continue
                if isinstance(a.get(k), dict) and isinstance(b.get(k), dict):
                    for k2 in sorted(set(a[k]) | set(b[k])):
                        if a[k].get(k2) != b[k].get(k2):
                            out.append("project setting %s.%s changed" % (k, k2))
                else:
                    out.append("project setting %s changed" % k)
    except (ValueError, UnicodeDecodeError) as e:
        out.append("could not read one version (%s)" % e)
    if not out:
        lines = list(difflib.unified_diff(old.decode("utf-8", "replace").splitlines(),
                                          new.decode("utf-8", "replace").splitlines(), lineterm="", n=0))
        changed = [l for l in lines if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        if path.endswith((".kicad_pcb", ".kicad_sch")):
            out.append("no change in meaning found by this summary (%d text lines differ; KiCad may have "
                       "re-saved the file)" % len(changed))
        else:
            out.append("%d text lines differ" % len(changed))
    return out


# ---------------------------------------------------------------- stages

class Build:
    def __init__(self, root, name, waivers, overwrite, keep_hand, settings=None):
        import hwcommon
        import kicad_env
        self.h, self.k = hwcommon, kicad_env
        self.root, self.name = root, name
        self.settings = settings or {"order_folder": FAB_DIR, "order_options": list(FAB_ARGS)}
        self.design = os.path.join(root, "design")
        self.hw, self.hw_rel = hwcommon.kicad_folder(root, self.design)
        self.waivers = waivers
        self.overwrite = overwrite          # path -> DC-
        self.own = Ownership(root)
        for p in keep_hand:
            r = self.own.rows.get(p, {})
            self.own.set(p, "hand", r.get("writer", ""), "")
            print("ownership: %s recorded as hand-owned" % p)
        if keep_hand:
            self.own.save()
        self.sch, self.net = name + ".kicad_sch", name + ".net"
        self.pcb, self.bom = name + ".kicad_pcb", name + "_bom.csv"

    def run(self, cmd, what, env=None):
        print("--- " + what, flush=True)
        res = subprocess.run(cmd, cwd=self.hw, env=env)
        if res.returncode:
            raise Stop(1, "%s failed (exit code %d): %s" % (what, res.returncode, " ".join(cmd)))

    def cli(self, *args):
        self.run([self.k.kicad_cli()] + list(args), "kicad-cli " + " ".join(args[:3]))

    def generator(self, stage, script, args, python):
        """Run a generator stage under the ownership step."""
        writer = "%s (%s)" % (script, stage)
        path = os.path.join(self.root, "scripts", script)
        if not os.path.isfile(path):
            print("--- %s: no scripts/%s, so nothing is generated (the files are used as they are)" % (stage, script))
            return
        before = design_files(self.root, self.hw)
        protected = {}
        for p, digest in before.items():
            why = self.own.status(p, digest)
            if why and p not in self.overwrite:
                protected[p] = why
        known = sorted(p for p, r in self.own.rows.items() if r["writer"] == writer)
        hand = [p for p in known if p in protected and self.own.rows[p]["owner"] == "hand"]
        if hand:
            print("--- %s skipped: it writes %s, which the ownership record says is hand-owned"
                  % (stage, ", ".join(hand)))
            return
        blocked = [p for p in known if p in protected]
        if blocked:
            lines, cleared = [], []
            fresh = self.sandbox(path, args, python, blocked)
            for p in blocked:
                with open(os.path.join(self.root, p), "rb") as f:
                    disk = f.read()
                if fresh.get(p) == disk:            # choice 2 done: the edit is in the generator now
                    cleared.append(p)
                    continue
                old = last_written(self.root, p, self.own.rows[p]["hash"])
                lines.append("%s: %s" % (p, protected[p]))
                if old is not None:
                    lines.append("    the last script write (from git), compared with the file on disk:")
                else:
                    old = fresh.get(p)
                    lines.append("    what the generator writes now (run in a temporary copy), compared with "
                                 "the file on disk:")
                lines += ["    " + l for l in meaning_diff(p, old, disk, self.sandbox_note)]
            for p in cleared:
                print("ownership: %s: the generator, run in a temporary copy, now writes the bytes on disk (the edit "
                      "was carried into it); it is recorded as written by %s" % (p, writer))
                protected.pop(p)
            if lines:
                raise Stop(3, "NOT WRITTEN. Stage %s writes files that changed after the last script write:\n%s\n%s"
                           % (stage, "\n".join(lines), CHOICES))
        snap, stamp = {}, {}
        for p in protected:
            full = os.path.join(self.root, p)
            with open(full, "rb") as f:
                snap[p] = f.read()
            stamp[p] = os.stat(full).st_mtime_ns
        known_stamp = dict((p, os.stat(os.path.join(self.root, p)).st_mtime_ns)
                           for p in known if p in before and p not in protected)
        failure = None
        scratch = scratch_dir(self.root)
        try:
            env = generator_env()
            env[OUTPUTS_ENV] = os.path.join(scratch, "outputs.txt")
            with open(env[OUTPUTS_ENV], "w"):
                pass
            try:
                self.run([python, path] + args, "%s (%s)" % (stage, script), env=env)
            except Stop as e:
                failure = e
            declared = self.declared(env[OUTPUTS_ENV])
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        restored, rewritten = [], []
        for p, data in sorted(snap.items()):
            full = os.path.join(self.root, p)
            now = None
            if os.path.isfile(full):
                with open(full, "rb") as f:
                    now = f.read()
            if now != data:
                with open(full, "wb") as f:
                    f.write(data)
                restored.append((p, now))
            elif os.stat(full).st_mtime_ns != stamp[p] and self.own.rows.get(p, {}).get("owner") != "hand":
                rewritten.append(p)         # written again with the bytes on disk: the generator's output
        after = design_files(self.root, self.hw)
        recorded = []
        for p, digest in sorted(after.items()):
            if p in protected and p not in rewritten:
                continue
            if (before.get(p) != digest or p in self.overwrite or p in rewritten
                    or self.own.rows.get(p, {}).get("writer") == writer):
                self.own.set(p, "script", writer, digest)
                if before.get(p) != digest or p in rewritten:
                    recorded.append(p)
        for p in known:
            if p not in after:              # a file of this generator that is no longer on disk
                del self.own.rows[p]
                print("ownership: %s is gone; its ownership row is dropped" % p)
        # A file this generator wrote before and did not touch in this run (same time stamp, same bytes).
        stale = [p for p in sorted(known_stamp) if p in after and after[p] == before[p]
                 and os.stat(os.path.join(self.root, p)).st_mtime_ns == known_stamp[p]]
        self.own.save()
        for p in rewritten:
            print("ownership: %s had no record; the generator wrote it again with the same bytes, so it is recorded "
                  "as written by %s" % (p, writer))
        for p in self.overwrite:
            if p in after:
                print("ownership: %s written under %s" % (p, self.overwrite[p]))
        restored_text = ""
        if restored:
            lines = []
            for p, generated in restored:
                lines.append("%s: %s; the generator tried to change it and the file on disk was put back"
                             % (p, protected[p]))
                if generated is not None:
                    lines += ["    what the generator writes now, compared with the file on disk:"]
                    lines += ["    " + l for l in meaning_diff(p, generated, snap[p])]
            restored_text = "NOT WRITTEN:\n%s\n%s" % ("\n".join(lines), CHOICES)
        if failure is not None:
            if recorded:
                print("ownership: the generator failed, but the files it wrote are its output and are recorded as "
                      "written by %s, so the next run is not blocked by them: %s" % (writer, ", ".join(recorded)))
            if restored_text:
                print(restored_text, file=sys.stderr)
            raise failure
        if restored_text:
            raise Stop(3, restored_text)
        # A generator may leave an unchanged file alone. A file it declared is its output. For the others,
        # run it in a copy without them: a file it writes there is still its output.
        stale = [p for p in stale if p not in declared]
        if stale:
            fresh = self.sandbox(path, args, python, stale, remove=stale)
            kept = [p for p in stale if p in fresh]
            if kept:
                print("    note: not written again in this run, but still written by %s when the file is taken away "
                      "(checked in a temporary copy), so still its output: %s" % (script, ", ".join(kept)))
            stale = [p for p in stale if p not in fresh]
        if stale:
            raise Stop(3, "NOT WRITTEN BY THE GENERATOR ANY MORE. Stage %s ran, but %s did not write these files, "
                          "which it wrote before (same time stamp and bytes as before the run; not declared by "
                          "the generator; not written in a temporary copy with the file taken away):\n    %s\n%s"
                          "They are still on disk and KiCad and the checks still read them. Nothing was deleted. "
                          "Choices for the user: 1 remove the file (its ownership row is dropped at the next "
                          "build); 2 make the generator write it again; 3 keep it as a hand-owned file: delete "
                          "its row from design/ownership.csv and run build.py --adopt."
                       % (stage, script, "\n    ".join(stale),
                          self.sandbox_note + "\n" if self.sandbox_note else ""))

    def declared(self, listing):
        """The files a generator declared as its own in the file named by HWSKILLS_OUTPUTS, as project paths."""
        out = set()
        root = os.path.realpath(self.root)
        try:
            with open(listing, encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
        except (OSError, UnicodeDecodeError):
            return out
        for line in lines:
            full = os.path.realpath(os.path.join(self.hw, line))
            if full.startswith(root + os.sep):
                out.add(os.path.relpath(full, root).replace(os.sep, "/"))
        return out

    sandbox_note = ""

    def sandbox(self, script_path, args, python, paths, remove=()):
        """Run a generator in a temporary copy of the project, in .hwtmp/; return {path: bytes it wrote}.
        The files in remove are left out of the copy. When the generator fails there, self.sandbox_note
        holds its exit code and last lines."""
        tmp = scratch_dir(self.root)
        self.sandbox_note = ""
        try:
            for sub in ("scripts", "design"):
                src = os.path.join(self.root, sub)
                if os.path.isdir(src):
                    shutil.copytree(src, os.path.join(tmp, sub))
            here_rel = os.path.relpath(HERE, self.root)
            skill = HERE
            if not here_rel.startswith(os.pardir) and here_rel != ".":
                skill = os.path.join(tmp, here_rel)
                if not os.path.isdir(skill):
                    shutil.copytree(HERE, skill, ignore=shutil.ignore_patterns("__pycache__"))
            for f in all_files(self.hw):
                if os.path.relpath(f, self.root).replace(os.sep, "/") in remove:
                    continue
                dst = os.path.join(tmp, os.path.relpath(f, self.root))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(f, dst)
                os.utime(dst, (0, 0))       # an old time stamp: a file the generator writes gets a new one
            script = os.path.join(tmp, os.path.relpath(script_path, self.root))
            env = generator_env()
            env.pop(OUTPUTS_ENV, None)
            env["PYTHONPATH"] = env["PYTHONPATH"].replace(HERE, skill, 1)
            res = subprocess.run([python, script] + args, cwd=os.path.normpath(os.path.join(tmp, self.hw_rel)),
                                 capture_output=True, env=env)
            out = {}
            if res.returncode != 0:
                tail = (res.stdout + res.stderr).decode("utf-8", "replace").strip().splitlines()[-8:]
                self.sandbox_note = ("the generator failed in the temporary copy (exit code %d); its last lines:\n%s"
                                     % (res.returncode, "\n".join("        " + l for l in tail)))
            for p in paths if res.returncode == 0 else []:
                full = os.path.join(tmp, p)
                if os.path.isfile(full) and os.stat(full).st_mtime != 0:     # written by the generator
                    with open(full, "rb") as fh:
                        out[p] = fh.read()
            return out
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def waive_args(self):
        out = []
        for w in self.waivers:
            out += ["--waive", w]
        return out

    def stage_sch(self):
        self.generator("sch", "gen_sch.py", [self.sch] + self.waive_args(), sys.executable)

    def stage_erc(self):
        expected, errors = self.h.expected_erc_items(self.design)
        errors += self.h.check_waivers(sorted(set(e[2] for e in expected)), self.design)
        if errors:
            raise Stop(2, "Expected ERC items in design/status.md:\n    " + "\n    ".join(errors))
        self.cli("sch", "erc", "--format", "json", "--severity-all", "-o", ERC_REPORT, self.sch)
        with open(os.path.join(self.hw, ERC_REPORT), encoding="utf-8") as f:
            erc = json.load(f)
        bad = [v for sheet in erc.get("sheets", []) for v in sheet.get("violations", [])]
        new, seen = [], set()
        for v in bad:
            items = [i.get("description", "") for i in v.get("items", [])]
            hit = erc_hits(expected, v)
            seen.update(hit)
            if not hit:
                new.append(v)
            print("    %s%s %s: %s (%s)" % ("new: " if expected and not hit else "", v.get("severity"),
                                            v.get("type"), v.get("description"), "; ".join(items)))
        gone = [e for e in expected if e not in seen]
        for e in gone:
            print('    no longer found: "%s" on %s, %s' % e)
        if not bad and not expected:
            print("ERC: 0 violations")
            return
        count = "ERC: %d violations: %d expected%s, %d new" % (
            len(bad), len(bad) - len(new), " (design/status.md)" if expected else "", len(new))
        if (new or gone) and self.waivers:
            print("%s, WAIVED by %s" % (count, ", ".join(self.waivers)))
        elif new:
            raise Stop(1, count + ". Fix the new ones, or record a waiver and pass --waive DC-nnn. A violation "
                       "that waits on work not yet done is recorded under a decision and listed under "
                       "\"Expected ERC items\" in design/status.md. The report is %s in the KiCad folder."
                       % ERC_REPORT)
        elif gone:
            raise Stop(1, count + ". Expected items no longer found: %d. For each, remove its line from "
                       "\"Expected ERC items\" in design/status.md, so the list stays the true one." % len(gone))
        else:
            print(count)

    def stage_netlist(self):
        self.cli("sch", "export", "netlist", "--format", "kicadsexpr", "-o", self.net, self.sch)
        sanitise_netlist(os.path.join(self.hw, self.net))
        print("    %s written again (an export: never protected; a hand edit to it is lost)" % self.net)

    def stage_bom(self):
        self.cli("sch", "export", "bom", "--fields", ",".join(BOM_FIELDS), "--labels", ",".join(BOM_LABELS),
                 "--group-by", "Value,Footprint,MPN", "--ref-range-delimiter", "", "-o", self.bom, self.sch)
        print("    %s written again (an export: never protected; a hand edit to it is lost)" % self.bom)

    def stage_board(self):
        self.generator("board", "gen_pcb.py", [self.net, self.pcb] + self.waive_args(), pcbnew_python(self.k))

    def stage_fab(self):
        fab = os.path.join(HERE, "fab.py")          # the skill's own, beside this file
        args = [self.pcb, self.settings["order_folder"]] + list(self.settings["order_options"]) + self.waive_args()
        self.run([sys.executable, fab] + args, "fabrication files")


CHOICES = ("Choices for the user: 1 keep the edit (build.py --keep-hand PATH); 2 carry the edit into the "
           "generator, rebuild and show the result matches; 3 overwrite it, recorded as a decision "
           "(build.py --overwrite PATH=DC-nnn).")


POWER_REF_RE = re.compile(r"#(PWR|FLG)\w*")     # the reference of a power symbol or a power flag


def erc_form(text):
    """An ERC text with the number of every power symbol and power flag reference left out (#PWR104
    reads as #PWR). Several power symbols sit on one net, and KiCad names any one of them, not the
    same one in every run."""
    return POWER_REF_RE.sub(lambda m: "#" + m.group(1), text)


def erc_hits(expected, violation):
    """The expected ERC items, as (text, item, DC-) tuples, that one violation of the ERC report matches:
    the text is in the violation's description, and the item starts one of its item descriptions.
    Both sides are compared in erc_form(), so the match does not depend on which power symbol is named."""
    text = erc_form(violation.get("description", ""))
    items = [erc_form(i.get("description", "")) for i in violation.get("items", [])]
    return [e for e in expected if erc_form(e[0]) in text
            and any(d == erc_form(e[1]) or d.startswith(erc_form(e[1]) + " ") for d in items)]


def sanitise_netlist(path):
    """KiCad writes the schematic's absolute path and the export time into the netlist; keep only
    the file name and drop the time, so the file is the same on every machine and run."""
    with open(path, encoding="utf-8") as f:
        text = f.read()

    def rel(m):
        return '(source "%s")' % re.split(r"[\\/]", m.group(1))[-1]
    text = re.sub(r'\(source "([^"]*[\\/][^"]*)"\)', rel, text)
    text = re.sub(r'\(date "[^"]*"\)', '(date "")', text)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def pcbnew_python(kicad_env):
    """An interpreter that can import pcbnew: this one, $KICAD_PYTHON or KiCad's own."""
    try:
        import pcbnew  # noqa: F401
        return sys.executable
    except ImportError:
        pass
    path = kicad_env.kicad_python()
    if not os.path.exists(path):
        raise Stop(2, kicad_env.pcbnew_hint("build.py (stage board)")
                   + "\nor set KICAD_PYTHON to an interpreter that has pcbnew.")
    return path


def find_name(hw, label="hardware/"):
    for ext in (".kicad_pro", ".kicad_sch"):
        found = sorted(f[:-len(ext)] for f in os.listdir(hw) if f.endswith(ext))
        if len(found) == 1:
            return found[0]
        if len(found) > 1 and ext == ".kicad_pro":
            raise Stop(2, "%s holds several projects (%s); pass --name" % (label, ", ".join(found)))
    raise Stop(2, "cannot tell the project name from %s; set \"project\" in %s or pass --name" % (label, SETTINGS))


def has_kicad_project(folder):
    return os.path.isdir(folder) and any(f.endswith((".kicad_pro", ".kicad_sch")) for f in os.listdir(folder))


def adopt_folder(root, design):
    """Find the one folder holding a KiCad project (the root included) and record it in design/status.md.
    Returns its name relative to the root."""
    import hwcommon
    found = hwcommon.kicad_project_folders(root)
    if not found:
        raise Stop(2, "no KiCad project (.kicad_pro) in %s or its folders; nothing to adopt" % root)
    if len(found) > 1:
        raise Stop(2, "KiCad projects in several folders (%s). Write the one to adopt into design/status.md as "
                      "the line 'KiCad folder: <folder>' and run build.py --adopt again."
                   % ", ".join(hwcommon.folder_label(f) for f in found))
    line = hwcommon.record_kicad_folder(design, found[0])
    print("KiCad files found in %s; the layout is kept, and design/status.md now says: %s"
          % (hwcommon.folder_label(found[0]), line))
    return found[0]


def snapshot(hw):
    import hwcommon
    return dict((os.path.relpath(p, hw).replace(os.sep, "/"), hwcommon.sha256_file(p)) for p in all_files(hw))


def reproduce(root, command, rel="hardware"):
    """Run the project's own build command in a temporary copy of the project, in .hwtmp/. Returns
    {design file path: (reproduced?, reason)} for every design file in the KiCad folder rel."""
    tmp = scratch_dir(root)
    try:
        copy = os.path.join(tmp, os.path.basename(root) or "project")
        shutil.copytree(root, copy, ignore=shutil.ignore_patterns(".git", SCRATCH, "*.lck", "_autosave-*", "*-backups"))
        hw_copy = os.path.normpath(os.path.join(copy, rel))
        files = design_files(copy, hw_copy)
        for p in files:                     # an old time stamp: a file the command writes gets a new one
            os.utime(os.path.join(copy, p), (0, 0))
        print("--- reproduce: running the project's own build in a temporary copy: %s" % command, flush=True)
        res = subprocess.run(command, shell=True, cwd=copy)
        out = {}
        after = design_files(copy, hw_copy)
        for p, digest in sorted(files.items()):
            full = os.path.join(copy, p)
            if res.returncode != 0:
                out[p] = (False, "the build command failed (exit code %d)" % res.returncode)
            elif p not in after:
                out[p] = (False, "the build command removed it")
            elif os.stat(full).st_mtime == 0:
                out[p] = (False, "the build command did not write it")
            elif after[p] != digest:
                out[p] = (False, "the build command writes different bytes")
            else:
                out[p] = (True, "reproduced byte for byte")
        for p in sorted(set(after) - set(files)):
            print("    note: the build command also writes %s, which is not in the project" % p)
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def adopt(root, command=None, rel="hardware"):
    """Record the design files in the KiCad folder rel that have no ownership record: hand-owned, or
    script-owned where the project's own build reproduces them byte for byte (--reproduce)."""
    own = Ownership(root)
    files = design_files(root, os.path.normpath(os.path.join(root, rel)))
    results = reproduce(root, command, rel) if command else {}
    writer = "%s (own build)" % command if command else ""
    for p, digest in sorted(files.items()):
        if p in own.rows:
            print("ownership: %s already recorded (%s); left as it is" % (p, own.rows[p]["owner"]))
            continue
        ok, why = results.get(p, (False, ""))
        if ok:
            own.set(p, "script", writer, digest)
            print("ownership: %s recorded as script-owned, writer %s (%s)" % (p, writer, why))
        else:
            own.set(p, "hand", "", digest)
            print("ownership: %s recorded as hand-owned%s" % (p, " (%s)" % why if why else ""))
    own.save()
    return 0


def build(a, want):
    b = Build(a.root, a.name, a.waive, a.overwrite, a.keep_hand, a.settings)
    for s in STAGES:
        if s in want:
            getattr(b, "stage_" + s)()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stages", nargs="*")
    ap.add_argument("--root", default=default_root())
    ap.add_argument("--copy-skill-scripts", metavar="DIR")
    ap.add_argument("--name")
    ap.add_argument("--twice", action="store_true")
    ap.add_argument("--waive", action="append", default=[], metavar="DC-nnn")
    ap.add_argument("--keep-hand", action="append", default=[], metavar="PATH")
    ap.add_argument("--overwrite", action="append", default=[], metavar="PATH=DC-nnn")
    ap.add_argument("--ignore-lock", action="store_true")
    ap.add_argument("--adopt", action="store_true")
    ap.add_argument("--reproduce", metavar="COMMAND")
    a = ap.parse_args(argv)
    a.root = os.path.abspath(a.root)
    design = os.path.join(a.root, "design")
    table_error = ()        # hwcommon's errors once the scripts folder is on the path; () catches nothing
    if a.copy_skill_scripts:
        setup_paths(a.root)
        try:
            return copy_skill_scripts(a.copy_skill_scripts)
        except Stop as e:
            print(str(e), file=sys.stderr)
            return e.code
    try:
        if not os.path.isdir(design):
            raise Stop(2, "no design/ folder in %s; the ownership record lives in design/ownership.csv (set the "
                          "project up first, or run build.py from the project root or pass --root)" % a.root)
        setup_paths(a.root)
        import hwcommon
        table_error = (hwcommon.TableError, hwcommon.ProjectError)
        hw, rel = hwcommon.kicad_folder(a.root, design)
        if a.adopt and hwcommon.recorded_kicad_folder(design) is None and not has_kicad_project(hw):
            rel = adopt_folder(a.root, design)
            hw = os.path.normpath(os.path.join(a.root, rel))
        label = hwcommon.folder_label(rel)
        if not os.path.isdir(hw):
            raise Stop(2, "no %s folder in %s. The KiCad files are looked for in hardware/ unless design/status.md "
                          "names another folder on a 'KiCad folder:' line; for an existing project, build.py "
                          "--adopt finds them and writes that line." % (label, a.root))
        unknown = [s for s in a.stages if s not in STAGES and s != "checks"]
        if unknown:
            raise Stop(2, "unknown stage %s; stages: %s checks" % (", ".join(unknown), " ".join(STAGES)))
        want = a.stages or list(STAGES)
        a.settings = read_settings(a.root)
        overwrite = {}
        for item in a.overwrite:
            path, _, dc = item.partition("=")
            overwrite[path.replace(os.sep, "/")] = dc
        problems = hwcommon.check_waivers(a.waive + list(overwrite.values()), os.path.join(a.root, "design"))
        if problems:
            raise Stop(2, "\n".join(problems))
        a.overwrite = overwrite
        a.keep_hand = [p.replace(os.sep, "/") for p in a.keep_hand]
        a.name = a.name or a.settings["project"] or find_name(hw, label)
        locks = lock_files(hw)
        if locks and not a.ignore_lock:
            raise Stop(5, "KiCad lock file found (%s): KiCad may have the project open. Close KiCad without "
                       "saving, then build again (or pass --ignore-lock if the lock file is stale)."
                       % ", ".join(os.path.basename(l) for l in locks))
        if a.reproduce and not a.adopt:
            raise Stop(2, "--reproduce goes with --adopt")
        if a.adopt:
            if a.stages:
                raise Stop(2, "--adopt runs no stage; build afterwards")
            adopt(a.root, a.reproduce, rel)
            print("done: adopt")
            return 0
        for w in a.waive:
            print("waiver in force: %s" % w)
        build(a, want)
        done = [s for s in STAGES if s in want]
        if a.twice:
            first = snapshot(hw)
            print("=== second build, to compare")
            a.keep_hand = []
            build(a, want)
            second = snapshot(hw)
            diff = sorted(p for p in set(first) | set(second) if first.get(p) != second.get(p))
            if diff:
                raise Stop(4, "NOT repeatable: %d files differ between the two builds:\n    %s"
                           % (len(diff), "\n    ".join(diff)))
            print("repeatable: %d files in %s are byte-identical after two builds" % (len(second), label))
        if a.settings["checks"] or "checks" in want:
            run_checks(a.root, a.settings["checks"])
            done.append("checks")
    except Stop as e:
        print(str(e), file=sys.stderr)
        return e.code
    except table_error as e:
        print("build: %s" % e, file=sys.stderr)
        return 2
    print("done: " + " ".join(done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
