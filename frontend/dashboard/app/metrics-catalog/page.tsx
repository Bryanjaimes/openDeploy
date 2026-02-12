"use client";

import { useEffect, useState } from "react";
import {
  fetchMetricsCatalog,
  type MetricDef,
  type MetricsCatalogResponse,
} from "@/lib/api";

/* ── tiny helpers ────────────────────────────────────────────── */

const TYPE_META: Record<string, { label: string; color: string; emoji: string }> = {
  llm:        { label: "LLM",        color: "#8b5cf6", emoji: "🧠" },
  vision:     { label: "Vision",     color: "#3b82f6", emoji: "👁️" },
  audio:      { label: "Audio",      color: "#f59e0b", emoji: "🔊" },
  video:      { label: "Video",      color: "#ef4444", emoji: "🎬" },
  multimodal: { label: "Multimodal", color: "#06b6d4", emoji: "🔀" },
  embeddings: { label: "Embeddings", color: "#10b981", emoji: "📐" },
  agentic:    { label: "Agentic",    color: "#ec4899", emoji: "🤖" },
  other:      { label: "Other",      color: "#6b7280", emoji: "📦" },
};

function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold"
      style={{ background: color + "18", color, border: `1px solid ${color}30` }}
    >
      {text}
    </span>
  );
}

function DirectionIcon({ up }: { up: boolean }) {
  return (
    <span
      className="inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold"
      style={{
        background: up ? "#10b98122" : "#ef444422",
        color: up ? "#10b981" : "#ef4444",
      }}
    >
      {up ? "↑" : "↓"}
    </span>
  );
}

/* ── main page ──────────────────────────────────────────────── */

export default function MetricsCatalogPage() {
  const [data, setData] = useState<MetricsCatalogResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [expandedCat, setExpandedCat] = useState<string | null>(null);

  useEffect(() => {
    fetchMetricsCatalog(selectedType ?? undefined)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [selectedType]);

  if (error) {
    return (
      <div className="p-8 text-red-400">
        <h1 className="text-xl font-bold mb-2">Metrics Catalog</h1>
        <p>{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-8 text-zinc-400 animate-pulse">
        Loading metrics catalog…
      </div>
    );
  }

  /* filter by search */
  const q = search.toLowerCase();
  const filtered = q
    ? data.metrics.filter(
        (m) =>
          m.name.toLowerCase().includes(q) ||
          m.key.toLowerCase().includes(q) ||
          m.description.toLowerCase().includes(q) ||
          m.category.toLowerCase().includes(q)
      )
    : data.metrics;

  /* group by category */
  const grouped: Record<string, MetricDef[]> = {};
  for (const m of filtered) {
    (grouped[m.category] ??= []).push(m);
  }
  const cats = Object.keys(grouped);

  /* count per model type */
  const typeCounts: Record<string, number> = {};
  for (const m of data.metrics) {
    for (const t of m.model_types) typeCounts[t] = (typeCounts[t] ?? 0) + 1;
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Metrics Catalog</h1>
        <p className="text-sm text-zinc-400 mt-1">
          {data.total} evaluation metrics across {data.model_types.length} model
          types. Every metric is available for any model — the defaults below
          show what&apos;s relevant per type.
        </p>
      </div>

      {/* Model-type pills */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setSelectedType(null)}
          className="rounded-full px-3 py-1.5 text-xs font-semibold transition-all"
          style={{
            background: !selectedType ? "#fff" : "#27272a",
            color: !selectedType ? "#000" : "#a1a1aa",
          }}
        >
          All ({data.total})
        </button>
        {data.model_types.map((t) => {
          const meta = TYPE_META[t] ?? TYPE_META.other;
          const active = selectedType === t;
          return (
            <button
              key={t}
              onClick={() => setSelectedType(active ? null : t)}
              className="rounded-full px-3 py-1.5 text-xs font-semibold transition-all flex items-center gap-1.5"
              style={{
                background: active ? meta.color + "25" : "#27272a",
                color: active ? meta.color : "#a1a1aa",
                border: active ? `1px solid ${meta.color}50` : "1px solid transparent",
              }}
            >
              <span>{meta.emoji}</span>
              {meta.label}
              <span className="opacity-60">({typeCounts[t] ?? 0})</span>
            </button>
          );
        })}
      </div>

      {/* Search */}
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search metrics by name, key, or description…"
        className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2.5 text-sm text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-600"
      />

      {/* Stats bar */}
      <div className="flex gap-6 text-xs text-zinc-500">
        <span>
          Showing <strong className="text-zinc-300">{filtered.length}</strong> metrics
        </span>
        <span>
          <strong className="text-zinc-300">{cats.length}</strong> categories
        </span>
      </div>

      {/* Categories */}
      <div className="space-y-3">
        {cats.map((cat) => {
          const metrics = grouped[cat];
          const isOpen = expandedCat === cat || !!search || cats.length <= 4;
          return (
            <div key={cat} className="rounded-xl border border-zinc-800 overflow-hidden">
              {/* Category header */}
              <button
                onClick={() => setExpandedCat(isOpen && !search ? null : cat)}
                className="w-full flex items-center justify-between px-5 py-3 bg-zinc-900/60 hover:bg-zinc-800/60 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="text-sm font-semibold text-zinc-200">{cat}</span>
                  <span className="text-xs text-zinc-500">
                    {metrics.length} metric{metrics.length !== 1 ? "s" : ""}
                  </span>
                </div>
                <span className="text-zinc-500 text-xs">{isOpen ? "▾" : "▸"}</span>
              </button>

              {/* Metric rows */}
              {isOpen && (
                <div className="divide-y divide-zinc-800/60">
                  {metrics.map((m) => (
                    <div
                      key={m.key}
                      className="px-5 py-3 flex items-start gap-4 hover:bg-zinc-800/30 transition-colors"
                    >
                      {/* Direction indicator */}
                      <div className="pt-0.5">
                        <DirectionIcon up={m.higher_is_better} />
                      </div>

                      {/* Main info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-zinc-100">
                            {m.name}
                          </span>
                          {m.unit && (
                            <span className="text-[10px] text-zinc-500 font-mono">
                              {m.unit}
                            </span>
                          )}
                          {m.has_db_column && (
                            <span className="text-[9px] text-emerald-500/70 font-mono">
                              indexed
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-zinc-400 mt-0.5 leading-relaxed">
                          {m.description}
                        </p>
                        <code className="text-[10px] text-zinc-600 font-mono mt-1 block">
                          {m.key}
                        </code>
                      </div>

                      {/* Model type badges */}
                      <div className="flex flex-wrap gap-1 shrink-0 max-w-[180px] justify-end">
                        {m.model_types.map((t) => (
                          <Badge
                            key={t}
                            text={(TYPE_META[t] ?? TYPE_META.other).label}
                            color={(TYPE_META[t] ?? TYPE_META.other).color}
                          />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-12 text-zinc-500 text-sm">
          No metrics match &ldquo;{search}&rdquo;
        </div>
      )}
    </div>
  );
}
