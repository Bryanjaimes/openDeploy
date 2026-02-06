"use client";

import { useEffect, useState } from "react";
import { useApiKey } from "@/lib/use-api-key";
import { fetchHistory, type HistoryEntry } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function HistoryPage() {
  const { apiKey } = useApiKey();
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!apiKey) return;
    fetchHistory(apiKey)
      .then(setEntries)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [apiKey]);

  if (!apiKey) {
    return (
      <p className="text-sm text-muted-foreground">
        Enter your API key in the sidebar to view history.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">History</h1>
        <p className="text-sm text-muted-foreground">
          Past prediction results, most recent first.
        </p>
      </div>

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {!loading && entries.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No predictions yet. Run some inferences to see them here.
        </p>
      )}

      <div className="space-y-3">
        {entries.map((e) => {
          const diag = e.result?.diagnosis as string | undefined;
          const isAbnormal = diag && /abnormal|detected/i.test(diag);
          return (
            <Card key={e.id} className="border-l-4" style={{ borderLeftColor: isAbnormal ? "hsl(var(--destructive))" : diag ? "hsl(142 71% 45%)" : "hsl(var(--border))" }}>
              <CardContent className="py-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-sm">{e.model}</span>
                  <span className="text-xs text-muted-foreground">
                    {new Date(e.timestamp).toLocaleString()}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground truncate">→ {e.input}</p>
                {diag ? (
                  <Badge variant={isAbnormal ? "destructive" : "default"}>
                    {diag}
                  </Badge>
                ) : (
                  <pre className="text-xs bg-muted p-2 rounded-md overflow-auto max-h-24">
                    {JSON.stringify(e.result, null, 2)}
                  </pre>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
