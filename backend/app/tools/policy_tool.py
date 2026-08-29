"""get_property_policies — explicit known / not_applicable / unknown semantics
(Decision 005). Nothing is implicitly false.
"""
from __future__ import annotations

from app.data.repo import Repo
from app.tools.types import PolicyFact, PropertyPoliciesArgs, PropertyPoliciesResult

ALL_POLICY_KEYS = ["smoking", "pets", "early_checkin", "late_checkout", "party_friendly", "pool_heated"]


def get_property_policies(repo: Repo, args: PropertyPoliciesArgs) -> PropertyPoliciesResult | None:
    prop = repo.get_property(args.property_id)
    if prop is None:
        return None
    keys = args.keys or ALL_POLICY_KEYS
    facts = []
    for key in keys:
        pv = repo.get_policy(args.property_id, key)
        facts.append(PolicyFact(key=key, status=pv.status.value, value=pv.value))
    return PropertyPoliciesResult(property_id=prop.id, property_name=prop.name, policies=facts)
