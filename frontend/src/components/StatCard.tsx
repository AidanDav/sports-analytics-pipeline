interface StatCardProps {
  label: string;
  value: string | number;
  detail?: string;
}
// Used on the Dashboard page to show the four summary numbers (teams, games, players, reports)
export default function StatCard({ label, value, detail }: StatCardProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <p className="text-sm text-slate-500 mb-1">{label}</p>
      <p className="text-2xl font-semibold text-slate-900">{value}</p>
      {detail && (
        <p className="text-xs text-slate-400 mt-1">{detail}</p>
      )}
    </div>
  );
}