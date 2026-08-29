"""Referent resolution — "the second one", "the villa", "what about that
place?" resolved against the registry of options actually shown (Bonus 2 /
plan §7), not re-guessed from scratch.
"""
from __future__ import annotations

from app.data.repo import Repo
from app.domain.state import ConversationState, OptionRef

_ORDINAL_WORDS = {
    "first": 1, "1st": 1, "one": 1,
    "second": 2, "2nd": 2, "two": 2,
    "third": 3, "3rd": 3, "three": 3,
    "fourth": 4, "4th": 4, "four": 4,
}

# Recovery behaviours (Bonus 2, plan §7): phrases with no ordinal or name in
# them at all, where the guest is nonetheless clearly asking Mira to pick.
_DEFER_TO_RANKING_PHRASES = ("whichever", "whatever", "you pick", "you choose", "recommend", "best one", "up to you")
_OTHER_PHRASES = ("other one", "the other", "different one", "another one")


def resolve_selection(state: ConversationState, referent_mentions: list[str], repo: Repo) -> OptionRef | None:
    if not state.shortlist:
        return None
    text = " ".join(referent_mentions).lower()

    # "what about the other one?" / "another one" — checked before the plain
    # ordinal-word match below, since "other one" and "another one" both
    # contain the bare word "one" and would otherwise be misread as ordinal 1.
    # Meaningful only when there's exactly one other option to switch to;
    # with three or more it's genuinely ambiguous and falls through rather
    # than guessing which "other" one is meant.
    if any(p in text for p in _OTHER_PHRASES):
        if len(state.shortlist) == 2 and state.focused_option is not None:
            other = next((o for o in state.shortlist if o.option_id != state.focused_option.option_id), None)
            if other is not None:
                return other
        return None

    if "last" in text:
        return state.referents.by_ordinal(len(state.shortlist))
    for word, ordinal in _ORDINAL_WORDS.items():
        if word in text:
            match = state.referents.by_ordinal(ordinal)
            if match is not None:
                return match

    for option in state.shortlist:
        prop = repo.get_property(option.property_id)
        if prop and prop.name.lower() in text:
            return option
        room = repo.get_room_type(option.room_type_id)
        if room and room.name.lower() in text:
            return option

    # "whichever is better" / "you pick" — defer to the shortlist's own
    # ranking (first = best match), never a guessed preference.
    if any(p in text for p in _DEFER_TO_RANKING_PHRASES):
        return state.shortlist[0]

    if len(state.shortlist) == 1:
        return state.shortlist[0]
    return None


def resolve_target_property(state: ConversationState, referent_mentions: list[str], repo: Repo) -> str | None:
    if state.focused_option is not None:
        return state.focused_option.property_id
    if referent_mentions:
        option = resolve_selection(state, referent_mentions, repo)
        if option is not None:
            return option.property_id
    if len(state.shortlist) == 1:
        return state.shortlist[0].property_id
    return None
