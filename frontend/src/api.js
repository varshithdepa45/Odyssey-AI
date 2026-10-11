const BASE = (import.meta.env.VITE_API_URL || "http://localhost:8010").replace(/\/$/, "");

const TEAM_KEY = "codehunt_team";
const ADMIN_KEY = "codehunt_admin";

function read(storage, key) {
  try {
    return JSON.parse(storage.getItem(key));
  } catch {
    return null;
  }
}

// The team session survives a closed tab; the admin session ends with the tab.
export const teamSession = {
  get: () => read(localStorage, TEAM_KEY),
  set: (value) => localStorage.setItem(TEAM_KEY, JSON.stringify(value)),
  clear: () => localStorage.removeItem(TEAM_KEY),
};
export const adminSession = {
  get: () => read(sessionStorage, ADMIN_KEY),
  set: (value) => sessionStorage.setItem(ADMIN_KEY, JSON.stringify(value)),
  clear: () => sessionStorage.removeItem(ADMIN_KEY),
};

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function describe(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg?.replace(/^Value error, /, "")).join(". ");
  return "Something went wrong";
}

async function request(path, { method = "GET", body, as } = {}) {
  const session = as === "admin" ? adminSession : as === "team" ? teamSession : null;
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (session?.get()?.token) headers.Authorization = `Bearer ${session.get().token}`;
  let response;
  try {
    response = await fetch(BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection.", 0);
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && session) {
      session.clear();
      window.dispatchEvent(new Event("codehunt-session"));
    }
    throw new ApiError(describe(data.detail), response.status);
  }
  return response;
}

export async function api(path, options) {
  return (await request(path, options)).json();
}

export async function downloadCsv(path, filename) {
  const blob = await (await request(path, { as: "admin" })).blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

export function formatElapsed(seconds) {
  if (seconds == null) return "—";
  const h = Math.floor(seconds / 3600);
  const m = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
  const s = String(seconds % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
}

/** Saves rows (arrays of cells) as a CSV file from the browser, for data that exists only in this tab. */
export function saveCsv(filename, rows) {
  const quote = (cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`;
  const blob = new Blob([rows.map((row) => row.map(quote).join(",")).join("\n")], { type: "text/csv" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}
