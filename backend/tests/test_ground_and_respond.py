from app.domain.state import ConversationState, OptionRef
from app.domain.trace import GroundingVerdict, NextAction, NextActionType
from app.llm.base import LLMError
from app.pipeline.ground import build_grounding_packet
from app.pipeline.policy import TurnContext
from app.pipeline.respond import _template_fallback, _validate_names, _validate_numbers, generate_response
from app.domain.trace import UserAct


def _option(**overrides) -> OptionRef:
    base = dict(option_id="p1:r1", property_id="p1", room_type_id="r1", ordinal=1,
                property_name="Grand Dunes Villa", room_type_name="Entire Villa", city="Goa",
                area="Candolim", star_tier=5, rooms_needed=1, nights=2, price_per_night=18000.0,
                estimated_total=36000.0)
    base.update(overrides)
    return OptionRef(**base)


def _ctx(**overrides) -> TurnContext:
    base = dict(user_act=UserAct.NEW_REQUEST)
    base.update(overrides)
    return TurnContext(**base)


def test_build_packet_includes_option_facts():
    state = ConversationState(conversation_id="c1")
    state.shortlist = [_option()]
    action = NextAction(type=NextActionType.PRESENT)
    packet = build_grounding_packet(state, _ctx(), action)
    assert len(packet.options) == 1
    assert "Grand Dunes Villa" in packet.allowed_names
    assert "36,000" in packet.allowed_numbers or "36000" in packet.allowed_numbers


def test_validate_numbers_flags_invented_price():
    state = ConversationState(conversation_id="c1")
    state.shortlist = [_option()]
    packet = build_grounding_packet(state, _ctx(), NextAction(type=NextActionType.PRESENT))
    draft = "This villa is available for just ₹99999 total, a steal!"
    assert _validate_numbers(draft, packet) == ["99999"]


def test_validate_numbers_allows_known_price():
    state = ConversationState(conversation_id="c1")
    state.shortlist = [_option()]
    packet = build_grounding_packet(state, _ctx(), NextAction(type=NextActionType.PRESENT))
    draft = "It's ₹36,000 total for 2 nights at 18000 per night."
    assert _validate_numbers(draft, packet) == []


def test_validate_names_flags_invented_property():
    state = ConversationState(conversation_id="c1")
    state.shortlist = [_option()]
    packet = build_grounding_packet(state, _ctx(), NextAction(type=NextActionType.PRESENT))
    draft = "I'd also recommend the Ocean Breeze Resort nearby."
    violations = _validate_names(draft, packet)
    assert "Ocean Breeze Resort" in violations


def test_validate_names_allows_known_property_and_safe_words():
    state = ConversationState(conversation_id="c1")
    state.shortlist = [_option()]
    packet = build_grounding_packet(state, _ctx(), NextAction(type=NextActionType.PRESENT))
    draft = "Good Morning! Grand Dunes Villa is available this weekend."
    assert _validate_names(draft, packet) == []


def test_template_fallback_present_is_grounded():
    state = ConversationState(conversation_id="c1")
    state.shortlist = [_option()]
    packet = build_grounding_packet(state, _ctx(), NextAction(type=NextActionType.PRESENT))
    text = _template_fallback(packet)
    assert "Grand Dunes Villa" in text
    assert "36,000" in text


def test_template_fallback_ask():
    packet = build_grounding_packet(
        ConversationState(conversation_id="c1"), _ctx(),
        NextAction(type=NextActionType.ASK, ask_field="destination"),
    )
    assert "stay" in _template_fallback(packet).lower()


def test_template_fallback_surface_unknown():
    state = ConversationState(conversation_id="c1")
    packet = build_grounding_packet(state, _ctx(), NextAction(type=NextActionType.SURFACE_UNKNOWN))
    packet.facts = [__import__("app.pipeline.ground", fromlist=["GroundedFact"]).GroundedFact(
        key="pool_heated", status="unknown", value=None,
    )]
    text = _template_fallback(packet)
    assert "don't" in text.lower() or "don" in text.lower()


class _RaisingClient:
    def complete_text(self, *, system: str, user: str) -> str:
        raise LLMError("boom")

    def complete_json(self, *, system, user, schema):
        raise LLMError("boom")


class _CleanClient:
    def complete_text(self, *, system: str, user: str) -> str:
        return "Grand Dunes Villa is available for ₹36,000 total across 2 nights."

    def complete_json(self, *, system, user, schema):
        raise NotImplementedError


class _RepairsOnSecondCallClient:
    def __init__(self):
        self.calls = 0

    def complete_text(self, *, system: str, user: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return "This is only ₹500 total, unbeatable!"
        return "It comes to ₹36,000 total across 2 nights."

    def complete_json(self, *, system, user, schema):
        raise NotImplementedError


class _NeverGroundedClient:
    def complete_text(self, *, system: str, user: str) -> str:
        return "This place is amazing and costs only ₹123456."

    def complete_json(self, *, system, user, schema):
        raise NotImplementedError


def _packet():
    state = ConversationState(conversation_id="c1")
    state.shortlist = [_option()]
    return build_grounding_packet(state, _ctx(), NextAction(type=NextActionType.PRESENT))


def test_generate_response_llm_error_falls_back_to_template():
    text, verdict = generate_response(_RaisingClient(), _packet())
    assert verdict == GroundingVerdict.FALLBACK
    assert "Grand Dunes Villa" in text


def test_generate_response_clean_when_grounded():
    text, verdict = generate_response(_CleanClient(), _packet())
    assert verdict == GroundingVerdict.CLEAN


def test_generate_response_repairs_on_second_pass():
    text, verdict = generate_response(_RepairsOnSecondCallClient(), _packet())
    assert verdict == GroundingVerdict.REPAIRED
    assert "36,000" in text


def test_generate_response_falls_back_when_never_grounded():
    text, verdict = generate_response(_NeverGroundedClient(), _packet())
    assert verdict == GroundingVerdict.FALLBACK
    assert "Grand Dunes Villa" in text
