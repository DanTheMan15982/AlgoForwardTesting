"use client";

import { useEffect, useRef } from "react";
import { useRealtimeStore } from "@/lib/store";

function getWsUrl() {
  if (typeof window === "undefined") return "";
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/ws`;
}

export function useRealtime() {
  const updatePrice = useRealtimeStore((s) => s.updatePrice);
  const patchEval = useRealtimeStore((s) => s.patchEval);
  const setWsConnected = useRealtimeStore((s) => s.setWsConnected);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectingRef = useRef(false);

  useEffect(() => {
    let pollingId: ReturnType<typeof setInterval> | null = null;
    let destroyed = false;

    const startPolling = () => {
      if (pollingId) return;
      pollingId = setInterval(async () => {
        const [pricesRes, evalsRes] = await Promise.all([fetch("/api/prices"), fetch("/api/evals")]);
        if (pricesRes.ok) {
          const prices = await pricesRes.json();
          useRealtimeStore.getState().setPrices(prices);
        }
        if (evalsRes.ok) {
          const evals = await evalsRes.json();
          useRealtimeStore.getState().setEvals(evals);
        }
      }, 5000);
    };

    const stopPolling = () => {
      if (pollingId) {
        clearInterval(pollingId);
        pollingId = null;
      }
    };

    const connect = () => {
      if (destroyed || reconnectingRef.current) return;
      reconnectingRef.current = true;
      const wsUrl = getWsUrl();
      if (!wsUrl) {
        reconnectingRef.current = false;
        return;
      }
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectingRef.current = false;
        setWsConnected(true);
        stopPolling();
      };

      ws.onclose = () => {
        reconnectingRef.current = false;
        setWsConnected(false);
        startPolling();
        if (!destroyed && !reconnectTimeoutRef.current) {
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectTimeoutRef.current = null;
            connect();
          }, 3000);
        }
      };

      ws.onerror = () => {
        setWsConnected(false);
        ws.close();
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === "prices") {
            useRealtimeStore.getState().setPrices(payload.data);
          }
          if (payload.type === "price_update") {
            const price = payload.data;
            if (price?.symbol) {
              updatePrice(price.symbol, price);
            }
          }
          if (payload.type === "eval_update") {
            const data = payload.data as { eval_id: string } & Record<string, unknown>;
            const { eval_id, ...rest } = data;
            patchEval(eval_id, rest as any);
          }
        } catch {
          return;
        }
      };
    };

    connect();
    startPolling();

    return () => {
      destroyed = true;
      stopPolling();
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      wsRef.current?.close();
    };
  }, [setWsConnected, updatePrice, patchEval]);
}
