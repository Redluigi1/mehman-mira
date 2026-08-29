from datetime import date

from app.domain.state import ConversationState, OptionRef, RejectionReason, Stage
from app.pipeline.extract import Objection, StateDelta
from app.pipeline.reconcile import apply_state_delta
from app.domain.trace import UserAct

TODAY = date(2026, 9, 2)


def _delta(**overrides) -> StateDelta:
    base = dict(user_act=UserAct.NEW_REQUEST, set_fields={}, clear_fields=[], referent_mentions=[],
                date_expression=None, objection=None, confidence={})
    base.update(overrides)
    return StateDelta(**base)


def test_new_request_sets_destination_and_party():
    state = ConversationState(conversation_id="c1")
    delta = _delta(set_fields={"destination.city": "Goa", "party.adults": 3}, date_expression="this weekend")
    state = apply_state_delta(state, delta, TODAY, turn_index=1)
    assert state.intent.destination.value.city == "Goa"
    assert state.intent.party.value.adults == 3
    assert state.intent.stay.value.check_in == "2026-09-04"
    assert state.intent.stay.value.check_out == "2026-09-06"


def test_modify_updates_in_place_without_resetting_other_fields():
    state = ConversationState(conversation_id="c1")
    state = apply_state_delta(state, _delta(
        set_fields={"destination.city": "Goa", "party.adults": 3}, date_expression="this weekend",
    ), TODAY, turn_index=1)

    modify = _delta(user_act=UserAct.MODIFY, set_fields={"party.adults": 4}, date_expression="one more night")
    state2 = apply_state_delta(state, modify, TODAY, turn_index=2)

    assert state2.intent.party.value.adults == 4
    assert state2.intent.destination.value.city == "Goa"  # untouched, not reset


def test_shortlist_invalidated_when_search_key_changes():
    state = ConversationState(conversation_id="c1")
    state = apply_state_delta(state, _delta(
        set_fields={"destination.city": "Goa", "party.adults": 2}, date_expression="this weekend",
    ), TODAY, turn_index=1)
    state.shortlist = [OptionRef(option_id="p:r", property_id="p", room_type_id="r", ordinal=1,
                        property_name="P", room_type_name="R", city="Goa", star_tier=4,
                        rooms_needed=1, nights=2, price_per_night=5000, estimated_total=10000)]
    state.stage = Stage.PRESENT

    changed = apply_state_delta(state, _delta(
        user_act=UserAct.MODIFY, set_fields={"party.adults": 4},
    ), TODAY, turn_index=2)
    assert changed.shortlist == []
    assert changed.stage == Stage.DISCOVER


def test_shortlist_survives_unrelated_field_change():
    state = ConversationState(conversation_id="c1")
    state = apply_state_delta(state, _delta(
        set_fields={"destination.city": "Goa", "party.adults": 2}, date_expression="this weekend",
    ), TODAY, turn_index=1)
    state.shortlist = [OptionRef(option_id="p:r", property_id="p", room_type_id="r", ordinal=1,
                        property_name="P", room_type_name="R", city="Goa", star_tier=4,
                        rooms_needed=1, nights=2, price_per_night=5000, estimated_total=10000)]

    same = apply_state_delta(state, _delta(
        user_act=UserAct.MODIFY, set_fields={"amenities_required": ["wifi"]},
    ), TODAY, turn_index=2)
    assert len(same.shortlist) == 1


def test_clear_fields_resets_slot():
    state = ConversationState(conversation_id="c1")
    state = apply_state_delta(state, _delta(set_fields={"budget.amount": 20000, "budget.basis": "per_night"}), TODAY, turn_index=1)
    assert state.intent.budget.value is not None

    cleared = apply_state_delta(state, _delta(clear_fields=["budget"]), TODAY, turn_index=2)
    assert cleared.intent.budget.value is None


def test_malformed_field_value_is_ignored_not_fatal():
    state = ConversationState(conversation_id="c1")
    delta = _delta(set_fields={"party.adults": "not-a-number", "destination.city": "Goa"})
    state = apply_state_delta(state, delta, TODAY, turn_index=1)
    assert state.intent.destination.value.city == "Goa"
    assert state.intent.party.value is None


def test_objection_recorded_against_focused_option():
    state = ConversationState(conversation_id="c1")
    state.focused_option = OptionRef(option_id="p:r", property_id="p", room_type_id="r", ordinal=1,
                        property_name="P", room_type_name="R", city="Goa", star_tier=4,
                        rooms_needed=1, nights=2, price_per_night=5000, estimated_total=10000)
    delta = _delta(user_act=UserAct.OBJECTION, objection=Objection(kind=RejectionReason.PRICE, detail="too expensive"))
    state = apply_state_delta(state, delta, TODAY, turn_index=2)
    assert len(state.rejected) == 1
    assert state.rejected[0].reason == RejectionReason.PRICE


def test_derived_party_type_family_with_kids():
    state = ConversationState(conversation_id="c1")
    delta = _delta(set_fields={"party.adults": 2, "party.children": [{"age": 8}]})
    state = apply_state_delta(state, delta, TODAY, turn_index=1)
    assert state.intent.party_type.value == "family_with_kids"
