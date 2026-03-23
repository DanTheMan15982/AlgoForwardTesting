"use client";

import { formatDateTime } from "@/lib/format";

type EventItem = {
  id: string;
  ts: string;
  type: string;
  payload: Record<string, unknown>;
};

type EventListProps = {
  events: EventItem[];
};

export function EventList({ events }: EventListProps) {
  return (
    <div className="max-h-[320px] space-y-3 overflow-y-auto overflow-x-hidden pr-2">
      {events.map((event) => (
        <div
          key={event.id}
          className="rounded-lg border border-border/70 bg-panel/70 p-3 shadow-glowSoft"
        >
          <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.2em] text-slate-500">
            <span>{event.type}</span>
            <span>{formatDateTime(event.ts)}</span>
          </div>
          <div className="mt-2 text-sm text-slate-300 break-words">
            {JSON.stringify(event.payload)}
          </div>
        </div>
      ))}
    </div>
  );
}
