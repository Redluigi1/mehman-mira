"""suggest_addons — eligibility rules plus segment affinity (Bonus 1, plan §7).
Deterministic throughout: eligibility is checked against the same dataset
facts the guest could be told about (property amenities, known policies),
never guessed. Ranking may use `party_type` and other segment signals to
order suggestions, but the *reason* text only ever cites something the
guest explicitly stated (Decision 009 — segmentation is silent, never
spoken aloud; an explicitly-stated occasion or trip purpose is not that).
"""
from __future__ import annotations

from app.data.repo import Repo
from app.tools.types import SuggestAddonsArgs, SuggestAddonsResult, SuggestedAddon

MAX_SUGGESTIONS = 2


def _is_eligible(addon, repo: Repo, property_id: str) -> bool:
    if addon.eligibility is None:
        return True
    if addon.eligibility == "requires_airport":
        prop = repo.get_property(property_id)
        return prop is not None and "airport_shuttle" in prop.amenities
    if addon.eligibility == "requires_early_checkin_available":
        policy = repo.get_policy(property_id, "early_checkin")
        return policy.status == "known" and policy.value in (False, "on_request")
    if addon.eligibility == "requires_late_checkout_available":
        policy = repo.get_policy(property_id, "late_checkout")
        return policy.status == "known" and policy.value in (False, "on_request")
    return False


def _reason(addon, args: SuggestAddonsArgs) -> str:
    if args.occasion and args.occasion in addon.segment_affinity:
        return f"you mentioned it's your {args.occasion.replace('_', ' ')}"
    if args.trip_purpose and args.trip_purpose in addon.segment_affinity:
        return f"handy for a {args.trip_purpose} trip"
    if addon.eligibility == "requires_airport":
        return "this property offers an airport shuttle"
    if addon.eligibility in ("requires_early_checkin_available", "requires_late_checkout_available"):
        return "available on request, guaranteed if booked ahead"
    return "a popular add-on at this property"


def _score(addon, args: SuggestAddonsArgs) -> int:
    score = 0
    if args.party_type and args.party_type in addon.segment_affinity:
        score += 1
    if args.occasion and args.occasion in addon.segment_affinity:
        score += 2
    if args.trip_purpose and args.trip_purpose in addon.segment_affinity:
        score += 2
    return score


def suggest_addons(repo: Repo, args: SuggestAddonsArgs) -> SuggestAddonsResult:
    candidates = [a for a in repo.get_addons(args.property_id) if _is_eligible(a, repo, args.property_id)]
    ranked = sorted(candidates, key=lambda a: _score(a, args), reverse=True)[:MAX_SUGGESTIONS]
    suggestions = [
        SuggestedAddon(id=a.id, name=a.name, price=a.price, price_basis=a.price_basis.value, reason=_reason(a, args))
        for a in ranked
    ]
    return SuggestAddonsResult(property_id=args.property_id, suggestions=suggestions)
