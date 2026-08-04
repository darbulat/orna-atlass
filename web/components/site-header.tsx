"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

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
      >Profile</AnalyticsLink>
    </>
  );
}

export function SiteHeader({ className = "", active }: SiteHeaderProps) {
  const mobileMenuRef = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    const closeMenu = (restoreFocus = false) => {
      const menu = mobileMenuRef.current;
      if (!menu?.open) return;
      menu.removeAttribute("open");
      if (restoreFocus) menu.querySelector("summary")?.focus();
    };
    const handlePointerDown = (event: PointerEvent) => {
      const menu = mobileMenuRef.current;
      if (menu?.open && !menu.contains(event.target as Node)) closeMenu();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeMenu(true);
    };
    const handleScroll = () => closeMenu();

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("scroll", handleScroll);
    };
  }, []);

  return (
    <nav className={["site-nav", className].filter(Boolean).join(" ")} aria-label="Primary navigation">
      <Link className="site-wordmark" href="/">ORNA Atlas</Link>
      <div className="site-menu-links site-menu-links-desktop">
        <HeaderLinks active={active} />
      </div>
      <details className="site-menu site-menu-mobile" ref={mobileMenuRef}>
        <summary aria-label="Menu">
          <span className="site-menu-icon" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
        </summary>
        <div
          className="site-menu-links"
          onClick={(event) => {
            if (event.target instanceof Element && event.target.closest("a")) {
              mobileMenuRef.current?.removeAttribute("open");
            }
          }}
        >
          <HeaderLinks active={active} />
        </div>
      </details>
    </nav>
  );
}
