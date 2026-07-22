"use client";

import { useEffect } from "react";
import { apiUrl } from "../lib/api/sessions";

const eventNames = new Set([
  "globe_view", "session_preview_start", "session_preview_second", "locked_point_hit", "paywall_shown",
  "signup_started", "signup_completed", "member_session_play", "subscription_intent", "collections_view",
  "search_opened", "login_opened", "membership_cta_click", "marker_click", "reset_view_click", "time_filter_dawn", "time_filter_day",
  "time_filter_dusk", "time_filter_night", "carousel_scroll", "location_search", "card_inline_play", "card_open",
  "see_all_click", "player_play", "player_pause", "player_seek", "favorite_add", "favorite_requires_login",
  "player_next", "player_prev", "timeline_species_click", "session_close", "paywall_signup_click",
  "paywall_learn_more", "paywall_dismissed", "signup_email_submit", "membership_reserve_click",
  "point_opened",
  "play_started",
  "favorite_clicked",
  "lock_clicked",
  "registration_started",
  "membership_interest_submitted",
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
  "globe", "globe_controls", "time_filter", "location_search", "location_carousel", "popular_locations",
  "collections",
  "globe_marker",
  "location_card",
  "session_overlay",
  "soft_paywall",
  "header",
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

    const params = new URLSearchParams(window.location.search);
    if (params.get("magic") === "success") {
      persistEvent(new CustomEvent("orna:analytics", {
        detail: { name: "signup_completed", placement: "membership_form" },
      }));
      params.delete("magic");
      params.delete("magic_error");
      const query = params.toString();
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${query ? `?${query}` : ""}`,
      );
    }

    return () => window.removeEventListener("orna:analytics", persistEvent);
  }, []);

  return null;
}
