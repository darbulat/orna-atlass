"use client";

import { useEffect } from "react";
import { apiUrl } from "../lib/api/sessions";

const eventNames = new Set([
  "sample_play_started",
  "listening_30_seconds",
  "listening_5_minutes",
  "registration_completed",
  "hero_cta_clicked",
  "listening_path_selected",
  "membership_cta_clicked",
  "final_cta_clicked",
]);

const placements = new Set([
  "global_player",
  "hero_sample",
  "hero_primary",
  "hero_secondary",
  "intent_focus",
  "intent_restore",
  "intent_unwind",
  "intent_explore",
  "pricing_card",
  "footer_atlas",
  "footer_membership",
  "membership_form",
]);

export function AnalyticsBridge() {
  useEffect(() => {
    const persistEvent = (event: Event) => {
      const detail = (event as CustomEvent<unknown>).detail;
      if (!detail || typeof detail !== "object") return;

      const candidate = detail as { name?: unknown; placement?: unknown };
      if (typeof candidate.name !== "string" || !eventNames.has(candidate.name)) return;
      const placement = typeof candidate.placement === "string"
        ? candidate.placement
        : "global_player";
      if (!placements.has(placement)) return;

      void fetch(apiUrl("/api/v1/analytics/events"), {
        method: "POST",
        credentials: "omit",
        keepalive: true,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: candidate.name, placement }),
      }).catch(() => {
        // Analytics must never interrupt playback, registration, or navigation.
      });
    };

    window.addEventListener("orna:analytics", persistEvent);
    return () => window.removeEventListener("orna:analytics", persistEvent);
  }, []);

  return null;
}
