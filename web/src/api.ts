import type { ApiError } from "./types";

const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

export class RequestError extends Error {
  status: number;
  code: string;
  details: unknown;

  constructor(status: number, payload: ApiError) {
    super(payload.message);
    this.status = status;
    this.code = payload.code;
    this.details = payload.details;
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({
      code: "REQUEST_FAILED",
      message: "The server could not complete the request.",
      details: {},
      request_id: "",
    }))) as ApiError;
    throw new RequestError(response.status, payload);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const money = (value: string | number) =>
  new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  }).format(Number(value));

export const shortDate = (value: string) =>
  new Intl.DateTimeFormat("es-CO", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));

export const idempotencyKey = () => crypto.randomUUID();
