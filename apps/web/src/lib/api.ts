/**
 * Thin fetch wrapper around the FastAPI backend.
 *
 * Server components call the backend directly; client components hit
 * the same URL. In production, the dashboard is served from the same
 * Traefik host as the API, so relative URLs would also work — we use
 * an absolute one so the dev experience matches without a proxy.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  payload: unknown;
  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit & { token?: string } = {},
): Promise<T> {
  const { token, ...rest } = init;
  const res = await fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(rest.headers ?? {}),
    },
    cache: "no-store",
  });
  const text = await res.text();
  const data: unknown = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail =
      typeof data === "object" && data && "detail" in data
        ? String((data as { detail?: unknown }).detail ?? "")
        : res.statusText;
    throw new ApiError(detail || `HTTP ${res.status}`, res.status, data);
  }
  return data as T;
}

export const apiBaseUrl = BASE_URL;
