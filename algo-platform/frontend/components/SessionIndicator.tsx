"use client";

import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";

type SessionKey = "ASIA" | "LONDON" | "NY" | "OFF";

const sessionStyles: Record<SessionKey, string> = {
  ASIA: "border-neonMagenta/40 bg-neonMagenta/10 text-neonMagenta",
  LONDON: "border-neon/40 bg-neon/10 text-neon",
  NY: "border-success/40 bg-success/10 text-success",
  OFF: "border-border/70 bg-panelSoft/60 text-slate-400"
};

function getSession(utcHour: number): SessionKey {
  if (utcHour >= 0 && utcHour < 8) return "ASIA";
  if (utcHour >= 8 && utcHour < 13) return "LONDON";
  if (utcHour >= 13 && utcHour < 22) return "NY";
  return "OFF";
}

export function SessionIndicator() {
  const [session, setSession] = useState<SessionKey>(() => getSession(new Date().getUTCHours()));

  useEffect(() => {
    const update = () => setSession(getSession(new Date().getUTCHours()));
    update();
    const timer = setInterval(update, 60000);
    return () => clearInterval(timer);
  }, []);

  const className = useMemo(() => sessionStyles[session], [session]);

  return (
    <Badge
      className={`px-3 py-1 text-[13px] tracking-[0.2em] transition-colors duration-200 ${className}`}
    >
      {session}
    </Badge>
  );
}
