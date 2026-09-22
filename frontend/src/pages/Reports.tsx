import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { getReports, generateReport, getConferences } from "../api/client";
import type { Report } from "../api/types";
import PageHeader from "../components/PageHeader";
import DataTable, { type Column } from "../components/DataTable";

const COLUMNS: Column<Report>[] = [
  {
    header: "Title",
    accessor: (r) => (
      <Link to={`/reports/${r.id}`} className="font-medium text-blue-600 hover:text-blue-700">
        {r.title}
      </Link>
    ),
  },
  {
    header: "Type",
    accessor: (r) => r.report_type.replace("_", " "),
    className: "w-36",
  },
  {
    header: "Season",
    accessor: (r) => r.season ?? "--",
    className: "w-20",
  },
  {
    header: "Week",
    accessor: (r) => r.week ?? "--",
    className: "w-20",
  },
  {
    header: "Status",
    accessor: (r) => (
      <span
        className={`text-xs px-2 py-0.5 rounded-full ${
          r.status === "complete"
            ? "bg-green-100 text-green-700"
            : r.status === "failed"
            ? "bg-red-100 text-red-700"
            : "bg-yellow-100 text-yellow-700"
        }`}
      >
        {r.status}
      </span>
    ),
    className: "w-24",
  },
];

export default function Reports() {
  const [data, setData] = useState<Report[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  // Generate form state
  const [genSeason, setGenSeason] = useState(2024);
  const [genWeek, setGenWeek] = useState(1);
  const [genLeague, setGenLeague] = useState("nfl");
  const [genConference, setGenConference] = useState("");
  const [conferences, setConferences] = useState<string[]>([]);
  const [genError, setGenError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const limit = 25;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getReports({ limit, offset });
      setData(result.data);
      setTotal(result.total);
    } catch (err) {
      console.error("Failed to load reports:", err);
    } finally {
      setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    load();
  }, [load]);

    useEffect(() => {
    getConferences()
      .then(setConferences)
      .catch((err) => console.error("Failed to load conferences:", err));
  }, []);

    async function handleGenerate() {
    setGenerating(true);
    setGenError(null);
    try {
      const report = await generateReport(
        genSeason,
        genWeek,
        genLeague,
        genConference || undefined
      );
      // A "failed" report is still a 200, e.g. no games that week.
      // Show why instead of quietly adding a red row to the table.
      if (report.status === "failed") {
        setGenError(report.content);
      } else {
        setShowForm(false);
      }
      load();
    } catch (err) {
      // 400s from the route land here with the backend's message
      setGenError(err instanceof Error ? err.message : "Report generation failed");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="AI-generated weekly analytical reports"
        action={
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            Generate Report
          </button>
        }
      />

      {/* Generate form */}
      {showForm && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 mb-6">
          <h3 className="font-medium text-slate-900 mb-3">Generate Weekly Report</h3>
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <label className="block text-xs text-slate-500 mb-1">Season</label>
              <select
                value={genSeason}
                onChange={(e) => setGenSeason(Number(e.target.value))}
                className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white"
              >
                {[2026, 2025, 2024, 2023].map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Week</label>
              <select
                value={genWeek}
                onChange={(e) => setGenWeek(Number(e.target.value))}
                className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white"
              >
                {Array.from({ length: 18 }, (_, i) => i + 1).map((w) => (
                  <option key={w} value={w}>Week {w}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">League</label>
              <select
                value={genLeague}
                onChange={(e) => {setGenLeague(e.target.value);
                  if (e.target.value !== "cfb") setGenConference("");
                }}
                className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white"
              >
                <option value="nfl">NFL</option>
                <option value="cfb">College Football</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Conference</label>
              <select
                value={genConference}
                onChange={(e) => setGenConference(e.target.value)}
                disabled={genLeague !== "cfb"}
                title={genLeague !== "cfb" ? "Select College Football to scope by conference" : undefined}
                className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white disabled:bg-slate-100 disabled:text-slate-400"
              >
                <option value="">All Games</option>
                {conferences.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <button
              onClick={handleGenerate}
              disabled={generating}
              className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {generating ? "Generating..." : "Generate"}
            </button>
          </div>
           {genError && (
            <p className="mt-3 text-sm text-red-600">{genError}</p>
          )}
        </div>
      )}

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