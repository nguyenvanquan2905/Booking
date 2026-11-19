"""Layer 2 policy, BAML schema-aligned extraction & DOM injection guard (MVP-15 — owner: C)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from booking_agent.agent.guardrails.layer1_normalize import NormalizedBookingInput
from booking_agent.shared.errors import ErrorCode, PolicyViolationError

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)ignore\s+(all\s+)?previous\s+instructions"),
    re.compile(r"(?i)forget\s+(all\s+)?(prior|previous)\s+rules"),
    re.compile(r"(?i)<\s*script\b"),
    re.compile(r"(?i)javascript\s*:"),
    re.compile(r"(?i)\b(drop\s+table|union\s+select|;\s*delete\s+from)\b"),
    re.compile(r"(?i)\b(system\s+prompt|exfiltrate|reveal\s+api\s*key)\b"),
    re.compile(r"(?i)\b(override|change|set)\s+(party_size|phone|allow_deposit_max)\b"),
    re.compile(r"(?i)\b(127\.0\.0\.1|localhost|169\.254\.169\.254|0\.0\.0\.0)\b"),
)

_HITL_PAYMENT_RE = re.compile(
    r"(?i)\b(deposit|payment|credit\s*card|chuy[eể]n\s*kho[aả]n|c[oọ]c|thanh\s*to[aá]n)\b"
)

_SOCIAL_SITE_IDS = frozenset(
    {
        "facebook",
        "fb",
        "fanpage",
        "messenger",
        "zalo",
        "zalo_oa",
        "zalooa",
        "instagram",
        "ig",
        "instagram_dm",
    }
)

_SOCIAL_CHANNEL_RE = re.compile(
    r"(?i)(?:facebook\.com|fb\.com|zalo\.me|oa\.zalo|instagram\.com|"
    r"\b(?:facebook\s+fanpage|zalo\s+oa|instagram\s+dm)\b)"
)

_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_UNQUOTED_KEY_RE = re.compile(r"([{\[,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:")
_DEPOSIT_VALUE_RE = re.compile(r"(?i)(?:deposit|dat\s*coc|coc)\s*[:=]?\s*(\d[\d.,]*)")


@dataclass(slots=True)
class PolicyConfig:
    allowed_sites: frozenset[str] = field(default_factory=frozenset)
    hitl_party_size_threshold: int = 10
    max_notes_length: int = 500
    web_only: bool = True


class PolicyDecision(BaseModel):
    allowed: bool
    requires_hitl: bool = False
    risk_level: Literal["low", "medium", "high"] = "low"
    reasons: list[str] = Field(default_factory=list)
    blocked_code: ErrorCode | None = None


class ExtractedBookingForm(BaseModel):
    """Schema-aligned booking form extraction from compact A11y Tree (MVP-15)."""

    site_id: str
    date: str | None = None
    time: str | None = None
    party_size: int | None = None
    phone: str | None = None
    branch: str | None = None
    deposit_amount: int = Field(default=0, ge=0)
    missing_fields: list[str] = Field(default_factory=list)
    injection_detected: bool = False
    repaired_client_side: bool = False


def repair_json_fast(raw_text: str) -> tuple[dict[str, Any], bool]:
    """Client-side tolerant JSON parser (<0.1ms) fixing fences, trailing commas, unquoted keys."""
    text = raw_text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed, False
    except json.JSONDecodeError:
        pass

    repaired = text
    if repaired.startswith("```"):
        lines = repaired.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        repaired = "\n".join(lines).strip()

    repaired = _TRAILING_COMMA_RE.sub(r"\1", repaired)
    repaired = _UNQUOTED_KEY_RE.sub(r'\1"\2":', repaired)
    if "'" in repaired and '"' not in repaired:
        repaired = repaired.replace("'", '"')

    parsed = json.loads(repaired)
    if not isinstance(parsed, dict):
        raise ValueError("Repaired JSON payload must be an object")
    return parsed, True


class LlmFormFields(BaseModel):
    """Fields the Tier-3 LLM must return from a compact A11y Tree (MVP-15 output contract)."""

    date: str | None = Field(default=None, description="Booking date YYYY-MM-DD")
    time: str | None = Field(default=None, description="Booking time HH:MM")
    party_size: int | None = Field(default=None, description="Number of guests")
    phone: str | None = Field(default=None, description="Contact phone field label")
    branch: str | None = Field(default=None, description="Restaurant branch")
    deposit_amount: int = Field(default=0, description="Required deposit in VND")
    missing_fields: list[str] = Field(default_factory=list, description="Fields not found")


_BAML_TYPE_NAMES = {"str": "string", "int": "int", "list[str]": "string[]"}


def render_baml_format_prompt() -> str:
    """Compact BAML-style output-format block (type signature only, SAP parses the rest)."""
    lines = ["Answer in JSON using this schema:", "{"]
    for name, info in LlmFormFields.model_fields.items():
        ann = str(info.annotation).replace("typing.", "")
        optional = "None" in ann
        base = ann.replace(" | None", "").replace("<class '", "").replace("'>", "")
        type_name = _BAML_TYPE_NAMES.get(base, base)
        lines.append(f"  {name}: {type_name}{' or null' if optional else ''},")
    lines.append("}")
    return "\n".join(lines)


def render_json_schema_format_prompt() -> str:
    """Baseline: full JSON Schema output-format block (what plain function-calling sends)."""
    schema = json.dumps(LlmFormFields.model_json_schema(), indent=2)
    return f"Return a JSON object that strictly validates against this JSON Schema:\n{schema}"


def estimate_tokens(text: str) -> int:
    """Cheap tokenizer-free estimate (~4 chars/token, cl100k-like) for format-overhead budgets."""
    return max(1, -(-len(text) // 4))


def format_token_savings() -> float:
    """Fraction of format-description tokens saved by BAML-style schema vs full JSON Schema."""
    baml = estimate_tokens(render_baml_format_prompt())
    full = estimate_tokens(render_json_schema_format_prompt())
    return 1.0 - (baml / full)


def scan_for_injection(text: str) -> bool:
    """Return True if untrusted text matches any prompt injection or SSRF pattern."""
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


def parse_and_guard_a11y(
    a11y_tree_snapshot: str,
    trusted_intent: NormalizedBookingInput,
) -> tuple[ExtractedBookingForm, PolicyDecision]:
    """Parse A11y form fields with BAML-style repair and strict Data-Control Isolation."""
    if scan_for_injection(a11y_tree_snapshot):
        form = ExtractedBookingForm(
            site_id=trusted_intent.site_id,
            date=trusted_intent.booking_date,
            time=trusted_intent.booking_time.strftime("%H:%M"),
            party_size=trusted_intent.party_size,
            phone=trusted_intent.customer_phone,
            injection_detected=True,
        )
        decision = PolicyDecision(
            allowed=False,
            risk_level="high",
            reasons=["Indirect prompt injection detected inside untrusted A11y/DOM snapshot"],
            blocked_code=ErrorCode.PROMPT_INJECTION_DETECTED,
        )
        return form, decision

    parsed_fields: dict[str, Any] = {}
    repaired_flag = False
    stripped = a11y_tree_snapshot.strip()
    if stripped.startswith("{") or stripped.startswith("```"):
        try:
            parsed_fields, repaired_flag = repair_json_fast(stripped)
        except Exception:
            parsed_fields = {}

    deposit_amount = 0
    if "deposit_amount" in parsed_fields:
        try:
            deposit_amount = max(0, int(parsed_fields["deposit_amount"]))
        except (TypeError, ValueError):
            deposit_amount = 0
    else:
        m = _DEPOSIT_VALUE_RE.search(a11y_tree_snapshot)
        if m:
            digits = re.sub(r"[^\d]", "", m.group(1))
            if digits:
                deposit_amount = int(digits)

    branch_val = parsed_fields.get("branch")
    if branch_val is not None and scan_for_injection(str(branch_val)):
        return (
            ExtractedBookingForm(site_id=trusted_intent.site_id, injection_detected=True),
            PolicyDecision(
                allowed=False,
                risk_level="high",
                reasons=["Malicious branch value rejected by Data-Control Isolation"],
                blocked_code=ErrorCode.PROMPT_INJECTION_DETECTED,
            ),
        )

    # Data-Control Isolation: always keep trusted user intent fields over untrusted web values
    missing: list[str] = []
    if not parsed_fields.get("date") and "date" not in a11y_tree_snapshot.lower():
        missing.append("date")
    if not parsed_fields.get("time") and "time" not in a11y_tree_snapshot.lower():
        missing.append("time")

    form = ExtractedBookingForm(
        site_id=trusted_intent.site_id,
        date=trusted_intent.booking_date,
        time=trusted_intent.booking_time.strftime("%H:%M"),
        party_size=trusted_intent.party_size,
        phone=trusted_intent.customer_phone,
        branch=str(branch_val) if branch_val is not None else None,
        deposit_amount=deposit_amount,
        missing_fields=missing,
        injection_detected=False,
        repaired_client_side=repaired_flag,
    )

    if deposit_amount > trusted_intent.allow_deposit_max:
        return form, PolicyDecision(
            allowed=True,
            requires_hitl=True,
            risk_level="high",
            reasons=[
                f"Detected deposit {deposit_amount} exceeds allow_deposit_max "
                f"({trusted_intent.allow_deposit_max})"
            ],
        )

    return form, PolicyDecision(allowed=True, requires_hitl=False, risk_level="low")


def evaluate_policy(
    booking_input: NormalizedBookingInput,
    *,
    config: PolicyConfig | None = None,
    raise_on_block: bool = False,
) -> PolicyDecision:
    """Evaluate safety, web-only channel rules, prompt-injection, and HITL policies."""
    cfg = config or PolicyConfig()
    reasons: list[str] = []

    if cfg.web_only and (
        booking_input.channel != "web"
        or booking_input.site_id in _SOCIAL_SITE_IDS
        or _SOCIAL_CHANNEL_RE.search(booking_input.site_id)
        or _SOCIAL_CHANNEL_RE.search(booking_input.notes)
    ):
        decision = PolicyDecision(
            allowed=False,
            risk_level="medium",
            reasons=["Social media channels are deprecated; only web booking sites are supported"],
            blocked_code=ErrorCode.UNSUPPORTED_CHANNEL,
        )
        if raise_on_block:
            raise PolicyViolationError(
                decision.reasons[0],
                code=ErrorCode.UNSUPPORTED_CHANNEL,
                details={"site_id": booking_input.site_id, "channel": booking_input.channel},
            )
        return decision

    if cfg.allowed_sites and booking_input.site_id not in cfg.allowed_sites:
        decision = PolicyDecision(
            allowed=False,
            risk_level="high",
            reasons=[f"Site '{booking_input.site_id}' is not in the configured allowlist"],
            blocked_code=ErrorCode.POLICY_BLOCKED,
        )
        if raise_on_block:
            raise PolicyViolationError(
                decision.reasons[0],
                code=ErrorCode.POLICY_BLOCKED,
                details={"site_id": booking_input.site_id},
            )
        return decision

    fields_to_scan = (
        booking_input.site_id,
        booking_input.restaurant_name,
        booking_input.customer_name,
        booking_input.notes,
    )
    for text in fields_to_scan:
        if scan_for_injection(text):
            decision = PolicyDecision(
                allowed=False,
                risk_level="high",
                reasons=["Suspicious prompt injection or unsafe URL pattern detected"],
                blocked_code=ErrorCode.PROMPT_INJECTION_DETECTED,
            )
            if raise_on_block:
                raise PolicyViolationError(
                    decision.reasons[0],
                    code=ErrorCode.PROMPT_INJECTION_DETECTED,
                )
            return decision

    if len(booking_input.notes) > cfg.max_notes_length:
        decision = PolicyDecision(
            allowed=False,
            risk_level="medium",
            reasons=[f"notes length exceeds limit ({cfg.max_notes_length})"],
            blocked_code=ErrorCode.POLICY_BLOCKED,
        )
        if raise_on_block:
            raise PolicyViolationError(decision.reasons[0], code=ErrorCode.POLICY_BLOCKED)
        return decision

    requires_hitl = False
    risk_level: Literal["low", "medium", "high"] = "low"

    if booking_input.party_size >= cfg.hitl_party_size_threshold:
        requires_hitl = True
        risk_level = "medium"
        reasons.append(
            f"Large party size ({booking_input.party_size} >= "
            f"{cfg.hitl_party_size_threshold}) requires approval"
        )

    if booking_input.notes and _HITL_PAYMENT_RE.search(booking_input.notes):
        requires_hitl = True
        risk_level = "high"
        reasons.append("Payment or deposit instruction detected in notes")

    return PolicyDecision(
        allowed=True,
        requires_hitl=requires_hitl,
        risk_level=risk_level,
        reasons=reasons,
        blocked_code=None,
    )
