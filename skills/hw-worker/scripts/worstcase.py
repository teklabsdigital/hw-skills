# Copyright 2026 Teklabs Digital (hw-skills)
# SPDX-License-Identifier: Apache-2.0
"""Worst-case helper for the calc scripts in design/calcs/. Python 3 standard library only.

Use it from a calc script:

    from worstcase import tol, extremes, monte_carlo, report
    INPUTS = {"r_top": tol(100e3, 1), "v_ref": (0.788, 0.800, 0.812)}   # (min, nominal, max)
    ok = report("lockout rising", result, INPUTS, LIMIT)                # prints min, nominal, max

or run it on a calc script written from the template in references/project-files.md (a file that
defines INPUTS, LIMIT and result(v)):

    python3 worstcase.py design/calcs/<block>_<what>.py [--mc N] [--seed S] [--write]

Extreme-value corners are the default: every combination of each input's minimum and maximum.
--mc N adds a seeded Monte Carlo run (uniform within each input's range); the seed is printed.
--write saves the printed lines to design/calcs/<block>_<what>.txt.
Every result has a line "terms left out:". It lists what the equation does not hold (a drift, a leakage,
a tolerance not in INPUTS), read from the calc script's LEFT_OUT = ["<term>", ...], or from report()'s
left_out. An empty list prints "none". With no list the line says NOT STATED. Carry the line to wherever
the result is used.
Exit code 0 inside the limit, 1 outside it (a violation unless a decision covers it), 2 on a bad file.
"""
import argparse
import ast
import itertools
import os
import random
import sys


def tol(nominal, percent):
    """(min, nominal, max) for a symmetric tolerance in percent."""
    d = abs(nominal) * percent / 100.0
    return (nominal - d, nominal, nominal + d)


def corners(inputs):
    """Every combination of each input's minimum and maximum, as dicts."""
    names = list(inputs)
    return [dict(zip(names, c)) for c in itertools.product(*[(inputs[n][0], inputs[n][2]) for n in names])]


def extremes(fn, inputs):
    """(low, nominal, high, corner at low, corner at high) over the extreme-value corners."""
    vals = [(fn(c), c) for c in corners(inputs)]
    low, high = min(vals, key=lambda v: v[0]), max(vals, key=lambda v: v[0])
    return low[0], fn({k: v[1] for k, v in inputs.items()}), high[0], low[1], high[1]


def monte_carlo(fn, inputs, n=10000, seed=1):
    """(low, mean, high) of n runs with each input uniform in its range; repeatable for one seed."""
    rng = random.Random(seed)
    vals = [fn({k: rng.uniform(v[0], v[2]) for k, v in inputs.items()}) for _ in range(n)]
    return min(vals), sum(vals) / len(vals), max(vals)


def left_out_line(left_out):
    """The line that lists the terms a result left out. None: the calc script did not state them."""
    if left_out is None:
        return ("  terms left out: NOT STATED (add LEFT_OUT = [\"<term>\", ...] to the calc script; "
                "an empty list when nothing is left out)")
    if isinstance(left_out, str):
        left_out = [left_out]
    if not isinstance(left_out, (list, tuple)) or not all(isinstance(t, str) for t in left_out):
        raise ValueError("LEFT_OUT must be a list of the terms left out, each in words")
    terms = [t.strip() for t in left_out if t.strip()]
    return "  terms left out: %s" % ("; ".join(terms) if terms else "none")


def report(name, fn, inputs, limit=None, mc=0, seed=1, out=print, left_out=None):
    """Print min, nominal and max (and Monte Carlo when mc > 0), then the terms left out; True when
    inside the limit. left_out is the list of terms the equation does not hold (an empty list for none)."""
    terms = left_out_line(left_out)
    low, nom, high, c_low, c_high = extremes(fn, inputs)
    out("%s: min %.6g  nominal %.6g  max %.6g  limit %s" % (name, low, nom, high, limit if limit else "none"))
    out("  min at: " + ", ".join("%s=%.6g" % kv for kv in sorted(c_low.items())))
    out("  max at: " + ", ".join("%s=%.6g" % kv for kv in sorted(c_high.items())))
    if mc:
        m_low, m_mean, m_high = monte_carlo(fn, inputs, mc, seed)
        out("  Monte Carlo (%d runs, uniform, seed %d): min %.6g  mean %.6g  max %.6g" % (mc, seed, m_low, m_mean, m_high))
    out(terms)
    ok = limit is None or (limit[0] <= low and high <= limit[1])
    out("  %s" % ("inside the limit" if ok else "OUTSIDE THE LIMIT"))
    return ok


def load_calc(path):
    """INPUTS, LIMIT and result from a calc script, without running its own print and assert lines."""
    space = load_calc_names(path)
    return space["INPUTS"], space.get("LIMIT"), space["result"]


def load_calc_names(path):
    """Every name a calc script defines (INPUTS, LIMIT, LEFT_OUT, result), without running its own
    print and assert lines."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    # Imports, functions and UPPER-CASE constants only; the template's own corner loop, print and assert
    # lines are left out, so this file does the arithmetic once.
    keep = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef))
            or (isinstance(n, ast.Assign) and all(isinstance(t, ast.Name) and t.id.isupper() for t in n.targets))]
    space = {"__name__": "calc", "__file__": path}
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    exec(compile(ast.Module(body=keep, type_ignores=[]), path, "exec"), space)  # noqa: S102 - the user's own calc
    for key in ("INPUTS", "result"):
        if key not in space:
            raise ValueError("%s defines no %s" % (path, key))
    return space


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("calc", help="a calc script that defines INPUTS, LIMIT and result(v)")
    ap.add_argument("--mc", type=int, default=0, metavar="N", help="also run N seeded Monte Carlo trials")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--write", action="store_true", help="save the output beside the script as .txt")
    a = ap.parse_args(argv)
    try:
        space = load_calc_names(a.calc)
        inputs, limit, fn, left_out = space["INPUTS"], space.get("LIMIT"), space["result"], space.get("LEFT_OUT")
        bad = [k for k, v in inputs.items() if len(v) != 3 or not v[0] <= v[1] <= v[2]]
        if bad:
            raise ValueError("INPUTS %s must be (min, nominal, max) in that order" % ", ".join(bad))
        left_out_line(left_out)
    except (OSError, SyntaxError, ValueError, TypeError) as e:
        print("worstcase: %s" % e, file=sys.stderr)
        return 2
    lines = []
    ok = report(os.path.splitext(os.path.basename(a.calc))[0], fn, inputs, limit, a.mc, a.seed, lines.append,
                left_out)
    print("\n".join(lines))
    if a.write:
        txt = os.path.splitext(a.calc)[0] + ".txt"
        with open(txt, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        print("wrote %s" % txt)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
