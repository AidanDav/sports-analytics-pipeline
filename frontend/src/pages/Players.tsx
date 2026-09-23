import { useEffect, useState, useCallback } from "react";
import { getPlayers } from "../api/client";
import type { Player } from "../api/types";
import PageHeader from "../components/PageHeader";
import DataTable, { type Column } from "../components/DataTable";
import TeamLink from "../components/TeamLink";

const COLUMNS: Column<Player>[] = [
  {
    header: "Name",
    accessor: (p) => (
      <span className="font-medium">
        {p.first_name ? `${p.first_name} ` : ""}
        {p.last_name}
      </span>
    ),
  },
  {
    header: "Position",
    accessor: (p) => p.position || "--",
    className: "w-24",
  },
  {
    header: "#",
    accessor: (p) => p.number ?? "--",
    className: "w-16",
  },
  {
    header: "Team",
    accessor: (p) => <TeamLink id={p.team_id} name={p.team_name} className="" />,
  },
  {
    header: "League",
    accessor: (p) => (
      <span
        className={`text-xs px-2 py-0.5 rounded-full ${
          p.league === "nfl"
            ? "bg-blue-100 text-blue-700"
            : "bg-amber-100 text-amber-700"
        }`}
      >
        {p.league.toUpperCase()}
      </span>
    ),
    className: "w-24",
  },
];

export default function Players() {
  const [data, setData] = useState<Player[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [position, setPosition] = useState("");
  const [league, setLeague] = useState("");
  const [loading, setLoading] = useState(true);

  const limit = 25;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getPlayers({ search, position, league, limit, offset });
      setData(result.data);
      setTotal(result.total);
    } catch (err) {
      console.error("Failed to load players:", err);
    } finally {
      setLoading(false);
    }
  }, [search, position, league, offset]);

  useEffect(() => {
    load();
  }, [load]);

  function resetPage(setter: (v: string) => void, value: string) {
    setter(value);
    setOffset(0);
  }

  return (
    <div>
      <PageHeader title="Players" subtitle={`${total} players in the database`} />

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <input
          type="text"
          placeholder="Search by name..."
          value={search}
          onChange={(e) => resetPage(setSearch, e.target.value)}
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent w-64"
        />
        <select
          value={position}
          onChange={(e) => resetPage(setPosition, e.target.value)}
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          <option value="">All Positions</option>
          <option value="QB">QB</option>
          <option value="RB">RB</option>
          <option value="WR">WR</option>
          <option value="DEF">DEF</option>
          <option value="K">K</option>
        </select>
        <select
          value={league}
          onChange={(e) => resetPage(setLeague, e.target.value)}
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          <option value="">All Leagues</option>
          <option value="nfl">NFL</option>
          <option value="cfb">College Football</option>
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