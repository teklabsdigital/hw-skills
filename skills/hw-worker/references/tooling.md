# Tooling

Tools, installs and the known traps of working with KiCad from scripts.

## Contents

Install policy; KiCad; KiCad facts; Never save from the editor; Two fill engines; Simulator; PDF tools; Router; Long runs; Repeatability; Platforms.

## Install policy

- Install nothing without the user's approval. Ask through your report, with what, why, the exact version and the source.
- Choose a version released at least 30 days before today. Check the release date on the project's own release page and cite it. If every release is newer than 30 days, flag it instead of choosing.
- Pin the exact version in the project (no ranges, no "latest"). Turn off auto-update where the tool has it. Never run blanket upgrade commands.
- When a tool is needed, offer both an existing tool and, if it is small, an option to build one, with the trade-off. If a loop is too slow to iterate (for example a router taking many minutes per run), say so and propose a faster route; do not just wait.
- Record every tool and version in `design/status.md`.
- The user may have a rule of their own on tool versions and automatic updates. It is asked once at setup and kept in the `Tool version rule:` line of `design/status.md`. Apply it to every new install, and to the tools already installed: at setup, report the version and release date of each installed tool the project uses and check each against the rule. A tool that does not meet it is reported, not changed; each exception the user allows is recorded as a decision.
- KiCad's own update check and its backup settings are the user's settings, outside the project. Report what they are. Do not change them.

## KiCad

- The project names one KiCad release (10.0.x at the time of writing), chosen by the install policy and recorded in `design/status.md`.
- `kicad_env.py` is the only place KiCad's locations are looked up: environment variables first (`KICAD_CLI`, `KICAD_FOOTPRINT_DIR`, `KICAD_SYMBOL_DIR`, `KICAD_3DMODEL_DIR`), then KiCad's own variables, then the default install location for the operating system. Run it at setup and record what it found.
- Board scripts need a Python that can import `pcbnew`. `build.py` uses the Python you started if it can, else `KICAD_PYTHON`, else KiCad's own Python. KiCad's bundled Python may lack common packages: use the standard library only.
- Run the tests of a tool with the same Python that will run the project scripts. A test that passes under another Python shows nothing about the one in use.
- `kicad-cli` does ERC, DRC, exports and renders. Prefer it to the editor for anything that must be repeatable.

## KiCad facts

Check each of these on the KiCad version the project uses.

- The exported netlist leaves out a net with no pin on it.
- Power symbols join by name across all sheets. Two rails drawn with the same power symbol name are one net, and the rules check (ERC) does not flag it. `sch_check.py rails` is the check for this.
- ERC complains about empty sub-sheets, and about power flags until the supply sheet is drawn. List these as expected ERC items while they wait (`references/project-files.md`, status.md).
- An unused pin tied to ground may need its pin type set to passive to pass ERC.
- Removing a label renames its net. Compare nets by their members (the pins on them), not by name.
- The lock files are `~<file>.kicad_sch.lck` and `~<file>.kicad_pro.lck`, beside the open file.

## Never save from the editor

KiCad rewrites files it has open, including the project file, and can change rules, severities, net classes, labels and text sizes. On an earlier board an open editor silently loosened rule severities and dropped a net class.

- Before any regeneration or edit of a file the user may have open, the report and the coordinator say: "close KiCad without saving".
- Before every build, look for the lock files KiCad writes beside open files (KiCad facts). If one is there, stop: the user closes KiCad. Never remove a lock file, and never build in a copy to get round one. `build.py` stops on a lock file too. The names are not verified for every KiCad version; record what you see.
- The project file and rule file are written whole by `project_settings.py` from the project tables, so editor changes do not survive a build. A setting changed in the editor is lost: any setting the design needs belongs in the tables.
- For a hand-owned file the engineer may edit in KiCad, see `references/adapting.md`.

## Two fill engines

KiCad's Python zone filler ignores the custom rules in the rule file. A fill made only by the Python filler can pass checks it should fail.

- Re-pour zones with `kicad-cli pcb drc --refill-zones --save-board` before trusting a fill or a DRC result. `python3 hwskills/pcblib.py drc BOARD` does this; a generator built on `pcblib.py` does it in its last step.
- The re-pour saves the board, so on a hand-owned board it runs on a copy. `pcblib.py drc` decides from `design/ownership.csv`: in place only when the board is recorded as script-owned and its hash matches, otherwise on a copy, and it checks the board's bytes are unchanged afterwards.

