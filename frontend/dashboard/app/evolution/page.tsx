"use client";

import { useEffect, useState } from "react";
import {
  fetchEvolution,
  fetchRoadmap,
  type EvolutionEntry,
  type RoadmapResponse,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
  Cell,
} from "recharts";

/* ── Constants ───────────────────────────────────────────────── */

const ALL_VERSIONS = ["V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7"] as const;

const versionMeta: Record<string, { color: string; emoji: string; label: string }> = {
  V0: { color: "#94a3b8", emoji: "🏁", label: "Baseline" },
  V1: { color: "#60a5fa", emoji: "⚽", label: "Sports Objects" },
  V2: { color: "#34d399", emoji: "🏋️", label: "Athlete Pose" },
  V3: { color: "#fbbf24", emoji: "🥊", label: "Basic Actions" },
  V4: { color: "#f97316", emoji: "🏀", label: "Sport-Specific" },
  V5: { color: "#a78bfa", emoji: "🎬", label: "Sequences" },
  V6: { color: "#f472b6", emoji: "⚡", label: "Edge RT" },
  V7: { color: "#ef4444", emoji: "🏆", label: "Universal" },
};

/* ── Helpers ─────────────────────────────────────────────────── */

const fmt = (v: number | null | undefined, d = 1) => (v != null ? v.toFixed(d) : "—");
const fmtPct = (v: number | null | undefined) => (v != null ? `${(v * 100).toFixed(1)}%` : "—");

function StatusDot({ status }: { status: string }) {
  const cls =
    status === "completed"
      ? "bg-green-500"
      : status === "training"
        ? "bg-yellow-400 animate-pulse"
        : "bg-muted-foreground/30";
  return <span className={`inline-block h-2 w-2 rounded-full ${cls}`} />;
}

/* ── Main ────────────────────────────────────────────────────── */

