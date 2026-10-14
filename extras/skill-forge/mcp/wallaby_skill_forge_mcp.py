#!/usr/bin/env python3
"""wallaby_skill_forge_mcp.py — Skill Forge MCP server (public 1.0.0).

An analyst, not a generator. This server does only deterministic work:
requirement-derivation scaffolds, prompt assembly, machine health checks,
and failure-ledger bookkeeping. All generation and rewriting — the semantic
work — is done by the calling AI, never by this server.

Three tools (two call shapes: standalone / full flow):
  skill_forge    — create a skill (or SOP, or a combo of both). Two stages:
                   without `answers` it returns derivation guidance plus the
                   questionnaire skeleton; with `answers` it returns the
                   assembled generation prompt. mode="full" additionally
                   seeds the failure ledger, embeds a feedback hook in the
                   generated skill, and appends the operating-rhythm card.
  skill_optimize — optimize an existing skill: locate it, run seven machine
                   health checks, read its failure ledger, and assemble the
                   optimization package (diagnosis + failure history + the
                   optimization prompt). The rewrite itself belongs to the AI.
  skill_feedback — log a failure: append one entry to the failure ledger.

Failure ledger: ~/.skill-forge/ledger.jsonl (append-only, single-file).
Search paths: SKILL_FORGE_DIRS env var (os.pathsep-separated) takes
priority over the defaults (cwd, ~/.hermes/skills, ~/.claude/skills,
~/.config/hermes/skills).

Protocol: MCP over stdio, JSON-RPC 2.0, newline-delimited frames.
Zero dependencies — standard library only.
"""
import datetime
import json
import os
import re
import sys

SERVER_NAME = "wallaby-skill-forge-mcp"
SERVER_VERSION = "1.0.0"
TEMPLATE_VERSION = "1.0.0"  # protocol version; carried in every tool response to detect stale copies

LEDGER_DIR = os.path.expanduser("~/.skill-forge")
LEDGER_PATH = os.path.join(LEDGER_DIR, "ledger.jsonl")

DEFAULT_SKILL_DIRS = [
    os.getcwd(),
    os.path.expanduser("~/.hermes/skills"),
    os.path.expanduser("~/.claude/skills"),
    os.path.expanduser("~/.config/hermes/skills"),
]

# ── High-stakes detection (deterministic; no model self-assessment) ────────
# High-risk = an ACTION + OBJECT compound match, outside a review context
# (checking/reviewing is looking, not doing). Plain noun scanning misfires
# badly, so compounds only.
# Packs are pluggable; default auto = union of all packs. Bias wide on the
# safe side: a false positive costs one extra question, a false negative
# leaves a high-risk scene unconfirmed. Patterns are bilingual (EN + zh).
REVIEW_CONTEXT_RE = re.compile(r"检查|审查|过一遍|双检|合规|review|audit", re.IGNORECASE)
STAKES_PACKS = {
    "governance": [
        (re.compile(r"(部署|发布|上线|push|deploy|release|ship).{0,24}(生产|prod|线上|官网|VPS|服务器|公网|production|live)", re.IGNORECASE), "deploy/release to production"),
        (re.compile(r"(删除|删库|rm\s+-rf|drop\s+table|清空|wipe|purge)", re.IGNORECASE), "irreversible deletion"),
        (re.compile(r"(扣款|扣费|支付|付款|退款|充值|调价|改价|签发.{0,4}(key|额度)|charge|refund|payment|price\s+(change|update))", re.IGNORECASE), "money movement"),
        (re.compile(r"(密钥|token|密码|凭证|credential|secret|password).{0,8}(生成|创建|上传|提交|公开|create|upload|publish|share)", re.IGNORECASE), "credential operation"),
        (re.compile(r"(对外|公开|PR|推文|博客|官网|Reddit|邮件|public|tweet|blog|email).{0,10}(发|投|提交|publish|post|submit|send)", re.IGNORECASE), "public posting"),
        (re.compile(r"(客户|用户|customer|user).{0,6}(数据|信息|data).{0,6}(导出|外发|共享|export|share|send)", re.IGNORECASE), "customer data export"),
    ],
    "personal": [
        (re.compile(r"(买入|卖出|调仓|加仓|清仓|建仓|定投|杠杆|buy|sell|short|long).{0,10}(股|基金|币|仓|理财|etf|期货|stock|fund|crypto|position)", re.IGNORECASE), "financial trade"),
        (re.compile(r"(投资|理财|持仓|股票|基金|investment|portfolio|stock).{0,6}(建议|方案|组合|推荐|advice|recommendation)", re.IGNORECASE), "financial advice"),
        (re.compile(r"(体检|症状|病历|化验|检查报告|身体|symptom|diagnosis|medication).{0,10}(建议|诊断|吃药|用药|治疗|剂量|药|就医|advice|dosage|treatment)", re.IGNORECASE), "health advice"),
        (re.compile(r"(相册|照片|通讯录|聊天记录|身份证|护照|住址|定位|photo|contact|passport|address|location).{0,8}(发|上传|分享|外发|公开|群|upload|share|publish|post)", re.IGNORECASE), "personal data sharing"),
        (re.compile(r"(删除|清理|清空|格式化|抹掉|delete|wipe|format|erase).{0,12}(文件|照片|相册|下载|硬盘|桌面|聊天记录|file|photo|disk|desktop|chat)", re.IGNORECASE), "personal data deletion"),
        (re.compile(r"(自动|定时|每月|到期|auto|recurring|scheduled).{0,4}(扣费|续费|扣款|付款|charge|billing|renewal|payment)", re.IGNORECASE), "recurring charge"),
        (re.compile(r"(自动|批量|定时|bulk|batch|auto).{0,6}(降价|涨价|改价|上架|下架|打折|发货|repricing|listing|delisting|discount|fulfillment)", re.IGNORECASE), "bulk store automation"),
        (re.compile(r"(群发|代发|自动发|定时发|mass|bulk|scheduled).{0,6}(邮件|消息|短信|评论|帖|email|message|sms|comment|post)", re.IGNORECASE), "automated messaging"),
    ],
}


def stakes_scan(text, domain="auto"):
    """Return the list of high-risk surfaces hit (with pack suffix).
    Review context exempts the scan (the action is looking, not doing).
    domain: "auto" = union of all packs (default, biased wide); or a pack
    name / list of pack names."""
    if REVIEW_CONTEXT_RE.search(text):
        return []
    if domain == "auto":
        packs = list(STAKES_PACKS)
    elif isinstance(domain, str):
        packs = [domain]
    else:
        packs = list(domain)
    hits = []
    for pack in packs:
        for rx, label in STAKES_PACKS.get(pack, []):
            if rx.search(text):
                hits.append(f"{label} ({pack})")
    return hits


