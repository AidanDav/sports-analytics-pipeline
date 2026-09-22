"""Conference filtering shared by the games route and the report service.

Presets like "Power 4" are UI conveniences, not conferences that exist in
the data, so they get expanded here into the real conference names.
Keeping this in one place means the Games page and report generation can
never disagree on what a conference filter matches.
"""
from sqlalchemy import or_, select

from app.models.game import Game
from app.models.team import Team

# Exact strings as stored by CFBD. The filter is an exact match,
# so "Big 10" or "American" would silently match nothing.
POWER_4 = ["SEC", "Big Ten", "Big 12", "ACC"]
GROUP_OF_5 = [
    "American Athletic",
    "Conference USA",
    "Mid-American",
    "Mountain West",
    "Pac-12",
    "Sun Belt",
]
FBS_CONFERENCES = POWER_4 + GROUP_OF_5 + ["FBS Independents"]

# Preset name -> the real conference names it stands for
PRESETS: dict[str, list[str]] = {
    "Power 4": POWER_4,
    "All FBS": FBS_CONFERENCES,
}


def conference_options() -> list[str]:
    """What the frontend dropdowns offer: presets first, then each conference."""
    return list(PRESETS) + FBS_CONFERENCES


def expand_conference(conference: str) -> list[str]:
    """Turn a filter value into the list of conference names to match.

    A preset expands to its members. Anything else is treated as a
    single real conference name.
    """
    return PRESETS.get(conference, [conference])


def game_in_conference(conference: str):
    """SQL condition: the game involves at least one team from the conference.

    Uses a subquery of team IDs instead of joining Team twice (once for
    home, once for away). The database resolves the subquery once and
    checks both columns against it.
    """
    team_ids = select(Team.id).where(
        Team.conference.in_(expand_conference(conference))
    )
    return or_(
        Game.home_team_id.in_(team_ids),
        Game.away_team_id.in_(team_ids),
    )