import { Link } from "react-router-dom";

interface TeamLinkProps {
  id: number | null;
  name: string | null;
  className?: string;
}

// A team name that links to its detail page. Falls back to plain text
// when there's no ID, e.g. an opponent missing from our teams table.
export default function TeamLink({ id, name, className = "font-medium" }: TeamLinkProps) {
  if (!name) return <span className="text-slate-400">--</span>;
  if (id === null) return <span className={className}>{name}</span>;

  return (
    <Link to={`/teams/${id}`} className={`${className} text-slate-900 hover:text-blue-600`}>
      {name}
    </Link>
  );
}