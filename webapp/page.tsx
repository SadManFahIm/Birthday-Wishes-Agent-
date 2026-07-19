"use client";
// app/page.tsx — Dashboard
import useSWR from "swr";
import { api } from "@/lib/api";
import {
  StatCard, PageHeader, SectionTitle, Button, Spinner,
} from "@/components/ui";
import { Activity, Pause, Play, Zap } from "lucide-react";
import { useState } from "react";

const GRADE_COLORS: Record<string, string> = {
  "A+": "#3fb950", A: "#58a6ff", B: "#4fc3f7",
  C:    "#d29922", D: "#f85149",
};

export default function DashboardPage() {
  const { data: health, mutate, isLoading } = useSWR(
    "/health", () => api.health.get(), { refreshInterval: 30_000 }
  );
  const [action, setAction] = useState<string | null>(null);

  async function handleAgent(type: "pause" | "resume" | "tune") {
    setAction(type);
    try {
      await api.agent[type]();
      mutate();
    } finally {
      setAction(null);
    }
  }

  const nh    = health?.network_health;
  const score = nh?.score ?? null;
  const grade = nh?.grade ?? "–";
  const color = nh ? (GRADE_COLORS[grade] ?? "#8b949e") : "var(--muted)";

  return (
    <div>
      <PageHeader
        icon="🎂"
        title="Dashboard"
        subtitle="Birthday Wishes Agent — live overview"
      >
        <div
          className="pill"
          style={
            health?.paused
              ? { background: "#1a0505", color: "var(--red)", border: "1px solid var(--red)" }
              : { background: "#051a09", color: "var(--green)", border: "1px solid var(--green)" }
          }
        >
          {health?.paused ? "⏸ Paused" : "▶ Running"}
        </div>
      </PageHeader>

      {isLoading ? (
        <Spinner />
      ) : (
        <>
          {/* Network health hero */}
          <div
            className="card mb-6 text-center"
            style={{ borderColor: `${color}44`, borderLeftWidth: 4, borderLeftColor: color }}
          >
            <div
              className="text-5xl font-bold font-mono mb-1"
              style={{ color }}
            >
              {score !== null ? score : "–"}
            </div>
            <div className="text-xs mb-2" style={{ color: "var(--muted)" }}>
              Network Health / 100
            </div>
            <div className="font-bold text-lg" style={{ color }}>
              {grade} — {nh?.grade_label ?? "No data"}
            </div>
          </div>

          {/* Quick stats */}
          <div className="grid grid-cols-3 gap-4 mb-6">
            <StatCard
              label="Status"
              value={health?.paused ? "Paused" : "Running"}
              color={health?.paused ? "var(--red)" : "var(--green)"}
            />
            <StatCard label="Version"  value={health?.version ?? "9.0.0"} />
            <StatCard label="Health Grade" value={grade} color={color} />
          </div>

          {/* Agent controls */}
          <SectionTitle>
            <Activity size={12} /> Agent Controls
          </SectionTitle>
          <div className="flex gap-3">
            <Button
              variant="danger"
              onClick={() => handleAgent("pause")}
              disabled={!!action || health?.paused}
            >
              <Pause size={14} />
              {action === "pause" ? "Pausing…" : "Pause Agent"}
            </Button>
            <Button
              variant="primary"
              onClick={() => handleAgent("resume")}
              disabled={!!action || !health?.paused}
            >
              <Play size={14} />
              {action === "resume" ? "Resuming…" : "Resume Agent"}
            </Button>
            <Button onClick={() => handleAgent("tune")} disabled={!!action}>
              <Zap size={14} />
              {action === "tune" ? "Tuning…" : "Run Tune Cycle"}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
