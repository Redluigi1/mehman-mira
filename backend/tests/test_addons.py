"""suggest_addons — eligibility and ranking (Bonus 1, plan §7)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.data.loader import build_database
from app.data.repo import Repo
from app.tools.addons import suggest_addons
from app.tools.types import SuggestAddonsArgs

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> Repo:
    db_path = tmp_path_factory.mktemp("db") / "mira_test.db"
    conn = build_database(DATA_DIR, db_path)
    return Repo(conn)


def test_airport_pickup_only_eligible_with_shuttle_amenity(repo: Repo):
    with_shuttle = suggest_addons(repo, SuggestAddonsArgs(property_id="alibaug-gen-16"))
    without_shuttle = suggest_addons(repo, SuggestAddonsArgs(property_id="alibaug-gen-15"))
    assert any(s.id == "addon-airport-pickup" for s in with_shuttle.suggestions)
    assert not any(s.id == "addon-airport-pickup" for s in without_shuttle.suggestions)


def test_guaranteed_early_checkin_ineligible_once_already_free(repo: Repo):
    # coorg-gen-11's early_checkin policy is known True — already free and
    # guaranteed, so paying to "guarantee" it again would be a bad upsell.
    result = suggest_addons(repo, SuggestAddonsArgs(property_id="coorg-gen-11"))
    assert not any(s.id == "addon-early-checkin" for s in result.suggestions)


def test_at_most_two_suggestions_with_reasons(repo: Repo):
    result = suggest_addons(repo, SuggestAddonsArgs(
        property_id="alibaug-gen-16", party_type="couple", occasion="anniversary",
    ))
    assert 0 < len(result.suggestions) <= 2
    assert all(s.reason for s in result.suggestions)


def test_explicit_occasion_ranks_above_unrelated_addon(repo: Repo):
    result = suggest_addons(repo, SuggestAddonsArgs(property_id="alibaug-gen-16", occasion="anniversary"))
    assert result.suggestions[0].id == "addon-candlelight-dinner"
    assert "anniversary" in result.suggestions[0].reason
