// Centralized API client. Every backend call goes through here so
// base URL logic, error handling, and query param building live in
// one place instead of scattered across components.

import type {
  PaginatedResponse,
  Team,
  Game,
  Player,
  PlayerStats,
  Report,
} from "./types";

// In dev, Vite proxies /api -> backend:8000 (see vite.config.ts).
// In production, the env var points to the real API URL.
const BASE = import.meta.env.VITE_API_URL || "/api";

async function fetchJSON<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${BASE}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") {
        url.searchParams.set(key, value);
      }
    });
  }

  const response = await fetch(url.toString());
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

// --- Teams ---

export function getTeams(params?: {
  conference?: string;
  search?: string;
  limit?: number;
  offset?: number;
}) {
  return fetchJSON<PaginatedResponse<Team>>("/teams", {
    conference: params?.conference || "",
    search: params?.search || "",
    limit: String(params?.limit ?? 25),
    offset: String(params?.offset ?? 0),
  });
}

export function getTeam(id: number) {
  return fetchJSON<Team>(`/teams/${id}`);
}

// --- Games ---

export function getGames(params?: {
  season?: number;
  week?: number;
  team_id?: number;
  limit?: number;
  offset?: number;
}) {
  return fetchJSON<PaginatedResponse<Game>>("/games", {
    season: params?.season ? String(params.season) : "",
    week: params?.week ? String(params.week) : "",
    team_id: params?.team_id ? String(params.team_id) : "",
    limit: String(params?.limit ?? 25),
    offset: String(params?.offset ?? 0),
  });
}

// --- Players ---

export function getPlayers(params?: {
  team_id?: number;
  position?: string;
  search?: string;
  league?: string;
  limit?: number;
  offset?: number;
}) {
  return fetchJSON<PaginatedResponse<Player>>("/players", {
    team_id: params?.team_id ? String(params.team_id) : "",
    position: params?.position || "",
    search: params?.search || "",
    league: params?.league || "",
    limit: String(params?.limit ?? 25),
    offset: String(params?.offset ?? 0),
  });
}

export function getPlayer(id: number) {
  return fetchJSON<Player>(`/players/${id}`);
}

// --- Player Stats ---

export function getPlayerStats(
  playerId: number,
  params?: {
    stat_category?: string;
    game_id?: number;
    limit?: number;
    offset?: number;
  }
) {
  return fetchJSON<PaginatedResponse<PlayerStats>>(
    `/players/${playerId}/stats`,
    {
      stat_category: params?.stat_category || "",
      game_id: params?.game_id ? String(params.game_id) : "",
      limit: String(params?.limit ?? 25),
      offset: String(params?.offset ?? 0),
    }
  );
}

// --- Reports ---

export function getReports(params?: {
  report_type?: string;
  season?: number;
  limit?: number;
  offset?: number;
}) {
  return fetchJSON<PaginatedResponse<Report>>("/reports", {
    report_type: params?.report_type || "",
    season: params?.season ? String(params.season) : "",
    limit: String(params?.limit ?? 25),
    offset: String(params?.offset ?? 0),
  });
}

export function getReport(id: number) {
  return fetchJSON<Report>(`/reports/${id}`);
}

// --- Report Generation (POST) ---

export async function generateReport(
  season: number,
  week: number,
  league = "nfl"
): Promise<Report> {
  const url = `${BASE}/reports/generate/weekly?season=${season}&week=${week}&league=${league}`;
  const response = await fetch(url, { method: "POST" });
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}