import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import Markdown from "react-markdown";
import { getReport } from "../api/client";
import type { Report } from "../api/types";

export default function ReportDetail() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      if (!id) return;
      try {
        const data = await getReport(Number(id));
        setReport(data);
      } catch (err) {
        setError("Failed to load report");
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        Loading report...
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="text-center py-16">
        <p className="text-slate-500 mb-4">{error || "Report not found"}</p>
        <Link to="/reports" className="text-blue-600 hover:text-blue-700 text-sm">
          Back to reports
        </Link>
      </div>
    );
  }

  return (
    <div>
      {/* Back link */}
      <Link to="/reports" className="text-sm text-slate-500 hover:text-slate-700 mb-4 inline-block">
        ← Back to reports
      </Link>

      {/* Report header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{report.title}</h1>
          <div className="flex items-center gap-3 mt-2">
            {report.season && (
              <span className="text-sm text-slate-500">{report.season} Season</span>
            )}
            {report.week && (
              <span className="text-sm text-slate-500">Week {report.week}</span>
            )}
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
          </div>
        </div>
      </div>

      {/* Report body */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 lg:p-8">
        {report.content ? (
          <div className="report-content max-w-none">
            <Markdown>{report.content}</Markdown>
          </div>
        ) : (
          <p className="text-slate-400">No content available</p>
        )}
      </div>
    </div>
  );
}