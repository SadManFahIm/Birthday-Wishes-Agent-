// lib/api.ts — typed API client for FastAPI backend

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json() as Promise<T>;
}

// ── Health ─────────────────────────────────────────────────────────────────
export const api = {
  health: {
    get:    ()         => req<import("@/types").HealthStatus>("/api/v1/health"),
  },

  // ── Contacts ──────────────────────────────────────────────────────────────
  contacts: {
    list:   (tier?: string) =>
      req<{ contacts: import("@/types").Contact[]; total: number }>(
        `/api/v1/contacts${tier ? `?tier=${tier}` : ""}`),
    upsert: (body: object) =>
      req("/api/v1/contacts", { method: "POST", body: JSON.stringify(body) }),
  },

  // ── Queue ─────────────────────────────────────────────────────────────────
  queue: {
    list:    (status = "pending") =>
      req<{ items: import("@/types").QueueItem[]; total: number }>(
        `/api/v1/queue?status=${status}`),
    approve: (id: number, body?: object) =>
      req(`/api/v1/queue/${id}/approve`,
          { method: "POST", body: JSON.stringify(body ?? {}) }),
    reject:  (id: number) =>
      req(`/api/v1/queue/${id}/reject`, { method: "POST", body: "{}" }),
  },

  // ── Wish ──────────────────────────────────────────────────────────────────
  wish: {
    generate: (body: object) =>
      req<import("@/types").WishGenerateResponse>(
        "/api/v1/wish/generate", { method: "POST", body: JSON.stringify(body) }),
    send: (body: object) =>
      req("/api/v1/wish/send", { method: "POST", body: JSON.stringify(body) }),
  },

  // ── Analytics ─────────────────────────────────────────────────────────────
  analytics: {
    platformROI:  (days = 30)  =>
      req<import("@/types").PlatformROI>(
        `/api/v1/analytics/platform-roi?period_days=${days}`),
    sentiment:    ()           => req("/api/v1/analytics/sentiment"),
    scoreTrend:   (days = 90)  =>
      req(`/api/v1/analytics/score-trend?period_days=${days}`),
  },

  // ── VIP ───────────────────────────────────────────────────────────────────
  vip: {
    list:   () =>
      req<{ vip_contacts: import("@/types").VIPContact[] }>("/api/v1/vip"),
    flag:   (id: string, body: object) =>
      req(`/api/v1/vip/${id}`, { method: "POST", body: JSON.stringify(body) }),
    unflag: (id: string) =>
      req(`/api/v1/vip/${id}`, { method: "DELETE" }),
  },

  // ── Revenue ───────────────────────────────────────────────────────────────
  revenue: {
    summary: (days = 365) =>
      req<import("@/types").RevenueSummary>(`/api/v1/revenue?days=${days}`),
    log:     (body: object) =>
      req("/api/v1/revenue", { method: "POST", body: JSON.stringify(body) }),
  },

  // ── Agent control ──────────────────────────────────────────────────────────
  agent: {
    pause:  () => req("/api/v1/agent/pause",  { method: "POST", body: "{}" }),
    resume: () => req("/api/v1/agent/resume", { method: "POST", body: "{}" }),
    tune:   () => req("/api/v1/agent/tune",   { method: "POST", body: "{}" }),
  },
};
