# hw-skills

Two AI skills for electronics circuit board design in KiCad.

**Status: work in progress, and being refined on each new board.** Feedback and improvements are welcome as pull requests.

## Install

Copy this prompt and paste it into a Claude Code session:

```text
Install the hw-skills plugin from https://github.com/teklabsdigital/hw-skills

Read the README at that link and follow its "Steps for the AI doing the install".
Tell me what you will install and ask me before you install anything.
When it is done, tell me the version you installed and how to start.
```

Claude does the rest, and asks you before it installs anything. Then start a new session and run `/hw-skills:hw-coordinator`.

For another tool, or to see what the AI will do, read "Install details" further down.

## What to expect

These skills do not design a board for you. They give an engineer who stays in charge:

- faster design work, with every value traced to a datasheet page;
- a schematic drawn by script, so every change shows in a diff;
- SPICE simulation of each module, run from the command line with the simulator that ships with KiCad;
- checks that can fail, run on every build;
- automated board placement and routing, with KiCad's design-rule check run on every build;
- fabrication and assembly files for a board maker.

Plan to read every plot and answer many questions. The checkpoints are where you look and decide.

## Where the skills come from

The skills come from two real projects and one grid router (https://github.com/teklabsdigital/hw-gridrouter; no tagged release yet, so pin an exact commit).

**The first board** is a Bluetooth OBD-II dongle for a vehicle's CAN bus (https://github.com/teklabsdigital/hw-obd2-dongle). It is a reasonably complex design: a 100 V buck converter, vehicle supply protection, a radio module and a CAN FD bus, with 84 parts on a 4-layer board of 50 x 36 mm. An AI drew the schematic, placed and routed the board, and wrote the fabrication and assembly files for JLCPCB, all by script, with an engineer directing. The design-rule check is clean. Its repository holds the scripts, the KiCad files, the fabrication files and a written evaluation of what the AI did well and poorly.

**The second board** is a power converter that is significantly more complex: far higher current and many more modules. It is being designed with the skills themselves. The schematic is in progress, and several modules have been simulated in SPICE.

| Stage | First board | Second, more complex board |
|---|---|---|
| Requirements, part choice, datasheet reading | Done | Done with the skills. Lessons in this release. |
| Logical design, schematic, schematic checks | Done | In progress with the skills. Lessons in this release. |
| SPICE simulation of modules | Not done | In progress with the skills. New in this release. |
| Board layout, routing, board checks | Done: routed by script, design-rule check clean | Next. Not started. |
| Fabrication and assembly files | Done: ready for JLCPCB | After the board. |
| Building the board, firmware, bench test | Not done | Planned. |

"Done" means the stage was worked through with an engineer and its checks pass. Neither board has been built yet. The aim is a complete set of skills proven on the complex project from requirements to bench test.

`LESSONS.md` lists the lessons and where each one lives in the skills.

## What the skills do

- **hw-coordinator** is the one skill you start. It opens with a five-step map of the process (requirements, parts, schematic, board, fabrication files), and explains any step when you ask. It asks what you are building, or what you want to add to a board you already have. It keeps the work tied to a numbered list of features, plans the work as sprints, and reports in plain English. It hands the detailed work to workers.
- **hw-worker** does one unit of work from a written brief: reading a datasheet, building or checking the schematic or the board, a review, or the fabrication files. It ends with a short report.

## How changes are made

You say what you want, and the AI makes the changes to the schematic and the board. Normally a worker edits a generator script and rebuilds, so every change shows up in a diff.

You can also edit in KiCad yourself, or bring an existing KiCad project.

The skills copy their scripts into a `hwskills/` folder of the project, and never write over a file the project already has. In a project that has its own generator scripts or build, the skills keep their hands off its files and run board checks on a copy.

## Install details

The prompt under "Install" at the top of this file is all a Claude Code user needs. This section holds the steps the AI follows, and the route for other tools.

### Steps for the AI doing the install

You are reading this because a user pasted the prompt above, or gave you the link to this repository and asked you to install it. Use the link the user gave you wherever a step says "the link".

1. Tell the user what will be installed: one plugin named `hw-skills`, holding two skills (`hw-coordinator`, `hw-worker`) and one worker sub-agent. It is installed for the user's account, not into the current project. Ask for a yes before you go on.
2. In Claude Code, run:

   ```sh
   claude plugin install hw-skills --marketplace [the link]
   ```

   This adds the repository as a plugin marketplace and installs the plugin from it. If that form is refused, run the two steps apart: `claude plugin marketplace add [the link]`, then `claude plugin install hw-skills@hw-skills`.
3. Check the result with `claude plugin list`. Report the plugin version it shows. If the install failed, show the user the error as printed. Do not try another route without asking.
4. Tell the user to start a new session, because a running session does not load a new plugin, and to begin with `/hw-skills:hw-coordinator`. The worker sub-agent is named `hw-skills:hw-worker`.
5. Install nothing else. KiCad, a compiler and the grid router are not part of this install. The coordinator checks for them at the start of a project and asks the user before each one.

In a tool other than Claude Code, use the table below: clone the repository at the link, copy the two folders in `skills/` into the tool's skills folder, and copy the worker wrapper for the tool into its agents folder. Ask the user first, and say which folders you will write to.

### Other tools

The skills follow the open Agent Skills format (a folder with a `SKILL.md` file). Each tool has its own way to load them and its own way to define the worker sub-agent.

Copy or link the two folders in `skills/` into the folder your tool reads skills from. Then copy the worker wrapper for your tool into its agents folder.

| Tool | Skills folder | Worker wrapper | Copy the wrapper to |
|---|---|---|---|
| Cursor | `.agents/skills/` or `.cursor/skills/` | `adapters/cursor/hw-worker.md` | `.cursor/agents/` |
| Codex | `.agents/skills/` | `adapters/codex/hw-worker.toml` | `.codex/agents/` |
| Antigravity, Devin | `.agents/skills/` | `adapters/antigravity/hw-worker.md` | `.agents/agents/` |
| Copilot (VS Code, Copilot CLI) | `.github/skills/` or `.agents/skills/` | `com.github.copilot/agents/hw-worker.agent.md` | `.github/agents/` |

These routes come from each tool's documentation.

A tool with no sub-agents can still use the skills: the coordinator then runs the worker procedure itself, one unit at a time. That is slower and uses the main model for everything.

## Licence and credit

Copyright 2026 Trevor Attema, Teklabs Digital.

You may use, change and share this work, also for paid work, as long as you give credit. It has two licences:

- **Scripts** (the files in `skills/hw-worker/scripts/` and `tests/`): Apache License 2.0, in the file `LICENSE`. Keep the `NOTICE` file with any copy you pass on.
- **Text** (everything else: the skill text, the reference files, the wrappers, this README and `LESSONS.md`): Creative Commons Attribution 4.0 International, in the file `LICENSE-CC-BY-4.0`.

To give credit, name "hw-skills by Trevor Attema, Teklabs Digital", link to this repository, name the licence, and say if you changed anything. The `NOTICE` file holds the exact wording.

## Feedback

The skills are work in progress. Feedback and improvements are welcome as pull requests.
