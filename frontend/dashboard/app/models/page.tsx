"use client";

import { useEffect, useState } from "react";
import { useApiKey } from "@/lib/use-api-key";
import { fetchModels, type Model } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";

export default function ModelsPage() {
  const { apiKey } = useApiKey();
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!apiKey) return;
    fetchModels(apiKey)
      .then(setModels)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [apiKey]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Models</h1>
        <p className="text-sm text-muted-foreground">
          All registered model endpoints. Click a model to run inference.
        </p>
      </div>

      {!apiKey && (
        <p className="text-sm text-muted-foreground">
          Enter your API key in the sidebar to load models.
        </p>
      )}

      {apiKey && loading && <p className="text-sm text-muted-foreground">Loading…</p>}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {models.map((m) => (
          <Link key={m.name} href={`/models/${encodeURIComponent(m.name)}`}>
            <Card className="h-full hover:border-primary/50 transition-colors cursor-pointer">
              <CardContent className="pt-5 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold text-sm truncate">{m.name}</h3>
                  <Badge variant={m.ready ? "default" : "secondary"} className="shrink-0">
                    {m.ready ? "Ready" : "Loading"}
                  </Badge>
                </div>
                <div className="flex gap-2 flex-wrap">
                  <Badge variant="outline">{m.input_type}</Badge>
                  <Badge variant="outline">v{m.version}</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  Endpoint: <code data-glossary="inference">/models/{m.name}/predict</code>
                </p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