# ── Ledger redaction (applied before every write) ──────────────────────────
# Keys/tokens/emails/full IPv4/home-dir usernames. IPv4 must require all four
# octets, or it misfires on identifier fragments like "F-151".
REDACT_RULES = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "[REDACTED_KEY]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]{10,}"), "[REDACTED_TOKEN]"),
    (re.compile(r"(?i)(token|apikey|api_key|secret|password)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[REDACTED_IP]"),
    (re.compile(r"/Users/[A-Za-z0-9_\-]+/"), "~/"),
]


def redact(text):
    for rx, repl in REDACT_RULES:
        text = rx.sub(repl, str(text))
    return text


# ── Prompt templates (the protocol's thick layer) ──────────────────────────

# Entry routing (three lanes): the user says "skill" explicitly → main flow,
# no questions asked. Says "SOP" explicitly → SOP branch. Fuzzy → routing
# questionnaire (four criteria), then re-call with a [skill]/[sop]/[combo] tag.

ROUTE_TAG_RE = re.compile(r"^\s*\[(skill|sop|combo)\]\s*", re.IGNORECASE)
ROUTE_SKILL_RE = re.compile(r"skill|技能", re.IGNORECASE)
ROUTE_SOP_RE = re.compile(r"\bsop\b|手册|规范文档|制度|管理办法|standard operating procedure", re.IGNORECASE)

ROUTE_GUIDANCE = """You are a requirements router. The user wants to build something but hasn't picked a form — help them decide between a skill (an execution spec an AI follows) and an SOP (a standard operating procedure written for people).

【Four criteria】Derive each from the description:
1. Who consumes the output: an AI re-executing it repeatedly → skill; humans reading and following → SOP;
2. Volume: rules that fit in ~40 lines → a skill can hold them; dozens of items, manual-grade → SOP (skills over ~6KB burn through weaker models' reasoning budget — measured 25-50% empty responses);
3. Usage pattern: high-frequency repeated execution → skill; occasional reference → SOP;
4. Both at once (AI must execute AND content is large AND people read it) → combo: a thin-shell skill (trigger words + red lines + pointer) plus the SOP as the content body, cross-linked so the two never drift apart.

【Derive first】If you can infer the form from the description, don't ask. If you can't, ask the four questions above — all at once, never drip-feed.

【After deciding】Call this tool again with the description prefixed by a form tag:
- [skill] → skill creation flow
- [sop] → SOP creation flow
- [combo] → two deliverables (thin-shell skill + SOP body)

【Discipline】Routing only picks the form — never talk the user out of the thing itself. If the user already named the form, their word wins; this questionnaire does not trigger.
"""

SOP_GUIDANCE = """You are an SOP requirements analyst. The user wants to create an SOP (standard operating procedure — an execution document written for people). Work these rules:

【Default to yes】The user said they want an SOP, so they get an SOP. No talking them out of it, no questioning necessity.

【Derive first】Walk this skeleton and derive each item from the description:
- Purpose and scope: what does this SOP govern, and what does it explicitly not cover?
- Activation: under what circumstances is it used?
- Roles: who executes, who owns it (Owner), how often is it reviewed?
- Steps and criteria: operating steps one by one; for key steps, the completion criterion (file exists / output contains a string / a named human confirms);
- Exceptions and escalation: what to do when it breaks, what counts as an escalation condition, who to call;
- Failure history: has this process blown up before? Where? (Record only what really happened — never invent.)

【Three-way classification】Every item lands in one bucket: user-confirmed / safe derivation (harmless if wrong, mark it) / open and critical (only this bucket earns a question — ask everything at once).

When derivation/confirmation is done, call skill_forge again: description prefixed with [sop], answers parameter carrying:
{
  "skill_name": "sop-name-english-lowercase-hyphenated",
  "task": "what the SOP governs + its purpose",
  "triggers": "activation conditions (verbatim)",
  "environment": "usage scene / roles / Owner",
  "redlines": ["operations or overreach that must never happen, one per entry"],
  "failures": ["real failure points (empty if none)"],
  "acceptance": "how to judge this SOP is useful",
  "non_triggers": "situations it does not apply to",
  "form": "sop"
}
Mode this run: {{MODE}}
{{STAKES_NOTICE}}"""

SOP_GENERATION_PROMPT = """You are an SOP writer. Using the confirmed requirements below, generate an SOP document (a single Markdown file).

## Requirements (facts may not be altered)

- Name: {{SKILL_NAME}}
- Purpose and task: {{TASK}}
- Activation conditions: {{TRIGGERS}}
- Usage scene / roles: {{ENVIRONMENT}}
- Red lines (one by one): {{REDLINES}}
- Known failure points: {{FAILURES}}
- Acceptance criteria: {{ACCEPTANCE}}
- Non-applicable situations: {{NON_TRIGGERS}}

## SOP skeleton (six sections, all required)

1. Purpose and scope — what it governs, what it doesn't; one paragraph;
2. Activation conditions — when this SOP is used;
3. Roles and responsibilities — executor / Owner / review cycle;
4. Operating steps — numbered one by one; key steps carry a completion criterion (file exists / output contains a string / a named human confirms);
5. Exceptions and escalation — common failures + handling + escalation conditions (when to stop, who to call);
6. Change log — append-only table (date + what changed + why); first row = this creation.

## SOP discipline (the opposite of a skill: SOPs are for people, so be thorough)

- Background, rationale, and examples are all welcome — human readers carry no size budget (that budget is a skill constraint; don't mix the two);
- Volatile facts (versions, prices, specific dates) are still written as pointers, never hard-coded ("see the latest version of file X");
- Failure history records only what really happened, one source note per entry; if none, write "none on record" — never invent;
- Sign-off: creation date + Owner + review cycle.

## Post-generation self-check

- [ ] All six sections present?
- [ ] Every red line concrete and checkable (not a slogan)?
- [ ] Do the step criteria actually check something?
- [ ] Any volatile facts hard-coded?
- [ ] Failure history all real and sourced?"""

