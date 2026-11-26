# Platforms: starting workers in each tool

Read this at the first session in a tool, and when starting a worker fails. Record the execution mode you found in `design/status.md`, on its `Execution mode:` line.

The routes below come from each tool's own documentation pages, read on 2026-11-23 (sources under the table). Tools change: treat each fact as true on that date only. Facts marked "not verified" were not found on a page. If a route does not work as written, tell the user and fall back to the next mode.

## Execution modes

1. **Sub-agents, and the worker's model can be set.** Start one worker per unit through the tool's sub-agent mechanism, using the hw-worker wrapper for this tool, so the wrapper's model applies.
2. **Sub-agents, but the worker's model cannot be set** (the wrapper sets none, the plan does not allow it, or the tool ignores it). Still delegate: it keeps your own context small. Tell the user once that workers run on the main model and cost more.
3. **No sub-agents** (a chat surface without them, or a mode that turns them off). Run the hw-worker procedure yourself, one unit at a time, in sequence. Write each unit's report to its file before starting the next. Afterwards read each report as `briefs.md` (Reading a report) says, not your earlier working. Tell the user at the start that this mode is slower and uses the main model for everything; they may switch to a less costly model by hand for long units.

To find the mode: check whether a worker agent named `hw-worker` (Codex: `hw_worker`) is available. If not, tell the user which wrapper file to copy where (table below), or carry on in mode 3 if they prefer.

## Model split

- A stronger model coordinates: it plans, thinks, asks, records and reports. Workers run on a capable model that costs less than the coordinator's, and do the long, detailed work: datasheets, schematic, board, checks, reviews, fabrication files. "Cheaper" always means cheaper than the coordinator's model, not the cheapest available.
- The reason: the coordinating model costs more, so it must not spend its tokens on detail.
- Each sprint plan says, for every unit, whether its worker runs on the same model as you or a cheaper one.
- It is a setting. The user's appetite for cost decides. Show it in the first-session table: read the model the wrapper for this tool sets, and show that, or "the same model as mine" if it sets none.
- The model name lives in each tool's worker wrapper, never in this skill. To change the worker's model, the user edits the wrapper for their tool.
- Blind reviewers use the same worker wrapper. Do not move a blind reviewer to a weaker model than the normal worker: its value is in reading thoroughly.

## Per tool

| Tool | Worker wrapper and where it goes | How to start a worker | Where the worker's model comes from | Notes |
|---|---|---|---|---|
| Claude Code (plugin) | Shipped in the plugin as agent `hw-skills:hw-worker`. Copied by hand: `.claude/agents/hw-worker.md`. | Start a sub-agent with the Agent tool, agent type `hw-skills:hw-worker` (or `hw-worker` if copied). Pass the whole brief as the prompt. | The `model` field of the wrapper. A per-call model override may win over it (not verified), so do not pass one unless the user asked. | Coordinator command: `/hw-skills:hw-coordinator`. If the worker cannot find the skill, give it the path `${CLAUDE_PLUGIN_ROOT}/skills/hw-worker/SKILL.md`. |
| Cursor | Copy the Cursor adapter to `.cursor/agents/hw-worker.md`. Skills in `.agents/skills/` or `.cursor/skills/`. | Delegate to the sub-agent by name, or the user types `/hw-worker`. | The `model` field of the wrapper. | On older request-based plans without Max Mode, sub-agents run on a default model whatever the wrapper says (mode 2). A direct sub-agent may start one more level; workers must not. Coordinator: `/hw-coordinator`. |
| Codex | Copy the Codex adapter to `.codex/agents/hw-worker.toml`; its agent name is `hw_worker`. Skills in `.agents/skills/`. | Ask for the `hw_worker` agent; Codex delegates when skill instructions ask it to. | The adapter sets no model, so the worker inherits your model (mode 2) unless the user adds one. | A community report says sub-agents with a pinned model sometimes fail to start (not verified). Coordinator: `$hw-coordinator` or `/skills`. |
| Copilot (VS Code, Copilot CLI) | The plugin's `com.github.copilot/agents/hw-worker.agent.md`, or a copy in `.github/agents/`. Skills in `.github/skills/` or `.agents/skills/`. | VS Code runs custom agents as sub-agents through its task tool (the older Local harness uses `runSubagent`). Copilot CLI: name the agent in the prompt, or `/agent`. | The wrapper sets no model, so the worker uses the current model (mode 2) unless the user adds one. | Repository instructions are not passed to custom sub-agents by default: the brief must hold everything. Coordinator: `/hw-coordinator`. |
| Antigravity | Copy the Antigravity adapter to `.agents/agents/hw-worker.md`. Skills in `.agents/skills/`. | `invoke_subagent` with `hw-worker`. | The `model` field of the wrapper, in Antigravity's own tier names. | Sub-agents run in the background and do not get your conversation: the brief must hold everything. Coordinator: `/hw-coordinator`. |
| Devin | Reads the same `.agents/agents/hw-worker.md` file. Skills in `.agents/skills/`. | Start the sub-agent by name (sub-agents are marked experimental). | An unset model means the administrator's default sub-agent model, not yours. Whether the Antigravity adapter's model value is accepted here is not verified. | No nesting unless `max-nesting` is set. Coordinator: `/hw-coordinator`. |
| Any other tool that reads SKILL.md folders | None | If it has no sub-agents: mode 3. | Your model. | |

