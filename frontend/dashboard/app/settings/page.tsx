"use client";

import { useApiKey } from "@/lib/use-api-key";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";

export default function SettingsPage() {
  const { apiKey, setApiKey } = useApiKey();

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Platform configuration
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Authentication</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground font-medium">
              API Key
            </label>
            <Input
              type="password"
              placeholder="OPENDEPLOY_API_KEY"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Stored in localStorage. Used for all API requests.
            </p>
          </div>
        </CardContent>
      </Card>

      <Separator />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Endpoints</CardTitle>
        </CardHeader>
        <CardContent className="text-sm space-y-2">
          <Row label="API" value={process.env.NEXT_PUBLIC_API_URL ?? "/api (proxied)"} />
          <Row label="Prometheus" value="http://localhost:9090" />
          <Row label="Grafana" value="http://localhost:3002" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">About</CardTitle>
        </CardHeader>
        <CardContent className="text-sm space-y-1">
          <Row label="Version" value="0.7.0" />
          <Row label="Framework" value="Next.js + shadcn/ui" />
          <Row label="Backend" value="FastAPI + Prometheus" />
          <Row label="CLI" value="Go + Cobra" />
        </CardContent>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
