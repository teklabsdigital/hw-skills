# Copyright 2026 Teklabs Digital (hw-skills)
# SPDX-License-Identifier: Apache-2.0
"""Where KiCad lives on this machine: the only place the scripts look it up.

Each location is taken from the first of
  1. the project's environment variable (KICAD_CLI, KICAD_FOOTPRINT_DIR, KICAD_SYMBOL_DIR,
     KICAD_3DMODEL_DIR, KICAD_PYTHON),
  2. KiCad's own variable, if it is set (KICAD10_FOOTPRINT_DIR, KICAD10_SYMBOL_DIR,
     KICAD10_3DMODEL_DIR),
  3. the default install location of KiCad 10 on macOS, Windows or Linux,
and must exist; otherwise the script stops and says which variable to set.

    python3 kicad_env.py        prints what was found, and the kicad-cli version line,
                                for design/status.md

Developed on macOS. Default paths for Windows and Linux are included.
Plain Python, no pcbnew.
"""
import os
import shutil
import subprocess
import sys

KICAD_VERSION = "10.0"


def _program_files():
    return os.environ.get("ProgramFiles", r"C:\Program Files")


def _defaults(what):
    """Default install locations of KiCad 10, most likely first."""
    if sys.platform == "darwin":
        app = "/Applications/KiCad/KiCad.app/Contents"
        return {"cli": [os.path.join(app, "MacOS", "kicad-cli")],
                "share": [os.path.join(app, "SharedSupport")],
                "python": [os.path.join(app, "Frameworks", "Python.framework", "Versions", "Current",
                                        "bin", "python3")]}[what]
    if sys.platform == "win32":
        root = os.path.join(_program_files(), "KiCad", KICAD_VERSION)
        return {"cli": [os.path.join(root, "bin", "kicad-cli.exe")],
                "share": [os.path.join(root, "share", "kicad")],
                "python": [os.path.join(root, "bin", "python.exe")]}[what]
    return {"cli": [p for p in (shutil.which("kicad-cli"),) if p] + ["/usr/bin/kicad-cli"],
            "share": ["/usr/share/kicad", "/usr/local/share/kicad"],
            "python": ["/usr/bin/python3"]}[what]


class NotFound(Exception):
    pass


def _lookup(own_var, kicad_var, defaults, what):
    for var in (own_var, kicad_var):
        if var and os.environ.get(var):
            path = os.environ[var]
            if not os.path.exists(path):
                raise NotFound("%s is set to %r, which does not exist." % (var, path))
            return path
    for path in defaults:
        if os.path.exists(path):
            return path
    raise NotFound("KiCad %s: cannot find the %s (looked in: %s).\n"
                   "Install KiCad %s, or set the environment variable %s to its location."
                   % (KICAD_VERSION, what, ", ".join(defaults) or "PATH", KICAD_VERSION, own_var))


def _find(own_var, kicad_var, defaults, what):
    try:
        return _lookup(own_var, kicad_var, defaults, what)
    except NotFound as e:
        sys.exit(str(e))


def _share(sub):
    return [os.path.join(d, sub) for d in _defaults("share")]


def kicad_cli():
    """Path of the kicad-cli program (stops with a message if it is not found)."""
    return _find("KICAD_CLI", None, _defaults("cli"), "kicad-cli program")


def find_kicad_cli():
    """Path of the kicad-cli program, or None (for callers that can go on without it)."""
    try:
        return _lookup("KICAD_CLI", None, _defaults("cli"), "kicad-cli program")
    except NotFound:
        return None


def footprint_dir():
    """KiCad's footprint library folder (holds the *.pretty folders)."""
    return _find("KICAD_FOOTPRINT_DIR", "KICAD10_FOOTPRINT_DIR", _share("footprints"), "footprint libraries")


def symbol_dir():
    """KiCad's symbol library folder (holds the *.kicad_sym files)."""
    return _find("KICAD_SYMBOL_DIR", "KICAD10_SYMBOL_DIR", _share("symbols"), "symbol libraries")


def model_dir():
    """KiCad's 3D model folder (holds the *.3dshapes folders)."""
    return _find("KICAD_3DMODEL_DIR", "KICAD10_3DMODEL_DIR", _share("3dmodels"), "3D model libraries")


def kicad_python():
    """A Python that can import pcbnew: $KICAD_PYTHON, else KiCad's own (best guess for this OS)."""
    if os.environ.get("KICAD_PYTHON"):
        return os.environ["KICAD_PYTHON"]
    for path in _defaults("python"):
        if os.path.exists(path):
            return path
    return _defaults("python")[0]


def cli_version(cli=None):
    """The first lines of `kicad-cli version --format about` (version and build), or ''."""
    cli = cli or find_kicad_cli()
    if not cli:
        return ""
    try:
        res = subprocess.run([cli, "version", "--format", "about"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    except OSError:
        return ""
    keep = [l.strip() for l in res.stdout.splitlines() if l.strip().startswith(("Version:", "Date:"))]
    return "; ".join(keep)


def pcbnew_hint(script):
    """Message for a script that needs pcbnew but was started with another Python."""
    if sys.platform == "linux":
        how = ("the system Python that KiCad's package installed pcbnew for (usually /usr/bin/python3;\n"
               "on Debian and Ubuntu the kicad package provides it)")
    else:
        how = "KiCad's own Python:\n    " + kicad_python()
    return ("%s needs KiCad's pcbnew module, which this Python (%s) does not have.\nRun it with %s"
            % (script, sys.executable, how))


def require_pcbnew(script):
    """Import and return pcbnew, or stop with a message naming the right interpreter."""
    try:
        import pcbnew
    except ImportError:
        sys.exit(pcbnew_hint(script))
    return pcbnew


if __name__ == "__main__":
    for name, fn in (("kicad-cli", kicad_cli), ("footprints", footprint_dir), ("symbols", symbol_dir),
                     ("3D models", model_dir)):
        print("%-11s %s" % (name, fn()))
    print("%-11s %s (a Python that should import pcbnew; not tried here)" % ("pcbnew", kicad_python()))
    print("%-11s %s" % ("version", cli_version() or "unknown"))
