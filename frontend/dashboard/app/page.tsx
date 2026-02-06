"use client";

import { useEffect, useState } from "react";
import { useApiKey } from "@/lib/use-api-key";
import { fetchModels, fetchMetrics, fetchHealth, type Model, type Metrics } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Activity,
  Cpu,
  Gauge,
  HeartPulse,
  Zap,
  AlertTriangle,
} from "lucide-react";

export default function DashboardPage() {
  const { apiKey } = useApiKey();
  const [models, setModels] = useState<Model[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [healthy, setHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(() => setHealthy(true))
      .catch(() => setHealthy(false));
  }, []);

  useEffect(() => {
    if (!apiKey) return;
    const load = () => {
      fetchModels(apiKey).then(setModels).catch(() => {});
      fetchMetrics(apiKey).then(setMetrics).catch(() => {});
    };
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, [apiKey]);

  const fmt = (v: number | null | undefined, suffix = "") =>
    v != null ? `${Math.round(v)}${suffix}` : "—";

  if (!apiKey) {
    return (
      <div className="flex items-center justify-center h-[60vh] text-muted-foreground">
        <div className="text-center space-y-2">
          <div className="mx-auto h-12 w-12 rounded-full bg-muted flex items-center justify-center">
            <Cpu className="h-6 w-6 text-muted-foreground" />
          </div>
          <p className="text-sm">Enter your API key in the sidebar to connect.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground text-sm">
          Platform overview — live metrics refresh every 10s
        </p>
      </div>

      {/* Status strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard
          icon={<HeartPulse className="h-4 w-4" />}
          label="API Health"
          value={healthy === null ? "…" : healthy ? "Healthy" : "Down"}
          accent={healthy ? "text-emerald-500" : "text-destructive"}
        />
        <StatCard
          icon={<Cpu className="h-4 w-4" />}
          label="Models"
          value={models.length.toString()}
        />
        <StatCard
          icon={<Activity className="h-4 w-4" />}
          label="RPS"
          value={metrics?.rps != null ? metrics.rps.toFixed(1) : "—"}
          glossary="rps"
        />
        <StatCard
          icon={<Gauge className="h-4 w-4" />}
          label="P95 Latency"
          value={fmt(metrics?.p95_ms, " ms")}
          glossary="p95"
        />
        <StatCard
          icon={<Zap className="h-4 w-4" />}
          label="Active Reqs"
          value={fmt(metrics?.active_requests)}
          glossary="active requests"
        />
        <StatCard
          icon={<AlertTriangle className="h-4 w-4" />}
          label="Error Rate"
          value={
            metrics?.error_rate_pct != null
              ? `${metrics.error_rate_pct.toFixed(1)}%`
              : "—"
          }
          accent={
            metrics && metrics.error_rate_pct > 5
              ? "text-destructive"
              : undefined
          }
        />
      </div>

      {/* GPU Card */}
      {metrics?.gpu?.available && (
        <Card>
          <CardContent className="pt-5">
            <p className="text-xs text-muted-foreground font-medium mb-3">GPU</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              <div data-glossary="gpu utilization">
                <span className="text-muted-foreground cursor-help decoration-dotted underline underline-offset-4 decoration-muted-foreground/40">Utilization</span>
                <p className="text-lg font-semibold">
                  {fmt(metrics.gpu.utilization_gpu_pct, "%")}
                </p>
              </div>
              <div data-glossary="vram">
                <span className="text-muted-foreground cursor-help decoration-dotted underline underline-offset-4 decoration-muted-foreground/40">VRAM</span>
                <p className="text-lg font-semibold">
                  {fmt(metrics.gpu.vram_used_mb)} / {fmt(metrics.gpu.vram_total_mb)} MB
                </p>
              </div>
              <div data-glossary="gpu power">
                <span className="text-muted-foreground cursor-help decoration-dotted underline underline-offset-4 decoration-muted-foreground/40">Power</span>
                <p className="text-lg font-semibold">
                  {metrics.gpu.power_watts != null
                    ? `${Math.round(metrics.gpu.power_watts)} W`
                    : "—"}
                </p>
              </div>
              <div data-glossary="cost per inference">
                <span className="text-muted-foreground cursor-help decoration-dotted underline underline-offset-4 decoration-muted-foreground/40">Cost / Inference</span>
                <p className="text-lg font-semibold">
                  {metrics.cost_per_inference != null
                    ? `$${metrics.cost_per_inference.toFixed(6)}`
                    : "—"}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Model list */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Deployed Models</h2>
        {models.length === 0 ? (
          <p className="text-sm text-muted-foreground">No models loaded.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {models.map((m) => (
              <Card key={m.name} className="hover:border-primary/50 transition-colors">
                <CardContent className="pt-5 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm truncate">{m.name}</span>
                    <Badge variant={m.ready ? "default" : "secondary"}>
                      {m.ready ? "Ready" : "Loading"}
                    </Badge>
                  </div>
                  <div className="flex gap-2">
                    <Badge variant="outline" className="text-xs">
                      {m.input_type}
                    </Badge>
                    <Badge variant="outline" className="text-xs">
                      v{m.version}
                    </Badge>
                  </div>
                  {metrics?.model_load_times_ms?.[m.name] != null && (
                    <p className="text-xs text-muted-foreground">
                      Load time: {Math.round(metrics.model_load_times_ms[m.name])} ms
                    </p>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  accent,
  glossary,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  accent?: string;
  glossary?: string;
}) {
  return (
    <Card data-glossary={glossary}>
      <CardContent className="pt-5 space-y-1">
        <div className={`flex items-center gap-1.5 text-muted-foreground text-xs font-medium ${glossary ? "cursor-help decoration-dotted underline underline-offset-4 decoration-muted-foreground/40" : ""}`}>
          {icon} {label}
        </div>
        <p className={`text-xl font-bold ${accent ?? ""}`}>{value}</p>
      </CardContent>
    </Card>
  );
}
