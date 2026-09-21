// These types mirror the Pydantic response schemas in backend/app/schemas/
// so the frontend stays in sync with the API contract.

export interface PaginatedResponse<T> {
  total: number;
  limit: number;
  offset: number;
  data: T[];
}

export interface Team {
  id: number;
  name: string;
  abbreviation: string | null;
  conference: string | null;
  league: string;
}

export interface Game {
  id: number;
  season: number;
  week: number | null;
  home_team: string;
  away_team: string;
  home_score: number | null;
  away_score: number | null;
  game_date: string | null;
  status: string | null;
  venue: string | null;
}

export interface Player {
  id: number;
  first_name: string | null;
  last_name: string;
  position: string | null;
  number: number | null;
  team_id: number | null;
  team_name: string | null;
  league: string;
}

export interface PlayerStats {
  id: number;
  player_id: number | null;
  game_id: number | null;
  stat_category: string;
  attempts: number | null;
  completions: number | null;
  yards: number | null;
  touchdowns: number | null;
  interceptions: number | null;
  receptions: number | null;
  targets: number | null;
  carries: number | null;
  fumbles: number | null;
  tackles: number | null;
  sacks: number | null;
}

export interface Report {
  id: number;
  report_type: string;
  title: string;
  content: string | null;
  status: string;
  season: number | null;
  week: number | null;
}