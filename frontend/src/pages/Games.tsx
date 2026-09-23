import { useEffect, useState, useCallback } from "react";
import { getGames, getConferences } from "../api/client";
import type { Game } from "../api/types";
import PageHeader from "../components/PageHeader";
import DataTable, { type Column } from "../components/DataTable";
import TeamLink from "../components/TeamLink";

const COLUMNS: Column<Game>[] = [
  {
    header: "Week",
    accessor: (g) => g.week ?? "--",
    className: "w-16",
  },
  {
    header: "Matchup",
    accessor: (g) => (
      <span className="whitespace-nowrap">
        <TeamLink id={g.away_team_id} name={g.away_team} />
        <span className="text-slate-400 mx-1">@</span>
        <TeamLink id={g.home_team_id} name={g.home_team} />
      </span>
    ),
  },
  {
    header: "Score",
    accessor: (g) =>
      g.away_score !== null && g.home_score !== null ? (
        <span className="font-medium tabular-nums">
          {g.away_score} - {g.home_score}
        </span>
      ) : (
        <span className="text-slate-400">{g.status || "TBD"}</span>
      ),
    className: "w-24",
  },
  {
    header: "Date",
    accessor: (g) => g.game_date || "--",
    className: "w-28",
  },
  {
    header: "Venue",
    accessor: (g) => g.venue || "--",
  },
];

const SELECT_CLASS =
  "px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white disabled:bg-slate-100 disabled:text-slate-400";

export default function Games() {
  const [data, setData] = useState<Game[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [season, setSeason] = useState<number>(2024);
  const [week, setWeek] = useState<number | "">("");
  const [league, setLeague] = useState("");
  const [conference, setConference] = useState("");
  const [conferences, setConferences] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const limit = 25;

  // Conference options come from the backend once on mount, so the
  // dropdown always matches what the filter actually accepts
  useEffect(() => {
    getConferences()
      .then(setConferences)
      .catch((err) => console.error("Failed to load conferences:", err));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getGames({
        season,
        week: week === "" ? undefined : week,
        league: league || undefined,
        conference: conference || undefined,
        limit,
        offset,
      });
      setData(result.data);
      setTotal(result.total);
    } catch (err) {
      console.error("Failed to load games:", err);
    } finally {
      setLoading(false);
    }
  }, [season, week, league, conference, offset]);

  useEffect(() => {
    load();
  }, [load]);

  function handleLeague(value: string) {
    setLeague(value);
    // Conferences only exist for CFB. Clear it so a leftover "SEC"
    // doesn't silently filter NFL down to zero games.
    if (value !== "cfb") setConference("");
    setOffset(0);
  }

  // "2024 season", "2024 SEC season", "2024 NFL season"
  const scopeLabel = conference || (league === "nfl" ? "NFL" : league === "cfb" ? "CFB" : "");
  const subtitle = `${total} games for the ${season}${scopeLabel ? ` ${scopeLabel}` : ""} season`;

  return (
    <div>
      <PageHeader title="Games" subtitle={subtitle} />

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <select
          value={season}
          onChange={(e) => { setSeason(Number(e.target.value)); setOffset(0); }}
          className={SELECT_CLASS}
        >
          {[2026, 2025, 2024, 2023].map((y) => (
            <option key={y} value={y}>{y} Season</option>
          ))}
        </select>

        <select
          value={week}
          onChange={(e) => {
            setWeek(e.target.value === "" ? "" : Number(e.target.value));
            setOffset(0);
          }}
          className={SELECT_CLASS}
        >
          <option value="">All Weeks</option>
          {Array.from({ length: 18 }, (_, i) => i + 1).map((w) => (
            <option key={w} value={w}>Week {w}</option>
          ))}
        </select>

        <select
          value={league}
          onChange={(e) => handleLeague(e.target.value)}
          className={SELECT_CLASS}
        >
          <option value="">All Leagues</option>
          <option value="nfl">NFL</option>
          <option value="cfb">College Football</option>
        </select>

        <select
          value={conference}
          onChange={(e) => { setConference(e.target.value); setOffset(0); }}
          disabled={league !== "cfb"}
          title={league !== "cfb" ? "Select College Football to filter by conference" : undefined}
          className={SELECT_CLASS}
        >
          <option value="">All Conferences</option>
          {conferences.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      <DataTable
        columns={COLUMNS}
        data={data}
        total={total}
        limit={limit}
        offset={offset}
        onPageChange={setOffset}
        loading={loading}
      />
    </div>
  );
}