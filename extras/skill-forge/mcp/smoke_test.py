#!/usr/bin/env python3
"""smoke_test.py — wallaby_skill_forge_mcp smoke tests (public 1.0.0).

Usage: python3 smoke_test.py  (runs under a temporary HOME; the real ledger
is never touched)
Covers: initialize / tools/list / prompts/list / prompts:get / forge two-stage
/ full-flow ledger write / feedback append / optimize health checks (a clean
skill plus a six-disease fixture) / routing lanes / SOP & combo branches.
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "wallaby_skill_forge_mcp.py")

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


class Server:
    def __init__(self, home):
        env = dict(os.environ, HOME=home)
        self.proc = subprocess.Popen(
            [sys.executable, SERVER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, env=env,
        )
        self._id = 0

    def call(self, method, params=None):
        self._id += 1
        frame = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params:
            frame["params"] = params
        self.proc.stdin.write(json.dumps(frame) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("server closed stdout")
            resp = json.loads(line)
            if resp.get("id") == self._id:
                return resp

    def tool_text(self, name, args):
        resp = self.call("tools/call", {"name": name, "arguments": args})
        return resp["result"]["content"][0]["text"]

    def close(self):
        self.proc.terminate()


def main():
    tmp = tempfile.mkdtemp(prefix="skillforge-smoke-")
    srv = Server(tmp)
    try:
        print("== protocol face ==")
        r = srv.call("initialize", {"protocolVersion": "2024-11-05"})
        check("initialize", r["result"]["serverInfo"]["name"] == "wallaby-skill-forge-mcp")
        r = srv.call("tools/list")
        names = [t["name"] for t in r["result"]["tools"]]
        check("tools/list three tools", names == ["skill_forge", "skill_optimize", "skill_feedback"], str(names))
        r = srv.call("prompts/list")
        check("prompts/list two entries", len(r["result"]["prompts"]) == 2)
        r = srv.call("prompts/get", {"name": "skill_forge", "arguments": {"description": "x"}})
        check("prompts/get skill_forge", "skill_forge" in r["result"]["messages"][0]["content"]["text"])

        print("== skill_forge two stages ==")
        t = srv.tool_text("skill_forge", {"description": "make me a skill: turn weekly meeting recordings into notes"})
        check("stage one = derivation guidance", "Derive first" in t and "answers" in t and "Default to yes" in t)
        check("stage one carries version stamp", "template_version=1.0" in t)
        check("stage one three-way classification", "open and critical" in t and "Safe derivation" in t)

        print("== deterministic stakes ==")
        t = srv.tool_text("skill_forge", {"description": "make me a skill: deploy the order service to production"})
        check("high-risk forces confirmation", "high-risk surfaces" in t and "deploy/release to production" in t)
        t = srv.tool_text("skill_forge", {"description": "make me a skill: review compliance before publishing the blog"})
        check("review context exempt", "No high-risk surface hit" in t)
        t = srv.tool_text("skill_forge", {"description": "make me a skill: organize my local note files"})
        check("low-risk stays quiet", "No high-risk surface hit" in t)

        answers = {
            "skill_name": "meeting-notes",
            "task": "turn meeting recordings into fixed-format notes",
            "triggers": "\"organize the meeting notes\" \"take notes for the last meeting\"",
            "environment": "Hermes + a small model, files in ~/meetings/",
            "redlines": ["never delete the original recordings"],
            "failures": ["last time it mixed up people's names"],
            "acceptance": "notes go out without me fixing names",
            "non_triggers": "during casual chat",
            "form": "single",
        }
        t = srv.tool_text("skill_forge", {
            "description": "x", "mode": "full", "answers": answers})
        check("stage two = generation prompt", "Output spec" in t and "meeting-notes" in t)
        check("full carries feedback hook", "skill_feedback" in t)
        check("full carries optimize entry", "skill_optimize" in t)
        check("full writes ledger", "Wrote 1 initial failure record" in t)
        ledger = os.path.join(tmp, ".skill-forge", "ledger.jsonl")
        check("ledger.jsonl physically exists", os.path.exists(ledger))

        t = srv.tool_text("skill_forge", {"description": "x", "answers": answers})
        check("standalone has no feedback hook", "skill_feedback" not in t)

        print("== skill_feedback ==")
        t = srv.tool_text("skill_feedback", {
            "skill": "meeting-notes", "scene": "weekly meeting notes", "failure": "mixed up names again",
            "severity": "high"})
        check("feedback appended", "Recorded:" in t and "meeting-notes" in t)
        with open(ledger, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        check("ledger holds two entries", len(lines) == 2, str(len(lines)))

        print("== skill_optimize ==")
        t = srv.tool_text("skill_optimize", {"skill": "no-such-thing-xyz"})
        check("zero hits reported honestly", "not found" in t)

        good = "---\nname: ok\ndescription: use when the user says \"organize meeting notes\"\n---\n# Red lines\nNever delete files.\n## Pitfalls\n- Pitfall: names get mixed up. Fix: cross-check the roster.\n"
        t = srv.tool_text("skill_optimize", {"skill": "meeting-notes", "content": good})
        check("clean skill mostly green", "✅ 1" in t and "✅ 5" in t and "🔴" not in t.split("Summary")[0])
        check("ledger read back into report", "mixed up names again" in t)
        check("carries optimization prompt", "substance test" in t)

        bad = "---\nname: bad\ndescription: This skill is able to handle files\n---\nUse tool.py v1.2 to process, valid as of today. Write into production files.\n" * 120
        assert len(bad.encode("utf-8")) >= 9216, f"bad fixture size drifted: {len(bad.encode('utf-8'))}"
        t = srv.tool_text("skill_optimize", {"skill": "bad", "content": bad})
        check("bad: manual-style description flagged", "🟡 1" in t)
        check("bad: size danger zone flagged", "🔴 2" in t and "danger zone" in t)
        check("bad: hard-coded version flagged", "🟡 3" in t)
        check("bad: bare filename flagged", "🟡 4" in t)
        check("bad: missing red lines flagged", "🔴 5" in t)
        check("bad: missing pitfalls flagged", "🟡 6" in t)

        print("== three-section report + waiver + redaction ==")
        check("report has three sections", "Section 1 · Structural health" in t and "Section 2 · Behavioral confidence" in t and "Section 3 · Unknowns" in t)
        check("section two denies behavioral proof", '"production-ready"' in t)
        waived = good + "\nforge-waiver: 2 size is justified by the process itself\n"
        t = srv.tool_text("skill_optimize", {"skill": "meeting-notes", "content": waived})
        check("waiver shown explicitly", "(waived: forge-waiver 2)" in t)
        t = srv.tool_text("skill_feedback", {
            "skill": "meeting-notes", "scene": "ran in /Users/someone/secret with key=sk-abcdef0123456789aa",
            "failure": "a@b.com never got the mail", "severity": "low"})
        check("feedback redaction", "[REDACTED_KEY]" in t and "[REDACTED_EMAIL]" in t and "/Users/someone/" not in t)
        pure = "---\nname: pure\ndescription: use when the user says \"polish this paragraph\"\n---\nPure text polishing.\n"
        t = srv.tool_text("skill_optimize", {"skill": "pure", "content": pure})
        check("text-only skill exempt from red lines", "exempt (graded)" in t and "🔴 5" not in t)

        print("== type tolerance + description boundary ban + trigger window ==")
        drifted = dict(answers)
        drifted["triggers"] = ["organize meeting notes", "note the last meeting"]  # weaker models drift strings into arrays
        drifted["form"] = "weird-form"  # illegal form falls back to single
        t = srv.tool_text("skill_forge", {"description": "x", "answers": drifted})
        check("array triggers normalized into template", "organize meeting notes; note the last meeting" in t)
        check("drifted fields listed transparently", "【Type tolerance】" in t and "triggers" in t)
        check("illegal form falls back to single", "single (one file)" in t)
        check("spec carries description boundary ban", "NEVER go in the description" in t)
        longq = ("---\nname: longq\ndescription: use when the user says \"extract the key fields "
                 "(amount, tax id, date, header) from invoice images into a table and send me "
                 "a weekly summary\"\n---\n# Red lines\nNever modify source files\n## Pitfalls\nNone on record.\n")
        t = srv.tool_text("skill_optimize", {"skill": "longq", "content": longq})
        check("long quoted triggers not misflagged", "✅ 1" in t, t.splitlines()[0] if t else "")

        print("== domain packs + distinction question + birth certificate + ledger fields ==")
        longtail = [
            ("give me investment advice based on my holdings and execute the trades", "financial advice"),
            ("auto-discount and relist unsold items in my online store", "bulk store automation"),
            ("book tomorrow's train ticket and charge it to my card", "money movement"),
            ("give me medication dosage advice based on my exam report", "health advice"),
            ("upload my phone photos and share them by email", "personal data sharing"),
            ("delete useless files from my downloads folder", "personal data deletion"),
        ]
        for scene, expect_label in longtail:
            t = srv.tool_text("skill_forge", {"description": f"I want a skill: {scene}"})
            check(f"long-tail hit [{expect_label}]", expect_label in t, scene)
        t = srv.tool_text("skill_forge", {"description": "make me a skill: organize my local note files"})
        check("low-risk still quiet (no false-positive regression)", "No high-risk surface hit" in t)
        t = srv.tool_text("skill_forge", {"description": "make me a skill: audit my medication dosage records"})
        check("health scene review-context exempt (auditing is looking, not doing)", "No high-risk surface hit" in t)
        conf = dict(answers)
        conf["confusables"] = ["translating recordings into English", "wanting only the notes template without execution"]
        t = srv.tool_text("skill_forge", {"description": "x", "mode": "full", "answers": conf})
        check("confusables enter generation prompt", "Confusable neighbors" in t and "translating recordings into English" in t)
        check("birth certificate assembled", "Trigger test pairs · birth certificate" in t and "Should trigger" in t and "Should NOT trigger" in t)
        check("spec splits boundaries two ways", "Input-shape restrictions" in t and "Neighbor routing verdicts" in t)
        t = srv.tool_text("skill_feedback", {
            "skill": "meeting-notes", "scene": "weekly meeting notes", "failure": "did not fire when it should have",
            "domain": "personal", "attribution": "route"})
        check("feedback with domain/attribution persisted", '"domain": "personal"' in t and '"attribution": "route"' in t)

        print("== ritual budget + idle ledger + rhythm card + composability / step-embedded hook ==")
        t = srv.tool_text("skill_forge", {"description": "x", "answers": answers})
        check("spec carries ritual budget clause", "Ritual budget" in t and "never cut steps" in t)
        check("spec carries criteria budget", "under half the step body" in t)
        check("spec carries composability clause", "the only capability in the environment" in t)
        t = srv.tool_text("skill_forge", {"description": "x", "mode": "full", "answers": answers})
        check("feedback hook embedded as a task step", "LAST numbered step" in t and "Wrap-up: review this run" in t)
        check("full outro points at the rhythm card", "operating-rhythm card" in t)
        t = srv.tool_text("skill_optimize", {"skill": "meeting-notes", "content": good})
        check("optimize interview guidance", "ask the user one question" in t and "on-the-spot collection" in t)

        ritual_heavy = (
            "---\nname: ritual-heavy\ndescription: use when the user says \"organize files\"\n---\n"
            "## Red lines\nNever delete source files.\n## Pitfalls\nNone on record (to be backfilled from the failure ledger).\n"
            "## Feedback hook\nLog failures with skill_feedback.\n## Change log\n2026-10-13 initial version.\n"
        )
        t = srv.tool_text("skill_optimize", {"skill": "ritual-heavy", "content": ritual_heavy})
        check("ritual overflow flagged 🟡 7", "🟡 7" in t and "budget" in t)
        judge_heavy = (
            "---\nname: judge-heavy\ndescription: use when the user says \"process data\"\n---\n"
            "## Red lines\nNever modify source data.\n## Steps\n"
            "1. Read the file. Criterion: file exists.\n2. Process. Criterion: output is non-empty.\n3. Write. Criterion: write succeeds.\n"
            "4. Verify. Criterion: row counts match.\nSelf-check: all criteria pass.\nAcceptance: the user confirms correctness.\n"
        )
        t = srv.tool_text("skill_optimize", {"skill": "judge-heavy", "content": judge_heavy})
        check("criteria majority flagged 🟡 7", "criterion lines exceed half" in t)
        t = srv.tool_text("skill_optimize", {"skill": "meeting-notes", "content": good})
        check("clean skill check 7 green", "✅ 7" in t)
        check("report carries rhythm card", "Operating-rhythm card" in t and "Log failures as they happen" in t)
        # idle ledger: hand-write a 20-day-old record for another skill
        old = {"date": (datetime.date.today() - datetime.timedelta(days=20)).isoformat(),
               "skill": "stale-skill", "scene": "x", "failure": "y", "severity": "mid",
               "source": "feedback", "domain": "unmarked", "attribution": "unknown"}
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(old, ensure_ascii=False) + "\n")
        t = srv.tool_text("skill_optimize", {"skill": "stale-skill", "content": good})
        check("idle ledger flagged", "Idle-ledger warning" in t and "observational capture" in t)
        t = srv.tool_text("skill_optimize", {"skill": "meeting-notes", "content": good})
        check("recent records raise no idle warning", "Idle-ledger warning" not in t)

        print("== size smoke three tiers + red-line wording discipline + form routing ==")
        safe = good + "Additional step notes.\n" * 20  # ~0.5KB, safe zone
        t = srv.tool_text("skill_optimize", {"skill": "safe-skill", "content": safe})
        check("size safe zone green", "✅ 2" in t and "safe zone" in t)
        risky = good + ("## Steps\n" + "1. Process the input per protocol and verify each output against its criterion.\n" * 90)
        assert 6144 <= len(risky.encode("utf-8")) < 9216, f"risky fixture size drifted: {len(risky.encode('utf-8'))}"
        t = srv.tool_text("skill_optimize", {"skill": "risky-skill", "content": risky})
        check("size risk zone yellow", "🟡 2" in t and "risk zone" in t)
        t = srv.tool_text("skill_forge", {"description": "[skill] x"})
        check("guidance carries form routing", "Form routing" in t and "overcautious shutdowns" in t)
        t = srv.tool_text("skill_forge", {"description": "x", "answers": answers})
        check("spec carries red-line wording discipline", "blanket shutdown clauses" in t and "concrete and checkable" in t)
        check("birth certificate carries size smoke", "Size smoke" in t and "compress and distill" in t)
        shell_answers = dict(answers, form="shell")
        t = srv.tool_text("skill_forge", {"description": "x", "answers": shell_answers})
        check("shell form rule carries its use case", "fuzzy-boundary tasks" in t)

        print("== entry routing: three lanes + SOP/combo branches ==")
        t = srv.tool_text("skill_forge", {"description": "I want to lock down my expense reporting process, it happens every week"})
        check("fuzzy description gets the router", "requirements router" in t and "[skill]" in t and "[sop]" in t and "[combo]" in t)
        check("router never talks the user out", "never talk the user out of the thing itself" in t)
        t = srv.tool_text("skill_forge", {"description": "make me a skill: organize meeting notes"})
        check("explicit skill goes straight to the main flow", "Derive first" in t and "requirements router" not in t)
        t = srv.tool_text("skill_forge", {"description": "write me an SOP: vendor onboarding review"})
        check("explicit SOP gets SOP guidance", "SOP requirements analyst" in t and "Activation" in t)
        t = srv.tool_text("skill_forge", {"description": "[sop] vendor onboarding review", "answers": answers})
        check("SOP generation prompt six-section skeleton", "SOP generation prompt" in t and "Change log" in t and "Exceptions and escalation" in t)
        check("SOP discipline is the opposite of a skill", "for people" in t and "thorough" in t)
        t = srv.tool_text("skill_forge", {"description": "[combo] compliance review manual plus automated checks", "answers": answers})
        check("combo delivers two pieces back to back", "Generation prompt" in t and "SOP generation prompt" in t and "combo, second piece" in t)
        t = srv.tool_text("skill_forge", {"description": "[combo] compliance review", "answers": dict(answers, form="single")})
        check("combo forces the shell form", "shell (thin shell)" in t)
        # maintenance trigger: at 3 failure records for one skill, the ledger nudges optimization at write time
        for i in range(2):
            srv.tool_text("skill_feedback", {"skill": "nudge-test", "scene": f"scene {i}", "failure": f"failure {i}"})
        t = srv.tool_text("skill_feedback", {"skill": "nudge-test", "scene": "scene 3", "failure": "failed again"})
        check("three records trigger the maintenance nudge", "Maintenance nudge" in t and "optimize nudge-test" in t)
        t = srv.tool_text("skill_feedback", {"skill": "nudge-test", "scene": "scene 4", "failure": "failed yet again"})
        check("no nagging below the next threshold", "Maintenance nudge" not in t)
    finally:
        srv.close()

    print(f"\nResult: {PASS} passed / {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
