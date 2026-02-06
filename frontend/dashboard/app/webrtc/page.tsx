"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { useApiKey } from "@/lib/use-api-key";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Video, StopCircle } from "lucide-react";

export default function WebRTCPage() {
  const { apiKey } = useApiKey();
  const [gateway, setGateway] = useState("");
  const [api, setApi] = useState("");
  const [interval, setInterval_] = useState(100);
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState("Idle");
  const [lastResult, setLastResult] = useState<Record<string, unknown> | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!gateway) setGateway(`${window.location.origin}/webrtc`);
    if (!api) setApi(`${window.location.origin}/api`);
  }, []);

  const encodeFrame = useCallback((imageData: ImageData) => {
    const { width, height, data } = imageData;
    const rgb = new Uint8Array(width * height * 3);
    let s = 0, d = 0;
    while (s < data.length) {
      rgb[d++] = data[s];
      rgb[d++] = data[s + 1];
      rgb[d++] = data[s + 2];
      s += 4;
    }
    const header = new ArrayBuffer(12);
    const view = new DataView(header);
    view.setUint32(0, width, true);
    view.setUint32(4, height, true);
    view.setUint32(8, 1, true); // format = RGB
    const payload = new Uint8Array(12 + rgb.length);
    payload.set(new Uint8Array(header), 0);
    payload.set(rgb, 12);
    return payload;
  }, []);

  async function start() {
    setStatus("Connecting…");
    try {
      const pc = new RTCPeerConnection();
      const dc = pc.createDataChannel("frames");
      pcRef.current = pc;
      dcRef.current = dc;

      const localStream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480 },
        audio: false,
      });
      streamRef.current = localStream;
      if (videoRef.current) videoRef.current.srcObject = localStream;
      pc.addTrack(localStream.getVideoTracks()[0], localStream);

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const res = await fetch(`${gateway}/offer`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
        body: JSON.stringify({ sdp: offer.sdp, type: offer.type }),
      });
      if (!res.ok) throw new Error(`Gateway error: ${res.status}`);
      const answer = await res.json();
      await pc.setRemoteDescription(new RTCSessionDescription(answer));

      dc.onopen = () => {
        setStatus("Streaming");
        setStreaming(true);
        timerRef.current = setInterval(() => sendFrame(), interval);
      };
      dc.onclose = () => setStatus("DataChannel closed");
      dc.onerror = () => setStatus("DataChannel error");
    } catch (e) {
      setStatus((e as Error).message);
    }
  }

  async function sendFrame() {
    const dc = dcRef.current;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!dc || dc.readyState !== "open" || !video || !canvas) return;

    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    dc.send(encodeFrame(imageData));

    try {
      const res = await fetch(`${api}/vision/stream/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
        body: JSON.stringify({ model: "diabetic-retinopathy-glaucoma-detector" }),
      });
      if (res.ok) {
        const data = await res.json();
        setLastResult(data.metrics ?? data);
      }
    } catch {}
  }

  function stop() {
    if (timerRef.current) clearInterval(timerRef.current);
    dcRef.current?.close();
    pcRef.current?.close();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    pcRef.current = null;
    dcRef.current = null;
    streamRef.current = null;
    setStreaming(false);
    setStatus("Stopped");
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">WebRTC Stream</h1>
        <p className="text-sm text-muted-foreground">
          Stream camera frames over WebRTC for real-time vision inference.
        </p>
      </div>

      {/* Config */}
      <Card>
        <CardContent className="pt-5 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Gateway URL</label>
              <Input value={gateway} onChange={(e) => setGateway(e.target.value)} />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">API URL</label>
              <Input value={api} onChange={(e) => setApi(e.target.value)} />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Interval (ms)</label>
              <Input
                type="number"
                min={10}
                value={interval}
                onChange={(e) => setInterval_(Number(e.target.value))}
              />
            </div>
          </div>

          <div className="flex gap-3">
            <Button onClick={start} disabled={streaming}>
              <Video className="h-4 w-4 mr-2" /> Start
            </Button>
            <Button variant="secondary" onClick={stop} disabled={!streaming}>
              <StopCircle className="h-4 w-4 mr-2" /> Stop
            </Button>
            <Badge variant="outline" className="ml-auto self-center">
              {status}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Video */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Camera Preview</CardTitle>
          </CardHeader>
          <CardContent>
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="w-full rounded-lg border bg-muted"
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Capture Buffer</CardTitle>
          </CardHeader>
          <CardContent>
            <canvas
              ref={canvasRef}
              width={640}
              height={480}
              className="w-full rounded-lg border bg-muted"
            />
          </CardContent>
        </Card>
      </div>

      {/* Results */}
      {lastResult && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Latest Result</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-xs bg-muted p-3 rounded-md overflow-auto max-h-48">
              {JSON.stringify(lastResult, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