## Simulator

KiCad ships a circuit simulator library, and `spice.py` loads it. Nothing is installed, so simulation needs no approval under the install policy. Run `spice.py engine-check` once on each machine and KiCad version before any result is trusted. The known traps of the library are listed in `references/simulation.md` (Engine facts); read them before driving it.

## PDF tools

The route for reading datasheets, in order: your tool's own PDF reading and page viewing; on macOS only, the skill's `pdftext.swift` and `pdfpage.swift`; elsewhere an approved, pinned install. Record the route in `design/status.md`. If pages cannot be rendered and viewed, figure and graph rows stay open, and the report says so first. Details: `references/datasheets.md`, PDF route.

- A text extract collapses numbered lists and drops figures and graphs. Read those pages from the renders.
- A scanned page has no text layer. The fetch lists such pages; they are read from the renders only.
- A copy from a distributor or another host may carry a cover page or lack pages, so its page numbers differ from the maker's copy. Such a copy is checked before use (`references/datasheets.md`, Get).
- A very large PDF may hold the same text in several languages. Extract and render only the pages in the working language, and record which.

## Router

The grid router is the standard method for routing, strongly recommended because it makes re-routing fast. It is a separate library and repository: https://github.com/teklabsdigital/hw-gridrouter

- Clone it into the folder `router/` inside the project root, git-ignored, only with approval. Never above or beside the project. It has no tagged release yet, so pin an exact commit (a tag once one exists). Record which in `design/status.md`.
- Build it with the C compiler, and run its own test suite after building. Report the result.
- `pcblib.py` is the glue between KiCad boards and the router (see `references/board.md`, Router). It looks in `router/` at the project root and nowhere above it. `--router` or `GRIDROUTER_PATH` names another folder; a relative path is read against the project root, and a path that holds no router is an error. It prints the folder it loaded: check that it is the approved copy.
- After any change to the router or the glue, run the whole test suite, not part of it, and report any option with no test (WR-14).
- Say where the code came from (WR-13).

## Long runs

- Before a long run (routing, a refine pass, a full build, a set of simulations), set a time budget and say what it is.
- Keep to the cap on parallel processes the brief gives. With no cap given, run one process at a time: a long job must not load the user's machine.
- Print progress lines during the run, and put the timings in the report. An earlier router run deadlocked with no progress shown and the user found an empty board.
- A long job keeps a short progress file, `design/progress/BR-<sprint>-<n>.md` (template in `references/project-files.md`, progress files), rewritten after each step. The coordinator reads it without stopping the job, and an interrupted job is picked up from it.
- If a run seems stuck, use the script's trace switch to see where, stop at the budget, and report.
- macOS has no `timeout` command; use the script's own budget option.
- After any routing run, check the board is not empty and count unrouted nets before anything else.

## Repeatability

Two builds of the same input must give byte-identical files.

- Name-based IDs in the schematic generator, a seeded ID generator for the board, the netlist path and export time stripped, and fixed dates in order files make this possible.
- `build.py --twice` builds twice and compares every file in the KiCad folder (`hardware/`, or the folder `design/status.md` names) byte for byte (exit 4 on a difference). Run it when generated output changes, and before fabrication. Where a project's own `build.py` lacks it, build twice yourself and compare checksums.
- Every difference in `git diff` after a change is explained (WR-07). An unexpected difference is a finding: report it, do not commit over it.
- A simulation run gives the same files twice, and its result never depends on machine speed or the clock. When a run does not converge, follow the one fixed order of fallbacks the brief gives and report each step (`references/simulation.md`, Repeatable runs).
- Builds are made in place, with scratch files in `.hwtmp/` (`references/repository.md`, Layout). No build is made in a copy of the project.
- Repeatability has only been shown on one operating system at a time.

## Platforms

- The scripts were developed on macOS. On Windows and Linux, report anything that behaves differently.
- `pdftext.swift` and `pdfpage.swift` work on macOS only.
- The router needs a C compiler. If it fails to build (more likely on Windows), report it; do not work around it with a different tool without approval.
- `kicad_env.py` holds default paths for Windows and Linux. If `pcbnew` does not import from KiCad's Python there, report it.
- Files the user will publish should be readable on Windows (see `references/repository.md`, PB-02).