export default function EvolutionPage() {
  const [entries, setEntries] = useState<EvolutionEntry[]>([]);
  const [roadmap, setRoadmap] = useState<RoadmapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<string>("all");

  useEffect(() => {
    const load = async () => {
      try {
        const [evo, rm] = await Promise.all([fetchEvolution(), fetchRoadmap()]);
        setEntries(evo);
        setRoadmap(rm);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load");
      }
    };
    load();
    const iv = setInterval(load, 30_000);
    return () => clearInterval(iv);
  }, []);

  const filtered = selectedVersion === "all" ? entries : entries.filter((e) => e.version === selectedVersion);
  const stage = roadmap?.roadmap.find((s) => s.version === selectedVersion) ?? null;
  const latest = filtered.length ? filtered[filtered.length - 1] : null;
  const completedStages = roadmap?.roadmap.filter((s) => s.status === "completed").length ?? 0;
  const pct = roadmap ? Math.round((completedStages / roadmap.roadmap.length) * 100) : 0;

  const chartData = filtered.map((e) => ({
    label: `${e.version}.${e.iteration}`,
    version: e.version,
    tag: e.tag,
    confidence: e.precision != null ? +(e.precision * 100).toFixed(1) : null,
    mAP50: e.mAP50 != null ? +(e.mAP50 * 100).toFixed(1) : null,
    recall: e.recall != null ? +(e.recall * 100).toFixed(1) : null,
    f1: e.f1_score != null ? +(e.f1_score * 100).toFixed(1) : null,
    inferenceMs: e.avg_inference_ms,
    detections: e.avg_detections,
  }));

  if (error) {
    return (
      <div className="p-8">
        <Card className="border-red-500/40">
          <CardContent className="pt-6 text-red-400">Error: {error}</CardContent>
        </Card>
      </div>
    );
  }

  /* ── Render ────────────────────────────────────────────────── */
  return (
    <div className="flex flex-col gap-6 p-6 md:p-8 max-w-[1400px] mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Model Evolution</h1>
        <p className="text-muted-foreground text-sm mt-1">
          V0 COCO Baseline → V7 Universal Sports AI
        </p>
      </div>

      {/* ── Timeline Track ───────────────────────────────────── */}
      <Card className="overflow-hidden">
        <CardContent className="p-0">
          {/* Gradient progress bar */}
          <div className="h-1.5 bg-muted">
            <div
              className="h-full bg-gradient-to-r from-slate-400 via-blue-500 via-green-400 via-yellow-400 via-orange-500 via-violet-500 via-pink-500 to-red-500 transition-all duration-1000"
              style={{ width: `${Math.max(pct, 6)}%` }}
            />
          </div>

          {/* Version pills row */}
          <div className="flex items-center gap-1.5 px-4 py-3 overflow-x-auto">
            <button
              onClick={() => setSelectedVersion("all")}
              className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${
                selectedVersion === "all"
                  ? "bg-foreground text-background shadow"
                  : "bg-muted/60 text-muted-foreground hover:bg-muted"
              }`}
            >
              Overview
            </button>

            {ALL_VERSIONS.map((v) => {
              const m = versionMeta[v];
              const hasData = entries.some((e) => e.version === v);
              const active = selectedVersion === v;
              return (
                <button
                  key={v}
                  onClick={() => setSelectedVersion(v)}
                  className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${
                    active
                      ? "shadow ring-1"
                      : hasData
                        ? "hover:shadow"
                        : "opacity-40 hover:opacity-70"
                  }`}
                  style={{
                    backgroundColor: active ? m.color + "25" : undefined,
                    color: active || hasData ? m.color : undefined,
                    ringColor: active ? m.color : undefined,
                  }}
                >
                  <span>{m.emoji}</span>
                  <span>{v}</span>
                  {hasData && !active && <StatusDot status="completed" />}
                </button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* ── Version Detail Banner ────────────────────────────── */}
      {selectedVersion !== "all" && stage && (
        <div
          className="rounded-xl p-5 border"
          style={{
            borderColor: versionMeta[selectedVersion].color + "40",
            background: `linear-gradient(135deg, ${versionMeta[selectedVersion].color}08, ${versionMeta[selectedVersion].color}15)`,
          }}
        >
          <div className="flex flex-col sm:flex-row sm:items-center gap-4">
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <span className="text-4xl">{versionMeta[selectedVersion].emoji}</span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-bold" style={{ color: versionMeta[selectedVersion].color }}>
                    {selectedVersion}
                  </h2>
                  <span className="text-sm text-muted-foreground">· {stage.name}</span>
                  <StatusDot status={stage.status} />
                </div>
                <p className="text-sm text-muted-foreground truncate">{stage.goal}</p>
              </div>
            </div>
            <div className="text-right text-sm text-muted-foreground">
              {filtered.length} iteration{filtered.length !== 1 ? "s" : ""}
            </div>
          </div>

          {latest && (
            <div className="grid grid-cols-3 sm:grid-cols-5 gap-6 mt-5 pt-4 border-t" style={{ borderColor: versionMeta[selectedVersion].color + "20" }}>
              <Stat label="Confidence" value={fmtPct(latest.precision)} accent={versionMeta[selectedVersion].color} />
              <Stat label="mAP@50" value={fmtPct(latest.mAP50)} />
              <Stat label="Inference" value={latest.avg_inference_ms != null ? `${fmt(latest.avg_inference_ms)}ms` : "—"} />
              <Stat label="Detections" value={fmt(latest.avg_detections)} />
              <Stat label="Classes" value={latest.total_classes != null ? String(latest.total_classes) : "—"} />
            </div>
          )}
        </div>
      )}

      {/* ── Overview KPIs ────────────────────────────────────── */}
      {selectedVersion === "all" && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPI label="Current" value={roadmap?.current_version ?? "—"} sub={`${pct}% → V7`} />
          <KPI label="Iterations" value={String(roadmap?.total_entries ?? 0)} />
          <KPI label="Confidence" value={entries.length ? fmtPct(entries[entries.length - 1]?.precision) : "—"} />
          <KPI label="Inference" value={entries.length ? `${fmt(entries[entries.length - 1]?.avg_inference_ms)}ms` : "—"} />
        </div>
      )}

      {/* ── Roadmap Grid (overview only) ─────────────────────── */}
      {selectedVersion === "all" && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {roadmap?.roadmap.map((s) => {
            const m = versionMeta[s.version];
            const hasData = entries.some((e) => e.version === s.version);
            return (
              <button
                key={s.version}
                onClick={() => setSelectedVersion(s.version)}
                className="text-left rounded-lg border p-4 transition-all hover:shadow-md hover:scale-[1.02] group"
                style={{
                  borderColor: hasData ? m.color + "50" : undefined,
                  background: hasData ? m.color + "08" : undefined,
                }}
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-lg">{m.emoji}</span>
                  <span className="text-xs font-bold" style={{ color: m.color }}>{s.version}</span>
                  <StatusDot status={s.status} />
                </div>
                <p className="text-sm font-medium leading-tight">{s.name}</p>
                <p className="text-[11px] text-muted-foreground mt-1 line-clamp-2">{s.goal}</p>
                {s.latest && (
                  <div className="mt-3 pt-2 border-t border-border/40 grid grid-cols-2 gap-1 text-[11px]">
                    <span className="text-muted-foreground">Conf</span>
                    <span className="text-right font-medium">{fmtPct(s.latest.precision)}</span>
                    <span className="text-muted-foreground">Speed</span>
                    <span className="text-right font-medium">{fmt(s.latest.avg_inference_ms)}ms</span>
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* ── Charts ───────────────────────────────────────────── */}
      {chartData.length > 0 && (
        <div className="grid md:grid-cols-2 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                {selectedVersion === "all" ? "Accuracy Trend" : `${selectedVersion} Accuracy`}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" unit="%" />
                  <Tooltip contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="confidence" name="Confidence" stroke="#60a5fa" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="mAP50" name="mAP@50" stroke="#34d399" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="recall" name="Recall" stroke="#fbbf24" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="f1" name="F1" stroke="#f472b6" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                {selectedVersion === "all" ? "Inference Speed" : `${selectedVersion} Speed`}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
                  <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" unit="ms" />
                  <Tooltip contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
                  <Area
                    type="monotone"
                    dataKey="inferenceMs"
                    name="Inference"
                    stroke={selectedVersion !== "all" ? versionMeta[selectedVersion].color : "#a78bfa"}
                    fill={(selectedVersion !== "all" ? versionMeta[selectedVersion].color : "#a78bfa") + "20"}
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── Version Comparison Bar (overview) ────────────────── */}
      {selectedVersion === "all" && (() => {
        const withData = ALL_VERSIONS
          .map((v) => entries.filter((e) => e.version === v))
          .filter((arr) => arr.length > 0)
          .map((arr) => arr.reduce((a, b) => ((b.precision ?? 0) > (a.precision ?? 0) ? b : a)));
        if (withData.length < 1) return null;

        const data = withData.map((e) => ({
          version: e.version,
          confidence: e.precision != null ? +(e.precision * 100).toFixed(1) : 0,
          speed: e.avg_inference_ms ?? 0,
        }));

        return (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Version Comparison</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={data} barGap={4}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="version" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                  <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
                  <Tooltip contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="confidence" name="Confidence %" radius={[4, 4, 0, 0]}>
                    {data.map((d) => (
                      <Cell key={d.version} fill={versionMeta[d.version]?.color ?? "#888"} />
                    ))}
                  </Bar>
                  <Bar dataKey="speed" name="Speed (ms)" fill="#a78bfa60" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        );
      })()}

      <Separator />

      {/* ── Iteration Cards ──────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">
            {selectedVersion === "all" ? "All Iterations" : `${selectedVersion} Iterations`}
          </h2>
          <Badge variant="secondary" className="text-xs">
            {filtered.length}
          </Badge>
        </div>

        {filtered.length === 0 ? (
          <Card>
            <CardContent className="py-16 text-center">
              <p className="text-3xl mb-3">{selectedVersion !== "all" ? versionMeta[selectedVersion]?.emoji : "📊"}</p>
              <p className="text-muted-foreground text-sm">
                {selectedVersion === "all" ? "No iterations yet." : `No iterations for ${selectedVersion}.`}
              </p>
              {stage && <p className="text-xs text-muted-foreground/70 mt-1">Goal: {stage.goal}</p>}
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3">
            {[...filtered].reverse().map((entry) => {
              const m = versionMeta[entry.version];
              return (
                <Card
                  key={entry.id}
                  className="overflow-hidden transition-all hover:shadow-md"
                  style={{ borderLeftWidth: 3, borderLeftColor: m?.color ?? "#888" }}
                >
                  <CardContent className="py-4 px-5">
                    {/* Top row */}
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <span
                        className="text-xs font-bold px-2 py-0.5 rounded-full"
                        style={{ backgroundColor: (m?.color ?? "#888") + "20", color: m?.color }}
                      >
                        {entry.version}.{entry.iteration}
                      </span>
                      <span className="text-sm font-medium">{entry.tag}</span>
                      {entry.model_arch && (
                        <Badge variant="secondary" className="text-[10px] h-5">{entry.model_arch}</Badge>
                      )}
                      <span className="ml-auto text-[11px] text-muted-foreground tabular-nums">
                        {entry.timestamp ? new Date(entry.timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : ""}
                      </span>
                    </div>

                    {/* Description */}
                    <p className="text-sm text-muted-foreground mb-3">{entry.description}</p>

                    {/* Metrics row — clean horizontal pills */}
                    <div className="flex flex-wrap gap-2 text-xs">
                      <Pill label="Conf" value={fmtPct(entry.precision)} color={m?.color} />
                      <Pill label="mAP" value={fmtPct(entry.mAP50)} />
                      <Pill label="Recall" value={fmtPct(entry.recall)} />
                      <Pill label="F1" value={fmtPct(entry.f1_score)} />
                      <Pill label="Speed" value={entry.avg_inference_ms != null ? `${fmt(entry.avg_inference_ms)}ms` : "—"} />
                      <Pill label="Dets" value={fmt(entry.avg_detections)} />
                      <Pill label="Cls" value={entry.total_classes != null ? String(entry.total_classes) : "—"} />
                      <Pill label="Imgs" value={entry.num_eval_images != null ? String(entry.num_eval_images) : "—"} />
                    </div>

                    {/* Changes */}
                    {entry.changes && entry.changes.length > 0 && (
                      <ul className="mt-3 space-y-0.5">
                        {entry.changes.map((c, i) => (
                          <li key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
                            <span className="mt-1.5 h-1 w-1 rounded-full bg-muted-foreground/40 shrink-0" />
                            {c}
                          </li>
                        ))}
                      </ul>
                    )}

                    {/* Target classes */}
                    {entry.target_classes && entry.target_classes.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {entry.target_classes.slice(0, 12).map((cls) => (
                          <span key={cls} className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                            {cls}
                          </span>
                        ))}
                        {entry.target_classes.length > 12 && (
                          <span className="text-[10px] text-muted-foreground/60">+{entry.target_classes.length - 12} more</span>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Sub-components ──────────────────────────────────────────── */

function KPI({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card>
      <CardContent className="pt-4 pb-3 px-4">
        <p className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">{label}</p>
        <p className="text-2xl font-bold tracking-tight mt-0.5">{value}</p>
        {sub && <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div>
      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</p>
      <p className="text-base font-bold mt-0.5" style={accent ? { color: accent } : undefined}>{value}</p>
    </div>
  );
}

function Pill({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-muted/60"
      style={color && value !== "—" ? { borderLeft: `2px solid ${color}` } : undefined}
    >
      <span className="text-muted-foreground">{label}</span>
      <span className="font-semibold">{value}</span>
    </span>
  );
}
