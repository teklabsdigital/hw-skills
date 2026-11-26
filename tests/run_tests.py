#!/usr/bin/env python3
# Copyright 2026 Teklabs Digital (hw-skills)
# SPDX-License-Identifier: Apache-2.0
"""Self-check and script tests for the hw-skills repository.

Run from anywhere with Python 3 and nothing else installed:

    python3 tests/run_tests.py              check this repository, then test the scripts
    python3 tests/run_tests.py --root DIR   check a copy of it (used to test the checks)
    python3 tests/run_tests.py --self-only  only the self-check of the text and packaging

Each check prints PASS, FAIL or SKIP. The exit code is 1 if any check fails.
The script tests use tiny fixtures written by tests/fixtures.py into a temporary folder.
Tests that run KiCad's command line are skipped, with the reason, when it is not found;
the Swift tests are skipped away from macOS.
"""

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

SK = "hwskills"   # the project folder that holds the skill's scripts (fixtures.SKILL_DIR)

sys.dont_write_bytecode = True      # no __pycache__ inside the repository

# Strings that must not appear in shipped files are built in pieces, so this
# file does not trip its own scans.
WORKING_DIR = "_" + "working"
TEST_DIR = "hw-skills" + "-test"
EM_DASH = chr(0x2014)

SKILLS = ("hw-coordinator", "hw-worker")
SPEC_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
MAX_SKILL_LINES = 500

TEXT_EXT = {".md", ".json", ".toml", ".py", ".txt", ".yml", ".yaml", ".csv", ".swift"}
TEXT_NAMES = {".gitignore", ".gitattributes"}
SKIP_DIRS = {".git", WORKING_DIR, "__pycache__"}
SKIP_FILES = {".DS_Store"}

KICAD_EXT = {".kicad_pro", ".kicad_sch", ".kicad_pcb", ".kicad_prl", ".kicad_dru", ".kicad_mod", ".kicad_sym"}
TEST_PROJECT_DIRS = {"hand", "known-answer", "trial", "results"}

# Canonical text in skills/ names no model, no agent tool and no tool-specific
# path. Those belong in the wrappers.
MODEL_RE = re.compile(
    r"\b(opus|sonnet|haiku|fable|gpt-?\d[\w.-]*|gemini[\w.-]*|composer-\d[\w.-]*|"
    r"claude-[a-z]+-\d[\w.-]*|llama[\w.-]*|mistral[\w.-]*|codestral)\b",
    re.IGNORECASE,
)
AGENT_TOOL_RE = re.compile(
    r"\b(runSubagent|invoke_subagent|spawn_agent|activate_skill)\b|"
    r"\b(Task|Agent|Skill) tool\b"
)
TOOL_PATH_RE = re.compile(
    r"(?<![\w.])\.(claude|cursor|codex|github|gemini|agents|devin|windsurf|opencode)/|"
    r"\$\{?CLAUDE_[A-Z_]+\}?|\.claude-plugin\b"
)
# The coordinator's platform reference describes each tool's mechanics, so it
# may name agent tools and tool paths. It still names no model.
PLATFORM_REF = "skills/hw-coordinator/references/platforms.md"

# Writing rules, applied to every shipped text file.
NFR_RE = re.compile(r"\bnon-?\s?functional\b|\bNFRs?\b", re.IGNORECASE)
PROCESS_GATE_RE = re.compile(
    r"\b(quality|approval|review|stage|sprint|release|exit|entry|hard|soft|human|phase|"
    r"decision|sign-off|signoff|design|schematic|board|parts|go/no-go)[ -]gates?\b|"
    r"\bgates? ?(check|checks|review|reviews|approval|criteria|keeper|keeping)\b|"
    r"\bgatekeep\w*",
    re.IGNORECASE,
)

HOME_PATH_RE = re.compile(r"/" + r"Users/[^/\s]+|/" + r"home/[^/\s]+|[A-Za-z]:\\" + r"Users\\")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+\b")

SUMMARY_START = "<!-- report-summary:start -->"
SUMMARY_END = "<!-- report-summary:end -->"
DECISION_START = "<!-- decision-entry:start -->"
DECISION_END = "<!-- decision-entry:end -->"

AP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
# The one permitted outside link to a named organisation (the grid router), and where it may appear.
ROUTER_URL = "https://github.com/teklabsdigital/hw-gridrouter"
# The published board the skills were first drawn from: credited in the README only, never in skills/.
FIRST_BOARD_URL = "https://github.com/teklabsdigital/hw-obd2-dongle"
# This repository's own address: in the README's install prompt only.
OWN_URL = "https://github.com/teklabsdigital/hw-skills"
ALLOWED_URLS = {
    AP_SCHEMA: ("plugin.json", "tests/run_tests.py"),
    ROUTER_URL: ("README.md", "skills/hw-worker/references/tooling.md", "tests/run_tests.py"),
    FIRST_BOARD_URL: ("README.md", "tests/run_tests.py"),
    OWN_URL: ("README.md", "tests/run_tests.py"),
}
URL_RE = re.compile(r"https?://[^\s)\]>\"'`]+")
AP_FIELDS = {"$schema", "name", "version", "description", "author", "homepage", "repository",
             "license", "keywords", "extensions"}


# ---------------------------------------------------------------- helpers

def rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def shipped_files(root):
    """Every file in the repository except git internals and the ignored working folder."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name in SKIP_FILES:
                continue
            out.append(os.path.join(dirpath, name))
    return out


def is_text(path):
    name = os.path.basename(path)
    return name in TEXT_NAMES or os.path.splitext(name)[1] in TEXT_EXT


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def parse_frontmatter(text):
    """Parse the small YAML subset used in skill and agent frontmatter.

    Returns (fields, body, errors). Supports plain, quoted, folded (>) and
    literal (|) scalars, inline lists, block lists and one level of mapping.
    """
    errors = []
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return None, text, ["frontmatter must start with '---' on the first line"]
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].rstrip() == "---")
    except StopIteration:
        return None, text, ["frontmatter has no closing '---'"]
    fields = {}
    key = None
    i = 1
    while i < end:
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if line[0] in " \t":
            if key is None:
                errors.append("indented line before any key: %r" % line)
            else:
                item = line.strip()
                if item.startswith("- "):
                    if not isinstance(fields[key], list):
                        fields[key] = []
                    fields[key].append(unquote(item[2:].strip()))
                elif ":" in item:
                    if not isinstance(fields[key], dict):
                        fields[key] = {}
                    k, v = item.split(":", 1)
                    fields[key][k.strip()] = unquote(v.strip())
                else:
                    errors.append("cannot read line under %r: %r" % (key, line))
            i += 1
            continue
        if ":" not in line:
            errors.append("not a 'key: value' line: %r" % line)
            i += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in fields:
            errors.append("duplicate key %r" % key)
        if value in (">", ">-", "|", "|-"):
            block = []
            i += 1
            while i < end and (not lines[i].strip() or lines[i][0] in " \t"):
                block.append(lines[i].strip())
                i += 1
            joiner = " " if value.startswith(">") else "\n"
            fields[key] = joiner.join(b for b in block if b)
            continue
        if value.startswith("["):
            if not value.endswith("]"):
                errors.append("unclosed inline list for %r" % key)
            inner = value[1:-1].strip()
            fields[key] = [unquote(x.strip()) for x in inner.split(",")] if inner else []
        elif value == "":
            fields[key] = ""
        else:
            if value[0] not in "'\"" and (": " in value or " #" in value):
                errors.append("value of %r has ': ' or ' #' and must be quoted for YAML" % key)
            fields[key] = unquote(value)
        i += 1
    body = "\n".join(lines[end + 1:])
    return fields, body, errors


class Results:
    def __init__(self):
        self.passed = self.failed = self.skipped = 0

    def report(self, name, failures, skip_reason=None):
        if skip_reason:
            self.skipped += 1
            print("SKIP  %s: %s" % (name, skip_reason))
        elif failures:
            self.failed += 1
            print("FAIL  %s" % name)
            for f in failures:
                print("        - %s" % f)
        else:
            self.passed += 1
            print("PASS  %s" % name)


# ---------------------------------------------------------------- checks

def check_skill_frontmatter(root):
    failures = []
    skills_dir = os.path.join(root, "skills")
    found = sorted(d for d in os.listdir(skills_dir)
                   if os.path.isdir(os.path.join(skills_dir, d))) if os.path.isdir(skills_dir) else []
    if tuple(found) != SKILLS:
        failures.append("skills/ holds %s, expected %s" % (found, list(SKILLS)))
    for skill in found:
        path = os.path.join(skills_dir, skill, "SKILL.md")
        if not os.path.isfile(path):
            failures.append("skills/%s has no SKILL.md" % skill)
            continue
        fields, body, errors = parse_frontmatter(read(path))
        failures += ["skills/%s/SKILL.md: %s" % (skill, e) for e in errors]
        if fields is None:
            continue
        where = "skills/%s/SKILL.md" % skill
        extra = set(fields) - SPEC_FIELDS
        if extra:
            failures.append("%s: fields outside the Agent Skills spec: %s" % (where, sorted(extra)))
        name = fields.get("name", "")
        if not isinstance(name, str):
            failures.append("%s: name must be a string, got %r" % (where, name))
            name = ""
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) or len(name) > 64:
            failures.append("%s: name %r breaks the spec rules" % (where, name))
        if name != skill:
            failures.append("%s: name %r does not match folder %r" % (where, name, skill))
        desc = fields.get("description", "")
        if not isinstance(desc, str) or not desc.strip():
            failures.append("%s: description is missing or empty" % where)
        elif len(desc) > 1024:
            failures.append("%s: description is %d characters, limit 1024" % (where, len(desc)))
        elif "<" in desc or ">" in desc:
            failures.append("%s: description has angle brackets" % where)
        if "compatibility" in fields:
            c = fields["compatibility"]
            if not isinstance(c, str) or not 1 <= len(c) <= 500:
                failures.append("%s: compatibility must be 1 to 500 characters" % where)
        if "metadata" in fields:
            m = fields["metadata"]
            if not isinstance(m, dict) or not all(isinstance(v, str) for v in m.values()):
                failures.append("%s: metadata must map strings to strings" % where)
        if "allowed-tools" in fields and not isinstance(fields["allowed-tools"], str):
            failures.append("%s: allowed-tools must be a space-separated string" % where)
        if not body.strip():
            failures.append("%s: body is empty" % where)
    return failures


def check_line_counts(root):
    failures = []
    for skill in SKILLS:
        path = os.path.join(root, "skills", skill, "SKILL.md")
        if os.path.isfile(path):
            n = len(read(path).splitlines())
            if n >= MAX_SKILL_LINES:
                failures.append("skills/%s/SKILL.md has %d lines, limit is under %d"
                                % (skill, n, MAX_SKILL_LINES))
    return failures


LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
SKILL_PATH_RE = re.compile(r"`((?:references|scripts|assets)/[\w./-]+)`")
REPO_PATH_RE = re.compile(
    r"`((?:skills|agents|adapters|tests|com\.github\.copilot|\.claude-plugin)/[\w./-]*|plugin\.json)`")
PLUGIN_ROOT_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+)")


def check_references(root):
    failures = []
    # Inside each skill: paths are relative to the skill root (Agent Skills spec).
    for skill in SKILLS:
        skill_root = os.path.join(root, "skills", skill)
        if not os.path.isdir(skill_root):
            continue
        for dirpath, _, filenames in os.walk(skill_root):
            for name in filenames:
                if not name.endswith(".md"):
                    continue
                path = os.path.join(dirpath, name)
                text = read(path)
                targets = [t for t in LINK_RE.findall(text)
                           if not re.match(r"[a-z]+:|#", t)]
                targets += SKILL_PATH_RE.findall(text)
                for t in targets:
                    t = t.split("#")[0]
                    if t and not os.path.exists(os.path.join(skill_root, t)):
                        failures.append("%s: %s does not resolve from the skill root"
                                        % (rel(root, path), t))
    # Root documents and wrappers: repository paths.
    for name in ("README.md", "AGENTS.md", "LESSONS.md", "CLAUDE.md"):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        text = read(path)
        targets = [t for t in LINK_RE.findall(text) if not re.match(r"[a-z]+:|#", t)]
        targets += REPO_PATH_RE.findall(text)
        for t in targets:
            t = t.split("#")[0]
            if t and not os.path.exists(os.path.join(root, t)):
                failures.append("%s: %s does not exist" % (name, t))
        for imp in re.findall(r"^@(\S+)", text, re.MULTILINE):
            if not os.path.exists(os.path.join(root, imp)):
                failures.append("%s: import @%s does not exist" % (name, imp))
    for path in shipped_files(root):
        if is_text(path):
            for t in PLUGIN_ROOT_RE.findall(read(path)):
                if not os.path.exists(os.path.join(root, t)):
                    failures.append("%s: ${CLAUDE_PLUGIN_ROOT}/%s does not exist" % (rel(root, path), t))
    return failures


def load_json(root, relpath, failures):
    path = os.path.join(root, relpath)
    if not os.path.isfile(path):
        failures.append("%s is missing" % relpath)
        return None
    try:
        return json.loads(read(path))
    except ValueError as e:
        failures.append("%s does not parse: %s" % (relpath, e))
        return None


def check_manifests(root):
    failures = []
    plugin = load_json(root, ".claude-plugin/plugin.json", failures)
    market = load_json(root, ".claude-plugin/marketplace.json", failures)
    name = None
    if isinstance(plugin, dict):
        name = plugin.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
            failures.append(".claude-plugin/plugin.json: name %r is not kebab-case" % name)
        author = plugin.get("author")
        if not isinstance(author, dict) or not author.get("name"):
            failures.append(".claude-plugin/plugin.json: author.name is missing")
    if isinstance(market, dict):
        if not market.get("name"):
            failures.append("marketplace.json: name is missing")
        owner = market.get("owner")
        if not isinstance(owner, dict) or not owner.get("name"):
            failures.append("marketplace.json: owner.name is missing")
        entries = market.get("plugins")
        if not isinstance(entries, list) or not entries:
            failures.append("marketplace.json: plugins is empty")
        else:
            names = [e.get("name") for e in entries if isinstance(e, dict)]
            if name and name not in names:
                failures.append("marketplace.json: no entry for plugin %r" % name)
            for e in entries:
                src = e.get("source") if isinstance(e, dict) else None
                if isinstance(src, str):
                    if not (src == "." or src.startswith("./")) or ".." in src:
                        failures.append("marketplace.json: source %r must start with ./" % src)
                    elif not os.path.isdir(os.path.join(root, src)):
                        failures.append("marketplace.json: source %r is not a folder" % src)
    # Agent Plugins 1.0 manifest, shipped only if it does no harm (outline V02).
    if os.path.isfile(os.path.join(root, "plugin.json")):
        ap = load_json(root, "plugin.json", failures)
        if isinstance(ap, dict):
            if ap.get("$schema") != AP_SCHEMA:
                failures.append("plugin.json: $schema must be %s" % AP_SCHEMA)
            extra = set(ap) - AP_FIELDS
            if extra:
                failures.append("plugin.json: fields outside Agent Plugins 1.0: %s" % sorted(extra))
            apn = ap.get("name", "")
            # Pattern and length copied from the published Agent Plugins 1.0.0 schema.
            if (not isinstance(apn, str) or not 1 <= len(apn) <= 64
                    or not re.fullmatch(r"(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", apn)):
                failures.append("plugin.json: name %r breaks the Agent Plugins rules" % apn)
            for f in ("version", "description", "homepage", "repository", "license"):
                if f in ap and not isinstance(ap[f], str):
                    failures.append("plugin.json: %s must be a string" % f)
            kw = ap.get("keywords", [])
            if not isinstance(kw, list) or not all(isinstance(k, str) for k in kw):
                failures.append("plugin.json: keywords must be a list of strings")
            if name and apn != name:
                failures.append("plugin.json: name %r differs from the Claude Code name %r" % (apn, name))
            if isinstance(plugin, dict) and ap.get("version") != plugin.get("version"):
                failures.append("plugin.json: version differs from .claude-plugin/plugin.json")
    return failures


WRAPPERS = {
    # path: (required fields, allowed model check, fields that must not appear)
    "agents/hw-worker.md": (("name", "description", "model"),
                            lambda m: m == "opus" or m.startswith("claude-opus-"),
                            ("hooks", "mcpServers", "permissionMode")),
    "com.github.copilot/agents/hw-worker.agent.md": (("name", "description"), None, ()),
    "adapters/cursor/hw-worker.md": (("name", "description", "model"), None, ()),
    "adapters/antigravity/hw-worker.md": (("name", "description", "model"),
                                          lambda m: m in ("inherit", "flash", "pro"), ()),
}


def check_wrappers(root):
    failures = []
    for relpath, (required, model_ok, banned) in WRAPPERS.items():
        path = os.path.join(root, relpath)
        if not os.path.isfile(path):
            failures.append("%s is missing" % relpath)
            continue
        fields, body, errors = parse_frontmatter(read(path))
        failures += ["%s: %s" % (relpath, e) for e in errors]
        if fields is None:
            continue
        for f in required:
            if not fields.get(f):
                failures.append("%s: %s is missing" % (relpath, f))
        if fields.get("name") != "hw-worker":
            failures.append("%s: name must be hw-worker" % relpath)
        if model_ok and fields.get("model") and not model_ok(fields["model"]):
            failures.append("%s: model %r is not an accepted value here" % (relpath, fields["model"]))
        for f in banned:
            if f in fields:
                failures.append("%s: %s is ignored for plugin agents; remove it" % (relpath, f))
        failures += wrapper_body_failures(relpath, body)
        if relpath == "agents/hw-worker.md":
            # A worker must not start workers of its own: the Claude Code wrapper keeps Agent disallowed.
            dis = fields.get("disallowedTools", "")
            names = dis if isinstance(dis, list) else re.split(r"[,\s]+", dis or "")
            if "Agent" not in [n.strip() for n in names]:
                failures.append("%s: disallowedTools must include Agent" % relpath)
    relpath = "adapters/codex/hw-worker.toml"
    path = os.path.join(root, relpath)
    if not os.path.isfile(path):
        failures.append("%s is missing" % relpath)
    else:
        try:
            import tomllib
        except ImportError:
            tomllib = None
        if tomllib is None:
            text = read(path)
            for f in ("name", "description", "developer_instructions"):
                if not re.search(r"^%s\s*=" % f, text, re.MULTILINE):
                    failures.append("%s: %s is missing" % (relpath, f))
        else:
            try:
                with open(path, "rb") as fh:
                    data = tomllib.load(fh)
            except Exception as e:  # noqa: BLE001 - report any parse error
                failures.append("%s does not parse: %s" % (relpath, e))
                data = {}
            for f in ("name", "description", "developer_instructions"):
                if not isinstance(data.get(f), str) or not data.get(f).strip():
                    failures.append("%s: %s is missing" % (relpath, f))
            if data.get("developer_instructions"):
                failures += wrapper_body_failures(relpath, data["developer_instructions"])
    return failures


def wrapper_body_failures(relpath, body):
    lines = [l for l in body.splitlines() if l.strip()]
    out = []
    if not any("hw-worker" in l for l in lines):
        out.append("%s: body does not name the hw-worker skill" % relpath)
    if len(lines) > 3:
        out.append("%s: body has %d lines; a wrapper holds no procedure" % (relpath, len(lines)))
    return out


def check_canonical_text(root):
    failures = []
    skills_dir = os.path.join(root, "skills")
    for path in shipped_files(skills_dir) if os.path.isdir(skills_dir) else []:
        if not is_text(path):
            continue
        r = rel(root, path)
        for n, line in enumerate(read(path).splitlines(), 1):
            m = MODEL_RE.search(line)
            if m:
                failures.append("%s:%d: model name %r" % (r, n, m.group(0)))
            if r == PLATFORM_REF:
                continue
            m = AGENT_TOOL_RE.search(line)
            if m:
                failures.append("%s:%d: agent tool name %r" % (r, n, m.group(0)))
            m = TOOL_PATH_RE.search(line)
            if m:
                failures.append("%s:%d: tool-specific path %r" % (r, n, m.group(0)))
    return failures


def check_writing_rules(root):
    failures = []
    for path in shipped_files(root):
        if not is_text(path):
            continue
        r = rel(root, path)
        for n, line in enumerate(read(path).splitlines(), 1):
            if EM_DASH in line:
                failures.append("%s:%d: em dash" % (r, n))
            m = NFR_RE.search(line)
            if m:
                failures.append("%s:%d: %r; say quality characteristics" % (r, n, m.group(0)))
            m = PROCESS_GATE_RE.search(line)
            if m:
                failures.append("%s:%d: %r; say checkpoint" % (r, n, m.group(0)))
    return failures


def summary_block(path, start_mark=SUMMARY_START, end_mark=SUMMARY_END):
    text = read(path)
    if start_mark not in text:
        return None
    start = text.index(start_mark) + len(start_mark)
    end = text.find(end_mark, start)
    if end < 0:
        return ""
    return text[start:end].strip()


def check_decision_entry(root):
    """The decision-log entry form is kept in two files; the copies must match."""
    log = "skills/hw-coordinator/references/decision-log.md"
    files = "skills/hw-worker/references/project-files.md"
    blocks = {}
    failures = []
    for r in (log, files):
        path = os.path.join(root, r)
        b = summary_block(path, DECISION_START, DECISION_END) if os.path.isfile(path) else None
        if b is None:
            failures.append("%s has no %s block" % (r, DECISION_START))
        elif b == "":
            failures.append("%s: the decision-entry block has no %s marker" % (r, DECISION_END))
        blocks[r] = b
    if blocks.get(log) and blocks.get(files) and blocks[log] != blocks[files]:
        failures.append("the decision-entry forms in decision-log.md and project-files.md differ")
    return failures


def check_summary_block(root):
    briefs = os.path.join(root, "skills/hw-coordinator/references/briefs.md")
    worker = os.path.join(root, "skills/hw-worker/SKILL.md")
    have_briefs = os.path.isfile(briefs)
    b = summary_block(briefs) if have_briefs else None
    w = summary_block(worker) if os.path.isfile(worker) else None
    if not have_briefs and w is None:
        return [], "references/briefs.md and the worker report template are not written yet"
    failures = []
    if b is None:
        failures.append("skills/hw-coordinator/references/briefs.md has no %s block" % SUMMARY_START)
    if w is None:
        failures.append("skills/hw-worker/SKILL.md has no %s block" % SUMMARY_START)
    if b == "" or w == "":
        failures.append("a summary block has no %s marker" % SUMMARY_END)
    if b and w and b != w:
        failures.append("the summary blocks in briefs.md and hw-worker/SKILL.md differ")
    return failures, None


def check_no_pointers(root):
    failures = []
    working_re = re.compile(r"(?<![A-Za-z0-9])" + re.escape(WORKING_DIR) + r"\b")
    for path in shipped_files(root):
        if not is_text(path):
            continue
        r = rel(root, path)
        text = read(path)
        if r != ".gitignore" and working_re.search(text):
            failures.append("%s points into the git-ignored working folder" % r)
        if TEST_DIR in text:
            failures.append("%s points into the separate test folder" % r)
    return failures


def check_no_test_projects(root):
    failures = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for d in dirnames:
            if d in TEST_PROJECT_DIRS:
                failures.append("%s/ looks like a test project folder; those live outside the repository"
                                % rel(root, os.path.join(dirpath, d)))
        for name in filenames:
            if os.path.splitext(name)[1] in KICAD_EXT or name in ("fp-lib-table", "sym-lib-table"):
                failures.append("%s is a KiCad project file; test projects live outside the repository"
                                % rel(root, os.path.join(dirpath, name)))
    return failures


def check_personal_data(root):
    failures = []
    for path in shipped_files(root):
        if not is_text(path):
            continue
        r = rel(root, path)
        for n, line in enumerate(read(path).splitlines(), 1):
            m = HOME_PATH_RE.search(line)
            if m:
                failures.append("%s:%d: machine path %r" % (r, n, m.group(0)))
            m = EMAIL_RE.search(line)
            if m:
                failures.append("%s:%d: email address %r" % (r, n, m.group(0)))
    return failures


CODE_HOSTS_RE = re.compile(r"^https?://(www\.)?(github\.com|gitlab\.com|bitbucket\.org|codeberg\.org)/", re.I)


def check_urls(root):
    """Outside links: the schema, router and first-board URLs only where listed; platform documentation
    links only in the coordinator's platform reference; no other links, and no other code-hosting links."""
    failures = []
    for path in shipped_files(root):
        if not is_text(path):
            continue
        r = rel(root, path)
        for n, line in enumerate(read(path).splitlines(), 1):
            for url in URL_RE.findall(line):
                url = url.rstrip(".,;:")
                if url in ALLOWED_URLS:
                    if r not in ALLOWED_URLS[url]:
                        failures.append("%s:%d: %s may appear only in %s" % (r, n, url, ", ".join(ALLOWED_URLS[url])))
                elif CODE_HOSTS_RE.match(url):
                    failures.append("%s:%d: code-hosting link %s; only the router and first-board URLs are allowed" % (r, n, url))
                elif r != PLATFORM_REF:
                    failures.append("%s:%d: link %s is not on the allowed list" % (r, n, url))
    return failures


def check_versions(root):
    """The scripts' SKILLS_VERSION equals the plugin version, so status.md records one number."""
    failures = []
    common = os.path.join(root, "skills", "hw-worker", "scripts", "hwcommon.py")
    if not os.path.isfile(common):
        return ["skills/hw-worker/scripts/hwcommon.py is missing"]
    m = re.search(r'^SKILLS_VERSION = "([^"]+)"', read(common), re.MULTILINE)
    plugin = load_json(root, ".claude-plugin/plugin.json", failures)
    if not m:
        failures.append("hwcommon.py has no SKILLS_VERSION line")
    elif isinstance(plugin, dict) and plugin.get("version") != m.group(1):
        failures.append("hwcommon.py SKILLS_VERSION %s differs from the plugin version %s"
                        % (m.group(1), plugin.get("version")))
    return failures


COMMAND_SCRIPTS = ("sch_check", "table_check", "board_check", "spice", "build", "pcblib")
COMMAND_RE = re.compile(r"\b(%s)\.py ([a-z][a-z0-9_-]*)" % "|".join(COMMAND_SCRIPTS))
CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")


def check_commands_exist(root):
    """Every command of a script that the text names in a code span is a word the script knows."""
    failures = []
    scripts = os.path.join(root, "skills", "hw-worker", "scripts")
    source = {}
    for path in shipped_files(root):
        if os.path.splitext(path)[1] != ".md":
            continue
        r = rel(root, path)
        for n, line in enumerate(read(path).splitlines(), 1):
            for span in CODE_SPAN_RE.findall(line):
                for script, word in COMMAND_RE.findall(span):
                    if script not in source:
                        p = os.path.join(scripts, script + ".py")
                        source[script] = read(p) if os.path.isfile(p) else ""
                    if '"%s"' % word not in source[script]:
                        failures.append("%s:%d: %s.py has no command %r" % (r, n, script, word))
    return failures


def check_deny_terms(root, deny_path):
    """No shipped text file holds a term of the owner's deny-list, which is kept outside the repository.

    Returns (failures, skip_reason). One term per line; blank lines and lines that start with # are skipped."""
    if not deny_path:
        return [], "no deny-list given (--deny-terms or HW_SKILLS_DENY_TERMS)"
    if not os.path.isfile(deny_path):
        return ["the deny-list %s is not a file" % os.path.basename(deny_path)], None
    terms = [t.strip() for t in read(deny_path).splitlines()]
    terms = [t for t in terms if t and not t.startswith("#")]
    if not terms:
        return ["the deny-list holds no terms"], None
    pats = [(t, re.compile(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])", re.I)) for t in terms]
    failures = []
    for path in shipped_files(root):
        if not is_text(path):
            continue
        r = rel(root, path)
        for n, line in enumerate(read(path).splitlines(), 1):
            for t, pat in pats:
                if pat.search(line):
                    failures.append("%s:%d: deny-list term %d of the list" % (r, n, terms.index(t) + 1))
    return failures, None


# ---------------------------------------------------------------- script tests
# Each test returns a list of failures. A test that needs a missing tool raises Skip.

class Skip(Exception):
    pass


class Ctx:
    """What the script tests share: the module under test, the fixtures, the tools found."""

    def __init__(self, root):
        self.root = root
        self.scripts = os.path.join(root, "skills", "hw-worker", "scripts")
        for d in (self.scripts, os.path.join(root, "tests")):
            if d not in sys.path:
                sys.path.insert(0, d)
        import fixtures
        import hwcommon
        fixtures.SKILL_SCRIPTS = self.scripts
        self.fx, self.h = fixtures, hwcommon
        self.cli = None
        try:
            import kicad_env
            self.cli = kicad_env.find_kicad_cli()
        except ImportError:
            pass

    def module(self, name, alias=None):
        """Import a script by file, under an alias when its name could clash (build)."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(alias or name, os.path.join(self.scripts, name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def need_cli(self):
        if not self.cli:
            raise Skip("kicad-cli not found (set KICAD_CLI to run these tests)")


def run(cmd, cwd=None, env=None, timeout=900):
    """Run a command; (exit code, stdout and stderr together)."""
    e = dict(os.environ)
    e["PYTHONDONTWRITEBYTECODE"] = "1"
    for k, v in (env or {}).items():
        if v is None:
            e.pop(k, None)
        else:
            e[k] = v
    res = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=timeout)
    return res.returncode, res.stdout + res.stderr


@contextlib.contextmanager
def environ(**kw):
    old = dict((k, os.environ.get(k)) for k in kw)
    for k, v in kw.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def expect(failures, ok, message):
    if not ok:
        failures.append(message)
    return ok


def expect_run(failures, what, result, code, *texts):
    """Check a run's exit code and that its output holds each text; show the output on failure."""
    got, out = result
    bad = [t for t in texts if t not in out]
    if got != code or bad:
        tail = "\n".join("            | " + l for l in out.strip().splitlines()[-12:])
        failures.append("%s: exit %s (expected %s)%s\n%s" % (
            what, got, code, "; output lacks %r" % bad if bad else "", tail))
        return False
    return True


def fread(path, mode="r"):
    if "b" in mode:
        with open(path, "rb") as f:
            return f.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def fwrite(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def oxford(items):
    return ", ".join(items[:-1]) + " or " + items[-1]


# A small board in KiCad 10 form; NET1 and NET2 are the pad net tokens, so the older numbered form can be tried.
SMALL_BOARD = (
    '(kicad_pcb (version 20260206) (generator "pcbnew")\n'
    '  (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))\n'
    '  (setup (aux_axis_origin 100 120))\n'
    '  (footprint "lib:R_0603" (layer "B.Cu") (at 110 105 90)\n'
    '    (property "Reference" "R1" (at 0 0 0)) (property "Value" "10k" (at 0 0 0)) (property "MPN" "X-1")\n'
    '    (attr smd dnp)\n'
    '    (pad "1" smd rect (at -0.8 0) (size 0.9 0.95) (layers "B.Cu" "B.Mask") NET1)\n'
    '    (pad "2" smd rect (at 0.8 0) (size 0.9 0.95) (layers "B.Cu" "B.Mask") NET2))\n'
    '  (segment (start 0 0) (end 1 0) (width 0.2) (layer "B.Cu") (net "/A")))\n')

SMALL_NETLIST = (
    '(export (version "E") (design (source "x.kicad_sch") (date ""))\n'
    '  (components (comp (ref "R1") (value "10k") (footprint "lib:R")\n'
    '    (fields (field (name "MPN") "X-1") (field (name "Empty")))\n'
    '    (property (name "dnp")) (tstamps "abc")))\n'
    '  (nets (net (code "1") (name "/A") (node (ref "R1") (pin "1") (pintype "passive")))\n'
    '        (net (code "2") (name "/B") (node (ref "R1") (pin "2") (pinfunction "K") (pintype "passive")))))\n')


# ---- hwcommon.py

def test_hwcommon_sexpr(ctx):
    h, f = ctx.h, []
    t = h.parse_sexpr('(a "b c" (d 1) "e\\"f")')
    expect(f, t == ["a", "b c", ["d", "1"], 'e"f'], "parse_sexpr gave %r" % (t,))
    expect(f, isinstance(t[1], h.Q) and not isinstance(t[0], h.Q), "quoted atoms must come back as Q, plain as str")
    for bad in ("(a (b)", "(a))", "(a) (b)"):
        try:
            h.parse_sexpr(bad)
            f.append("parse_sexpr accepted the unbalanced %r" % bad)
        except ValueError:
            pass
    for form, n1, n2 in (("KiCad 10", '(net "/A")', '(net "/B")'), ("numbered", '(net 1 "/A")', '(net 2 "/B")')):
        b = h.board_summary(h.parse_sexpr(SMALL_BOARD.replace("NET1", n1).replace("NET2", n2)))
        fp = b["footprints"][0] if b["footprints"] else {}
        expect(f, b["copper_layers"] == ["F.Cu", "B.Cu"], "%s board: copper layers %r" % (form, b["copper_layers"]))
        expect(f, b["aux_origin"] == (100.0, 120.0), "%s board: aux origin %r" % (form, b["aux_origin"]))
        expect(f, (fp.get("ref"), fp.get("value"), fp.get("layer"), fp.get("x"), fp.get("y"), fp.get("rot"))
               == ("R1", "10k", "B.Cu", 110.0, 105.0, 90.0), "%s board: footprint read as %r" % (form, fp))
        expect(f, fp.get("attrs") == {"smd", "dnp"}, "%s board: attrs %r" % (form, fp.get("attrs")))
        expect(f, fp.get("fields", {}).get("MPN") == "X-1", "%s board: MPN field not read" % form)
        expect(f, [p["net"] for p in fp.get("pads", [])] == ["/A", "/B"], "%s board: pad nets not read" % form)
        expect(f, b["nets"] == ["/A", "/B"] and b["counts"]["segment"] == 1, "%s board: nets or counts wrong" % form)
    return f


def test_hwcommon_netlist(ctx):
    h, f = ctx.h, []
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "x.net")
        fwrite(p, SMALL_NETLIST)
        comps, nets = h.read_netlist(p)
    c = comps.get("R1", {})
    expect(f, c.get("value") == "10k" and c.get("footprint") == "lib:R", "component R1 read as %r" % c)
    expect(f, c.get("fields") == {"MPN": "X-1", "Empty": ""}, "fields read as %r" % c.get("fields"))
    expect(f, "dnp" in c.get("properties", {}) and c.get("uuid") == "abc", "dnp property or tstamps not read")
    expect(f, nets == {"/A": [("R1", "1", "", "passive")], "/B": [("R1", "2", "K", "passive")]},
           "nets read as %r" % nets)
    return f


def test_hwcommon_tables(ctx):
    h, fx, f = ctx.h, ctx.fx, []
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "parts.csv")
        fwrite(p, fx.PARTS_CSV)
        rows = h.read_table(p)
        expect(f, [r["refs"] for r in rows] == ["R1;R2", "R3", "J1"], "parts.csv rows read as %r" % rows)
        expect(f, h.split_list(rows[0]["refs"]) == ["R1", "R2"], "split_list did not split R1;R2")
        lines = fx.PARTS_CSV.splitlines()
        cols = lines[0].split(",")
        cols[0], cols[1] = cols[1], cols[0]
        for what, text in (("columns out of order", "\n".join([",".join(cols)] + lines[1:]) + "\n"),
                           ("a short row", lines[0] + "\nR9,1k\n"),
                           ("an empty file", "")):
            fwrite(p, text)
            try:
                h.read_table(p)
                f.append("read_table accepted %s" % what)
            except h.TableError:
                pass
        expect(f, h.read_table(os.path.join(tmp, "pins.csv")) == [], "a missing table must read as no rows")
        own = os.path.join(tmp, "ownership.csv")
        rows = [{"path": "hardware/a.kicad_sch", "owner": "script", "writer": "gen_sch.py (sch)", "hash": "ab",
                 "commit": ""}, {"path": "hardware/b.kicad_pcb", "owner": "hand", "writer": "", "hash": "",
                                 "commit": "c1"}]
        h.write_table(own, "ownership.csv", rows)
        back = [dict((k, v) for k, v in r.items() if k != "_line") for r in h.read_table(own)]
        expect(f, back == rows, "ownership.csv did not read back as written")
        expect(f, fread(own, "rb").startswith(b"path,owner,writer,hash,commit\n"), "ownership.csv header or line ends")
    return f


def test_hwcommon_lists_match_text(ctx):
    """The shared lists and table headers are the ones the shipped text gives (project-files.md)."""
    h, f = ctx.h, []
    path = os.path.join(ctx.root, "skills", "hw-worker", "references", "project-files.md")
    text = read(path)
    for name, cols in sorted(h.TABLES.items()):
        expect(f, ",".join(cols) in text, "%s: header in hwcommon.TABLES is not the one in project-files.md" % name)
    for what, items in (("compliance kind", h.KINDS), ("compliance category", h.COMPLIANCE_CATEGORIES),
                        ("section category", h.SECTION_CATEGORIES), ("schematic_result", h.SCHEMATIC_RESULTS),
                        ("board_result", h.BOARD_RESULTS), ("found_by", h.FOUND_BY), ("parts role", h.ROLES),
                        ("finding category", h.FINDING_CATEGORIES), ("perspective", h.PERSPECTIVES)):
        expect(f, ", ".join(items) in text, "%s list differs from project-files.md: %s" % (what, ", ".join(items)))
    expect(f, "category " + oxford(h.HARD_CATEGORIES) in text, "hard-row categories differ from project-files.md")
    expect(f, "A " + oxford(h.SECTIONS_NEEDING_ROWS) + " section with zero rows" in text,
           "sections needing rows differ from project-files.md")
    expect(f, set(h.HARD_CATEGORIES) <= set(h.COMPLIANCE_CATEGORIES), "a hard category is not a compliance category")
    expect(f, set(h.SECTIONS_NEEDING_ROWS) <= set(h.SECTION_CATEGORIES), "a section needing rows is not a category")
    expect(f, h.is_hard({"category": "grounding"}) and not h.is_hard({"category": "electrical"}), "is_hard wrong")
    return f


def test_hwcommon_decisions(ctx):
    h, f = ctx.h, []
    for value, closes in (("DC-001", True), ("DC-1234", True), ("proposed", False), ("", False),
                          ("DC-1", False), ("DC-001; DC-002", False)):
        expect(f, h.decision_closes(value) == closes, "decision_closes(%r) should be %s" % (value, closes))
    cases = {"dru:netclass Signal": ("dru", "netclass Signal", None), "dru:a-no-vias": ("dru", "a-no-vias", None),
             "check:single_point CN-004": ("check", "single_point", "CN-004"),
             "review:BRD-12": ("review", "BRD-12", None),
             "check:copper_area CN-001": None, "check:single_point": None, "check:unknown_check CN-001": None,
             "dru:": None, "review:": None, "": None, "netclass Signal": None}
    for text, want in cases.items():
        got = h.parse_enforcer(text)
        expect(f, got == want, "parse_enforcer(%r) gave %r, expected %r" % (text, got, want))
    with tempfile.TemporaryDirectory() as tmp:
        fwrite(os.path.join(tmp, "decisions.md"), ctx.fx.DECISIONS_MD)
        expect(f, h.decision_ids(tmp) == {"DC-001"}, "decision_ids read %r" % h.decision_ids(tmp))
        expect(f, h.check_waivers(["DC-001"], tmp) == [], "a recorded waiver was refused")
        expect(f, len(h.check_waivers(["DC-999", "waive-it"], tmp)) == 2, "unrecorded or malformed waivers accepted")
        for status, notes, errors in (
                (ctx.fx.STATUS_MD, [], 0),
                ('Expected DRC notes:\n  - "No pad found for pin 3" on Footprint J1, DC-001\nNext step: x\n',
                 [("No pad found for pin 3", "Footprint J1", "DC-001")], 0),
                ("Expected DRC notes: the J1 pins\n", [], 1),
                ('Expected DRC notes:\n  - "No pad" on Footprint J1\n', [], 1)):
            fwrite(os.path.join(tmp, "status.md"), status)
            got = h.expected_drc_notes(tmp)
            expect(f, got[0] == notes and len(got[1]) == errors,
                   "expected_drc_notes on %r gave %r" % (status.splitlines()[0:2], got))
    expect(f, sorted(["C10", "R1", "C2", "C1"], key=h.ref_key) == ["C1", "C2", "C10", "R1"], "ref_key order wrong")
    return f


# ---- kicad_env.py

def test_kicad_env(ctx):
    f = []
    k = ctx.module("kicad_env", "kicad_env_under_test")
    with tempfile.TemporaryDirectory() as tmp:
        missing = os.path.join(tmp, "no-such-cli")
        with environ(KICAD_CLI=sys.executable):
            expect(f, k.find_kicad_cli() == sys.executable and k.kicad_cli() == sys.executable,
                   "KICAD_CLI is not used first")
        with environ(KICAD_CLI=missing):
            expect(f, k.find_kicad_cli() is None, "find_kicad_cli should give None for a missing KICAD_CLI")
            try:
                k.kicad_cli()
                f.append("kicad_cli() went on with a missing KICAD_CLI")
            except SystemExit as e:
                expect(f, "KICAD_CLI is set to" in str(e), "the message does not name KICAD_CLI: %s" % e)
        with environ(KICAD_FOOTPRINT_DIR=None, KICAD10_FOOTPRINT_DIR=tmp):
            expect(f, k.footprint_dir() == tmp, "KiCad's own KICAD10_FOOTPRINT_DIR is not used")
        with environ(KICAD_FOOTPRINT_DIR=tmp, KICAD10_FOOTPRINT_DIR=missing):
            expect(f, k.footprint_dir() == tmp, "KICAD_FOOTPRINT_DIR must win over KICAD10_FOOTPRINT_DIR")
        with environ(KICAD_PYTHON=missing):
            expect(f, k.kicad_python() == missing, "KICAD_PYTHON is not used first")
        res = run([sys.executable, os.path.join(ctx.scripts, "kicad_env.py")], env={"KICAD_CLI": missing})
        expect(f, res[0] != 0 and "KICAD_CLI is set to" in res[1], "kicad_env.py with a missing KICAD_CLI: %r" % (res,))
    if ctx.cli:
        expect(f, k.cli_version(ctx.cli).startswith("Version:"), "cli_version gave %r" % k.cli_version(ctx.cli))
    return f


# ---- project_settings.py

def test_project_settings(ctx):
    f = []
    ps = ctx.module("project_settings", "project_settings_under_test")
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_project(os.path.join(tmp, "p"))
        design = os.path.join(proj, "design")
        pro = os.path.join(proj, "hardware", "x.kicad_pro")
        dru = os.path.join(proj, "hardware", "x.kicad_dru")
        notes = ps.write_project(pro, design)
        first = (fread(pro, "rb"), fread(dru, "rb"))
        expect(f, notes == [], "notes on the full fixture tables: %r" % notes)
        fwrite(pro, '{"board": {"design_settings": {"rules": {"min_clearance": 9}}}, "junk": 1}\n')
        fwrite(dru, "(version 1)\n(rule junk)\n")
        ps.write_project(pro, design)
        expect(f, (fread(pro, "rb"), fread(dru, "rb")) == first, "a junk project file changed the output")
        os.remove(pro)
        os.remove(dru)
        expect_run(f, "project_settings.py from no file",
                   run([sys.executable, os.path.join(proj, SK, "project_settings.py"), pro]), 0, "wrote x.kicad_pro")
        expect(f, (fread(pro, "rb"), fread(dru, "rb")) == first, "output from no file differs from the first write")
        d = json.loads(first[0].decode("utf-8"))
        expect(f, first[0].decode("utf-8") == json.dumps(d, indent=2, sort_keys=True) + "\n",
               "the project file is not in KiCad's saved form (keys sorted, two-space indent)")
        classes =dict((c["name"], c) for c in d["net_settings"]["classes"])
        sig = classes.get("Signal", {})
        expect(f, (sig.get("clearance"), sig.get("track_width")) == (0.2, 0.25), "net class Signal: %r" % sig)
        expect(f, (classes.get("Default", {}).get("clearance"), classes.get("Default", {}).get("track_width"))
               == (0.2, 0.2), "net class Default is not KiCad's default")
        expect(f, d["net_settings"]["netclass_patterns"] == [{"netclass": "Signal", "pattern": "/A"},
                                                            {"netclass": "Signal", "pattern": "/B"}],
               "net-class patterns: %r" % d["net_settings"]["netclass_patterns"])
        rules = d["board"]["design_settings"]["rules"]
        expect(f, rules.get("min_track_width") == 0.127 and rules.get("min_via_diameter") == 0.45,
               "board minimums not taken from fab-capabilities.csv")
        expect(f, d["schematic"]["top_level_sheets"][0]["filename"] == "x.kicad_sch", "root sheet name wrong")
        rtext = first[1].decode("utf-8")
        for want in ('(rule "netclass Signal width"', '(rule "netclass Signal clearance"', '(rule "a-no-vias"',
                     "(constraint via_count (max 0))", "A.NetName == '/A'", '(rule "fab: track width"',
                     "(constraint track_width (min 0.127mm))", "# CN-001, CN-002"):
            expect(f, want in rtext, "rule file lacks %r" % want)
        expect(f, "/B" not in rtext.split('(rule "a-no-vias"')[1], "rule a-no-vias names /B, which CN-003 does not")
        caps = os.path.join(design, "fab-capabilities.csv")
        fwrite(caps, "\n".join(l for l in ctx.fx.FAB_CSV.splitlines() if not l.startswith("min_track,")) + "\n")
        notes = ps.write_project(pro, design)
        expect(f, any("no min_track row" in n for n in notes), "a missing capability row gives no note: %r" % notes)
        cons = os.path.join(design, "constraints.csv")
        for row, msg in (("CN-005,user,single_point,/A,-,dru:bad-rule,whole,own figure,", "cannot be written as a rule"),
                         ("CN-006,user,max_length,/A,10,dru:netclass Signal,whole,own figure,", "cannot set a net class"),
                         ("CN-007,user,clearance,/A,wide,dru:a-rule,whole,own figure,", "is not a number")):
            fwrite(cons, ctx.fx.CONSTRAINTS_CSV + row + "\n")
            expect_run(f, "project_settings.py with %s" % row.split(",")[0],
                       run([sys.executable, os.path.join(proj, SK, "project_settings.py"), pro]), 2, msg)
    saved = dict(ps.SEVERITY_CHANGES)
    try:
        ps.SEVERITY_CHANGES["pin_not_connected"] = ("warning", "")
        try:
            ps.severities()
            f.append("a severity change with no DC- decision was accepted")
        except ps.SettingsError:
            pass
        ps.SEVERITY_CHANGES["pin_not_connected"] = ("warning", "DC-001")
        ps.SEVERITY_CHANGES["track_dangling"] = ("warning", "DC-001")
        erc, board = ps.severities()
        expect(f, erc["pin_not_connected"] == "warning" and board["track_dangling"] == "warning",
               "a recorded severity change was not applied")
    finally:
        ps.SEVERITY_CHANGES.clear()
        ps.SEVERITY_CHANGES.update(saved)
    return f


# ---- build.py, without KiCad (schematic generator stage only)

def build_run(proj, *args):
    return run([sys.executable, os.path.join(proj, SK, "build.py")] + list(args), cwd=proj)


def ownership(ctx, proj):
    return dict((r["path"], r) for r in ctx.h.read_table(os.path.join(proj, "design", "ownership.csv")))


SCH = "hardware/fixture.kicad_sch"


def test_build_ownership(ctx):
    f = []
    h = ctx.h
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_project(os.path.join(tmp, "p"))
        sch = os.path.join(proj, SCH)
        if not expect_run(f, "first build sch", build_run(proj, "sch"), 0, "done: sch"):
            return f
        own = ownership(ctx, proj)
        expect(f, len(own) == 8 and all(r["owner"] == "script" and r["writer"] == "gen_sch.py (sch)"
                                        for r in own.values()), "ownership.csv after the first build: %r" % own)
        expect(f, all(h.sha256_file(os.path.join(proj, p)) == r["hash"] for p, r in own.items()),
               "a recorded hash differs from the file")
        # An untouched file is written: change the generator's input and rebuild.
        parts = os.path.join(proj, "design", "parts.csv")
        fwrite(parts, fread(parts).replace("HDR-1X02,", "HDR-1X02-B,"))
        expect_run(f, "build sch after a parts.csv change", build_run(proj, "sch"), 0, "done: sch")
        expect(f, '"MPN" "HDR-1X02-B"' in fread(sch), "the untouched schematic was not written again")
        expect(f, ownership(ctx, proj)[SCH]["hash"] == h.sha256_file(sch), "the new hash was not recorded")
        # A hand edit: reported, not written, record unchanged.
        clean = fread(sch)
        edited = clean.replace('(property "Value" "10k"', '(property "Value" "22k"', 1)
        fwrite(sch, edited)
        record = fread(os.path.join(proj, "design", "ownership.csv"), "rb")
        expect_run(f, "build sch after a hand edit", build_run(proj, "sch"), 3, "NOT WRITTEN",
                   "symbol R1 field Value: '10k' -> '22k'", "Choices for the user")
        expect(f, fread(sch) == edited, "the hand-edited schematic was overwritten")
        expect(f, fread(os.path.join(proj, "design", "ownership.csv"), "rb") == record,
               "ownership.csv changed although nothing was written")
        expect_run(f, "--overwrite with an unrecorded decision",
                   build_run(proj, "sch", "--overwrite", SCH + "=DC-999"), 2, "not in design/decisions.md")
        expect(f, fread(sch) == edited, "a refused --overwrite still wrote the file")
        # Choice 1: keep the edit.
        expect_run(f, "--keep-hand", build_run(proj, "sch", "--keep-hand", SCH), 0, "recorded as hand-owned",
                   "sch skipped")
        expect(f, fread(sch) == edited and ownership(ctx, proj)[SCH]["owner"] == "hand", "keep-hand did not keep it")
        expect_run(f, "build sch with a hand-owned schematic", build_run(proj, "sch"), 0, "sch skipped")
        # Choice 3: overwrite under a recorded decision.
        expect_run(f, "--overwrite under DC-001", build_run(proj, "sch", "--overwrite", SCH + "=DC-001"), 0,
                   "written under DC-001")
        expect(f, fread(sch) == clean, "--overwrite did not write the generator's output")
        r = ownership(ctx, proj)[SCH]
        expect(f, r["owner"] == "script" and r["hash"] == h.sha256_file(sch), "--overwrite did not record the write")
        expect_run(f, "build sch --twice", build_run(proj, "sch", "--twice"), 0, "repeatable: ")
    return f


def test_build_restore(ctx):
    """A protected file the stage is not known to write is put back, and the build stops."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_project(os.path.join(tmp, "p"))
        if not expect_run(f, "first build sch", build_run(proj, "sch"), 0):
            return f
        sym = "hardware/fixture.kicad_sym"
        own = ownership(ctx, proj)
        del own[sym]
        ctx.h.write_table(os.path.join(proj, "design", "ownership.csv"), "ownership.csv",
                          [own[k] for k in sorted(own)])
        path = os.path.join(proj, sym)
        edited = fread(path) + "\n"
        fwrite(path, edited)
        expect_run(f, "build sch with an unrecorded, edited library", build_run(proj, "sch"), 3,
                   "no ownership record, so hand-owned", "put back")
        expect(f, fread(path) == edited, "the unrecorded file was not put back")
        expect(f, sym not in ownership(ctx, proj), "the put-back file was recorded as script-written")
    return f


def test_build_setup_errors(ctx):
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_project(os.path.join(tmp, "p"))
        expect_run(f, "unknown stage", build_run(proj, "route"), 2, "unknown stage route")
        expect_run(f, "malformed waiver", build_run(proj, "sch", "--waive", "yes"), 2, "not a decision ID")
        lock = os.path.join(proj, "hardware", "~fixture.kicad_sch.lck")
        fwrite(lock, "")
        expect_run(f, "lock file", build_run(proj, "sch"), 5, "KiCad lock file found")
        expect(f, not os.path.exists(os.path.join(proj, SCH)), "the build wrote files despite the lock file")
        expect_run(f, "--ignore-lock", build_run(proj, "sch", "--ignore-lock"), 0, "done: sch")
        shutil.rmtree(os.path.join(proj, "design"))
        expect_run(f, "no design/ folder", build_run(proj, "sch"), 2, "no design/ folder")
    return f


def test_build_units(ctx):
    f = []
    b = ctx.module("build", "build_under_test")
    pro_a = json.dumps({"a": {"b": 1}, "c": 1}).encode()
    pro_b = json.dumps({"a": {"b": 2}, "c": 1}).encode()
    expect(f, b.meaning_diff("x.kicad_pro", pro_a, pro_b) == ["project setting a.b changed"], "project diff wrong")
    pcb = SMALL_BOARD.replace("NET1", '(net "/A")').replace("NET2", '(net "/B")')
    moved = pcb.replace("(at 110 105 90)", "(at 111 105 90)").replace('(pad "2" smd rect (at 0.8 0) (size 0.9 0.95) '
                                                                       '(layers "B.Cu" "B.Mask") (net "/B")',
                                                                       '(pad "2" smd rect (at 0.8 0) (size 0.9 0.95) '
                                                                       '(layers "B.Cu" "B.Mask") (net "/C")')
    got = b.meaning_diff("x.kicad_pcb", pcb.encode(), moved.encode())
    for want in ("footprint R1 x: 110.0 -> 111.0", "footprint R1 pad nets changed"):
        expect(f, want in got, "board diff lacks %r: %r" % (want, got))
    resaved = pcb.replace("(at 110 105 90)", "(at  110  105  90)").encode()
    expect(f, b.meaning_diff("x.kicad_pcb", pcb.encode(), resaved) ==
           ["no change in meaning found by this summary (2 text lines differ; KiCad may have re-saved the file)"],
           "a byte-only board change is not reported as no change in meaning: %r"
           % b.meaning_diff("x.kicad_pcb", pcb.encode(), resaved))
    expect(f, b.meaning_diff("x.kicad_sch", None, b"x")[0].startswith("no version to compare"), "missing old version")
    expect(f, b.meaning_diff("x.txt", b"a\n", b"b\n") == ["2 text lines differ"], "plain text diff wrong")
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "x.net")
        fwrite(p, '(export (design (source "C:\\\\work\\\\x.kicad_sch") (date "Mon 1 Jan")) (source "/a/b/y.kicad_sch"))\n')
        b.sanitise_netlist(p)
        expect(f, fread(p) == '(export (design (source "x.kicad_sch") (date "")) (source "y.kicad_sch"))\n',
               "sanitise_netlist gave %r" % fread(p))
    return f


# ---- fab.py, without KiCad

def fab_fp(ref, value="10k", x=110.0, y=105.0, rot=0.0, layer="F.Cu", attrs=("smd",), fields=None, tht=False,
           lib="fixture:R_0603"):
    kind = "thru_hole" if tht else "smd"
    layers = ["*.Cu", "*.Mask"] if tht else ["F.Cu", "F.Mask", "F.Paste"]
    pads = [{"number": n, "type": kind, "shape": "rect", "x": 0.0, "y": dy, "w": 0.9, "h": 0.95, "layers": layers,
             "net": "", "drill": 1.0 if tht else 0.0} for n, dy in (("1", 0.0), ("2", 2.54 if tht else 1.6))]
    return {"ref": ref, "value": value, "lib_id": lib, "layer": layer, "x": x, "y": y, "rot": rot,
            "attrs": set(attrs), "fields": dict(fields or {}), "pads": pads}


def fab_board(changes=None, extra=()):
    """The fixture's four parts as board footprints; changes: ref -> dict of footprint keys to replace."""
    src = {"Manufacturer": "Maker A", "MPN": "RES-10K-0603", "Supplier": "SUPPLIER-A", "Supplier PN": "SA-1001"}
    fps = {"R1": fab_fp("R1", fields=src), "R2": fab_fp("R2", y=110.0, fields=src),
           "R3": fab_fp("R3", y=115.0, fields=src, attrs=("smd", "dnp")),
           "J1": fab_fp("J1", "Conn_2", 104.0, 106.73, attrs=("through_hole",), tht=True, lib="fixture:PinHeader_1x02",
                        fields={"Manufacturer": "Maker B", "MPN": "HDR-1X02", "Supplier": "SUPPLIER-B",
                                "Supplier PN": "SB-2002"})}
    for ref, ch in (changes or {}).items():
        if ch is None:
            del fps[ref]
        else:
            fps[ref].update(ch)
    return {"aux_origin": (100.0, 120.0), "copper_layers": ["F.Cu", "B.Cu"], "footprints": list(fps.values()) + list(extra)}


def test_fab_parts(ctx):
    f = []
    fab = ctx.module("fab", "fab_under_test")
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "parts.csv")
        fwrite(p, ctx.fx.PARTS_CSV)
        rows = ctx.h.read_table(p)
    logo = fab_fp("LOGO1", attrs=("board_only",))
    parts, problems, _ = fab.collect_parts(fab_board(extra=[logo]), rows, None)
    expect(f, problems == [], "clean board: %r" % problems)
    expect(f, [(q["ref"], q["fitted"]) for q in parts] == [("J1", True), ("R1", True), ("R2", True), ("R3", False)],
           "fitted state: %r" % [(q["ref"], q["fitted"], q["why"]) for q in parts])
    variant_rows = [dict(r, variant="V2") if r["refs"] == "R3" else r for r in rows]
    cases = [
        ("an MPN that differs", fab_board({"R1": {"fields": {"MPN": "OTHER"}}}), rows, "R1 MPN: board says 'OTHER'"),
        ("a part missing from the board", fab_board({"R2": None}), rows, "R2 is in parts.csv but not on the board"),
        ("a part missing from parts.csv", fab_board(extra=[fab_fp("R9")]), rows, "R9 is on the board but not in parts.csv"),
        ("not fitted but not DNP", fab_board({"R3": {"attrs": {"smd"}}}), rows, "R3: parts.csv says not fitted"),
        ("DNP but fitted", fab_board({"R1": {"attrs": {"smd", "dnp"}}}), rows, "R1: the board marks it do-not-populate"),
        ("a duplicate in parts.csv", fab_board(), rows + [dict(rows[2])], "J1 appears in more than one row"),
        ("a duplicate on the board", fab_board(extra=[fab_fp("R1")]), rows, "designator R1 is used by more than one"),
    ]
    for what, board, rws, want in cases:
        _, got, _ = fab.collect_parts(board, rws, None)
        expect(f, any(want in g for g in got), "%s: no problem %r in %r" % (what, want, got))
    vboard = fab_board({"R3": {"attrs": {"smd"}}})
    for variant, fitted in ((None, False), ("V2", True), ("v2", True), ("V3", False)):
        parts, got, _ = fab.collect_parts(vboard, variant_rows, variant)
        r3 = [q for q in parts if q["ref"] == "R3"][0]
        expect(f, got == [] and r3["fitted"] == fitted, "variant %r: R3 fitted %s, problems %r" % (variant, r3["fitted"], got))
    bottom = fab_fp("R1", x=110.0, y=105.0, rot=450.0, layer="B.Cu")
    expect(f, fab.position({"aux_origin": (100.0, 120.0)}, bottom) == (10.0, 15.0, 90.0),
           "position gave %r" % (fab.position({"aux_origin": (100.0, 120.0)}, bottom),))
    parts, _, _ = fab.collect_parts(fab_board({"R1": {"layer": "B.Cu"}}), rows, None)
    expect(f, parts[1]["side"] == "Bottom", "a B.Cu footprint is not on the bottom side")
    return f


def test_fab_files(ctx):
    f = []
    fab = ctx.module("fab", "fab_under_test")
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "parts.csv")
        fwrite(p, ctx.fx.PARTS_CSV)
        board = fab_board()
        parts, _, _ = fab.collect_parts(board, ctx.h.read_table(p), None)
        out = os.path.join(tmp, "out")
        texts = fab.neutral_files(board, parts)
        texts.update(fab.assembler_files(board, parts, "SUPPLIER-A"))
        texts.update(fab.hand_file(parts, {"J1"}))
        for name, text in texts.items():
            ctx.h.write_text(os.path.join(out, name), text)
        expect(f, fab.consistency(out, board, parts, "SUPPLIER-A") == [], "consistency on clean files: %r"
               % fab.consistency(out, board, parts, "SUPPLIER-A"))
        for name, line in (("bom.csv", "R1;R2,2,10k,R_0603,Maker A,RES-10K-0603,SUPPLIER-A,SA-1001"),
                           ("placement.csv", "R1,10k,R_0603,10.0000,15.0000,0,Top,SMD"),
                           ("placement.csv", "J1,Conn_2,PinHeader_1x02,4.0000,13.2700,0,Top,THT"),
                           ("not_fitted.csv", "R3,10k,R_0603,not fitted (parts.csv)"),
                           ("assembler_bom.csv", "10k,\"R1,R2\",R_0603,SA-1001,Maker A,RES-10K-0603"),
                           ("assembler_cpl.csv", "R2,10.0000mm,10.0000mm,Top,0"),
                           ("assembler_not_fitted.csv", "J1,Conn_2,PinHeader_1x02,Maker B,HDR-1X02,SUPPLIER-B,SB-2002,"
                                                        "through-hole")):
            expect(f, line in fread(os.path.join(out, name)).splitlines(), "%s lacks the line %r" % (name, line))
        hand = fread(os.path.join(out, "hand_assembly.csv")).splitlines()
        expect(f, [l.split(",")[1] for l in hand[1:]] == ["R1", "R2", "J1"], "hand-assembly order: %r" % hand)
        expect(f, "orientation" in hand[-1] and "solder after the SMD parts" in hand[-1], "J1 hand notes: %r" % hand[-1])
        # Seeded faults in the written files.
        for name, edit, want in (
                ("bom.csv", lambda t: t.replace("R1;R2", "R1"), "bom.csv differs from the fitted parts"),
                ("placement.csv", lambda t: t + "R3,10k,R_0603,10,5,0,Top,SMD\n", "a not-fitted part appears"),
                ("placement.csv", lambda t: t + "R1,10k,R_0603,10,15,0,Top,SMD\n", "placement.csv lists R1 more than once"),
                ("assembler_cpl.csv", lambda t: "\n".join(t.splitlines()[:-1]) + "\n", "assembler BOM and placement"),
                ("not_fitted.csv", lambda t: t + "R7,1k,R_0603,x\n", "designators not on the board: R7")):
            path = os.path.join(out, name)
            keep = fread(path)
            fwrite(path, edit(keep))
            got = fab.consistency(out, board, parts, "SUPPLIER-A")
            expect(f, any(want in g for g in got), "%s edited: no problem %r in %r" % (name, want, got))
            fwrite(path, keep)
        # DRC report reading and expected parity notes.
        report = {"violations": [{"type": "clearance", "severity": "error", "description": "Clearance violation"}],
                  "unconnected_items": [],
                  "schematic_parity": [
                      {"type": "net_conflict", "description": "No pad found for pin 3 in schematic",
                       "items": [{"description": "Footprint J1"}]},
                      {"type": "missing_footprint", "description": "Missing footprint",
                       "items": [{"description": "Symbol R9"}]}]}
        problems, found = fab.drc_problems(report, [("No pad found for pin 3", "Footprint J1", "DC-001")])
        expect(f, len(found) == 1 and [p["type"] for p in problems] == ["clearance", "missing_footprint"],
               "drc_problems gave %r, %r" % (problems, found))
        problems, found = fab.drc_problems(report, [])
        expect(f, len(problems) == 3 and not found, "with no expected notes every parity item is a problem")
        # Fixed dates in Gerber and drill files.
        g = os.path.join(tmp, "x.gbr")
        fwrite(g, "%TF.CreationDate,2026-11-23T16:52:15+01:00*%\nG04 Created by KiCad (PCBNEW 10.0) date "
                  "2026-11-23 16:52:15*\n; DRILL file {KiCad 10.0} date 2026-11-23T16:52:15+0100\n")
        fab.fix_stamps(g, "2026-01-02")
        expect(f, fread(g) == "%TF.CreationDate,2026-01-02T00:00:00+00:00*%\nG04 Created by KiCad (PCBNEW 10.0) date "
                              "2026-01-02 00:00:00*\n; DRILL file {KiCad 10.0} date 2026-01-02T00:00:00\n",
               "fix_stamps gave %r" % fread(g))
    return f


def test_fab_cli_errors(ctx):
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_project(os.path.join(tmp, "p"))
        board = os.path.join(proj, "hardware", "fixture.kicad_pcb")
        fwrite(board, "(kicad_pcb)\n")
        fab = [sys.executable, os.path.join(proj, SK, "fab.py")]
        expect_run(f, "fab.py on a missing board", run(fab + [board + "x"]), 2, "does not exist")
        expect_run(f, "fab.py with a bad date", run(fab + [board, "--date", "2026-1-2"]), 2, "--date must be")
        expect_run(f, "fab.py with an unrecorded waiver", run(fab + [board, "--waive", "DC-999"]), 2,
                   "not in design/decisions.md")
        fwrite(os.path.join(proj, "design", "status.md"), "Expected DRC notes: J1 pins\n")
        expect_run(f, "fab.py with an unreadable status.md", run(fab + [board]), 2, "expected DRC note")
        fwrite(os.path.join(proj, "design", "status.md"), ctx.fx.STATUS_MD)
        expect_run(f, "fab.py without kicad-cli", run(fab + [board], env={"KICAD_CLI": os.path.join(tmp, "none")}),
                   3, "kicad-cli not found")
        expect(f, not os.path.exists(os.path.join(proj, "hardware", "fab")), "fab.py wrote files after an error")
    return f


# ---- With KiCad's command line

def test_kicad_build_twice(ctx):
    ctx.need_cli()
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_project(os.path.join(tmp, "clean"))
        if not expect_run(f, "build.py --twice", build_run(proj, "--twice"), 0, "ERC: 0 violations",
                          "DRC (zones poured again, board not saved): 0 violations, 0 unconnected, 0 parity items",
                          "Consistency (FB-01): pass", "repeatable: "):
            return f
        out = os.path.join(proj, "hardware", "fab")
        want = {"fixture_gerbers.zip", "bom.csv", "placement.csv", "not_fitted.csv", "assembler_bom.csv",
                "assembler_cpl.csv", "assembler_not_fitted.csv", "hand_assembly.csv"}
        expect(f, set(os.listdir(out)) == want, "order folder holds %s" % sorted(os.listdir(out)))
        with zipfile.ZipFile(os.path.join(out, "fixture_gerbers.zip")) as z:
            names = z.namelist()
            expect(f, len(names) >= 10 and any(n.endswith(".drl") for n in names), "zip holds %r" % names)
            for info in z.infolist():
                expect(f, info.date_time[:3] == (2026, 1, 2), "%s dated %r in the zip" % (info.filename, info.date_time))
                dates = set(re.findall(r"20\d\d-\d\d-\d\d", z.read(info).decode("latin-1")))
                expect(f, dates <= {"2026-01-02"}, "%s holds the dates %s" % (info.filename, sorted(dates)))
        pcb = os.path.join(proj, "hardware", "fixture.kicad_pcb")
        pos = os.path.join(tmp, "pos.csv")
        res = run([ctx.cli, "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--use-drill-file-origin",
                   "--side", "both", "-o", pos, pcb])
        if expect(f, res[0] == 0, "kicad-cli pcb export pos failed: %s" % res[1][-300:]):
            import csv
            with open(pos, encoding="utf-8") as fh:
                kicad = dict((r["Ref"], r) for r in csv.DictReader(fh))
            with open(os.path.join(out, "placement.csv"), encoding="utf-8") as fh:
                ours = list(csv.DictReader(fh))
            expect(f, [r["Designator"] for r in ours] == ["J1", "R1", "R2"], "placement.csv parts: %r" % ours)
            for r in ours:
                k = kicad.get(r["Designator"], {})
                same = k and all(abs(float(r[a]) - float(k[b])) < 1e-3 for a, b in
                                 (("X (mm)", "PosX"), ("Y (mm)", "PosY"), ("Rotation", "Rot"))) \
                    and r["Side"].lower() == k["Side"]
                expect(f, same, "%s: placement.csv %r, KiCad's position file %r" % (r["Designator"], r, k))
        expect(f, "R3," in fread(os.path.join(out, "not_fitted.csv")), "R3 is not in not_fitted.csv")
        own = ownership(ctx, proj)
        expect(f, own.get("hardware/fixture.kicad_pcb", {}).get("writer") == "gen_pcb.py (board)",
               "the board is not recorded as written by the board stage")
        # A hand edit of the board, found through the generator run in a temporary copy.
        text = fread(pcb)
        fwrite(pcb, text.replace("(at 110 105)", "(at 111 105)", 1))
        expect_run(f, "build board after a hand edit of the board", build_run(proj, "board"), 3,
                   "footprint R1 x: 110.0 -> 111.0")
        expect(f, "(at 111 105)" in fread(pcb), "the hand-edited board was overwritten")
    return f


def test_kicad_fault_and_waiver(ctx):
    ctx.need_cli()
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_project(os.path.join(tmp, "fault"), fault="thin_track")
        out = os.path.join(proj, "hardware", "fab")
        expect_run(f, "build.py with a seeded thin track", build_run(proj), 1, "track_width", "Nothing written")
        expect(f, not os.path.exists(out), "files were written despite the violation")
        expect_run(f, "fab with an unrecorded waiver", build_run(proj, "fab", "--waive", "DC-999"), 2,
                   "not in design/decisions.md")
        expect_run(f, "fab with the recorded waiver", build_run(proj, "fab", "--waive", "DC-001"), 0,
                   "WAIVED by DC-001", "Consistency (FB-01): pass")
        expect(f, os.path.isfile(os.path.join(out, "fixture_gerbers.zip")), "no Gerber zip after the waiver")
    return f


# ---- PDF tools (macOS)

def test_swift_pdf_tools(ctx):
    if sys.platform != "darwin" or not shutil.which("swift"):
        raise Skip("the PDF scripts are macOS only and need swift")
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        pdf = ctx.fx.write_pdf(os.path.join(tmp, "in.pdf"))
        txt, png = os.path.join(tmp, "out.txt"), os.path.join(tmp, "out.png")
        res = run(["swift", os.path.join(ctx.scripts, "pdftext.swift"), pdf, txt], cwd=tmp)
        expect(f, res[0] == 0 and os.path.isfile(txt) and ctx.fx.PDF_TEXT in fread(txt) and
               "pages with no text layer (read them from the renders): none" in res[1],
               "pdftext.swift: %r" % (res,))
        blank = ctx.fx.write_pdf(os.path.join(tmp, "blank.pdf"), text="")
        res = run(["swift", os.path.join(ctx.scripts, "pdftext.swift"), blank, txt], cwd=tmp)
        expect(f, res[0] == 0 and "pages with no text layer (read them from the renders): 1" in res[1] and
               "page 1 (no text layer: read the page render)" in fread(txt),
               "pdftext.swift on a page with no text layer: %r" % (res,))
        res = run(["swift", os.path.join(ctx.scripts, "pdfpage.swift"), pdf, "1", png, "1"], cwd=tmp)
        expect(f, res[0] == 0 and os.path.isfile(png) and fread(png, "rb")[:8] == b"\x89PNG\r\n\x1a\n",
               "pdfpage.swift: %r" % (res,))
        res = run(["swift", os.path.join(ctx.scripts, "pdfpage.swift"), pdf, "2", png], cwd=tmp)
        expect(f, res[0] != 0 and "usage" in res[1], "pdfpage.swift on a missing page: %r" % (res,))
        # every page in one run, named <prefix>_p<page>.png; a second run leaves the files as they are
        prefix = os.path.join(tmp, "renders", "IN-1")
        os.makedirs(os.path.dirname(prefix))
        res = run(["swift", os.path.join(ctx.scripts, "pdfpage.swift"), pdf, "all", prefix, "1"], cwd=tmp)
        first = prefix + "_p1.png"
        expect(f, res[0] == 0 and os.path.isfile(first) and "pages 1; already there and left as they were: 0" in res[1],
               "pdfpage.swift all: %r" % (res,))
        fwrite(first, "kept")
        res = run(["swift", os.path.join(ctx.scripts, "pdfpage.swift"), pdf, "all", prefix, "1"], cwd=tmp)
        expect(f, res[0] == 0 and fread(first) == "kept" and "left as they were: 1" in res[1],
               "pdfpage.swift all overwrote a render already there: %r" % (res,))
    return f


SCRIPT_TESTS = [
    ("hwcommon: S-expressions and both board net forms", test_hwcommon_sexpr),
    ("hwcommon: netlist reader", test_hwcommon_netlist),
    ("hwcommon: project tables", test_hwcommon_tables),
    ("hwcommon: shared lists match project-files.md", test_hwcommon_lists_match_text),
    ("hwcommon: decisions, enforcers, waivers, expected DRC notes", test_hwcommon_decisions),
    ("kicad_env: lookup order and messages", test_kicad_env),
    ("project_settings: same bytes from tables, rules, refusals", test_project_settings),
    ("build: ownership step (sch stage)", test_build_ownership),
    ("build: a protected file written anyway is put back", test_build_restore),
    ("build: setup errors and the lock file", test_build_setup_errors),
    ("build: meaning diff and netlist clean-up", test_build_units),
    ("fab: parts against the board", test_fab_parts),
    ("fab: written files, read-back check, DRC notes, dates", test_fab_files),
    ("fab: refusals before any KiCad run", test_fab_cli_errors),
    ("KiCad: full build twice, order files, placement, board hand edit", test_kicad_build_twice),
    ("KiCad: seeded DRC violation, then a waiver", test_kicad_fault_and_waiver),
    ("macOS: PDF text and page tools", test_swift_pdf_tools),
]


# ======================================================================== HB-5 section (generator libraries)
# schlib.py, pcblib.py, build.py --adopt / --reproduce, and the hand-placed test project. The tests that
# need KiCad's Python (pcbnew) or the grid router skip, with the reason, when either is missing. The
# router is found through GRIDROUTER_PATH or a "router" folder beside this repository; the hand
# project through HW_SKILLS_TEST_HAND or the separate test folder beside this repository.

FAKE_DEVICE_SYM = (
    '(kicad_symbol_lib\n\t(version 20241209)\n\t(generator "test")\n'
    '\t(symbol "R"\n\t\t(exclude_from_sim no)\n'
    '\t\t(property "Reference" "R"\n\t\t\t(at 2.032 0 90)\n\t\t)\n'
    '\t\t(property "Value" "R"\n\t\t\t(at 0 0 90)\n\t\t)\n'
    '\t\t(property "Footprint" ""\n\t\t\t(at 0 0 0)\n\t\t)\n'
    '\t\t(property "Datasheet" "~"\n\t\t\t(at 0 0 0)\n\t\t)\n'
    '\t\t(symbol "R_1_1"\n'
    '\t\t\t(pin passive line\n\t\t\t\t(at 0 3.81 270)\n\t\t\t\t(length 1.27)\n\t\t\t\t(name "~")\n\t\t\t\t(number "1")\n\t\t\t)\n'
    '\t\t\t(pin passive line\n\t\t\t\t(at 0 -3.81 90)\n\t\t\t\t(length 1.27)\n\t\t\t\t(name "~")\n\t\t\t\t(number "2")\n\t\t\t)\n'
    '\t\t)\n\t)\n'
    '\t(symbol "R_Small"\n\t\t(extends "R")\n'
    '\t\t(property "Reference" "R"\n\t\t\t(at 1 0 90)\n\t\t)\n'
    '\t\t(property "Value" "R_Small"\n\t\t\t(at 0 0 90)\n\t\t)\n'
    '\t\t(property "Description" "small resistor"\n\t\t\t(at 0 0 0)\n\t\t)\n\t)\n)\n')


def test_schlib_units(ctx):
    """schlib without KiCad: a fake symbol library and footprint folder."""
    schlib = ctx.module("schlib")
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        symdir, fpdir = os.path.join(tmp, "sym"), os.path.join(tmp, "fp", "Resistor_SMD.pretty")
        os.makedirs(symdir)
        os.makedirs(fpdir)
        fwrite(os.path.join(symdir, "Device.kicad_sym"), FAKE_DEVICE_SYM)
        fwrite(os.path.join(fpdir, "R_0603_1608Metric.kicad_mod"), '(footprint "R_0603_1608Metric")\n')
        proj = os.path.join(tmp, "p")
        hw, design = os.path.join(proj, "hardware"), os.path.join(proj, "design")
        os.makedirs(hw)
        os.makedirs(design)
        header = ctx.fx.PARTS_CSV.splitlines()[0]
        row = "%s,%s,%s,0603,Maker A,MPN-%s,SUPPLIER-A,SA-%s,pull,,,1%%,50 V,0.01,0.005,1000,2026-01-02,active,,1,,,,,,,yes,yes,,no"
        fwrite(os.path.join(design, "parts.csv"), "\n".join([
            header, row % ("R1", "10k", "Resistor_SMD:R_0603_1608Metric", "10K", "1"),
            row % ("R2", "1k", "Resistor_SMD:R_0402_missing", "1K", "2")]) + "\n")
        fwrite(os.path.join(design, "decisions.md"), ctx.fx.DECISIONS_MD)
        sch_path = os.path.join(hw, "t.kicad_sch")

        def make():
            s = schlib.Schematic(sch_path, symbol_dir=symdir, footprint_dir=os.path.dirname(fpdir), date="2026-01-02")
            child = s.add_sheet("Child", "child.kicad_sch", at=(20, 10), size=(10, 4), pins=[("A", "input", "left", 2)])
            r1 = s.root.place("Device:R", "R", None, 10, 10)
            r2 = child.place("Device:R_Small", "R", None, 10, 10, rot=90)
            child.hier_label("A", 5, 10, "input")
            s.root.wire(r1["1"], (10, 5))
            return s, r1, r2, child
        s, r1, r2, child = make()
        expect(f, (r1["1"], r1["2"]) == ((10, 8.5), (10, 11.5)), "R1 pins at %r" % dict(r1))
        expect(f, (r2["1"], r2["2"]) == ((8.5, 10), (11.5, 10)), "R2 (rotated 90) pins at %r" % dict(r2))
        flat = s.symbol("Device:R_Small")
        expect(f, '"small resistor"' in flat and '(symbol "R_Small_1_1"' in flat and "(extends" not in flat,
               "R_Small not flattened from R")
        expect(f, child.path() == "/%s/%s" % (s.root_uuid, child.sheet_uuid), "child path %s" % child.path())
        expect(f, any("R2: footprint Resistor_SMD:R_0402_missing is in no KiCad or project library" in p
                      for p in s.check()), "missing footprint not reported: %r" % s.check())
        code, msgs = s.write()
        expect(f, code == 1 and not os.listdir(hw), "violation without a waiver: code %s, files %r" % (code, os.listdir(hw)))
        code, msgs = s.write(["DC-999"])
        expect(f, code == 2, "unrecorded waiver: code %s" % code)
        code, msgs = make()[0].write(["DC-001"])
        expect(f, code == 0 and any("WAIVED by DC-001" in m for m in msgs), "recorded waiver: %s %r" % (code, msgs))
        names = sorted(os.listdir(hw))
        expect(f, names == ["child.kicad_sch", "t.kicad_dru", "t.kicad_pro", "t.kicad_sch"], "written: %r" % names)
        if names:
            root_text, child_text = fread(sch_path), fread(os.path.join(hw, "child.kicad_sch"))
            expect(f, '(pin "A" input' in root_text and "(sheet_instances" in root_text, "root sheet lacks the sheet pin")
            expect(f, "(sheet_instances" not in child_text, "the child sheet has sheet_instances")
            expect(f, '(path "%s"' % child.path() in child_text, "child symbol not under the sheet's path")
            expect(f, '"MPN" "MPN-10K"' in root_text and '"Supplier PN" "SA-2"' in child_text,
                   "sourcing fields from parts.csv not written")
            first = dict((n, fread(os.path.join(hw, n), "rb")) for n in names)
            make()[0].write(["DC-001"])
            expect(f, all(fread(os.path.join(hw, n), "rb") == first[n] for n in names), "two writes differ")
        a, b = make()[0], make()[0]
        expect(f, a.uid("x") == b.uid("x") and a.uid("x") != a.uid("y"), "name-based IDs not repeatable")
        for what, call in (("value differing from parts.csv", lambda s: s.root.place("Device:R", "R", "22k", 1, 1)),
                           ("diagonal wire", lambda s: s.root.wire((0, 0), (1, 1))),
                           ("hierarchical label on the root", lambda s: s.root.hier_label("A", 1, 1))):
            try:
                call(schlib.Schematic(sch_path, symbol_dir=symdir, footprint_dir=os.path.dirname(fpdir)))
                f.append("%s: no SchematicError" % what)
            except schlib.SchematicError:
                pass
        s = schlib.Schematic(sch_path, symbol_dir=symdir, footprint_dir=os.path.dirname(fpdir))
        s.add_sheet("Child", "child.kicad_sch", pins=[("A", "input", "left", 2)])
        expect(f, any("pin A has no hierarchical label" in p for p in s.check()), "unlabelled sheet pin not reported")
    return f


def kicad_python(ctx):
    """KiCad's Python with pcbnew, or Skip."""
    try:
        import kicad_env
        path = kicad_env.kicad_python()
    except (ImportError, SystemExit):
        path = None
    if not path or not os.path.exists(path):
        raise Skip("KiCad's Python (with pcbnew) not found (set KICAD_PYTHON to run these tests)")
    return path


def router_path(ctx):
    """The grid router's folder, or Skip. Only read and imported, never written."""
    for c in (os.environ.get("GRIDROUTER_PATH"), os.path.join(os.path.dirname(ctx.root), "router")):
        if c and os.path.isfile(os.path.join(c, "gridrouter", "__init__.py")):
            return c
    raise Skip("grid router not found (set GRIDROUTER_PATH to a clone of it)")


PCBLIB_PROBE = r'''
import json, os, sys
sys.path.insert(0, sys.argv[1])
import pcblib, project_settings
out = {}
dru = os.path.join(sys.argv[2], "t.kicad_dru")
caps, ncs, rules, _ = project_settings.load_tables(sys.argv[3])
open(dru, "w").write(project_settings.rules_text(caps, ncs, rules))
d = pcblib.read_dru(dru)
out["no_via"] = sorted(d["no_via"])
out["min_clearance"] = d["min_clearance"]
out["rc"] = [pcblib._rc(x) for x in (0.35, 0.55, 0.5, 0.7, 0.75, 0.8)]
rep = {"violations": [{"type": "clearance", "items": []}], "unconnected_items": [],
       "schematic_parity": [{"description": "No pad found for pin 3", "items": [{"description": "Footprint J1"}]},
                            {"description": "Missing footprint", "items": [{"description": "Symbol R9"}]}]}
p, found = pcblib.drc_problems(rep, [("No pad found for pin", "Footprint J1", "DC-001")])
out["problems"] = [v.get("type", v.get("description")) for v in p]
out["found"] = len(found)
src = os.path.join(sys.argv[2], "src")
os.makedirs(os.path.join(src, "sub"))
for n in ("b.kicad_pcb", "~b.kicad_pcb.lck", "sub/s.kicad_sch"):
    open(os.path.join(src, n), "w").write("x")
os.makedirs(os.path.join(src, "b-backups"))
c = pcblib.copy_project(os.path.join(src, "b.kicad_pcb"), os.path.join(sys.argv[2], "dst"))
out["copied"] = sorted(os.path.relpath(os.path.join(dp, n), os.path.dirname(c)) for dp, _, ns in os.walk(os.path.dirname(c)) for n in ns)
errs = []
for dest in (os.path.join(src, "inside"), os.path.join(sys.argv[2], "dst")):
    try:
        pcblib.copy_project(os.path.join(src, "b.kicad_pcb"), dest)
    except pcblib.PcbError as e:
        errs.append(str(e)[:20])
out["copy_errors"] = len(errs)
out["owner_none"] = pcblib.board_owner(os.path.join(src, "b.kicad_pcb"))[0]
print("PROBE " + json.dumps(out, sort_keys=True))
'''


def test_pcblib_units(ctx):
    kpy = kicad_python(ctx)
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_lib_project(os.path.join(tmp, "p"))
        probe = os.path.join(tmp, "probe.py")
        fwrite(probe, PCBLIB_PROBE)
        res = run([kpy, probe, ctx.scripts, tmp, os.path.join(proj, "design")])
        m = re.search(r"^PROBE (.*)$", res[1], re.MULTILINE)
        if not expect(f, res[0] == 0 and m, "probe failed: %s" % res[1][-600:]):
            return f
        got = json.loads(m.group(1))
        expect(f, got["no_via"] == ["SENSE"], "no-via nets from the rule file: %r" % got["no_via"])
        expect(f, got["min_clearance"] == 0.127, "board minimum clearance from the rule file: %r" % got["min_clearance"])
        # the earlier board's radii: 0.2 mm track, 0.15 mm clearance, 0.5 mm wide track, 0.6 mm via
        expect(f, got["rc"] == [3, 5, 5, 7, 7, 8], "router radii %r (expected 3, 5, 5, 7, 7, 8)" % got["rc"])
        expect(f, got["problems"] == ["clearance", "Missing footprint"] and got["found"] == 1,
               "clean-report test: %r, %d expected notes" % (got["problems"], got["found"]))
        expect(f, got["copied"] == ["b.kicad_pcb", "sub/s.kicad_sch"], "project copy holds %r" % got["copied"])
        expect(f, got["copy_errors"] == 2, "copy into the project or a non-empty folder not refused")
        expect(f, got["owner_none"] == "hand", "a board with no ownership record is not hand-owned")
    return f


def lib_env(ctx):
    return {"GRIDROUTER_PATH": router_path(ctx)}


def test_kicad_lib_build(ctx):
    """The library fixture: two-sheet schematic (ERC), generated board routed with DRC clean, twice
    byte for byte, order files; then the ownership step and DRC on a real generated board."""
    ctx.need_cli()
    kpy = kicad_python(ctx)
    env = lib_env(ctx)
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_lib_project(os.path.join(tmp, "lib"))
        res = run([sys.executable, os.path.join(proj, SK, "build.py"), "--twice"], cwd=proj, env=env)
        if not expect_run(f, "library fixture build.py --twice", res, 0, "ERC: 0 violations",
                          "wrote libfix.kicad_sch: 2 sheets, 7 symbols",
                          "DRC in place, zones poured again and saved: 0 violations, 0 unconnected, 0 parity items",
                          "silk labels: 0.80 mm high, 7 of 7 placed", "Consistency (FB-01): pass", "repeatable: "):
            return f
        hw = os.path.join(proj, "hardware")
        comps, nets = ctx.h.read_netlist(os.path.join(hw, "libfix.net"))
        want = {"/Power/VIN": ["C1.1", "J1.1", "U1.3"], "SENSE": ["J1.2", "R2.2"],
                "+3V3": ["C2.1", "R1.1", "R2.1", "U1.2"], "GND": ["C1.2", "C2.2", "D1.1", "J1.3", "U1.1"]}
        for name, pins in want.items():
            got = ["%s.%s" % (n[0], n[1]) for n in nets.get(name, [])]
            expect(f, got == pins, "net %s joins %r (expected %r)" % (name, got, pins))
        expect(f, comps.get("U1", {}).get("fields", {}).get("MPN") == "REG-3V3-SOT223", "U1 MPN not from parts.csv")
        pcb = os.path.join(hw, "libfix.kicad_pcb")
        root = ctx.h.read_sexpr(pcb)
        segs = ctx.h.find(root, "segment")
        vias = ctx.h.find(root, "via")
        net_of = lambda n: ctx.h.value(n, "net")
        expect(f, len(segs) > 10, "the board has %d track pieces" % len(segs))
        expect(f, not [v for v in vias if net_of(v) == "SENSE"], "SENSE (no vias by the rule file) has a via")
        thin = [s for s in segs if net_of(s) in ("+3V3", "/Power/VIN") and float(ctx.h.value(s, "width")) < 0.4 - 1e-6]
        expect(f, not thin, "%d Power class track pieces under 0.4 mm" % len(thin))
        own = ownership(ctx, proj)
        expect(f, own.get("hardware/libfix.kicad_pcb", {}).get("writer") == "gen_pcb.py (board)" and
               own.get("hardware/power.kicad_sch", {}).get("writer") == "gen_sch.py (sch)",
               "ownership records: %r" % sorted((k, v["writer"]) for k, v in own.items()))
        # DRC through pcblib: in place on the script-owned board (re-pour gives the same bytes), then
        # on a copy once the board is hand-owned.
        before = fread(pcb, "rb")
        pcblib = os.path.join(proj, SK, "pcblib.py")
        expect_run(f, "pcblib drc, script-owned", run([kpy, pcblib, "drc", pcb], env=env), 0,
                   "DRC in place (script-owned, writer gen_pcb.py (board))", "DRC clean")
        expect(f, fread(pcb, "rb") == before, "re-pour in place changed the generated board's bytes")
        expect_run(f, "keep the board as hand-owned", run([sys.executable, os.path.join(proj, SK, "build.py"),
                                                           "--keep-hand", "hardware/libfix.kicad_pcb", "erc"],
                                                          cwd=proj, env=env), 0)
        keep = os.path.join(tmp, "drc-copy")
        expect_run(f, "pcblib drc, hand-owned", run([kpy, pcblib, "drc", pcb, "--copy", keep], env=env), 0,
                   "on a copy (libfix.kicad_pcb: recorded as hand-owned)", "DRC clean")
        expect(f, fread(pcb, "rb") == before and os.path.isfile(os.path.join(keep, "libfix.kicad_pcb")),
               "DRC on a copy: the board changed, or no copy was kept")
        # A hand edit of the generated board: the board stage refuses and leaves the bytes.
        proj2 = os.path.join(tmp, "lib2")
        shutil.copytree(proj, proj2)
        rows = ownership(ctx, proj2)
        rows["hardware/libfix.kicad_pcb"] = dict(rows["hardware/libfix.kicad_pcb"], owner="script",
                                                 hash=ctx.h.sha256_file(os.path.join(proj2, "hardware", "libfix.kicad_pcb")))
        ctx.h.write_table(os.path.join(proj2, "design", "ownership.csv"), "ownership.csv",
                          [dict((k, v) for k, v in r.items() if k != "_line") for _, r in sorted(rows.items())])
        pcb2 = os.path.join(proj2, "hardware", "libfix.kicad_pcb")
        text = fread(pcb2)
        m = re.search(r'\(footprint "Resistor_SMD:R_0603_1608Metric"\n\t\t\(layer "F.Cu"\)\n\t\t\(uuid "[^"]+"\)\n'
                      r'\t\t\(at ([-\d.]+) ([-\d.]+)', text)
        if expect(f, m, "R footprint position not found in the board text"):
            edited = text[:m.start(1)] + "%g" % (float(m.group(1)) + 1) + text[m.end(1):]
            fwrite(pcb2, edited)
            expect_run(f, "build board after a hand edit of the generated board",
                       run([sys.executable, os.path.join(proj2, SK, "build.py"), "board"], cwd=proj2, env=env), 3,
                       "NOT WRITTEN", "x: %s -> %s" % (float(m.group(1)), float(m.group(1)) + 1))
            expect(f, fread(pcb2) == edited, "the hand-edited generated board was overwritten")
        # Adopting it as an existing project, with its own schematic generator as the writer (item 7).
        proj3 = os.path.join(tmp, "lib3")
        shutil.copytree(proj, proj3)
        os.remove(os.path.join(proj3, "design", "ownership.csv"))
        cmd = '"%s" scripts/gen_sch.py hardware/libfix.kicad_sch' % sys.executable
        res = run([sys.executable, os.path.join(proj3, SK, "build.py"), "--adopt", "--reproduce", cmd], cwd=proj3)
        expect_run(f, "adopt with reproduction", res, 0, "done: adopt")
        rows = ownership(ctx, proj3)
        script = sorted(p for p, r in rows.items() if r["owner"] == "script")
        expect(f, script == ["hardware/libfix.kicad_dru", "hardware/libfix.kicad_pro", "hardware/libfix.kicad_sch",
                             "hardware/power.kicad_sch"], "reproduced files: %r" % script)
        expect(f, rows.get("hardware/libfix.kicad_pcb", {}).get("owner") == "hand" and
               "libfix.kicad_pcb recorded as hand-owned (the build command did not write it)" in res[1],
               "the board, not written by the command, is not hand-owned with its reason")
        expect(f, all(r["writer"] == cmd + " (own build)" for p, r in rows.items() if r["owner"] == "script"),
               "writer of reproduced files: %r" % sorted(set(r["writer"] for r in rows.values())))
        # HB-7 item 18: the project's own build writes the project file, so DRC never saves in place
        pcb3 = os.path.join(proj3, "hardware", "libfix.kicad_pcb")
        rows["hardware/libfix.kicad_pcb"] = dict(rows["hardware/libfix.kicad_pcb"], owner="script",
                                                 writer="gen_pcb.py (board)", hash=ctx.h.sha256_file(pcb3))
        ctx.h.write_table(os.path.join(proj3, "design", "ownership.csv"), "ownership.csv",
                          [dict((k, v) for k, v in r.items() if k != "_line") for _, r in sorted(rows.items())])
        own_files = [os.path.join(proj3, "hardware", "libfix" + x) for x in (".kicad_pcb", ".kicad_pro", ".kicad_dru")]
        before3 = [fread(p, "rb") for p in own_files]
        expect_run(f, "pcblib drc with a project file the project's own build writes",
                   run([kpy, os.path.join(proj3, SK, "pcblib.py"), "drc", pcb3], env=env), 0,
                   "on a copy (libfix.kicad_pro: written by the project's own build")
        expect(f, [fread(p, "rb") for p in own_files] == before3, "DRC changed a file the project's own build writes")
        # HB-7 item 18: a table problem stops DRC with a plain message, before anything is written
        proj5 = os.path.join(tmp, "lib5")
        shutil.copytree(proj, proj5)
        cons5 = os.path.join(proj5, "design", "constraints.csv")
        fwrite(cons5, fread(cons5) + "CN-099,user,single_point,SENSE,-,dru:bad-rule,whole,own figure,\n")
        pcb5 = os.path.join(proj5, "hardware", "libfix.kicad_pcb")
        rows5 = ownership(ctx, proj5)       # script-owned again (the keep-hand step above made it hand-owned)
        rows5["hardware/libfix.kicad_pcb"] = dict(rows5["hardware/libfix.kicad_pcb"], owner="script",
                                                  writer="gen_pcb.py (board)", hash=ctx.h.sha256_file(pcb5))
        ctx.h.write_table(os.path.join(proj5, "design", "ownership.csv"), "ownership.csv",
                          [dict((k, v) for k, v in r.items() if k != "_line") for _, r in sorted(rows5.items())])
        before5 = fread(pcb5, "rb")
        res = run([kpy, os.path.join(proj5, SK, "pcblib.py"), "drc", pcb5], env=env)
        expect_run(f, "pcblib drc with a constraint that cannot be a rule", res, 2, "cannot be written as a rule",
                   "Nothing was written")
        expect(f, "Traceback" not in res[1] and fread(pcb5, "rb") == before5, "a refused DRC wrote the board or crashed")
        proj4 = os.path.join(tmp, "lib4")
        shutil.copytree(proj, proj4)
        os.remove(os.path.join(proj4, "design", "ownership.csv"))
        child = os.path.join(proj4, "hardware", "power.kicad_sch")
        fwrite(child, fread(child).replace('"POWER"', '"POWER SUPPLY"'))
        res = run([sys.executable, os.path.join(proj4, SK, "build.py"), "--adopt", "--reproduce", cmd], cwd=proj4)
        expect(f, ownership(ctx, proj4).get("hardware/power.kicad_sch", {}).get("owner") == "hand" and
               "power.kicad_sch recorded as hand-owned (the build command writes different bytes)" in res[1],
               "a hand-edited sheet the generator does not reproduce is not hand-owned: %s" % res[1][-400:])
    return f


PLACED_BOARD = r'''
import os, sys
sys.path.insert(0, sys.argv[1])
import pcbnew, pcblib
b = pcblib.GenBoard(sys.argv[3], sys.argv[2], seed=5)
b.outline(0, 0, 30, 20)
b.place_table({"J1": (3, 5, 0), "C1": (8, 9, 90), "U1": (14, 9, 0), "C2": (20, 9, 90),
               "R1": (25, 5, 90), "D1": (25, 11, 90), "R2": (9, 16, 0)})
b.zone("GND", "B.Cu", [(0.5, 0.5), (29.5, 0.5), (29.5, 19.5), (0.5, 19.5)])
r1 = [p for p in b.fps["R1"].Pads() if p.GetNumber() == "2"][0]
d1 = [p for p in b.fps["D1"].Pads() if p.GetNumber() == "2"][0]
a, e = r1.GetPosition(), d1.GetPosition()
side = a.x + pcbnew.FromMM(1.5)                 # beside the two parts, clear of their other pads
pts = [a, pcbnew.VECTOR2I(side, a.y), pcbnew.VECTOR2I(side, e.y), e]
for p, q in zip(pts, pts[1:]):
    t = pcbnew.PCB_TRACK(b.board)
    t.SetStart(p)
    t.SetEnd(q)
    t.SetWidth(pcbnew.FromMM(0.25))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNet(r1.GetNet())
    b.board.Add(t)
b.labels()
b.save()
print("PLACED", " ".join("%.4f %.4f" % (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)) for p in pts[1:3]))
'''


def test_kicad_placed_board_route(ctx):
    """The placed-board driver on a synthetic placed board with one track already laid: routed into a
    copy with DRC clean, the laid track kept, the input untouched."""
    ctx.need_cli()
    kpy = kicad_python(ctx)
    env = lib_env(ctx)
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_lib_project(os.path.join(tmp, "placed"))
        if not expect_run(f, "schematic and netlist", run([sys.executable, os.path.join(proj, SK, "build.py"),
                                                           "sch", "erc", "netlist"], cwd=proj), 0, "ERC: 0 violations"):
            return f
        hw = os.path.join(proj, "hardware")
        pcb = os.path.join(hw, "libfix.kicad_pcb")
        script = os.path.join(tmp, "place.py")
        fwrite(script, PLACED_BOARD)
        res = run([kpy, script, ctx.scripts, os.path.join(hw, "libfix.net"), pcb])
        m = re.search(r"^PLACED (.*)$", res[1], re.MULTILINE)
        if not expect(f, res[0] == 0 and m, "placing the board failed: %s" % res[1][-600:]):
            return f
        laid = tuple(round(float(v), 4) for v in m.group(1).split())
        before = fread(pcb, "rb")
        out = os.path.join(tmp, "routed")
        res = run([kpy, os.path.join(ctx.scripts, "pcblib.py"), "route", pcb, out], env=env)
        expect_run(f, "pcblib route on a placed board", res, 0, "review the routed copy",
                   "3 kept from before routing",
                   "DRC on the routed copy, zones poured again and saved: 0 violations, 0 unconnected, 0 parity items",
                   "input board unchanged")
        expect(f, fread(pcb, "rb") == before, "the input board changed")
        routed = ctx.h.read_sexpr(os.path.join(out, "libfix.kicad_pcb"))
        ends = []
        for s in ctx.h.find(routed, "segment"):
            a, b = ctx.h.first(s, "start"), ctx.h.first(s, "end")
            ends.append((round(float(a[1]), 4), round(float(a[2]), 4), round(float(b[1]), 4), round(float(b[2]), 4)))
        expect(f, laid in ends, "the track laid before routing (%r) is not in the routed copy unchanged" % (laid,))
    return f


def hand_project(ctx):
    """The hand-placed project in the separate test folder, or Skip."""
    path = os.environ.get("HW_SKILLS_TEST_HAND") or os.path.join(os.path.dirname(ctx.root), TEST_DIR, "hand")
    pcbs = [n for n in os.listdir(path) if n.endswith(".kicad_pcb")] if os.path.isdir(path) else []
    if len(pcbs) != 1:
        raise Skip("the hand-placed test project is not there (set HW_SKILLS_TEST_HAND to its folder)")
    return path, pcbs[0]


def test_kicad_hand_project(ctx):
    """The hand-placed, unrouted test project, used only through copies: adopted as hand-owned, DRC on a
    copy, routed into a copy (DRC clean), and order files from the routed copy."""
    ctx.need_cli()
    hand, board = hand_project(ctx)
    kpy = kicad_python(ctx)
    env = lib_env(ctx)
    f = []
    hashes = dict((n, ctx.h.sha256_file(os.path.join(hand, n))) for n in sorted(os.listdir(hand)))
    name = board[:-len(".kicad_pcb")]
    with tempfile.TemporaryDirectory() as tmp:
        proj = os.path.join(tmp, "adopted")
        shutil.copytree(hand, os.path.join(proj, "hardware"))
        os.makedirs(os.path.join(proj, "design"))
        os.makedirs(os.path.join(proj, SK))
        shutil.copy(os.path.join(ctx.scripts, "build.py"), os.path.join(proj, SK, "build.py"))
        for n in ctx.fx.LIB_COPIED:
            shutil.copy(os.path.join(ctx.scripts, n), os.path.join(proj, SK, n))
        res = run([sys.executable, os.path.join(proj, SK, "build.py"), "--adopt"], cwd=proj)
        expect_run(f, "adopt the hand project", res, 0, "done: adopt")
        rows = ownership(ctx, proj)
        expect(f, rows and all(r["owner"] == "hand" for r in rows.values()) and
               "hardware/%s" % board in rows, "adopted records: %r" % sorted((k, v["owner"]) for k, v in rows.items()))
        pcb = os.path.join(proj, "hardware", board)
        before = fread(pcb, "rb")
        res = run([kpy, os.path.join(ctx.scripts, "pcblib.py"), "drc", pcb], env=env)
        expect_run(f, "DRC on the unrouted hand board", res, 1, "on a copy (%s: recorded as hand-owned)" % board,
                   "unconnected")
        expect(f, fread(pcb, "rb") == before, "DRC changed the hand-owned board")
        out = os.path.join(tmp, "routed")
        res = run([kpy, os.path.join(ctx.scripts, "pcblib.py"), "route", pcb, out], env=env)
        expect_run(f, "route the hand board into a copy", res, 0,
                   "DRC on the routed copy, zones poured again and saved: 0 violations, 0 unconnected, 0 parity items",
                   "input board unchanged")
        expect(f, fread(pcb, "rb") == before, "routing changed the hand-owned board")
        # order files from the routed copy, with parts.csv taken from the board's fields
        routed = os.path.join(out, board)
        if os.path.isfile(routed):
            rproj = os.path.join(tmp, "routedproj")
            shutil.copytree(out, os.path.join(rproj, "hardware"))
            os.makedirs(os.path.join(rproj, "design"))
            summary = ctx.h.read_board(routed)
            header = ctx.fx.PARTS_CSV.splitlines()[0]
            cols = header.split(",")
            lines = [header]
            for fp in summary["footprints"]:
                row = dict((c, "") for c in cols)
                fl = fp["fields"]
                row.update(refs=fp["ref"], value=fp["value"], footprint=fp["lib_id"], manufacturer=fl.get("Manufacturer", ""),
                           mpn=fl.get("MPN", ""), supplier=fl.get("Supplier", ""), supplier_pn=fl.get("Supplier PN", ""))
                lines.append(",".join('"%s"' % row[c] if "," in row[c] else row[c] for c in cols))
            fwrite(os.path.join(rproj, "design", "parts.csv"), "\n".join(lines) + "\n")
            res = run([sys.executable, os.path.join(ctx.scripts, "fab.py"), os.path.join(rproj, "hardware", board),
                       os.path.join(rproj, "hardware", "fab"), "--date", "2026-01-02"])
            expect_run(f, "fab.py on the routed hand board", res, 0, "0 violations, 0 unconnected",
                       "Missing sourcing fields (not guessed)", "Consistency (FB-01): pass")
            expect(f, os.path.isfile(os.path.join(rproj, "hardware", "fab", name + "_gerbers.zip")), "no Gerber zip")
    after = dict((n, ctx.h.sha256_file(os.path.join(hand, n))) for n in sorted(os.listdir(hand)))
    expect(f, after == hashes, "the test project's hand/ folder changed")
    return f


SCRIPT_TESTS += [
    ("schlib: pins, flattening, sheets, fields, IDs, refusals (no KiCad)", test_schlib_units),
    ("pcblib: rule file, router radii, clean-report test, project copy", test_pcblib_units),
    ("KiCad: two-sheet schematic, generated board routed, twice, ownership, adopt", test_kicad_lib_build),
    ("KiCad: placed-board driver keeps laid tracks, routes into a copy", test_kicad_placed_board_route),
    ("KiCad: hand-placed test project, adopted, DRC on a copy, routed copy, order files", test_kicad_hand_project),
]
# ======================================================================== end of HB-5 section


# ======================================================================== HB-6 section (check scripts)

def chk(ctx, script, *args, env=None):
    """Run one of the check scripts from the skill folder."""
    return run([sys.executable, os.path.join(ctx.scripts, script)] + list(args), env=env)


def check_proj(ctx, tmp, fault=""):
    return ctx.fx.make_check_project(os.path.join(tmp, fault or "clean"), fault=fault)


CALC = '''"""Worst case: divider (fixture)."""
import itertools

INPUTS = {
    "r_top": (99e3, 100e3, 101e3),   # fixture
    "r_bot": (21.78e3, 22e3, 22.22e3),
    "v_ref": (0.588, 0.6, 0.612),
}
LIMIT = @@LIMIT@@


def result(v):
    return v["v_ref"] * (1 + v["r_top"] / v["r_bot"])


corners = [dict(zip(INPUTS, c)) for c in itertools.product(*[(a, c) for a, _, c in INPUTS.values()])]
values = [result(c) for c in corners]
low, high = min(values), max(values)
print("template line")
assert LIMIT[0] <= low and high <= LIMIT[1], "outside the limit"
'''


def test_check_worstcase(ctx):
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        calc = os.path.join(tmp, "buck_vout.py")
        fwrite(calc, CALC.replace("@@LIMIT@@", "(3.1, 3.5)"))
        res = chk(ctx, "worstcase.py", calc, "--mc", "200", "--seed", "7", "--write")
        expect_run(f, "worstcase inside the limit", res, 0, "buck_vout: min 3.2", "max 3.4", "inside the limit",
                   "Monte Carlo (200 runs, uniform, seed 7)")
        expect(f, "template line" not in res[1], "worstcase ran the template's own print line")
        expect(f, os.path.isfile(os.path.join(tmp, "buck_vout.txt")), "--write saved no .txt")
        again = chk(ctx, "worstcase.py", calc, "--mc", "200", "--seed", "7")
        expect(f, again[1].splitlines()[:4] == res[1].splitlines()[:4], "the seeded Monte Carlo run is not repeatable")
        fwrite(calc, CALC.replace("@@LIMIT@@", "(3.25, 3.35)"))
        expect_run(f, "worstcase outside the limit", chk(ctx, "worstcase.py", calc), 1, "OUTSIDE THE LIMIT")
        fwrite(calc, CALC.replace("@@LIMIT@@", "(3.1, 3.5)").replace("(0.588, 0.6, 0.612)", "(0.612, 0.6, 0.588)"))
        expect_run(f, "worstcase with inputs out of order", chk(ctx, "worstcase.py", calc), 2, "(min, nominal, max)")
    return f


def test_check_sch(ctx):
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        res = chk(ctx, "sch_check.py", "all", "--project", proj)
        expect_run(f, "sch_check all on the clean fixture", res, 0, "pins: pass", "alloc: pass", "powerup: pass",
                   "testpoints: pass", "U4 pin 2 GND: power_in hidden, net GND", "unconfirmed rows: J2 2 of 6, U2 2 of 12",
                   "J2.2: net /SWDIO; series: none; protection: NONE; reaches: U2.8",
                   "J1.1: net +VIN; series: none; protection: D1 on +VIN", "/INT: 1 pull: R5 10k to +3V3",
                   "R6 4k7 pull-up to +3V3: up to 702 uA", "+3V3: 22.1 uF nominal")
        expect(f, fread(os.path.join(proj, "design", "net-review.csv")).count("\n") == 1,
               "a review list wrote net-review.csv without --record")
        # the seeded faults
        expect_run(f, "pins with U2 TX and RX swapped", chk(ctx, "sch_check.py", "pins", "--project",
                                                            check_proj(ctx, tmp, "pin_swap")), 1,
                   "U2 pin 6 (PA2): on net /RX, pins.csv says /TX", "U2 pin 7 (PA3): on net /TX, pins.csv says /RX")
        expect_run(f, "powerup with the enable pull-down removed", chk(ctx, "sch_check.py", "powerup", "--project",
                                                                      check_proj(ctx, tmp, "floating_enable")), 1,
                   "U3 pin 3 (EN), net /BOOST_EN: must be low in reset; nothing gives it")
        nopull = check_proj(ctx, tmp, "no_int_pull")
        expect_run(f, "opendrain with the interrupt pull removed", chk(ctx, "sch_check.py", "opendrain", "--project", nopull),
                   1, "/INT: 0 pulls: NONE", "opendrain: FAIL (1)")
        # the review list closed with reasons, then reopened when the circuit changes
        expect_run(f, "opendrain --record", chk(ctx, "sch_check.py", "opendrain", "--record", "--project", proj), 0,
                   "recorded 3 new and 0 reopened items")
        nr = os.path.join(proj, "design", "net-review.csv")
        rows = ctx.h.read_table(nr)
        for r in rows:
            r.update({"reason": "pull fitted (%s)" % r["item"].split(": ")[-1].split(" ")[0], "closed_by": "worker",
                      "date": "2026-01-02"})
        ctx.h.write_table(nr, "net-review.csv", rows)
        expect_run(f, "netreview with every item closed", chk(ctx, "table_check.py", "netreview", "--project", proj), 0,
                   "netreview: pass")
        shutil.copy(nr, os.path.join(nopull, "design", "net-review.csv"))
        expect_run(f, "opendrain --record after the pull was removed",
                   chk(ctx, "sch_check.py", "opendrain", "--record", "--project", nopull), 1,
                   "CHANGED since it was closed", "recorded 0 new and 1 reopened items", "opendrain: FAIL (1)")
        # an open item is listed and counted in an ordinary run, and fails only at the schematic checkpoint
        early = chk(ctx, "table_check.py", "netreview", "--project", nopull)
        expect_run(f, "netreview after the item reopened, no checkpoint", early, 0,
                   "net-review items: 3, open: 1", "  NR-001 opendrain /INT: open (no written reason)", "netreview: pass")
        expect(f, "FAIL  NR-001" not in early[1], "netreview failed an open item with no --stage")
        expect_run(f, "netreview after the item reopened, ST5", chk(ctx, "table_check.py", "netreview", "--project", nopull,
                                                                    "--stage", "ST5"), 0, "netreview: pass")
        expect_run(f, "netreview after the item reopened, schematic checkpoint",
                   chk(ctx, "table_check.py", "netreview", "--project", nopull, "--stage", "ST6"), 1,
                   "FAIL  NR-001 opendrain /INT: open (no written reason)", "netreview: FAIL (1)")
        # a test point asked for and missing; unreadable input
        fwrite(os.path.join(proj, "design", "requirements.md"),
               ctx.fx.CHECK_REQUIREMENTS_MD.replace("- +3V3: bench", "- +3V3: bench\n- /SDA: production test"))
        expect_run(f, "testpoints with one missing", chk(ctx, "sch_check.py", "testpoints", "--project", proj), 1,
                   "net /SDA has no test point")
        os.remove(os.path.join(proj, "hardware", "check.net"))
        expect_run(f, "sch_check with no netlist", chk(ctx, "sch_check.py", "pins", "--project", proj), 2,
                   "no netlist at")
    return f


def test_check_st_import(ctx):
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        data = ctx.fx.write_st_data(os.path.join(tmp, "st"))
        args = ["pins", "--project", proj, "--import", "st", "--data", data, "--designator", "U2"]
        expect_run(f, "ST pin data against the U2 rows", chk(ctx, "sch_check.py", *args), 0,
                   "vendor data: STM32X001AXTx.xml (RefName STM32X001AXTx) for U2, MPN STM32X001AXT6", "pins: pass")
        bad = ctx.fx.write_st_data(os.path.join(tmp, "st_bad"), rename_pin6=True)
        expect_run(f, "ST pin data with pin 6 renamed",
                   chk(ctx, "sch_check.py", *(args[:6] + [bad] + args[7:])), 1,
                   "U2 pin 6: pins.csv name 'PA2', vendor data 'PA9'")
        expect_run(f, "an importer that does not exist", chk(ctx, "sch_check.py", "pins", "--project", proj,
                                                             "--import", "acme", "--data", data), 2,
                   "no importer for 'acme'", "st = ST open pin data")
        pins = os.path.join(proj, "design", "pins.csv")
        keep = [l for l in fread(pins).splitlines() if not l.startswith("U2,")]
        fwrite(pins, "\n".join(keep) + "\n")
        expect_run(f, "ST pin data written as new rows", chk(ctx, "sch_check.py", *(args + ["--write"])), 0,
                   "12 rows for U2 from the vendor data", "wrote 12 rows")
        rows = [r for r in ctx.h.read_table(pins) if r["designator"] == "U2"]
        expect(f, len(rows) == 12 and all(r["confirmed"] == "" for r in rows)
               and rows[0]["source"] == "vendor data ST open pin data STM32X001AXTx.xml, DBVersion V9.9",
               "written rows: %r" % rows[:1])
    return f


def test_check_tables(ctx):
    f = []
    tc = "table_check.py"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        p = ["--project", proj, "--today", "2026-01-10"]
        expect_run(f, "table_check all on the clean fixture", chk(ctx, tc, "all", *p), 0, "compliance: pass",
                   "sections: pass", "constraints: pass", "fabcap: pass", "parts: pass", "packs: pass", "suppress: pass",
                   "stale: pass", "findings: pass", "netreview: pass", "checklists: pass", "text: pass", "writers: pass",
                   "constraints by enforcer: rule (dru:) 1, check (check:) 12, review alone (review:) 1",
                   "carried rows resting on a reviewer's verdict alone: 1 (DS-018)")
        expect_run(f, "summary", chk(ctx, tc, "summary", *p), 0,
                   "unconfirmed pin rows, microcontrollers: U2 2 of 12",
                   "unconfirmed pin rows, connectors: J1 0 of 2, J2 2 of 6", "layout rows carried: 9, with constraints: 9",
                   "open waivers: 1 (DC-002)", "ST7: capabilities sourced 8 of 8", "not counted:")
        expect_run(f, "impact of U1", chk(ctx, tc, "impact", "U1", *p), 0, "constraints.csv: CN-002", "pins.csv: U1 5",
                   "sections.csv: BUCK-1.pdf 7.4")
        # the seeded faults of the exit check
        for fault, cmd, text in (
                ("layout_no_constraint", "constraints", "DS-019 (U1, 7.4 Layout guidelines): carried layout row with no constraint"),
                ("same_island_only", "constraints", "DS-010: the text asks for single point"),
                ("rule_no_source", "fabcap", "min_track (line 2): source_url ''"),
                ("part_swapped", "stale", "compliance.csv DS-001: taken from BUCK-1, but U1 is now BUCK-2")):
            expect_run(f, "%s with the fault %s" % (cmd, fault),
                       chk(ctx, tc, cmd, "--project", check_proj(ctx, tmp, fault)), 1, text)
        same = chk(ctx, tc, "constraints", "--project", os.path.join(tmp, "same_island_only"))
        expect(f, "the sufficiency is partial at most" in same[1], "the same_island-only fault does not say partial")
        # more faults, each on a copy of the clean fixture
        cases = (
            ("design/reports/BR-02-01.md", "CN-014 met:", "CN-099 met:", "constraints", "CN-014 (line 15): no verdict in section 6"),
            ("design/constraints.csv", "no sub-command reads the port direction", "", "constraints", "review:BD-07 alone needs"),
            ("hardware/check.kicad_dru", 'rule "netclass Power clearance"', 'rule "netclass Power other"', "constraints",
             "rule 'netclass Power clearance' is not in the rule file"),
            ("design/compliance.csv", "should,protection,electrical,\"An input fuse should be fitted\",none,,not met,,DC-001",
             "should,protection,electrical,\"An input fuse should be fitted\",none,,not met,,proposed", "compliance",
             "DS-003 (line 4): hard row (protection) is not met with no DC- decision (proposed)"),
            ("design/compliance.csv", ",must,layout,physical,\"Place the input capacitor close to VIN\",,,carried",
             ",must,layout,physical,\"Place the input capacitor close to VIN\",,,met", "compliance",
             "a layout row is carried to constraints, not met"),
            ("design/requirements.md", "- Microcontroller; on;", "- Microcontroller; off;", "packs",
             "U2 (STM32X001AXT6): category microcontroller switches pack GS-SEC on, but the board profile has Microcontroller off"),
            ("design/sections.csv", "thermal,electrical;physical,0,0,0,no instructions here (BR-01-01; 2026-01-02)",
             "thermal,electrical;physical,0,0,0,", "sections", "thermal section with zero rows and no note"),
            ("design/findings.csv", "reviewer side remark,open,", "reviewer side remark,,", "findings", "not triaged"),
            ("README.md", "U1 converts", "U9 converts", "text", "README.md:3: U9 is not a designator in the design"),
        )
        for i, (rel, old, new, cmd, text) in enumerate(cases):
            copy = os.path.join(tmp, "case%d" % i)
            shutil.copytree(proj, copy)
            path = os.path.join(copy, rel)
            body = fread(path)
            if not expect(f, old in body, "case %d: %r not in %s" % (i, old, rel)):
                continue
            fwrite(path, body.replace(old, new, 1))
            expect_run(f, "%s after editing %s (case %d)" % (cmd, rel, i), chk(ctx, tc, cmd, "--project", copy,
                                                                                "--today", "2026-01-10"), 1, text)
        os.remove(os.path.join(proj, "design", "renders", "BUCK-1_p12.png"))
        expect_run(f, "compliance with the render missing", chk(ctx, tc, "compliance", *p), 1,
                   "DS-002 (line 3): graph row has no saved render design/renders/BUCK-1_p12.png")
        os.makedirs(os.path.join(proj, "design", "passes"))
        fwrite(os.path.join(proj, "design", "passes", "BUCK-1_physical.csv"), ",".join(ctx.h.TABLES["compliance.csv"]) + "\n")
        fwrite(os.path.join(proj, "design", "passes", "U1-physical.csv"), ",".join(ctx.h.TABLES["compliance.csv"]) + "\n")
        expect_run(f, "compliance with a badly named staging file", chk(ctx, tc, "compliance", *p), 1,
                   "design/passes/U1-physical.csv: name it <MPN>_<perspective>.csv", "staging files in design/passes/")
        # an old stock and price date is listed with its age in any run, and fails only before ordering (ST12)
        old = chk(ctx, tc, "parts", "--project", proj, "--today", "2026-06-01")
        expect_run(f, "parts checked long ago, ordinary run", old, 0,
                   "checked 2026-01-02, 150 days ago (more than 30); a fail only at the parts check before ordering",
                   "parts: pass")
        expect(f, "FAIL  " not in old[1], "parts failed an old date with no --stage")
        expect_run(f, "parts checked long ago, schematic checkpoint",
                   chk(ctx, tc, "parts", "--project", proj, "--today", "2026-06-01", "--stage", "ST6"), 0, "parts: pass")
        expect_run(f, "parts checked long ago, before ordering",
                   chk(ctx, tc, "parts", "--project", proj, "--today", "2026-06-01", "--stage", "ST12"), 1,
                   "FAIL  ", "checked 2026-01-02, 150 days ago (more than 30)")
        expect_run(f, "an unknown sub-command first", chk(ctx, tc, "U1", "impact", *p), 2, "start with a sub-command")
    return f


def test_check_scan(ctx):
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        out_dir = os.path.join(proj, "out")
        os.makedirs(out_dir)
        fwrite(os.path.join(out_dir, "clean.txt"), "U1 converts 12 V to 3.3 V.\n")
        expect_run(f, "scan of a clean folder", chk(ctx, "table_check.py", "scan", out_dir, "--project", proj), 0,
                   "findings 0")
        secret = "hunter" + "22" + "secret"
        mail = "someone" + "@" + "example.org"
        home = "/" + "Users/" + "someone/project/board.kicad_pcb"
        key = "AKIA" + "ABCDEFGHIJKLMNOP"
        fwrite(os.path.join(proj, "design", ".private-terms"), "Clientco\n")
        fwrite(os.path.join(out_dir, "notes.txt"), "built in %s\nmail %s\npassword = %s\nkey %s\n"
               "Order number: 12345-678\nfor Clientco\n" % (home, mail, secret, key))
        fwrite(os.path.join(out_dir, "x.net"), '(export (version "E") (design (source "%s") (date "2026-01-02 10:00")))\n'
               % home)
        with zipfile.ZipFile(os.path.join(out_dir, "gerbers.zip"), "w") as z:
            z.writestr("a.gbr", "G04 made by %s*\n" % mail)
        res = chk(ctx, "table_check.py", "scan", out_dir, "--project", proj)
        expect_run(f, "scan with seeded secrets", res, 1, "machine path", "email address", "password or token",
                   "access key", "account or order number", "private term", "netlist source", "netlist date",
                   "gerbers.zip!a.gbr:1: email address")
        for value in (secret, mail, home, key, "Clientco", "12345-678"):
            expect(f, value not in res[1], "the scan printed %r in full" % value)
    return f


def test_check_board(ctx):
    f = []
    bc = "board_check.py"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        p = ["--project", proj, "--no-repour"]
        expect_run(f, "board_check on the clean fixture", chk(ctx, bc, *p), 0, "board_check: 12 passed, 0 failed",
                   "PASS CN-001 same_island", "PASS CN-002 single_point", "every join is inside U1.3")
        off = check_proj(ctx, tmp, "pad_off_island")
        expect_run(f, "the ground pad moved off the island", chk(ctx, bc, "--project", off, "--no-repour"), 1,
                   "FAIL CN-001 same_island", "2 pieces on F.Cu")
        expect_run(f, "the same fault, waived", chk(ctx, bc, "same_island", "--project", off, "--no-repour",
                                                   "--waive", "CN-001=DC-002"), 0, "WAIVED by DC-002 CN-001")
        expect_run(f, "a waiver not in decisions.md", chk(ctx, bc, "--project", off, "--no-repour", "--waive",
                                                         "CN-001=DC-099"), 2, "not in design/decisions.md")
        for check, objects, limit, code, text in (
                ("via_in_pad", "U1", "0", 1, "1 vias in pads (allowed 0)"),
                ("distance", "U1.1; C1.1", "1", 1, "TOO FAR"),
                ("keepout", "area:108,108,112,112", "", 1, "pad U1.3 of GND on F.Cu"),
                ("noisy_distance", "U1.4; noisy:/SW", "3", 1, "TOO CLOSE"),
                ("decouple_per_pin", "U2.1", "0.1", 1, "C3 at 0.250 mm (limit 0.1)  TOO FAR"),
                ("edge_distance", "J1", "2", 1, "J1 (courtyard)"),
                ("via_count", "U1.3", "1", 1, "cannot run: via_count needs within:<mm>"),
                ("single_point", "U1.3; layer:F.Cu", "0.5", 0, "spread of the joins 0.000 mm")):
            args = [check, "--objects", objects] + (["--limit", limit] if limit else []) + p
            expect_run(f, "%s %s" % (check, objects), chk(ctx, bc, *args), code, text)
        expect_run(f, "an aid", chk(ctx, bc, "loop_area", "--objects", "C1.1; U1.1; U1.3; C1.2", *p), 0,
                   "mm2", "not a pass or fail")
        expect_run(f, "node capacitance", chk(ctx, bc, "node_capacitance", "--objects", "/SW", "--er", "4.5", "--h",
                                              "1.5", *p), 0, "pF in total")
        expect_run(f, "an unknown check", chk(ctx, bc, "nearness", *p), 2, "unknown check 'nearness'")
        expect_run(f, "unreadable objects", chk(ctx, bc, "distance", "--objects", "U1.1; ??", "--limit", "1", *p), 1,
                   "cannot read '??'")
        body = fread(os.path.join(proj, "hardware", "check.kicad_pcb"))
        two = body.replace('(filled_polygon (layer "B.Cu") (pts (xy 100.5 100.5)',
                           '(filled_polygon (layer "B.Cu") (pts (xy 101 101) (xy 102 101) (xy 102 102)))\n'
                           '    (filled_polygon (layer "B.Cu") (pts (xy 100.5 100.5)', 1)
        fwrite(os.path.join(proj, "hardware", "check.kicad_pcb"), two)
        expect_run(f, "the plane in two pieces", chk(ctx, bc, "plane_one_piece", *p), 1, "2 pieces")
    return f


def test_kicad_check_scripts(ctx):
    ctx.need_cli()
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        board = os.path.join(proj, "hardware", "check.kicad_pcb")
        before = fread(board, "rb")
        expect_run(f, "board_check with the zones poured again by kicad-cli", chk(ctx, "board_check.py", "--project", proj),
                   0, "zones poured again on a copy by kicad-cli", "board_check: 12 passed, 0 failed")
        expect(f, fread(board, "rb") == before, "board_check changed the design's board file")
        expect_run(f, "artefacts on the partly routed fixture, poured by kicad-cli",
                   chk(ctx, "board_check.py", "artefacts", "--objects", "", "--project", proj), 1,
                   "unrouted connections (from the file): 36", "unconnected items (KiCad DRC after the re-pour): 36")
        off = check_proj(ctx, tmp, "pad_off_island")
        expect_run(f, "pad off the island, poured by kicad-cli", chk(ctx, "board_check.py", "same_island", "--project", off),
                   1, "FAIL CN-001 same_island")
        # the HB-4 fixture, built by build.py with kicad-cli: real netlist and board
        hb4 = ctx.fx.make_project(os.path.join(tmp, "hb4"))
        if not expect_run(f, "build.py sch erc netlist board", build_run(hb4, "sch", "erc", "netlist", "board"), 0,
                          "ERC: 0 violations"):
            return f
        expect_run(f, "sch_check pins on a KiCad-exported netlist", chk(ctx, "sch_check.py", "pins", "--project", hb4), 0,
                   "pins: pass")
        expect_run(f, "sch_check protect on a KiCad-exported netlist", chk(ctx, "sch_check.py", "protect", "--project", hb4),
                   0, "J1.1: net /A", "protection: NONE")
        expect_run(f, "table_check stale on a KiCad-exported netlist", chk(ctx, "table_check.py", "stale", "--project", hb4),
                   0, "stale: pass")
        expect_run(f, "artefacts on the routed HB-4 board", chk(ctx, "board_check.py", "artefacts", "--objects", "",
                                                                 "--project", hb4), 0, "unrouted connections (from the file): 0")
        pcb = os.path.join(hb4, "hardware", "fixture.kicad_pcb")
        text = fread(pcb)
        fwrite(pcb, text.replace("  (via ", '  (segment (start 120 112) (end 122 112) (width 0.25) (layer "F.Cu") '
                                             '(net "/A") (uuid "00000000-0000-0000-0000-00000000dead"))\n  (via ', 1))
        expect_run(f, "artefacts with a dangling track", chk(ctx, "board_check.py", "artefacts", "--objects", "",
                                                             "--project", hb4), 1, "dangling track end of /A")
    return f


SCRIPT_TESTS += [
    ("worstcase: corners, seeded Monte Carlo, limit, template lines skipped", test_check_worstcase),
    ("sch_check: clean fixture, seeded faults, review list closed and reopened", test_check_sch),
    ("sch_check: ST open pin data importer (invented fixture file)", test_check_st_import),
    ("table_check: clean fixture, the exit-check faults and more", test_check_tables),
    ("table_check scan: seeded secrets found and masked", test_check_scan),
    ("board_check: clean fixture, ground pad off the island, waiver, ad hoc checks, aids", test_check_board),
    ("KiCad: board_check after a kicad-cli pour; checks on KiCad-exported files", test_kicad_check_scripts),
]
# ======================================================================== end of HB-6 section


# ======================================================================== HB-7 section (adoption fixes)

def own_layout(ctx, dest, folder="."):
    """The check fixture as an existing project in its own layout: its KiCad files moved out of hardware/
    into folder (the root by default), no ownership rows, build.py in hwskills/."""
    ctx.fx.make_check_project(dest)
    hw = os.path.join(dest, "hardware")
    target = os.path.normpath(os.path.join(dest, folder))
    os.makedirs(target, exist_ok=True)
    for n in sorted(os.listdir(hw)):
        shutil.move(os.path.join(hw, n), os.path.join(target, n))
    os.rmdir(hw)
    fwrite(os.path.join(dest, "design", "ownership.csv"), "path,owner,writer,hash,commit\n")
    shutil.copy(os.path.join(ctx.scripts, "build.py"), os.path.join(dest, SK, "build.py"))
    return dest


def kicad_hashes(ctx, folder):
    return dict((n, ctx.h.sha256_file(os.path.join(folder, n))) for n in sorted(os.listdir(folder))
                if n.startswith(ctx.fx.CHECK_NAME + "."))


def test_adopt_own_layout(ctx):
    """KiCad files in the project root or another folder: --adopt records the folder in status.md and
    every check script finds the files there; the layout is kept."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = own_layout(ctx, os.path.join(tmp, "root"))
        before = kicad_hashes(ctx, proj)
        expect_run(f, "build with the KiCad files in the root, before adoption", build_run(proj, "erc"), 2,
                   "no hardware/ folder in", "build.py --adopt finds them")
        res = build_run(proj, "--adopt")
        expect_run(f, "adopt with the KiCad files in the root", res, 0, "KiCad files found in the project root",
                   "KiCad folder: . (the project root)", "ownership: check.kicad_pcb recorded as hand-owned",
                   "done: adopt")
        status = fread(os.path.join(proj, "design", "status.md"))
        expect(f, "\nKiCad folder: . (the project root)\n" in status and
               status.index("Ownership:") < status.index("KiCad folder:") < status.index("Tools:"),
               "status.md after adoption:\n%s" % status)
        rows = ownership(ctx, proj)
        expect(f, "check.kicad_pcb" in rows and "fp-lib-table" in rows and
               all(r["owner"] == "hand" for r in rows.values()) and
               not [p for p in rows if p.startswith(("hardware/", "design/", "scripts/", SK + "/")) or p.endswith(".net")],
               "ownership rows: %r" % sorted(rows))
        again = build_run(proj, "--adopt")
        expect_run(f, "adopt again", again, 0, "check.kicad_pcb already recorded")
        expect(f, "KiCad files found" not in again[1] and fread(os.path.join(proj, "design", "status.md")) == status,
               "a second adoption changed status.md")
        expect_run(f, "sch_check all, files in the root", chk(ctx, "sch_check.py", "all", "--project", proj), 0,
                   "pins: pass", "powerup: pass", "J2.2: net /SWDIO; series: none; protection: NONE; reaches: U2.8")
        res = chk(ctx, "table_check.py", "all", "--project", proj, "--today", "2026-01-10")
        expect_run(f, "table_check all, files in the root", res, 0, "compliance: pass", "constraints: pass",
                   "fabcap: pass", "parts: pass", "suppress: pass", "stale: pass", "text: pass", "writers: pass",
                   "design files with no ownership row (hand-owned): 0")
        expect(f, "not run" not in res[1], "a check did not run with the files in the root")
        expect_run(f, "board_check, files in the root", chk(ctx, "board_check.py", "--project", proj, "--no-repour"),
                   0, "board_check: 12 passed, 0 failed")
        expect(f, kicad_hashes(ctx, proj) == before, "adoption or a check changed a design file")
        # a sub-folder of the user's choosing
        sub = own_layout(ctx, os.path.join(tmp, "sub"), "electronics/kicad")
        expect_run(f, "adopt with the KiCad files in electronics/kicad", build_run(sub, "--adopt"), 0,
                   "KiCad folder: electronics/kicad/", "ownership: electronics/kicad/check.kicad_pcb recorded")
        expect_run(f, "sch_check pins, files in electronics/kicad", chk(ctx, "sch_check.py", "pins", "--project", sub),
                   0, "pins: pass")
        expect_run(f, "board_check from inside the KiCad folder",
                   chk(ctx, "board_check.py", "--project", os.path.join(sub, "electronics", "kicad"), "--no-repour"), 0,
                   "board_check: 12 passed, 0 failed")
        # two KiCad projects: adoption asks which, and goes on once status.md names it
        two = own_layout(ctx, os.path.join(tmp, "two"), "a")
        os.makedirs(os.path.join(two, "b"))
        shutil.copy(os.path.join(two, "a", "check.kicad_pro"), os.path.join(two, "b", "other.kicad_pro"))
        expect_run(f, "adopt with two KiCad projects", build_run(two, "--adopt"), 2,
                   "KiCad projects in several folders (a/, b/)", "'KiCad folder: <folder>'")
        fwrite(os.path.join(two, "design", "status.md"), ctx.fx.CHECK_STATUS_MD + "KiCad folder: a/\n")
        expect_run(f, "adopt once status.md names the folder", build_run(two, "--adopt"), 0,
                   "ownership: a/check.kicad_pcb recorded as hand-owned")
        # a folder outside the project is refused; the hardware/ layout writes no line
        fwrite(os.path.join(two, "design", "status.md"), ctx.fx.CHECK_STATUS_MD + "KiCad folder: ../elsewhere\n")
        expect_run(f, "a KiCad folder outside the root", chk(ctx, "sch_check.py", "pins", "--project", two), 2,
                   "must name a folder inside the project root")
        std = check_proj(ctx, tmp)
        shutil.copy(os.path.join(ctx.scripts, "build.py"), os.path.join(std, SK, "build.py"))
        expect_run(f, "adopt in the hardware/ layout", build_run(std, "--adopt"), 0, "done: adopt")
        expect(f, "KiCad folder" not in fread(os.path.join(std, "design", "status.md")),
               "adoption wrote a KiCad folder line for the default hardware/ layout")
    return f


def test_check_hb7_tables(ctx):
    """table_check: checklists and missing tables listed until a checkpoint, KiCad's default severities,
    pin-level impact, named hand-owned files, a pass's staging files checked before the merge."""
    f = []
    tc = "table_check.py"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        # checklists: an item with no result is listed in a plain run and fails only at a checkpoint
        copy = os.path.join(tmp, "checklists")
        shutil.copytree(proj, copy)
        rep = os.path.join(copy, "design", "reports", "BR-02-01.md")
        fwrite(rep, fread(rep).replace("SC-01 met", "met"))
        plain = chk(ctx, tc, "checklists", "--project", copy)
        expect_run(f, "checklists with an item open, plain run", plain, 0, "with no result yet: 1",
                   "  SC-01 (board.md): no result in any review report", "checklists: pass")
        expect(f, "FAIL" not in plain[1], "checklists failed an open item in a plain run")
        expect_run(f, "checklists open item, all", chk(ctx, tc, "all", "--project", copy, "--today", "2026-01-10"), 0,
                   "SC-01 (board.md): no result", "checklists: pass")
        expect_run(f, "checklists at ST9 (SC-01 belongs to ST10)", chk(ctx, tc, "checklists", "--project", copy,
                                                                        "--stage", "ST9"), 0, "checklists: pass")
        expect_run(f, "checklists at the board checkpoint", chk(ctx, tc, "checklists", "--project", copy, "--stage",
                                                                 "ST11"), 1, "FAIL  SC-01 (board.md): no result")
        # missing tables: not present, check not run; a fail only from the table's checkpoint on
        gone = os.path.join(tmp, "gone")
        shutil.copytree(proj, gone)
        for n in ("compliance.csv", "findings.csv", "fab-capabilities.csv"):
            os.remove(os.path.join(gone, "design", n))
        res = chk(ctx, tc, "all", "--project", gone, "--today", "2026-01-10")
        expect_run(f, "all with three tables missing", res, 0, "design/compliance.csv not present, check not run",
                   "compliance: not run", "fabcap: not run", "findings: not run",
                   "not run (input not present): compliance, fabcap, findings")
        expect(f, "compliance: pass" not in res[1] and "findings: pass" not in res[1],
               "a missing table still passes silently")
        res = chk(ctx, tc, "all", "--project", gone, "--today", "2026-01-10", "--stage", "ST6")
        expect_run(f, "all with three tables missing, schematic checkpoint", res, 1,
                   "FAIL  design/compliance.csv not present, check not run (a fail from --stage ST6 on)",
                   "FAIL  design/findings.csv not present", "fabcap: not run")
        expect_run(f, "fabcap missing at the board checkpoint", chk(ctx, tc, "fabcap", "--project", gone,
                                                                    "--stage", "ST11"), 1,
                   "FAIL  design/fab-capabilities.csv not present, check not run")
        # board severities left at KiCad's defaults: listed with a recommendation, failed at the board checkpoint
        sev = os.path.join(tmp, "sev")
        shutil.copytree(proj, sev)
        pro_path = os.path.join(sev, "hardware", "check.kicad_pro")
        pro = json.loads(fread(pro_path))
        pro["board"]["design_settings"]["rule_severities"]["connection_width"] = "warning"
        fwrite(pro_path, json.dumps(pro, indent=2, sort_keys=True) + "\n")
        res = chk(ctx, tc, "suppress", "--project", sev)
        expect_run(f, "suppress with a KiCad default severity", res, 0,
                   "board check connection_width is warning, KiCad's default; recommended: error", "suppress: pass")
        expect_run(f, "the same at the board checkpoint", chk(ctx, tc, "suppress", "--project", sev, "--stage", "ST11"),
                   1, "FAIL  board check connection_width is warning, KiCad's default; recommended: error; no decision")
        pro["board"]["design_settings"]["rule_severities"]["via_dangling"] = "ignore"
        fwrite(pro_path, json.dumps(pro, indent=2, sort_keys=True) + "\n")
        expect_run(f, "suppress with a severity below KiCad's default", chk(ctx, tc, "suppress", "--project", sev), 1,
                   "FAIL  board check via_dangling is ignore, should be error; no decision names it")
        # no rule file (a hand-made project): a net class in the project file counts, at or above the limit
        nodru = os.path.join(tmp, "nodru")
        shutil.copytree(proj, nodru)
        os.remove(os.path.join(nodru, "hardware", "check.kicad_dru"))
        expect_run(f, "constraints with no rule file", chk(ctx, "table_check.py", "constraints", "--project", nodru), 0,
                   "no rule file: net classes taken from the project file for CN-013", "constraints: pass")
        cons_path = os.path.join(nodru, "design", "constraints.csv")
        fwrite(cons_path, fread(cons_path).replace("CN-013,user,clearance,+VIN,0.4,", "CN-013,user,clearance,+VIN,0.5,"))
        expect_run(f, "constraints with no rule file and a class below the limit",
                   chk(ctx, "table_check.py", "constraints", "--project", nodru), 1,
                   "net class Power has clearance 0.4 in the project file, below the limit 0.5")
        # impact matches pin-level keys (J2.2 traces to J2)
        fwrite(os.path.join(proj, "design", "net-review.csv"), "id,list,net_or_pin,item,reason,closed_by,date\n"
               "NR-001,protect,J2.2,\"net /SWDIO; series: none; protection: NONE; reaches: U2.8\",,,\n")
        expect_run(f, "impact of J2 with a pin-level review item", chk(ctx, tc, "impact", "J2", "--project", proj), 0,
                   "net-review.csv: NR-001")
        # writers names the design files that have no ownership row
        res = chk(ctx, tc, "writers", "--project", proj)
        expect_run(f, "writers names the files with no row", res, 0, "  hardware/check.kicad_sch",
                   "  hardware/fp-lib-table")
        expect(f, "hardware/check.net" not in res[1], "writers counts the exported netlist as a design file")
        # a pass's staging files, checked before the merge
        passes = os.path.join(proj, "design", "passes")
        os.makedirs(passes)
        rows_path = os.path.join(passes, "BUCK-1_physical.csv")
        head = ",".join(ctx.h.TABLES["compliance.csv"])
        good = ('physical-1,,BUCK-1,BUCK-1.pdf,A,7.4,10,,must,layout,physical,"Keep the loop small",,,carried,,,,,pass\n'
                'physical-2,,BUCK-1,BUCK-1.pdf,A,9,13,,recommend,thermal,physical,"Use thermal vias",,,open,,,,,pass\n')
        fwrite(rows_path, head + "\n" + good)
        sec_path = os.path.join(passes, "BUCK-1_physical_sections.csv")
        sec_head = ",".join(ctx.h.TABLES["sections.csv"])
        fwrite(sec_path, sec_head + "\nBUCK-1.pdf,A,7.4,Layout guidelines,10-11,layout,physical,0,0,1,\n"
               "BUCK-1.pdf,A,9,Thermal information,13,thermal,physical,0,0,1,\n"
               "BUCK-1.pdf,A,6,Absolute maximum ratings,2,absolute-maximum,,0,0,0,\n"
               "BUCK-1.pdf,A,8,Typical application,12,typical-application,,0,0,0,\n")
        res = chk(ctx, tc, "compliance", "sections", "--project", proj, "--staged", rows_path, "--staged", sec_path)
        expect_run(f, "a clean staged pass", res, 0, "staged rows checked (before the merge): BUCK-1_physical.csv",
                   "compliance: pass", "sections: pass",
                   "not claimed in these files (another pass's scope, or still to claim; listed, not failed): 2")
        # item 5: the staging file holds the whole inventory; an empty one, or one with a section left out, fails
        whole = fread(sec_path)
        fwrite(sec_path, sec_head + "\n")
        expect_run(f, "an empty staged sections file", chk(ctx, tc, "sections", "--project", proj, "--staged", sec_path),
                   1, "BUCK-1_physical_sections.csv holds no rows")
        fwrite(sec_path, "\n".join(l for l in whole.splitlines() if ",A,8," not in l) + "\n")
        expect_run(f, "a staged sections file missing an inventory section",
                   chk(ctx, tc, "sections", "--project", proj, "--staged", sec_path), 1,
                   "1 sections of the BUCK-1.pdf inventory are missing from the staging file", ": 8")
        # item 10: a relative --staged path is found from --project, and the project from the staged path
        rel = os.path.join("design", "passes", "BUCK-1_physical.csv")
        expect_run(f, "a relative --staged path with --project", chk(ctx, tc, "compliance", "--project", proj,
                                                                    "--staged", rel), 0, "compliance: pass")
        expect_run(f, "no --project: the project found from the staged path",
                   chk(ctx, tc, "compliance", "--staged", rows_path), 0, "compliance: pass")
        fwrite(sec_path, whole)
        fwrite(rows_path, head + "\n" + good.replace("physical-2,", "DS-050,").replace(",thermal,physical,",
                                                                                      ",thermal,electrical,"))
        fwrite(sec_path, sec_head + "\nBUCK-1.pdf,A,7.4,Layout guidelines,10-11,layout,physical,0,0,0,\n"
               "BUCK-1.pdf,A,9,Thermal information,13,thermal,electrical,0,1,0,\n")
        res = chk(ctx, tc, "compliance", "sections", "--project", proj, "--staged", rows_path, "--staged", sec_path)
        expect_run(f, "a staged pass with faults", res, 1, "DS-050 (BUCK-1_physical.csv line 3): id must be physical-<n>",
                   "perspective 'electrical' lacks physical", "layout section with zero rows and no note",
                   "a staging file holds the claims of its own pass (physical) only")
        expect_run(f, "a badly named staging file given", chk(ctx, tc, "compliance", "--project", proj, "--staged",
                                                              os.path.join(passes, "U1-physical.csv")), 2,
                   "name it <MPN>_<perspective>.csv")
    return f


DC_WORKER = """
## Read the input capacitor's rating from the datasheet table, not the front page (DC-003)
Kind: decision
Decided by: worker BR-03-02; seen by user: no
Date: 2026-01-05
Stage: ST3
Options: the table (chosen); the front page
Reason: the two places disagree (DS-001); the table is the cautious reading
Affects: requirements none; parts none; schematic none; board none; cost none
Status: in force
"""


def test_check_decision_log(ctx):
    """table_check: the decision log (fields, IDs, back-pointers, entries the user has not seen), a pass's
    staged findings, an empty capability table, checklists in ID order, calculation and no-guidance rows,
    and page renders no row cites."""
    f = []
    tc = "table_check.py"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        log = os.path.join(proj, "design", "decisions.md")
        clean = fread(log)
        expect_run(f, "decisions on the clean fixture", chk(ctx, tc, "decisions", "--project", proj), 0,
                   "decisions: 2; decided by user 1, coordinator 1, worker 0",
                   "decided on the user's behalf, not yet seen by the user: 0", "decisions: pass")
        # a worker's choice the user has not seen: listed by decisions and by summary, not failed
        fwrite(log, clean + DC_WORKER)
        expect_run(f, "decisions with a worker's choice not yet seen", chk(ctx, tc, "decisions", "--project", proj), 0,
                   "decided by user 1, coordinator 1, worker 1",
                   "not yet seen by the user: 1 (DC-003)", "decisions: pass")
        expect_run(f, "summary lists the unseen entry", chk(ctx, tc, "summary", "--project", proj), 0,
                   "decided on the user's behalf, not yet seen by the user: 1 (DC-003)")
        # seeded faults, each on the clean log plus the worker entry
        superseded = clean + DC_WORKER.replace("Status: in force", "Status: superseded by DC-004")
        faults = (
            ("missing field", (clean + DC_WORKER).replace("Options: the table (chosen); the front page\n", ""),
             "DC-003 (decisions.md line 23): no Options"),
            ("seen not said", (clean + DC_WORKER).replace("; seen by user: no", ""),
             "decided by the worker; say \"seen by user: yes\" or \"no\""),
            ("who unknown", (clean + DC_WORKER).replace("Decided by: worker", "Decided by: someone"),
             "Decided by 'someone BR-03-02; seen by user: no' must start with user, coordinator, worker"),
            ("old one-line form", clean + "\nDC-003 Use the table value\n", "DC-003 (decisions.md line 23): the one-line form"),
            ("an ID used twice", (clean + DC_WORKER).replace("(DC-003)", "(DC-001)"),
             "DC-001 (decisions.md line 23): ID used twice"),
            ("number below the last", (clean + DC_WORKER).replace("(DC-002)", "(DC-005)"),
             "DC-003 (decisions.md line 23): IDs rise in file order"),
            ("Replaces a missing ID", clean + DC_WORKER + "Replaces: DC-009\n",
             "DC-003 (decisions.md line 23): Replaces DC-009, which is not in the log"),
            ("old entry not marked superseded", clean + DC_WORKER + "Replaces: DC-001\n",
             "Replaces DC-001, but the Status of DC-001 does not say \"superseded by DC-003\""),
            ("superseded by a missing entry", superseded, "superseded by DC-004, which is not in the log"),
            ("bad kind and status", (clean + DC_WORKER).replace("Kind: decision\nDecided by: worker",
                                                                "Kind: guess\nDecided by: worker")
             .replace("Status: in force\n", "Status: maybe\n"), "Kind 'guess' is not one of"),
        )
        for name, text, want in faults:
            fwrite(log, text)
            expect_run(f, "decisions with the fault: %s" % name, chk(ctx, tc, "decisions", "--project", proj), 1, want)
        # a change of mind done right: the new entry replaces the old, the old says superseded by the new
        fwrite(log, clean.replace("Status: in force\n\n## Waive", "Status: superseded by DC-003\n\n## Waive", 1)
               + DC_WORKER + "Replaces: DC-001\n")
        expect_run(f, "decisions with a change of mind", chk(ctx, tc, "decisions", "--project", proj), 0,
                   "decisions: pass")
        fwrite(log, clean)
        expect_run(f, "all on the clean fixture runs decisions", chk(ctx, tc, "all", "--project", proj,
                                                                     "--today", "2026-01-10"), 0, "decisions: pass")
        # a pass's findings staging file: ids <perspective>-F<n>
        passes = os.path.join(proj, "design", "passes")
        os.makedirs(passes)
        fpath = os.path.join(passes, "BUCK-1_electrical_findings.csv")
        fhead = ",".join(ctx.h.TABLES["findings.csv"])
        good = ('electrical-F1,BR-03-02,3,risk,U1,"two current limits disagree",datasheet error,open,\n'
                'electrical-F2,BR-03-02,4,remark,U1,"a typo in the pin table",side remark,open,\n')
        fwrite(fpath, fhead + "\n" + good)
        expect_run(f, "staged findings, clean", chk(ctx, tc, "findings", "--project", proj, "--staged", fpath), 0,
                   "staged findings checked (before the merge): BUCK-1_electrical_findings.csv",
                   "staged findings: 2, of which violations: 0", "findings: pass")
        fwrite(fpath, fhead + "\n" + good.replace("electrical-F2", "FD-002").replace(",risk,", ",worry,"))
        expect_run(f, "staged findings with faults", chk(ctx, tc, "findings", "--project", proj, "--staged", fpath), 1,
                   "FD-002 (BUCK-1_electrical_findings.csv line 3): id must be a new electrical-F<n>",
                   "category 'worry'")
        fwrite(fpath, fhead + "\n" + good)
        expect_run(f, "compliance and findings given only a findings staging file",
                   chk(ctx, tc, "compliance", "findings", "--project", proj, "--staged", fpath), 0,
                   "findings: pass")
        shutil.rmtree(passes)
        # an empty capability table: listed in a plain run, a fail at the board checkpoint
        cap = os.path.join(proj, "design", "fab-capabilities.csv")
        full_cap = fread(cap)
        fwrite(cap, full_cap.splitlines()[0] + "\n")
        res = chk(ctx, tc, "fabcap", "--project", proj)
        expect_run(f, "fabcap header only, plain run", res, 0, "capability rows: 0",
                   "has no rows (header only): no capability is sourced; listed, not failed", "fabcap: pass")
        expect_run(f, "fabcap header only, board checkpoint", chk(ctx, tc, "fabcap", "--project", proj, "--stage", "ST11"),
                   1, "FAIL  design/fab-capabilities.csv has no rows (header only)")
        fwrite(cap, full_cap)
        # checklists listed in ID order, not file order
        rep = os.path.join(proj, "design", "reports", "BR-02-01.md")
        report = fread(rep)
        cl = os.path.join(proj, "design", "checklists", "board.md")
        checklist = fread(cl)
        fwrite(cl, checklist.replace("| BD-07 |", "| BD-09 |").replace("| SC-01 |", "| BD-08 |")
               .replace("| RM-01 | Antenna keep-out | module guide | ST8 | board_check.py | Radio |",
                        "| BD-10 | Antenna keep-out | module guide | ST8 | none | always |\n"
                        "| BD-02 | Mounting holes | mechanical drawing | ST8 | none | always |"))
        fwrite(rep, report.replace("Results: BD-07 met; SC-01 met", "Results: none yet"))
        res = chk(ctx, tc, "checklists", "--project", proj)
        order = [res[1].find("  %s (board.md)" % i) for i in ("BD-02", "BD-08", "BD-09", "BD-10")]
        expect_run(f, "checklists with four items open", res, 0, "  BD-02 (board.md): no result")
        expect(f, -1 not in order and order == sorted(order),
               "checklist items are not listed in ID order: %s" % res[1])
        fwrite(cl, checklist)
        fwrite(rep, report)
        # a calculation row closed without its script; a no-guidance row without evidence
        comp = os.path.join(proj, "design", "compliance.csv")
        rows = fread(comp)
        calc = ('DS-090,U1,BUCK-1,BUCK-1.pdf,A,8.2 Equation 3,9,,calculation,electrical,electrical,'
                '"Peak switch current against the lowest current limit",,,met,,,,"by hand",pass\n')
        silent = ('DS-091,U1,BUCK-1,BUCK-1.pdf,A,7.4,10,,recommend,layout,physical,'
                  '"no guidance found in BUCK-1.pdf: feedback trace near the switch node",,,carried,,,,,pass\n')
        fwrite(comp, rows + calc + silent)
        expect_run(f, "compliance with a calculation and a no-guidance row faulty", chk(ctx, tc, "compliance",
                                                                                         "--project", proj), 1,
                   "DS-090 (line 14): calculation row is met, but its evidence names no script in design/calcs/",
                   "DS-091 (line 15): a \"no guidance found\" row needs evidence")
        fwrite(comp, rows + calc.replace('"by hand"', '"design/calcs/peak_current.py pass"')
               + silent.replace(",,,,,pass", ",,,,\"read 7.4 and the evaluation guide; searched feedback\",pass"))
        expect_run(f, "the same rows with evidence", chk(ctx, tc, "compliance", "--project", proj), 0,
                   "compliance: pass")
        fwrite(comp, rows)
        # page renders no row cites are listed, never failed
        fwrite(os.path.join(proj, "design", "renders", "BUCK-1_p3.png"), "")
        expect_run(f, "compliance lists a render no row cites", chk(ctx, tc, "compliance", "--project", proj), 0,
                   "page renders no figure or graph row cites (the merge deletes them; listed, not failed): 1",
                   "compliance: pass")
    return f


def test_check_hb7_scripts(ctx):
    """The scan passes the skill's own scripts as copied into a project, and still finds a secret seeded
    into one of them; the protection walk lists pulls; net_length and ref_plane say no track."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        scripts = os.path.join(proj, SK)
        shutil.rmtree(scripts)
        os.makedirs(scripts)
        shipped = sorted(n for n in os.listdir(ctx.scripts) if os.path.isfile(os.path.join(ctx.scripts, n)))
        for n in shipped:
            shutil.copy(os.path.join(ctx.scripts, n), os.path.join(scripts, n))
        res = chk(ctx, "table_check.py", "scan", scripts, "--project", proj)
        expect_run(f, "scan of the skill's own scripts", res, 0, "scanned the files named: %d files" % len(shipped),
                   "findings 0")
        seeded = os.path.join(scripts, "hwcommon.py")
        body = fread(seeded)
        fwrite(seeded, body + 'API_KEY = "' + "Zq8" + "rT2vLm9xP" + '"\n')
        res = chk(ctx, "table_check.py", "scan", scripts, "--project", proj)
        expect_run(f, "scan with a secret seeded into a script copy", res, 1,
                   "hwcommon.py:%d: password or token" % (body.count("\n") + 1), "findings 1")
        expect(f, "rT2vLm9xP" not in res[1], "the seeded secret was printed in full")
        # the protection walk: a pull-up and a pull-down on connector nets are pulls, not series parts
        net_path = os.path.join(proj, "hardware", "check.net")
        text = fread(net_path)
        for ref, pin, old, new in (("R6", "2", "/SCL", "/SWDIO"), ("R4", "1", "/BOOST_EN", "/SWCLK")):
            node = '(node (ref "%s") (pin "%s") (pinfunction "") (pintype "passive"))' % (ref, pin)
            if not expect(f, node in text, "fixture netlist lacks %s" % node):
                return f
            text = text.replace(" " + node, "", 1)
            head = '(name "%s") (class "Default") ' % new
            text = text.replace(head, head + node + " ", 1)
        fwrite(net_path, text)
        res = chk(ctx, "sch_check.py", "protect", "--project", proj)
        expect_run(f, "protect with a pull-up and a pull-down on the debug header", res, 0,
                   "J2.2: net /SWDIO; series: none; pulls: R6 to +3V3; protection: NONE; reaches: U2.8 [",
                   "J2.3: net /SWCLK; series: none; pulls: R4 to GND; protection: NONE; reaches: U2.9")
        # net_length and ref_plane on a net with no track: not measured, never a pass
        p = ["--project", proj, "--no-repour"]
        for check, objects in (("net_length", "/SCL"), ("ref_plane", "/SCL; plane:GND on B.Cu")):
            res = chk(ctx, "board_check.py", check, "--objects", objects, "--limit", "20", *p)
            expect_run(f, "%s on a net with no track" % check, res, 0, "NO TRACK (not measured) ad hoc %s" % check,
                       "/SCL: no track (not routed yet): not measured", "1 not measured (no track)")
            expect(f, "PASS" not in res[1], "%s passed a net with no track" % check)
        res = chk(ctx, "board_check.py", "net_length", "--objects", "/SWDIO; /SCL", "--limit", "5", *p)
        expect_run(f, "net_length with one net too long and one with no track", res, 1, "FAIL ad hoc net_length",
                   "TOO LONG", "/SCL: no track")
        expect_run(f, "the table-driven run still passes on the routed nets", chk(ctx, "board_check.py", *p), 0,
                   "board_check: 12 passed, 0 failed, 0 waived\n")
    return f


PRIORITY_ROW = ('DS-030,U1,BUCK-1,BUCK-1.pdf,A,8 Typical application,12,,must,electrical,electrical,'
                '"Fit a bootstrap capacitor",,,open,,,,,pass\n')
PACKAGE_ROW = ('DS-031,U1,BUCK-1,BUCK-1.pdf,A,10 Package,14,,must,package,physical,'
               '"The exposed pad must be soldered to the board",,,open,,,,,pass\n')
ASSEMBLY_ROW = ('DS-032,U1,BUCK-1,BUCK-1.pdf,A,11 Assembly,15,,must,assembly,physical,'
                '"Bake the part before reflow if it was exposed too long",,,open,,,,,pass\n')
DATA_ROW = ('DS-033,U1,BUCK-1,BUCK-1.pdf,A,10 Package,14,,data,package,physical,'
            '"Exposed pad 1.6 mm square",,,open,,,,,pass\n')


def test_priority_tables(ctx):
    """HB-7 priority items in table_check, each with a seeded fault: open must and hard rows (1), package
    and assembly rows closing later and the data kind (16), header-only tables (6), a not-met board review
    verdict (2), a constraint changed since its sufficiency review (3), the fabrication and repository
    checklists counted and an "all" stage (4), stale rows about another part and "U1;R3" (9), a missing
    stock date and several packs (11), the CSV error cause (10)."""
    f = []
    tc = "table_check.py"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        p = ["--project", proj]
        design = os.path.join(proj, "design")
        comp = os.path.join(design, "compliance.csv")
        base = fread(comp)
        # 1: an open must row: listed in an ordinary run, a fail at the schematic checkpoint, covered by a DC-
        fwrite(comp, base + PRIORITY_ROW)
        plain = chk(ctx, tc, "compliance", *p)
        expect_run(f, "an open must row, ordinary run", plain, 0, "open must and hard rows",
                   "must row (electrical, U1) is open, with no result and no DC- decision (closes by ST6)",
                   "compliance: pass")
        expect_run(f, "an open must row at the schematic checkpoint", chk(ctx, tc, "compliance", *p, "--stage", "ST6"), 1,
                   "FAIL  DS-030 (line 14): must row (electrical, U1) is open")
        fwrite(comp, base + PRIORITY_ROW.replace(",open,,,,,pass", ",open,,DC-001,,,pass"))
        expect_run(f, "an open must row covered by a decision", chk(ctx, tc, "compliance", *p, "--stage", "ST6"), 0,
                   "compliance: pass")
        # 16: package rows close at the board checkpoint, assembly rows with the order files; kind data
        fwrite(comp, base + PACKAGE_ROW + ASSEMBLY_ROW + DATA_ROW)
        expect_run(f, "package and assembly rows at the schematic checkpoint",
                   chk(ctx, tc, "compliance", *p, "--stage", "ST6"), 0, "(closes by ST11)", "(closes by ST12)",
                   "compliance: pass")
        res = chk(ctx, tc, "compliance", *p, "--stage", "ST11")
        expect_run(f, "package row at the board checkpoint", res, 1, "FAIL  DS-031", "(closes by ST12)")
        expect(f, "FAIL  DS-032" not in res[1] and "DS-033" not in res[1],
               "an assembly row failed before ST12, or a data row was counted as must: %s" % res[1][-600:])
        expect_run(f, "assembly row before ordering", chk(ctx, tc, "compliance", *p, "--stage", "ST12"), 1,
                   "FAIL  DS-032")
        # 6: header-only compliance and sections tables
        head = base.splitlines()[0] + "\n"
        sec = os.path.join(design, "sections.csv")
        sec_base = fread(sec)
        fwrite(comp, head)
        fwrite(sec, sec_base.splitlines()[0] + "\n")
        expect_run(f, "header-only tables, ordinary run", chk(ctx, tc, "compliance", "sections", *p), 0,
                   "design/compliance.csv has no rows (header only)", "design/sections.csv has no rows (header only)",
                   "listed, a fail from the schematic checkpoint")
        expect_run(f, "header-only tables at the schematic checkpoint",
                   chk(ctx, tc, "compliance", "sections", *p, "--stage", "ST6"), 1,
                   "FAIL  design/compliance.csv has no rows", "FAIL  design/sections.csv has no rows")
        fwrite(comp, base)
        fwrite(sec, sec_base)
        # 2: a board review verdict "not met" is a violation unless a decision covers it
        rep = os.path.join(design, "reports", "BR-02-01.md")
        rep_base = fread(rep)
        fwrite(rep, rep_base.replace("CN-014 met:", "CN-014 not met:"))
        expect_run(f, "a not-met verdict with no decision", chk(ctx, tc, "constraints", *p), 1,
                   "CN-014 (line 15): violation: board review BR-02-01 says not met")
        fwrite(rep, rep_base.replace("CN-014 met:", "CN-014 not met (DC-002):"))
        expect_run(f, "a not-met verdict under a decision", chk(ctx, tc, "constraints", *p), 0,
                   "CN-014: not met in BR-02-01, covered by DC-002", "constraints: pass")
        fwrite(rep, rep_base.replace("CN-014 met:", "CN-014 cannot tell:"))
        expect_run(f, "a cannot-tell verdict, ordinary run", chk(ctx, tc, "constraints", *p), 0,
                   "says cannot tell, with no DC- decision; a fail from the board checkpoint")
        fwrite(rep, rep_base)
        # 3: a limit loosened after the sufficiency review
        expect_run(f, "constraints with no baseline", chk(ctx, tc, "constraints", *p), 0,
                   "no sufficiency-review baseline (design/constraints-reviewed.csv)")
        expect_run(f, "record the sufficiency baseline", chk(ctx, tc, "constraints", *p, "--record-review", "BR-01-01",
                                                             "--today", "2026-01-10"), 0,
                   "sufficiency baseline recorded for BR-01-01: 14 constraints")
        cons = os.path.join(design, "constraints.csv")
        cons_base = fread(cons)
        fwrite(cons, cons_base.replace("CN-005,DS-013,distance,\"U1.1; C1.1\",5,", "CN-005,DS-013,distance,\"U1.1; C1.1\",8,"))
        expect_run(f, "a loosened limit, ordinary run", chk(ctx, tc, "constraints", *p), 0,
                   "CN-005 changed since sufficiency review BR-01-01: limit '5' -> '8'; no DC- decision in its note")
        expect_run(f, "a loosened limit at the board rules checkpoint", chk(ctx, tc, "constraints", *p, "--stage", "ST7"),
                   1, "FAIL  CN-005 changed since sufficiency review BR-01-01")
        fwrite(cons, fread(cons).replace(",datasheet,\nCN-006", ",datasheet,DC-002 widened\nCN-006"))
        expect_run(f, "a loosened limit under a decision", chk(ctx, tc, "constraints", *p, "--stage", "ST7"), 0,
                   "(under DC-002)", "constraints: pass")
        fwrite(cons, cons_base)
        # 4: the fabrication and repository checklists are copied and counted; a stage cell "all"
        cl = os.path.join(design, "checklists")
        for name in ("checklist-fabrication.md", "checklist-repository.md", "checklist-logical.md"):
            shutil.copy(os.path.join(ctx.root, "skills", "hw-worker", "references", name),
                        os.path.join(cl, name[len("checklist-"):]))
        res = chk(ctx, tc, "checklists", *p, "--stage", "ST12")
        for iid in ("FB-01 (fabrication.md)", "PB-05 (repository.md)", "LG-08 (logical.md)"):
            expect(f, iid in res[1], "checklists at ST12 does not count %s: %s" % (iid, res[1][-800:]))
        res = chk(ctx, tc, "checklists", *p, "--stage", "ST1")
        expect(f, "LG-08 (logical.md)" in res[1] and "FB-01" not in res[1],
               "an 'all' item is skipped, or a ST12 item counted, at ST1: %s" % res[1][-800:])
        # 9: stale: rows about an external part taken from another part's datasheet, and "U1;R3"
        fwrite(comp, base + 'DS-040,R3,BUCK-1,BUCK-1.pdf,A,8 Typical application,12,,recommend,external-component,'
               'electrical,"Pull EN up to VIN",100k,,met,,,,,pass\n'
               'DS-041,U1;R3,BUCK-1,BUCK-1.pdf,A,8 Typical application,12,,recommend,external-component,'
               'electrical,"EN pull-up value",100k,,met,,,,,pass\n')
        expect_run(f, "stale with rows about another part", chk(ctx, tc, "stale", *p), 0,
                   "compliance rows about another part, taken from a fitted part's datasheet: 2", "stale: pass")
        fwrite(comp, base + 'DS-042,U1;R3,BUCK-2,BUCK-2.pdf,A,8,12,,recommend,external-component,electrical,'
               '"EN pull-up value",100k,,met,,,,,pass\n')
        expect_run(f, "stale with a part no longer fitted", chk(ctx, tc, "stale", *p), 1,
                   "compliance.csv DS-042: taken from BUCK-2, but U1 is now BUCK-1, and BUCK-2 is not fitted",
                   "compliance.csv DS-042: taken from BUCK-2, but R3 is now RES-100K-0603")
        fwrite(comp, base)
        # 11: a missing stock date fails only from the schematic checkpoint; a part in several packs
        parts = os.path.join(design, "parts.csv")
        parts_base = fread(parts)
        fwrite(parts, parts_base.replace("R2,22k,fixture:R_0603,0603,Maker A,RES-22K-0603,SUPPLIER-A,SA-1022,other,,,1%,"
                                         "50 V,0.01,0.005,1000,2026-01-02,", "R2,22k,fixture:R_0603,0603,Maker A,"
                                         "RES-22K-0603,SUPPLIER-A,SA-1022,other,,,1%,50 V,0.01,0.005,1000,,"))
        plain = chk(ctx, tc, "parts", *p, "--today", "2026-01-10")
        expect_run(f, "no stock date, ordinary run", plain, 0, "R2 (RES-22K-0603): stock and price have no checked date; "
                   "a fail from the schematic checkpoint", "parts: pass")
        expect_run(f, "no stock date at the schematic checkpoint",
                   chk(ctx, tc, "parts", *p, "--today", "2026-01-10", "--stage", "ST6"), 1,
                   "FAIL  R2 (RES-22K-0603): stock and price have no checked date")
        fwrite(parts, parts_base.replace(",other,microcontroller,", ",other,microcontroller;switching converter,"))
        expect_run(f, "a part in two packs", chk(ctx, tc, "packs", *p), 0, "packs: pass")
        fwrite(parts, parts_base.replace(",other,microcontroller,", ",other,microcontroller;radio,"))
        expect_run(f, "a part in a pack that is off", chk(ctx, tc, "packs", *p), 1,
                   "category radio switches pack")
        fwrite(parts, parts_base)
        # 10: the CSV error names the likely cause
        fwrite(comp, base + 'DS-050,U1,BUCK-1,BUCK-1.pdf,A,8,12,,should,electrical,electrical,Keep it short, and wide,'
               ',,open,,,,,pass\n')
        expect_run(f, "an unquoted comma", chk(ctx, tc, "compliance", *p), 2,
                   "likely an unquoted comma inside a value: put that value in double quotes")
        fwrite(comp, base)
    return f


def add_pad(text, ref_pad_line, extra):
    """Put `extra` (a pad line) after the line of the board text that starts with ref_pad_line."""
    i = text.index(ref_pad_line)
    j = text.index("\n", i) + 1
    return text[:j] + extra + text[j:]


EP_LINE = '    (pad "3" smd rect (at 0 0) (size 1.6 1.6)'


def test_priority_board_pads(ctx):
    """HB-7 item 8: same_island and single_point read every pad with a number, not only the first."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        p = ["--project", proj, "--no-repour"]
        pcb = os.path.join(proj, "hardware", "check.kicad_pcb")
        base = fread(pcb)
        if not expect(f, EP_LINE in base, "the fixture's U1 exposed pad line is not in the board"):
            return f
        via = ('  (via (at 110 111.6) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "GND") '
               '(uuid "00000000-0000-4000-8000-00000000a001"))\n')
        # a second copy of pad 3 off the ground island: same_island must see it
        fwrite(pcb, add_pad(base, EP_LINE, '    (pad "3" smd rect (at 0 -3) (size 1 1) (layers "F.Cu" "F.Mask" "F.Paste") '
                                           '(net "GND") (uuid "00000000-0000-4000-8000-00000000a002"))\n'))
        expect_run(f, "same_island with a pad 3 copy off the island", chk(ctx, "board_check.py", "same_island", *p), 1,
                   "2 pieces on F.Cu")
        # a via in a second copy of pad 3: inside the pad for single_point (in:U1.3)
        fwrite(pcb, base.replace("  (zone ", via + "  (zone ", 1))
        expect_run(f, "single_point with a via outside the one pad 3", chk(ctx, "board_check.py", "single_point", *p),
                   1, "joins outside U1.3")
        fwrite(pcb, add_pad(base, EP_LINE, '    (pad "3" smd rect (at 0 1.6) (size 1 1) (layers "F.Cu" "F.Mask" "F.Paste") '
                                           '(net "GND") (uuid "00000000-0000-4000-8000-00000000a003"))\n')
               .replace("  (zone ", via + "  (zone ", 1))
        expect_run(f, "single_point with the via in a second pad 3", chk(ctx, "board_check.py", "single_point", *p), 0,
                   "every join is inside U1.3")
        expect_run(f, "same_island with the second pad 3 on the island", chk(ctx, "board_check.py", "same_island", *p),
                   0, "share one GND island on F.Cu")
    return f


PRIORITY_SHADOW = r'''
import os, sys
sys.path.insert(0, sys.argv[1])          # a folder of the project's own modules, same names
import project_settings, hwcommon
assert getattr(project_settings, "OWN", False) and getattr(hwcommon, "OWN", False)
sys.path.insert(0, sys.argv[2])          # the skill's folder
import schlib
print("schlib uses", os.path.basename(os.path.dirname(schlib.project_settings.__file__)),
      os.path.basename(os.path.dirname(schlib.hwcommon.__file__)), "own" if getattr(schlib.hwcommon, "OWN", False) else "skill")
'''


def test_priority_build(ctx):
    """HB-7 items 7, 12 and 18: a failed generator run records its output, the sandbox failure text is
    shown, the copy into hwskills/ never overwrites, the libraries import their own siblings, and fab.py
    warns about placeholder supplier part numbers."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_project(os.path.join(tmp, "p"))
        if not expect_run(f, "first build sch", build_run(proj, "sch"), 0, "done: sch"):
            return f
        gen = os.path.join(proj, "scripts", "gen_sch.py")
        gen_base = fread(gen)
        parts = os.path.join(proj, "design", "parts.csv")
        # 7: the generator writes, then fails: its output is recorded, and the next run is not blocked
        fwrite(gen, gen_base + 'raise SystemExit("seeded failure after the files were written")\n')
        fwrite(parts, fread(parts).replace("HDR-1X02,", "HDR-1X02-B,"))
        expect_run(f, "a generator that fails after writing", build_run(proj, "sch"), 1,
                   "the generator failed, but the files it wrote are its output and are recorded")
        fwrite(gen, gen_base)
        expect_run(f, "the next run after a failed one", build_run(proj, "sch"), 0, "done: sch")
        # 7: a hand edit while the generator fails: the temporary-copy run shows why it failed
        sch = os.path.join(proj, SCH)
        fwrite(sch, fread(sch).replace('(property "Value" "10k"', '(property "Value" "22k"', 1))
        fwrite(gen, gen_base.replace("import fixture_parts as fx", 'raise SystemExit("seeded failure before writing")\n'
                                     "import fixture_parts as fx", 1))
        expect_run(f, "a hand edit with a failing generator", build_run(proj, "sch"), 3, "NOT WRITTEN",
                   "the generator failed in the temporary copy (exit code 1)", "seeded failure before writing")
        fwrite(gen, gen_base)
        # 18: --copy-skill-scripts writes into hwskills/ and never overwrites
        fresh = os.path.join(tmp, "fresh")
        os.makedirs(fresh)
        skill_build = os.path.join(ctx.scripts, "build.py")
        expect_run(f, "copy the skill scripts into a new project", run([sys.executable, skill_build,
                                                                        "--copy-skill-scripts", fresh]), 0,
                   "skill scripts into hwskills/")
        expect(f, os.path.isfile(os.path.join(fresh, "hwskills", "build.py")) and
               not os.path.exists(os.path.join(fresh, "build.py")), "the copy did not land in hwskills/ only")
        clash = os.path.join(tmp, "clash")
        os.makedirs(os.path.join(clash, "hwskills"))
        fwrite(os.path.join(clash, "hwskills", "project_settings.py"), "OWN = True\n")
        expect_run(f, "copy onto a project file of the same name", run([sys.executable, skill_build,
                                                                        "--copy-skill-scripts", clash]), 2,
                   "NOT COPIED", "hwskills/project_settings.py")
        expect(f, fread(os.path.join(clash, "hwskills", "project_settings.py")) == "OWN = True\n" and
               os.listdir(os.path.join(clash, "hwskills")) == ["project_settings.py"],
               "a refused copy changed or added files")
        # 18: the libraries import their own siblings, whatever the project's modules of the same name
        own = os.path.join(tmp, "own")
        os.makedirs(own)
        for n in ("project_settings.py", "hwcommon.py"):
            fwrite(os.path.join(own, n), "OWN = True\n")
        probe = os.path.join(tmp, "probe.py")
        fwrite(probe, PRIORITY_SHADOW)
        expect_run(f, "schlib beside the project's own modules", run([sys.executable, probe, own, ctx.scripts]), 0,
                   "schlib uses scripts scripts skill")
    # 12: placeholder supplier part numbers stay out of the assembler BOM, with a reason
    fab = ctx.module("fab", "fab_under_test")
    src = {"Manufacturer": "Maker A", "MPN": "RES-10K-0603", "Supplier": "SUPPLIER-A", "Supplier PN": "TBD"}
    board = fab_board({"R2": {"fields": src}})
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "parts.csv")
        fwrite(p, ctx.fx.PARTS_CSV)
        rows = ctx.h.read_table(p)
    pair = [r for r in rows if r["refs"] == "R1;R2"][0]
    rows = [r for r in rows if r is not pair] + [dict(pair, refs="R1"), dict(pair, refs="R2", supplier_pn="TBD")]
    parts, _, _ = fab.collect_parts(board, rows, None)
    texts = fab.assembler_files(board, parts, "SUPPLIER-A")
    bom = texts["assembler_bom.csv"]
    expect(f, "TBD" not in bom and '"R1,R2"' not in bom, "a placeholder part number went into the assembler BOM: %s" % bom)
    expect(f, "supplier part number 'TBD' is not a part number" in texts["assembler_not_fitted.csv"],
           "the placeholder is not listed with its reason: %s" % texts["assembler_not_fitted.csv"])
    expect(f, [fab.placeholder_pn(v) for v in ("TBD", "C137763", "not checked", "SA-1001?", "")] ==
           [True, False, True, True, False], "placeholder_pn misreads a value")
    return f


SCRIPT_TESTS += [
    ("HB-7 priority: open must rows, verdicts, baseline, checklists, stale, parts, header-only tables",
     test_priority_tables),
    ("HB-7 priority: board_check reads every pad with a number", test_priority_board_pads),
    ("HB-7 priority: failed generator runs, copy into hwskills/, sibling imports, placeholder part numbers",
     test_priority_build),
]


SCRIPT_TESTS += [
    ("adoption: KiCad files in the root or another folder, recorded and found by every check", test_adopt_own_layout),
    ("table_check: checklists, missing tables, KiCad's severities, impact, writers, staged passes",
     test_check_hb7_tables),
    ("scan of the skill's own scripts, protection-walk pulls, net checks with no track", test_check_hb7_scripts),
    ("table_check: decision log, staged findings, empty capability table, checklist order, calculation rows",
     test_check_decision_log),
]
# ======================================================================== end of HB-7 section


# ======================================================================== faults met in use
# Each test plants one fault a project met while it used the scripts, and fails if the script lets it by.

def test_profile_rows(ctx):
    """table_check: a board-profile row the reader cannot read is listed and fails. It is never dropped."""
    f = []
    tc = "table_check.py"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        req = os.path.join(proj, "design", "requirements.md")
        clean = fread(req)
        fwrite(req, clean.replace("- Radio; off; user answer",
                                  "- Radio; on, to confirm; user answer\n- Wireless link; on; user answer\n"
                                  "- USB; maybe; user answer\n- Ethernet"))
        for cmd in ("packs", "checklists"):
            res = chk(ctx, tc, cmd, "--project", proj)
            expect_run(f, "%s with four board-profile rows it cannot read" % cmd, res, 1,
                       "board profile rows not read: 4",
                       "FAIL  design/requirements.md line 16: board profile row \"Radio; on, to confirm; user answer\": "
                       "state 'on, to confirm' must be on or off alone",
                       "line 17: board profile row \"Wireless link; on; user answer\": 'Wireless link' is not a switch",
                       "line 18: board profile row \"USB; maybe; user answer\": state 'maybe' must be on or off alone",
                       "line 19: board profile row \"Ethernet\": no state")
        # the row form as a table, with a header and a rule line, and a full stop after the state: all read
        fwrite(req, clean.replace("- Switching converter; on; part choice (U1, U3)\n- Microcontroller; on; part choice (U2)\n"
                                  "- Radio; off; user answer\n",
                                  "Switches not named here are off.\n| Switch | State | Reason |\n|---|---|---|\n"
                                  "| Switching converter | on | part choice (U1, U3) |\n"
                                  "| Microcontroller | On. | part choice (U2) |\n| Radio | off | user answer |\n"))
        expect_run(f, "packs with the profile as a table", chk(ctx, tc, "packs", "--project", proj), 0,
                   "switches on in the board profile: Microcontroller, Switching converter", "packs: pass")
    return f


def test_scan_nothing(ctx):
    """table_check scan: a scan that read no file is a fail, never a pass."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        try:
            made = subprocess.run(["git", "-C", proj, "init", "-q"], capture_output=True).returncode == 0
        except OSError:
            made = False
        if not made:
            raise Skip("git is not here to make a repository with nothing in it")
        # a repository before its first commit: nothing staged, nothing tracked
        expect_run(f, "scan of a repository with nothing staged or tracked",
                   chk(ctx, "table_check.py", "scan", "--project", proj), 1, "no file was scanned", "scan: FAIL")
        empty = os.path.join(proj, "empty")
        os.makedirs(empty)
        expect_run(f, "scan of an empty folder", chk(ctx, "table_check.py", "scan", empty, "--project", proj), 1,
                   "no file was scanned")
    return f


def test_scan_published(ctx):
    """table_check scan: an address a maker printed in a saved document is counted apart and does not fail.
    Everything else in that folder still fails, and so does an address in the project's own list there."""
    f = []
    tc = "table_check.py"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        ds = os.path.join(proj, "datasheets")
        os.makedirs(ds, exist_ok=True)
        sales = "sales" + "@" + "maker.example"
        fwrite(os.path.join(ds, "PART-A.txt"), "PART-A step-down converter\nContact %s or support%s\n"
               % (sales, "@" + "maker.example"))
        fwrite(os.path.join(ds, "README.md"), "PART-A.txt: PART-A, Maker, rev C\n")
        res = chk(ctx, tc, "scan", ds, "--project", proj)
        expect_run(f, "scan of a datasheet text with the maker's addresses", res, 0, "findings 0",
                   "in published documents (datasheets/), not counted: 2 email addresses",
                   "datasheets/PART-A.txt: 2")
        expect(f, sales not in res[1], "the scan printed a maker's address in full")
        fwrite(os.path.join(proj, "design", ".private-terms"), "Clientco\n")
        fwrite(os.path.join(ds, "PART-A.txt"), "PART-A step-down converter\nContact %s\nmarked up for Clientco\n" % sales)
        expect_run(f, "a private term in a datasheet text", chk(ctx, tc, "scan", ds, "--project", proj), 1,
                   "FOUND datasheets/PART-A.txt:3: private term", "findings 1", "not counted: 1 email address")
        fwrite(os.path.join(ds, "PART-A.txt"), "PART-A step-down converter\n")
        fwrite(os.path.join(ds, "README.md"), "PART-A.txt: PART-A, Maker, rev C, sent by %s\n" % sales)
        expect_run(f, "an address in the datasheet list the project writes", chk(ctx, tc, "scan", ds, "--project", proj),
                   1, "FOUND datasheets/README.md:1: email address")
    return f


def test_scan_reviewed(ctx):
    """table_check scan: a hit a person accepted is recorded once and does not fail again. A row with no
    reason or no name, and a row that matches nothing, fail."""
    f = []
    tc = "table_check.py"
    head = "file,line,kind,reason,decided_by\n"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        out_dir = os.path.join(proj, "out")
        os.makedirs(out_dir)
        temp = "/" + "var/folders/" + "ab/cdef0123/T/run-1"
        fwrite(os.path.join(out_dir, "notes.txt"), "first line\nthe tool wrote to %s once\n" % temp)
        args = ("scan", out_dir, "--project", proj)
        expect_run(f, "scan with one hit", chk(ctx, tc, *args), 1, "FOUND out/notes.txt:2: machine path", "findings 1")
        rev = os.path.join(proj, "design", "scan-reviewed.csv")
        fwrite(rev, head + "out/notes.txt,2,machine path,a system folder with no user name in it,user\n")
        expect_run(f, "the same hit, reviewed", chk(ctx, tc, *args), 0, "findings 0", "reviewed and accepted: 1",
                   "REVIEWED out/notes.txt:2: machine path (a system folder with no user name in it; decided by user)")
        fwrite(os.path.join(out_dir, "notes.txt"), "first line\nthe tool wrote to %s once\nand to %s\n" % (temp, temp))
        expect_run(f, "a second hit on another line", chk(ctx, tc, *args), 1, "FOUND out/notes.txt:3: machine path",
                   "findings 1", "reviewed and accepted: 1")
        fwrite(os.path.join(out_dir, "notes.txt"), "first line\nthe tool wrote to %s once\n" % temp)
        fwrite(rev, head + "out/notes.txt,2,machine path,,user\n")
        expect_run(f, "a reviewed row with no reason", chk(ctx, tc, *args), 1, "scan-reviewed.csv line 2",
                   "needs a reason and who decided", "FOUND out/notes.txt:2: machine path")
        fwrite(rev, head + "out/notes.txt,2,machine path,a system folder,user\n"
               "out/notes.txt,1,machine path,a system folder,user\n")
        expect_run(f, "a reviewed row that matches nothing", chk(ctx, tc, *args), 1, "scan-reviewed.csv line 3",
                   "nothing is found there now")
    return f


def test_checklist_result_form(ctx):
    """table_check checklists: an item has a result only when a report gives it in the result form. A report
    that names the item for another reason does not answer it."""
    f = []
    tc = "table_check.py"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        rep = os.path.join(proj, "design", "reports", "BR-02-01.md")
        clean = fread(rep)
        given = "Results: BD-07 met; SC-01 met"
        expect(f, given in clean, "the fixture report no longer holds %r" % given)
        for what, line in (("a list of the items a pack brings in", "Results: BD-07 met\nThe pack brings in SC-01."),
                           ("an item proposed, with no result", "Results: BD-07 met\nPropose SC-01 for the next review."),
                           ("a result word before the ID", "Results: BD-07 met\nnot met by anything yet: SC-01")):
            fwrite(rep, clean.replace(given, line))
            expect_run(f, "checklists with %s" % what, chk(ctx, tc, "checklists", "--project", proj, "--stage", "ST11"),
                       1, "with no result yet: 1", "FAIL  SC-01 (board.md): no result in any review report")
        for what, line in (("ID, colon, result", "BD-07: met\nSC-01: does not apply (no converter on this board)"),
                           ("ID in bold", "**BD-07** met\n- **SC-01**: cannot tell (needs the board file)"),
                           ("IDs sharing one result", "BD-07, SC-01: met"),
                           ("a note in brackets after the ID", "BD-07 (decoupling) met; SC-01 (switch node): not met"),
                           ("a table row", "| Item | Result | Evidence |\n|---|---|---|\n| BD-07 | met | C1 at U1 |\n"
                                           "| SC-01 | Not met | loop area |")):
            fwrite(rep, clean.replace(given, line))
            expect_run(f, "checklists with %s" % what, chk(ctx, tc, "checklists", "--project", proj, "--stage", "ST11"),
                       0, "with no result yet: 0")
    return f


FINDINGS_HEAD = "id,report,severity,category,location,text,source,status,decision\n"


def test_findings_open(ctx):
    """table_check: a status that starts with "open" is open, whatever follows it. An open row is not
    counted as triaged, and the summary names an open violation by its whole ID."""
    f = []
    tc = "table_check.py"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        fwrite(os.path.join(proj, "design", "findings.csv"), FINDINGS_HEAD
               + 'FD-001,BR-02-01,4,remark,U4,"label the sensor port",reviewer side remark,open,\n'
               'FD-002,BR-02-01,1,violation,U1: pin 3,"the enable pin floats",board review,open; waits on the new part,\n'
               'FD-003,BR-02-01,1,violation,U1: pin 5,"the feedback trace is long",board review,Open,\n'
               'FD-004,BR-02-01,2,risk,C1,"little margin on the rating",board review,fixed (build 3),\n')
        expect_run(f, "findings with an open violation that carries a note",
                   chk(ctx, tc, "findings", "--project", proj), 0, "open violations: 2",
                   "  FD-002 (U1: pin 3): the enable pin floats", "open findings: 3 of 4")
        res = chk(ctx, tc, "summary", "--project", proj)
        expect_run(f, "summary with open rows", res, 0, "open violations: 2 (FD-002; FD-003)",
                   "findings triaged 1 of 4; findings still open 3 of 4")
    return f


def test_findings_form(ctx):
    """table_check findings: a severity or category outside the set fails. The summary counts as extraction
    misses only the rows that name a part, and lists the others."""
    f = []
    tc = "table_check.py"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        fd = os.path.join(proj, "design", "findings.csv")
        fwrite(fd, FINDINGS_HEAD
               + 'FD-001,BR-02-01,5,remark,U4,"label the sensor port",reviewer side remark,open,\n'
               'FD-002,BR-02-01,2,gap,U1,"no test point on the output",board review,open,\n'
               'FD-003,BR-02-01,2,Risk,C1,"little margin on the rating",board review,open,\n')
        expect_run(f, "findings with a severity and two categories outside the set",
                   chk(ctx, tc, "findings", "--project", proj), 1, "FD-001 (line 2): severity '5' must be 1 to 4",
                   "FD-002 (line 3): category 'gap'", "FD-003 (line 4): category 'Risk'", "findings: FAIL (3)")
        fwrite(fd, FINDINGS_HEAD
               + 'FD-001,BR-02-01,2,extraction miss,U1,"the note on page 9 has no DS row",blind review,rows added,\n'
               'FD-002,BR-02-01,2,extraction miss,CAP-10U-1206,"the derating figure has no DS row",blind review,open,\n'
               'FD-003,BR-02-01,3,extraction miss,requirements.md,"the storage range is not asked",review,open,\n')
        expect_run(f, "summary with an extraction miss that names no part", chk(ctx, tc, "summary", "--project", proj), 0,
                   "extraction misses found: 2 (rows of that category that name no part or datasheet: 1: FD-003)")
    return f


def test_summary_sections(ctx):
    """table_check summary: the requirements sections are found when the file is tidied (headings one level
    down, or numbered), and a section that is missing or empty is named."""
    f = []
    tc = "table_check.py"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        req = os.path.join(proj, "design", "requirements.md")
        clean = fread(req)
        expect_run(f, "summary on the clean fixture", chk(ctx, tc, "summary", "--project", proj), 0,
                   "requirements sections filled 5 of 5")
        tidy = clean
        for n, head in enumerate(("Environment profile", "Misuse cases", "User journey", "Board profile", "Test points"), 3):
            tidy = tidy.replace("## %s\n" % head, "### %d. %s\n" % (n, head))
        tidy = tidy.replace("### 3. Environment", "## Requirements in force\n### 3. Environment")
        fwrite(req, tidy + "## History\nOlder text is in design/requirements-history.md.\n")
        expect_run(f, "summary with the sections one level down and numbered",
                   chk(ctx, tc, "summary", "--project", proj), 0, "requirements sections filled 5 of 5")
        fwrite(req, clean.replace("## Test points\n- +3V3: bench\n", "").replace("power up: FR-01\n", ""))
        expect_run(f, "summary with one section missing and one empty", chk(ctx, tc, "summary", "--project", proj), 0,
                   "requirements sections filled 3 of 5 (not found: Test points; empty: User journey)")
    return f


def test_summary_withdrawn(ctx):
    """table_check summary: a withdrawn requirement keeps its ID, names its decision, and is counted apart
    from the items that still wait for evidence."""
    f = []
    tc = "table_check.py"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        req = os.path.join(proj, "design", "requirements.md")
        clean = fread(req)
        expect_run(f, "summary on the clean fixture", chk(ctx, tc, "summary", "--project", proj), 0,
                   "requirements: FR- 1 of 1 with evidence; QC- 0 of 1 with results\n")
        fwrite(req, clean.replace("## Quality characteristics\n",
                                  "FR-02 Withdrawn (DC-002): drive a relay. Source: user.\n"
                                  "FR-03 Withdrawn: a second output. Source: user.\n"
                                  "## Quality characteristics\nQC-02 withdrawn (DC-002): mass under 20 g. Source: user.\n"))
        expect_run(f, "summary with withdrawn items", chk(ctx, tc, "summary", "--project", proj), 0,
                   "requirements: FR- 1 of 2 with evidence; QC- 0 of 1 with results; withdrawn: FR-02, QC-02; "
                   "marked withdrawn with no DC- decision (still counted): FR-03\n")
    return f


def test_decisions_ended(ctx):
    """table_check decisions: one entry replaces several; an entry a later one ends without replacing it is
    "closed (how, DC-nnn)", the named entry must exist, and the failure says which of the two forms to use."""
    f = []
    tc = "table_check.py"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        log = os.path.join(proj, "design", "decisions.md")
        clean = fread(log)
        both = clean.replace("Status: in force", "Status: superseded by DC-003")
        if both.count("superseded by DC-003") != 2:
            return ["the fixture log no longer has two entries in force"]
        fwrite(log, both + DC_WORKER + "Replaces: DC-001, DC-002\n")
        expect_run(f, "decisions with one entry that replaces two", chk(ctx, tc, "decisions", "--project", proj), 0,
                   "decisions: pass")
        fwrite(log, clean.replace("Status: in force", "Status: closed (settled by DC-003)", 1) + DC_WORKER)
        expect_run(f, "decisions with an entry closed by a later one", chk(ctx, tc, "decisions", "--project", proj), 0,
                   "decisions: pass")
        fwrite(log, clean.replace("Status: in force", "Status: closed (settled by DC-009)", 1) + DC_WORKER)
        expect_run(f, "decisions with an entry closed by one not in the log",
                   chk(ctx, tc, "decisions", "--project", proj), 1,
                   "DC-001 (decisions.md line 3): Status names DC-009, which is not in the log")
        fwrite(log, clean.replace("Status: in force", "Status: superseded by DC-003", 1) + DC_WORKER)
        expect_run(f, "decisions with an entry superseded by one that does not replace it",
                   chk(ctx, tc, "decisions", "--project", proj), 1,
                   "superseded by DC-003, but DC-003 has no \"Replaces: DC-001\"",
                   "if DC-003 changes this decision, add DC-001 to its Replaces line",
                   "if it only ends it, write the Status as \"closed (<how>, DC-003)\"")
    return f


TURNED_PINS = [("1", "A", "passive", -7.62, 2.54, 0), ("2", "B", "passive", -7.62, -5.08, 0),
               ("3", "C", "passive", 7.62, 0, 180), ("4", "D", "passive", 2.54, 10.16, 270)]


def test_kicad_turned_symbols(ctx):
    """schlib against KiCad itself: a symbol with no symmetry at each rotation with each mirror. A label
    on each pin position schlib gives must join that pin in KiCad's netlist, and a field asked left or
    right must be drawn on that side of its anchor in KiCad's plot."""
    ctx.need_cli()
    schlib = ctx.module("schlib")
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        hw = os.path.join(tmp, "p", "hardware")
        os.makedirs(hw)
        os.makedirs(os.path.join(tmp, "p", "design"))
        sch_path = os.path.join(hw, "t.kicad_sch")
        s = schlib.Schematic(sch_path, date="2026-01-02")
        lib_id = s.make_symbol("TURNED", "Resistor_SMD:R_0603_1608Metric", "", "test symbol",
                               ((-5.08, -7.62), (5.08, 7.62)), TURNED_PINS)
        want, anchors = {}, {}
        for row, mirror in enumerate((None, "x", "y")):
            for col, rot in enumerate((0, 90, 180, 270)):
                x, y = 15 + 20 * col, 12 + 26 * row
                tag = "%d%s" % (rot, mirror or "n")
                part = s.root.place(lib_id, "U", "V%sL" % tag, x, y, rot=rot, mirror=mirror, hide_ref=True,
                                    val=(x, y - 8, "left"))
                for num in "1234":
                    s.root.label("N%s_%s" % (tag, num), *part[num])
                    want["N%s_%s" % (tag, num)] = "%s.%s" % (part.ref, num)
                anchors["V%sL" % tag] = (x * schlib.U, "left")
                # a second copy, joined to nothing, carries the field asked right
                s.root.place(lib_id, "U", "V%sR" % tag, x, y + 13, rot=rot, mirror=mirror, hide_ref=True,
                             val=(x, y + 8, "right"))
                anchors["V%sR" % tag] = (x * schlib.U, "right")
        code, msgs = s.write()
        if not expect(f, code == 0, "the schematic was not written: %r" % msgs[-3:]):
            return f
        net = os.path.join(tmp, "t.net")
        res = run([ctx.cli, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", net, sch_path])
        if not expect(f, res[0] == 0 and os.path.isfile(net), "netlist export failed: %s" % res[1][-300:]):
            return f
        got = dict((name.lstrip("/"), ["%s.%s" % (x[0], x[1]) for x in nodes])
                   for name, nodes in ctx.h.read_netlist(net)[1].items())
        wrong = sorted("%s on %s" % (name, ", ".join(got.get(name, [])) or "no pin")
                       for name, pin in want.items() if got.get(name) != [pin])
        expect(f, not wrong, "pins: %d of %d labels are not on their pin in KiCad's netlist (N<rotation><mirror>_"
               "<pin>): %s" % (len(wrong), len(want), "; ".join(wrong[:8])))
        out = os.path.join(tmp, "svg")
        res = run([ctx.cli, "sch", "export", "svg", "-o", out, sch_path])
        plots = [x for x in os.listdir(out) if x.endswith(".svg")] if os.path.isdir(out) else []
        if not expect(f, res[0] == 0 and plots, "plot failed: %s" % res[1][-300:]):
            return f
        svg = fread(os.path.join(out, plots[0]))
        off = []
        for text, (ax, side) in sorted(anchors.items()):
            m = re.search(r"<desc>%s</desc>(.*?)</g>" % re.escape(text), svg, re.S)
            xs = [float(v) for v in re.findall(r"-?\d+\.\d+", m.group(1))][0::2] if m else []
            if not xs:
                off.append("%s not found in the plot" % text)
            elif (side == "left" and min(xs) < ax - 0.3) or (side == "right" and max(xs) > ax + 0.3):
                off.append("%s drawn from %.1f to %.1f, anchor %.1f" % (text, min(xs), max(xs), ax))
        expect(f, not off, "fields: %d of %d are not on the side asked (V<rotation><mirror><L or R>): %s"
               % (len(off), len(anchors), "; ".join(off[:8])))
    return f


def erc_fixture(ctx, proj, open_pins):
    """A hand-kept schematic in the fixture project: three symbols, with a label on every pin except
    open_pins (ref.pin), so ERC reports exactly those pins as not connected."""
    schlib = ctx.module("schlib")
    for gen in ("gen_sch.py", "gen_pcb.py"):
        path = os.path.join(proj, "scripts", gen)
        if os.path.exists(path):
            os.remove(path)
    s = schlib.Schematic(os.path.join(proj, SCH), date="2026-01-02")
    lib_id = s.make_symbol("TURNED", "Resistor_SMD:R_0603_1608Metric", "", "test symbol",
                           ((-5.08, -7.62), (5.08, 7.62)), TURNED_PINS)
    for i in range(3):                      # three, so a label still joins two pins when one is left open
        part = s.root.place(lib_id, "U", "TURNED", 30 + 40 * i, 40)
        for num in "1234":
            if "%s.%s" % (part.ref, num) not in open_pins:
                s.root.label("N" + num, *part[num])
    return s.write()


ERC_STATUS = """Expected ERC items:
  - "Pin not connected" on Symbol U1 Pin 1, DC-001
  - "Pin not connected" on Symbol U2 Pin 3, DC-001
"""


def test_build_erc_expected(ctx):
    """build.py erc: violations recorded under "Expected ERC items" in design/status.md do not stop the
    build, so the netlist is exported. The list is compared, not the count. The report stays in the project."""
    ctx.need_cli()
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_project(os.path.join(tmp, "p"))
        status = os.path.join(proj, "design", "status.md")
        net = os.path.join(proj, "hardware", "fixture.net")
        code, msgs = erc_fixture(ctx, proj, ("U1.1", "U2.3"))
        if not expect(f, code == 0, "the schematic was not written: %r" % msgs[-3:]):
            return f
        expect_run(f, "erc with two violations and no list", build_run(proj, "erc", "netlist"), 1,
                   "ERC: 2 violations: 0 expected, 2 new", "Symbol U1 Pin 1", "Symbol U2 Pin 3")
        expect(f, not os.path.exists(net), "the netlist was exported although ERC stopped the build")
        expect(f, os.path.isfile(os.path.join(proj, "hardware", "ERC.json")),
               "the ERC report is not in the KiCad folder (hardware/ERC.json)")
        clean = fread(status)
        fwrite(status, clean + ERC_STATUS)
        expect_run(f, "erc with both violations expected", build_run(proj, "erc", "netlist"), 0,
                   "ERC: 2 violations: 2 expected (design/status.md), 0 new", "done: erc netlist")
        expect(f, os.path.isfile(net), "the netlist was not exported with every violation expected")
        # The same count, another list: one expected pin joined, another pin left open.
        code, msgs = erc_fixture(ctx, proj, ("U1.1", "U2.4"))
        expect_run(f, "erc with the same count and another list", build_run(proj, "erc", "netlist"), 1,
                   "ERC: 2 violations: 1 expected (design/status.md), 1 new", "new: ", "Symbol U2 Pin 4",
                   'no longer found: "Pin not connected" on Symbol U2 Pin 3')
        # An expected item that is gone stops the build until its line is removed.
        code, msgs = erc_fixture(ctx, proj, ("U1.1",))
        expect_run(f, "erc with an expected item that is gone", build_run(proj, "erc"), 1,
                   "ERC: 1 violations: 1 expected (design/status.md), 0 new",
                   'no longer found: "Pin not connected" on Symbol U2 Pin 3', "remove its line")
        fwrite(status, clean + ERC_STATUS.replace("Pin 1, DC-001", "Pin 1, DC-999"))
        expect_run(f, "an expected item under a decision not in the log", build_run(proj, "erc"), 2,
                   "DC-999 is not in design/decisions.md")
        fwrite(status, clean + "Expected ERC items:\n  - Pin not connected on U1\n")
        expect_run(f, "an expected item that cannot be read", build_run(proj, "erc"), 2,
                   "cannot read expected ERC item")
        fwrite(status, clean)
        expect_run(f, "--twice with the report in the KiCad folder", build_run(proj, "erc", "netlist", "--twice",
                                                                               "--waive", "DC-001"), 0,
                   "WAIVED by DC-001", "repeatable: ")
    return f


def test_build_stale_output(ctx):
    """build.py: a design file the generator wrote before and no longer writes is listed and the build stops;
    nothing is deleted. Once the file is removed, its ownership row is dropped."""
    f = []
    extra = "hardware/extra.kicad_sym"
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_project(os.path.join(tmp, "p"))
        gen = os.path.join(proj, "scripts", "gen_sch.py")
        clean = fread(gen)
        fwrite(gen, clean + '\nhwcommon.write_text(os.path.join(HW, "extra.kicad_sym"), "(kicad_symbol_lib)\\n")\n')
        if not expect_run(f, "first build sch", build_run(proj, "sch"), 0, "done: sch"):
            return f
        if not expect(f, ownership(ctx, proj).get(extra, {}).get("writer") == "gen_sch.py (sch)",
                      "the extra library was not recorded as the generator's output"):
            return f
        expect_run(f, "second build, every file written again", build_run(proj, "sch"), 0, "done: sch")
        fwrite(gen, clean)
        expect_run(f, "build after the generator stopped writing a file", build_run(proj, "sch"), 3,
                   "NOT WRITTEN BY THE GENERATOR ANY MORE", extra, "remove the file")
        expect(f, os.path.isfile(os.path.join(proj, extra)), "the build deleted the file")
        expect(f, extra in ownership(ctx, proj), "the ownership row was dropped while the file is still there")
        os.remove(os.path.join(proj, extra))
        expect_run(f, "build after the stale file was removed", build_run(proj, "sch"), 0,
                   "%s is gone; its ownership row is dropped" % extra, "done: sch")
        expect(f, extra not in ownership(ctx, proj), "the ownership row of a removed file was kept")
    return f


ROUTER_PROBE = r'''
import contextlib, io, json, os, sys
sys.path.insert(0, sys.argv[1])
import pcblib
os.environ.pop("GRIDROUTER_PATH", None)
outer = os.path.realpath(sys.argv[2])
proj, hw = os.path.join(outer, "proj"), os.path.join(outer, "proj", "hardware")


def router(folder):
    os.makedirs(os.path.join(folder, "gridrouter"))
    for n in ("__init__.py", "kicad.py"):
        open(os.path.join(folder, "gridrouter", n), "w").close()


def rel(p):
    return os.path.relpath(os.path.realpath(p), outer).replace(os.sep, "/") if p else None


os.makedirs(os.path.join(proj, "design"))
os.makedirs(hw)
router(os.path.join(outer, "router"))               # a copy above the project: never to be found
out = {"above_only": rel(pcblib.find_router(None, hw))}
router(os.path.join(proj, "tools", "gr"))
os.chdir(outer)                                     # a relative path is read against the project root
out["relative"] = rel(pcblib.find_router(os.path.join("tools", "gr"), hw))
os.environ["GRIDROUTER_PATH"] = os.path.join(outer, "router")
out["env"] = rel(pcblib.find_router(None, hw))      # a path the user names may be anywhere
del os.environ["GRIDROUTER_PATH"]
try:
    pcblib.find_router("nowhere", hw)
    out["bad_hint"] = "no error"
except pcblib.PcbError as e:
    out["bad_hint"] = str(e).replace(outer, "").replace(os.sep, "/")
router(os.path.join(proj, "router"))
out["inside"] = rel(pcblib.find_router(None, hw))
said = io.StringIO()
with contextlib.redirect_stdout(said):
    pcblib.load_router(None, hw)
out["said"] = said.getvalue().replace(outer, "").replace(os.sep, "/").strip()
print("PROBE " + json.dumps(out, sort_keys=True))
'''


def test_router_search(ctx):
    """pcblib: the router is looked for in router/ at the project root and never above it; a relative path
    given is read against the project root; a path given that holds no router is an error; the path
    loaded is printed."""
    kpy = kicad_python(ctx)
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        probe = os.path.join(tmp, "probe.py")
        fwrite(probe, ROUTER_PROBE)
        os.makedirs(os.path.join(tmp, "outer"))
        res = run([kpy, probe, ctx.scripts, os.path.join(tmp, "outer")])
        m = re.search(r"^PROBE (.*)$", res[1], re.MULTILINE)
        if not expect(f, res[0] == 0 and m, "probe failed: %s" % res[1][-600:]):
            return f
        got = json.loads(m.group(1))
        expect(f, got["above_only"] is None, "a router above the project root was found: %r" % got["above_only"])
        expect(f, got["relative"] == "proj/tools/gr", "a relative path gave %r, not the folder in the project"
               % got["relative"])
        expect(f, got["env"] == "router", "GRIDROUTER_PATH gave %r" % got["env"])
        expect(f, "holds no gridrouter" in got["bad_hint"] and "/proj/nowhere" in got["bad_hint"],
               "a path given with no router in it: %r" % got["bad_hint"])
        expect(f, got["inside"] == "proj/router", "router/ in the project gave %r" % got["inside"])
        expect(f, got["said"] == "router: /proj/router", "the path loaded was not printed: %r" % got["said"])
    return f


SCRIPT_TESTS += [
    ("pcblib: the router search stays inside the project", test_router_search),
    ("build.py: a file the generator stopped writing is listed, never deleted", test_build_stale_output),
    ("build.py erc: expected items are compared as a list, and the netlist follows", test_build_erc_expected),
    ("schlib against KiCad: pins and fields of a turned and mirrored symbol", test_kicad_turned_symbols),
    ("table_check decisions: an entry ended by a later one", test_decisions_ended),
    ("table_check: a board-profile row that cannot be read fails", test_profile_rows),
    ("table_check summary: a withdrawn requirement is counted apart", test_summary_withdrawn),
    ("table_check summary: requirements sections in a tidied file", test_summary_sections),
    ("table_check: a status that starts with open is open", test_findings_open),
    ("table_check: the findings form and the extraction-miss count", test_findings_form),
    ("table_check checklists: only the result form answers an item", test_checklist_result_form),
    ("table_check scan: a scan of no files fails", test_scan_nothing),
    ("table_check scan: makers' addresses in saved documents are counted apart", test_scan_published),
    ("table_check scan: a reviewed hit is recorded once", test_scan_reviewed),
]
# ======================================================================== end of the faults met in use


# ======================================================================== S3 section (spice.py, simulation)
# spice.py: engine-check, netlist, model-check and run. The project is built in a temporary folder. The
# tests of the model table, the circuit file, the measures and the limits need no simulator. The tests
# that run a circuit skip, with the reason, when KiCad or its simulator library is not found.

SPICE_BUF = ("* BUF1: a stand-in written for this test. It leaves out everything but the gain.\n"
             ".subckt BUF1 in gnd out\n"
             "E1 out gnd in gnd 2\n"
             "R1 out gnd 1k\n"
             ".ends BUF1\n")
SPICE_MODEL_HEAD = "mpn,model_file,model_name,kind,pin_order,source,fetched,sha256,licence,checked,evidence\n"
SPICE_SCEN_HEAD = "id,scenario,corner,setup,measure,limit_low,limit_high,source\n"
SPICE_SCEN = (SPICE_SCEN_HEAD
              + "S01,normal on,nominal,V1 /alpha/NET_A 0 12; .op,final v(/alpha/OUT),3.9,4.1,FR-001\n"
              + "S02,step,nominal,V1 /alpha/NET_A 0 PULSE(0 12 0 1u 1u 1 2); .tran 10u 1m,max v(/alpha/MID),1.9,2.1,"
                "DS-010\n"
              + "S03,rail,nominal,V1 /alpha/NET_A 0 12; .op,final v(+5V),3.9,,FR-002\n")


def spice_sha(text):
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def spice_comp(ref, value, sheet, mpn="", dnp=False):
    return ('    (comp (ref "%s") (value "%s") (footprint "lib:X")\n'
            '      (fields (field (name "MPN") "%s"))\n'
            '      (property (name "Sheetname") (value "%s")) (property (name "Sheetfile") (value "%s.kicad_sch"))%s\n'
            '      (sheetpath (names "/%s/") (tstamps "/t-%s/")) (tstamps "t-%s"))\n'
            % (ref, value, mpn, sheet, sheet, ' (property (name "dnp"))' if dnp else "", sheet, sheet, ref))


def spice_netlist(comps, nets):
    out = '(export (version "E") (design (source "fixture.kicad_sch") (date ""))\n  (components\n'
    out += "".join(spice_comp(*c) for c in comps) + "  )\n  (nets\n"
    for k, (name, nodes) in enumerate(sorted(nets.items()), 1):
        out += '    (net (code "%d") (name "%s")%s)\n' % (k, name, "".join(
            ' (node (ref "%s") (pin "%s") (pintype "passive"))' % n for n in nodes))
    return out + "  ))\n"


SPICE_COMPS = [("R1", "10k", "alpha"), ("R2", "2k 1%", "alpha"), ("R3", "1k", "alpha"),
               ("U1", "BUF", "alpha", "BUF-1"), ("R8", "4k7", "alpha", "", True), ("J1", "Conn", "beta", "HDR-1"),
               ("R9", "1k", "beta")]
SPICE_NETS = {"/alpha/NET_A": [("R1", "1"), ("J1", "1")],
              "/alpha/MID": [("R1", "2"), ("R2", "1"), ("U1", "1"), ("R8", "1")],
              "/alpha/OUT": [("U1", "2"), ("R3", "1")],
              "+5V": [("R3", "2"), ("R9", "1")],
              "GND": [("R2", "2"), ("U1", "3"), ("R8", "2"), ("J1", "2"), ("R9", "2")]}


def spice_proj(tmp, model=SPICE_BUF, row=None, comps=None, nets=None, extra_rows="", sha=None, table=None):
    """A small project: module alpha (a divider and a gain block) and a part on another sheet."""
    root = os.path.join(tmp, "proj")
    if os.path.isdir(root):
        shutil.rmtree(root)
    for d in ("design", "hardware", "sim/models", "sim/alpha"):
        os.makedirs(os.path.join(root, *d.split("/")))
    fwrite(os.path.join(root, "hardware", "fixture.net"),
           spice_netlist(comps or SPICE_COMPS, nets or SPICE_NETS))
    fwrite(os.path.join(root, "hardware", "fixture.kicad_pro"), "{}\n")
    if model is not None:
        fwrite(os.path.join(root, "sim", "models", "buf.lib"), model)
    r = {"mpn": "BUF-1", "model_file": "sim/models/buf.lib", "model_name": "BUF1", "kind": "stand-in",
         "pin_order": "1;3;2", "source": "written from the datasheet", "fetched": "2026-01-02",
         "sha256": sha or spice_sha(model or ""), "licence": "own", "checked": "yes", "evidence": "report"}
    r.update(row or {})
    cols = SPICE_MODEL_HEAD.strip().split(",")
    fwrite(os.path.join(root, "design", "sim-models.csv"),
           table if table is not None else SPICE_MODEL_HEAD + ",".join(r[c] for c in cols) + "\n" + extra_rows)
    fwrite(os.path.join(root, "sim", "alpha", "scenarios.csv"), SPICE_SCEN)
    return root


def spice(ctx, root, *args, env=None):
    return run([sys.executable, os.path.join(ctx.scripts, "spice.py")] + list(args) + ["--project", root], env=env)


def spice_library(ctx):
    """The spice module, after a check that the simulator library is there; Skip when it is not."""
    ctx.need_cli()
    s = ctx.module("spice")
    try:
        s.find_library()
    except s.SpiceError as e:
        raise Skip("simulator library not found: %s" % str(e).splitlines()[0])
    return s


def test_spice_model_table(ctx):
    """model-check without the simulator: a clean table passes; each planted fault fails and is named."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        root = spice_proj(tmp)
        expect_run(f, "clean table", spice(ctx, root, "model-check"), 0, "pass  BUF-1", "1 rows, 0 failed")
        fwrite(os.path.join(root, "sim", "models", "part.lib"), ".model DX D(IS=1n)\n")
        inc = SPICE_BUF + ".include part.lib\n"
        root = spice_proj(tmp, model=inc)
        fwrite(os.path.join(root, "sim", "models", "part.lib"), ".model DX D(IS=1n)\n")
        expect_run(f, "an include of a file inside sim/models/", spice(ctx, root, "model-check"), 0, "pass  BUF-1")
        root = spice_proj(tmp, row={"checked": "no"})
        expect_run(f, "a model not yet checked", spice(ctx, root, "model-check"), 0, "checked is not yes")
        faults = [
            ("a command block", {"model": SPICE_BUF + ".control\nshell touch x\n.endc\n"}, "simulator command"),
            ("a shell call", {"model": SPICE_BUF + ".shell touch x\n"}, "simulator command or shell call"),
            ("a system call", {"model": SPICE_BUF + ".SYSTEM touch x\n"}, "simulator command or shell call"),
            ("an exec line", {"model": SPICE_BUF + "  .exec touch x\n"}, "simulator command"),
            ("an include above sim/models/", {"model": SPICE_BUF + ".include ../../design/sim-models.csv\n"},
             "outside sim/models/"),
            ("an include by absolute path", {"model": SPICE_BUF + '.include "/etc/hosts"\n'}, "outside sim/models/"),
            ("a library include outside", {"model": SPICE_BUF + ".lib ../other.lib tt\n"}, "outside sim/models/"),
            ("an include of a missing file", {"model": SPICE_BUF + ".inc gone.lib\n"}, "is not there"),
            ("an analysis line", {"model": SPICE_BUF + ".tran 1u 1m\n"}, "analysis or output line"),
            ("a control character", {"model": SPICE_BUF + "* a\x1bb\n"}, "control character"),
            ("a wrong sha256", {"sha": "0" * 64}, "sha256 of sim/models/buf.lib"),
            ("a missing file", {"model": None}, "is not there"),
            ("a model name not in the file", {"row": {"model_name": "BUF2"}}, "model name BUF2 is not defined"),
            ("a file outside sim/models/", {"row": {"model_file": "design/sim-models.csv"}}, "is not under sim/models/"),
            ("a file above the project", {"row": {"model_file": "sim/models/../../x.lib"}}, "is not under sim/models/"),
            ("an unknown kind", {"row": {"kind": "typical"}}, "must be maker or stand-in"),
            ("a pin count that differs", {"row": {"pin_order": "1;3"}}, "pin_order has 2 pins"),
            ("an empty pin order", {"row": {"pin_order": ""}}, "pin_order is empty"),
            ("a stand-in not named in its file", {"model": SPICE_BUF.replace("stand-in", "model")},
             "does not say \"stand-in\""),
        ]
        for what, kw, text in faults:
            root = spice_proj(tmp, **kw)
            expect_run(f, "model-check with " + what, spice(ctx, root, "model-check"), 1, "fail  ", text)
        root = spice_proj(tmp, model=SPICE_BUF.replace("stand-in", "model"), row={"kind": "maker"})
        expect_run(f, "a maker's file need not say stand-in", spice(ctx, root, "model-check"), 0, "pass  BUF-1")
        dup = "BUF-1,sim/models/buf.lib,BUF1,stand-in,1;3;2,x,2026-01-02,%s,own,yes,r\n" % spice_sha(SPICE_BUF)
        root = spice_proj(tmp, extra_rows=dup)
        expect_run(f, "two rows for one part", spice(ctx, root, "model-check"), 2, "a second row for BUF-1")
        root = spice_proj(tmp, table=SPICE_MODEL_HEAD.replace("licence", "license"))
        expect_run(f, "a wrong header", spice(ctx, root, "model-check"), 2, "the header must be exactly")
        root = spice_proj(tmp, table=SPICE_MODEL_HEAD)
        expect_run(f, "an empty table", spice(ctx, root, "model-check"), 2, "holds no row")
        os.remove(os.path.join(root, "design", "sim-models.csv"))
        expect_run(f, "no table", spice(ctx, root, "model-check"), 2, "design/sim-models.csv is not there")
    return f


def test_spice_netlist(ctx):
    """netlist: the circuit file from the netlist and the model table, the same bytes twice; it stops on a
    part with no row and on each other planted fault, and writes nothing then."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        root = spice_proj(tmp)
        cir = os.path.join(root, "sim", "alpha", "alpha.cir")
        if expect_run(f, "clean netlist", spice(ctx, root, "netlist", "alpha"), 0,
                      "sim/alpha/alpha.cir written", "R8: not fitted, left out", "edge nodes: +5V /alpha/NET_A"):
            text = fread(cir)
            for line in ("R1 /alpha/NET_A /alpha/MID 10000", "R2 /alpha/MID 0 2000", "R3 /alpha/OUT +5V 1000",
                         "XU1 /alpha/MID 0 /alpha/OUT BUF1", ".subckt BUF1 in gnd out", "* ground: GND"):
                expect(f, ("\n" + line + "\n") in text, "circuit file lacks the line %r:\n%s" % (line, text))
            expect(f, "R9" not in text and "J1" not in text and "R8 " not in text,
                   "a part of another sheet, or one not fitted, is in the circuit file")
            expect(f, text.rstrip().endswith(".end") and root not in text, "no closing .end, or a machine path")
            spice(ctx, root, "netlist", "alpha")
            expect(f, fread(cir) == text, "a second netlist run gave other bytes")
        fwrite(os.path.join(root, "design", "modules.csv"),
               "module,sheet,ref_block,purpose\ngain,alpha.kicad_sch,100,test\n")
        expect_run(f, "the sheet from design/modules.csv", spice(ctx, root, "netlist", "gain"), 0,
                   "sim/gain/gain.cir written")
        expect_run(f, "a module with a row, asked for by its sheet name", spice(ctx, root, "netlist", "beta"), 2,
                   "no row in design/sim-models.csv for: J1 (HDR-1)")
        faults = [
            ("a part with no row", {"comps": SPICE_COMPS + [("U2", "AMP", "alpha", "AMP-9")],
                                    "nets": dict(SPICE_NETS, **{"/alpha/X": [("U2", "1")]})},
             "no row in design/sim-models.csv for: U2 (AMP-9)"),
            ("a part with no MPN and no row", {"comps": SPICE_COMPS + [("TP1", "TestPoint", "alpha")]},
             "TP1 (no MPN field, value TestPoint)"),
            ("a value that is no number", {"comps": [("R1", "see note", "alpha")] + SPICE_COMPS[1:]},
             "R1: value 'see note' is not a plain number"),
            ("a pin the part does not have", {"row": {"pin_order": "1;3;7"}}, "names pin 7"),
            ("a wrong sha256", {"sha": "1" * 64}, "sha256 of sim/models/buf.lib"),
            ("a refused model file", {"model": SPICE_BUF + ".control\nquit\n.endc\n"}, "refused"),
            ("no ground net", {"nets": dict((k.replace("GND", "0V"), v) for k, v in SPICE_NETS.items())},
             "name the module's reference net with --ground"),
            ("two nets that become one node", {"comps": SPICE_COMPS + [("R4", "1k", "alpha")],
                                               "nets": dict(SPICE_NETS, **{"/alpha/mid": [("R4", "1")],
                                                                           "/alpha/Y": [("R4", "2")]})},
             "would both become the node"),
        ]
        for what, kw, text in faults:
            root = spice_proj(tmp, **kw)
            expect_run(f, "netlist with " + what, spice(ctx, root, "netlist", "alpha"), 2, text)
            expect(f, not os.path.exists(os.path.join(root, "sim", "alpha", "alpha.cir")),
                   "netlist with %s still wrote a circuit file" % what)
        root = spice_proj(tmp, nets=dict((k.replace("GND", "0V"), v) for k, v in SPICE_NETS.items()))
        expect_run(f, "--ground", spice(ctx, root, "netlist", "alpha", "--ground", "0V"), 0, "written")
        root = spice_proj(tmp)
        expect_run(f, "a module with no part", spice(ctx, root, "netlist", "gamma"), 2, "no part of")
        expect_run(f, "a module name that is a path", spice(ctx, root, "netlist", "../x"), 2, "letters, digits")
        os.remove(os.path.join(root, "hardware", "fixture.net"))
        expect_run(f, "no netlist", spice(ctx, root, "netlist", "alpha"), 2, "export it with the build first")
    return f


def test_spice_measures(ctx):
    """Measures and limits on known vectors, the setup rules, a stale or edited circuit file, and the
    message when the library is not found. No simulator is loaded."""
    s, f = ctx.module("spice"), []
    vecs = {"time": [0.0, 1.0, 2.0, 4.0], "out": [0.0, 2.0, 2.0, 6.0], "v1#branch": [-1.0, -1.0, -1.0, -1.0]}
    for text, want in (("final v(out)", 6.0), ("first v(OUT)", 0.0), ("value v(out) at 0.5", 1.0),
                       ("value v(out) at 3", 4.0), ("max v(out)", 6.0), ("max v(out) to 2", 2.0),
                       ("min v(out) from 1", 2.0), ("pp v(out) from 0.5 to 3", 3.0), ("avg v(out) to 2", 1.5),
                       ("avg v(out)", 2.75), ("rms i(v1)", 1.0), ("cross v(out) 1 rise", 0.5),
                       ("cross v(out) 4 rise from 1", 3.0), ("final i(V1) scale -1k", 1000.0),
                       ("value out at 500m", 1.0)):
        try:
            got = s.measure(vecs, text)
        except ValueError as e:
            got = "error: %s" % e
        expect(f, isinstance(got, float) and abs(got - want) < 1e-9, "measure %r gave %r, not %r" % (text, got, want))
    for text in ("final v(nowhere)", "median v(out)", "value v(out)", "value v(out) at 9", "cross v(out) 7 rise",
                 "cross v(out) 1", "max v(out) from 3 to 1", "final v(out) extra", "final"):
        try:
            f.append("measure %r gave %r, not an error" % (text, s.measure(vecs, text)))
        except ValueError:
            pass
    for args, want in (((2.0, "1.9", "2.1", "FR-001"), "pass"), ((1.9, "1.9", "2.1", "FR-001"), "pass"),
                       ((2.1, "1.9", "2.1", "FR-001"), "pass"), ((1.89, "1.9", "2.1", "FR-001"), "fail"),
                       ((2.11, "1.9", "2.1", "FR-001"), "fail"), ((5.0, "", "2.1", "DS-010"), "fail"),
                       ((-5.0, "", "2.1", "DS-010"), "pass"), ((5.0, "1.9", "", "DS-010"), "pass"),
                       ((0.0015, "1m", "2m", "DS-010"), "pass"), ((0.0025, "1m", "2m", "DS-010"), "fail"),
                       ((float("nan"), "1", "2", "DS-010"), "fail"), ((2.0, "1.9", "2.1", ""), "no source"),
                       ((2.0, "1.9", "2.1", "  "), "no source"), ((2.0, "", "", "FR-001"), "no limit")):
        got = s.judge(*args)
        expect(f, got == want, "judge%r gave %r, not %r" % (args, got, want))
    for text, want in (("10k", 1e4), ("4.7u", 4.7e-6), ("1meg", 1e6), ("2m", 2e-3), ("-1.5e-3", -1.5e-3), ("5v", 5.0)):
        expect(f, abs(s.number(text) - want) <= abs(want) * 1e-12, "number(%r) gave %r" % (text, s.number(text)))
    for text, want in (("100k", 1e5), ("1k65", 1650.0), ("4u7 100V", 4.7e-6), ("2M", 2e6), ("4R7", 4.7),
                       ("330 1%", 330.0), ("100nF", 1e-7), ("10m", 1e-2)):
        expect(f, abs(s.part_value(text) - want) <= abs(want) * 1e-12,
               "part_value(%r) gave %r" % (text, s.part_value(text)))
    with tempfile.TemporaryDirectory() as tmp:
        root = spice_proj(tmp)
        fwrite(os.path.join(root, "sim", "models", "src.lib"), ".subckt SRC p n\nV1 p x 12\nR1 x n 0.1\n.ends\n")

        def setup(text):
            row = {"id": "S01", "_line": 2, "setup": text}
            try:
                return s.setup_lines(row, "sim/alpha/scenarios.csv", root)
            except s.SpiceError as e:
                return str(e)

        got = setup("V1 a 0 12; .include sim/models/src.lib; .tran 1u 1m")
        expect(f, isinstance(got, list) and ".subckt SRC p n" in got and not any(".include" in x for x in got),
               "a setup with an include inside sim/models/ gave %r" % (got,))
        for text, want in (("V1 a 0 12", "exactly one analysis"), ("V1 a 0 1; .op; .tran 1u 1m", "exactly one analysis"),
                           ("V1 a 0 1; .ac dec 10 1 1k", "exactly one analysis"),
                           (".control; shell touch x; .endc; .op", "simulator command"),
                           (".include ../../hardware/fixture.net; .op", "outside sim/models/"),
                           (".op; .end", "a line .end"), (".op; .system ls", "shell call")):
            got = setup(text)
            expect(f, isinstance(got, str) and want in got and "line 2 (S01)" in got,
                   "setup %r gave %r, not a refusal with %r" % (text, got, want))
        # run stops before the simulator is loaded when the circuit file is not what netlist writes now
        none = {"KICAD_NGSPICE": os.path.join(tmp, "no-such-library")}
        expect_run(f, "run with no circuit file", spice(ctx, root, "run", "alpha", env=none), 2, "write it with")
        expect_run(f, "netlist", spice(ctx, root, "netlist", "alpha"), 0, "written")
        cir = os.path.join(root, "sim", "alpha", "alpha.cir")
        made = fread(cir)
        fwrite(cir, made.replace("R2 /alpha/MID 0 2000", "R2 /alpha/MID 0 2200"))
        expect_run(f, "run on a circuit file edited by hand", spice(ctx, root, "run", "alpha", env=none), 2,
                   "is not what spice.py netlist writes now", "stale")
        fwrite(cir, made)
        net = os.path.join(root, "hardware", "fixture.net")
        fwrite(net, fread(net).replace('(value "2k 1%")', '(value "3k")'))
        expect_run(f, "run after the schematic changed", spice(ctx, root, "run", "alpha", env=none), 2,
                   "is not what spice.py netlist writes now")
        expect_run(f, "netlist again", spice(ctx, root, "netlist", "alpha"), 0, "written")
        expect_run(f, "run with the library not found", spice(ctx, root, "run", "alpha", env=none), 2,
                   "simulator library not found", "KICAD_NGSPICE")
        expect_run(f, "engine-check with the library not found", spice(ctx, root, "engine-check", env=none), 2,
                   "simulator library not found")
        scen = os.path.join(root, "sim", "alpha", "scenarios.csv")
        for what, text, want in (
                ("a second row for one scenario and corner", SPICE_SCEN + SPICE_SCEN.splitlines()[1] + "\n",
                 "one row per scenario and corner"),
                ("a limit that is no number", SPICE_SCEN.replace(",3.9,4.1,", ",low,4.1,"), "is not a number"),
                ("a wrong header", SPICE_SCEN.replace("limit_low", "low"), "the header must be exactly"),
                ("no rows", SPICE_SCEN_HEAD, "holds no row")):
            fwrite(scen, text)
            expect_run(f, "run with " + what, spice(ctx, root, "run", "alpha", env=none), 2, want)
    return f


SPICE_WRONG_HAND = (
    "import sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import spice\n"
    "title, deck, checks = spice.ENGINE_CASES[0]\n"
    "spice.ENGINE_CASES[0] = (title, deck, [(checks[0][0], 2.5, checks[0][2], 'planted')] + checks[1:])\n"
    "sys.exit(spice.main(['engine-check']))\n")
SPICE_WRONG_DECK = (
    "import sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import spice\n"
    "title, deck, checks = spice.ENGINE_CASES[1]\n"
    "spice.ENGINE_CASES[1] = (title, [x.replace('C1 c 0 1u', 'C1 c 0 2u') for x in deck], checks)\n"
    "sys.exit(spice.main(['engine-check']))\n")


def test_kicad_spice_engine(ctx):
    """engine-check on KiCad's library: passes as shipped; fails with a planted wrong hand value and with a
    planted wrong circuit."""
    spice_library(ctx)
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        expect_run(f, "engine-check", spice(ctx, tmp, "engine-check"), 0, "engine-check: pass", "simulator library:",
                   "pass  final v(mid)", "pass  value v(c) at 1m")
        for what, code, text in (("a wrong hand value", SPICE_WRONG_HAND, "fail  final v(mid)"),
                                 ("a wrong circuit", SPICE_WRONG_DECK, "fail  value v(c) at 1m")):
            probe = os.path.join(tmp, "probe.py")
            fwrite(probe, code)
            expect_run(f, "engine-check with " + what, run([sys.executable, probe, ctx.scripts]), 1, text,
                       "engine-check: FAIL")
    return f


def test_kicad_spice_run(ctx):
    """run on KiCad's library: values against hand values, files written, the same files on a second run;
    a planted failing limit, a limit with no source, a vector that is not there, a circuit that cannot
    be solved and a changed result file each fail. model-check --points runs one model alone."""
    spice_library(ctx)
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        root = spice_proj(tmp)
        res = os.path.join(root, "sim", "alpha", "results")
        scen = os.path.join(root, "sim", "alpha", "scenarios.csv")
        expect_run(f, "netlist", spice(ctx, root, "netlist", "alpha"), 0, "written")
        if not expect_run(f, "clean run", spice(ctx, root, "run", "alpha"), 0, "pass       S01 nominal",
                          "pass       S02 nominal", "pass       S03 nominal", "3 rows: 3 pass",
                          "5 files written to sim/alpha/results/"):
            return f
        table = fread(os.path.join(res, "results.csv")).splitlines()
        expect(f, table[0] == "id,scenario,corner,measure,value,limit_low,limit_high,result,source"
               and table[1] == "S01,normal on,nominal,final v(/alpha/OUT),4,3.9,4.1,pass,FR-001"
               and table[3].split(",")[4] == "4", "results.csv is not the hand values (4 V):\n%s" % "\n".join(table))
        v = float(table[2].split(",")[4])
        expect(f, abs(v - 2.0) < 1e-3, "S02: the divider's peak is %r, by hand 2 V" % v)
        wave = fread(os.path.join(res, "S02_nominal.csv")).splitlines()
        expect(f, wave[0].startswith("time,") and "/alpha/mid" in wave[0] and len(wave) > 50,
               "the waveform file of S02 is not a table over time: %r" % wave[:2])
        note = fread(os.path.join(res, "run.txt"))
        expect(f, "circuit file: sim/alpha/alpha.cir sha256 " in note and root not in note,
               "run.txt lacks the circuit file's checksum, or holds a machine path:\n%s" % note)
        before = dict((n, fread(os.path.join(res, n), "rb")) for n in sorted(os.listdir(res)))
        expect_run(f, "second run", spice(ctx, root, "run", "alpha", "--again"), 0, "0 differ", "the same files twice")
        expect_run(f, "third run, written", spice(ctx, root, "run", "alpha"), 0, "3 rows: 3 pass")
        after = dict((n, fread(os.path.join(res, n), "rb")) for n in sorted(os.listdir(res)))
        expect(f, before == after, "a run written twice gave other bytes")
        p = os.path.join(res, "S01_nominal.csv")
        fwrite(p, fread(p).replace("4", "5"))
        expect_run(f, "second run against a changed result file", spice(ctx, root, "run", "alpha", "--again"), 1,
                   "differs  sim/alpha/results/S01_nominal.csv", "the run is not repeatable")
        fwrite(os.path.join(res, "S09_old.csv"), "time\n")
        fwrite(scen, SPICE_SCEN
               + "S04,limit,nominal,V1 /alpha/NET_A 0 12; .op,final v(/alpha/OUT),5,6,FR-003\n"
               + "S05,no source,nominal,V1 /alpha/NET_A 0 12; .op,final v(/alpha/OUT),3.9,4.1,\n"
               + "S06,no vector,nominal,V1 /alpha/NET_A 0 12; .op,final v(/alpha/NOWHERE),3.9,4.1,FR-004\n"
               + "S07,no limit,nominal,V1 /alpha/NET_A 0 12; .op,final v(/alpha/OUT),,,\n"
               + "S08,low supply,low,V1 /alpha/NET_A 0 9; .op,final v(/alpha/OUT),2.9,3.1,FR-005\n"
               + "S08,low supply,cold,V1 /alpha/NET_A 0 9; .temp -40; .op,final v(/alpha/OUT),2.9,3.1,FR-005\n"
               + "S10,loop,nominal,V1 /alpha/NET_A 0 12; V2 /alpha/NET_A 0 5; .op,final v(/alpha/OUT),3.9,4.1,FR-006\n")
        expect_run(f, "run with planted faults", spice(ctx, root, "run", "alpha"), 1,
                   "fail       S04 nominal", "no source  S05 nominal", "error      S06 nominal",
                   "no vector /alpha/nowhere", "no limit   S07 nominal", "pass       S08 low", "pass       S08 cold",
                   "error      S10 nominal", "stale: files in sim/alpha/results/ that this run did not write: S09_old.csv",
                   "A limit with no source is not a pass limit")
        table = fread(os.path.join(res, "results.csv"))
        expect(f, ",5,6,fail,FR-003" in table and ",no source," in table and ",error,FR-004" in table,
               "results.csv lacks the failed rows:\n%s" % table)
        fwrite(scen, SPICE_SCEN_HEAD
               + "S01,cmd,nominal,V1 /alpha/NET_A 0 12; .control; quit; .endc; .op,final v(/alpha/OUT),3.9,4.1,FR-001\n")
        expect_run(f, "run with a command in a setup", spice(ctx, root, "run", "alpha"), 2, "simulator command")
        points = os.path.join(root, "sim", "buf-points.csv")
        fwrite(points, SPICE_SCEN_HEAD
               + "P01,gain,nominal,V1 a 0 1.5; X1 a 0 y BUF1; .op,final v(y),2.9,3.1,DS-020\n")
        expect_run(f, "model-check of one model alone",
                   spice(ctx, root, "model-check", "--mpn", "BUF-1", "--points", points), 0, "pass  BUF-1",
                   "pass       P01 nominal", "sim/buf-points.results.csv written")
        expect(f, "P01,gain,nominal,final v(y),3,2.9,3.1,pass,DS-020" in fread(points[:-4] + ".results.csv"),
               "the model check's result file lacks the row")
        fwrite(points, fread(points).replace("2.9,3.1", "1.9,2.1"))
        expect_run(f, "model-check with a figure outside the datasheet's limits",
                   spice(ctx, root, "model-check", "--mpn", "BUF-1", "--points", points), 1, "fail       P01 nominal")
        expect_run(f, "model-check of a part with no row",
                   spice(ctx, root, "model-check", "--mpn", "AMP-9", "--points", points), 2, "AMP-9 has no row")
        expect_run(f, "model-check with --mpn alone", spice(ctx, root, "model-check", "--mpn", "BUF-1"), 2,
                   "go together")
    return f


SCRIPT_TESTS += [
    ("spice model-check: the model table, and model files refused as data", test_spice_model_table),
    ("spice netlist: the circuit file from the netlist and the model table", test_spice_netlist),
    ("spice: measures, limits, setups, a stale circuit file, no library", test_spice_measures),
    ("KiCad: spice engine-check passes, and fails on a planted fault", test_kicad_spice_engine),
    ("KiCad: spice run, twice the same, planted faults, one model alone", test_kicad_spice_run),
]
# ======================================================================== end of S3 section


# ======================================================================== S4 section (schlib.py and build.py)
# Group S4. build.py: the settings file design/build.json, the project checks hook, the scratch folder,
# the lock stop, the copy list and the rule for a file a generator stopped writing. schlib.py: declared
# rails, designator blocks, multi-unit parts, drawing helpers, the multi-sheet skeleton, the firmware
# page and the datasheet field.

def s4_settings(proj, **kw):
    data = {"project": "fixture", "order_folder": "fab", "order_options": [], "checks": []}
    data.update(kw)
    fwrite(os.path.join(proj, "design", "build.json"), json.dumps(data, indent=2) + "\n")


def s4_build(proj, *args, **env):
    return run([sys.executable, os.path.join(proj, SK, "build.py")] + list(args), cwd=proj, env=env or None)


def s4_plain_project(ctx, dest):
    """The fixture project with the skill's build.py as shipped: no constant filled in."""
    proj = ctx.fx.make_project(dest)
    shutil.copy(os.path.join(ctx.scripts, "build.py"), os.path.join(proj, SK, "build.py"))
    return proj


def test_s4_build_settings(ctx):
    """build.py reads design/build.json; nothing is edited in the copied script."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = s4_plain_project(ctx, os.path.join(tmp, "p"))
        expect_run(f, "no settings file and an empty KiCad folder", build_run(proj, "sch"), 2, "design/build.json")
        s4_settings(proj)
        expect_run(f, "build sch with design/build.json", build_run(proj, "sch"), 0, "done: sch")
        expect(f, os.path.isfile(os.path.join(proj, SCH)), "the project named in build.json was not built")
        fwrite(os.path.join(proj, SK, "fab.py"), 'import sys\nprint("ORDER ARGS " + " ".join(sys.argv[1:]))\n')
        s4_settings(proj, order_folder="maker", order_options=["--date", "2026-01-02"])
        expect_run(f, "the order folder and options reach the order stage", build_run(proj, "fab"), 0,
                   "ORDER ARGS fixture.kicad_pcb maker --date 2026-01-02")
        proj = s4_plain_project(ctx, os.path.join(tmp, "p2"))
        s4_settings(proj, project="other")
        expect_run(f, "another project name", build_run(proj, "sch"), 0, "done: sch")
        expect(f, os.path.isfile(os.path.join(proj, "hardware", "other.kicad_sch")), "project 'other' was not built")
        proj = s4_plain_project(ctx, os.path.join(tmp, "p3"))
        s4_settings(proj, project="other")
        expect_run(f, "--name over the settings file", build_run(proj, "sch", "--name", "named"), 0, "done: sch")
        expect(f, os.path.isfile(os.path.join(proj, "hardware", "named.kicad_sch")), "--name was not used")
        proj = s4_plain_project(ctx, os.path.join(tmp, "p4"))
        path = os.path.join(proj, "design", "build.json")
        good = {"project": "fixture", "order_folder": "fab", "order_options": [], "checks": []}
        faults = [("text that is not JSON", '{"project": "fixture",\n', "not valid JSON"),
                  ("a list in place of the object", "[]\n", "one JSON object"),
                  ("an unknown key", json.dumps(dict(good, fab_dir="x")), "fab_dir"),
                  ("checks that is not a list", json.dumps(dict(good, checks="python3 scripts/checks/a.py")), "checks"),
                  ("an order option that is not text", json.dumps(dict(good, order_options=[1])), "order_options"),
                  ("the template text left in", json.dumps(dict(good, project="<KiCad project name>")), "template"),
                  ("an order folder outside the KiCad folder", json.dumps(dict(good, order_folder="../out")),
                   "order_folder")]
        for what, text, said in faults:
            fwrite(path, text)
            expect_run(f, "build.json with " + what, build_run(proj, "sch"), 2, "design/build.json", said)
        expect(f, not os.listdir(os.path.join(proj, "hardware")), "a refused settings file still let the build write")
    return f


S4_CHECK = ('import os\nimport sys\nimport hwcommon  # noqa: F401\n'
            'print("CHECK %s RAN in " + os.path.basename(os.getcwd()))\nsys.exit(%d)\n')


def test_s4_build_checks(ctx):
    """The checks list of design/build.json: run after the stages, from the project root; one that fails
    fails the build; a command outside scripts/checks/ is refused before anything runs."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_project(os.path.join(tmp, "p"))
        checks = os.path.join(proj, "scripts", "checks")
        os.makedirs(checks)
        fwrite(os.path.join(checks, "ok.py"), S4_CHECK % ("ok", 0))
        fwrite(os.path.join(checks, "bad.py"), S4_CHECK % ("bad", 1))
        s4_settings(proj, checks=["python3 scripts/checks/ok.py"])
        res = build_run(proj, "sch")
        if expect_run(f, "build sch with one project check", res, 0, "CHECK ok RAN in p", "done: sch checks"):
            expect(f, res[1].index("wrote") < res[1].index("CHECK ok"), "the project check ran before the stage")
        res = build_run(proj, "checks")
        expect_run(f, "the checks alone", res, 0, "CHECK ok RAN in p", "done: checks")
        expect(f, "wrote" not in res[1], "build.py checks ran a generator")
        s4_settings(proj, checks=["python3 scripts/checks/bad.py", "python3 scripts/checks/ok.py"])
        res = build_run(proj, "sch")
        expect_run(f, "a project check that fails", res, 1, "CHECK bad RAN", "CHECK ok RAN", "FAIL",
                   "scripts/checks/bad.py")
        expect(f, "done:" not in res[1], "the build said done although a project check failed")
        for what, cmd in (("a command outside scripts/checks", "python3 scripts/gen_sch.py x"),
                          ("a check file that is not there", "python3 scripts/checks/none.py"),
                          ("a path that climbs out of scripts/checks", "python3 scripts/checks/../gen_sch.py x")):
            s4_settings(proj, checks=[cmd])
            res = build_run(proj, "sch")
            expect_run(f, what, res, 2, "design/build.json", "scripts/checks")
            expect(f, "wrote" not in res[1], "%s: a stage ran before the refusal" % what)
        s4_settings(proj)
        expect_run(f, "no project checks", build_run(proj, "checks"), 0, "no project checks")
    return f


S4_TRACE = ('\nwith open(os.environ["S4_TRACE"], "a") as _t:\n    _t.write(os.path.realpath(os.getcwd()) + "\\n")\n')


def test_s4_build_scratch(ctx):
    """Scratch files only in .hwtmp/ at the project root: created, git-ignored, left empty."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        trace = os.path.join(tmp, "trace.txt")

        def traced(proj):
            lines = fread(trace).split() if os.path.isfile(trace) else []
            inside = os.path.realpath(proj) + os.sep
            return [l for l in lines if not (l + os.sep).startswith(inside)]
        proj = ctx.fx.make_project(os.path.join(tmp, "p"))
        gen = os.path.join(proj, "scripts", "gen_sch.py")
        fwrite(gen, fread(gen) + S4_TRACE)
        ignore, scratch = os.path.join(proj, ".gitignore"), os.path.join(proj, ".hwtmp")
        fwrite(ignore, ".DS_Store\n")
        if not expect_run(f, "first build sch", s4_build(proj, "sch", S4_TRACE=trace), 0, "done: sch"):
            return f
        expect(f, os.path.isdir(scratch), "the build did not make .hwtmp/")
        expect(f, fread(ignore).splitlines() == [".DS_Store", "/.hwtmp/"], ".gitignore is %r" % fread(ignore))
        sch = os.path.join(proj, SCH)
        fwrite(sch, fread(sch).replace('(property "Value" "10k"', '(property "Value" "22k"', 1))
        expect_run(f, "build after a hand edit (the generator is run in a copy)", s4_build(proj, "sch", S4_TRACE=trace),
                   3, "NOT WRITTEN")
        expect(f, len(fread(trace).split()) >= 2, "the generator was not run in a copy: %r" % fread(trace))
        expect(f, not traced(proj), "a generator ran outside the project: %r" % traced(proj))
        expect(f, os.path.isdir(scratch) and not os.listdir(scratch), ".hwtmp/ was not left empty")
        expect(f, fread(ignore).count(".hwtmp") == 1, ".gitignore got the line twice: %r" % fread(ignore))
        proj = ctx.fx.make_project(os.path.join(tmp, "q"))
        gen = os.path.join(proj, "scripts", "gen_sch.py")
        if not expect_run(f, "first build sch (second project)", build_run(proj, "sch"), 0, "done: sch"):
            return f
        os.remove(os.path.join(proj, "design", "ownership.csv"))
        fwrite(gen, fread(gen) + S4_TRACE)
        os.remove(trace)
        cmd = '"%s" scripts/gen_sch.py hardware/fixture.kicad_sch' % sys.executable
        expect_run(f, "--adopt --reproduce", s4_build(proj, "--adopt", "--reproduce", cmd, S4_TRACE=trace), 0,
                   "recorded as script-owned")
        expect(f, os.path.isfile(trace) and not traced(proj), "the project's own build ran outside the project: %r"
               % traced(proj))
        scratch = os.path.join(proj, ".hwtmp")
        expect(f, os.path.isdir(scratch) and not os.listdir(scratch), ".hwtmp/ was not left empty after --reproduce")
        expect(f, "/.hwtmp/" in fread(os.path.join(proj, ".gitignore")).splitlines(), "no .gitignore line was written")
    return f


def test_s4_build_lock(ctx):
    """KiCad's lock file beside the project file stops the build, and --adopt too."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_project(os.path.join(tmp, "p"))
        lock = os.path.join(proj, "hardware", "~fixture.kicad_pro.lck")
        fwrite(lock, "")
        expect_run(f, "build with the project lock file", build_run(proj, "sch"), 5, "KiCad lock file found",
                   "~fixture.kicad_pro.lck")
        expect(f, os.listdir(os.path.join(proj, "hardware")) == ["~fixture.kicad_pro.lck"], "the build wrote files")
        pro = os.path.join(proj, "hardware", "fixture.kicad_pro")
        fwrite(pro, "{}\n")
        expect_run(f, "--adopt with the lock file", build_run(proj, "--adopt"), 5, "KiCad lock file found")
        expect(f, not os.path.isfile(os.path.join(proj, "design", "ownership.csv")), "--adopt wrote a record")
        expect(f, os.path.isfile(lock), "the lock file was removed")
        os.remove(lock)
        os.remove(pro)
        expect_run(f, "build with no lock file", build_run(proj, "sch"), 0, "done: sch")
    return f


def test_s4_copy_list(ctx):
    """--copy-skill-scripts takes its list from the scripts folder, so a new script is copied."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        skill = os.path.join(tmp, "skill", "scripts")
        shutil.copytree(ctx.scripts, skill, ignore=shutil.ignore_patterns("__pycache__"))
        fwrite(os.path.join(skill, "newcheck.py"), '"""A script added later (test only)."""\n')
        fwrite(os.path.join(skill, ".hidden"), "x\n")
        fwrite(os.path.join(skill, "old.pyc"), "x\n")
        proj = os.path.join(tmp, "p")
        os.makedirs(proj)
        expect_run(f, "copy", run([sys.executable, os.path.join(skill, "build.py"), "--copy-skill-scripts", proj]), 0,
                   "copied")
        want = sorted(n for n in os.listdir(skill) if os.path.isfile(os.path.join(skill, n))
                      and not n.startswith(".") and not n.endswith(".pyc"))
        got = sorted(os.listdir(os.path.join(proj, SK))) if os.path.isdir(os.path.join(proj, SK)) else []
        expect(f, got == want, "copied %r, the folder holds %r" % (got, want))
        expect(f, "newcheck.py" in got and "spice.py" in got and "schlib.py" in got, "a script is missing: %r" % got)
        expect(f, all(fread(os.path.join(proj, SK, n), "rb") == fread(os.path.join(skill, n), "rb") for n in got),
               "a copy has other bytes")
    return f


S4_SKIP = '''
_p, _t = os.path.join(HW, "extra.kicad_sym"), "(kicad_symbol_lib)\\n"
if not os.path.isfile(_p) or open(_p).read() != _t:
    hwcommon.write_text(_p, _t)
'''
S4_DECLARE = '''
if os.environ.get("HWSKILLS_OUTPUTS"):
    with open(os.environ["HWSKILLS_OUTPUTS"], "a") as _d:
        _d.write("\\n".join(%s) + "\\n")
'''


def test_s4_build_stale_skip(ctx):
    """The stale-file stop does not fire for a generator that skips writing unchanged files, with or
    without a declared list; a file truly dropped still stops the build."""
    f = []
    extra = "hardware/extra.kicad_sym"
    with tempfile.TemporaryDirectory() as tmp:
        proj = ctx.fx.make_project(os.path.join(tmp, "p"))
        gen = os.path.join(proj, "scripts", "gen_sch.py")
        clean = fread(gen)
        fwrite(gen, clean + S4_SKIP)
        if not expect_run(f, "first build sch", build_run(proj, "sch"), 0, "done: sch"):
            return f
        res = build_run(proj, "sch")
        expect_run(f, "second build, the unchanged file not written again, nothing declared", res, 0,
                   "done: sch", "not written again")
        expect(f, extra in ownership(ctx, proj), "the row of the unchanged file was dropped")
        fwrite(gen, clean + S4_SKIP + S4_DECLARE % "[OUT, _p]")
        res = build_run(proj, "sch")
        expect_run(f, "the same, with the file declared", res, 0, "done: sch")
        expect(f, "not written again" not in res[1], "a declared file was checked in a copy all the same")
        fwrite(gen, clean + S4_DECLARE % "[OUT]")
        expect_run(f, "the generator no longer writes or declares the file", build_run(proj, "sch"), 3,
                   "NOT WRITTEN BY THE GENERATOR ANY MORE", extra)
        expect(f, os.path.isfile(os.path.join(proj, extra)), "the build deleted the file")
        fwrite(gen, clean)
        expect_run(f, "the generator no longer writes the file and declares nothing", build_run(proj, "sch"), 3,
                   "NOT WRITTEN BY THE GENERATOR ANY MORE", extra)
        expect(f, os.path.isfile(os.path.join(proj, extra)), "the build deleted the file")
    return f


SCRIPT_TESTS += [
    ("S4 build.py: settings from design/build.json", test_s4_build_settings),
    ("S4 build.py: the project checks hook", test_s4_build_checks),
    ("S4 build.py: scratch files only in .hwtmp/", test_s4_build_scratch),
    ("S4 build.py: the lock file of the project stops the build", test_s4_build_lock),
    ("S4 build.py: the copy list comes from the scripts folder", test_s4_copy_list),
    ("S4 build.py: a generator that skips unchanged files is not stopped", test_s4_build_stale_skip),
]

# ---- S4, schlib.py. A fake symbol library and footprint folder, so these run without KiCad.

def s4_sym(name, units, datasheet="~", description="", extra=""):
    """A library symbol. units: [[(pin number, pin name, x, y, angle)]], one list per unit."""
    out = ('\t(symbol "%s"\n%s\t\t(exclude_from_sim no)\n'
           '\t\t(property "Reference" "X"\n\t\t\t(at 2.032 0 90)\n\t\t)\n'
           '\t\t(property "Value" "%s"\n\t\t\t(at 0 0 90)\n\t\t)\n'
           '\t\t(property "Footprint" ""\n\t\t\t(at 0 0 0)\n\t\t)\n'
           '\t\t(property "Datasheet" "%s"\n\t\t\t(at 0 0 0)\n\t\t)\n'
           '\t\t(property "Description" "%s"\n\t\t\t(at 0 0 0)\n\t\t)\n' % (name, extra, name, datasheet, description))
    for i, pins in enumerate(units):
        out += '\t\t(symbol "%s_%d_1"\n' % (name, i + 1)
        for num, pname, x, y, ang in pins:
            out += ('\t\t\t(pin passive line\n\t\t\t\t(at %s %s %d)\n\t\t\t\t(length 1.27)\n\t\t\t\t(name "%s")\n'
                    '\t\t\t\t(number "%s")\n\t\t\t)\n' % (x, y, ang, pname, num))
        out += '\t\t)\n'
    return out + '\t)\n'


S4_LIB_HEAD = '(kicad_symbol_lib\n\t(version 20241209)\n\t(generator "test")\n'
S4_DEVICE = (S4_LIB_HEAD
             + s4_sym("R", [[("1", "~", 0, 3.81, 270), ("2", "~", 0, -3.81, 90)]], description="Resistor")
             + s4_sym("DUAL", [[("1", "A", -5.08, 0, 0), ("2", "B", 5.08, 0, 180)],
                               [("3", "C", -5.08, 0, 0), ("4", "D", 5.08, 0, 180)]], description="Two units")
             + s4_sym("TRI", [[("1", "~", 0, 3.81, 270), ("2", "~", 0, -3.81, 90), ("3", "~", 2.54, 0, 180)]])
             + s4_sym("REG1", [[("1", "IN", -5.08, 0, 0), ("2", "OUT", 5.08, 0, 180)]],
                      datasheet="library/reg1.pdf", description="REG1 regulator")
             + ")\n")
S4_POWER = (S4_LIB_HEAD
            + "".join(s4_sym(n_, [[("1", "~", 0, 0, 90)]], extra="\t\t(power global)\n",
                             description='Power symbol creates a global label with name \\"%s\\"' % n_)
                      for n_ in ("+5V", "GND", "PWR_FLAG"))
            + ")\n")
S4_FP = "Resistor_SMD:R_0603_1608Metric"
S4_RAILS = "rail,kind,voltage,source,note\n+5V,supply,5,J1,\nGND,ground,0,,\n+7V5,supply,7.5,U1,\n"
S4_MODULES = ("module,sheet,ref_block,purpose\nalpha,alpha.kicad_sch,100-102,first\n"
              "beta,beta.kicad_sch,200-299,second\n")
S4_NETS = "net,modules,note\nNET_A,alpha;beta,a signal\nNET_B,beta,a test net\n"
S4_PART_ROW = "%s,%s,%s,0603,Maker A,%s,SUPPLIER-A,SA-1,pull,,,1%%,50 V,0.01,0.005,1000,2026-01-02,active,,1,,,,%s,,,yes,yes,,no"


class S4Sch:
    """A project in a temporary folder for the schlib tests: fake libraries, and the design files given."""

    def __init__(self, ctx, tmp, name="p", **files):
        self.schlib = ctx.module("schlib")
        self.symdir, fpdir = os.path.join(tmp, "sym"), os.path.join(tmp, "fp", "Resistor_SMD.pretty")
        os.makedirs(self.symdir, exist_ok=True)
        os.makedirs(fpdir, exist_ok=True)
        fwrite(os.path.join(self.symdir, "Device.kicad_sym"), S4_DEVICE)
        fwrite(os.path.join(self.symdir, "power.kicad_sym"), S4_POWER)
        fwrite(os.path.join(fpdir, "R_0603_1608Metric.kicad_mod"), '(footprint "R_0603_1608Metric")\n')
        self.fpdir = os.path.dirname(fpdir)
        self.proj = os.path.join(tmp, name)
        self.hw, self.design = os.path.join(self.proj, "hardware"), os.path.join(self.proj, "design")
        os.makedirs(self.hw)
        os.makedirs(self.design)
        self.path = os.path.join(self.hw, "t.kicad_sch")
        for key, text in files.items():
            self.put(key, text)

    def put(self, key, text):
        """put("rails_csv", text) writes design/rails.csv; None removes the file."""
        path = os.path.join(self.design, key.replace("_", ".") if "_" in key else key)
        path = os.path.join(self.design, {"module_nets_csv": "module-nets.csv"}.get(key, os.path.basename(path)))
        if text is None:
            if os.path.isfile(path):
                os.remove(path)
        else:
            fwrite(path, text)

    def new(self, **kw):
        return self.schlib.Schematic(self.path, symbol_dir=self.symdir, footprint_dir=self.fpdir,
                                     date="2026-01-02", **kw)

    def refused(self, f, what, call, *texts):
        """call(schematic) must raise SchematicError, and the message must hold every text."""
        try:
            call(self.new())
        except self.schlib.SchematicError as e:
            for t in texts:
                expect(f, t in str(e), "%s: the refusal lacks %r: %s" % (what, t, e))
            return
        f.append("%s: not refused" % what)

    def read(self, name="t.kicad_sch"):
        return fread(os.path.join(self.hw, name))


def test_s4_rails(ctx):
    """power() only for a rail declared in design/rails.csv; a project power symbol named as the rail."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        p = S4Sch(ctx, tmp, rails_csv=S4_RAILS)
        s = p.new()
        a = s.root.power("+5V", 10, 10)
        s.root.power("GND", 10, 20)
        s.root.power("PWR_FLAG", 12, 10)
        expect(f, a["1"] == (10, 10) and a.ref == "#PWR01", "+5V placed as %s at %r" % (a.ref, dict(a)))
        lib_id = s.make_power_symbol("+7V5", like="+5V")
        s.root.power("+7V5", 20, 10)
        code, msgs = s.write()
        if expect(f, code == 0 and lib_id == "t:+7V5", "declared rails: code %s, %r, symbol %s" % (code, msgs, lib_id)):
            sym, root = p.read("t.kicad_sym"), p.read()
            expect(f, '(symbol "+7V5"' in sym and '"+7V5_1_1"' in sym and "+5V" not in sym,
                   "the project power symbol is not named as the rail throughout")
            expect(f, '(lib_id "t:+7V5")' in root and '(property "Value" "+7V5"' in root,
                   "the rail is not drawn with its project symbol")
            expect(f, '(lib_id "power:+5V")' in root and '(lib_id "power:PWR_FLAG")' in root, "stock symbols not used")
        p.refused(f, "a name that is not a declared rail", lambda s: s.root.power("+3V3", 1, 1),
                  "design/rails.csv", "+3V3")
        p.refused(f, "a declared rail with no stock symbol", lambda s: s.root.power("+7V5", 1, 1),
                  "+7V5", "make_power_symbol")
        p.refused(f, "a project power symbol for a name that is not a rail",
                  lambda s: s.make_power_symbol("+9V", like="+5V"), "design/rails.csv", "+9V")
        p.refused(f, "a project power symbol from a stock symbol that is not there",
                  lambda s: s.make_power_symbol("+7V5", like="+99V"), "+99V")
        p.refused(f, "a rail as a sheet pin",
                  lambda s: s.add_sheet("A", "a.kicad_sch", pins=[("GND", "input", "left", 2)]), "GND", "rail")
        p.refused(f, "a rail as a net label", lambda s: s.root.label("GND", 1, 1), "GND", "rail")
        p.put("rails_csv", "rail,kind,voltage,source,note\n+5V,supply,5,J1,\n+5V,supply,5,J2,\n")
        p.refused(f, "a rail in two rows", lambda s: s, "design/rails.csv", "+5V")
        p.put("rails_csv", None)
        s = p.new()
        s.root.power("+5V", 10, 10)
        expect(f, any("design/rails.csv" in x for x in s.notes), "no note that the rail names were not checked")
    return f


def test_s4_blocks(ctx):
    """Designators come from the module's block in design/modules.csv, for every prefix."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        p = S4Sch(ctx, tmp, modules_csv=S4_MODULES)

        def make(first=1):
            s = p.new()
            al, be = s.add_sheet("alpha", "alpha.kicad_sch"), s.add_sheet("beta", "beta.kicad_sch", at=(30, 10))
            refs = [al.place("Device:R", "R", "1k", 10, 10 + 5 * i, footprint=S4_FP).ref for i in range(first)]
            return s, al, be, refs
        s, al, be, refs = make(3)
        got = refs + [be.place("Device:R", "R", "1k", 10, 10, footprint=S4_FP).ref,
                      be.place("Device:DUAL", "U", "x", 20, 10, footprint=S4_FP).ref,
                      be.power("GND", 30, 10).ref, s.root.place("Device:R", "R", "1k", 5, 5, footprint=S4_FP).ref]
        expect(f, got == ["R100", "R101", "R102", "R200", "U200", "#PWR200", "R1"], "designators: %r" % got)
        try:
            al.place("Device:R", "R", "1k", 10, 40, footprint=S4_FP)
            f.append("a fourth R in the block 100-102 was not refused")
        except p.schlib.SchematicError as e:
            expect(f, "100-102" in str(e) and "alpha" in str(e) and "design/modules.csv" in str(e),
                   "overflow message: %s" % e)
        one = make(1)[2].place("Device:R", "R", "1k", 10, 10, footprint=S4_FP).ref
        two = make(2)[2].place("Device:R", "R", "1k", 10, 10, footprint=S4_FP).ref
        expect(f, one == two == "R200", "a part added on one sheet renumbered another: %s, %s" % (one, two))
        s, al, be, refs = make(1)
        got = [be.place("Device:R", "R", "1k", 10, 10, footprint=S4_FP, designator="R200").ref,
               be.place("Device:R", "R", "1k", 10, 15, footprint=S4_FP).ref]
        expect(f, got == ["R200", "R201"], "a given designator and the next free one: %r" % got)
        place = lambda sheet, ref: (lambda s: getattr(s.add_sheet("alpha", "alpha.kicad_sch") if sheet else s.root,
                                                      "place")("Device:R", "R", "1k", 1, 1, footprint=S4_FP,
                                                               designator=ref))
        p.refused(f, "a designator outside its module's block", place(True, "R250"), "R250", "100-102", "alpha")
        p.refused(f, "a designator with another prefix", place(True, "C100"), "C100")
        p.refused(f, "a designator of a module's block on a sheet that is not the module", place(False, "R100"),
                  "R100", "alpha")
        try:
            be.place("Device:R", "R", "1k", 10, 20, footprint=S4_FP, designator="R200")
            f.append("a designator used twice was not refused")
        except p.schlib.SchematicError:
            pass
        for what, text, said in (
                ("a block that is not two numbers", "alpha,alpha.kicad_sch,abc,x\n", "ref_block"),
                ("a block that runs backwards", "alpha,alpha.kicad_sch,200-100,x\n", "ref_block"),
                ("two blocks that overlap", "alpha,alpha.kicad_sch,100-199,x\nbeta,beta.kicad_sch,150-250,y\n", "overlap"),
                ("one sheet for two modules", "alpha,a.kicad_sch,100-199,x\nbeta,a.kicad_sch,200-299,y\n", "a.kicad_sch"),
                ("one module in two rows", "alpha,a.kicad_sch,100-199,x\nalpha,b.kicad_sch,200-299,y\n", "alpha")):
            p.put("modules_csv", "module,sheet,ref_block,purpose\n" + text)
            p.refused(f, what, lambda s: s, "design/modules.csv", said)
        p.put("modules_csv", None)
        s = p.new()
        got = [s.add_sheet("alpha", "alpha.kicad_sch").place("Device:R", "R", "1k", 1, 1, footprint=S4_FP).ref,
               s.root.place("Device:R", "R", "1k", 5, 5, footprint=S4_FP).ref]
        expect(f, got == ["R1", "R2"], "with no modules.csv the designators are %r" % got)
    return f


def test_s4_multi_unit(ctx):
    """unit() places another unit of a part under the same designator."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        p = S4Sch(ctx, tmp)
        s = p.new()
        u = s.root.place("Device:DUAL", "U", "x", 10, 10, footprint=S4_FP)
        expect(f, any("U1" in x and "unit 2" in x for x in s.check()), "an unplaced unit is not reported: %r" % s.check())
        b = s.root.unit(u, 2, 30, 10, rot=180)
        expect(f, b.ref == u.ref == "U1" and sorted(u) == ["1", "2", "A", "B"] and sorted(b) == ["3", "4", "C", "D"],
               "units: %s %r, %s %r" % (u.ref, sorted(u), b.ref, sorted(b)))
        expect(f, (u["1"], u["2"], b["3"], b["4"]) == ((8, 10), (12, 10), (32, 10), (28, 10)),
               "unit pins at %r %r" % (dict(u), dict(b)))
        expect(f, s.root.place("Device:R", "R", "1k", 5, 5, footprint=S4_FP).ref == "R1"
               and s.root.place("Device:DUAL", "U", "x", 10, 30, footprint=S4_FP).ref == "U2", "the next designators")
        s.root.unit(s.root.place("Device:DUAL", "U", "x", 10, 40, footprint=S4_FP, unit=2), 1, 30, 40)
        expect(f, any("U2" in x and "unit 2" in x for x in s.check()) and not any("U1" in x or "U3" in x for x in s.check()),
               "unplaced units: %r" % s.check())
        s = p.new()
        u = s.root.place("Device:DUAL", "U", "x", 10, 10, footprint=S4_FP)
        s.root.unit(u, 2, 30, 10)
        code, msgs = s.write()
        if expect(f, code == 0 and msgs[-1].endswith("1 symbols"), "written: %s %r" % (code, msgs)):
            text = p.read()
            expect(f, text.count('(reference "U1")') == 2 and text.count("\n\t\t(unit 2)\n") == 1
                   and text.count('(property "Reference" "U1"') == 2, "the two units are not one part in the file")
            ids = re.findall(r'\(dnp no\)\n\t\t\(uuid "([^"]+)"', text)
            expect(f, len(set(ids)) == 2, "the two units share an ID: %r" % ids)
        two = lambda s: s.root.place("Device:DUAL", "U", "x", 10, 10, footprint=S4_FP)
        p.refused(f, "a unit the symbol does not have", lambda s: s.root.unit(two(s), 3, 1, 1), "unit 3", "U1")
        p.refused(f, "the first unit placed again", lambda s: s.root.unit(two(s), 1, 1, 1), "unit 1", "U1")

        def twice(s):
            u = two(s)
            s.root.unit(u, 2, 1, 1)
            s.root.unit(u, 2, 5, 5)
        p.refused(f, "a unit placed twice", twice, "unit 2", "U1")
        p.refused(f, "a second unit of a one-unit part",
                  lambda s: s.root.unit(s.root.place("Device:R", "R", "1k", 1, 1, footprint=S4_FP), 2, 5, 5), "unit 2")
    return f


def s4_points(text, kind):
    return [(float(a), float(b)) for a, b in re.findall(r"\(%s (-?[\d.]+) (-?[\d.]+)" % kind, text)]


def test_s4_drawing(ctx):
    """The midway helper and the centring helper."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        p = S4Sch(ctx, tmp)
        s = p.new()
        mid = lambda sch, a, b, sym="Device:R": sch.root.midway(sym, "R", "1k", a, b, footprint=S4_FP)
        r1, r2, r3 = mid(s, (10, 5), (10, 15)), mid(s, (20, 15), (20, 5)), mid(s, (5, 30), (16, 30))
        expect(f, (r1["1"], r1["2"]) == ((10, 8.5), (10, 11.5)), "midway, downwards: %r" % dict(r1))
        expect(f, (r2["1"], r2["2"]) == ((20, 11.5), (20, 8.5)), "midway, upwards (pin 1 to the first point): %r" % dict(r2))
        expect(f, (r3["1"], r3["2"]) == ((9, 30), (12, 30)), "midway, across: %r" % dict(r3))
        code, msgs = s.write()
        if expect(f, code == 0, "midway: not written: %r" % msgs):
            text = p.read()
            for a, b in (((10, 5), (10, 8.5)), ((10, 11.5), (10, 15)), ((5, 30), (9, 30)), ((12, 30), (16, 30))):
                want = "(xy %s %s) (xy %s %s)" % tuple(p.schlib.mm(v) for v in a + b)
                expect(f, want in text, "midway: no wire %r to %r" % (a, b))
        p.refused(f, "midway between points not in line", lambda s: mid(s, (1, 1), (5, 6)), "in line")
        p.refused(f, "midway with a part of three pins", lambda s: mid(s, (1, 1), (1, 20), "Device:TRI"), "two pins")
        p.refused(f, "midway in a gap shorter than the part", lambda s: mid(s, (1, 1), (1, 3)), "too short")
        p.refused(f, "midway between one point and itself", lambda s: mid(s, (1, 1), (1, 1)))

        def draw(s):
            box = s.add_sheet("Child", "child.kicad_sch", at=(4, 4), size=(10, 4), pins=[("A", "input", "right", 2)])
            box.hier_label("A", 5, 5)
            r = s.root.place("Device:R", "R", "1k", 30, 4, footprint=S4_FP)
            s.root.wire(box.pins["A"], (30, 6), r["2"])
            s.root.frame("Block", 2, 1, 34, 12)
            return r
        s = p.new()
        r = draw(s)
        s.write()
        plain = p.read()
        s = p.new()
        r = draw(s)
        dx, dy = s.root.centre()
        code, msgs = s.write()
        text = p.read()
        expect(f, code == 0 and (dx, dy) != (0, 0) and dx == int(dx) and dy == int(dy),
               "centre: code %s, shift %r" % (code, (dx, dy)))
        expect(f, r["2"] == (30, 5.5), "centre() changed the positions the generator works with: %r" % dict(r))
        for kind in ("at", "xy", "start", "end"):
            a, b = s4_points(plain, kind), s4_points(text, kind)
            moved = set((round(x2 - x1, 3), round(y2 - y1, 3)) for (x1, y1), (x2, y2) in zip(a, b))
            lib = set([(0.0, 0.0)])         # coordinates inside lib_symbols stay
            expect(f, len(a) == len(b) and moved - lib == set([(round(dx * 2.54, 3), round(dy * 2.54, 3))]),
                   "centre: (%s ...) moved by %r, not by one shift of %r U" % (kind, sorted(moved), (dx, dy)))
        body = text.split("(lib_symbols", 1)[1]
        body = body[body.index("\n\t)\n"):]
        pts = [q_ for kind in ("at", "xy", "start", "end") for q_ in s4_points(body, kind)]
        xs, ys = [x for x, _ in pts], [y for _, y in pts]
        if expect(f, bool(pts), "centre: no coordinates read"):
            expect(f, min(xs) >= 10 and max(xs) <= 287 and min(ys) >= 10 and max(ys) <= 168,
                   "centre: the drawing is not clear of the border and the title block: x %s..%s y %s..%s"
                   % (min(xs), max(xs), min(ys), max(ys)))
            expect(f, abs((min(xs) + max(xs)) / 2 - 148.5) <= 1.3 and abs((min(ys) + max(ys)) / 2 - 89) <= 1.3,
                   "centre: the drawing's middle is at %.1f, %.1f mm" % ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))

        def wide(s):
            s.root.place("Device:R", "R", "1k", 5, 5, footprint=S4_FP)
            s.root.place("Device:R", "R", "1k", 125, 5, footprint=S4_FP)
            s.root.centre()
        p.refused(f, "centring a drawing larger than the page", wide, "A4")
        s = p.new(paper="A3")
        s.root.place("Device:R", "R", "1k", 5, 5, footprint=S4_FP)
        s.root.place("Device:R", "R", "1k", 125, 5, footprint=S4_FP)
        expect(f, s.root.centre() is not None, "the same drawing was refused on a larger page")
        p.refused(f, "centring an empty sheet", lambda s: s.root.centre(), "nothing")
    return f


def test_s4_skeleton(ctx):
    """skeleton(): a top sheet of boxes and one sub-sheet per row of design/modules.csv."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        p = S4Sch(ctx, tmp, modules_csv=S4_MODULES, module_nets_csv=S4_NETS, rails_csv=S4_RAILS)
        s = p.new()
        sheets = s.skeleton()
        expect(f, sorted(sheets) == ["alpha", "beta"] and [x.file for x in s.sheets] == ["alpha.kicad_sch",
                                                                                        "beta.kicad_sch"],
               "sheets: %r" % [x.file for x in s.sheets])
        expect(f, sorted(sheets["alpha"].pins) == ["NET_A"] and sorted(sheets["beta"].pins) == ["NET_A", "NET_B"],
               "edge pins from module-nets.csv: %r, %r" % (sorted(sheets["alpha"].pins), sorted(sheets["beta"].pins)))
        code, msgs = s.write()
        if expect(f, code == 0, "empty skeleton: %s %r" % (code, msgs)):
            root, beta = p.read(), p.read("beta.kicad_sch")
            expect(f, root.count("\t(sheet\n") == 2 and root.count('(pin "NET_A" bidirectional') == 2
                   and root.count('(label "NET_A"') == 2, "the top sheet lacks the boxes, their pins or the net labels")
            expect(f, '(hierarchical_label "NET_A"' in beta and '(hierarchical_label "NET_B"' in beta,
                   "a sub-sheet lacks its edge labels")
            boxes = re.findall(r"\t\(sheet\n\t\t\(at ([\d.]+) ([\d.]+)\)\n\t\t\(size ([\d.]+) ([\d.]+)\)", root)
            (x1, y1, w1, h1), (x2, y2, w2, h2) = [tuple(float(v) for v in b) for b in boxes]
            expect(f, x1 + w1 < x2 or y1 + h1 < y2, "the two boxes overlap: %r" % (boxes,))
        drawn = []

        def draw_alpha(sheet):
            r = sheet.place("Device:R", "R", "1k", 20, 10, footprint=S4_FP)
            sheet.hier_label("OUT", 20, 5, "output")
            sheet.wire((20, 5), r["1"])
            drawn.append((sheet.name, r.ref))

        class BetaFile:                     # a module file, as a generator would import it
            NAME, FILE, AT, SIZE = "beta", "beta.kicad_sch", (40, 30), (12, 6)
            PINS = [("IN", "input", "left", 3)]

            @staticmethod
            def draw(sheet):
                sheet.hier_label("IN", 5, 5, "input")
                drawn.append((sheet.name, sheet.place("Device:R", "R", "1k", 20, 10, footprint=S4_FP).ref))
        s = p.new()
        sheets = s.skeleton([{"name": "alpha", "at": (8, 8), "size": (10, 4),
                              "pins": [("OUT", "output", "right", 2)], "draw": draw_alpha}, BetaFile], labels=False)
        expect(f, drawn == [("alpha", "R100"), ("beta", "R200")], "draw functions and their designators: %r" % drawn)
        expect(f, (sheets["alpha"].at, sheets["beta"].at, sheets["beta"].size) == ((8, 8), (40, 30), (12, 6))
               and sheets["alpha"].pins == {"OUT": (18, 10)}, "the box positions and pins given were not used")
        code, msgs = s.write()
        expect(f, code == 0 and "(label " not in p.read(), "skeleton with draw functions: %s %r" % (code, msgs))
        spec = lambda **kw: (lambda s: s.skeleton([dict({"name": "alpha"}, **kw)]))
        p.refused(f, "a module file for a module not in modules.csv", spec(name="gamma"), "gamma", "design/modules.csv")
        p.refused(f, "a module file naming another sheet file", spec(file="other.kicad_sch"), "other.kicad_sch", "alpha")
        p.refused(f, "a rail as an edge pin", spec(pins=[("+5V", "input", "left", 1)]), "+5V", "rail")
        p.refused(f, "one module given twice", lambda s: s.skeleton([{"name": "alpha"}, {"name": "alpha"}]), "alpha")
        p.refused(f, "a module file with no name", lambda s: s.skeleton([{"at": (1, 1)}]), "name")
        p.put("module_nets_csv", "net,modules,note\nNET_A,alpha;gamma,x\n")
        p.refused(f, "a net row naming a module not in modules.csv", lambda s: s.skeleton(), "design/module-nets.csv",
                  "gamma")
        p.put("module_nets_csv", "net,modules,note\n+5V,alpha;beta,x\n")
        p.refused(f, "a rail as a net between modules", lambda s: s.skeleton(), "+5V", "rail")
        p.put("modules_csv", None)
        p.refused(f, "a skeleton with no modules.csv", lambda s: s.skeleton(), "design/modules.csv")
    return f


S4_FIRMWARE = """# Firmware instructions: fixture
## alpha
can: NET_A on pin 3; the level of the input; 0 to 3.3 V; 1 kHz. Source: sheet alpha. Status: decided with the user (DC-001)
must: switch the output off; reads NET_A; threshold 2.5 V; respond within 10 ms. Source: DC-001. Status: stated by a worker, not decided
## Across modules
must: hold NET_B low at start; reads nothing; threshold none; respond within the time not given. Source: report. Status: missing: the response time; only guard at start-up
"""


def test_s4_firmware_page(ctx):
    """firmware_page(): the closing text sheet, generated from design/firmware.md, each line with its status."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        p = S4Sch(ctx, tmp, firmware_md=S4_FIRMWARE)
        s = p.new()
        s.add_sheet("Child", "child.kicad_sch")
        page = s.firmware_page()
        code, msgs = s.write()
        if expect(f, code == 0 and s.sheets[-1] is page and page.file == "firmware.kicad_sch",
                  "firmware page: %s %r" % (code, msgs)):
            text = " ".join(re.findall(r'\(text "((?:[^"\\]|\\.)*)"', p.read("firmware.kicad_sch")))
            for want in ("Firmware instructions: fixture", "alpha", "Across modules", "NET_A on pin 3",
                         "respond within 10 ms", "DECIDED", "NOT DECIDED", "MISSING", "the response time",
                         "only guard at start-up", "decided with the user (DC-001)",
                         "3 lines: 1 decided, 1 not decided, 1 missing"):
                expect(f, want in text, "the firmware page lacks %r" % want)
            words = set(re.findall(r"[A-Za-z0-9_.]+", S4_FIRMWARE))
            expect(f, not [w for w in ("2.5", "kHz", "DC-001", "NET_B") if w not in text],
                   "a figure of the source is not on the page")
            root = p.read()
            expect(f, root.rindex('"Sheetfile" "firmware.kicad_sch"') > root.rindex('"Sheetfile" "child.kicad_sch"')
                   and '(page "3")' in root, "the firmware page is not the last sheet")
            expect(f, "(symbol" not in p.read("firmware.kicad_sch").split("(lib_symbols", 1)[1],
                   "the firmware page holds a symbol")
            del words

        def later(s):
            s.firmware_page()
            s.add_sheet("Late", "late.kicad_sch")
        p.refused(f, "a sheet added after the closing sheet", later, "last")
        p.refused(f, "a second firmware page", lambda s: (s.firmware_page(), s.firmware_page()))
        for what, old, new, said in (
                ("a line with no status", " Status: stated by a worker, not decided", "", "line 4"),
                ("a status that is none of the three", "stated by a worker, not decided", "probably fine", "line 4"),
                ("a decided line with no decision", "decided with the user (DC-001)", "decided with the user", "line 3"),
                ("a missing line that does not say what", "missing: the response time", "missing:", "line 6"),
                ("a line with no source", " Source: sheet alpha.", "", "line 3"),
                ("a line that is no heading, can or must", "## Across modules", "also: something", "line 5")):
            p.put("firmware_md", S4_FIRMWARE.replace(old, new))
            s = p.new()
            s.firmware_page()
            code, msgs = s.write()
            expect(f, code == 1 and any("design/firmware.md" in m and said in m for m in msgs),
                   "%s: code %s, %r" % (what, code, msgs))
        many = S4_FIRMWARE + "".join("can: signal %d of many; meaning; range; speed. Source: report. Status: missing: "
                                     "the range\n" % i for i in range(150))
        p.put("firmware_md", many)
        s = p.new()
        page = s.firmware_page()
        text = "".join(page.items)
        expect(f, page.paper != "A4" and "signal 149 of many" in text and "153 lines" in text,
               "a long list: paper %s" % page.paper)
        ys = [y for _, y in s4_points(text, "at")]
        height = {"A3": 297, "A2": 420, "A1": 594, "A0": 841}.get(page.paper, 0)
        expect(f, ys and max(ys) <= height - 46, "a long list runs into the title block: lowest text at %s on %s"
               % (max(ys) if ys else None, page.paper))
        p.put("firmware_md", None)
        p.refused(f, "no design/firmware.md", lambda s: s.firmware_page(), "design/firmware.md")
    return f


def test_s4_datasheet_field(ctx):
    """The Datasheet and Description of a symbol never come from a library symbol that is another part."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        header = ctx.fx.PARTS_CSV.splitlines()[0]
        rows = [S4_PART_ROW % ("U1", "REG1", S4_FP, "REG1", ""),
                S4_PART_ROW % ("U2", "OTHER9", S4_FP, "OTHER9", ""),
                S4_PART_ROW % ("U3", "OTHER9", S4_FP, "OTHER8", "datasheets/OTHER8.pdf"),
                S4_PART_ROW % ("R1", "1k", S4_FP, "RES-1K", ""),
                S4_PART_ROW % ("U4", "MADE1", S4_FP, "MADE1", "")]
        p = S4Sch(ctx, tmp, parts_csv="\n".join([header] + rows) + "\n")
        s = p.new()
        for i in range(3):
            s.root.place("Device:REG1", "U", None, 10, 10 + 10 * i)
        s.root.place("Device:R", "R", None, 30, 10)
        made = s.make_symbol("MADE1", S4_FP, "datasheets/MADE1.pdf", "made for this part", ((-5.08, -2.54), (5.08, 2.54)),
                             [("1", "A", "passive", -7.62, 0, 0)])
        s.root.place(made, "U", None, 30, 30)
        code, msgs = s.write()
        if expect(f, code == 0, "not written: %r" % msgs):
            fields = {}
            for block in p.read().split("\t(symbol\n")[1:]:
                ref = re.search(r'\(property "Reference" "([^"]*)"', block).group(1)
                fields[ref] = dict((k, re.search(r'\(property "%s" "((?:[^"\\]|\\.)*)"' % k, block).group(1))
                                   for k in ("Datasheet", "Description"))
            expect(f, fields["U1"] == {"Datasheet": "library/reg1.pdf", "Description": "REG1 regulator"},
                   "the library symbol of the part itself: %r" % fields["U1"])
            expect(f, fields["U2"]["Datasheet"] == "" and "REG1" not in fields["U2"]["Description"]
                   and "OTHER9" in fields["U2"]["Description"], "a borrowed symbol, no link in parts.csv: %r" % fields["U2"])
            expect(f, fields["U3"]["Datasheet"] == "datasheets/OTHER8.pdf" and "REG1" not in fields["U3"]["Description"]
                   and "OTHER8" in fields["U3"]["Description"], "a borrowed symbol, link in parts.csv: %r" % fields["U3"])
            expect(f, fields["R1"] == {"Datasheet": "", "Description": "Resistor"},
                   "a general symbol: %r" % fields["R1"])
            expect(f, fields["U4"] == {"Datasheet": "datasheets/MADE1.pdf", "Description": "made for this part"},
                   "a project symbol: %r" % fields["U4"])
            notes = [m for m in msgs if m.startswith("note:")]
            expect(f, any("U2" in m and "design/parts.csv" in m and "REG1" in m for m in notes)
                   and not any("U1 " in m or "U4" in m for m in notes), "notes: %r" % notes)
    return f


def test_s4_declared_files(ctx):
    """write() appends every file it wrote to the file named by HWSKILLS_OUTPUTS, for build.py."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        p = S4Sch(ctx, tmp)
        listing = os.path.join(tmp, "outputs.txt")
        old = os.environ.get("HWSKILLS_OUTPUTS")
        os.environ["HWSKILLS_OUTPUTS"] = listing
        try:
            s = p.new()
            s.add_sheet("Child", "child.kicad_sch")
            s.make_symbol("MADE1", S4_FP, "", "x", ((-5.08, -2.54), (5.08, 2.54)), [("1", "A", "passive", -7.62, 0, 0)])
            code, msgs = s.write()
        finally:
            if old is None:
                del os.environ["HWSKILLS_OUTPUTS"]
            else:
                os.environ["HWSKILLS_OUTPUTS"] = old
        got = sorted(os.path.basename(l) for l in fread(listing).split("\n") if l) if os.path.isfile(listing) else []
        want = sorted(n_ for n_ in os.listdir(p.hw))
        expect(f, code == 0 and got == want and "child.kicad_sch" in got and "t.kicad_pro" in got,
               "declared %r, written %r" % (got, want))
        expect(f, all(os.path.isabs(l) for l in fread(listing).split("\n") if l) if got else False,
               "the declared paths are not absolute")
        s = p.new()
        s.write()
        expect(f, fread(listing).count("t.kicad_sch") == 1, "files were declared with the variable not set")
    return f


def test_s4_kicad_skeleton(ctx):
    """The new schlib output against KiCad itself: a skeleton of two modules, a project power symbol, a
    part of several units, centred sheets and the firmware page. KiCad must read it, and its netlist
    must hold the nets as drawn."""
    ctx.need_cli()
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        p = S4Sch(ctx, tmp, modules_csv=S4_MODULES.replace("100-102", "100-199"), module_nets_csv=S4_NETS,
                  rails_csv=S4_RAILS, firmware_md=S4_FIRMWARE)
        s = p.schlib.Schematic(p.path, date="2026-01-02")
        s.make_power_symbol("+7V5", like="+5V")
        fp = "Resistor_SMD:R_0603_1608Metric"
        try:
            s.symbol("Amplifier_Operational:LM358")
            dual = "Amplifier_Operational:LM358"
        except p.schlib.SchematicError:
            dual = None

        def draw_alpha(sheet):
            sheet.hier_label("NET_A", 20, 10, "bidirectional")
            sheet.midway("Device:R", "R", "10k", (20, 10), (20, 22), footprint=fp)
            sheet.power("GND", 20, 22)
            if dual:
                u = sheet.place(dual, "U", "LM358", 40, 15, footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
                b = sheet.unit(u, 2, 60, 15)
                sheet.unit(u, 3, 80, 15)
                sheet.label("NET_C", *u["1"])
                sheet.label("NET_C", *b["7"])
            sheet.centre()

        def draw_beta(sheet):
            sheet.hier_label("NET_A", 20, 22, "bidirectional")
            sheet.hier_label("NET_B", 30, 22, "bidirectional")
            sheet.midway("Device:R", "R", "10k", (20, 10), (20, 22), footprint=fp)
            sheet.power("+7V5", 20, 10)
            sheet.midway("Device:R", "R", "10k", (30, 10), (30, 22), footprint=fp)
            sheet.power("+5V", 30, 10)
            sheet.centre()
        s.skeleton([{"name": "alpha", "draw": draw_alpha}, {"name": "beta", "draw": draw_beta}])
        s.firmware_page()
        s.root.centre()
        code, msgs = s.write()
        if not expect(f, code == 0, "the schematic was not written: %r" % msgs[-4:]):
            return f
        net = os.path.join(tmp, "t.net")
        res = run([ctx.cli, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", net, p.path])
        if not expect(f, res[0] == 0 and os.path.isfile(net), "netlist export failed: %s" % res[1][-300:]):
            return f
        comps, nets = ctx.h.read_netlist(net)[:2]
        got = dict((name.lstrip("/"), sorted("%s.%s" % (x[0], x[1]) for x in nodes)) for name, nodes in nets.items())
        refs = sorted(set(n_.split(".")[0] for v in got.values() for n_ in v))
        expect(f, [r for r in refs if r.startswith("R")] == ["R100", "R200", "R201"], "designators in KiCad: %r" % refs)
        expect(f, sorted(x.split(".")[0] for x in got.get("NET_A", [])) == ["R100", "R200"],
               "NET_A does not join the two modules through the top sheet: %r" % got.get("NET_A"))
        expect(f, [x.split(".")[0] for x in got.get("+7V5", [])] == ["R200"], "the project power symbol's net: %r"
               % got.get("+7V5"))
        expect(f, [x.split(".")[0] for x in got.get("GND", []) if x.startswith("R")] == ["R100"],
               "GND: %r" % got.get("GND"))
        expect(f, [x.split(".")[0] for x in got.get("+5V", [])] == ["R201"], "+5V: %r" % got.get("+5V"))
        if dual:
            key = [k for k in got if k.endswith("NET_C")]
            expect(f, len(key) == 1 and got[key[0]] == ["U100.1", "U100.7"],
                   "the two units of one part are not joined as drawn: %r" % [got[k] for k in key])
            expect(f, "U100.8" in got.get("+5V", []) + [x for v in got.values() for x in v], "unit 3 is not in the netlist")
        res = run([ctx.cli, "sch", "erc", "--format", "json", "--severity-all", "-o", os.path.join(tmp, "erc.json"), p.path])
        if expect(f, res[0] == 0 and os.path.isfile(os.path.join(tmp, "erc.json")), "ERC did not run: %s" % res[1][-300:]):
            erc = json.loads(fread(os.path.join(tmp, "erc.json")))
            sheets = [x.get("path") for x in erc.get("sheets", [])]
            expect(f, len(sheets) == 4, "KiCad reads %d sheets, not the top sheet, two modules and the firmware page: %r"
                   % (len(sheets), sheets))
            bad = [v.get("description", "") for x in erc.get("sheets", []) for v in x.get("violations", [])
                   if v.get("type") in ("hier_label_mismatch", "duplicate_reference", "missing_unit", "duplicate_sheet_names",
                                        "pin_not_connected") and not dual or v.get("type") in ("hier_label_mismatch",
                                                                                              "duplicate_reference",
                                                                                              "missing_unit")]
            expect(f, not bad, "ERC: %r" % bad[:6])
    return f


SCRIPT_TESTS += [
    ("S4 schlib: power() only for the rails of design/rails.csv", test_s4_rails),
    ("S4 schlib: designator blocks from design/modules.csv", test_s4_blocks),
    ("S4 schlib: the units of one part under one designator", test_s4_multi_unit),
    ("S4 schlib: the midway and centring helpers", test_s4_drawing),
    ("S4 schlib: the multi-sheet skeleton", test_s4_skeleton),
    ("S4 schlib: the firmware page", test_s4_firmware_page),
    ("S4 schlib: datasheet and description of a borrowed symbol", test_s4_datasheet_field),
    ("S4 schlib: the files written are declared to the build", test_s4_declared_files),
    ("S4 KiCad: skeleton, project power symbol, units, centring and the firmware page", test_s4_kicad_skeleton),
]
# ======================================================================== end of S4 section


# ======================================================================== S2 section (table_check additions, worstcase)

def s2(ctx, *args):
    return chk(ctx, "table_check.py", *args)


S2_ANSWER = """
## The user said "yes, go on with the second sheet" (DC-003)
Kind: question answered
Decided by: user
Date: 2026-01-05
Stage: ST5
Options: none
Reason: asked whether to go on
Affects: requirements none; parts none; schematic none; board none; cost none
Status: closed (answered)
"""


def test_s2_question_answered(ctx):
    """table_check decisions: the kind "question answered" passes in its light form, and fails when it
    holds options, a change or another status."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        log = os.path.join(proj, "design", "decisions.md")
        clean = fread(log)
        fwrite(log, clean + S2_ANSWER)
        expect_run(f, "decisions with a question answered", s2(ctx, "decisions", "--project", proj), 0,
                   "decisions: 3", "decisions: pass")
        for name, old, new, want in (
                ("options given", "Options: none", "Options: yes (chosen); no", "Options must be \"none\""),
                ("a change in Affects", "parts none", "parts a larger fuse", "each part of Affects must say \"none\""),
                ("status in force", "Status: closed (answered)", "Status: in force", "Status must be \"closed (answered)\"")):
            fwrite(log, clean + S2_ANSWER.replace(old, new))
            expect_run(f, "a question answered with the fault: %s" % name, s2(ctx, "decisions", "--project", proj), 1,
                       "DC-003 (decisions.md line 23)", want)
    return f


def test_s2_worstcase_left_out(ctx):
    """worstcase.py: the result lists the terms the calc script says it left out, and says so when the
    script does not state them."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        calc = os.path.join(tmp, "alpha_vout.py")
        base = CALC.replace("@@LIMIT@@", "(3.1, 3.5)")
        fwrite(calc, base)
        expect_run(f, "worstcase with no LEFT_OUT", chk(ctx, "worstcase.py", calc), 0,
                   "terms left out: NOT STATED", "inside the limit")
        fwrite(calc, base.replace("LIMIT = ", 'LEFT_OUT = ["drift of r_top with temperature", "bias current"]\nLIMIT = '))
        res = chk(ctx, "worstcase.py", calc, "--write")
        expect_run(f, "worstcase with two terms left out", res, 0,
                   "terms left out: drift of r_top with temperature; bias current")
        expect(f, "terms left out: drift of r_top" in fread(os.path.join(tmp, "alpha_vout.txt")),
               "--write saved no terms left out")
        fwrite(calc, base.replace("LIMIT = ", "LEFT_OUT = []\nLIMIT = "))
        expect_run(f, "worstcase with nothing left out", chk(ctx, "worstcase.py", calc), 0, "terms left out: none")
        fwrite(calc, base.replace("LIMIT = ", "LEFT_OUT = 3\nLIMIT = "))
        expect_run(f, "worstcase with LEFT_OUT that is no list", chk(ctx, "worstcase.py", calc), 2, "LEFT_OUT")
    return f


S2_REQ = """# Requirements: alpha
## Functional requirements
FR-01 Convert the input to 3.3 V. Priority: must have. Source: user, 2026-01-02, "3.3 V out".
      Evidence: DS-001 met
FR-02 Show power with a light (proposed, to confirm). Priority: wanted. Source: worker BR-01-01.
FR-03 Withdrawn (DC-001): Charge a cell.
## Quality characteristics
QC-01 Cost: parts under 10 at quantity 10. Priority: must have. Source: user.
## Environment profile
Supplies it might see: 12 V bench supply. Source: user.
Temperature: does not apply
## Misuse cases
Reverse input: D1 clamps (proposed, to confirm, TC-002)
## Board profile
- Switching converter; on; part choice (U1, U3)
- Microcontroller; on; part choice (U2)
- Radio; off; user answer
## To confirm
TC-001; open; proposed by a worker; a light on +3V3, since no display is asked; FR-02
TC-002; open; needs the user's answer; may the input be reversed?; Misuse cases
TC-003; answered (DC-002); needs research; which standard covers the supply; it is a bench supply; QC-01
TC-004; withdrawn (DC-001); needs research; the charge voltage of the cell; FR-03
"""


def test_s2_requirements(ctx):
    """table_check requirements: the structure of design/requirements.md. Faults of form fail in every
    run; gaps are listed, and fail from --stage ST1."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        req = os.path.join(proj, "design", "requirements.md")
        log = os.path.join(proj, "design", "decisions.md")
        fixture, clean_log = fread(req), fread(log)
        p = ("requirements", "--project", proj)
        # the older fixture file: no Priority, and a line marked to confirm that is in no list
        res = s2(ctx, *p)
        expect_run(f, "requirements on a file with gaps, plain run", res, 0, "gaps: 3",
                   "FR-01 has no Priority", "QC-01 has no Priority", "marked to confirm, and not in the To confirm list",
                   "requirements: pass")
        expect(f, "FAIL" not in res[1], "a gap failed in a plain run")
        expect_run(f, "requirements on a file with gaps, at ST1", s2(ctx, *p, "--stage", "ST1"), 1,
                   "FAIL  design/requirements.md line 3: FR-01 has no Priority", "requirements: FAIL (3)")
        expect_run(f, "all still passes on the fixture", s2(ctx, "all", "--project", proj, "--today", "2026-01-10"), 0,
                   "requirements: pass", "datasheets: pass")
        fwrite(req, S2_REQ)
        expect_run(f, "requirements on the clean file", s2(ctx, *p, "--stage", "ST1"), 0,
                   "FR 2, QC 1 in force; withdrawn 1", "To confirm lines: 4 (open 2, answered 1, withdrawn 1)",
                   "gaps: 0", "requirements: pass")
        gaps = (
            ("no source", ' Source: user, 2026-01-02, "3.3 V out".', "", "line 3: FR-01 has no Source"),
            ("no priority", " Priority: wanted.", "", "line 5: FR-02 has no Priority"),
            ("an environment row with no source", "12 V bench supply. Source: user.", "12 V bench supply",
             "line 10: environment profile row \"Supplies it might see\" names no source"),
            ("a board profile row with no reason", "- Radio; off; user answer", "- Radio; off",
             "line 17: board profile row \"Radio\" has no reason"),
            ("an item to confirm that is in no list", "since no display is asked; FR-02", "since no display is asked; FR-01",
             "line 5: marked to confirm, and not in the To confirm list"),
            # one line of the list names the section, and two lines of the section are marked
            ("a section line to confirm that is in no list", "(proposed, to confirm, TC-002)",
             "(proposed, to confirm)\nWrong plug: F1 opens (proposed, to confirm)",
             "line 14: marked to confirm, and not in the To confirm list"),
        )
        for name, old, new, want in gaps:
            fwrite(req, S2_REQ.replace(old, new))
            expect(f, fread(req) != S2_REQ, "the fault %r was not planted" % name)
            expect_run(f, "requirements with the gap: %s, at ST1" % name, s2(ctx, *p, "--stage", "ST1"), 1,
                       "FAIL  design/requirements.md " + want, "requirements: FAIL (1)")
            expect_run(f, "requirements with the gap: %s, plain run" % name, s2(ctx, *p), 0, "gaps: 1", want)
        forms = (
            ("an ID used twice", "FR-02 Show", "FR-01 Show", "line 5: FR-01 is used twice (first at line 3)"),
            ("IDs out of order", "QC-01 Cost", "QC-02 Cost\nQC-01 Speed. Priority: wanted. Source: user.\nQC-03 Cost",
             "line 9: QC-01 comes after QC-02"),
            ("a priority that is no priority", "Priority: wanted.", "Priority: high.",
             "line 5: FR-02 Priority 'high' must be must have or wanted"),
            ("withdrawn with no decision", "FR-03 Withdrawn (DC-001):", "FR-03 Withdrawn:",
             "line 6: FR-03 is marked withdrawn with no decision"),
            ("withdrawn by a decision not in the log", "FR-03 Withdrawn (DC-001):", "FR-03 Withdrawn (DC-099):",
             "line 6: FR-03 is withdrawn by DC-099, which is not in the decision log"),
            ("a To confirm line with parts missing", "TC-002; open; needs the user's answer; ", "TC-002; open; ",
             "line 20: TC-002: a To confirm line is"),
            ("a state that is no state", "TC-002; open;", "TC-002; pending;",
             "line 20: TC-002 state 'pending' must be open, answered (DC-nnn) or withdrawn (DC-nnn)"),
            ("answered with no decision", "answered (DC-002)", "answered", "line 21: TC-003 state 'answered' must be"),
            ("answered by a decision not in the log", "answered (DC-002)", "answered (DC-099)",
             "line 21: TC-003 names DC-099, which is not in the decision log"),
            ("a kind that is no kind", "needs research; which", "to look up; which",
             "line 21: TC-003 kind 'to look up' must be one of: needs the user's answer, needs research, proposed by a worker"),
            ("a To confirm ID used twice", "TC-002; open", "TC-001; open", "line 20: TC-001 is used twice (first at line 19)"),
            ("To confirm IDs out of order", "TC-004; withdrawn", "TC-002; withdrawn", "line 22: TC-002"),
            ("a line in the list that is no To confirm line", "TC-004; withdrawn", "- ask about the cell\nTC-004; withdrawn",
             "line 22: not a To confirm line"),
            ("no item named", "may the input be reversed?; Misuse cases", "may the input be reversed?; ",
             "line 20: TC-002 names no item"),
        )
        for name, old, new, want in forms:
            fwrite(req, S2_REQ.replace(old, new))
            expect(f, fread(req) != S2_REQ, "the fault %r was not planted" % name)
            expect_run(f, "requirements with the fault of form: %s" % name, s2(ctx, *p), 1,
                       "FAIL  design/requirements.md " + want)
        # a decision that says it affects the requirements is cited in the file
        fwrite(req, S2_REQ)
        fwrite(log, clean_log + DC_WORKER.replace("Affects: requirements none", "Affects: requirements FR-01"))
        expect_run(f, "a decision that affects the requirements, not cited", s2(ctx, *p, "--stage", "ST1"), 1,
                   "FAIL  design/decisions.md: DC-003 says it affects the requirements (FR-01), and "
                   "design/requirements.md does not cite DC-003")
        fwrite(req, S2_REQ.replace('"3.3 V out".', '"3.3 V out". DC-003.'))
        expect_run(f, "the same decision, cited", s2(ctx, *p, "--stage", "ST1"), 0, "requirements: pass")
        os.remove(req)
        expect_run(f, "requirements with no file", s2(ctx, *p), 0, "design/requirements.md not present, check not run")
        expect_run(f, "requirements with no file, at ST1", s2(ctx, *p, "--stage", "ST1"), 1, "check not run")
    return f


def s2_rows(ctx, path, change):
    """Change the rows of a project table with change(rows), and write it back."""
    rows = ctx.h.read_table(path)
    change(rows)
    ctx.h.write_table(path, os.path.basename(path), rows)


def test_s2_parts_totals(ctx):
    """table_check parts-totals: the counts and the cost come from the rows of design/parts.csv."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        parts = os.path.join(proj, "design", "parts.csv")
        clean = fread(parts)
        p = ("parts-totals", "--project", proj)
        row = lambda rows, ref: [r for r in rows if r["refs"] == ref][0]  # noqa: E731
        expect_run(f, "parts-totals on the clean table", s2(ctx, *p), 0,
                   "parts rows: 16 (fitted 16, not fitted 0)", "designators: 19 (fitted 19, not fitted 0)",
                   "pull: 3 rows, 6 designators", "switching converter: 2 rows, 2 designators",
                   "SUPPLIER-B: 2 rows, 2 designators", "cost per board, unit_price: 3.94 from 16 priced rows",
                   "cost per board, qty_price: 3.335 from 16 priced rows", "fitted rows with no unit_price: 0",
                   "designators in more than one row: 0")
        s2_rows(ctx, parts, lambda rows: row(rows, "U4").update(variant="not fitted"))
        expect_run(f, "parts-totals with one part not fitted", s2(ctx, *p), 0,
                   "parts rows: 16 (fitted 15, not fitted 1)", "designators: 19 (fitted 18, not fitted 1)",
                   "cost per board, unit_price: 3.24 from 15 priced rows")
        fwrite(parts, clean)
        s2_rows(ctx, parts, lambda rows: row(rows, "U1").update(unit_price=""))
        expect_run(f, "parts-totals with a price missing", s2(ctx, *p), 0,
                   "cost per board, unit_price: 3.04 from 15 priced rows", "fitted rows with no unit_price: 1 (U1)")
        fwrite(parts, clean)
        s2_rows(ctx, parts, lambda rows: row(rows, "U1").update(unit_price="cheap"))
        expect_run(f, "parts-totals with a price that is no number", s2(ctx, *p), 0,
                   "U1: unit_price 'cheap' is not a number", "cost per board, unit_price: 3.04 from 15 priced rows")
        fwrite(parts, clean)
        s2_rows(ctx, parts, lambda rows: row(rows, "R2").update(refs="R2;R5"))
        expect_run(f, "parts-totals with a designator in two rows", s2(ctx, *p), 0,
                   "designators: 20 ", "designators in more than one row: 1", "R5 is in 2 rows")
        os.remove(parts)
        expect_run(f, "parts-totals with no table", s2(ctx, *p), 0, "design/parts.csv not present, check not run")
    return f


def test_s2_log_append(ctx):
    """table_check log-append: one entry at the end of the decision log with the next free number; the
    bytes before it are never changed; bad input writes nothing."""
    import datetime
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        log = os.path.join(proj, "design", "decisions.md")
        clean = fread(log, "rb")
        p = ("log-append", "--project", proj)
        full = ("--kind", "decision", "--by", "user", "--stage", "ST5", "--options", "22u (chosen); 10u",
                "--reason", "ripple (DS-001)", "--affects",
                "requirements none; parts C1; schematic input; board none; cost none")
        expect_run(f, "log-append of a decision", s2(ctx, *p, "--statement", "Use a larger input capacitor", *full), 0,
                   "appended DC-003 to design/decisions.md")
        after = fread(log, "rb")
        expect(f, after.startswith(clean) and len(after) > len(clean), "log-append changed the earlier entries")
        text = after[len(clean):].decode("utf-8")
        for want in ("## Use a larger input capacitor (DC-003)\n", "Kind: decision\n", "Decided by: user\n",
                     "Date: %s\n" % datetime.date.today().isoformat(), "Stage: ST5\n", "Options: 22u (chosen); 10u\n",
                     "Reason: ripple (DS-001)\n", "Status: in force\n"):
            expect(f, want in text, "the new entry lacks %r: %r" % (want, text))
        expect_run(f, "the log after log-append", s2(ctx, "decisions", "--project", proj), 0, "decisions: 3", "decisions: pass")
        # the lighter kind fills its own fixed fields
        expect_run(f, "log-append of a question answered",
                   s2(ctx, *p, "--statement", 'The user said "go on"', "--kind", "question answered", "--by", "user",
                      "--stage", "ST5", "--reason", "asked whether to go on"), 0, "appended DC-004")
        text = fread(log)
        expect(f, "Options: none\nReason: asked whether to go on\nAffects: requirements none; parts none; schematic none; "
               "board none; cost none\nStatus: closed (answered)\n" in text, "a question answered did not get its fixed fields")
        # a worker's choice is not yet seen by the user
        expect_run(f, "log-append of a worker's choice",
                   s2(ctx, *p, "--statement", "Read the rating from the table", *full[:2], "--by", "worker BR-03-02", *full[4:],
                      "--stage", "ST3, ST5"), 0, "appended DC-005")
        expect(f, "Decided by: worker BR-03-02; seen by user: no\n" in fread(log), "no seen by user: no")
        expect(f, "Stage: ST3, ST5\n" in fread(log), "several stages were not written")
        expect_run(f, "the log after three entries", s2(ctx, "decisions", "--project", proj), 0,
                   "not yet seen by the user: 1 (DC-005)", "decisions: pass")
        # a change of mind points back; the old entry is not touched, and the output says what to set
        before = fread(log, "rb")
        expect_run(f, "log-append with --replaces",
                   s2(ctx, *p, "--statement", "Fit an input fuse after all", *full, "--replaces", "DC-001"), 0,
                   "appended DC-006", 'set the Status of DC-001 to "superseded by DC-006"')
        after = fread(log, "rb")
        expect(f, after.startswith(before), "log-append with --replaces changed an earlier entry")
        expect(f, b"Replaces: DC-001\n" in after[len(before):], "no Replaces line")
        expect_run(f, "the log until the old Status is set", s2(ctx, "decisions", "--project", proj), 1,
                   "Replaces DC-001, but the Status of DC-001")
        # the next free number is past the highest in the file, whatever the gaps
        fwrite(log, clean.decode("utf-8").replace("(DC-002)", "(DC-007)"))
        expect_run(f, "log-append past a gap", s2(ctx, *p, "--statement", "Keep the header", *full), 0, "appended DC-008")
        os.remove(log)
        expect_run(f, "log-append with no log", s2(ctx, *p, "--statement", "Keep the header", *full), 0, "appended DC-001")
        expect(f, fread(log).startswith("# Decisions\n\n## Keep the header (DC-001)\n"), "the new log has no heading")
        fwrite(log, clean.decode("utf-8"))
        ok = ("--statement", "Keep the header") + full
        swap = lambda flag, value: tuple(value if i and ok[i - 1] == flag else x for i, x in enumerate(ok))  # noqa: E731
        drop = lambda flag: tuple(x for i, x in enumerate(ok) if x != flag and not (i and ok[i - 1] == flag))  # noqa: E731
        bad = (
            ("a kind that is no kind", swap("--kind", "choice"), "--kind"),
            ("decided by nobody known", swap("--by", "somebody"), "--by"),
            ("a worker with no brief", swap("--by", "worker"), "--by"),
            ("no reason", drop("--reason"), "--reason"),
            ("no statement", drop("--statement"), "--statement"),
            ("no options", drop("--options"), "--options"),
            ("Affects with parts missing", swap("--affects", "requirements none; parts none"), "--affects"),
            ("a line break in a value", swap("--statement", "Keep\nthe header"), "one line"),
            ("replaces an entry not in the log", ok + ("--replaces", "DC-099"), "DC-099"),
            ("a stage that is no stage", swap("--stage", "soon"), "--stage"),
            ("a status that is no status", ok + ("--status", "done"), "--status"),
            ("a word after the command", ("decisions",) + ok, "decisions"),
        )
        for name, args, want in bad:
            expect(f, args != ok, "the fault %r was not planted" % name)
            expect_run(f, "log-append with %s" % name, s2(ctx, *p, *args), 2, want)
            expect(f, fread(log, "rb") == clean, "log-append with %s wrote to the log" % name)
    return f


def test_s2_set_row(ctx):
    """table_check set-row: one row of a table is changed or added; every other line keeps its bytes."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        pins = os.path.join(proj, "design", "pins.csv")
        parts = os.path.join(proj, "design", "parts.csv")
        p = ("--project", proj)
        diff = lambda a, b: [i for i, (x, y) in enumerate(zip(a.split(b"\n"), b.split(b"\n")), 1) if x != y]  # noqa: E731
        before = fread(pins, "rb")
        res = s2(ctx, "set-row", "pins.csv", "U2,7", "net=/RX2", "confirmed=yes", *p)
        expect_run(f, "set-row on a pin row", res, 0, "design/pins.csv line 23: U2,7: changed", "net: /RX -> /RX2",
                   "confirmed: no -> yes")
        after = fread(pins, "rb")
        expect(f, diff(before, after) == [23] and before.count(b"\n") == after.count(b"\n"),
               "set-row changed other lines: %r" % diff(before, after))
        row = [r for r in ctx.h.read_table(pins) if (r["designator"], r["pin"]) == ("U2", "7")][0]
        expect(f, (row["net"], row["confirmed"], row["name"]) == ("/RX2", "yes", "PA3"), "the pin row is %r" % row)
        expect_run(f, "set-row with nothing to change", s2(ctx, "set-row", "pins.csv", "U2,7", "net=/RX2", *p), 0, "no change")
        expect(f, fread(pins, "rb") == after, "set-row with nothing to change wrote the file")
        # a value that holds a comma is quoted, and reads back whole
        before = fread(parts, "rb")
        expect_run(f, "set-row with a comma in the value", s2(ctx, "set-row", "parts.csv", "R2", "value=22k, 1%", *p), 0,
                   "design/parts.csv line 10: R2: changed")
        after = fread(parts, "rb")
        expect(f, diff(before, after) == [10], "set-row changed other lines of parts.csv: %r" % diff(before, after))
        expect(f, [r["value"] for r in ctx.h.read_table(parts) if r["refs"] == "R2"] == ["22k, 1%"], "the comma was lost")
        # a key that is in no row adds one row at the end
        expect_run(f, "set-row adding a row", s2(ctx, "set-row", "parts.csv", "R9", "value=1k", "role=other", *p), 0,
                   "design/parts.csv line 18: R9: added")
        added = fread(parts, "rb")
        expect(f, added.startswith(after) and added.count(b"\n") == after.count(b"\n") + 1, "the new row is not one line at the end")
        rows = ctx.h.read_table(parts)
        expect(f, len(rows) == 17 and (rows[-1]["refs"], rows[-1]["value"], rows[-1]["role"]) == ("R9", "1k", "other"),
               "the added row is %r" % rows[-1])
        expect_run(f, "the table after set-row", s2(ctx, "parts-totals", *p), 0, "parts rows: 17")
        # a template table that is not there yet is made with its header
        nr = os.path.join(proj, "design", "net-review.csv")
        os.remove(nr)
        expect_run(f, "set-row making a table", s2(ctx, "set-row", "net-review.csv", "NR-001", "list=protect", *p), 0, "added")
        expect(f, fread(nr) == "id,list,net_or_pin,item,reason,closed_by,date\nNR-001,protect,,,,,\n", "the new table is %r" % fread(nr))
        s2_rows(ctx, parts, lambda rows: rows.append(dict(rows[0])))
        keep = fread(parts, "rb"), fread(pins, "rb")
        bad = (
            ("a column the table does not have", ("parts.csv", "R2", "colour=red"), "colour"),
            ("no column given", ("parts.csv", "R2"), "column=value"),
            ("a word that is no column=value", ("parts.csv", "R2", "value"), "column=value"),
            ("a change to the key column", ("parts.csv", "R2", "refs=R8"), "key"),
            ("a key that two rows hold", ("parts.csv", "C1", "value=1u"), "2 rows"),
            ("half a key", ("pins.csv", "U2", "net=/RX"), "designator,pin"),
            ("a file that is no table", ("notes.txt", "R2", "value=1"), ".csv"),
            ("a table with no template and no file", ("other.csv", "R2", "value=1"), "other.csv"),
            ("a line break in a value", ("parts.csv", "R2", "value=1\n2"), "one line"),
        )
        for name, args, want in bad:
            expect_run(f, "set-row with %s" % name, s2(ctx, "set-row", *args, *p), 2, want)
            expect(f, (fread(parts, "rb"), fread(pins, "rb")) == keep, "set-row with %s wrote a file" % name)
    return f


S2_README = """# Datasheets
| file | part | MPN | maker | revision | from | URL | fetched |
|---|---|---|---|---|---|---|---|
| BUCK-1.pdf | regulator | BUCK-1 | Maker G | A, 2025-03 | maker | @@HOST@@/docs/BUCK-1.pdf | 2026-01-02 |
| SENSE-1.pdf | sensor | SENSE-1 | Maker J | A, 2025-01 | maker | @@HOST@@/docs/SENSE-1.pdf | 2026-01-02 |
| STD-1.pdf | a standard's preview | | | 2, 2024 | not committed | @@HOST@@/std/STD-1.pdf | 2026-01-02 |
""".replace("@@HOST@@", "https:" + "//example.com")


def test_s2_datasheets(ctx):
    """table_check datasheets: each document in datasheets/ has a README line and a text extract, and the
    setting line "Third-party PDFs committed:" is honoured."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        folder = os.path.join(proj, "datasheets")
        status = os.path.join(proj, "design", "status.md")
        clean_status = fread(status)
        p = ("datasheets", "--project", proj)
        expect_run(f, "datasheets with no folder", s2(ctx, *p), 0, "datasheets/ not present: no document to check", "datasheets: pass")
        expect_run(f, "datasheets with no folder, at ST6", s2(ctx, *p, "--stage", "ST6"), 1,
                   "FAIL  datasheets/ not present")

        def fresh():
            shutil.rmtree(folder, ignore_errors=True)
            os.makedirs(folder)
            fwrite(os.path.join(folder, "README.md"), S2_README)
            for stem in ("BUCK-1", "SENSE-1"):
                fwrite(os.path.join(folder, stem + ".pdf"), "%PDF-1.4 fixture\n")
                fwrite(os.path.join(folder, stem + ".txt"), "page 1\ntext of %s\n" % stem)
            fwrite(status, clean_status)

        fresh()
        expect_run(f, "datasheets on the clean folder", s2(ctx, *p), 0, "documents: 2; text extracts: 2; not committed: 0",
                   "Third-party PDFs committed: not set", "datasheets: pass")
        fwrite(status, clean_status + "Third-party PDFs committed: yes\n")
        expect_run(f, "datasheets with the setting yes", s2(ctx, *p), 0, "Third-party PDFs committed: yes", "datasheets: pass")
        readme = os.path.join(folder, "README.md")
        faults = (
            ("a document with no README line", lambda: fwrite(os.path.join(folder, "NOTE-7.pdf"), "x\n") or
             fwrite(os.path.join(folder, "NOTE-7.txt"), "x\n"),
             "datasheets/NOTE-7.pdf: no line in datasheets/README.md names it"),
            ("a document with no text extract", lambda: os.remove(os.path.join(folder, "SENSE-1.txt")),
             "datasheets/SENSE-1.pdf: no text extract (SENSE-1.txt) beside it"),
            ("an empty text extract", lambda: fwrite(os.path.join(folder, "SENSE-1.txt"), ""),
             "datasheets/SENSE-1.txt: the text extract is empty"),
            ("no README", lambda: os.remove(readme), "datasheets/README.md is not there"),
            ("a README line for a file that is not there", lambda: os.remove(os.path.join(folder, "BUCK-1.pdf")),
             "datasheets/README.md line 4: names BUCK-1.pdf, which is not in datasheets/"),
            ("a text extract of no listed document", lambda: fwrite(os.path.join(folder, "OTHER-9.txt"), "x\n"),
             "datasheets/OTHER-9.txt: a text extract of a document no line in datasheets/README.md names"),
            ("not committed with no URL", lambda: fwrite(readme, S2_README.replace("https:" + "//example.com/std/STD-1.pdf", "")),
             "datasheets/README.md line 6: says \"not committed\" and gives no URL"),
            ("the setting no, and a line that does not say so",
             lambda: fwrite(status, clean_status + "Third-party PDFs committed: no\n"),
             "datasheets/README.md line 4: BUCK-1.pdf: the setting \"Third-party PDFs committed: no\" is in force"),
        )
        for name, plant, want in faults:
            fresh()
            plant()
            expect_run(f, "datasheets with %s" % name, s2(ctx, *p), 1, "FAIL  " + want)
        # with the setting no, every PDF line says "not committed" and keeps its URL; the files may be absent
        fresh()
        fwrite(status, clean_status + "Third-party PDFs committed: no\n")
        fwrite(readme, S2_README.replace("| maker | https", "| maker, not committed | https"))
        os.remove(os.path.join(folder, "BUCK-1.pdf"))
        expect_run(f, "datasheets with the setting no, in order", s2(ctx, *p), 0, "not committed: 1", "datasheets: pass")
        # a document that is not to be committed is not in git
        fresh()
        fwrite(os.path.join(folder, "STD-1.pdf"), "%PDF-1.4 fixture\n")
        fwrite(os.path.join(folder, "STD-1.txt"), "page 1\n")
        expect_run(f, "datasheets with a document kept out of git, no repository", s2(ctx, *p), 0,
                   "not committed: 1", "not a git repository", "datasheets: pass")
        if run(["git", "--version"])[0] != 0:
            raise Skip("git is not installed; the tracked-file fault was not planted")
        run(["git", "-C", proj, "init", "-q"])
        run(["git", "-C", proj, "add", "datasheets/BUCK-1.pdf"])
        expect_run(f, "datasheets in a repository, the kept-out document not tracked", s2(ctx, *p), 0, "datasheets: pass")
        run(["git", "-C", proj, "add", "datasheets/STD-1.pdf"])
        expect_run(f, "datasheets with a not-committed document that git tracks", s2(ctx, *p), 1,
                   "FAIL  datasheets/STD-1.pdf: git tracks it")
    return f


def test_s2_scratch_pointer(ctx):
    """table_check scan: a kept file that points into the scratch folder is found; the brief's own
    Scratch line, the ignore line and the skill's own copies are not."""
    f = []
    scratch = "." + "hwtmp/"
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        docs = os.path.join(proj, "docs")
        note = os.path.join(docs, "notes.md")
        os.makedirs(docs, exist_ok=True)
        os.makedirs(os.path.join(proj, "hwskills"), exist_ok=True)
        fwrite(note, "Scratch:%sBR-01-01/\nScratch folder: %s\nThrow-away files go in `%s`, never elsewhere.\n/%s\n"
               % (scratch, scratch, scratch, scratch))
        p = ("scan", docs, "--project", proj)
        expect_run(f, "scan of a file that only names the scratch folder", s2(ctx, *p), 0, "findings 0", "scan: pass")
        fwrite(note, "The probe build is in %sBR-01-01/probe/alpha.kicad_sch\n" % scratch)
        expect_run(f, "scan of a file that points into the scratch folder", s2(ctx, *p), 1,
                   "notes.md:1: scratch folder path", "scan: FAIL (1)")
        os.remove(note)
        fwrite(os.path.join(proj, "hwskills", "note.md"), "built in %sBR-01-01/probe\n" % scratch)
        fwrite(note, "nothing here\n")
        expect_run(f, "scan of the skill's own copies", s2(ctx, "scan", docs, os.path.join(proj, "hwskills"), "--project", proj),
                   0, "scan: pass")
    return f


S2_STATUS = """Designs: logical agreed; electrical in review; physical in review
Ownership: schematic hand; board hand
KiCad folder: hardware/
Caveat on own edits said: 2026-01-02
Execution mode: one worker at a time
Settings: stop-and-ask = default; model split = default; reports = normal;
  datasheet passes = three for complex and pack parts; commits = offer at sprint close;
  backup commits = off; datasheet reading = up-front passes;
  log every prompt = on; market scan = none;
  simulation = per module; declined: alpha, DC-002; controller in the loop = no;
  sheets = per block; assembly = hand; derating = none;
  package size = 0603; form = all SMD
Suppliers: SUPPLIER-A, SUPPLIER-B; preferred makers: none
Tool version rule: none
Scratch folder: .hwtmp/
Third-party PDFs committed: yes
Region of use: bench only
User interface: on the board
PDF route: own PDF reading; figures readable: yes
Tools: KiCad 10.0; Python 3
Guidelines (may be bent): power paths first
User's own habits: none given
Schematic drawing habits: rails at the top
Sequencing: none
Expected DRC notes:
  - "Missing footprint" on Footprint J1, DC-001
Expected ERC items: none
Review baselines: schematic review BR-01-01 at 0000000; board review BR-02-01 at 0000000
Checkpoints: requirements read
Sheet progress:
  - alpha: drawn
  - beta: not started
Accepted, not yet drawn: none
Waiting on the user:
  - the supply's current limit, 2026-01-03, the fuse rating
Next thing to look at: the alpha sheet, two steps away
Next step: draw beta; the worker acts next
Skills version: hw-skills 0.1.0; scripts copied 2026-01-02
"""


def test_s2_status_lines(ctx):
    """The status.md template with every line filled gives no false failure in the checks that read it."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        design = os.path.join(proj, "design")
        base = s2(ctx, "all", "--project", proj, "--today", "2026-01-10")
        fwrite(os.path.join(design, "status.md"), S2_STATUS)
        res = s2(ctx, "all", "--project", proj, "--today", "2026-01-10")
        expect_run(f, "all with the whole status template", res, 0)
        expect(f, base[0] == 0 and [x for x in res[1].splitlines() if x.startswith("FAIL")] == [],
               "the whole status template gave failures: %s" % res[1][-600:])
        expect_run(f, "summary with the whole status template", s2(ctx, "summary", "--project", proj), 0,
                   "schematic review BR-01-01")
        notes, errors = ctx.h.expected_drc_notes(design)
        expect(f, notes == [("Missing footprint", "Footprint J1", "DC-001")] and not errors,
               "expected DRC notes read as %r, %r" % (notes, errors))
        expect(f, ctx.h.expected_erc_items(design) == ([], []), "expected ERC items read as %r" % (ctx.h.expected_erc_items(design),))
        expect(f, ctx.h.recorded_kicad_folder(design) in ("hardware", "hardware/"),
               "KiCad folder read as %r" % ctx.h.recorded_kicad_folder(design))
    return f


S2_TESTS = [
    ("S2 table_check parts-totals: counts and cost from the rows", test_s2_parts_totals),
    ("S2 table_check log-append: one entry at the end, nothing rewritten", test_s2_log_append),
    ("S2 table_check set-row: one row changed or added", test_s2_set_row),
    ("S2 table_check datasheets: a README line and a text extract for each file", test_s2_datasheets),
    ("S2 table_check scan: a kept file that points into the scratch folder", test_s2_scratch_pointer),
    ("S2 the status template with every line filled reads without failures", test_s2_status_lines),
    ("S2 table_check requirements: the structure of the requirements file", test_s2_requirements),
    ("S2 table_check decisions: the kind question answered", test_s2_question_answered),
    ("S2 worstcase: a result lists the terms left out", test_s2_worstcase_left_out),
]
SCRIPT_TESTS += S2_TESTS
# ======================================================================== end of S2 section


# ======================================================================== T2 section (ERC power references, lifecycle)
# build.py erc: an expected item does not depend on which power symbol KiCad named. table_check parts:
# the lifecycle in design/parts.csv against the maker's product pages saved in datasheets/.

def t2_violation(text, *items):
    """One violation in the form of KiCad's ERC report (JSON)."""
    return {"description": text, "severity": "error", "type": "fixture",
            "items": [{"description": i, "pos": {"x": 0.1, "y": 0.1}, "uuid": "0"} for i in items]}


T2_NOT_DRIVEN = "Input Power pin not driven by any Output Power pins"


def test_t2_erc_power_ref(ctx):
    """build.py erc: two ERC results that differ only in the power symbol KiCad named both match one
    expected line of design/status.md; a new item is still new."""
    f = []
    build = ctx.module("build", "build_t2")
    with tempfile.TemporaryDirectory() as tmp:
        fwrite(os.path.join(tmp, "status.md"), 'Expected ERC items:\n'
               '  - "Input Power pin not driven" on Symbol #PWR104 Pin 1, DC-001\n'
               '  - "Pin not connected" on Symbol U1 Pin 1, DC-001\n')
        expected, errors = ctx.h.expected_erc_items(tmp)
    if not expect(f, len(expected) == 2 and not errors, "the expected items read as %r, %r" % (expected, errors)):
        return f
    power, pin = expected
    first = t2_violation(T2_NOT_DRIVEN, "Symbol #PWR104 Pin 1 [Power input, Line]")
    second = t2_violation(T2_NOT_DRIVEN, "Symbol #PWR106 Pin 1 [Power input, Line]")
    expect(f, build.erc_hits(expected, first) == [power], "the run that names #PWR104 does not match the expected line")
    expect(f, build.erc_hits(expected, second) == [power],
           "the run that names #PWR106 does not match the line written with #PWR104: %r" % build.erc_hits(expected, second))
    flag = [("PWR_FLAG", "Symbol #FLG Pin 1", "DC-001")]
    for ref in ("#FLG01", "#FLG0102"):
        expect(f, build.erc_hits(flag, t2_violation("PWR_FLAG fixture text", "Symbol %s Pin 1 [Power output, Line]" % ref)) == flag,
               "an expected item written \"#FLG\" does not match %s" % ref)
    # what must still be told apart
    news = (
        ("another text on a power symbol", t2_violation("Pin not connected", "Symbol #PWR106 Pin 1 [Power input, Line]")),
        ("the same text on a part", t2_violation(T2_NOT_DRIVEN, "Symbol U3 Pin 2 [Power input, Line]")),
        ("the same text on another pin of a power symbol", t2_violation(T2_NOT_DRIVEN, "Symbol #PWR104 Pin 2 [Power input, Line]")),
        ("a part whose designator starts the same", t2_violation("Pin not connected", "Symbol U10 Pin 1 [Input, Line]")),
        ("another part", t2_violation("Pin not connected", "Symbol U2 Pin 1 [Input, Line]")),
    )
    for name, v in news:
        expect(f, build.erc_hits(expected, v) == [], "%s was taken as expected: %r" % (name, build.erc_hits(expected, v)))
    expect(f, build.erc_hits(expected, t2_violation("Pin not connected", "Symbol U1 Pin 1 [Input, Line]")) == [pin],
           "the expected item on a part no longer matches")
    return f


T2_PAGE = "_product-page.txt"
T2_SENSOR_PAGE = """SNS-70 humidity sensor
Product status: Not recommended for new designs

Code          Package     Status                             Packing
SNS-70S6-TR   SOT-23-6    Not recommended for new designs    tape and reel, 3000
"""
T2_FAMILY_PAGE = """REG-33 regulator family
Product family status: Active (in production)

Code          Package     Status           Packing
REG-33S5-TR   SOT-23-5    Last time buy    tape and reel, 3000
REG-33DN-TR   DFN-4       Active           tape and reel, 10000
"""
T2_CLEAN_PAGE = """MCU-11 controller
Product status: Active (in production)

Code           Package     Status    Packing
MCU-11T14-TR   TSSOP-14    Active    tape and reel, 2500
"""
T2_ELSEWHERE_PAGE = """CHG-56 charger
Code          Package     Status    Packing
CHG-56S5-TR   SOT-23-5    Active    tape and reel, 3000
CHG-56DN-TR   DFN-6       Obsolete  none

News: the DFN-6 code is discontinued.
"""
# check-fixture row (by its refs) -> the invented orderable code it carries in these tests
T2_CODES = {"D1": "SNS-70S6-TR", "L1": "REG-33S5-TR", "J2": "MCU-11T14-TR", "TP1": "CHG-56S5-TR"}


def t2_project(ctx, tmp, pages, lifecycle=None):
    """The check fixture with four rows given invented codes, a lifecycle each (default active), and the
    maker pages saved in datasheets/."""
    proj = check_proj(ctx, tmp)

    def change(rows):
        for r in rows:
            if r["refs"] in T2_CODES:
                r["mpn"] = T2_CODES[r["refs"]]
                r["lifecycle"] = (lifecycle or {}).get(r["refs"], "active (maker page, read 2026-01-02)")
    s2_rows(ctx, os.path.join(proj, "design", "parts.csv"), change)
    os.makedirs(os.path.join(proj, "datasheets"), exist_ok=True)
    for stem, text in pages.items():
        fwrite(os.path.join(proj, "datasheets", stem + T2_PAGE), text)
    return proj, ("parts", "--project", proj, "--today", "2026-01-10")


def test_t2_lifecycle_code_line(ctx):
    """table_check parts: parts.csv says active, and the saved maker page says otherwise on the line of
    the exact orderable code. Both planted cases fail; the clean row does not."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj, p = t2_project(ctx, tmp, {"SNS-70": T2_SENSOR_PAGE, "REG-33": T2_FAMILY_PAGE, "MCU-11": T2_CLEAN_PAGE})
        code, out = res = s2(ctx, *p)
        expect_run(f, "parts with two codes that the saved pages say are not active", res, 1,
                   "maker pages read (datasheets/*_product-page.txt): 3",
                   'FAIL  D1 (SNS-70S6-TR): lifecycle says active, and datasheets/SNS-70_product-page.txt line 5, '
                   'which names SNS-70S6-TR, says "Not recommended for new designs"',
                   'FAIL  L1 (REG-33S5-TR): lifecycle says active, and datasheets/REG-33_product-page.txt line 5, '
                   'which names REG-33S5-TR, says "Last time buy"',
                   "parts: FAIL (2)")
        expect(f, "MCU-11T14-TR" not in "\n".join(x for x in out.splitlines() if "FAIL" in x or "says" in x),
               "the clean row was failed or listed: %s" % out[-600:])
        # the other code of the family is active: a row that orders that one passes
        s2_rows(ctx, os.path.join(proj, "design", "parts.csv"),
                lambda rows: [r.update(mpn="REG-33DN-TR") for r in rows if r["refs"] == "L1"])
        os.remove(os.path.join(proj, "datasheets", "SNS-70" + T2_PAGE))
        expect_run(f, "parts with the active code of the same family", s2(ctx, *p), 0,
                   "maker pages read (datasheets/*_product-page.txt): 2", "parts: pass")
    return f


def test_t2_lifecycle_listed(ctx):
    """table_check parts: a lifecycle word elsewhere in a part's page, and a part with no saved page, are
    listed and counted, not failed. With no page at all the count is 0, in words."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj, p = t2_project(ctx, os.path.join(tmp, "a"), {})
        base = s2(ctx, *p)
        expect_run(f, "parts with no saved maker page", base, 0, "maker pages read (datasheets/*_product-page.txt): 0",
                   "rows with a page that names the exact code: 0",
                   "no saved maker page names the exact code: 16 of 16 fitted rows with an MPN (listed, not failed)",
                   "parts: pass")
        expect_run(f, "parts with no saved maker page, at ST6", s2(ctx, *p, "--stage", "ST6"), 0,
                   "no saved maker page names the exact code: 16 of 16", "parts: pass")
        shutil.rmtree(os.path.join(proj, "datasheets"))
        expect_run(f, "parts with no datasheets folder", s2(ctx, *p), 0,
                   "maker pages read (datasheets/*_product-page.txt): 0", "parts: pass")
        proj, p = t2_project(ctx, os.path.join(tmp, "b"), {"CHG-56": T2_ELSEWHERE_PAGE, "MCU-11": T2_CLEAN_PAGE})
        expect_run(f, "parts with a lifecycle word elsewhere in the page", s2(ctx, *p), 0,
                   "maker pages read (datasheets/*_product-page.txt): 2",
                   "rows with a page that names the exact code: 2",
                   'TP1 (CHG-56S5-TR): datasheets/CHG-56_product-page.txt line 4 says "Obsolete", not on a line that names '
                   "CHG-56S5-TR (2 such lines)",
                   "listed, not failed",
                   "no saved maker page names the exact code: 14 of 16", "parts: pass")
        # a page that names only a longer code does not count as a page of the shorter one
        fwrite(os.path.join(proj, "datasheets", "MCU-11" + T2_PAGE), T2_CLEAN_PAGE.replace("MCU-11T14-TR", "MCU-11T14-TRX"))
        expect_run(f, "parts with a page that names only another code", s2(ctx, *p), 0,
                   "rows with a page that names the exact code: 1", "no saved maker page names the exact code: 15 of 16")
    return f


def test_t2_lifecycle_decision(ctx):
    """table_check parts: a lifecycle that is not active needs a decision by the user, named in the cell.
    With one, the row passes, and the page is not held against it."""
    f = []
    pages = {"SNS-70": T2_SENSOR_PAGE}
    cases = (
        ("no decision", "NRND (maker page, read 2026-01-02)", 1,
         "FAIL  D1 (SNS-70S6-TR): lifecycle 'NRND (maker page, read 2026-01-02)' is not active, and names no decision by "
         "the user (DC-nnn)"),
        ("a decision the user did not make", "NRND (maker page), DC-002", 1,
         "FAIL  D1 (SNS-70S6-TR): lifecycle 'NRND (maker page), DC-002' is not active, and names no decision by the user "
         "(DC-nnn); DC-002 is not a decision by the user in design/decisions.md"),
        ("a decision not in the log", "last time buy, DC-777", 1, "DC-777 is not a decision by the user"),
        ("an empty cell against the page", "", 1,
         "FAIL  D1 (SNS-70S6-TR): lifecycle is empty, and datasheets/SNS-70_product-page.txt line 5"),
        ("the user's decision", "NRND (maker page, read 2026-01-02), DC-001", 0, "rows under a decision by the user: 1"),
        ("active against the page, under the user's decision", "active (the page is out of date), DC-001", 0,
         "rows under a decision by the user: 1"),
    )
    with tempfile.TemporaryDirectory() as tmp:
        for n, (name, cell, code, want) in enumerate(cases):
            proj, p = t2_project(ctx, os.path.join(tmp, str(n)), pages, {"D1": cell})
            expect_run(f, "parts with a lifecycle that is not active: %s" % name, s2(ctx, *p), code, want,
                       "parts: pass" if code == 0 else "parts: FAIL (1)")
    return f


T2_TESTS = [
    ("T2 build.py erc: an expected item does not depend on the power symbol named", test_t2_erc_power_ref),
    ("T2 table_check parts: active in the table, not active on the code's line of the saved page",
     test_t2_lifecycle_code_line),
    ("T2 table_check parts: lifecycle words elsewhere, no saved page, no page at all", test_t2_lifecycle_listed),
    ("T2 table_check parts: a lifecycle that is not active needs the user's decision", test_t2_lifecycle_decision),
]
SCRIPT_TESTS += T2_TESTS
# ======================================================================== end of T2 section


# ======================================================================== S1 section (sch_check additions)
# Script worker S1: rails, modules (--probe), overlap, chosen, fields, netload, drive, and pins with no pin table.

# ---- S1 fixture: a project of module sheets, drawn by hand in KiCad 10 form, small enough to read.
# The netlist KiCad would export is worked out from the same description, so most tests run with no
# KiCad; test_kicad_s1_netlist compares that netlist with the one KiCad exports.

S1_NAME = "mods"
S1_FONT = "(effects (font (size 1.27 1.27))%s)"
# Library symbols: pins (number, name, type, x, y, angle, length), half size of the body, where the
# reference and value sit from the symbol's place (x, y, justify), footprint.
S1_SYMS = {
    "P2": {"pins": [("1", "~", "passive", 0, 3.81, 270, 1.27), ("2", "~", "passive", 0, -3.81, 90, 1.27)],
           "body": (1.016, 2.54), "ref": (2.54, -1.27, "left"), "val": (2.54, 1.27, "left")},
    "Q3": {"pins": [("1", "B", "input", -5.08, 0, 0, 2.54), ("2", "C", "passive", 2.54, 5.08, 270, 2.54),
                    ("3", "E", "passive", 2.54, -5.08, 90, 2.54)],
           "body": (2.54, 2.54), "ref": (5.08, -1.27, "left"), "val": (5.08, 1.27, "left")},
    "M3": {"pins": [("1", "G", "input", -5.08, 0, 0, 2.54), ("2", "D", "passive", 2.54, 5.08, 270, 2.54),
                    ("3", "S", "passive", 2.54, -5.08, 90, 2.54)],
           "body": (2.54, 2.54), "ref": (5.08, -1.27, "left"), "val": (5.08, 1.27, "left")},
    "U4": {"pins": [("1", "VIN", "power_in", -7.62, 7.62, 0, 2.54), ("2", "OUT", "output", -7.62, 2.54, 0, 2.54),
                    ("3", "EN", "input", -7.62, -2.54, 0, 2.54), ("4", "GND", "power_in", -7.62, -7.62, 0, 2.54)],
           "body": (5.08, 10.16), "ref": (0, -11.43, ""), "val": (0, 11.43, "")},
}
S1_STUB = {0: (-2.54, 0), 180: (2.54, 0), 90: (0, -2.54), 270: (0, 2.54)}     # away from the body, library axes
S1_DOWN = ("GND",)                                                            # power symbols drawn downwards


def s1_uid(*key):
    import uuid
    return str(uuid.uuid5(uuid.UUID("3b0e6a52-7c1d-4e8f-9a41-0d6c1f00a051"), "/".join(str(k) for k in key)))


def s1_q(text):
    return '"%s"' % str(text).replace("\\", "\\\\").replace('"', '\\"')


def s1_n(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


def s1_xy(px, py, rot, mirror):
    """A point of a library symbol (y up) on the sheet, from the symbol's place."""
    x, y = {0: (px, -py), 90: (-py, -px), 180: (-px, py), 270: (py, px)}[rot]
    return (-x if mirror == "y" else x), (-y if mirror == "x" else y)


def s1_part(ref, sym, value, x, y, pins, **more):
    p = {"ref": ref, "sym": sym, "value": value, "at": (x, y), "rot": 0, "mirror": "", "pins": pins, "role": "",
         "mpn": "MP-" + value, "spn": "SP-" + value, "datasheet": "ds/MP-%s.pdf" % value,
         "description": "fixture part " + value, "dnp": False, "ref_at": None, "val_at": None}
    p.update(more)
    return p


def s1_spec():
    """The clean project: module alpha (a regulator with its parts) and module beta (loads), joined by NET_A."""
    pw, lab, hier = (lambda n: ("pwr", n)), (lambda n: ("lab", n)), (lambda n: ("hier", n))
    far = {"ref_at": (0, -6.35, ""), "val_at": (0, 6.35, "")}
    side = {"ref_at": (3.81, -5.08, ""), "val_at": (3.81, 5.08, "")}
    return {
        "modules": [("alpha", "100-199", "regulator"), ("beta", "200-299", "loads")],
        "top": {"NET_A": ["alpha", "beta"]},
        "parts": {
            "alpha": [
                s1_part("U101", "U4", "REG-1", 50.8, 101.6, {"1": pw("+5V"), "2": hier("NET_A"), "3": lab("EN_A"),
                                                              "4": pw("GND")}),
                s1_part("R101", "P2", "10k", 76.2, 101.6, {"1": pw("+5V"), "2": lab("EN_A")}, role="pull"),
                s1_part("C101", "P2", "100n", 101.6, 101.6, {"1": pw("+5V"), "2": pw("GND")}),
                s1_part("R104", "P2", "1k", 127, 101.6, {"1": pw("+5V"), "2": pw("GND")}),
            ],
            "beta": [
                s1_part("R201", "P2", "1k", 50.8, 101.6, {"1": hier("NET_A"), "2": pw("GND")}, rot=90, **far),
                s1_part("R202", "P2", "4k7", 76.2, 101.6, {"1": hier("NET_A"), "2": lab("B1")}),
                s1_part("R203", "P2", "4k7", 101.6, 101.6, {"1": hier("NET_A"), "2": lab("B2")}),
                s1_part("Q201", "Q3", "NPN-1", 127, 101.6, {"1": lab("B1"), "2": pw("+5V"), "3": pw("GND")}),
                s1_part("Q202", "Q3", "NPN-1", 152.4, 101.6, {"1": lab("B2"), "2": pw("+5V"), "3": pw("GND")},
                        mirror="y", **side),
                s1_part("R205", "P2", "0R", 177.8, 101.6, {"1": pw("AGND"), "2": pw("GND")}, role="link"),
                s1_part("R207", "P2", "10k", 203.2, 101.6, {"1": pw("+5V"), "2": pw("GND")}, role="pull"),
            ],
        },
        "labels": {},            # module -> hierarchical labels that stand alone (the empty skeleton)
        "extra": {},             # sheet ("" is the top sheet) -> KiCad text added to it as it is
        "rails": [("+5V", "supply", "5"), ("+3V3", "supply", "3.3"), ("GND", "ground", "0"), ("AGND", "ground", "0")],
        "module_nets": [("NET_A", "alpha;beta")],
        "separate": [("AGND", "GND", "R205")],
        "chosen": [("pull", "role=pull;value=10k", "MP-10k", "SP-10k", "DC-001", "")],
    }


def s1_prop(name, text, x, y, hide=False, justify="", angle=0):
    return '    (property %s %s (at %s %s %s) %s)\n' % (
        s1_q(name), s1_q(text), s1_n(x), s1_n(y), angle,
        S1_FONT % ((" (justify %s)" % justify if justify else "") + (" (hide yes)" if hide else "")))


def s1_lib(names, powers):
    out = []
    for name in sorted(names):
        s = S1_SYMS[name]
        bx, by = s["body"]
        pins = "".join('        (pin %s line (at %s %s %s) (length %s) (name %s %s) (number %s %s))\n'
                       % (t, s1_n(x), s1_n(y), a, s1_n(ln), s1_q(nm), S1_FONT % "", s1_q(n), S1_FONT % "")
                       for n, nm, t, x, y, a, ln in s["pins"])
        out.append('    (symbol "fx:%s" (exclude_from_sim no) (in_bom yes) (on_board yes)\n%s%s'
                   '      (symbol "%s_0_1" (rectangle (start %s %s) (end %s %s) (stroke (width 0.254) (type default)) '
                   '(fill (type none))))\n      (symbol "%s_1_1"\n%s      )\n      (embedded_fonts no))\n'
                   % (name, s1_prop("Reference", name[0], 0, 0).replace("    (", "      (", 1),
                      s1_prop("Value", name, 0, 0).replace("    (", "      (", 1),
                      name, s1_n(-bx), s1_n(-by), s1_n(bx), s1_n(by), name, pins))
    for name in sorted(powers):
        end = -2.54 if name in S1_DOWN else 2.54
        out.append('    (symbol "fx:%s" (power global) (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes)) '
                   '(exclude_from_sim no) (in_bom yes) (on_board yes)\n%s%s'
                   '      (symbol "%s_0_1" (polyline (pts (xy 0 0) (xy 0 %s)) (stroke (width 0) (type default)) '
                   '(fill (type none))))\n      (symbol "%s_1_1"\n        (pin power_in line (at 0 0 90) (length 0) '
                   '(name "~" %s) (number "1" %s))\n      )\n      (embedded_fonts no))\n'
                   % (name, s1_prop("Reference", "#PWR", 0, 0, hide=True).replace("    (", "      (", 1),
                      s1_prop("Value", name, 0, 0).replace("    (", "      (", 1), name, s1_n(end), name,
                      S1_FONT % "", S1_FONT % ""))
    return "".join(out)


def s1_placed(lib_id, ref, at, rot, mirror, props, path, pins, dnp=False):
    return ('  (symbol (lib_id %s) (at %s %s %s)%s (unit 1) (body_style 1) (exclude_from_sim no) (in_bom yes) '
            '(on_board yes) (in_pos_files yes) (dnp %s) (uuid "%s")\n%s%s'
            '    (instances (project "%s" (path "%s" (reference %s) (unit 1)))))\n'
            % (s1_q(lib_id), s1_n(at[0]), s1_n(at[1]), rot, " (mirror %s)" % mirror if mirror else "",
               "yes" if dnp else "no", s1_uid("sym", ref), props,
               "".join('    (pin %s (uuid "%s"))\n' % (s1_q(n), s1_uid("pin", ref, n)) for n in pins),
               S1_NAME, path, s1_q(ref)))


def s1_wire(a, b):
    return ('  (wire (pts (xy %s %s) (xy %s %s)) (stroke (width 0) (type default)) (uuid "%s"))\n'
            % (s1_n(a[0]), s1_n(a[1]), s1_n(b[0]), s1_n(b[1]), s1_uid("wire", a, b)))


def s1_label(kind, name, at, left, key):
    word = {"lab": "label", "hier": "hierarchical_label", "glob": "global_label"}[kind]
    just = ("right" if left else "left") + (" bottom" if kind == "lab" else "")
    return '  (%s %s%s (at %s %s %s) %s (uuid "%s"))\n' % (
        word, s1_q(name), "" if kind == "lab" else " (shape input)", s1_n(at[0]), s1_n(at[1]), 180 if left else 0,
        S1_FONT % (" (justify %s)" % just), s1_uid(kind, key, name))


def s1_sheet_text(spec, module, links, powers_used):
    """One module sheet. links gets (pin key, token) pairs, the connections the netlist is worked out from."""
    path = "/%s/%s" % (s1_uid("root"), s1_uid("sheet", module))
    body, syms, pw = [], set(), set()
    for name, i in zip(spec["labels"].get(module, []), range(99)):
        body.append(s1_label("hier", name, (50.8, 50.8 + 7.62 * i), True, (module, "alone")))
        links.append((None, ("h", module, name)))
    for p in spec["parts"].get(module, []):
        s = S1_SYMS[p["sym"]]
        syms.add(p["sym"])
        x, y = p["at"]
        ra, va = p["ref_at"] or s["ref"], p["val_at"] or s["val"]
        props = (s1_prop("Reference", p["ref"], x + ra[0], y + ra[1], justify=ra[2]) +
                 s1_prop("Value", p["value"], x + va[0], y + va[1], justify=va[2]) +
                 s1_prop("Footprint", "fx:" + p["sym"], x, y, hide=True) +
                 s1_prop("Datasheet", p["datasheet"], x, y, hide=True) +
                 s1_prop("Description", p["description"], x, y, hide=True) +
                 s1_prop("Manufacturer", "Maker", x, y, hide=True) + s1_prop("MPN", p["mpn"], x, y, hide=True) +
                 s1_prop("Supplier", "SUPPLIER-A", x, y, hide=True) +
                 s1_prop("Supplier PN", p["spn"], x, y, hide=True))
        body.append(s1_placed("fx:" + p["sym"], p["ref"], (x, y), p["rot"], p["mirror"], props, path,
                              [n for n, _, _, _, _, _, _ in s["pins"]], p["dnp"]))
        for n, nm, t, px, py, ang, ln in s["pins"]:
            att = p["pins"].get(n)
            if att is None:
                continue
            dx, dy = S1_STUB[ang]
            a = s1_xy(px, py, p["rot"], p["mirror"])
            b = s1_xy(px + dx, py + dy, p["rot"], p["mirror"])
            a, b = (x + a[0], y + a[1]), (x + b[0], y + b[1])
            body.append(s1_wire(a, b))
            for kind, name in (att if isinstance(att, list) else [att]):
                if kind == "pwr":
                    pw.add(name)
                    pref = "#PWR%s%s%s" % (module, p["ref"], n)
                    down = name in S1_DOWN
                    body.append(s1_placed("fx:" + name, pref, b, 0, "",
                                          s1_prop("Reference", pref, b[0], b[1], hide=True) +
                                          s1_prop("Value", name, b[0], b[1] + (3.81 if down else -3.556)),
                                          path, ["1"]))
                    links.append(((p["ref"], n), ("g", name)))
                else:
                    body.append(s1_label(kind, name, b, b[0] < a[0], (p["ref"], n)))
                    links.append(((p["ref"], n), ("g", name) if kind == "glob" else (kind[0], module, name)))
    powers_used |= pw
    return ('(kicad_sch (version 20260306) (generator "eeschema") (generator_version "10.0") (uuid "%s")\n'
            '  (paper "A3")\n  (lib_symbols\n%s  )\n%s%s  (embedded_fonts no)\n)\n'
            % (s1_uid("file", module), s1_lib(syms, pw), "".join(body), spec["extra"].get(module, "")))


def s1_root_text(spec):
    """The top sheet: one box per module, the nets of spec["top"] between them, a label on each."""
    out, pins = [], {}
    for i, (module, _, _) in enumerate(spec["modules"]):
        nets = [n for n in sorted(spec["top"]) if module in spec["top"][n]]
        x, y = 50.8, 50.8 + 35.56 * i
        ptxt = ""
        for k, net in enumerate(nets):
            at = (x + 30.48, y + 5.08 + 5.08 * k)
            pins.setdefault(net, []).append(at)
            ptxt += '    (pin %s input (at %s %s 0) (uuid "%s") %s)\n' % (
                s1_q(net), s1_n(at[0]), s1_n(at[1]), s1_uid("spin", module, net), S1_FONT % " (justify right)")
        out.append('  (sheet (at %s %s) (size 30.48 25.4) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
                   '    (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0)) (uuid "%s")\n'
                   '    (property "Sheetname" %s (at %s %s 0) %s)\n    (property "Sheetfile" %s (at %s %s 0) %s)\n%s'
                   '    (instances (project "%s" (path "/%s" (page "%d")))))\n'
                   % (s1_n(x), s1_n(y), s1_uid("sheet", module), s1_q(module), s1_n(x), s1_n(y - 0.7116),
                      S1_FONT % " (justify left bottom)", s1_q(module + ".kicad_sch"), s1_n(x), s1_n(y + 25.9846),
                      S1_FONT % " (justify left top)", ptxt, S1_NAME, s1_uid("root"), i + 2))
    for k, net in enumerate(sorted(pins)):
        tx = 96.52 + 7.62 * k
        ends = sorted(pins[net], key=lambda p: p[1])
        for at in ends:
            out.append(s1_wire(at, (tx, at[1])))
        for a, b in zip(ends, ends[1:]):
            out.append(s1_wire((tx, a[1]), (tx, b[1])))
        for at in ends[1:-1]:
            out.append('  (junction (at %s %s) (diameter 0) (color 0 0 0 0) (uuid "%s"))\n'
                       % (s1_n(tx), s1_n(at[1]), s1_uid("junction", net, at)))
        out.append(s1_label("lab", net, (ends[0][0] + 2.54, ends[0][1]), False, ("top", net)))
    return ('(kicad_sch (version 20260306) (generator "eeschema") (generator_version "10.0") (uuid "%s")\n'
            '  (paper "A3")\n  (lib_symbols)\n%s%s  (sheet_instances (path "/" (page "1")))\n  (embedded_fonts no)\n)\n'
            % (s1_uid("root"), "".join(out), spec["extra"].get("", "")))


def s1_netlist_text(spec, links):
    """The netlist in the form KiCad exports, worked out from the pins and what each one is drawn on."""
    group = {}

    def top(t):
        while group.setdefault(t, t) != t:
            t = group[t]
        return t
    for net, modules in spec["top"].items():
        for m in modules:
            group[top(("h", m, net))] = top(("l", "", net))
    for pin, token in links:
        if pin is not None:
            group[top(("pin",) + pin)] = top(token)
    home = dict((p["ref"], m) for m, parts in spec["parts"].items() for p in parts)
    whole = set((home[pin[0]], token[-1]) for pin, token in links if pin is not None and token[0] == "g")
    for t in list(group):                       # KiCad joins a label to a power symbol of its name on its sheet
        if t[0] in ("l", "h") and (t[1], t[-1]) in whole:
            group[top(t)] = top(("g", t[-1]))
    names = {}
    for t in list(group):
        if t[0] != "pin":
            rank = {"g": (0, t[-1]), "l": (1 if t[1] == "" else 3, "/%s%s%s" % (t[1], "/" if t[1] else "", t[-1])),
                    "h": (2, "/%s/%s" % (t[1], t[-1]))}[t[0]]
            names[top(t)] = min(names.get(top(t), rank), rank)
    comps, libparts, nets = [], {}, {}
    for module, _, _ in spec["modules"]:
        for p in spec["parts"].get(module, []):
            s = S1_SYMS[p["sym"]]
            fields = [("Manufacturer", "Maker"), ("MPN", p["mpn"]), ("Supplier", "SUPPLIER-A"), ("Supplier PN", p["spn"])]
            comps.append(
                "    (comp (ref %s) (value %s) (footprint %s) (datasheet %s) (description %s)\n      (fields %s)\n"
                "      (libsource (lib \"fx\") (part %s) (description \"\"))\n"
                "      (property (name \"Sheetname\") (value %s)) (property (name \"Sheetfile\") (value %s))%s\n"
                "      (sheetpath (names \"/%s/\") (tstamps \"/%s/\")) (tstamps %s)\n      (units (unit (name \"A\") (pins %s))))\n"
                % (s1_q(p["ref"]), s1_q(p["value"]), s1_q("fx:" + p["sym"]), s1_q(p["datasheet"]), s1_q(p["description"]),
                   " ".join("(field (name %s) %s)" % (s1_q(k), s1_q(v)) for k, v in fields), s1_q(p["sym"]),
                   s1_q(module), s1_q(module + ".kicad_sch"), ' (property (name "dnp"))' if p["dnp"] else "",
                   module, s1_uid("sheet", module), s1_q(s1_uid("sym", p["ref"])),
                   " ".join("(pin (num %s))" % s1_q(x[0]) for x in s["pins"])))
            libparts[p["sym"]] = s["pins"]
            for n, nm, t, _, _, _, _ in s["pins"]:
                key = ("pin", p["ref"], n)
                name = names[top(key)][1] if key in group else "unconnected-(%s-Pad%s)" % (p["ref"], n)
                nets.setdefault(name, []).append((p["ref"], n, "%s_%s" % (nm, n), t))      # KiCad 10 writes name_number
    lp = "".join("    (libpart (lib \"fx\") (part %s) (pins %s))\n"
                 % (s1_q(sym), " ".join("(pin (num %s) (name %s) (type %s))" % (s1_q(x[0]), s1_q(x[1]), s1_q(x[2]))
                                         for x in pins)) for sym, pins in sorted(libparts.items()))
    ns = "".join("    (net (code \"%d\") (name %s) (class \"Default\") %s)\n"
                 % (i + 1, s1_q(name), " ".join("(node (ref %s) (pin %s)%s (pintype %s))"
                                                 % (s1_q(r), s1_q(p), " (pinfunction %s)" % s1_q(f) if f else "", s1_q(t))
                                                 for r, p, f, t in sorted(nodes)))
                 for i, (name, nodes) in enumerate(sorted(nets.items())))
    return ('(export (version "E")\n  (design (source "%s.kicad_sch") (date "") (tool "Eeschema 10.0"))\n'
            "  (components\n%s  )\n  (libparts\n%s  )\n  (nets\n%s  )\n)\n" % (S1_NAME, "".join(comps), lp, ns))


S1_DECISIONS = """# Decisions

## Use one 10k part for every pull (DC-001)
Kind: decision
Decided by: user
Date: 2026-01-02
Stage: ST4
Options: one part for every pull (chosen); a part chosen per position
Reason: fewer lines to buy
Affects: requirements none; parts every pull; schematic none; board none; cost lower
Status: in force
"""
S1_PARTS_HEAD = ("refs,value,footprint,package,manufacturer,mpn,supplier,supplier_pn,role,category,dielectric,"
                 "tolerance,voltage_rating,unit_price,qty_price,stock,checked,lifecycle,temp_grade,msl,peak_reflow,"
                 "alternate,variant,datasheet,datasheet_revision,errata,compliance_done,pins_done,model,model_checked\n")
S1_PINS_HEAD = ("designator,mpn,pin,name,functions,used_function,net,supply,levels,abs_max,current_limit,reset_state,"
                "boot_activity,control_input,required_in_reset,given_by,sleep_state,fault_state,source,source_page,"
                "confirmed\n")


def s1_project(dest, change=None, netlist=True):
    """Write the project into dest (created) and return dest. change(spec) plants a fault before it is drawn."""
    spec = s1_spec()
    if change:
        change(spec)
    hw, design = os.path.join(dest, "hardware"), os.path.join(dest, "design")
    for d in (os.path.join(hw, "fx.pretty"), design):
        os.makedirs(d, exist_ok=True)
    links, powers = [], set()
    files = {}
    for module, _, _ in spec["modules"]:
        if module not in spec.get("no_file", ()):
            files["hardware/%s.kicad_sch" % module] = s1_sheet_text(spec, module, links, powers)
    files["hardware/%s.kicad_sch" % S1_NAME] = s1_root_text(spec)
    parts = [p for m, _, _ in spec["modules"] for p in spec["parts"].get(m, [])]
    files["design/parts.csv"] = S1_PARTS_HEAD + "".join(
        "%s,%s,fx:%s,,Maker,%s,SUPPLIER-A,%s,%s,,,,,,,,,,,,,,,%s,,,,,,\n"
        % (p["ref"], p["value"], p["sym"], "MP-" + p["value"], "SP-" + p["value"], p["role"],
           "ds/MP-%s.pdf" % p["value"]) for p in parts)
    files["design/pins.csv"] = S1_PINS_HEAD
    files["design/rails.csv"] = "rail,kind,voltage,source,note\n" + "".join(
        "%s,%s,%s,,\n" % r for r in spec["rails"])
    files["design/modules.csv"] = "module,sheet,ref_block,purpose\n" + "".join(
        "%s,%s.kicad_sch,%s,%s\n" % (m, m, b, why) for m, b, why in spec.get("module_rows", spec["modules"]))
    files["design/module-nets.csv"] = "net,modules,note\n" + "".join("%s,%s,\n" % r for r in spec["module_nets"])
    files["design/separate-nets.csv"] = "net_a,net_b,link_part,reason\n" + "".join(
        "%s,%s,%s,kept apart\n" % r for r in spec["separate"])
    files["design/chosen-parts.csv"] = "kind,match,mpn,supplier_pn,decision,except_refs\n" + "".join(
        "%s,%s,%s,%s,%s,%s\n" % r for r in spec["chosen"])
    files["design/decisions.md"] = S1_DECISIONS + spec.get("decisions", "")
    files["design/requirements.md"] = "# Requirements\n\n## Test points\n\nNone asked for.\n"
    files["hardware/fp-lib-table"] = ('(fp_lib_table\n\t(version 7)\n\t(lib (name "fx")(type "KiCad")'
                                      '(uri "${KIPRJMOD}/fx.pretty")(options "")(descr "fixture footprints"))\n)\n')
    for sym, s in S1_SYMS.items():
        files["hardware/fx.pretty/%s.kicad_mod" % sym] = (
            '(footprint "%s" (version 20260206) (generator "pcbnew") (layer "F.Cu")\n%s)\n'
            % (sym, "".join('  (pad "%s" smd rect (at %s 0) (size 1 1) (layers "F.Cu" "F.Mask" "F.Paste"))\n'
                            % (x[0], 2 * i) for i, x in enumerate(s["pins"]))))
    if netlist:
        files["hardware/%s.net" % S1_NAME] = s1_netlist_text(spec, links)      # written last: never older than a sheet
    for rel, text in files.items():
        with open(os.path.join(dest, rel), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return dest


# ---- S1 tests

def s1(ctx, proj, *args, cli=False):
    """Run sch_check.py on a project; with cli False, kicad-cli is hidden from it."""
    env = None if cli else {"KICAD_CLI": os.path.join(proj, "no-kicad-cli-here")}
    return chk(ctx, "sch_check.py", *(list(args) + ["--project", proj, "--name", S1_NAME]), env=env)


def s1_get(spec, ref):
    for parts in spec["parts"].values():
        for p in parts:
            if p["ref"] == ref:
                return p
    raise KeyError(ref)


def s1_set(which, **kw):
    return lambda spec: s1_get(spec, which).update(kw)


def s1_pin(ref, pin, att):
    return lambda spec: s1_get(spec, ref)["pins"].update({pin: att})


def s1_add(module, part):
    return lambda spec: spec["parts"].setdefault(module, []).append(part)


def s1_key(key, value):
    return lambda spec: spec.update({key: value})


def s1_both(*changes):
    def change(spec):
        for c in changes:
            c(spec)
    return change


def s1_faults(ctx, f, tmp, command, cases, *extra):
    """Each case is (name, change, texts): the fault is drawn, and the command must fail and say each text."""
    for name, change, texts in cases:
        proj = s1_project(os.path.join(tmp, re.sub(r"\W+", "_", name)), change)
        expect_run(f, "%s with the fault: %s" % (command, name), s1(ctx, proj, command, *extra), 1, *texts)


def s1_r(ref, x, pin1, module_y=101.6, value="1k"):
    return s1_part(ref, "P2", value, x, module_y, {"1": pin1, "2": ("pwr", "GND")})


def s1_third_module(spec):
    spec["modules"].append(("gamma", "300-399", "more loads"))
    spec["parts"]["gamma"] = [s1_r("R301", 50.8, ("hier", "NET_A"))]
    spec["top"]["NET_A"].append("gamma")


def s1_second_net(kind):
    def change(spec):
        spec["parts"]["alpha"].append(s1_r("R105", 152.4, (kind, "NET_B")))
        spec["parts"]["beta"].append(s1_r("R208", 228.6, (kind, "NET_B")))
        if kind == "hier":
            spec["top"]["NET_B"] = ["alpha", "beta"]
    return change


def test_s1_rails(ctx):
    """sch_check rails: only a declared rail on a power symbol, one net per rail, nothing else on a rail
    wire, no rail on a label or sheet pin, no signal on a global label, the nets kept separate; and the
    check against the netlist."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = s1_project(os.path.join(tmp, "clean"))
        expect_run(f, "rails on the clean project", s1(ctx, proj, "rails"), 0, "rails: pass",
                   "declared and not drawn: +3V3", "agree with the netlist", "AGND and GND: joined by R205 only")
        s1_faults(ctx, f, tmp, "rails", (
            ("a power symbol that is no rail", s1_pin("C101", "1", ("pwr", "+9V")),
             ("alpha.kicad_sch", "power symbol +9V", "names no rail in design/rails.csv")),
            ("a rail on a local label", s1_pin("R104", "1", ("lab", "+5V")),
             ("rail +5V is on a local label",)),
            ("a rail on a hierarchical label", s1_both(s1_pin("R104", "1", ("hier", "+5V")),
                                                       lambda spec: spec["top"].update({"+5V": ["alpha"]})),
             ("rail +5V is on a hierarchical label", "rail +5V is on a sheet pin")),
            ("a rail split in two nets", s1_both(s1_pin("R104", "1", ("hier", "AGND")),
                                                 lambda spec: spec["top"].update({"AGND": ["alpha"]})),
             ("rail AGND is on a hierarchical label", "rail AGND is more than one net: AGND, /AGND")),
            ("a rail on a global label", s1_pin("R104", "1", ("glob", "+5V")), ("rail +5V is on a global label",)),
            ("a signal on a global label", s1_pin("R101", "2", ("glob", "EN_G")),
             ("signal EN_G is on a global label",)),
            ("two rails on one wire", s1_pin("C101", "1", [("pwr", "+5V"), ("pwr", "+3V3")]),
             ("two rails on one wire: +3V3, +5V",)),
            ("a label on a rail wire", s1_pin("C101", "1", [("pwr", "+5V"), ("lab", "X1")]),
             ("label X1 is on the wire of rail +5V",)),
            ("a second part joining two separate nets",
             s1_add("beta", s1_part("R206", "P2", "0R", 228.6, 101.6, {"1": ("pwr", "AGND"), "2": ("pwr", "GND")})),
             ("R206 joins AGND and GND", "only R205 may")),
            ("separate nets on one wire", s1_pin("R205", "1", [("pwr", "AGND"), ("pwr", "GND")]),
             ("two rails on one wire: AGND, GND", "AGND and GND are joined by a wire")),
        ))
        # the netlist is older than the drawing says: pins drawn on one wire, two nets in the netlist
        stale = s1_project(os.path.join(tmp, "stale"))
        net = os.path.join(stale, "hardware", S1_NAME + ".net")
        text = fread(net)
        node = '(node (ref "R101") (pin "2") (pinfunction "~_2") (pintype "passive"))'
        expect(f, node in text, "the fixture netlist has no node for R101 pin 2")
        fwrite(net, text.replace(node, "").replace('(name "AGND") (class "Default") ',
                                                    '(name "AGND") (class "Default") ' + node + " "))
        expect_run(f, "rails with a netlist that differs from the drawing", s1(ctx, stale, "rails"), 1,
                   "drawing and netlist disagree", "R101.2")
        # no netlist and no kicad-cli: the drawing rules still run, and the result says what was not proved
        bare = s1_project(os.path.join(tmp, "bare"), netlist=False)
        expect_run(f, "rails with no netlist and no kicad-cli", s1(ctx, bare, "rails"), 0,
                   "NOT PROVEN against KiCad's netlist", "rails: pass (NOT PROVEN against KiCad's netlist)")
        bare2 = s1_project(os.path.join(tmp, "bare2"), s1_pin("C101", "1", ("pwr", "+9V")), netlist=False)
        expect_run(f, "rails with no netlist and a power symbol that is no rail", s1(ctx, bare2, "rails"), 1,
                   "power symbol +9V")
        os.remove(os.path.join(bare, "design", "rails.csv"))
        expect_run(f, "rails with no rails.csv", s1(ctx, bare, "rails"), 2, "design/rails.csv")
        fwrite(os.path.join(bare2, "design", "rails.csv"), "rail,voltage\n+5V,5\n")
        expect_run(f, "rails with a wrong header in rails.csv", s1(ctx, bare2, "rails"), 2, "rails.csv", "header")
    return f


def test_s1_modules(ctx):
    """sch_check modules: the tables agree, one sheet per module, designators in the module's block, and
    every net between sheets is a table net that joins only its listed modules."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = s1_project(os.path.join(tmp, "clean"))
        expect_run(f, "modules on the clean project", s1(ctx, proj, "modules"), 0, "modules: pass",
                   "NET_A: alpha, beta")
        rows = s1_spec()["modules"]
        page = s1_project(os.path.join(tmp, "page"), s1_both(
            lambda spec: spec["modules"].append(("closing", "", "a page with no circuit")), s1_key("module_rows", rows)))
        expect_run(f, "modules with a closing sheet that holds no circuit", s1(ctx, page, "modules"), 0,
                   "modules: pass", "sheet closing.kicad_sch holds text only")
        s1_faults(ctx, f, tmp, "modules", (
            ("a module with no sheet", s1_key("module_rows", rows + [("gamma", "300-399", "more")]),
             ("module gamma: sheet gamma.kicad_sch is not in the drawing",)),
            ("a sheet with no module row", s1_key("module_rows", rows[:1]),
             ("sheet beta.kicad_sch is in the drawing and has no row in design/modules.csv",)),
            ("a designator outside its block", s1_set("R207", ref="R307"),
             ("beta.kicad_sch", "R307 is outside the block 200-299 of module beta")),
            ("blocks that overlap", s1_key("module_rows", [rows[0], ("beta", "150-299", "loads")]),
             ("blocks overlap", "100-199", "150-299")),
            ("a block that is no range", s1_key("module_rows", [rows[0], ("beta", "2xx", "loads")]),
             ("modules.csv line 3", "ref_block")),
            ("a net row naming an unknown module", s1_key("module_nets", [("NET_A", "alpha;delta")]),
             ("module-nets.csv line 2", "names module delta, which is not in design/modules.csv")),
            ("a net row with one module", s1_key("module_nets", [("NET_A", "alpha")]),
             ("module-nets.csv line 2", "fewer than two modules")),
            ("a net between sheets that is in no row", s1_second_net("hier"),
             ("net NET_B joins modules alpha, beta and is not in design/module-nets.csv",)),
            ("a signal between sheets on a global label", s1_second_net("glob"),
             ("net NET_B joins modules alpha, beta and is not in design/module-nets.csv",)),
            ("a net that joins a module not listed for it", s1_third_module,
             ("net NET_A joins module gamma, which design/module-nets.csv does not list for it",)),
            ("a second part joining two separate nets",
             s1_add("beta", s1_part("R206", "P2", "0R", 228.6, 101.6, {"1": ("pwr", "AGND"), "2": ("pwr", "GND")})),
             ("R206 joins AGND and GND",)),
            ("a part on the top sheet",
             s1_key("extra", {"": '  (symbol (lib_id "fx:P2") (at 152.4 50.8 0) (unit 1) (uuid "%s")\n'
                                  '    (property "Reference" "R1" (at 156.21 49.53 0))\n'
                                  '    (property "Value" "1k" (at 156.21 52.07 0)))\n' % s1_uid("top part")}),
             ("top sheet", "R1", "only the module boxes")),
        ))
        later = s1_project(os.path.join(tmp, "later"), s1_key("module_nets", [("NET_A", "alpha;beta"),
                                                                              ("NET_C", "alpha;beta")]))
        expect_run(f, "modules with a table net not drawn yet", s1(ctx, later, "modules"), 0, "modules: pass",
                   "NET_C: not drawn yet")
        expect_run(f, "modules --probe with no kicad-cli", s1(ctx, proj, "modules", "--probe"), 2, "kicad-cli")
        fwrite(os.path.join(later, "design", "module-nets.csv"), "net,module\nNET_A,alpha;beta\n")
        expect_run(f, "modules with a wrong header in module-nets.csv", s1(ctx, later, "modules"), 2,
                   "module-nets.csv", "header")
        os.remove(os.path.join(later, "hardware", S1_NAME + ".net"))
        fwrite(os.path.join(later, "design", "module-nets.csv"), "net,modules,note\nNET_A,alpha;beta,\n")
        expect_run(f, "modules with no netlist and no kicad-cli", s1(ctx, later, "modules"), 2, "netlist")
        os.remove(os.path.join(later, "design", "modules.csv"))
        expect_run(f, "modules with no modules.csv", s1(ctx, later, "modules"), 2, "design/modules.csv")
    return f


def s1_skeleton(spec):
    """The empty skeleton: the module sheets hold their hierarchical labels and nothing else."""
    spec["parts"] = {}
    spec["labels"] = {"alpha": ["NET_A", "NET_B"], "beta": ["NET_A", "NET_B"]}
    spec["top"] = {"NET_A": ["alpha", "beta"], "NET_B": ["alpha", "beta"]}
    spec["module_nets"] = [("NET_A", "alpha;beta"), ("NET_B", "alpha;beta")]
    spec["separate"] = []


def test_kicad_s1_netlist(ctx):
    """The S1 fixture is honest: KiCad's netlist of it holds the nets the fixture works out. Then rails
    and modules export the netlist themselves when the project has none, and say they are proved."""
    ctx.need_cli()
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = s1_project(os.path.join(tmp, "clean"))
        hw = os.path.join(proj, "hardware")
        own = os.path.join(hw, S1_NAME + ".net")
        theirs = os.path.join(tmp, "kicad.net")
        res = run([ctx.cli, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", theirs,
                   os.path.join(hw, S1_NAME + ".kicad_sch")])
        if not expect(f, os.path.isfile(theirs), "kicad-cli exported no netlist of the fixture: %s" % res[1][-300:]):
            return f
        a, b = ctx.h.read_netlist(own)[1], ctx.h.read_netlist(theirs)[1]
        for name in sorted(set(a) | set(b)):
            expect(f, a.get(name) == b.get(name), "net %s: the fixture says %s, KiCad says %s" % (name, a.get(name), b.get(name)))
        os.remove(own)
        before = sorted(os.listdir(hw))
        expect_run(f, "rails exporting its own netlist", s1(ctx, proj, "rails", cli=True), 0, "rails: pass",
                   "agree with the netlist", "exported by kicad-cli for this run")
        expect_run(f, "modules exporting its own netlist", s1(ctx, proj, "modules", cli=True), 0, "modules: pass")
        expect(f, sorted(os.listdir(hw)) == before and not os.path.exists(os.path.join(proj, ".hwtmp")),
               "the export left files behind: %s, .hwtmp %s" % (sorted(os.listdir(hw)), os.path.exists(os.path.join(proj, ".hwtmp"))))
        for name, change, command, texts in (
                ("a rail on a local label", s1_pin("R104", "1", ("lab", "+5V")), "rails",
                 ("rail +5V is on a local label", "agree with the netlist")),
                ("a rail on a hierarchical label", s1_both(s1_pin("R104", "1", ("hier", "+5V")),
                                                           lambda spec: spec["top"].update({"+5V": ["alpha"]})), "rails",
                 ("rail +5V is on a hierarchical label", "agree with the netlist")),
                ("a rail split in two nets", s1_both(s1_pin("R104", "1", ("hier", "AGND")),
                                                     lambda spec: spec["top"].update({"AGND": ["alpha"]})), "rails",
                 ("rail AGND is more than one net: AGND, /AGND", "agree with the netlist")),
                ("separate nets on one wire", s1_pin("R205", "1", [("pwr", "AGND"), ("pwr", "GND")]), "rails",
                 ("AGND and GND are joined by a wire",)),
                ("a net between sheets that is in no row", s1_second_net("hier"), "modules",
                 ("net NET_B joins modules alpha, beta and is not in design/module-nets.csv",)),
                ("a net that joins a module not listed for it", s1_third_module, "modules",
                 ("net NET_A joins module gamma",))):
            bad = s1_project(os.path.join(tmp, re.sub(r"\W+", "_", name)), change, netlist=False)
            expect_run(f, "%s on KiCad's own netlist with the fault: %s" % (command, name),
                       s1(ctx, bad, command, cli=True), 1, *texts)
    return f


def test_kicad_s1_probe(ctx):
    """sch_check modules --probe: a test point on every hierarchical label of a throw-away copy; each table
    net must reach its listed modules; a planted fault must be caught; nothing is left behind."""
    ctx.need_cli()
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = s1_project(os.path.join(tmp, "skeleton"), s1_skeleton, netlist=False)
        hw = os.path.join(proj, "hardware")
        before = dict((n, fread(os.path.join(hw, n))) for n in sorted(os.listdir(hw)) if n.endswith(".kicad_sch"))
        expect_run(f, "modules --probe on the empty skeleton", s1(ctx, proj, "modules", "--probe", cli=True), 0,
                   "modules: pass", "4 test points", "NET_A: alpha, beta", "NET_B: alpha, beta", "planted fault caught")
        after = dict((n, fread(os.path.join(hw, n))) for n in sorted(os.listdir(hw)) if n.endswith(".kicad_sch"))
        expect(f, before == after, "the probe changed the project's own sheet files")
        expect(f, not os.path.exists(os.path.join(proj, ".hwtmp")), "the probe copy was not removed")

        def unwired(spec):
            s1_skeleton(spec)
            spec["top"]["NET_B"] = ["alpha"]                 # beta's label has no pin on the top sheet
        bad = s1_project(os.path.join(tmp, "unwired"), unwired, netlist=False)
        expect_run(f, "modules --probe with a label not wired on the top sheet",
                   s1(ctx, bad, "modules", "--probe", cli=True), 1, "net NET_B does not reach module beta")

        def crossed(spec):
            s1_skeleton(spec)
            spec["modules"].append(("gamma", "300-399", "more"))
            spec["labels"]["gamma"] = ["NET_B"]
            spec["top"]["NET_B"] = ["alpha", "beta", "gamma"]
        bad = s1_project(os.path.join(tmp, "crossed"), crossed, netlist=False)
        expect_run(f, "modules --probe with a net wired to a module not listed",
                   s1(ctx, bad, "modules", "--probe", cli=True), 1, "net NET_B joins module gamma")

        def stray(spec):
            s1_skeleton(spec)
            spec["labels"]["beta"] = ["NET_A", "NET_B", "NET_Q"]
        bad = s1_project(os.path.join(tmp, "stray"), stray, netlist=False)
        expect_run(f, "modules --probe with a label that goes nowhere",
                   s1(ctx, bad, "modules", "--probe", cli=True), 1, "hierarchical label NET_Q of module beta")
        full = s1_project(os.path.join(tmp, "full"))
        expect_run(f, "modules --probe on the drawn project", s1(ctx, full, "modules", "--probe", cli=True), 0,
                   "modules: pass", "NET_A: alpha, beta", "planted fault caught")
        # the skeleton and the closing page as the generator library writes them
        made = os.path.join(tmp, "made")
        os.makedirs(os.path.join(made, "design"))
        for rel, text in (("design/modules.csv", "module,sheet,ref_block,purpose\nalpha,alpha.kicad_sch,100-199,first\n"
                                                 "beta,beta.kicad_sch,200-299,second\n"),
                          ("design/module-nets.csv", "net,modules,note\nNET_A,alpha;beta,a signal\n"),
                          ("design/rails.csv", "rail,kind,voltage,source,note\n+5V,supply,5,,\nGND,ground,0,,\n"),
                          ("design/firmware.md", "# Firmware instructions: fixture\n## alpha\ncan: NET_A on pin 3; the "
                           "level of the input; 0 to 3.3 V; 1 kHz. Source: sheet alpha. Status: decided with the user "
                           "(DC-001)\n")):
            fwrite(os.path.join(made, rel), text)
        os.makedirs(os.path.join(made, "hardware"))
        s = ctx.module("schlib").Schematic(os.path.join(made, "hardware", "t.kicad_sch"), date="2026-01-02")
        s.skeleton()
        s.firmware_page()
        if expect(f, s.write()[0] == 0, "the generated skeleton was not written"):
            env = None
            for args, texts in ((("modules", "--probe"), ("modules: pass", "2 test points", "NET_A: alpha, beta",
                                                          "planted fault caught", "holds text only")),
                                (("modules",), ("modules: pass", "NET_A: drawn, with no part pin on it yet",
                                              "holds text only")),
                                (("rails",), ("rails: pass", "agree with the netlist"))):
                expect_run(f, "%s on a generated skeleton with a closing page" % " ".join(args),
                           chk(ctx, "sch_check.py", *(list(args) + ["--project", made, "--name", "t"]), env=env), 0, *texts)
    return f


def test_s1_overlap(ctx):
    """sch_check overlap: text over other text, over a wire, and over another symbol."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = s1_project(os.path.join(tmp, "clean"), netlist=False)
        expect_run(f, "overlap on the clean project (no netlist needed)", s1(ctx, proj, "overlap"), 0, "overlap: pass")
        note = '  (text "note" (at 41.91 99.06 0) %s (uuid "%s"))\n' % (S1_FONT % "", s1_uid("note"))
        s1_faults(ctx, f, tmp, "overlap", (
            ("a value on its reference", s1_set("R101", val_at=(2.54, -1.27, "left")),
             ("alpha.kicad_sch", "R101 Value", "R101 Reference")),
            ("a note on a wire", s1_key("extra", {"alpha": note}), ('text "note"', "overlaps a wire")),
            ("a reference on another symbol", s1_set("C101", ref_at=(-25.4, 0, "")),
             ("C101 Reference", "overlaps symbol R101")),
            ("two labels on each other", s1_pin("R104", "1", [("lab", "X1"), ("lab", "X2")]),
             ('label "X1"', 'label "X2"')),
        ))
    return f


S1_EXCEPTION = """
## R207 keeps its own part (DC-002)
Kind: decision
Decided by: user
Date: 2026-01-03
Stage: ST5
Options: the chosen part (not chosen); its own part (chosen)
Reason: this position needs a tighter part
Affects: requirements none; parts R207; schematic none; board none; cost none
Status: in force
"""


def test_s1_chosen(ctx):
    """sch_check chosen: every position of a kind carries the chosen part, or is a recorded exception."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = s1_project(os.path.join(tmp, "clean"))
        expect_run(f, "chosen on the clean project", s1(ctx, proj, "chosen"), 0, "chosen: pass",
                   "R101: MP-10k, supplier number SP-10k", "R207: MP-10k, supplier number SP-10k", "pull: 2 positions")
        other = s1_set("R207", mpn="MP-OTHER", spn="SP-OTHER")
        s1_faults(ctx, f, tmp, "chosen", (
            ("a position with another part", other,
             ("R207", "kind pull", "MP-OTHER", "is not in except_refs")),
            ("a position with another supplier number", s1_set("R207", spn="SP-OTHER"),
             ("R207", "supplier number SP-OTHER", "is MP-10k, supplier number SP-10k")),
            ("an exception no decision names",
             s1_both(other, s1_key("chosen", [("pull", "role=pull;value=10k", "MP-10k", "SP-10k", "DC-001", "R207")])),
             ("R207 is in except_refs", "no user decision in design/decisions.md names it")),
            ("a match that cannot be read", s1_key("chosen", [("pull", "the pulls", "MP-10k", "SP-10k", "DC-001", "")]),
             ("chosen-parts.csv line 2", "match")),
            ("a row with no decision", s1_key("chosen", [("pull", "role=pull", "MP-10k", "SP-10k", "", "")]),
             ("chosen-parts.csv line 2", "decision")),
            ("a decision that is no entry", s1_key("chosen", [("pull", "role=pull", "MP-10k", "SP-10k", "DC-009", "")]),
             ("chosen-parts.csv line 2", "DC-009 is not an entry in design/decisions.md")),
        ))
        ok = s1_project(os.path.join(tmp, "excepted"), s1_both(
            other, s1_key("chosen", [("pull", "role=pull;value=10k", "MP-10k", "SP-10k", "DC-001", "R207")]),
            s1_key("decisions", S1_EXCEPTION)))
        expect_run(f, "chosen with a recorded exception", s1(ctx, ok, "chosen"), 0, "chosen: pass",
                   "R207: MP-OTHER, supplier number SP-OTHER (exception, DC-002)")
        os.remove(os.path.join(ok, "design", "chosen-parts.csv"))
        expect_run(f, "chosen with no chosen-parts.csv", s1(ctx, ok, "chosen"), 2, "design/chosen-parts.csv")
    return f


def test_s1_fields(ctx):
    """sch_check fields: supplier part number and datasheet link on every symbol, equal to parts.csv,
    and no link or description that names another part."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = s1_project(os.path.join(tmp, "clean"), netlist=False)
        expect_run(f, "fields on the clean project (no netlist needed)", s1(ctx, proj, "fields"), 0, "fields: pass",
                   "symbols checked: 11")
        s1_faults(ctx, f, tmp, "fields", (
            ("no supplier part number", s1_set("R104", spn=""), ("alpha.kicad_sch", "R104: no supplier part number")),
            ("no datasheet link", s1_set("R104", datasheet="~"), ("R104: no datasheet link",)),
            ("a datasheet link of another part", s1_set("R104", datasheet="ds/MP-10k.pdf"),
             ("R104: datasheet link ds/MP-10k.pdf names another part (MP-10k)",)),
            ("a description of another part", s1_set("R104", description="resistor MP-4k7 0603"),
             ("R104: description", "names another part (MP-4k7)")),
            ("a supplier number that differs from parts.csv", s1_set("R104", spn="SP-9"),
             ("R104: supplier part number SP-9 on the symbol, SP-1k in design/parts.csv",)),
            ("an MPN that differs from parts.csv", s1_set("R104", mpn="MP-9"),
             ("R104: MPN MP-9 on the symbol, MP-1k in design/parts.csv",)),
        ))
        dnp = s1_project(os.path.join(tmp, "dnp"), s1_set("R104", spn="", dnp=True), netlist=False)
        expect_run(f, "fields with a part that is not fitted", s1(ctx, dnp, "fields"), 0, "fields: pass",
                   "symbols checked: 10")
    return f


def test_s1_netload(ctx):
    """sch_check netload: the load on each rail and each driven net, summed across the sheets, with the
    share of a budget and a flag above the level."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = s1_project(os.path.join(tmp, "clean"))
        expect_run(f, "netload on the clean project", s1(ctx, proj, "netload"), 0,
                   "alpha.kicad_sch 5 mA", "beta.kicad_sch 500 uA", "+5V total: 5.5 mA",
                   "/NET_A", "driven by U101.2", "beta.kicad_sch up to 7.13 mA", "no budget given")
        res = s1(ctx, proj, "netload", "--budget", "+5V=0.0065")
        expect_run(f, "netload with a budget the rail nearly fills", res, 0, "92% of the budget 6.5 mA",
                   "ABOVE the level 80%")
        res = s1(ctx, proj, "netload", "--budget", "+5V=0.0065", "--level", "95")
        expect_run(f, "netload with a higher level", res, 0, "92% of the budget 6.5 mA")
        expect(f, "ABOVE" not in res[1], "netload flagged a rail under the level given")
        res = s1(ctx, proj, "netload", "--budget", "+5V=0.1")
        expect(f, "ABOVE" not in res[1] and "6% of the budget 100 mA" in res[1],
               "netload with a wide budget: %s" % res[1][-300:])
        more = s1_project(os.path.join(tmp, "more"), s1_add("beta", s1_r("R209", 228.6, ("pwr", "+5V"))))
        expect_run(f, "netload with one more load on another sheet", s1(ctx, more, "netload"), 0,
                   "beta.kicad_sch 5.5 mA", "+5V total: 10.5 mA")
        expect_run(f, "netload with a budget that cannot be read", s1(ctx, proj, "netload", "--budget", "+5V"), 2,
                   "--budget")
    return f


def test_s1_drive(ctx):
    """sch_check drive: one node feeding several transistor bases with no resistor each."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = s1_project(os.path.join(tmp, "clean"))
        expect_run(f, "drive on the clean project", s1(ctx, proj, "drive"), 0, "drive: pass")
        s1_faults(ctx, f, tmp, "drive", (
            ("two bases on one node", s1_pin("Q202", "1", ("lab", "B1")),
             ("net /beta/B1", "2 transistor bases", "Q201.1", "Q202.1", "no resistor each")),
        ))
        fets = s1_project(os.path.join(tmp, "fets"), s1_both(s1_pin("Q202", "1", ("lab", "B1")),
                                                             s1_set("Q201", sym="M3"), s1_set("Q202", sym="M3")))
        expect_run(f, "drive with two FET gates on one node", s1(ctx, fets, "drive"), 0, "drive: pass",
                   "2 gates share net /beta/B1")
    return f


def test_s1_pins_no_table(ctx):
    """sch_check pins: a part with no pin table still has its symbol pins compared with its footprint
    pads, and the missing table is still a fail."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = s1_project(os.path.join(tmp, "clean"))
        expect_run(f, "pins with no pin table", s1(ctx, proj, "pins"), 1,
                   "U101: checked without a pin table: 4 symbol pins, 4 footprint pads",
                   "U101 (MP-REG-1): no rows in pins.csv", "pins: FAIL (3)")
        mod = os.path.join(proj, "hardware", "fx.pretty", "U4.kicad_mod")
        fwrite(mod, "\n".join(l for l in fread(mod).splitlines() if '(pad "4"' not in l) + "\n")
        expect_run(f, "pins with no pin table and a pad missing", s1(ctx, proj, "pins"), 1,
                   "U101 pin 4: no pad 4 on the footprint", "pins: FAIL (4)")
        os.remove(os.path.join(proj, "design", "pins.csv"))
        expect_run(f, "pins with no pins.csv at all", s1(ctx, proj, "pins"), 1, "U101 pin 4: no pad 4 on the footprint")
    return f


def test_s1_all(ctx):
    """sch_check all: a check whose table the project does not have is named as not run, and is no fail."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = check_proj(ctx, tmp)
        res = chk(ctx, "sch_check.py", "all", "--project", proj)
        expect_run(f, "all on a project with none of the module tables", res, 0, "rails: not run (no design/rails.csv)",
                   "modules: not run (no design/modules.csv)", "chosen: not run (no design/chosen-parts.csv)",
                   "drive: pass", "== sch_check netload")
        own = s1_project(os.path.join(tmp, "own"))
        expect_run(f, "all on the module project", s1(ctx, own, "all"), 1, "rails: pass", "modules: pass",
                   "chosen: pass", "drive: pass", "pins: FAIL")
    return f


SCRIPT_TESTS += [
    ("S1 sch_check rails: declared rails only, and the proof against the netlist", test_s1_rails),
    ("S1 sch_check modules: tables, sheets, designator blocks, nets between modules", test_s1_modules),
    ("S1 sch_check overlap: text over text, a wire or a symbol", test_s1_overlap),
    ("S1 sch_check chosen: every position of a kind, exceptions", test_s1_chosen),
    ("S1 sch_check fields: supplier number, datasheet link, another part named", test_s1_fields),
    ("S1 sch_check netload: load summed across sheets, share of a budget", test_s1_netload),
    ("S1 sch_check drive: several bases on one node", test_s1_drive),
    ("S1 sch_check pins: a part with no pin table", test_s1_pins_no_table),
    ("S1 sch_check all: checks with no table are not run", test_s1_all),
    ("S1 KiCad: the fixture's netlist is KiCad's; rails and modules export their own", test_kicad_s1_netlist),
    ("S1 KiCad: modules --probe on the empty skeleton, with planted faults", test_kicad_s1_probe),
]
# ======================================================================== end of S1 section


# ======================================================================== T1 section (sch_check, after a known-answer trial)
# Four faults a trial project hid from sch_check: a table net joined to a rail, no control input marked,
# a declared rail with no voltage in its name, and review lines that said NONE and never failed.

T1_PIN_ROW = "U101,MP-REG-1,3,EN,enable,enable,EN_A,+5V,,,,,none,%s,%s,%s,,,datasheet table,,yes\n"


def t1_net_on_rail(spec):
    """NET_B is drawn between the modules, and in alpha its label sits on the wire of the +5V symbol."""
    spec["parts"]["alpha"].append(s1_part("R105", "P2", "1k", 152.4, 101.6,
                                          {"1": [("pwr", "+5V"), ("hier", "NET_B")], "2": ("pwr", "GND")}))
    spec["parts"]["beta"].append(s1_r("R208", 228.6, ("hier", "NET_B")))
    spec["top"]["NET_B"] = ["alpha", "beta"]
    spec["module_nets"] = [("NET_A", "alpha;beta"), ("NET_B", "alpha;beta")]


def t1_label_alone(spec):
    """NET_C is on a hierarchical label in each module, with no part pin on it yet."""
    spec["labels"] = {"alpha": ["NET_C"], "beta": ["NET_C"]}
    spec["top"]["NET_C"] = ["alpha", "beta"]
    spec["module_nets"] = [("NET_A", "alpha;beta"), ("NET_C", "alpha;beta")]


def t1_close_all(ctx, proj, reason):
    """Close every item of design/net-review.csv with a written reason."""
    nr = os.path.join(proj, "design", "net-review.csv")
    rows = ctx.h.read_table(nr)
    for r in rows:
        r.update({"reason": reason, "closed_by": "user", "date": "2026-01-02"})
    ctx.h.write_table(nr, "net-review.csv", rows)
    return len(rows)


def test_t1_modules_joined(ctx):
    """sch_check modules: a table net that is drawn, and that KiCad joined to another net, is a fail that
    names the other net. It is not "not drawn yet"."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = s1_project(os.path.join(tmp, "joined"), t1_net_on_rail)
        expect(f, '(name "NET_B")' not in fread(os.path.join(proj, "hardware", S1_NAME + ".net"))
               and '(name "/NET_B")' not in fread(os.path.join(proj, "hardware", S1_NAME + ".net")),
               "the fixture's netlist still has NET_B as a net of its own, so no fault is planted")
        res = s1(ctx, proj, "modules")
        expect_run(f, "modules with a table net drawn on a rail wire", res, 1,
                   "FAIL  net NET_B is drawn (", "alpha.kicad_sch", "is not a net of its own in the netlist",
                   "joined to net +5V")
        expect(f, "NET_B: not drawn yet" not in res[1], "modules said a drawn net is not drawn yet")
        alone = s1_project(os.path.join(tmp, "alone"), t1_label_alone)
        expect_run(f, "modules with a table net on labels and no part pin", s1(ctx, alone, "modules"), 0,
                   "modules: pass", "NET_C: drawn, with no part pin on it yet")
        later = s1_project(os.path.join(tmp, "later"), s1_key("module_nets", [("NET_A", "alpha;beta"),
                                                                              ("NET_C", "alpha;beta")]))
        expect_run(f, "modules with a table net on no label at all", s1(ctx, later, "modules"), 0, "modules: pass",
                   "NET_C: not drawn yet")
    return f


def test_t1_powerup_nothing(ctx):
    """sch_check powerup: with no control input in pins.csv the check is not run, and does not pass, unless
    design/status.md says the board has none. A pin named as an enable and marked "no" is a review line."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        proj = s1_project(os.path.join(tmp, "none"))
        pins = os.path.join(proj, "design", "pins.csv")
        fwrite(pins, S1_PINS_HEAD + T1_PIN_ROW % ("no", "", ""))
        res = s1(ctx, proj, "powerup")
        expect_run(f, "powerup with no control input marked", res, 2, "no row of design/pins.csv has control_input yes",
                   "review: U101 pin 3 (EN): control_input is no")
        expect(f, "powerup: pass" not in res[1], "powerup passed with no control input checked")
        res = s1(ctx, proj, "all")
        expect_run(f, "all with no control input marked", res, 1, "powerup: not run (no row of design/pins.csv")
        expect(f, "powerup: pass" not in res[1], "all printed a powerup pass with no control input checked")
        fwrite(os.path.join(proj, "design", "status.md"), "Designs: logical done\nControl inputs: none, DC-001\n")
        expect_run(f, "powerup on a board recorded as having no control inputs", s1(ctx, proj, "powerup"), 0,
                   "control inputs checked: 0 (design/status.md says the board has none)", "powerup: pass",
                   "review: U101 pin 3 (EN): control_input is no")
        fwrite(pins, S1_PINS_HEAD + T1_PIN_ROW % ("yes", "high", "R101"))
        res = s1(ctx, proj, "powerup")
        expect_run(f, "powerup with the enable marked", res, 0, "U101 pin 3 (EN), net /alpha/EN_A: high in reset",
                   "control inputs checked: 1", "powerup: pass")
        expect(f, "control_input is no" not in res[1], "powerup listed a marked control input for review")
    return f


def test_t1_currents_rails(ctx):
    """sch_check currents: a supply rail of design/rails.csv is at the voltage the table gives it."""
    f = []

    def rail(voltage):
        def change(spec):
            spec["rails"].append(("VSYS", "supply", voltage))
            spec["parts"]["alpha"].append(s1_part("R105", "P2", "10k", 152.4, 101.6,
                                                  {"1": ("pwr", "VSYS"), "2": ("lab", "X1")}))
        return change
    with tempfile.TemporaryDirectory() as tmp:
        proj = s1_project(os.path.join(tmp, "one"), rail("4.2"))
        res = s1(ctx, proj, "currents")
        expect_run(f, "currents with a resistor on a declared rail", res, 0, "VSYS 4.2 V",
                   "R105 10k pull-up to VSYS: up to 420 uA")
        expect(f, "R105 10k: neither end" not in res[1], "currents did not know a rail declared with its voltage")
        span = s1_project(os.path.join(tmp, "span"), rail("3.0 to 4.2"))
        expect_run(f, "currents with a rail declared as a range", s1(ctx, span, "currents"), 0,
                   "VSYS 4.2 V (the highest of 3.0 to 4.2)", "R105 10k pull-up to VSYS: up to 420 uA")
        expect_run(f, "currents with --rail over the table", s1(ctx, span, "currents", "--rail", "VSYS=3"), 0,
                   "R105 10k pull-up to VSYS: up to 300 uA")
        words = s1_project(os.path.join(tmp, "words"), rail("follows the cell"))
        expect_run(f, "currents with a rail voltage that is no number", s1(ctx, words, "currents"), 0,
                   "VSYS: voltage 'follows the cell' not read", "R105 10k: neither end at a known voltage")
    return f


def test_t1_review_none(ctx):
    """sch_check opendrain and decouple-list: an open-drain net with no pull, and supply pins with no
    capacitor to ground, each fail until the item is closed with a reason in design/net-review.csv."""
    f = []
    with tempfile.TemporaryDirectory() as tmp:
        clean = check_proj(ctx, tmp)
        res = chk(ctx, "sch_check.py", "opendrain", "--project", clean)
        expect_run(f, "opendrain with a pull on every net", res, 0, "/INT: 1 pull: R5 10k to +3V3")
        expect(f, "FAIL" not in res[1], "opendrain failed a net that has its pull")
        nopull = check_proj(ctx, tmp, "no_int_pull")
        expect_run(f, "opendrain with no pull on a net", chk(ctx, "sch_check.py", "opendrain", "--project", nopull), 1,
                   "/INT: 0 pulls: NONE", "FAIL  open-drain net /INT has no pull", "opendrain: FAIL (1)")
        expect_run(f, "opendrain --record with no pull on a net",
                   chk(ctx, "sch_check.py", "opendrain", "--record", "--project", nopull), 1, "opendrain: FAIL (1)")
        expect(f, t1_close_all(ctx, nopull, "pull is inside the reader on the cable (DC-001)") > 0,
               "opendrain --record wrote no item to close")
        res = chk(ctx, "sch_check.py", "opendrain", "--project", nopull)
        expect_run(f, "opendrain with the item closed by a reason", res, 0, "/INT: 0 pulls: NONE [closed by user")
        expect(f, "FAIL" not in res[1], "opendrain failed an item that is closed with a reason")
        # a supply pin with no capacitor to ground: the capacitor of the fixture moved off the rail
        proj = s1_project(os.path.join(tmp, "clean"))
        res = s1(ctx, proj, "decouple-list")
        expect_run(f, "decouple-list on the clean project", res, 0, "+5V: supply pins: U101.1; capacitors to ground: C101")
        expect(f, "FAIL" not in res[1], "decouple-list failed a supply pin that has its capacitor")
        bare = s1_project(os.path.join(tmp, "bare"), s1_pin("C101", "1", ("lab", "X9")))
        expect_run(f, "decouple-list with no capacitor on a supply pin", s1(ctx, bare, "decouple-list"), 1,
                   "+5V: supply pins: U101.1; capacitors to ground: NONE",
                   "FAIL  supply net +5V has supply pins (U101.1) and no capacitor to ground", "decouple-list: FAIL (1)")
        expect_run(f, "decouple-list --record with no capacitor", s1(ctx, bare, "decouple-list", "--record"), 1,
                   "decouple-list: FAIL (1)")
        t1_close_all(ctx, bare, "capacitor is on the supply board (DC-001)")
        res = s1(ctx, bare, "decouple-list")
        expect_run(f, "decouple-list with the item closed by a reason", res, 0, "capacitors to ground: NONE [closed by user")
        expect(f, "FAIL" not in res[1], "decouple-list failed an item that is closed with a reason")
        expect_run(f, "all with no capacitor on a supply pin", s1(ctx, s1_project(os.path.join(tmp, "bare2"), s1_pin(
            "C101", "1", ("lab", "X9"))), "all"), 1, "decouple-list: FAIL (1)")
    return f


SCRIPT_TESTS += [
    ("T1 sch_check modules: a table net joined to another net", test_t1_modules_joined),
    ("T1 sch_check powerup: no control input marked is not a pass", test_t1_powerup_nothing),
    ("T1 sch_check currents: rail voltages from the rails table", test_t1_currents_rails),
    ("T1 sch_check opendrain, decouple-list: a line that says NONE fails until closed", test_t1_review_none),
]
# ======================================================================== end of T1 section



def run_script_tests(root, results):
    if not os.path.isfile(os.path.join(root, "tests", "fixtures.py")):
        results.report("script tests", [], "tests/fixtures.py is not in %s" % root)
        return
    ctx = Ctx(root)
    print("\nScript tests (kicad-cli: %s)" % ("found" if ctx.cli else "not found"))
    for name, fn in SCRIPT_TESTS:
        try:
            results.report(name, fn(ctx))
        except Skip as e:
            results.report(name, [], str(e))
        except Exception as e:  # noqa: BLE001 - a crash in a test is a failure, with where it happened
            import traceback
            where = traceback.extract_tb(e.__traceback__)[-1]
            results.report(name, ["crashed: %s: %s (%s line %d)" % (type(e).__name__, e,
                                                                   os.path.basename(where.filename), where.lineno)])


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        help="repository root to check (default: this repository)")
    parser.add_argument("--self-only", action="store_true",
                        help="only the self-check of the text and packaging, not the script tests")
    parser.add_argument("--deny-terms", default=os.environ.get("HW_SKILLS_DENY_TERMS"),
                        help="a list of terms, kept outside the repository, that no shipped file may hold")
    args = parser.parse_args()
    root = os.path.abspath(args.root)

    results = Results()
    results.report("skill frontmatter (Agent Skills spec)", check_skill_frontmatter(root))
    results.report("SKILL.md under %d lines" % MAX_SKILL_LINES, check_line_counts(root))
    results.report("references resolve", check_references(root))
    results.report("plugin manifests", check_manifests(root))
    results.report("worker wrappers", check_wrappers(root))
    results.report("no model, agent tool or tool path names in skills/", check_canonical_text(root))
    results.report("writing rules", check_writing_rules(root))
    failures, skip = check_summary_block(root)
    results.report("report summary block copies match", failures, skip)
    results.report("decision-log entry form copies match", check_decision_entry(root))
    results.report("no shipped file points into the working or test folders", check_no_pointers(root))
    results.report("no test projects inside the repository", check_no_test_projects(root))
    results.report("no machine paths or email addresses", check_personal_data(root))
    results.report("outside links only where allowed", check_urls(root))
    results.report("script version matches the plugin version", check_versions(root))
    results.report("every script command the text names exists", check_commands_exist(root))
    failures, skip = check_deny_terms(root, args.deny_terms)
    results.report("no deny-list term in a shipped file", failures, skip)
    if not args.self_only:
        run_script_tests(root, results)

    print("\n%d passed, %d failed, %d skipped" % (results.passed, results.failed, results.skipped))
    return 1 if results.failed else 0


if __name__ == "__main__":
    sys.exit(main())
