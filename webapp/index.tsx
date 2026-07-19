// components/ui/index.tsx — shared UI primitives

import { ReactNode } from "react";

// ── StatCard ──────────────────────────────────────────────────────────────────
interface StatCardProps {
  label:  string;
  value:  string | number;
  color?: string;
  delta?: string;
  deltaUp?: boolean;
}

export function StatCard({ label, value, color, delta, deltaUp }: StatCardProps) {
  return (
    <div className="card text-center">
      <div
        className="text-2xl font-bold font-mono leading-none"
        style={{ color: color ?? "var(--text)" }}
      >
        {value}
      </div>
      {delta && (
        <div
          className="text-xs mt-1"
          style={{ color: deltaUp ? "var(--green)" : "var(--red)" }}
        >
          {deltaUp ? "↑" : "↓"} {delta}
        </div>
      )}
      <div className="text-xs mt-1 uppercase tracking-widest" style={{ color: "var(--muted)" }}>
        {label}
      </div>
    </div>
  );
}

// ── Badge ─────────────────────────────────────────────────────────────────────
interface BadgeProps {
  label: string;
  color: string;
}

export function Badge({ label, color }: BadgeProps) {
  return (
    <span
      className="pill"
      style={{
        background:  `${color}22`,
        color,
        border:      `1px solid ${color}55`,
      }}
    >
      {label}
    </span>
  );
}

// ── PageHeader ────────────────────────────────────────────────────────────────
interface PageHeaderProps {
  icon:     string;
  title:    string;
  subtitle?: string;
  children?: ReactNode;
}

export function PageHeader({ icon, title, subtitle, children }: PageHeaderProps) {
  return (
    <div
      className="flex items-center gap-4 pb-5 mb-6 border-b"
      style={{ borderColor: "var(--border)" }}
    >
      <span className="text-3xl">{icon}</span>
      <div className="flex-1">
        <h1 className="text-xl font-bold tracking-tight">{title}</h1>
        {subtitle && (
          <p className="text-sm mt-0.5" style={{ color: "var(--muted)" }}>
            {subtitle}
          </p>
        )}
      </div>
      {children}
    </div>
  );
}

// ── SectionTitle ──────────────────────────────────────────────────────────────
export function SectionTitle({ children }: { children: ReactNode }) {
  return <div className="section-title">{children}</div>;
}

// ── BarRow ────────────────────────────────────────────────────────────────────
interface BarRowProps {
  label:  string;
  value:  number;
  max:    number;
  color:  string;
  suffix?: string;
}

export function BarRow({ label, value, max, color, suffix = "" }: BarRowProps) {
  const pct = Math.min(100, max ? (value / max) * 100 : 0);
  return (
    <div className="flex items-center gap-3 mb-2">
      <div className="w-28 text-sm shrink-0" style={{ color: "var(--text)" }}>
        {label}
      </div>
      <div
        className="flex-1 rounded overflow-hidden"
        style={{ background: "#0d1117", height: 20 }}
      >
        <div
          className="h-full rounded flex items-center justify-end pr-2 text-xs font-bold"
          style={{ width: `${pct}%`, background: color, color: "#0d1117", minWidth: 4 }}
        >
          {pct > 20 ? `${value}${suffix}` : ""}
        </div>
      </div>
      <div className="w-12 text-right text-xs font-mono" style={{ color: "var(--muted)" }}>
        {value}{suffix}
      </div>
    </div>
  );
}

// ── Button ────────────────────────────────────────────────────────────────────
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "default" | "danger";
  size?:    "sm" | "md";
  children: ReactNode;
}

export function Button({
  variant = "default", size = "md", children, className = "", style, ...rest
}: ButtonProps) {
  const base = "inline-flex items-center gap-2 font-medium rounded-lg transition-colors";
  const sz   = size === "sm" ? "px-3 py-1.5 text-xs" : "px-4 py-2 text-sm";
  const vars: Record<string, React.CSSProperties> = {
    primary: {
      background: "var(--accent)", color: "#fff", border: "1px solid var(--accent)",
    },
    default: {
      background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)",
    },
    danger: {
      background: "#1a0505", color: "var(--red)", border: "1px solid var(--red)",
    },
  };
  return (
    <button
      className={`${base} ${sz} ${className}`}
      style={{ ...vars[variant], ...style }}
      {...rest}
    >
      {children}
    </button>
  );
}

// ── Spinner ───────────────────────────────────────────────────────────────────
export function Spinner() {
  return (
    <div className="flex items-center justify-center py-12">
      <div
        className="w-8 h-8 rounded-full border-2 animate-spin"
        style={{ borderColor: "var(--border)", borderTopColor: "var(--accent)" }}
      />
    </div>
  );
}

// ── EmptyState ────────────────────────────────────────────────────────────────
export function EmptyState({ message }: { message: string }) {
  return (
    <div className="text-center py-12" style={{ color: "var(--muted)" }}>
      <div className="text-4xl mb-3">🎂</div>
      <div className="text-sm">{message}</div>
    </div>
  );
}
