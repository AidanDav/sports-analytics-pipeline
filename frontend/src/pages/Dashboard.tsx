import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getTeams, getGames, getPlayers, getReports } from "../api/client";
import type { Game, Report } from "../api/types";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
// The dashboard fires four API calls in parallel with Promise.all 
// passing limit: 1 for teams and players because we only need the total count, not the rows.
export default function Dashboard() {
  const [teamCount, setTeamCount] = useState<number | null>(null);
  const [gameCount, setGameCount] = useState<number | null>(null);
  const [playerCount, setPlayerCount] = useState<number | null>(null);
  const [reportCount, setReportCount] = useState<number | null>(null);
  const [recentGames, setRecentGames] = useState<Game[]>([]);
  const [recentReports, setRecentReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [teams, games, players, reports] = await Promise.all([
          getTeams({ limit: 1 }),
          getGames({ limit: 5 }),
          getPlayers({ limit: 1 }),
          getReports({ limit: 5 }),
        ]);
        setTeamCount(teams.total);
        setGameCount(games.total);
        setPlayerCount(players.total);
        setReportCount(reports.total);
        setRecentGames(games.data);
        setRecentReports(reports.data);
      } catch (err) {
        console.error("Dashboard load failed:", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        Loading dashboard...
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Overview of your sports analytics pipeline"
      />

      {/* Summary stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard label="Teams" value={teamCount ?? 0} detail="NFL + College Football" />
        <StatCard label="Games" value={gameCount ?? 0} detail="All seasons" />
        <StatCard label="Players" value={playerCount ?? 0} detail="Active rosters" />
        <StatCard label="Reports" value={reportCount ?? 0} detail="AI-generated" />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Recent games */}
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-slate-900">Recent Games</h2>
            <Link to="/games" className="text-sm text-blue-600 hover:text-blue-700">
              View all
            </Link>
          </div>
          {recentGames.length === 0 ? (
            <p className="text-sm text-slate-400">No games ingested yet</p>
          ) : (
            <div className="space-y-3">
              {recentGames.map((game) => (
                <div key={game.id} className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
                  <div className="text-sm">
                    <span className="font-medium">{game.away_team}</span>
                    <span className="text-slate-400 mx-2">at</span>
                    <span className="font-medium">{game.home_team}</span>
                  </div>
                  <div className="text-sm text-right">
                    {game.away_score !== null && game.home_score !== null ? (
                      <span className="font-medium">
                        {game.away_score} - {game.home_score}
                      </span>
                    ) : (
                      <span className="text-slate-400">{game.status || "Scheduled"}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent reports */}
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-slate-900">Recent Reports</h2>
            <Link to="/reports" className="text-sm text-blue-600 hover:text-blue-700">
              View all
            </Link>
          </div>
          {recentReports.length === 0 ? (
            <p className="text-sm text-slate-400">No reports generated yet</p>
          ) : (
            <div className="space-y-3">
              {recentReports.map((report) => (
                <Link
                  key={report.id}
                  to={`/reports/${report.id}`}
                  className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0 hover:bg-slate-50 -mx-2 px-2 rounded transition-colors"
                >
                  <div className="text-sm font-medium">{report.title}</div>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      report.status === "complete"
                        ? "bg-green-100 text-green-700"
                        : report.status === "failed"
                        ? "bg-red-100 text-red-700"
                        : "bg-yellow-100 text-yellow-700"
                    }`}
                  >
                    {report.status}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}