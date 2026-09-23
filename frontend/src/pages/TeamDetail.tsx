import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getGames, getTeam } from "../api/client";
import type { Game, Team } from "../api/types";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import BoxScore from "../components/BoxScore";

// One game seen from this team's side
interface ScheduleRow {
  game: Game;
  isHome: boolean;
  opponent: string;
  opponentId: number | null;
  teamScore: number | null;
  oppScore: number | null;
  result: "W" | "L" | "T" | null;
}

function toRow(game: Game, teamId: number): ScheduleRow {
  const isHome = game.home_team_id === teamId;
  const teamScore = isHome ? game.home_score : game.away_score;
  const oppScore = isHome ? game.away_score : game.home_score;

  // Only final games get a result, so a scheduled game never shows as a tie
  let result: ScheduleRow["result"] = null;
  if (game.status === "final" && teamScore !== null && oppScore !== null) {
    result = teamScore > oppScore ? "W" : teamScore < oppScore ? "L" : "T";
  }

  return {
    game,
    isHome,
    opponent: isHome ? game.away_team : game.home_team,
    opponentId: isHome ? game.away_team_id : game.home_team_id,
    teamScore,
    oppScore,
    result,
  };
}

const RESULT_STYLES = {
  W: "bg-green-100 text-green-700",
  L: "bg-red-100 text-red-700",
  T: "bg-slate-100 text-slate-600",
};

function formatDate(date: string | null) {
  if (!date) return "--";
  // Parse as local midnight. new Date("2024-09-05") is UTC midnight,
  // which shows as Sep 4 anywhere west of Greenwich.
  return new Date(`${date}T00:00:00`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

export default function TeamDetail() {
  const { id } = useParams();
  const teamId = Number(id);

  const [team, setTeam] = useState<Team | null>(null);
  const [games, setGames] = useState<Game[]>([]);
  const [season, setSeason] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Clicking an opponent link reuses this component with a new id,
    // so everything from the previous team has to be cleared
    setLoading(true);
    setError(null);
    setSeason(null);
    setExpandedId(null);

    let cancelled = false;
    async function load() {
      try {
        // Games come back newest season first, so the limit drops the
        // oldest seasons rather than the end of the current one
        const [t, g] = await Promise.all([
          getTeam(teamId),
          getGames({ team_id: teamId, limit: 100 }),
        ]);
        if (cancelled) return;
        setTeam(t);
        setGames(g.data);
        setSeason(g.data[0]?.season ?? null);
      } catch (err) {
        console.error("Team load failed:", err);
        if (!cancelled) setError("Couldn't load this team.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [teamId]);

  const seasons = useMemo(
    () => [...new Set(games.map((g) => g.season))],
    [games]
  );

  const rows = useMemo(
    () => games.filter((g) => g.season === season).map((g) => toRow(g, teamId)),
    [games, season, teamId]
  );

  const summary = useMemo(() => {
    const played = rows.filter((r) => r.result !== null);
    const count = (r: ScheduleRow["result"]) => played.filter((p) => p.result === r).length;
    const pointsFor = played.reduce((sum, r) => sum + (r.teamScore ?? 0), 0);
    const pointsAgainst = played.reduce((sum, r) => sum + (r.oppScore ?? 0), 0);
    const ties = count("T");
    return {
      games: played.length,
      record: `${count("W")}-${count("L")}${ties ? `-${ties}` : ""}`,
      pointsFor,
      pointsAgainst,
      avg: (n: number) => (played.length ? (n / played.length).toFixed(1) : "0.0"),
    };
  }, [rows]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        Loading team...
      </div>
    );
  }

  if (error || !team) {
    return (
      <div className="text-center py-16">
        <p className="text-slate-600 mb-4">{error ?? "Team not found."}</p>
        <Link to="/teams" className="text-sm text-blue-600 hover:text-blue-700">
          Back to Teams
        </Link>
      </div>
    );
  }

  const leagueLabel = team.league === "nfl" ? "NFL" : "College Football";

  return (
    <div>
      <Link to="/teams" className="text-sm text-slate-500 hover:text-slate-700">
        ← Teams
      </Link>

      <div className="mt-2">
        <PageHeader
          title={team.name}
          subtitle={team.conference ? `${leagueLabel} · ${team.conference}` : leagueLabel}
          action={
            seasons.length > 1 && (
              <select
                value={season ?? ""}
                onChange={(e) => {
                  setSeason(Number(e.target.value));
                  setExpandedId(null);
                }}
                className="border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
              >
                {seasons.map((s) => (
                  <option key={s} value={s}>
                    {s} season
                  </option>
                ))}
              </select>
            )
          }
        />
      </div>

      {games.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-500">
          No games found for this team.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
            <StatCard
              label="Record"
              value={summary.record}
              detail={`${summary.games} games played`}
            />
            <StatCard
              label="Points scored"
              value={summary.pointsFor}
              detail={`${summary.avg(summary.pointsFor)} per game`}
            />
            <StatCard
              label="Points allowed"
              value={summary.pointsAgainst}
              detail={`${summary.avg(summary.pointsAgainst)} per game`}
            />
          </div>

          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <h2 className="px-5 py-4 font-semibold text-slate-900 border-b border-slate-200">
              {season} Schedule
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-slate-600">
                    <th className="px-4 py-3 text-left font-medium w-14">Wk</th>
                    <th className="px-4 py-3 text-left font-medium w-24">Date</th>
                    <th className="px-4 py-3 text-left font-medium">Opponent</th>
                    <th className="px-4 py-3 text-left font-medium">Result</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const expanded = expandedId === row.game.id;
                    return (
                      <Fragment key={row.game.id}>
                        <tr className="border-b border-slate-100">
                          <td className="px-4 py-3 text-slate-500">{row.game.week ?? "--"}</td>
                          <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                            {formatDate(row.game.game_date)}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <span className="text-slate-400 mr-1.5">{row.isHome ? "vs" : "@"}</span>
                            {row.opponentId ? (
                              <Link
                                to={`/teams/${row.opponentId}`}
                                className="font-medium text-slate-900 hover:text-blue-600"
                              >
                                {row.opponent}
                              </Link>
                            ) : (
                              <span className="font-medium">{row.opponent}</span>
                            )}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            {row.result ? (
                              <>
                                <span
                                  className={`text-xs font-semibold px-2 py-0.5 rounded-full mr-2 ${RESULT_STYLES[row.result]}`}
                                >
                                  {row.result}
                                </span>
                                <span className="tabular-nums">
                                  {row.teamScore}-{row.oppScore}
                                </span>
                              </>
                            ) : (
                              <span className="text-slate-400 capitalize">
                                {row.game.status ?? "scheduled"}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right">
                            {row.result && (
                              <button
                                onClick={() => setExpandedId(expanded ? null : row.game.id)}
                                className="text-sm text-blue-600 hover:text-blue-700 whitespace-nowrap"
                              >
                                {expanded ? "Hide" : "Box score"}
                              </button>
                            )}
                          </td>
                        </tr>
                        {expanded && (
                          <tr className="border-b border-slate-100">
                            <td colSpan={5} className="bg-slate-50 px-4 py-4">
                              <BoxScore gameId={row.game.id} teamId={teamId} />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}