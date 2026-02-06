"use client";

import { useEffect, useState } from "react";
import { useApiKey } from "@/lib/use-api-key";
import { fetchMetrics, type Metrics } from "@/lib/api";
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
  Cell,
} from "recharts";

/* ── Snapshot for time-series ────────────────────────────────── */

interface Snapshot {
  time: string;
  rps: number;
  p50: number;
  p90: number;
  p95: number;
  p99: number;
  p999: number;
  active: number;
  errorPct: number;
  successPct: number;
  queueDepth: number;
  gpuUtil: number;
  gpuTemp: number;
  gpuPower: number;
  vramPct: number;
  cpuUtil: number;
  ramPct: number;
  computeAvg: number;
}

const MAX_POINTS = 60;

/* ── Helpers ─────────────────────────────────────────────────── */

const fmt = (v: number | null | undefined, suffix = "") =>
  v != null ? `${Math.round(v * 100) / 100}${suffix}` : "—";

const fmtMs = (v: number | null | undefined) => fmt(v, " ms");

const fmtPct = (v: number | null | undefined) => fmt(v, "%");

const fmtBytes = (v: number | null | undefined) => {
  if (v == null) return "—";
  if (v < 1024) return `${Math.round(v)} B`;
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
  return `${(v / (1024 * 1024)).toFixed(1)} MB`;
};

const fmtDuration = (seconds: number) => {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
};

/* ── Main Page ───────────────────────────────────────────────── */

