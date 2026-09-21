import { useEffect, useState, useCallback } from "react";
import { getTeams } from "../api/client";
import type { Team } from "../api/types";
import PageHeader from "../components/PageHeader";
import DataTable, { type Column } from "../components/DataTable";

const COLUMNS: Column<Team>[] = [
  { header: "Name", accessor: (t) => <span className="font-medium">{t.name}</span> },
  { header: "Abbreviation", accessor: (t) => t.abbreviation || "--" },
  { header: "Conference", accessor: (t) => t.conference || "--" },
  {
    header: "League",
    accessor: (t) => (
      <span
        className={`text-xs px-2 py-0.5 rounded-full ${
          t.league === "nfl"
            ? "bg-blue-100 text-blue-700"
            : "bg-amber-100 text-amber-700"
        }`}
      >
        {t.league.toUpperCase()}
      </span>
    ),
  },
];

export default function Teams() {
  const [data, setData] = useState<Team[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [conference, setConference] = useState("");
  const [loading, setLoading] = useState(true);

  const limit = 25;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getTeams({ search, conference, limit, offset });
      setData(result.data);
      setTotal(result.total);
    } catch (err) {
      console.error("Failed to load teams:", err);
    } finally {
      setLoading(false);
    }
  }, [search, conference, offset]);

  useEffect(() => {
    load();
  }, [load]);

  // Reset to first page when filters change
  function handleSearch(value: string) {
    setSearch(value);
    setOffset(0);
  }

  function handleConference(value: string) {
    setConference(value);
    setOffset(0);
  }

  return (
    <div>
      <PageHeader title="Teams" subtitle={`${total} teams across NFL and college football`} />

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <input
          type="text"
          placeholder="Search teams..."
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent w-64"
        />
        <select
          value={conference}
          onChange={(e) => handleConference(e.target.value)}
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          <option value="">All Conferences</option>
          <option value="SEC">SEC</option>
          <option value="Big Ten">Big Ten</option>
          <option value="Big 12">Big 12</option>
          <option value="ACC">ACC</option>
          <option value="Pac-12">Pac-12</option>
          <option value="AFC">AFC</option>
          <option value="NFC">NFC</option>
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