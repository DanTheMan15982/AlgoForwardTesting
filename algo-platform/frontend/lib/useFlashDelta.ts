"use client";

import { useEffect, useRef, useState } from "react";

export type FlashDirection = "up" | "down" | "flat";

export function useFlashDelta(key: string, value?: number | null, durationMs = 700) {
  const prevRef = useRef<number | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [direction, setDirection] = useState<FlashDirection>("flat");
  const [flash, setFlash] = useState(false);

  useEffect(() => {
    prevRef.current = null;
    setDirection("flat");
    setFlash(false);
  }, [key]);

  useEffect(() => {
    if (value == null || Number.isNaN(value)) {
      return;
    }
    if (prevRef.current == null) {
      prevRef.current = value;
      return;
    }
    if (value === prevRef.current) {
      return;
    }
    const nextDirection: FlashDirection = value > prevRef.current ? "up" : "down";
    prevRef.current = value;
    setDirection(nextDirection);
    setFlash(true);
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    timeoutRef.current = setTimeout(() => setFlash(false), durationMs);
  }, [value, durationMs]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return { direction, flash };
}