export default function MetricsPage() {
  const { apiKey } = useApiKey();
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [history, setHistory] = useState<Snapshot[]>([]);

  useEffect(() => {
    if (!apiKey) return;
    const poll = () =>
      fetchMetrics(apiKey)
        .then((m) => {
          setMetrics(m);
          setHistory((prev) => {
            const snap: Snapshot = {
              time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
              rps: m.rps ?? 0,
              p50: m.p50_ms ?? 0,
              p90: m.p90_ms ?? 0,
              p95: m.p95_ms ?? 0,
              p99: m.p99_ms ?? 0,
              p999: m.p999_ms ?? 0,
              active: m.active_requests ?? 0,
              errorPct: m.error_rate_pct ?? 0,
              successPct: m.success_rate_pct ?? 100,
              queueDepth: m.queue_depth ?? 0,
              gpuUtil: m.gpu?.utilization_gpu_pct ?? 0,
              gpuTemp: m.gpu?.temp_gpu_c ?? 0,
              gpuPower: m.gpu?.power_watts ?? 0,
              vramPct: m.gpu?.vram_used_pct ?? 0,
              cpuUtil: m.cpu?.utilization_pct ?? 0,
              ramPct: m.memory?.ram_used_pct ?? 0,
              computeAvg: m.compute_avg_ms ?? 0,
            };
            const next = [...prev, snap];
            return next.length > MAX_POINTS ? next.slice(-MAX_POINTS) : next;
          });
        })
        .catch(() => {});
    poll();
    const id = setInterval(poll, 3_000);
    return () => clearInterval(id);
  }, [apiKey]);

  if (!apiKey) {
    return (
      <p className="text-sm text-muted-foreground">
        Enter your API key in the sidebar to view live metrics.
      </p>
    );
  }

  const m = metrics;

  return (
    <div className="space-y-8 pb-12">
      {/* Header */}
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Metrics Observatory</h1>
          <p className="text-sm text-muted-foreground">
            Full-stack telemetry — transistors → silicon → hardware → application — polling every 3s
          </p>
        </div>
        {m && (
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span>Uptime: <strong className="text-foreground">{fmtDuration(m.uptime_s)}</strong></span>
            <span>PID: <strong className="text-foreground">{m.system?.pid ?? "—"}</strong></span>
            <span>{m.system?.hostname}</span>
          </div>
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════════
          TIER 1: APPLICATION LAYER
         ═══════════════════════════════════════════════════════════ */}
      <Section title="⚡ Application Layer" subtitle="Request throughput, error rates, queue depth">
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
          <KPI label="Total Requests" value={fmt(m?.total_requests)} />
          <KPI label="RPS" value={m?.rps?.toFixed(2) ?? "—"} glossary="rps" />
          <KPI label="RPM" value={fmt(m?.rpm)} />
          <KPI label="Active" value={fmt(m?.active_requests)} glossary="active requests" />
          <KPI label="Queue Depth" value={fmt(m?.queue_depth)} />
          <KPI label="Success Rate" value={fmtPct(m?.success_rate_pct)} accent="emerald" />
          <KPI label="Error Rate" value={fmtPct(m?.error_rate_pct)} accent="red" glossary="error rate" />
          <KPI label="Error Count" value={fmt(m?.error_count)} accent="red" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
          <ChartCard title="Requests / sec" data={history}>
            <Area type="monotone" dataKey="rps" stroke="hsl(var(--chart-4))" fill="hsl(var(--chart-4))" fillOpacity={0.15} strokeWidth={2} name="RPS" />
          </ChartCard>
          <ChartCard title="Active Requests & Queue Depth" data={history}>
            <Area type="monotone" dataKey="active" stroke="hsl(var(--chart-5))" fill="hsl(var(--chart-5))" fillOpacity={0.1} strokeWidth={2} name="Active" />
            <Line type="monotone" dataKey="queueDepth" stroke="hsl(var(--chart-2))" dot={false} strokeWidth={1.5} strokeDasharray="5 3" name="Queue" />
          </ChartCard>
        </div>
      </Section>

      {/* ═══════════════════════════════════════════════════════════
          TIER 2: LATENCY DISTRIBUTION
         ═══════════════════════════════════════════════════════════ */}
      <Section title="⏱ Latency Distribution" subtitle="End-to-end request timing — every percentile">
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
          <KPI label="Min" value={fmtMs(m?.min_latency_ms)} />
          <KPI label="Avg" value={fmtMs(m?.avg_latency_ms)} />
          <KPI label="P50" value={fmtMs(m?.p50_ms)} glossary="p50" />
          <KPI label="P90" value={fmtMs(m?.p90_ms)} />
          <KPI label="P95" value={fmtMs(m?.p95_ms)} glossary="p95" />
          <KPI label="P99" value={fmtMs(m?.p99_ms)} glossary="p99" />
          <KPI label="P99.9" value={fmtMs(m?.p999_ms)} />
          <KPI label="Max" value={fmtMs(m?.max_latency_ms)} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
          <ChartCard title="Latency Percentiles (ms)" data={history} tall>
            <Line type="monotone" dataKey="p50" stroke="#22c55e" dot={false} strokeWidth={2} name="P50" />
            <Line type="monotone" dataKey="p90" stroke="#3b82f6" dot={false} strokeWidth={1.5} name="P90" />
            <Line type="monotone" dataKey="p95" stroke="#f59e0b" dot={false} strokeWidth={2} name="P95" />
            <Line type="monotone" dataKey="p99" stroke="#ef4444" dot={false} strokeWidth={2} name="P99" />
            <Line type="monotone" dataKey="p999" stroke="#a855f7" dot={false} strokeWidth={1.5} strokeDasharray="5 3" name="P99.9" />
          </ChartCard>
          <ChartCard title="Error Rate (%)" data={history}>
            <Area type="monotone" dataKey="errorPct" stroke="#ef4444" fill="#ef4444" fillOpacity={0.12} strokeWidth={2} name="Errors" />
          </ChartCard>
        </div>
      </Section>

      {/* ═══════════════════════════════════════════════════════════
          TIER 3: COMPUTE / MODEL LAYER
         ═══════════════════════════════════════════════════════════ */}
      <Section title="🧠 Compute / Model Layer" subtitle="Pure model execution time, model load, cold start">
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          <KPI label="Compute P50" value={fmtMs(m?.compute_p50_ms)} />
          <KPI label="Compute P95" value={fmtMs(m?.compute_p95_ms)} />
          <KPI label="Compute P99" value={fmtMs(m?.compute_p99_ms)} />
          <KPI label="Compute Avg" value={fmtMs(m?.compute_avg_ms)} />
          <KPI label="Last Compute" value={fmtMs(m?.last_compute_ms)} />
          <KPI label="Cold Start" value={fmtMs(m?.cold_start_ms)} glossary="cold start" />
          <KPI label="Overhead" value={
            m?.avg_latency_ms != null && m?.compute_avg_ms != null
              ? fmtMs(m.avg_latency_ms - m.compute_avg_ms)
              : "—"
          } />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
          <ChartCard title="Compute Time (ms)" data={history}>
            <Area type="monotone" dataKey="computeAvg" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.12} strokeWidth={2} name="Compute Avg" />
          </ChartCard>

          {/* Model load times */}
          {m?.model_load_times_ms && Object.keys(m.model_load_times_ms).length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Model Load Times</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={Object.entries(m.model_load_times_ms).map(([name, ms]) => ({ name: name.replace(/-/g, " "), ms: Math.round(ms * 100) / 100 }))}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Bar dataKey="ms" name="Load (ms)" radius={[4, 4, 0, 0]}>
                      {Object.entries(m.model_load_times_ms).map((_, i) => (
                        <Cell key={i} fill={["#22c55e", "#3b82f6", "#f59e0b", "#ef4444", "#a855f7", "#06b6d4"][i % 6]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Per-model breakdown table */}
        {m?.per_model && Object.keys(m.per_model).length > 0 && (
          <Card className="mt-4">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Per-Model Breakdown</CardTitle>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="text-left py-2 px-2 font-medium">Model</th>
                    <th className="text-right py-2 px-2 font-medium">Requests</th>
                    <th className="text-right py-2 px-2 font-medium">Errors</th>
                    <th className="text-right py-2 px-2 font-medium">P50</th>
                    <th className="text-right py-2 px-2 font-medium">P95</th>
                    <th className="text-right py-2 px-2 font-medium">P99</th>
                    <th className="text-right py-2 px-2 font-medium">Avg</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(m.per_model).map(([name, pm]) => (
                    <tr key={name} className="border-b border-border/40">
                      <td className="py-2 px-2 font-mono">{name}</td>
                      <td className="text-right py-2 px-2">{pm.requests}</td>
                      <td className="text-right py-2 px-2 text-red-400">{pm.errors}</td>
                      <td className="text-right py-2 px-2">{fmtMs(pm.p50_ms)}</td>
                      <td className="text-right py-2 px-2">{fmtMs(pm.p95_ms)}</td>
                      <td className="text-right py-2 px-2">{fmtMs(pm.p99_ms)}</td>
                      <td className="text-right py-2 px-2">{fmtMs(pm.avg_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}
      </Section>

      {/* ═══════════════════════════════════════════════════════════
          TIER 4: TOKENS & PAYLOAD
         ═══════════════════════════════════════════════════════════ */}
      <Section title="📦 Tokens & Payload" subtitle="LLM token accounting, request/response sizes">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <KPI label="Tokens In" value={fmt(m?.total_tokens_in)} glossary="tokens" />
          <KPI label="Tokens Out" value={fmt(m?.total_tokens_out)} />
          <KPI label="Total Tokens" value={fmt(m?.total_tokens)} />
          <KPI label="Avg Req Size" value={fmtBytes(m?.avg_request_size_bytes)} />
          <KPI label="Avg Res Size" value={fmtBytes(m?.avg_response_size_bytes)} />
          <KPI label="Cost / 1K Tokens" value={m?.cost_per_1k_tokens != null ? `$${m.cost_per_1k_tokens.toFixed(4)}` : "—"} glossary="cost per 1k tokens" />
        </div>
      </Section>

      {/* ═══════════════════════════════════════════════════════════
          TIER 5: COST & ECONOMICS
         ═══════════════════════════════════════════════════════════ */}
      <Section title="💰 Cost & Economics" subtitle="Infrastructure cost estimation and efficiency">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <KPI label="Price / Hour" value={m?.price_per_hour != null ? `$${m.price_per_hour.toFixed(4)}` : "—"} glossary="cost per inference" />
          <KPI label="Cost / Inference" value={m?.cost_per_inference != null ? `$${m.cost_per_inference.toFixed(6)}` : "—"} />
          <KPI label="Throughput / $" value={m?.throughput_per_dollar != null ? `${m.throughput_per_dollar.toFixed(2)} rps/$` : "—"} glossary="throughput per dollar" />
          <KPI label="Est. Daily Cost" value={m?.price_per_hour != null ? `$${(m.price_per_hour * 24).toFixed(2)}` : "—"} />
        </div>
      </Section>

      {/* ═══════════════════════════════════════════════════════════
          TIER 6: GPU SILICON
         ═══════════════════════════════════════════════════════════ */}
      <Section title="🔥 GPU Silicon" subtitle="SM cores, VRAM, thermals, clocks, PCIe, ECC — transistor-level">
        {m?.gpu?.available ? (
          <>
            {/* Device badge */}
            <div className="flex flex-wrap gap-2 mb-4">
              {m.gpu.gpu_name && <Badge variant="outline">{m.gpu.gpu_name}</Badge>}
              {m.gpu.driver_version && <Badge variant="outline">Driver {m.gpu.driver_version}</Badge>}
              {m.gpu.compute_capability && <Badge variant="outline">Compute {m.gpu.compute_capability}</Badge>}
              {m.gpu.pstate && <Badge variant="outline">PState {m.gpu.pstate}</Badge>}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
              <KPI label="GPU Utilization" value={fmtPct(m.gpu.utilization_gpu_pct)} glossary="gpu utilization" />
              <KPI label="Mem Utilization" value={fmtPct(m.gpu.utilization_mem_pct)} />
              <KPI label="VRAM Used" value={`${fmt(m.gpu.vram_used_mb)} MB`} glossary="vram" />
              <KPI label="VRAM Total" value={`${fmt(m.gpu.vram_total_mb)} MB`} />
              <KPI label="VRAM Free" value={`${fmt(m.gpu.vram_free_mb)} MB`} />
              <KPI label="VRAM %" value={fmtPct(m.gpu.vram_used_pct)} />
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mt-3">
              <KPI label="Power Draw" value={`${fmt(m.gpu.power_watts)} W`} glossary="gpu power" />
              <KPI label="Power Limit" value={`${fmt(m.gpu.power_limit_watts)} W`} />
              <KPI label="Power %" value={fmtPct(m.gpu.power_usage_pct)} />
              <KPI label="GPU Temp" value={`${fmt(m.gpu.temp_gpu_c)}°C`} />
              <KPI label="Mem Temp" value={m.gpu.temp_memory_c != null ? `${fmt(m.gpu.temp_memory_c)}°C` : "—"} />
              <KPI label="Fan Speed" value={fmtPct(m.gpu.fan_speed_pct)} />
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mt-3">
              <KPI label="SM Clock" value={`${fmt(m.gpu.sm_clock_mhz)} MHz`} />
              <KPI label="SM Max" value={`${fmt(m.gpu.sm_max_clock_mhz)} MHz`} />
              <KPI label="Mem Clock" value={`${fmt(m.gpu.mem_clock_mhz)} MHz`} />
              <KPI label="Mem Max Clock" value={`${fmt(m.gpu.mem_max_clock_mhz)} MHz`} />
              <KPI label="Clock Throttle" value={fmtPct(m.gpu.clock_throttle_pct)} />
              <KPI label="PCIe" value={m.gpu.pcie_gen != null ? `Gen${fmt(m.gpu.pcie_gen)} x${fmt(m.gpu.pcie_width)}` : "—"} />
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3">
              <KPI label="ECC Corrected" value={fmt(m.gpu.ecc_corrected ?? 0)} accent={m.gpu.ecc_corrected ? "amber" : undefined} />
              <KPI label="ECC Uncorrected" value={fmt(m.gpu.ecc_uncorrected ?? 0)} accent={m.gpu.ecc_uncorrected ? "red" : undefined} />
              <KPI label="Encoder Sessions" value={fmt(m.gpu.encoder_sessions)} />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
              <ChartCard title="GPU Utilization & VRAM %" data={history}>
                <Line type="monotone" dataKey="gpuUtil" stroke="#22c55e" dot={false} strokeWidth={2} name="GPU %" />
                <Line type="monotone" dataKey="vramPct" stroke="#f59e0b" dot={false} strokeWidth={2} name="VRAM %" />
              </ChartCard>
              <ChartCard title="GPU Temperature (°C) & Power (W)" data={history}>
                <Line type="monotone" dataKey="gpuTemp" stroke="#ef4444" dot={false} strokeWidth={2} name="Temp °C" />
                <Line type="monotone" dataKey="gpuPower" stroke="#a855f7" dot={false} strokeWidth={1.5} name="Power W" />
              </ChartCard>
            </div>
          </>
        ) : (
          <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
            No NVIDIA GPU detected — nvidia-smi unavailable
          </CardContent></Card>
        )}
      </Section>

      {/* ═══════════════════════════════════════════════════════════
          TIER 7: CPU SILICON
         ═══════════════════════════════════════════════════════════ */}
      <Section title="🖥 CPU Silicon" subtitle="Core utilization, frequency, context switches, interrupts">
        {m?.cpu?.available ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
              <KPI label="CPU Utilization" value={fmtPct(m.cpu.utilization_pct)} />
              <KPI label="Physical Cores" value={fmt(m.cpu.core_count_physical)} />
              <KPI label="Logical Cores" value={fmt(m.cpu.core_count_logical)} />
              <KPI label="Freq Current" value={`${fmt(m.cpu.freq_current_mhz)} MHz`} />
              <KPI label="Freq Max" value={`${fmt(m.cpu.freq_max_mhz)} MHz`} />
              <KPI label="Freq Throttle" value={fmtPct(m.cpu.freq_throttle_pct)} />
              <KPI label="Load Avg (1m)" value={m.cpu.load_1m?.toFixed(2) ?? "—"} />
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
              <KPI label="Load Avg (5m)" value={m.cpu.load_5m?.toFixed(2) ?? "—"} />
              <KPI label="Load Avg (15m)" value={m.cpu.load_15m?.toFixed(2) ?? "—"} />
              <KPI label="Context Switches" value={m.cpu.ctx_switches?.toLocaleString() ?? "—"} />
              <KPI label="Interrupts" value={m.cpu.interrupts?.toLocaleString() ?? "—"} />
            </div>

            {/* Per-core utilization */}
            {m.cpu.per_core_pct && m.cpu.per_core_pct.length > 0 && (
              <Card className="mt-4">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Per-Core Utilization</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={120}>
                    <BarChart data={m.cpu.per_core_pct.map((pct, i) => ({ core: `C${i}`, pct: Math.round(pct * 10) / 10 }))}>
                      <XAxis dataKey="core" tick={{ fontSize: 9 }} />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 9 }} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Bar dataKey="pct" name="%" radius={[3, 3, 0, 0]}>
                        {m.cpu.per_core_pct.map((pct, i) => (
                          <Cell key={i} fill={pct > 80 ? "#ef4444" : pct > 50 ? "#f59e0b" : "#22c55e"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
              <ChartCard title="CPU Utilization %" data={history}>
                <Area type="monotone" dataKey="cpuUtil" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.12} strokeWidth={2} name="CPU %" />
              </ChartCard>
            </div>
          </>
        ) : (
          <Card><CardContent className="py-6 text-center text-sm text-muted-foreground">
            {m?.cpu?.note ?? "CPU metrics unavailable — install psutil"}
          </CardContent></Card>
        )}
      </Section>

      {/* ═══════════════════════════════════════════════════════════
          TIER 8: SYSTEM MEMORY
         ═══════════════════════════════════════════════════════════ */}
      <Section title="🧮 System Memory" subtitle="RAM, swap, cache, buffers">
        {m?.memory?.available ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <KPI label="RAM Used" value={`${fmt(m.memory.ram_used_mb)} MB`} />
              <KPI label="RAM Total" value={`${fmt(m.memory.ram_total_mb)} MB`} />
              <KPI label="RAM Free" value={`${fmt(m.memory.ram_free_mb)} MB`} />
              <KPI label="RAM %" value={fmtPct(m.memory.ram_used_pct)} />
              <KPI label="Cached" value={`${fmt(m.memory.ram_cached_mb)} MB`} />
              <KPI label="Buffers" value={`${fmt(m.memory.ram_buffers_mb)} MB`} />
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3">
              <KPI label="Swap Used" value={`${fmt(m.memory.swap_used_mb)} MB`} />
              <KPI label="Swap Total" value={`${fmt(m.memory.swap_total_mb)} MB`} />
              <KPI label="Swap %" value={fmtPct(m.memory.swap_used_pct)} />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
              <ChartCard title="RAM Utilization %" data={history}>
                <Area type="monotone" dataKey="ramPct" stroke="#06b6d4" fill="#06b6d4" fillOpacity={0.12} strokeWidth={2} name="RAM %" />
              </ChartCard>
            </div>
          </>
        ) : (
          <Card><CardContent className="py-6 text-center text-sm text-muted-foreground">
            {m?.memory?.note ?? "Memory metrics unavailable — install psutil"}
          </CardContent></Card>
        )}
      </Section>

      {/* ═══════════════════════════════════════════════════════════
          TIER 9: SYSTEM INFO
         ═══════════════════════════════════════════════════════════ */}
      <Section title="📋 System Info" subtitle="Host identification, runtime, architecture">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <KPI label="Hostname" value={m?.system?.hostname ?? "—"} />
          <KPI label="OS" value={m?.system?.os ?? "—"} />
          <KPI label="Architecture" value={m?.system?.arch ?? "—"} />
          <KPI label="Python" value={m?.system?.python_version ?? "—"} />
          <KPI label="PID" value={fmt(m?.system?.pid)} />
        </div>
      </Section>
    </div>
  );
}

/* ── Reusable Components ─────────────────────────────────────── */

function Section({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-3">
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
      </div>
      {children}
      <Separator className="mt-6" />
    </div>
  );
}

function KPI({
  label,
  value,
  glossary,
  accent,
}: {
  label: string;
  value: string;
  glossary?: string;
  accent?: "emerald" | "red" | "amber";
}) {
  const accentClass = accent === "emerald"
    ? "text-emerald-500"
    : accent === "red"
      ? "text-red-500"
      : accent === "amber"
        ? "text-amber-500"
        : "";

  return (
    <Card data-glossary={glossary} className="bg-card/60">
      <CardContent className="pt-4 pb-3 px-3 space-y-0.5">
        <p className={`text-[10px] text-muted-foreground font-medium uppercase tracking-wider ${glossary ? "cursor-help decoration-dotted underline underline-offset-4 decoration-muted-foreground/40" : ""}`}>
          {label}
        </p>
        <p className={`text-base font-bold truncate ${accentClass}`}>{value}</p>
      </CardContent>
    </Card>
  );
}

const tooltipStyle = {
  background: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: 8,
  fontSize: 11,
};

function ChartCard({
  title,
  data,
  children,
  tall,
}: {
  title: string;
  data: Snapshot[];
  children: React.ReactNode;
  tall?: boolean;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={tall ? 260 : 180}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis dataKey="time" tick={{ fontSize: 9 }} />
            <YAxis tick={{ fontSize: 9 }} />
            <Tooltip contentStyle={tooltipStyle} />
            {children}
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