FORGE_GUIDANCE = """You are a skill requirements analyst. The user wants to create a skill. Work these rules:

【Default to yes】The user said they want a skill, so they get a skill. No talking them out of it, no questioning necessity.

【Derive first】Walk the questionnaire skeleton below and derive each answer from what the user already said.
Questionnaire skeleton (a derivation map, not a mandatory interview):
- A Workflow: what repeating task does this solve? How often? Is the output format fixed? (extract from frequency words — "every time", "again" — and format words)
- B Environment: which agent and model? What tools, directories, platforms does it touch? Any absolute red lines (production / payments / public posting / deleting files)?
- C Failure history: has an AI botched this kind of task before? Where?
- D Acceptance: how do we judge the skill works? When should it NOT trigger?
- E Distinction (verdict-line material): which similar tasks is this most easily confused with? What goes wrong if it fires on them?
  (Neighbor verdict lines are the only boundary form allowed in a trigger description — they must name the specific confusable scene; abstract boundaries are banned. Measured: abstract boundary lines collapse routing recall; named verdict lines prevent misfires.)

【Three-way classification】Put every derived answer in one of three buckets:
1. User-confirmed — the user said it, verbatim;
2. Safe derivation — reasonably inferred, harmless if wrong (fill it in, mark it as derived);
3. Open and critical — can't be derived AND shapes important scenes.
Only bucket 3 may block the flow and become a question. Never dress a derivation up as something the user said.

【Asking criteria】Only "open and critical" earns a question — and when you ask, ask everything at once, never drip-feed.
What counts as critical is not your guess: this tool scans the description with deterministic rules, and anything named under 【Deterministic flags】below MUST be confirmed with the user — never self-derived, never silently skipped.

【Auto-fill】Clear description + simple scene (single tool, single flow, reversible actions) = fill in everything yourself, don't interrupt the user.

【Form routing】Pick the form field from the executing model and the task's boundaries (three-regime measured conclusions):
- Target model is a cheap/fast tier (weaker) → single: structured scaffolding lifts weak models the most (measured quality 0.88 → 2.0);
- Strong model + fixed, clear-cut task → single (strong models tie with scaffolding on easy tasks; you lose nothing);
- Strong model + multi-branch, fuzzy-boundary task → shell: thick constraints push strong models into overcautious shutdowns (measured: they refuse with "conditions not fully met" and skip parts they could have done);
- Any case where the body projects over ~6KB → layered (detail sinks into references/: ≥6KB enters the reasoning burn-through zone — 25% empty responses on weak models).
Can't derive the target model → default single.

【Trigger-word discipline】Triggers grow from the user's own words. Don't summarize on their behalf. Don't invent scenes they never mentioned.

When derivation/confirmation is done, call skill_forge again with the answers parameter:
{
  "skill_name": "english-lowercase-hyphenated",
  "task": "the task, with the user's own words",
  "triggers": "trigger scenes, verbatim, 3-5 short phrases",
  "environment": "agent and model / tools and directories involved",
  "redlines": ["red lines, one per entry"],
  "failures": ["known real failures; empty if none — never invent"],
  "acceptance": "acceptance criteria",
  "non_triggers": "when it should not trigger",
  "confusables": "most-confusable similar tasks, named one by one (verdict-line material; empty if none)",
  "form": "single (one file <=40 lines) | layered (scene-tiered) | shell (thin shell); default single"
}
Mode this run: {{MODE}}
{{STAKES_NOTICE}}"""

GENERATION_PROMPT = """You are an AI-skill writer. Using the confirmed requirements below, generate a skill directory (SKILL.md, plus references/ when the form calls for it).

## Requirements (facts may not be altered)

- Skill name: {{SKILL_NAME}}
- Task: {{TASK}}
- Trigger scenes (user's own words): {{TRIGGERS}}
- Environment constraints: {{ENVIRONMENT}}
- Red lines (absolute, one by one): {{REDLINES}}
- Known failures: {{FAILURES}}
- Acceptance criteria: {{ACCEPTANCE}}
- Non-triggers: {{NON_TRIGGERS}}
- Confusable neighbors: {{CONFUSABLES}}
- Chosen form: {{FORM}}

## Output spec

1. The frontmatter `description` carries only positive trigger conditions ("use this skill when the user says or does X"), including phrasings the user would actually say. No feature brochures. Boundaries are handled two ways (two experiment rounds behind this split):
   - Input-shape restrictions ("plain text only", "only when …") NEVER go in the description — routers execute them as do-not-trigger rules, and recall collapses;
   - Neighbor routing verdicts ARE allowed and SHOULD go in, but each must name the specific confusable scene ("when the user only wants X and Y is not involved, do not trigger this skill") — no abstract boundaries.
   Also: the skill does not assume it is the only capability in the environment — the description claims only its own scene territory; never write anything that demotes, overrides, or replaces other tools or skills.
2. The body holds only what breaks the model's default behavior: project-specific facts, red lines, steps, pitfalls. Cut anything the model already knows.
3. Red lines go first in the body, one short sentence each, starting with "Never" or "Always". Two wording rules (measured on the hard-task set): ①every red line must be concrete and checkable ("never guess amount fields", not "never make mistakes"); ②NEVER write blanket shutdown clauses ("if conditions are not fully met, stop entirely") — strong models execute these as righteous shutdowns and skip work they could have done. Outside the red lines, keep working: if input is slightly off or partly missing, do the parts that can be done and report what was missing. Stop only on an explicit red line.
4. Pitfalls: only real, observed failures (one source note each). If there is no real failure history at creation time, add a single trailing note — "Pitfalls: none on record (to be backfilled from the failure ledger)" — and NO standalone section. Never invent plausible-looking pitfalls — an invented pitfall is worse than none.
5. Commands use full paths — no bare filenames. Never hard-code versions, dates, or prices — write pointers ("see the latest version of file X").
6. Key steps get checkable completion criteria (file exists / exit code / output contains a string). Not every step needs one; total criteria text stays under half the step body. One closing self-check line may end the flow.
7. Ritual budget: maintenance content (pitfall placeholders, feedback hooks, change logs) totals ≤3 lines and never gets its own section. Budget goes to task steps first — when space runs out, cut ritual and compress criteria, never cut steps.
8. Form constraint: {{FORM_RULE}}
9. {{FEEDBACK_HOOK}}

## Post-generation self-check (fix, then deliver)

- [ ] Is the description trigger conditions, not a manual?
- [ ] Zero input-shape restrictions in the description? Do all verdict lines (if any) name concrete scenes?
- [ ] Are all red lines at the top, none dropped?
- [ ] Anything written that the model already knows?
- [ ] Any hard-coded volatile facts?
- [ ] Full paths for every command?
- [ ] Any trigger scenes the user never mentioned?
- [ ] Are acceptance criteria actually checkable?
- [ ] Ritual budget held — maintenance content ≤3 lines, no standalone section? Criteria under half the step text?"""

FORM_RULES = {
    "single": "Single file — ≤40 lines (the ceiling is not a target). Don't force splits; budget goes to steps and substance.",
    "layered": "Layered — the body keeps only high-frequency rules plus a scene routing table; scene detail moves into references/ files (engage when the body projects over ~6KB, the burn-through risk line).",
    "shell": "Thin shell — the body holds only red lines, criteria, and pointer tables; step detail is not duplicated (for strong-model execution on fuzzy-boundary tasks: the thicker the constraints, the easier a strong model shuts down righteously). Guard against double-source drift.",
}

