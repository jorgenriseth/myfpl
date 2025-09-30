import pytest
from pathlib import Path

import myfpl.validate as V


def make_sample_bootstrap():
    return {
        "element_types": [
            {"id": 1, "singular_name_short": "GKP"},
            {"id": 2, "singular_name_short": "DEF"},
            {"id": 3, "singular_name_short": "MID"},
            {"id": 4, "singular_name_short": "FWD"},
        ],
        "teams": [
            {"id": 1, "name": "Arsenal", "short_name": "ARS", "code": 3},
            {"id": 15, "name": "Newcastle", "short_name": "NEW", "code": 4},
        ],
        "elements": [
            {
                "id": 11,
                "first_name": "Benjamin",
                "second_name": "White",
                "web_name": "White",
                "element_type": 2,
                "now_cost": 54,
                "team": 1,
            },
            {
                "id": 498,
                "first_name": "Joe",
                "second_name": "White",
                "web_name": "White",
                "element_type": 3,
                "now_cost": 45,
                "team": 15,
            },
            {
                "id": 1,
                "first_name": "David",
                "second_name": "Raya Martín",
                "web_name": "Raya",
                "element_type": 1,
                "now_cost": 56,
                "team": 1,
            },
        ],
    }


def test_parse_input_line_simple():
    assert V.parse_input_line("Harry Kane") == ("Harry Kane", None)


def test_parse_input_line_with_team():
    assert V.parse_input_line("White; Arsenal") == ("White", "Arsenal")


def test_match_candidate_and_team_disambiguation():
    bs = make_sample_bootstrap()
    players = V.build_players_index(bs)
    # ambiguous without team
    matches = V.match_candidate("White", players)
    assert len(matches) == 2
    # disambiguate using team hint
    matches_a = V.match_candidate_with_team("White", "Arsenal", players)
    assert len(matches_a) == 1
    assert matches_a[0]["id"] == 11
    matches_n = V.match_candidate_with_team("White", "Newcastle", players)
    assert len(matches_n) == 1
    assert matches_n[0]["id"] == 498


def test_normalize_variants():
    assert V.normalize("J.Timber") == V.normalize("J Timber")
