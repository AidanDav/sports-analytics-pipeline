// Drill-down for one game: a team's player stat lines grouped by category.
// Fetches on mount, so it only costs a request when a row is expanded.

import { useEffect, useState, type ReactNode } from "react";
import { getGameStats } from "../api/client";
import type { GameStatLine } from "../api/types";

interface StatColumn {
  header: string;
  value: (s: GameStatLine) => ReactNode;
}

const show = (v: number | null) => v ?? "--";

const YDS: StatColumn = { header: "YDS", value: (s) => show(s.yards) };
const TD: StatColumn = { header: "TD", value: (s) => show(s.touchdowns) };

// Each category only has a few meaningful columns, so a single wide
// table with every stat would be mostly "--"
const COLUMNS: Record<string, StatColumn[]> = {
  passing: [
    { header: "C/ATT", value: (s) => `${show(s.completions)}/${show(s.attempts)}` },
    YDS,
    TD,
    { header: "INT", value: (s) => show(s.interceptions) },
  ],
  rushing: [{ header: "CAR", value: (s) => show(s.carries) }, YDS, TD],
  receiving: [
    { header: "REC", value: (s) => show(s.receptions) },
    { header: "TGT", value: (s) => show(s.targets) },
    YDS,
    TD,
  ],
  defense: [
    { header: "TCKL", value: (s) => show(s.tackles) },
    { header: "SACKS", value: (s) => show(s.sacks) },
  ],
};
const DEFAULT_COLUMNS = [YDS, TD];

interface BoxScoreProps {
  gameId: number;
  teamId: number;
}

export default function BoxScore({ gameId, teamId }: BoxScoreProps) {
  const [lines, setLines] = useState<GameStatLine[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    // Ignore a response that arrives after the row was collapsed
    let cancelled = false;
    getGameStats(gameId, teamId)
      .then((data) => !cancelled && setLines(data))
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, [gameId, teamId]);

  if (error) {
    return <p className="text-sm text-red-600">Couldn't load the box score.</p>;
  }
  if (lines === null) {
    return <p className="text-sm text-slate-400">Loading box score...</p>;
  }
  if (lines.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        No box score for this game yet. Stats are pulled a few hours after
        games finish, and some FCS games have no box score available.
      </p>
    );
  }

  // The backend already sorts by category, and Map keeps insertion
  // order, so the groups come out passing, rushing, receiving, defense
  const groups = new Map<string, GameStatLine[]>();
  for (const line of lines) {
    const group = groups.get(line.stat_category) ?? [];
    group.push(line);
    groups.set(line.stat_category, group);
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {[...groups].map(([category, rows]) => {
        const columns = COLUMNS[category] ?? DEFAULT_COLUMNS;
        return (
          <div key={category} className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
            <h3 className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500 border-b border-slate-200">
              {category}
            </h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500">
                  <th className="px-3 py-2 text-left font-medium">Player</th>
                  {columns.map((c) => (
                    <th key={c.header} className="px-3 py-2 text-right font-medium">
                      {c.header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.id} className="border-t border-slate-100">
                    <td className="px-3 py-2 whitespace-nowrap">
                      {s.player_name}
                      {s.position && (
                        <span className="ml-1.5 text-xs text-slate-400">{s.position}</span>
                      )}
                    </td>
                    {columns.map((c) => (
                      <td key={c.header} className="px-3 py-2 text-right tabular-nums">
                        {c.value(s)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}