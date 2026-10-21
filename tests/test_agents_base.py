"""T1 (S1): AgentRunner behavior without I/O: Pydantic output validation with
one re-ask, agent.turn / tool.call event payloads (prompt_version, model,
latency, tokens), and prompt loading.

These tests use a scripted model and an in-memory fake service, so they run
fully offline. The DB-backed conversation lives in tests.test_agents_recruit.
"""

from typing import Any

from app.agents.base import AgentOutputError, AgentRunner, ToolOutcome, TurnContext
from app.agents.model_port import ScriptedModel
from app.settings import Settings

# ------------------------------------------------------------ fake service


class FakeAgentService:
    """In-memory stand-in for app.agents.services.AgentService.

    Mirrors the same contract the real service implements: context(),
    execute_tool() (with the pure dispatcher as the enforcement point) and
    record_event(). Events collect in `self.events` as (EventType, payload).
    """

    def __init__(
        self,
        *,
        state: str = "contacted",
        agent: str = "recruit",
        tool_results: dict[str, ToolOutcome] | None = None,
    ) -> None:
        self.agent = agent
        self.state = state
        self.tool_results = tool_results or {}
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.tool_calls: list[tuple[str, dict[str, Any]]] = []

    def context(self) -> TurnContext:
        from app.agents.tools import tools_for

        return TurnContext(
            state=self.state,
            candidate_name="Marta",
            language="es",
            allowed_tools=tools_for(self.agent, self.state),
        )

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolOutcome:
        from app.agents.tools import ToolDispatcher

        self.tool_calls.append((tool_name, dict(arguments)))
        rejection = ToolDispatcher().validate(tool_name, self.agent, self.state)
        if rejection is not None:
            self.record_event(
                "tool.call",
                {
                    "tool": tool_name,
                    "status": "rejected",
                    "reason": rejection.reason,
                    "state": self.state,
                },
            )
            return ToolOutcome(status="rejected", result={}, reason=rejection.reason)
        outcome = self.tool_results.get(
            tool_name, ToolOutcome(status="ok", result={"applied": True}, reason=None)
        )
        self.record_event(
            "tool.call",
            {"tool": tool_name, "status": outcome.status, "result": outcome.result},
        )
        return outcome

    def record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        key = event_type.value if hasattr(event_type, "value") else str(event_type)
        self.events.append((key, dict(payload)))


# ---------------------------------------------------------------- runner


def _runner(service: FakeAgentService, replies: list[dict[str, Any]]) -> AgentRunner:
    return AgentRunner(service, ScriptedModel(replies), agent=service.agent)


def test_valid_turn_records_agent_turn_with_six_point_metadata() -> None:
    service = FakeAgentService(state="contacted")
    runner = _runner(
        service,
        replies=[
            {"message": {"body": "Hola, soy el asistente de Lumbre Burger.", "language": "es"}}
        ],
    )

    result = runner.run_turn("Hola, vi el cartel del local")

    assert result.status == "ok"
    assert result.message is not None
    assert result.message.body.startswith("Hola")
    assert result.validation_retries == 0
    turns = [p for t, p in service.events if t == "agent.turn"]
    assert len(turns) == 1
    payload = turns[0]
    assert payload["agent"] == "recruit"
    assert payload["prompt_version"] == "v1"
    assert payload["model"] == "scripted"
    assert payload["state"] == "contacted"
    assert payload["status"] == "ok"
    assert payload["latency_ms"] >= 0
    assert payload["tokens"]["input"] >= 0
    assert payload["tokens"]["output"] >= 0


def test_runner_applies_allowed_tool_calls_through_the_service() -> None:
    service = FakeAgentService(state="contacted")
    runner = _runner(
        service,
        replies=[
            {
                "message": {"body": "Gracias por tu respuesta.", "language": "es"},
                "tool_calls": [{"name": "capture_consent", "arguments": {"channel": "whatsapp"}}],
                "extracted_facts": {"consent_granted": True, "language": "es"},
            }
        ],
    )

    result = runner.run_turn("Si, doy mi consentimiento")

    assert [o.status for o in result.tool_outcomes] == ["ok"]
    assert service.tool_calls == [("capture_consent", {"channel": "whatsapp"})]
    assert result.extracted_facts is not None
    assert result.extracted_facts.consent_granted is True


def test_oversized_body_fails_validation_and_reasks_once() -> None:
    # WhatsApp-sized rule: a body over the schema limit is invalid model
    # output; the runner re-asks exactly once and then proceeds.
    service = FakeAgentService(state="contacted")
    long_body = "x" * 700
    runner = _runner(
        service,
        replies=[
            {"message": {"body": long_body, "language": "es"}},
            {"message": {"body": "Hola, soy el asistente.", "language": "es"}},
        ],
    )

    result = runner.run_turn("Hola")

    assert result.status == "ok"
    assert result.validation_retries == 1
    assert result.message is not None and result.message.body == "Hola, soy el asistente."
    assert len(service.events) >= 2  # message.in + agent.turn (one final turn only)
    turns = [p for t, p in service.events if t == "agent.turn"]
    assert len(turns) == 1
    assert turns[0]["validation_retries"] == 1


def test_two_invalid_outputs_raise_after_one_reask() -> None:
    service = FakeAgentService(state="contacted")
    runner = _runner(
        service,
        replies=[
            {"message": {"body": "sin idioma"}},
            {"message": {"body": "", "language": "de"}},
        ],
    )

    try:
        runner.run_turn("Hola")
        raised = False
    except AgentOutputError:
        raised = True
    assert raised, "second invalid output must raise AgentOutputError"
    turns = [p for t, p in service.events if t == "agent.turn"]
    assert len(turns) == 1
    assert turns[0]["status"] == "invalid_output"
    assert turns[0]["validation_retries"] == 1
    # No tool ran and no valid message went out.
    assert service.tool_calls == []


def test_unknown_prompt_agent_fails_loudly() -> None:
    service = FakeAgentService(state="contacted")
    try:
        AgentRunner(service, ScriptedModel(), agent="nonexistent", prompt_version="v1")
        raised = False
    except FileNotFoundError:
        raised = True
    assert raised


# ------------------------------------------------------------- model factory


def test_factory_selects_scripted_by_default() -> None:
    from app.agents.model_port import ScriptedModel, build_model

    model = build_model(Settings(llm_mode="scripted"))
    assert isinstance(model, ScriptedModel)


def test_factory_selects_strands_openai_when_live_with_key() -> None:
    from app.agents.model_port import StrandsOpenAIModel, build_model

    model = build_model(
        Settings(llm_mode="live", openai_api_key="sk-test", openai_model="gpt-4.1-mini")
    )
    assert isinstance(model, StrandsOpenAIModel)
    assert model.model_name == "gpt-4.1-mini"


def test_live_mode_without_api_key_fails_loudly() -> None:
    from app.agents.model_port import StrandsOpenAIModel

    try:
        StrandsOpenAIModel(cfg=Settings(llm_mode="live", openai_api_key=None))
        raised = False
    except ValueError:
        raised = True
    assert raised
