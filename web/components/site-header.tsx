"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AnalyticsLink } from "./analytics-link";

type SiteHeaderProps = {
  className?: string;
  active?: "map" | "collections" | "about" | "membership";
};

export function SiteHeader({ className = "", active }: SiteHeaderProps) {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 700px)");
    const updateViewport = () => setIsMobile(query.matches);
    updateViewport();
    query.addEventListener("change", updateViewport);
    return () => query.removeEventListener("change", updateViewport);
  }, []);

  return (
    <nav className={["site-nav", className].filter(Boolean).join(" ")} aria-label="Primary navigation">
      <Link className="site-wordmark" href="/">ORNA Atlas</Link>
      <details className="site-menu" open={isMobile ? undefined : true}>
        <summary>Menu</summary>
        <div className="site-menu-links">
          <AnalyticsLink
            className={active === "collections" ? "active" : undefined}
            destination="/collections"
            eventName="collections_view"
            placement="header"
          >Collections</AnalyticsLink>
          <Link className={active === "about" ? "active" : undefined} href="/about">About</Link>
          <AnalyticsLink
            className={active === "membership" ? "active" : undefined}
            destination="/membership?mode=register"
            eventName="membership_cta_click"
            placement="header"
          >Subscribe</AnalyticsLink>
        </div>
      </details>
    </nav>
  );
}