FEEDBACK_HOOK_LINE = (
    "Write failure logging as the LAST numbered step of the task flow (a formal step, numbered "
    "with the task steps — not a footnote, not its own section): \"Wrap-up: review this run for "
    "anomalies, incompletions, or failures — if any, and the environment provides a skill_feedback "
    "tool, call it with the skill name, the scene, and a one-line failure; if no such tool exists, "
    "skip. Never fabricate a call. If nothing went wrong, this step passes silently.\""
)

FULL_FLOW_OUTRO = (
    "\n\n【Full-flow add-on】When delivering, tell the user: this skill is now on file, and failures "
    "will be logged. After about a week of use, they can say \"optimize this skill\" and you will "
    "run skill_optimize for a health check plus an optimization package (the report ends with an "
    "operating-rhythm card: log failures as they happen / weekly threshold check / degrade on idle "
    "ledger / regression-test after big rewrites)."
)

OPTIMIZE_PROMPT = """First, ask the user one question: recently, has this skill misfired, felt off, or failed to trigger when it should have?
Append the answer to the failure records below as optimization input (don't assume the ledger is recording — measured across models, embedded feedback hooks fail silently, so on-the-spot collection is the fallback channel). Ask first, then start:

Go through the skill section by section, sentence by sentence, with a substance test: if this sentence were deleted, would behavior change? Four verdicts:
- Cut: deleting it changes nothing — narrative, family history, dead data snapshots.
- Sink: low-frequency scene detail moves into references/; the body keeps a one-line routing pointer (the trigger condition, in one line).
- Demote: don't cut or sink — switch to read-on-demand. Allowed only if you can name which scene needs it AND that scene has another fallback; can't name both → not allowed.
- Keep: red lines, high-frequency rules, and the trigger protocol always stay in the body. Before deleting any red line, rewrite it into a shorter red line that stays.

After editing, append one line to the change-log area at the end of the skill: date + what changed + why.
The failure records below are the priority input for this optimization (check each one off: confirm the rewrite catches it):
{{FAILURE_ENTRIES}}

Full skill text:
{{SKILL_CONTENT}}"""

# ── Tool schemas ────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "skill_forge",
        "description": (
            "Use when the user wants to turn a repeating workflow into a skill, or wants to "
            "codify a process but is unsure whether it should be a skill or an SOP. This is a "
            "creation analyst: if the user named the form, it goes straight to work (defaults "
            "to yes, never talks them out of it); if the form is unclear, it offers routing "
            "criteria (skill = spec an AI executes / SOP = document people read / combo = "
            "thin-shell skill + SOP body), then derives requirements from the questionnaire "
            "skeleton (asking only what can't be derived and matters), and finally returns an "
            "assembled generation prompt that you (the AI) execute. mode='full' runs the full "
            "flow: it additionally seeds the failure ledger and embeds a feedback hook in the "
            "generated skill."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "The user's raw description of the skill they want."},
                "mode": {
                    "type": "string",
                    "enum": ["standalone", "full"],
                    "description": "standalone = creation only (default); full = full flow (creation + failure ledger + feedback hook + optimization loop).",
                },
                "answers": {
                    "type": "object",
                    "description": "Structured answers after derivation/interview (skill_name/task/triggers/environment/redlines/failures/acceptance/non_triggers/form). Providing this enters the prompt-assembly stage.",
                },
            },
            "required": ["description"],
        },
    },
    {
        "name": "skill_optimize",
        "description": (
            "Use when the user wants to optimize or health-check an existing skill. Locates the "
            "skill by name or path, runs seven machine health checks, reads its failure ledger, "
            "and returns a diagnostic report plus an optimization prompt. The actual rewrite is "
            "yours (the AI's) — this tool never edits files."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "Skill name or path to its SKILL.md."},
                "content": {"type": "string", "description": "Optional: paste the full SKILL.md text (skips the search)."},
            },
            "required": ["skill"],
        },
    },
    {
        "name": "skill_feedback",
        "description": (
            "Use when a skill misfires, fails, or produces output below expectations — append "
            "the failure scene to the failure ledger (~/.skill-forge/ledger.jsonl) as input "
            "for a future skill_optimize pass."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "The skill that failed."},
                "scene": {"type": "string", "description": "What you were trying to do (one line)."},
                "failure": {"type": "string", "description": "How it failed (one line)."},
                "severity": {
                    "type": "string",
                    "enum": ["low", "mid", "high"],
                    "description": "Severity (default mid).",
                },
                "domain": {
                    "type": "string",
                    "description": "Optional: scene domain (e.g. governance/personal/investing/retail…), for measuring the experience-base distribution.",
                },
                "attribution": {
                    "type": "string",
                    "enum": ["route", "content", "boundary", "unknown"],
                    "description": "Optional attribution: route = fired wrong / didn't fire → fix the description; content = fired but done badly → fix the body; boundary = verdict-line problem; unknown = unsure (default).",
                },
            },
            "required": ["skill", "scene", "failure"],
        },
    },
]

PROMPTS = [
    {
        "name": "skill_forge",
        "description": "Create a new skill (analyst-guided: derive requirements → generation prompt)",
        "arguments": [
            {"name": "description", "description": "One-line description of the skill you want", "required": True},
            {"name": "mode", "description": "standalone or full (full flow)", "required": False},
        ],
    },
    {
        "name": "skill_optimize",
        "description": "Optimize / health-check an existing skill (diagnosis + failure ledger + optimization prompt)",
        "arguments": [
            {"name": "skill", "description": "Skill name or path", "required": True},
        ],
    },
]

# ── Failure ledger ──────────────────────────────────────────────────────────


def _today():
    return datetime.date.today().isoformat()


