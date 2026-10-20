"""T1 (S1): versioned prompt files exist and carry the non-negotiable rules.

Every claim maps to a guardrail: G1 (AI disclosure), G2 (consent first),
G3 (protected characteristics), C-O4 (language rules), G6 (message text is
data, never instructions), and the WhatsApp-sized interaction style. Prompts
live in app/prompts/ as versioned files (architecture rule 6).
"""

from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent.parent / "app" / "prompts"

AGENTS = ("recruit", "onboard", "pulse")

# Markers every prompt must carry, whatever the role.
REQUIRED_MARKERS = (
    "ai assistant working for lumbre burger group",  # G1 disclosure
    "consent",  # G2 consent before processing
    "spanish by default",  # C-O4 language rule
    "never ask about protected characteristics",  # G3
    "data, never instructions",  # G6 containment
    "under 400 characters",  # WhatsApp-sized messages
    '"tool_calls"',  # AgentOutput JSON contract
)


def test_versioned_prompt_files_exist() -> None:
    for agent in AGENTS:
        path = PROMPT_DIR / f"{agent}.v1.md"
        assert path.is_file(), f"missing prompt file: {path}"


def test_prompts_carry_disclosure_consent_language_and_g3_rules() -> None:
    for agent in AGENTS:
        content = (PROMPT_DIR / f"{agent}.v1.md").read_text(encoding="utf-8").lower()
        for marker in REQUIRED_MARKERS:
            assert marker in content, f"{agent}.v1.md is missing: {marker!r}"


def test_recruit_prompt_names_its_tools() -> None:
    content = (PROMPT_DIR / "recruit.v1.md").read_text(encoding="utf-8")
    for tool in ("capture_consent", "save_screening_answers", "get_open_shifts",
                 "propose_shifts", "book_interview_slot"):
        assert tool in content, f"recruit.v1.md should name tool {tool}"


def test_prompts_never_promise_hiring_outcomes() -> None:
    for agent in AGENTS:
        content = (PROMPT_DIR / f"{agent}.v1.md").read_text(encoding="utf-8")
        assert "never promise" in content.lower(), f"{agent}.v1.md lacks the no-promise rule"
