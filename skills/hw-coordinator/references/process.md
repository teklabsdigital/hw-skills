# The process, for the user

The greeting, the five steps the user sees, and what to say when the user asks about a step. The thirteen stages in `stages.md` are your own map. The user sees only these five steps.

## Contents

The greeting; Existing project; The five steps; Explain a step; Where are we.

## The greeting

Give it once, as the first reply, when there is no `design/status.md` and the user did not ask a single question about a part or a circuit. Use this text. Do not add to it.

> I help you design a circuit board in KiCad, or add a feature to one you already have. You say what you want. I make the changes and show you the result. You decide at each checkpoint.
>
> The process:
> 1. **Requirements**: what the board must do and where it is used.
> 2. **Parts**: choose them and read their datasheets.
> 3. **Schematic**: drawn module by module, simulated, then reviewed.
> 4. **Board**: rules, placement, your 3D sign-off, routing, review.
> 5. **Fabrication files**: ready for a board maker.
>
> Expect questions and plots to read along the way. Say "explain 3" for more on any step, or "where are we" at any time.
>
> To start: what are you building, or what do you want to change? A few sentences is enough: what it does, how it is powered, what it connects to, who uses it, and whether it will be sold.

If the user's first message already says what they are building, give the greeting without its last paragraph and go straight to the first-session table (`questions.md`, First session). The greeting and the table are then one reply.

## Existing project

When the folder holds a KiCad project, replace the last paragraph of the greeting with:

> I see a KiCad project here. I will take stock of it first and change nothing: an inventory, the checks, and a ranked list of what I find. Then a new feature goes through the same steps, only for the parts it touches.
>
> What do you want to add or change?

## The five steps

| Step | Stages | Ends when |
|---|---|---|
| 1 Requirements | ST0, ST1, ST2 | the user has read the requirements and the direction is chosen |
| 2 Parts | ST3 | each part has its datasheet rows and its pin table |
| 3 Schematic | ST4, ST5, ST6 | the schematic checkpoint |
| 4 Board | ST7 to ST11 | the board checkpoint |
| 5 Fabrication files | ST12 | the order files are made and checked |

Publishing the repository (ST13) is optional and is not a step. Steps overlap: parts are chosen while requirements settle, and a change can send one module back a step. Say so when it happens.

## Explain a step

When the user asks about a step ("explain 3", "what happens in the board step"), answer in at most ten lines, in this order: what happens, what you will ask them, what they get, what to watch for. Use the entry below, then add where this project stands in that step. For a change to an existing board, say that the step covers only the modules the change touches, and that the checks still run on the whole design.

Answer a question about one thing inside a step (a check, a file, a word) directly and briefly. Do not recite the step.

**1 Requirements.**
- What happens: the project is set up. A worker drafts the requirements from your words: functional requirements, quality characteristics, where the board is used, and what a user could do wrong. Open questions on the approach are researched.
- You are asked: one batch of questions, each with a proposed answer.
- You get: a short requirements file to read. It is a read, not a lock.
- Watch for: anything written there that you did not say. It is marked "proposed, to confirm" until you answer.

**2 Parts.**
- What happens: candidate parts are compared with price and stock. The datasheet of each chosen part is read, and every instruction in it becomes a row the design is checked against.
- You are asked: to choose between candidates, and to approve any part that raises cost.
- You get: a parts table with sources, and the datasheet rows.
- Watch for: parts near the end of their life, and figures marked "from memory, not verified".

**3 Schematic.**
- What happens: the design is split into modules. Each module is drawn by a script, checked, and simulated. A second worker reviews it.
- You are asked: to agree the module split, to read the plot of each sheet, and to decide each finding.
- You get: the schematic as a PDF, the check and simulation results, and a list of what the firmware must do.
- Watch for: the plots. Read every one. Most corrections are made here, and they are cheapest here.

**4 Board.**
- What happens: the board rules are set from the board maker's limits. Parts are placed, you sign off the 3D view, the board is routed, and it is reviewed against each datasheet's layout instructions.
- You are asked: the board maker, the outline and enclosure, your placement habits, and the 3D sign-off before routing.
- You get: a routed board with KiCad's design-rule check run on every build.
- Watch for: connectors, buttons and lights in the 3D view. They are hard to move after routing.

**5 Fabrication files.**
- What happens: the order files, the parts list and the placement file are made, and checked against each other and against current stock.
- You are asked: whether to order, and any waiver.
- You get: files a board maker accepts, and a record of what was and was not verified.
- Watch for: the list of what is not verified. Only a built and tested board shows that a design works.

## Where are we

At the start of every session and in every close report, give one position line: the step, its number, and a count that means something. For example: "Step 3 of 5, schematic: 4 of 9 modules drawn and checked." When the user asks "where are we", give that line, what is waiting on them, and the next step.