def ledger_append(skill, scene, failure, severity="mid", source="feedback",
                  domain="unmarked", attribution="unknown"):
    # domain/attribution turn the experience base from "imagined" into "measured";
    # attribution picks the repair path (route → description / content → body /
    # boundary → verdict lines).
    os.makedirs(LEDGER_DIR, exist_ok=True)
    entry = {
        "date": _today(),
        "skill": redact(skill),
        "scene": redact(scene),
        "failure": redact(failure),
        "severity": severity,
        "source": source,
        "domain": redact(domain),
        "attribution": attribution,
    }
    with open(LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def ledger_read(skill=None):
    if not os.path.exists(LEDGER_PATH):
        return []
    entries = []
    with open(LEDGER_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if skill is None or e.get("skill") == skill:
                entries.append(e)
    return entries

# ── skill_forge ─────────────────────────────────────────────────────────────

_STR_FIELDS = ("skill_name", "task", "triggers", "environment", "acceptance",
               "non_triggers", "confusables", "form")
_LIST_FIELDS = ("redlines", "failures")


def _normalize_answers(answers):
    """Type-tolerant answers: weaker models often emit string fields as JSON
    arrays, and template assembly only accepts strings. Normalize on the
    deterministic side instead of betting on schema compliance. Returns
    (normalized copy, list of drifted fields)."""
    out = dict(answers)
    drifted = []

    def to_str(v):
        if isinstance(v, str):
            return v
        if isinstance(v, list):
            return "; ".join(str(x) for x in v)
        if v is None:
            return ""
        return json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else str(v)

    def to_list(v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, list):
            return [str(x) for x in v]
        return [str(v)]

    for k in _STR_FIELDS:
        if out.get(k) is not None and not isinstance(out.get(k), str):
            drifted.append(k)
        out[k] = to_str(out.get(k))
    for k in _LIST_FIELDS:
        if out.get(k) is not None and not isinstance(out.get(k), list):
            drifted.append(k)
        out[k] = to_list(out.get(k))
    if out.get("form") not in FORM_RULES:
        out["form"] = "single"
    return out, drifted


def _birth_tests(answers):
    """Generate-and-verify: assemble trigger test pairs deterministically from
    the answers, zero model involvement. fire side ← verbatim triggers;
    no-fire side ← confusables + non_triggers. Up to 4 pairs.
    The pairs are the skill's behavioral baseline: born with it, consulted on
    every failure for attribution (routing error vs content error)."""
    def split_items(text):
        items = [t.strip(" 「」\"'，,") for t in re.split(r"[；;\n]", text or "")]
        return [t for t in items if t and not t.startswith("（")]

    fires = split_items(answers.get("triggers"))
    nofires = split_items(answers.get("confusables")) + split_items(answers.get("non_triggers"))
    if not fires:
        return ""
    lines = ["【Trigger test pairs · birth certificate】Once the skill is installed, check its "
             "trigger behavior with these sentences (keep them as a regression baseline; on "
             "failure, attribute first: wrong pick / no pick = routing error → fix the "
             "description; picked but done badly = content error → fix the body):"]
    for idx, fire in enumerate(fires[:4], 1):
        line = f"{idx}. Should trigger: \"{fire}\""
        if idx - 1 < len(nofires):
            line += f"  | Should NOT trigger: \"{nofires[idx - 1]}\""
        lines.append(line)
    return "\n".join(lines)


def _route(description):
    """Entry routing. Returns (route, description with the tag stripped).
    Priority: explicit [tag] > said SOP > said skill > fuzzy (None = show the
    routing questionnaire). Saying \"skill\" goes straight to the main flow —
    the default-to-yes discipline holds. Saying both → the tag wins."""
    m = ROUTE_TAG_RE.match(description)
    if m:
        return m.group(1).lower(), ROUTE_TAG_RE.sub("", description, count=1).strip()
    has_sop = bool(ROUTE_SOP_RE.search(description))
    has_skill = bool(ROUTE_SKILL_RE.search(description))
    if has_sop and not has_skill:
        return "sop", description
    if has_skill:
        return "skill", description
    return None, description


def tool_forge(args):
    description = (args.get("description") or "").strip()
    if not description:
        raise ValueError("empty description")
    mode = args.get("mode") or "standalone"
    answers = args.get("answers")
    route, description = _route(description)
    if not description:
        raise ValueError("empty description after route tag")

    mode_label = "full flow (full)" if mode == "full" else "standalone"
    hits = stakes_scan(description)
    if hits:
        notice = (
            f"\n【Deterministic flags】The description hits high-risk surfaces: {', '.join(hits)}. "
            "Red lines and environment items on these surfaces are \"open and critical\" — "
            "if you can't derive them, you MUST confirm with the user. Never self-derive, "
            "never silently skip."
        )
    else:
        notice = "\n【Deterministic flags】No high-risk surface hit (or review context) — proceed with the regular three-way classification."

    if not answers:
        if route is None:
            return ROUTE_GUIDANCE + _version_tail()
        if route == "sop":
            return SOP_GUIDANCE.replace("{{MODE}}", mode_label).replace("{{STAKES_NOTICE}}", notice) + _version_tail()
        if route == "combo":
            # combo stage one = skill guidance + enforced shell form + SOP guidance, back to back
            combo_note = ("\n\n【Combo two-piece form】This need is judged a two-piece delivery: a "
                          "thin-shell skill (trigger words + red lines + a pointer to the SOP) plus "
                          "the SOP document (the content body). The answers form field is fixed to "
                          "shell; while deriving, also plan what the SOP body will hold.")
            return (FORGE_GUIDANCE.replace("{{MODE}}", mode_label)
                    .replace("{{STAKES_NOTICE}}", notice) + combo_note + _version_tail())
        return FORGE_GUIDANCE.replace("{{MODE}}", mode_label).replace("{{STAKES_NOTICE}}", notice) + _version_tail()

    # Stage two: assemble the generation prompt (normalize types first — weaker
    # models drift answer fields)
    answers, drifted = _normalize_answers(answers)
    if route == "combo":
        answers["form"] = "shell"  # combo forces shell: content lives in the SOP; the skill is trigger + red lines + pointer
    skill_name = (answers.get("skill_name") or "new-skill").strip()
    form = answers.get("form") or "single"
    form_label = {"single": "single (one file)", "layered": "layered (scene-tiered)", "shell": "shell (thin shell)"}.get(form, form)

    def _list(key, empty="(none)"):
        v = answers.get(key) or []
        if isinstance(v, str):
            v = [v]
        return "\n".join(f"  - {x}" for x in v) if v else empty

    slot_vals = {
        "{{SKILL_NAME}}": skill_name,
        "{{TASK}}": answers.get("task") or description,
        "{{TRIGGERS}}": answers.get("triggers") or "(extract from the task description)",
        "{{ENVIRONMENT}}": answers.get("environment") or "(unspecified — treat as a generic environment)",
        "{{REDLINES}}": _list("redlines"),
        "{{FAILURES}}": _list("failures"),
        "{{ACCEPTANCE}}": answers.get("acceptance") or "(unspecified — confirm one with the user after generation)",
        "{{NON_TRIGGERS}}": answers.get("non_triggers") or "(unspecified)",
    }

    # SOP branch: swap templates (skeleton and discipline are the opposite of a
    # skill — written for people, thoroughness wins)
    if route == "sop":
        prompt = SOP_GENERATION_PROMPT
        for slot, val in slot_vals.items():
            prompt = prompt.replace(slot, val)
        out = ("【SOP generation prompt】Execute the following block as your instruction and generate:\n\n" + prompt)
        if drifted:
            out += (f"\n\n【Type tolerance】answers fields auto-normalized: {', '.join(drifted)} "
                    "(array/non-standard type → the type the template needs; next time emit the field types from the questionnaire skeleton)")
        return out + _version_tail()

    hook = FEEDBACK_HOOK_LINE if mode == "full" else "(not applicable in standalone mode)"
    prompt = GENERATION_PROMPT
    for slot, val in {**slot_vals,
                      "{{CONFUSABLES}}": answers.get("confusables") or "(unspecified)",
                      "{{FORM}}": form_label,
                      "{{FORM_RULE}}": FORM_RULES.get(form, FORM_RULES["single"]),
                      "{{FEEDBACK_HOOK}}": hook}.items():
        prompt = prompt.replace(slot, val)

    out = "【Generation prompt】Execute the following block as your instruction and generate:\n\n" + prompt
    if route == "combo":
        sop_prompt = SOP_GENERATION_PROMPT
        for slot, val in slot_vals.items():
            sop_prompt = sop_prompt.replace(slot, val)
        out += ("\n\n━━ combo, second piece ━━\n\n【SOP generation prompt】The content body of the "
                "same need — execute the following block as your instruction and generate the SOP document:\n\n" + sop_prompt)
    if mode == "full":
        written = []
        for f in answers.get("failures") or []:
            ledger_append(skill_name, "pre-creation interview capture", str(f), source="interview")
            written.append(str(f))
        out += FULL_FLOW_OUTRO
        out += f"\n\n【Ledger】Wrote {len(written)} initial failure record(s) → {LEDGER_PATH}"
    tests = _birth_tests(answers)
    if tests:
        out += "\n\n" + tests
    # Size smoke (burn-through law): shipped with the birth certificate — the
    # first thing to do after installing the skill is measure its size
    out += ("\n\n【Size smoke】After installing the skill, run skill_optimize on it and read check "
            "#2: <6KB = safe zone (measured zero burn-throughs on weak models); ≥6KB = risk zone "
            "(25% empty responses); ≥9KB = danger zone (50% empty responses). Over the line → "
            "compress and distill first, then put it to work.")
    if drifted:
        out += (f"\n\n【Type tolerance】answers fields auto-normalized: {', '.join(drifted)} "
                "(array/non-standard type → the type the template needs; next time emit the field types from the questionnaire skeleton)")
    return out + _version_tail()

# ── skill_optimize ──────────────────────────────────────────────────────────

VERSION_RE = re.compile(r"v\d+\.\d+")
SNAPSHOT_RE = re.compile(r"截至|保底价|\$\d|as of\b", re.IGNORECASE)
BARE_FILE_RE = re.compile(r"`?\b([\w\-]+\.(?:py|sh|js|ts|md))\b`?")
BARE_FILE_EXEMPT = {"SKILL.md", "README.md"}
REDLINE_RE = re.compile(r"红线|绝不|必须|must not|never ", re.IGNORECASE)
PITFALL_RE = re.compile(r"踩坑|坑|pitfall|gotcha|暂无可考|none on record", re.IGNORECASE)
# Trigger-phrase window 60: trigger words often come as long quoted lists, and
# a 20-char window misfires (measured 8/10 false positives while behavior
# tests scored full marks — structural health ≠ behavioral confidence). This
# check is a heuristic hint only; behavior tests are the arbiter.
TRIGGER_RE = re.compile(r"当.{0,60}时|用于.{0,60}场景|使用本技能|use when|when the user", re.IGNORECASE)
# Ritual budget: maintenance lines (pitfall placeholder / feedback hook /
# change log / birth certificate) >3, or criterion lines >50% of the body,
# earns a 🟡 nudge to compress. Red lines don't count as ritual (they are
# keep-forever by definition); criteria are required by spec 6 but budgeted.
RITUAL_LINE_RE = re.compile(r"踩坑|暂无可考|回灌|skill_feedback|变更记录|出生证明|触发测试对|pitfall|none on record|feedback hook|change log|birth certificate|trigger test pair", re.IGNORECASE)
JUDGE_LINE_RE = re.compile(r"判据|验收标准|完成判据|自检|criterion|criteria|acceptance|self-check", re.IGNORECASE)
DESC_RE = re.compile(r"^description:\s*(.+)$", re.MULTILINE)
WAIVER_RE = re.compile(r"forge-waiver:\s*(\d+)", re.IGNORECASE)
# Red-line grading: only skills touching shell/network/files/money ACTIONS are
# forced to carry a red-line section; purely conversational skills are exempt
RISK_ACTION_RE = re.compile(
    r"(部署|发布|上线|删除|执行命令|写入|SSH|ssh|curl|扣款|支付|充值|对外|公网|生产|deploy|release|delete|payment|charge|production|public)",
    re.IGNORECASE,
)


def _find_skill(name):
    """Find SKILL.md by name across the usual locations; return matching paths."""
    extra = os.environ.get("SKILL_FORGE_DIRS", "")
    dirs = [d for d in extra.split(os.pathsep) if d] + DEFAULT_SKILL_DIRS
    hits = []
    for base in dirs:
        if not os.path.isdir(base):
            continue
        direct = os.path.join(base, name, "SKILL.md")
        if os.path.exists(direct):
            hits.append(direct)
            continue
        for root, subdirs, files in os.walk(base):
            depth = root[len(base):].count(os.sep)
            if depth >= 2:
                subdirs[:] = []
                continue
            if os.path.basename(root) == name and "SKILL.md" in files:
                hits.append(os.path.join(root, "SKILL.md"))
    return hits


def _health_check(content):
    """Seven machine checks (heuristics, not behavioral evidence).
    Returns (row list, waived-check set).

    Waiver: a line `forge-waiver: <n> <reason>` inside the skill exempts check
    <n> — it keeps heuristic noise from compounding into alert fatigue.
    Waived rows are listed visibly, never swallowed silently.
    """
    waived = set(WAIVER_RE.findall(content))
    rows = []
    lines = content.splitlines()
    nbytes = len(content.encode("utf-8"))

    def emit(idx, level, text):
        if str(idx) in waived:
            rows.append(f"✅ {idx} {text} (waived: forge-waiver {idx})")
        else:
            rows.append(f"{level} {idx} {text}")

    m = DESC_RE.search(content)
    if not m:
        emit(1, "🔴", "description missing — frontmatter has no description field")
    elif TRIGGER_RE.search(m.group(1)):
        emit(1, "✅", "description carries trigger phrasing")
    else:
        emit(1, "🟡", "description reads like a manual (no \"use when\"/\"当…时\" trigger phrasing; heuristic hint — behavior tests are the arbiter)")

    # Size smoke, three tiers (measured burn-through law): burn-through = the
    # reasoning budget maxes out and the model returns empty. <6KB safe zone
    # (0/8 measured); ≥6KB risk zone (25% empty on weak models); ≥9KB danger
    # zone (50% on naturally bloated files — twice as toxic as same-size
    # padded files).
    if nbytes >= 9216:
        emit(2, "🔴", f"size {nbytes} bytes, danger zone (≥9KB; ~50% measured burn-through on weak models) "
             "— compress and distill before it goes to work; messiness (repetition, tangled structure) is more toxic than raw size")
    elif nbytes >= 6144:
        emit(2, "🟡", f"size {nbytes} bytes, risk zone (6-9KB; ~25% measured empty responses on weak models) "
             "— compress below 6KB if you can; if not, run a burn-through smoke on the target model")
    else:
        emit(2, "✅", f"size {nbytes} bytes ({len(lines)} lines), safe zone (<6KB, zero measured burn-throughs)")

    hits = VERSION_RE.findall(content) + SNAPSHOT_RE.findall(content)
    if hits:
        emit(3, "🟡", f"{len(hits)} suspected hard-coded volatile fact(s) ({', '.join(hits[:5])}) — rewrite as pointers")
    else:
        emit(3, "✅", "no hard-coded versions or snapshots found")

    bare = [b for b in BARE_FILE_RE.findall(content) if "/" not in b and b not in BARE_FILE_EXEMPT]
    if bare:
        emit(4, "🟡", f"{len(bare)} suspected bare filename(s) ({', '.join(bare[:5])}) — commands need full paths")
    else:
        emit(4, "✅", "no bare filenames found")

    if REDLINE_RE.search(content):
        emit(5, "✅", "red-line section present")
    elif RISK_ACTION_RE.search(content):
        emit(5, "🔴", "no red-line section, and the content touches shell/network/files/money actions — high loss-of-control risk; add red lines")
    else:
        emit(5, "✅", "no red-line section; no high-risk actions detected — conversational/text skills are exempt (graded)")

    if PITFALL_RE.search(content):
        emit(6, "✅", "pitfalls section present (including the \"none on record\" placeholder)")
    else:
        emit(6, "🟡", "pitfalls section missing — a new skill may use a \"none on record\" placeholder; real failure history must be listed")

    body_lines = [l for l in lines if l.strip() and not l.strip().startswith("---")]
    ritual = [l for l in body_lines if RITUAL_LINE_RE.search(l)]
    judges = [l for l in body_lines if JUDGE_LINE_RE.search(l) and not RITUAL_LINE_RE.search(l)]
    if len(ritual) > 3:
        emit(7, "🟡", f"maintenance content runs {len(ritual)} lines (budget ≤3) — compress pitfall placeholders / feedback hooks / change logs into a single trailing note, no standalone sections")
    elif body_lines and len(judges) > 3 and len(judges) / len(body_lines) > 0.5:
        emit(7, "🟡", f"criterion lines exceed half the body ({len(judges)}/{len(body_lines)} lines) — criteria only for key steps, totaling under half the step text")
    else:
        emit(7, "✅", f"ritual budget held (maintenance {len(ritual)} lines / criteria {len(judges)} lines)")

    return rows, waived


def _ledger_idle_warn(fails):
    """Idle-ledger test: history exists but nothing new in 14 days — either
    nothing really failed, or the feedback hook isn't running (agent
    self-logging is unverified). Attach a warning plus the observational-
    capture downgrade path."""
    dates = [e.get("date", "") for e in fails if e.get("date")]
    if not dates:
        return None
    latest = max(dates)
    try:
        days = (datetime.date.today() - datetime.date.fromisoformat(latest)).days
    except ValueError:
        return None
    if days < 14:
        return None
    return (
        f"🟡 Idle-ledger warning: the most recent failure record is {days} days old ({latest}). "
        "Two possibilities: nothing really failed, or the feedback hook isn't running (the agent "
        "isn't logging). Action: downgrade to observational capture — after each use of the skill, "
        "ask \"did anything just fail?\" and record by hand. If the ledger stays idle for a full "
        "month, re-check whether the trigger conditions and the feedback hook are still in the "
        "skill body."
    )


def tool_optimize(args):
    skill = (args.get("skill") or "").strip()
    if not skill:
        raise ValueError("empty skill")
    content = args.get("content")
    located = None

    if not content:
        if os.path.exists(skill):
            located = skill
        else:
            hits = _find_skill(skill)
            if not hits:
                return (
                    f"Skill \"{skill}\" not found. Locations searched: {', '.join(DEFAULT_SKILL_DIRS)}.\n"
                    "Provide the full path to SKILL.md, or paste the file content into the content parameter."
                ) + _version_tail()
            if len(hits) > 1:
                return "Multiple candidates found — pick one:\n" + "\n".join(hits) + _version_tail()
            located = hits[0]
        with open(located, "r", encoding="utf-8") as f:
            content = f.read()

    skill_key = os.path.basename(os.path.dirname(located)) if located else skill
    rows, waived = _health_check(content)
    fails = ledger_read(skill_key) or ledger_read(skill)

    report = [f"【Health report】{skill_key}" + (f" ({located})" if located else " (content pasted directly)")]

    # ── Section 1: structural health (heuristics, not behavioral evidence) ──
    report.append("\n━━ Section 1 · Structural health (heuristic checks — prove it \"looks right\", not that it \"works\") ━━")
    report += rows
    red = sum(1 for r in rows if r.startswith("🔴"))
    yellow = sum(1 for r in rows if r.startswith("🟡"))
    report.append(
        f"Summary: 🔴{red} 🟡{yellow}; the machine only labels — verdicts belong to humans. "
        "For a confirmed false positive, add a line `forge-waiver: <n> <reason>` inside the skill to exempt that check."
    )

    # ── Section 2: behavioral confidence (this report carries no behavioral
    # evidence — it only points to where the evidence lives) ──
    report.append("\n━━ Section 2 · Behavioral confidence (all-green structure ≠ works) ━━")
    report.append(f"Failure ledger: {len(fails)} record(s) for {skill_key}")
    for e in fails[-10:]:
        report.append(f"  - [{e.get('date')}] ({e.get('source')}/{e.get('severity')}) {e.get('scene')}: {e.get('failure')}")
    idle = _ledger_idle_warn(fails)
    if idle:
        report.append(idle)
    report.append(
        "Trigger accuracy cannot be measured by this tool — it needs an external trigger test set "
        "(15-20 should-fire / should-not-fire prompt pairs, run against the target model and "
        "counted). Without behavioral evidence, no conclusion in this report may be stated as "
        "\"production-ready\"."
    )

    # ── Section 3: unknowns (the machine can't judge — ask yourself) ──
    report.append("\n━━ Section 3 · Unknowns (ask yourself) ━━")
    report.append(
        "Do the trigger words still match real usage? Recently, has it failed to fire when it "
        "should, or fired when it shouldn't? No ledger records ≠ no failures — agent self-report "
        f"is best-effort; failures can also be logged by hand into {LEDGER_PATH} "
        "(one JSON line: date/skill/scene/failure/severity/source/domain/attribution=manual)."
    )

    # ── Operating-rhythm card (a skill is a living thing — deliver the rhythm,
    # not just the artifact) ──
    report.append("\n━━ Operating-rhythm card (treat the skill as a living thing) ━━")
    report.append(
        "1. Log failures as they happen: call skill_feedback on the spot, or hand-write one ledger line — don't save them up.\n"
        "2. Weekly check: scan the ledger weekly — the same failure kind hitting ≥3 times means run skill_optimize for an optimization package.\n"
        "3. Idle ledger: near-zero new entries for two weeks → downgrade to observational capture (ask \"did anything fail?\" after each use); idle for a full month → re-check trigger conditions.\n"
        "4. Regression: after every big rewrite, re-run the birth certificate's trigger test pairs and confirm routing hasn't regressed."
    )

    opt = OPTIMIZE_PROMPT.replace(
        "{{FAILURE_ENTRIES}}",
        "\n".join(f"- [{e.get('date')}] {e.get('scene')}: {e.get('failure')}" for e in fails) or "(no ledger records)",
    ).replace("{{SKILL_CONTENT}}", content)

    report.append("\n【Optimization prompt】When the report shows 🟡/🔴 or the ledger holds failure records, execute the following block as your instruction and rewrite:\n\n" + opt)
    return "\n".join(report) + _version_tail()


def tool_feedback(args):
    skill = (args.get("skill") or "").strip()
    scene = (args.get("scene") or "").strip()
    failure = (args.get("failure") or "").strip()
    if not (skill and scene and failure):
        raise ValueError("skill/scene/failure must all be non-empty")
    severity = args.get("severity") or "mid"
    domain = (args.get("domain") or "unmarked").strip()
    attribution = (args.get("attribution") or "unknown").strip()
    if attribution not in ("route", "content", "boundary", "unknown"):
        attribution = "unknown"
    entry = ledger_append(skill, scene, failure, severity, source="feedback",
                          domain=domain, attribution=attribution)
    # Maintenance trigger: when one skill's failures pile up to the threshold,
    # nudge optimization at write time — no longer relying on the user
    # remembering to say "optimize this". Once every 3 records, to avoid
    # nagging on every failure (alert fatigue).
    n_skill = len([e for e in ledger_read() if e.get("skill") == redact(skill)])
    nudge = ""
    if n_skill >= 3 and n_skill % 3 == 0:
        nudge = (f"\n\n【Maintenance nudge】\"{skill}\" now has {n_skill} failure records — the "
                 f"weekly-check threshold. Consider saying \"optimize {skill}\" now; these ledger "
                 "records become the main optimization input. If the same failure kind repeats, "
                 "root-cause that kind first.")
    return (
        f"Recorded: {json.dumps(entry, ensure_ascii=False)}\n"
        f"Ledger: {LEDGER_PATH} ({len(ledger_read())} total). "
        "After a few accumulate, say \"optimize this skill\" to run skill_optimize for an optimization package."
        + nudge
    ) + _version_tail()


def _version_tail():
    return f"\n\n(template_version={TEMPLATE_VERSION}, server={SERVER_NAME} {SERVER_VERSION})"

# ── Protocol layer (MCP over stdio, JSON-RPC 2.0) ───────────────────────────

def log_err(msg):
    print(f"[skill_forge_mcp] {msg}", file=sys.stderr, flush=True)


def result_ok(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def result_err(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def tool_text(text):
    return {"content": [{"type": "text", "text": text}]}


HANDLERS = {
    "skill_forge": tool_forge,
    "skill_optimize": tool_optimize,
    "skill_feedback": tool_feedback,
}


def handle_call(params):
    name = params.get("name")
    args = params.get("arguments") or {}
    handler = HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"unknown tool: {name}")
    return tool_text(handler(args))


def handle_prompt_get(params):
    name = params.get("name")
    pargs = params.get("arguments") or {}
    if name == "skill_forge":
        desc = pargs.get("description") or "(no description given — ask the user what kind of skill they want first)"
        mode = pargs.get("mode") or "standalone"
        text = (
            f"Call the skill_forge tool with description={desc!r}, mode={mode!r}. "
            "Follow the analyst guidance it returns exactly: derive first, ask only what the "
            "asking criteria name, and call again with answers when done."
        )
    elif name == "skill_optimize":
        skill = pargs.get("skill") or "(ask the user which skill to optimize first)"
        text = (
            f"Call the skill_optimize tool with skill={skill!r}. "
            "Once you have the diagnostic report and the optimization prompt, the rewrite is "
            "yours — but show the user a summary of the report before rewriting."
        )
    else:
        raise ValueError(f"unknown prompt: {name}")
    return {
        "messages": [
            {"role": "user", "content": {"type": "text", "text": text}}
        ]
    }


def handle(frame):
    method = frame.get("method")
    req_id = frame.get("id")
    if method == "initialize":
        return result_ok(req_id, {
            "protocolVersion": frame.get("params", {}).get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return result_ok(req_id, {})
    if method == "tools/list":
        return result_ok(req_id, {"tools": TOOLS})
    if method == "tools/call":
        try:
            return result_ok(req_id, handle_call(frame.get("params") or {}))
        except Exception as e:
            return result_ok(req_id, {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True})
    if method == "prompts/list":
        return result_ok(req_id, {"prompts": PROMPTS})
    if method == "prompts/get":
        try:
            return result_ok(req_id, handle_prompt_get(frame.get("params") or {}))
        except Exception as e:
            return result_err(req_id, -32602, str(e))
    if req_id is not None:
        return result_err(req_id, -32601, f"method not found: {method}")
    return None


def main():
    log_err(f"{SERVER_NAME} {SERVER_VERSION} up (template {TEMPLATE_VERSION})")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            frame = json.loads(line)
        except json.JSONDecodeError:
            log_err(f"bad frame: {line[:120]}")
            continue
        log_err(f"<- {frame.get('method')}")
        resp = handle(frame)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
