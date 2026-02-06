"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
  useEffect,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { findGlossaryEntry, fetchAndCacheEntry, type GlossaryEntry } from "@/lib/glossary";

/* ── Context ────────────────────────────────────────────────────── */

interface TooltipCtx {
  show: (entry: GlossaryEntry, x: number, y: number) => void;
  hide: () => void;
}

const Ctx = createContext<TooltipCtx>({ show: () => {}, hide: () => {} });

export function useGlossaryTooltip() {
  return useContext(Ctx);
}

/* ── Provider (wrap the app) ────────────────────────────────────── */

export function GlossaryTooltipProvider({ children }: { children: ReactNode }) {
  const [entry, setEntry] = useState<GlossaryEntry | null>(null);
  const [loading, setLoading] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [visible, setVisible] = useState(false);
  const hideTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [mounted, setMounted] = useState(false);
  const lastKey = useRef<string>("");

  useEffect(() => setMounted(true), []);

  const show = useCallback((e: GlossaryEntry, x: number, y: number) => {
    clearTimeout(hideTimer.current);
    setEntry(e);
    setPos({ x, y });
    setVisible(true);
  }, []);

  const hide = useCallback(() => {
    hideTimer.current = setTimeout(() => {
      setVisible(false);
      setLoading(false);
    }, 150);
  }, []);

  /* ── Global delegated listener ─────────────────────────────── */
  useEffect(() => {
    function onPointerMove(ev: PointerEvent) {
      const target = ev.target as HTMLElement | null;
      if (!target) return;

      const el = target.closest<HTMLElement>("[data-glossary]");
      if (el) {
        const key = el.getAttribute("data-glossary") ?? "";

        // Show fallback immediately (no flicker)
        const found = findGlossaryEntry(key);
        if (found) {
          show(found, ev.clientX, ev.clientY);
        } else {
          // No fallback — show a loading placeholder
          show(
            { term: key, short: "Looking up…", category: undefined },
            ev.clientX,
            ev.clientY,
          );
          setLoading(true);
        }

        // Fire async AI fetch in background (de-duped + cached)
        if (key !== lastKey.current) {
          lastKey.current = key;
          fetchAndCacheEntry(key).then((aiEntry) => {
            if (aiEntry && lastKey.current === key) {
              setEntry(aiEntry);
              setLoading(false);
            }
          });
        }
        return;
      }

      if (visible) {
        lastKey.current = "";
        hide();
      }
    }

    document.addEventListener("pointermove", onPointerMove, { passive: true });
    return () => document.removeEventListener("pointermove", onPointerMove);
  }, [show, hide, visible]);

  return (
    <Ctx.Provider value={{ show, hide }}>
      {children}
      {mounted &&
        createPortal(
          <GlassTooltip entry={entry} pos={pos} visible={visible} loading={loading} />,
          document.body
        )}
    </Ctx.Provider>
  );
}

/* ── Glassmorphic floating tooltip ──────────────────────────────── */

function GlassTooltip({
  entry,
  pos,
  visible,
  loading,
}: {
  entry: GlossaryEntry | null;
  pos: { x: number; y: number };
  visible: boolean;
  loading: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [adjusted, setAdjusted] = useState(pos);

  useEffect(() => {
    if (!ref.current || !visible) return;
    const rect = ref.current.getBoundingClientRect();
    const pad = 16;
    let x = pos.x + 14;
    let y = pos.y + 14;

    if (x + rect.width + pad > window.innerWidth) {
      x = pos.x - rect.width - 14;
    }
    if (y + rect.height + pad > window.innerHeight) {
      y = pos.y - rect.height - 14;
    }
    setAdjusted({ x: Math.max(pad, x), y: Math.max(pad, y) });
  }, [pos, visible]);

  if (!entry) return null;

  const categoryColor: Record<string, string> = {
    Metric: "bg-blue-500/20 text-blue-300 border-blue-500/30",
    Infra: "bg-purple-500/20 text-purple-300 border-purple-500/30",
    ML: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
    Cost: "bg-amber-500/20 text-amber-300 border-amber-500/30",
    Platform: "bg-cyan-500/20 text-cyan-300 border-cyan-500/30",
  };

  return (
    <div
      ref={ref}
      className="fixed z-[9999] pointer-events-none select-none"
      style={{
        left: adjusted.x,
        top: adjusted.y,
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(4px)",
        transition: "opacity 180ms ease, transform 180ms ease",
      }}
    >
      <div
        className="
          max-w-xs rounded-xl px-4 py-3 space-y-1.5
          border border-white/[0.12]
          shadow-[0_8px_32px_rgba(0,0,0,0.45)]
        "
        style={{
          background: "rgba(15, 18, 30, 0.72)",
          backdropFilter: "blur(20px) saturate(160%)",
          WebkitBackdropFilter: "blur(20px) saturate(160%)",
        }}
      >
        {/* Header row */}
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-white/90 leading-tight">
            {entry.term}
          </span>
          {entry.category && (
            <span
              className={`
                inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border
                ${categoryColor[entry.category] ?? "bg-white/10 text-white/60 border-white/10"}
              `}
            >
              {entry.category}
            </span>
          )}
          {loading && (
            <span className="inline-block w-3 h-3 rounded-full border-2 border-white/30 border-t-white/80 animate-spin" />
          )}
        </div>

        {/* Short description */}
        <p className={`text-[12px] leading-relaxed text-white/70 ${loading ? "animate-pulse" : ""}`}>
          {entry.short}
        </p>

        {/* Detail */}
        {entry.detail && (
          <p className="text-[11px] leading-relaxed text-white/45 pt-0.5">
            {entry.detail}
          </p>
        )}

        {/* AI badge */}
        {!loading && entry.detail && (
          <div className="flex items-center gap-1 pt-1">
            <span className="text-[9px] text-white/25">✦ AI-generated</span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Convenience wrapper ────────────────────────────────────────── */

export function Glossary({
  term,
  children,
  className,
}: {
  term: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      data-glossary={term}
      className={`
        cursor-help
        decoration-dotted underline underline-offset-4
        decoration-muted-foreground/40
        ${className ?? ""}
      `}
    >
      {children}
    </span>
  );
}