Sources, all read on 2026-11-23:

- Claude Code: https://code.claude.com/docs/en/skills.md and https://code.claude.com/docs/en/plugins-reference.md (plugin agents; the plugin root variable is substituted when an agent or skill body loads).
- Cursor: https://cursor.com/docs/skills and https://cursor.com/docs/subagents (folders, the `model` field, the older plans without Max Mode, one extra level of nesting).
- Codex: https://developers.openai.com/codex/skills and https://developers.openai.com/codex/subagents (folders, TOML agents, model precedence: the file, then the spawn value, then the default, then the parent's model). The pinned-model failure is a community report seen only in a search result.
- Copilot: https://code.visualstudio.com/docs/agents/run/subagents (page dated 2026-11-18; task tool and the older Local harness) and https://docs.github.com/en/copilot/concepts/agents/copilot-cli/about-custom-agents (repository instructions not passed to custom sub-agents). Which Copilot surfaces honour a wrapper's `model` is not verified.
- Antigravity: https://antigravity.google/docs/subagents.md (folders, `invoke_subagent`, tier names, background runs without the parent's conversation).
- Devin: https://docs.devin.ai/cli/subagents.md (marked experimental; unset model means the administrator's default; nesting only with `max-nesting`).

## Rules in every mode

- **Workers never start sub-agents.** Several tools forbid or limit nesting. Every brief says so.
- **Pass everything in the brief.** Several tools give the worker none of your conversation.
- **Paths: relative in the file, absolute in the start message.** The brief file names paths relative to the project root, so it never holds a machine path and passes the confidentiality scan. The message that starts the worker gives the project root and where the hw-worker skill is installed (for example the plugin root path in Claude Code); those two lines are never written into the brief file.
- **Results come back as files** in the fixed report format, so you read them the same way whoever wrote them.
- **Keep parallel workers few, and say how many.** Each worker spends tokens on its own, so parallel runs multiply cost. Default: at most three at once, for independent units only (for example the three perspective passes of one part, or two blocks that share nothing). State the number in the sprint plan; the user can change it. Schematic build work is serial: one build worker at a time. A read-only unit may run beside a build.
- **Parallel workers never append to a shared file.** Each writes its own rows file, `design/passes/BR-<sprint>-<n>_<table>.csv`, in its own scratch folder under `.hwtmp/` for anything throw-away, and one writer named in the briefs merges the rows. Each worker reports any file that changed under it.
- **Workers do not talk to the user.** A worker that needs data stops and lists it under "Data needed from the user"; you ask.

## When something fails

| What happened | What to do |
|---|---|
| A worker cannot be started | Tell the user, with the reason if known. Run that unit in mode 3, or ask the user to install the wrapper. Record the mode in `design/status.md`. |
| A worker says it cannot load the hw-worker skill | Re-send the brief with the path to `skills/hw-worker/SKILL.md` in this installation. |
| A report is missing, or has no summary block | Ask the worker, or a fresh one, to write the report from its files. Never reconstruct a report from memory. |
| Workers run on the main model | Say so once, as a cost note, and carry on in mode 2. |
| A worker cannot read PDF pages or render figures | Figure and graph rows stay open. Tell the user and offer the PDF routes: the tool's own PDF reading and page viewing; the skill's macOS scripts (macOS only); or an install, with approval and a pinned version. |
| A worker stopped or was interrupted | Read its progress file, `design/progress/BR-<sprint>-<n>.md`, and check the files it names. Start a fresh worker from the restart block (`reporting.md`, Pause, end of day, interruption and restart). Never rebuild its work from memory. |
| Your context is getting long | Write the step in progress, the briefs out and the next step to `design/status.md`, then continue from the start-of-session routine. |
