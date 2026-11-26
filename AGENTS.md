# AGENTS.md

For people and AI agents working on this repository. It is not loaded by the skills, and it does not tell anyone how to design a board. The skills themselves are in `skills/`.

## Layout

| Path | What it is |
|---|---|
| `skills/hw-coordinator/` | The skill a user starts. `SKILL.md` plus `references/`. |
| `skills/hw-worker/` | The skill a worker follows for one unit of work. `SKILL.md`, `references/` and `scripts/`. |
| `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | Claude Code plugin manifest and marketplace. |
| `agents/hw-worker.md` | Claude Code plugin agent: a thin wrapper that loads the hw-worker skill. |
| `plugin.json` | Agent Plugins 1.0 manifest for tools that read that format. |
| `com.github.copilot/agents/hw-worker.agent.md` | Copilot agent wrapper. |
| `adapters/` | Copy-in wrapper files for tools whose plugins cannot ship agents. |
| `tests/run_tests.py` | The self-check. |

The text in `skills/` is the one canonical copy. Everything else is a thin wrapper that points to it. A wrapper holds frontmatter and one instruction, never a procedure.

## Tests

Run the self-check from the repository root with Python 3 and nothing else installed:

```sh
python3 tests/run_tests.py
```

It must pass before any change is offered for commit. It checks:

- skill frontmatter against the Agent Skills specification, and that each `name` matches its folder;
- each `SKILL.md` is under 500 lines;
- every relative file reference in the skills and the README resolves;
- the JSON manifests parse and agree on the plugin name;
- the wrapper files have the fields their tool needs;
- no model names, agent tool names or tool-specific paths in the canonical text in `skills/`;
- the writing rules below;
- the report summary block in the coordinator's brief reference matches the one in the worker skill (once both exist). In both `skills/hw-coordinator/references/briefs.md` and `skills/hw-worker/SKILL.md`, the "## Summary" heading sits outside the markers, and only the eight summary lines sit between `<!-- report-summary:start -->` and `<!-- report-summary:end -->`; change both copies together;
- the decision-log entry form in `skills/hw-coordinator/references/decision-log.md` matches the one in `skills/hw-worker/references/project-files.md`, between `<!-- decision-entry:start -->` and `<!-- decision-entry:end -->`; change both copies together;
- every script command the text names in a code span is a word that script knows;
- no shipped file holds a term from the owner's deny-list. The list is kept outside the repository. Give its path with `--deny-terms` or in `HW_SKILLS_DENY_TERMS`; with no list the check is skipped and says so;
- no shipped file points into the git-ignored working folder or into the separate test folder beside the repository;
- no KiCad test projects inside the repository;
- no personal paths or email addresses in shipped files.

Test projects, known-answer tests and trial boards live outside this repository, never inside it.

## Writing rules

These apply to every shipped file.

- Plain English. Short sentences.
- No em dashes.
- Say "functional requirements" and "quality characteristics". Never use the other common term for the second kind.
- A point where the engineer looks and decides is a "checkpoint". Never call it a gate. (The word is fine for logic gates and transistor gates.)
- State nothing as verified unless a check that can fail was run, with its command and output.
- No model names, agent tool names or tool-specific paths in `skills/`. Those belong in the wrappers. The canonical text says "start a worker on a cheaper model, if your tool can".
- No personal names, email addresses or machine paths in any shipped file. The one exception is the copyright holder's name, in `NOTICE`, the licence section of the README, and the `license` line of each `SKILL.md`. The licence lines at the top of each script name the company only: the scripts are copied into users' projects, and the confidentiality scan there flags a user name.

## Licence

Scripts (`skills/hw-worker/scripts/`, `tests/`) are under Apache 2.0 (`LICENSE`). All other files are under CC BY 4.0 (`LICENSE-CC-BY-4.0`). `NOTICE` holds the copyright line and the credit wording. A new script starts with the same two licence lines as the others. Do not edit the two licence texts.

## Git

Commit only when the owner asks. Do not push or add a remote without the owner.
