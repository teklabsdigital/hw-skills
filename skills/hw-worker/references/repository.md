# Repository

Procedures for the project layout and git (ST0), commits at any stage, and the optional publication step (ST13).

## Contents

Layout; Git and commits; Confidentiality scan; README; Licence; Publication; Release items (PB-).

## Layout

Set up at ST0, from day one, so nothing has to be moved later:

```
<project>/
  README.md  AGENTS.md (or the tool's own instructions file)  .gitignore  .gitattributes
  hwskills/    copies of the skill scripts, build.py among them, with the skills version recorded, so
               the project builds without the skills; the name is chosen so the copies never land on
               a project's own files
  scripts/     the project's generators (gen_sch.py, gen_pcb.py per board); they import the skill
               libraries from hwskills/
  scripts/checks/  checks that belong to this one project, apart from the copied skill scripts;
               the build runs them through the checks list in design/build.json
  hardware/    KiCad files, script-owned or hand-owned as recorded in design/ownership.csv;
               <manufacturer>/ for order files (an existing project keeps its own folder)
  datasheets/  <MPN>.pdf and its text extract; <MPN>_product-page.txt, the maker's page as read;
               README.md listing every file and its designators
  design/      project state files (references/project-files.md); calcs/ is the one
               calculations folder
  sim/         simulation: models/ for model files; <module>/ for each module's edge-case list,
               scenarios, generated circuit file and results (references/simulation.md)
  .hwtmp/      the one scratch folder, git-ignored: every throw-away and temporary file
  docs/        user documents and images
  firmware/    reserved; README only
```

- `.gitignore`, with patterns anchored to the project root where they name one place: `/.hwtmp/`; `design/.private-terms`; the agent tool's local settings files; KiCad's local state, `*.kicad_prl` (the editor's own view settings, rewritten whenever a file is opened), lock files `*.lck`, `_autosave-*`, `*-backups/` and `fp-info-cache`; generated rule-check reports (`ERC.json` among them), compiled files; `/router/` when the router is cloned there; and `datasheets/*.pdf` when the `Third-party PDFs committed:` line of `design/status.md` says no.
- `.gitattributes`: keep KiCad and generated files byte-exact on checkout (no line-ending conversion), and mark generated files as generated.
- **Scratch.** All scratch work goes in `.hwtmp/`, each brief in its own folder there. Never use a system or session temporary folder. Never do design work in a copy outside the project: scripts build in place, and they look for KiCad's lock files first and stop if the project is open. Nothing in a kept file points into `.hwtmp/`.
- **Simulation files.** Committed: `design/sim-models.csv`, `sim/models/`, and each module's `edge-cases.md`, `scenarios.csv` and generated `<module>.cir`, so a diff shows what changed in the circuit. `sim/<module>/results/` is committed too, unless it is large; then the report keeps the figures and the user chooses whether the folder is git-ignored. Makers' models are committed so the simulation runs on every machine the user works on. Each has licence terms, recorded in the model table: before the project is published, check each model's terms.
- **Third-party documents.** Ask once at setup whether saved datasheets and other third-party documents are committed, and record the answer in the `Third-party PDFs committed:` line. The ignore file and the scan follow it. A document that may not be committed (the answer is no, or the file is a standard's preview or carries a notice that forbids copying) is kept locally, git-ignored, and listed in `datasheets/README.md` as "not committed" with its source and revision, so it can be fetched again. Of a very large PDF in several languages, save the file, extract only the pages in the working language, and record which pages.
- Copy the skill scripts with `python3 <skill>/scripts/build.py --copy-skill-scripts <project root>`. It writes only into `hwskills/`, and stops with a list, copying nothing, when a file there has other bytes. The build is then `python3 hwskills/build.py`.
- For an existing project, keep its layout. Add `design/`, `datasheets/` and `hwskills/` beside it, and propose moves only if the user asks. The project's own `build.py`, `scripts/` and modules are never touched. The KiCad files stay where they are: `build.py --adopt` writes their folder into `design/status.md` as the line `KiCad folder: <folder>` (`.` for the project root), and every script reads them there (`references/adapting.md`, Adopting an existing project).
- Keep the datasheets and their text extracts; they are needed for analysis. Remove dead files (old scripts, superseded outputs) only with the user's agreement, and list them. Removing a module leaves stale files in several places: follow `references/project-files.md` (modules).

## Git and commits

- Create a local git repository at setup if there is none. Private; no remote unless the user asks.
- Commit only when the user asks, or as the commit setting in `design/status.md` says (default: offer a commit at sprint close; commit on "yes").
- **Backup commits.** The setting `backup commits` is asked at setup. When it is on, the worker commits the work before each schematic build without asking, and that commit is the backup: no copy of a file is kept instead. The message says "backup before <build>, BR-nn-nn". When it is off, nothing is committed without the user's yes, as above. A backup commit is never pushed.
- Before every commit run the confidentiality scan. Show its result only if it finds something. A backup commit is not made past a finding: stop and report.
- At a pause or the end of a day, the worker in hand brings its progress file up to date, `Next step` in `design/status.md` is written, and the work is committed as the commit settings allow. After an interrupted run, check before anything else: `git status` for files half written; the stopped job's progress file; rows files left in `design/passes/`; and that no KiCad lock file was left behind (ask the user; never remove one).
- Commit messages say what changed and which sprint, brief and IDs it serves.
- Never push, add a remote, or change any repository's visibility unless the user asks for that exact action. Never touch another repository.

## Confidentiality scan

`table_check.py scan` on the staged files (or a folder). It looks for:

- absolute machine paths, user and host names;
- email addresses;
- keys, tokens and passwords;
- supplier account details (account numbers, order numbers, addresses);
- every term in `design/.private-terms` (client names, code names).

The netlist's absolute path and export time are stripped by `build.py netlist`; the scan checks they stayed out. A finding is reported to the user, who decides. Never commit past a finding without the user's answer.

- Makers' documents in `datasheets/` print the makers' own contact addresses. The scan counts email addresses there apart, per file, and they do not fail. Every other kind of finding still fails there, and so does an address in `datasheets/README.md`, which the project writes.
- When the user accepts a finding, add a row to `design/scan-reviewed.csv` (`references/project-files.md`) with the reason and who decided. The scan then lists it as reviewed and does not fail on it. Never add a row without the user's answer.
- A scan that read no file fails. Before the first commit, stage the files or name the project folder.

## README

A clear README if the repository is made through the skills: what the board is, its state, how to build the files, the layout, and where the datasheets and design records are.

- Ask which images the user wants. Do not add layer images or views they did not ask for.
- What the README says about status (built, tested, not built) is the user's choice. Do not force a status banner. The coordinator's own reports stay plain about what is verified.
- Lead with the real-board result when there is one, rather than a benchmark figure.

## Licence

The project's licence is the user's choice. Ask; do not pick. Write the licence files they choose.

## Publication

Optional, only when the user asks.

1. Run the release items below. Check the licence terms of every model in `sim/models/` and of every third-party document that is committed; one that does not allow publishing is a numbered decision for the user.
2. Offer a fresh-context cold read: a worker with no history clones the repository, builds it, and compares the output with the committed files. On an earlier board this found a project file with no generator, loosened rule severities, stale text, a home path in the netlist, and builds that were not byte-repeatable.
3. Set the repository name, description and tags the user approves.

## Release items (PB-)

The PB- items are in `references/checklist-repository.md`. Setup copies them to `design/checklists/repository.md`, where `table_check.py checklists` counts them.
