import logging
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.game import Game
from app.models.team import Team
from app.models.player import Player
from app.models.player_stats import PlayerStats
from app.models.report import Report

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-5"


class ReportService:
    """Generates analytical reports from ingested sports data using Claude."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def _gather_week_data(self, season: int, week: int, league: str = "nfl") -> dict:
        """Pull all relevant data for a given week to feed into the prompt."""

        # Get all games for this week
        result = await self.db.execute(
            select(Game).where(
                Game.season == season,
                Game.week == week,
                Game.status == "final",
                Game.league == league
            )
        )
        games = result.scalars().all()

        if not games:
            return {"games": [], "top_performers": []}

        # Build team lookup for name resolution
        team_ids = set()
        for g in games:
            if g.home_team_id:
                team_ids.add(g.home_team_id)
            if g.away_team_id:
                team_ids.add(g.away_team_id)

        team_lookup = {}
        if team_ids:
            result = await self.db.execute(
                select(Team).where(Team.id.in_(team_ids))
            )
            team_lookup = {t.id: t.name for t in result.scalars().all()}

        # Format game summaries
        game_summaries = []
        game_ids = []
        for g in games:
            game_ids.append(g.id)
            game_summaries.append({
                "home_team": team_lookup.get(g.home_team_id, "Unknown"),
                "away_team": team_lookup.get(g.away_team_id, "Unknown"),
                "home_score": g.home_score,
                "away_score": g.away_score,
                "venue": g.venue,
            })

        # Get top stat performances from these games
        # Passing: most yards
        top_passers = await self._top_performers(
            game_ids, "passing", "yards", limit=3
        )
        # Rushing: most yards
        top_rushers = await self._top_performers(
            game_ids, "rushing", "yards", limit=3
        )
        # Receiving: most yards
        top_receivers = await self._top_performers(
            game_ids, "receiving", "yards", limit=3
        )

        return {
            "games": game_summaries,
            "top_passers": top_passers,
            "top_rushers": top_rushers,
            "top_receivers": top_receivers,
        }

    async def _top_performers(
        self, game_ids: list[int], category: str, stat_col: str, limit: int = 3
    ) -> list[dict]:
        """Find the top performers in a stat category across a set of games."""
        # Get the column dynamically
        col = getattr(PlayerStats, stat_col)

        result = await self.db.execute(
            select(PlayerStats)
            .where(
                PlayerStats.game_id.in_(game_ids),
                PlayerStats.stat_category == category,
                col.isnot(None),
            )
            .order_by(col.desc())
            .limit(limit)
        )
        stats = result.scalars().all()

        performers = []
        for s in stats:
            # Resolve player name
            player_result = await self.db.execute(
                select(Player).where(Player.id == s.player_id)
            )
            player = player_result.scalar_one_or_none()
            name = f"{player.first_name or ''} {player.last_name}".strip() if player else "Unknown"

            performers.append({
                "player": name,
                "yards": s.yards,
                "touchdowns": s.touchdowns,
                "attempts": s.attempts,
                "completions": s.completions,
                "carries": s.carries,
                "receptions": s.receptions,
            })

        return performers

    def _build_prompt(self, season: int, week: int, data: dict, league: str = "nfl") -> str:
        """Build a structured prompt from the gathered data."""
        league_name = "NFL" if league == "nfl" else "College Football"
        games_text = ""
        for g in data["games"]:
            games_text += (
                f"  {g['away_team']} {g['away_score']} at "
                f"{g['home_team']} {g['home_score']}"
            )
            if g["venue"]:
                games_text += f" ({g['venue']})"
            games_text += "\n"

        def format_performers(performers, category):
            if not performers:
                return "  No data available\n"
            lines = ""
            for p in performers:
                line = f"  {p['player']}: {p['yards']} yards"
                if category == "passing":
                    line += f", {p['completions']}/{p['attempts']}, {p['touchdowns']} TD"
                elif category == "rushing":
                    line += f", {p['carries']} carries, {p['touchdowns']} TD"
                elif category == "receiving":
                    line += f", {p['receptions']} rec, {p['touchdowns']} TD"
                lines += line + "\n"
            return lines

        prompt = f"""You are a sports analytics writer. Generate a weekly analytical report
for the {season} {league_name} Season, Week {week}.

Here is the data from this week's games:

SCORES:
{games_text}
TOP PASSERS:
{format_performers(data['top_passers'], 'passing')}
TOP RUSHERS:
{format_performers(data['top_rushers'], 'rushing')}
TOP RECEIVERS:
{format_performers(data['top_receivers'], 'receiving')}

Write a report with these sections:
1. **Week Overview** - Summarize the week's action, highlight the biggest games
2. **Top Performances** - Break down the standout individual performances using the stats above
3. **Key Takeaways** - 3-4 analytical observations about trends or surprises

Keep the tone analytical but engaging. Use specific numbers from the data provided.
Write in markdown format. Do not invent stats that are not in the data above."""

        return prompt

    async def generate_weekly_report(self, season: int, week: int, league: str = "nfl") -> Report:
        """Generate a weekly summary report for a given season and week."""
        league_name = "NFL" if league == "nfl" else "College Football"
        # Create the report record in "generating" state
        report = Report(
            report_type="weekly_summary",
            title=f"{season} {league_name} Season - Week {week} Summary",
            content="",
            prompt_used="",
            model=MODEL,
            status="generating",
            season=season,
            week=week,
        )
        self.db.add(report)
        await self.db.flush()

        try:
            # Step 1: Gather data from our database
            data = await self._gather_week_data(season, week, league)

            if not data["games"]:
                report.status = "failed"
                report.content = "No completed games found for this week."
                report.completed_at = datetime.now(timezone.utc)
                return report

            # Step 2: Build the prompt
            prompt = self._build_prompt(season, week, data, league)
            report.prompt_used = prompt

            # Step 3: Call Claude
            logger.info(f"Generating report for {season} Week {week}")
            message = self.client.messages.create(
                model=MODEL,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )

            # Step 4: Store the result
            report.content = message.content[0].text
            report.status = "complete"

            logger.info(f"Report generated for {season} Week {week}")

        except Exception as e:
            report.status = "failed"
            report.content = f"Generation failed: {str(e)}"
            logger.error(f"Report generation failed: {e}")

        return report