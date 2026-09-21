import { useEffect, useState, useCallback } from "react";
import { getGames } from "../api/client";
import type { Game } from "../api/types";
import PageHeader from "../components/PageHeader";
import DataTable, { type Column } from "../components/DataTable";

const COLUMNS: Column<Game>[] = [
  {
    header: "Week",
    accessor: (g) => g.week ?? "--",
    className: "w-16",
  },
  {
    header: "Matchup",
    accessor: (g) => (
      <span>
        <span className="font-medium">{g.away_team}</span>
        <span className="text-slate-400 mx-1">@</span>
        <span className="font-medium">{g.home_team}</span>
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

export default function Games() {
  const [data, setData] = useState<Game[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [season, setSeason] = useState<number>(2024);
  const [week, setWeek] = useState<number | "">("");
  const [loading, setLoading] = useState(true);

  const limit = 25;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getGames({
        season,
        week: week === "" ? undefined : week,
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
  }, [season, week, offset]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <PageHeader title="Games" subtitle={`${total} games for the ${season} season`} />

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <select
          value={season}
          onChange={(e) => { setSeason(Number(e.target.value)); setOffset(0); }}
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          {[2026, 2025, 2024, 2023].map((y) => (
            <option key={y} value={y}>{y} Season</option>
          ))}
        </select>
        <select
          value={week}
          onChange={(e) => { setWeek(e.target.value === "" ? "" : Number(e.target.value)); setOffset(0); }}
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          <option value="">All Weeks</option>
          {Array.from({ length: 18 }, (_, i) => i + 1).map((w) => (
            <option key={w} value={w}>Week {w}</option>
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