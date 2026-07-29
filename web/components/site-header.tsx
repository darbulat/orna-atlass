"use client";

import Link from "next/link";

import { AnalyticsLink } from "./analytics-link";

type SiteHeaderProps = {
  className?: string;
  active?: "map" | "collections" | "about" | "membership";
};

function HeaderLinks({ active }: Pick<SiteHeaderProps, "active">) {
  return (
    <>
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
    </>
  );
}

export function SiteHeader({ className = "", active }: SiteHeaderProps) {
  return (
    <nav className={["site-nav", className].filter(Boolean).join(" ")} aria-label="Primary navigation">
      <Link className="site-wordmark" href="/">ORNA Atlas</Link>
      <div className="site-menu-links site-menu-links-desktop">
        <HeaderLinks active={active} />
      </div>
      <details className="site-menu site-menu-mobile">
        <summary>Menu</summary>
        <div className="site-menu-links">
          <HeaderLinks active={active} />
        </div>
      </details>
    </nav>
  );
}
