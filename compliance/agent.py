"""
agent.py
--------
The compliance agent. DESIGN: a deterministic engine decides the verdict (every
finding traces to a rule + its cited quote); the LLM only writes the plain-English
summary and is never allowed to change the call.

Public entry point:
    check_compliance(spec: FenceSpec) -> ComplianceReport

Heavy deps (db, openai, jurisdiction) are imported lazily inside the functions
that need them, so the pure decision engine can be imported and unit-tested alone.
"""

import operator
import re

from compliance.schemas import FenceSpec, Finding, ComplianceReport

# ---- deterministic decision engine (pure; no DB / no LLM) -------------------
_OPS = {"<=": operator.le, ">=": operator.ge, "<": operator.lt,
        ">": operator.gt, "==": operator.eq, "=": operator.eq, "!=": operator.ne}

_MATERIAL_ALIASES = {
    "chain-link": "chain link", "chainlink": "chain link", "chain link": "chain link",
    "pvc": "vinyl", "brick": "masonry", "wrought iron": "iron", "aluminium": "aluminum",
}


def normalize_material(m: str) -> str:
    m = (m or "").strip().lower()
    return _MATERIAL_ALIASES.get(m, m)


def rule_applies(rule: dict, spec: FenceSpec) -> bool:
    """Does this rule govern this fence? (applicability, separate from the constraint)"""
    fields = rule.get("schema_fields", [])
    if "corner_lot" in fields and not spec.corner_lot:
        return False
    loc = rule.get("location", "any")
    if loc == "any":
        return True
    if loc == "street_side":
        return spec.corner_lot
    return loc == spec.location


def _spec_value(field: str, spec: FenceSpec):
    return {
        "height_ft": spec.height_ft,
        "pct_open": spec.pct_open,
        "material": normalize_material(spec.material),
        "near_pool": spec.near_pool,
        "corner_lot": spec.corner_lot,
    }.get(field)


def _cmp(spec_val, op: str, raw: str):
    fn = _OPS.get(op)
    if fn is None:
        return None
    if isinstance(spec_val, bool):
        return fn(spec_val, str(raw).strip().lower() in ("true", "1", "yes"))
    if isinstance(spec_val, (int, float)):
        nums = re.findall(r"-?\d+\.?\d*", str(raw))
        if not nums:
            return None
        return fn(float(spec_val), float(nums[0]))
    return fn(str(spec_val).strip().lower(), normalize_material(raw))


def evaluate_constraint(rule: dict, spec: FenceSpec):
    """Evaluate the rule's pass-condition against the fence.
    Returns (satisfied: bool|None, result_token). 'location' atoms are skipped
    here because applicability is handled by rule_applies()."""
    logic = rule.get("verdict_logic", "") or ""
    m = re.search(r"WHEN\s*(.*?)\s*THEN\s*(\w+)", logic, re.I)
    if not m:
        return None, "pass"                       # unparseable -> needs_review
    cond, result = m.group(1).strip().strip("()"), m.group(2).lower()
    if re.search(r"\bOR\b", cond, re.I):
        return None, result                       # don't guess on OR logic
    truths = []
    for atom in re.split(r"\s+AND\s+", cond, flags=re.I):
        am = re.match(r"\s*(\w+)\s*(<=|>=|!=|==|=|<|>)\s*'?([^']+?)'?\s*$", atom)
        if not am:
            continue
        field, op, val = am.group(1), am.group(2), am.group(3)
        if field == "location":
            continue
        sv = _spec_value(field, spec)
        if sv is None:
            continue
        r = _cmp(sv, op, val)
        if r is not None:
            truths.append(r)
    if not truths:
        return None, result
    return all(truths), result


def _status_for(satisfied, result: str) -> str:
    if satisfied is None:
        return "needs_review"
    if result == "pass":
        return "pass" if satisfied else "fail"
    if result == "fail":
        return "fail" if satisfied else "pass"
    return "needs_review" if satisfied else "pass"


def evaluate(spec: FenceSpec, record: dict) -> list[Finding]:
    findings = []
    for rule in record.get("rules", []):
        if not rule_applies(rule, spec):
            continue
        satisfied, result = evaluate_constraint(rule, spec)
        findings.append(Finding(
            rule_id=rule.get("rule_id", "?"),
            status=_status_for(satisfied, result),
            explanation=rule.get("rule_summary", ""),
            verbatim_text=rule.get("verbatim_text"),
            source_url=rule.get("source_url"),
            confidence=float(rule.get("confidence", 1.0)),
        ))
    return findings


def aggregate(findings: list[Finding]):
    """Most-restrictive-applicable-rule governs (conservative & safe)."""
    if not findings:
        return "NEEDS_REVIEW", True, [
            "No loaded rule covers this fence configuration; manual review needed."]
    if any(f.status == "fail" for f in findings):
        return "FAIL", False, []
    if any(f.status == "needs_review" for f in findings):
        return "NEEDS_REVIEW", True, [
            "One or more applicable rules could not be evaluated automatically."]
    return "PASS", False, []


# ---- orchestration (uses DB) ------------------------------------------------
def check_compliance(spec: FenceSpec) -> ComplianceReport:
    from compliance.db import get_rules

    jid = spec.jurisdiction_id
    if not jid and spec.address:
        from compliance.jurisdiction import resolve_jurisdiction
        jid = resolve_jurisdiction(spec.address)["jurisdiction_id"]

    if not jid:
        return ComplianceReport(
            matched=False, overall="NEEDS_REVIEW", needs_human_review=True,
            review_reasons=["Address is not in a covered jurisdiction; routed to human review."],
            summary="This address isn't in a city we have fence rules for yet, so it needs manual review.")

    record = get_rules(jid)
    if not record:
        return ComplianceReport(
            matched=False, jurisdiction_id=jid, overall="NEEDS_REVIEW", needs_human_review=True,
            review_reasons=[f"No rules loaded for {jid}."],
            summary="We don't have rules loaded for this city yet; manual review needed.")

    findings = evaluate(spec, record)
    overall, needs_review, reasons = aggregate(findings)
    report = ComplianceReport(
        matched=True, jurisdiction=record.get("jurisdiction"), jurisdiction_id=jid,
        overall=overall, findings=findings, needs_human_review=needs_review,
        review_reasons=reasons, source_url=record.get("source_url"))
    report.summary = _narrate(spec, report)
    return report


# ---- LLM narration (never changes the verdict; falls back if unavailable) ---
def _narrate(spec: FenceSpec, report: ComplianceReport) -> str:
    try:
        import os
        from openai import OpenAI
        client = OpenAI()
        facts = "; ".join(f"{f.rule_id}={f.status}" for f in report.findings)
        user = (f"A {spec.height_ft}ft {spec.material} fence in the {spec.location} yard "
                f"in {report.jurisdiction}. Deterministic verdict: {report.overall}. "
                f"Findings: {facts}. Write 2 plain sentences for the contractor explaining "
                f"the verdict. Do not invent rules; only summarize these findings.")
        r = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0,
            messages=[{"role": "system", "content": "Summarize a fence compliance result plainly. Never change the verdict."},
                      {"role": "user", "content": user}])
        return r.choices[0].message.content.strip()
    except Exception:
        fails = [f.explanation for f in report.findings if f.status == "fail"]
        if report.overall == "FAIL":
            return f"This fence does not comply in {report.jurisdiction}. Issue(s): " + "; ".join(fails) + "."
        if report.overall == "PASS":
            return f"This fence appears compliant with {report.jurisdiction}'s fence rules based on available checks."
        return "This configuration needs human review."