"use client";

import { useState, useEffect, type ReactNode } from "react";
import { ApiKeyContext } from "@/lib/use-api-key";
import { GlossaryTooltipProvider } from "@/components/glossary-tooltip";

const STORAGE_KEY = "opendeploy_api_key";

export function Providers({ children }: { children: ReactNode }) {
  const [apiKey, setApiKeyState] = useState("");

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) setApiKeyState(stored);
  }, []);

  function setApiKey(key: string) {
    setApiKeyState(key);
    localStorage.setItem(STORAGE_KEY, key);
  }

  return (
    <ApiKeyContext.Provider value={{ apiKey, setApiKey }}>
      <GlossaryTooltipProvider>
        {children}
      </GlossaryTooltipProvider>
    </ApiKeyContext.Provider>
  );
}
