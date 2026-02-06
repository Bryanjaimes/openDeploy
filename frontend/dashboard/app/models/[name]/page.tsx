"use client";

import { use, useEffect, useState, useRef } from "react";
import { useApiKey } from "@/lib/use-api-key";
import { predict, fetchMetrics, type PredictResult, type Metrics } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { ArrowLeft, Upload, Send, Loader2 } from "lucide-react";
import Link from "next/link";

export default function ModelDetailPage({
  params,
}: {
  params: Promise<{ name: string }>;
}) {
  const { name: rawName } = use(params);
  const name = decodeURIComponent(rawName);
  const { apiKey } = useApiKey();

  const [inputType, setInputType] = useState<"text" | "image">("text");
  const [textInput, setTextInput] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<PredictResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Detect input type from name heuristics
  useEffect(() => {
    if (/eye|retina|scanner|image|vision/i.test(name)) {
      setInputType("image");
    }
  }, [name]);

  // Live metrics
  useEffect(() => {
    if (!apiKey) return;
    const load = () => fetchMetrics(apiKey).then(setMetrics).catch(() => {});
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, [apiKey]);

  async function handlePredict() {
    if (!apiKey) return;
    setLoading(true);
    setError(null);
    setResult(null);
    const t0 = performance.now();
    try {
      const res = await predict(apiKey, name, {
        text: inputType === "text" ? textInput : undefined,
        file: inputType === "image" ? file ?? undefined : undefined,
      });
      setElapsed(Math.round(performance.now() - t0));
      setResult(res);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const fmt = (v: number | null | undefined, suffix = "") =>
    v != null ? `${Math.round(v)}${suffix}` : "—";

  return (
    <div className="max-w-4xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link href="/models">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-xl font-bold tracking-tight">{name}</h1>
          <p className="text-sm text-muted-foreground">
            <code data-glossary="inference">/models/{name}/predict</code>
          </p>
        </div>
        <Badge className="ml-auto">{inputType.toUpperCase()}</Badge>
      </div>

      <Separator />

      {/* Metrics strip */}
      {metrics && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
          <MiniStat label="P50" value={fmt(metrics.p50_ms, " ms")} glossary="p50" />
          <MiniStat label="P95" value={fmt(metrics.p95_ms, " ms")} glossary="p95" />
          <MiniStat label="P99" value={fmt(metrics.p99_ms, " ms")} glossary="p99" />
          <MiniStat
            label="Model Load"
            value={fmt(metrics.model_load_times_ms?.[name], " ms")}
          />
        </div>
      )}

      {/* Input */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Input</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {inputType === "text" ? (
            <div className="flex gap-2">
              <Input
                placeholder="Enter text for analysis…"
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handlePredict()}
                className="flex-1"
              />
              <Button onClick={handlePredict} disabled={loading || !textInput}>
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              <div
                className="border-2 border-dashed rounded-xl p-8 text-center cursor-pointer hover:border-primary/50 transition-colors"
                onClick={() => fileRef.current?.click()}
              >
                <Upload className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
                <p className="text-sm text-muted-foreground">
                  {file ? file.name : "Click or drag to upload an image"}
                </p>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files?.[0]) setFile(e.target.files[0]);
                  }}
                />
              </div>
              <Button onClick={handlePredict} disabled={loading || !file} className="w-full">
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Send className="h-4 w-4 mr-2" />
                )}
                Run Inference
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <Card className="border-destructive/50">
          <CardContent className="pt-5 text-sm text-destructive">{error}</CardContent>
        </Card>
      )}

      {/* Result */}
      {result && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center justify-between">
              Result
              {elapsed != null && (
                <Badge variant="outline" className="text-xs font-normal">
                  {elapsed} ms
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {/* Diagnosis shortcut */}
            {typeof result.diagnosis === "string" && (
              <div
                className={`rounded-lg p-4 mb-4 text-center font-semibold ${
                  /abnormal|detected/i.test(result.diagnosis)
                    ? "bg-destructive/10 text-destructive"
                    : "bg-emerald-500/10 text-emerald-600"
                }`}
              >
                {result.diagnosis}
              </div>
            )}

            {/* Sentiment shortcut */}
            {typeof result.sentiment === "string" && (
              <div className="rounded-lg p-4 mb-4 text-center font-semibold bg-primary/10 text-primary">
                {result.sentiment}
                {typeof result.confidence === "string" && (
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    ({result.confidence})
                  </span>
                )}
              </div>
            )}

            {/* Response text shortcut */}
            {typeof result.response === "string" && (
              <p className="mb-4 whitespace-pre-wrap">{result.response}</p>
            )}

            {/* Raw JSON */}
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground mb-1">
                Raw JSON
              </summary>
              <pre className="bg-muted p-3 rounded-md overflow-auto max-h-64">
                {JSON.stringify(result, null, 2)}
              </pre>
            </details>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function MiniStat({ label, value, glossary }: { label: string; value: string; glossary?: string }) {
  return (
    <div className="rounded-lg border p-3" data-glossary={glossary}>
      <p className={`text-xs text-muted-foreground ${glossary ? "cursor-help decoration-dotted underline underline-offset-4 decoration-muted-foreground/40" : ""}`}>{label}</p>
      <p className="font-semibold">{value}</p>
    </div>
  );
}
