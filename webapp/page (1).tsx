"use client";
// app/queue/page.tsx
import useSWR from "swr";
import { api } from "@/lib/api";
import {
  PageHeader, SectionTitle, Button, Spinner, EmptyState, Badge,
} from "@/components/ui";
import { CheckCircle, XCircle, Clock } from "lucide-react";
import { useState } from "react";
import type { QueueItem } from "@/types";

const PLATFORM_COLORS: Record<string, string> = {
  LinkedIn: "#58a6ff", WhatsApp: "#3fb950", Slack: "#4fc3f7",
  Facebook: "#bc8cff", Instagram: "#f78166",
};

export default function QueuePage() {
  const { data, mutate, isLoading } = useSWR(
    "/queue/pending", () => api.queue.list("pending")
  );
  const [acting, setActing] = useState<number | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [editText, setEditText] = useState("");

  const items: QueueItem[] = data?.items ?? [];

  async function approve(id: number, edited?: string) {
    setActing(id);
    await api.queue.approve(id, edited ? { edited_text: edited } : undefined);
    mutate();
    setActing(null);
    setEditId(null);
  }

  async function reject(id: number) {
    setActing(id);
    await api.queue.reject(id);
    mutate();
    setActing(null);
  }

  return (
    <div>
      <PageHeader
        icon="📥"
        title="Wish Queue"
        subtitle={`${data?.total ?? 0} wishes pending review`}
      />

      <SectionTitle>
        <Clock size={12} /> Pending Approval
      </SectionTitle>

      {isLoading ? (
        <Spinner />
      ) : items.length === 0 ? (
        <EmptyState message="Queue is empty — all wishes approved or rejected." />
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const pColor = PLATFORM_COLORS[item.platform] ?? "#8b949e";
            const isEditing = editId === item.id;
            return (
              <div key={item.id} className="card">
                {/* Header */}
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <div className="font-bold">{item.contact_name}</div>
                    <div className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
                      {item.created_at?.slice(0, 16).replace("T", " ")}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {item.personalization_score !== null && (
                      <Badge
                        label={`Score ${item.personalization_score}/10`}
                        color={item.personalization_score >= 7 ? "var(--green)" : "var(--yellow)"}
                      />
                    )}
                    <Badge label={item.platform} color={pColor} />
                  </div>
                </div>

                {/* Wish text */}
                {isEditing ? (
                  <textarea
                    className="w-full rounded-lg p-3 text-sm resize-none mb-3"
                    style={{
                      background: "#010409", border: "1px solid var(--border)",
                      color: "#7ee787", height: 100,
                    }}
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                  />
                ) : (
                  <div
                    className="rounded-lg p-3 text-sm mb-3 font-mono"
                    style={{ background: "#010409", color: "#c9d1d9" }}
                  >
                    {item.wish_text}
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2">
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={acting === item.id}
                    onClick={() =>
                      isEditing
                        ? approve(item.id, editText)
                        : approve(item.id)
                    }
                  >
                    <CheckCircle size={13} />
                    {isEditing ? "Save & Approve" : "Approve"}
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    disabled={acting === item.id}
                    onClick={() => reject(item.id)}
                  >
                    <XCircle size={13} /> Reject
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => {
                      if (isEditing) { setEditId(null); return; }
                      setEditId(item.id);
                      setEditText(item.wish_text);
                    }}
                  >
                    {isEditing ? "Cancel" : "✏️ Edit"}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
