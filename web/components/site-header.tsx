"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { apiErrorMessage } from "../lib/api/client";
import { requestMagicLink } from "../lib/api/auth";
import { AnalyticsLink } from "./analytics-link";

type SiteHeaderProps = {
  className?: string;
  active?: "map" | "collections" | "about" | "membership";
};

type HeaderDialogProps = {
  labelledBy: string;
  onClose: () => void;
  children: ReactNode;
};

function HeaderDialog({ labelledBy, onClose, children }: HeaderDialogProps) {
  const dialogRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    const backdrop = dialog?.parentElement;
    const backgroundElements = Array.from(backdrop?.parentElement?.children ?? [])
      .filter((element): element is HTMLElement => element instanceof HTMLElement && element !== backdrop);
    const previousBackgroundState = backgroundElements.map((element) => ({
      element,
      inert: element.inert,
      ariaHidden: element.getAttribute("aria-hidden"),
    }));
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    for (const element of backgroundElements) {
      element.inert = true;
      element.setAttribute("aria-hidden", "true");
    }
    const focusableElements = () => Array.from(dialog?.querySelectorAll<HTMLElement>(
      "button:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex='-1'])",
    ) ?? []);
    const containFocus = (event: FocusEvent) => {
      if (dialog && event.target instanceof Node && !dialog.contains(event.target)) {
        focusableElements()[0]?.focus();
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab") return;
      const focusable = focusableElements();
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!dialog?.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("focusin", containFocus);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("focusin", containFocus);
      for (const { element, inert, ariaHidden } of previousBackgroundState) {
        element.inert = inert;
        if (ariaHidden === null) element.removeAttribute("aria-hidden");
        else element.setAttribute("aria-hidden", ariaHidden);
      }
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  return (
    <div className="header-dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        ref={dialogRef}
        className="header-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button type="button" className="header-dialog-close" aria-label="Close" onClick={onClose}>×</button>
        {children}
      </section>
    </div>
  );
}

export function SiteHeader({ className = "", active }: SiteHeaderProps) {
  const searchTriggerRef = useRef<HTMLButtonElement | null>(null);
  const loginTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [dialog, setDialog] = useState<"search" | "login" | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [email, setEmail] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginMessage, setLoginMessage] = useState<string | null>(null);

  function closeDialog() {
    const closed = dialog;
    setDialog(null);
    window.setTimeout(() => {
      if (closed === "search") searchTriggerRef.current?.focus();
      if (closed === "login") loginTriggerRef.current?.focus();
    }, 0);
  }

  function openSearch() {
    window.dispatchEvent(new CustomEvent("orna:analytics", {
      detail: { name: "search_opened", placement: "header" },
    }));
    setDialog("search");
  }

  function openLogin() {
    window.dispatchEvent(new CustomEvent("orna:analytics", {
      detail: { name: "login_opened", placement: "header" },
    }));
    setLoginMessage(null);
    setDialog("login");
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = searchQuery.trim();
    if (!query) return;
    const atlasSearch = document.querySelector<HTMLInputElement>("#atlas-search");
    if (atlasSearch) {
      window.dispatchEvent(new CustomEvent("orna:open-search", { detail: { query } }));
      closeDialog();
      return;
    }
    window.location.assign(`/?search=${encodeURIComponent(query)}#atlas-search`);
  }

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginBusy(true);
    setLoginMessage(null);
    try {
      await requestMagicLink(email, `${window.location.pathname}${window.location.search}`);
      setLoginMessage("Check your email. The one-time sign-in link expires in 15 minutes.");
    } catch (error) {
      setLoginMessage(apiErrorMessage(error, "Email sign-in is temporarily unavailable."));
    } finally {
      setLoginBusy(false);
    }
  }

  return (
    <>
      <nav className={["site-nav", className].filter(Boolean).join(" ")} aria-label="Primary navigation">
        <Link className="site-wordmark" href="/">ORNA Atlas</Link>
        <div>
          <Link className={active === "map" ? "active" : undefined} href="/#atlas-entry">Map</Link>
          <AnalyticsLink
            className={active === "collections" ? "active" : undefined}
            destination="/collections"
            eventName="collections_view"
            placement="header"
          >Collections</AnalyticsLink>
          <Link className={active === "about" ? "active" : undefined} href="/about">About</Link>
          <button ref={searchTriggerRef} type="button" className="header-search-button" aria-label="Open search" onClick={openSearch}>Search</button>
          <button ref={loginTriggerRef} type="button" className="header-login-button" onClick={openLogin}>Sign in</button>
          <AnalyticsLink
            className={active === "membership" ? "active" : undefined}
            destination="/membership?mode=register"
            eventName="membership_cta_click"
            placement="header"
          >Subscribe</AnalyticsLink>
        </div>
      </nav>
      {dialog === "search" ? (
        <HeaderDialog labelledBy="header-search-title" onClose={closeDialog}>
          <p className="eyebrow">Explore ORNA Atlas</p>
          <h2 id="header-search-title">Search locations and recordings</h2>
          <form className="header-dialog-form" onSubmit={submitSearch}>
            <label htmlFor="header-search-query">Search</label>
            <input
              id="header-search-query"
              autoFocus
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Forest, country, or recording"
            />
            <button type="submit">Show results</button>
          </form>
        </HeaderDialog>
      ) : null}
      {dialog === "login" ? (
        <HeaderDialog labelledBy="header-login-title" onClose={closeDialog}>
          <p className="eyebrow">Your ORNA account</p>
          <h2 id="header-login-title">Sign in without leaving the atlas</h2>
          <form className="header-dialog-form" onSubmit={submitLogin}>
            <label htmlFor="header-login-email">Email address</label>
            <input
              id="header-login-email"
              type="email"
              autoComplete="email"
              autoFocus
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
            />
            <button type="submit" disabled={loginBusy}>{loginBusy ? "Please wait…" : "Email me a sign-in link"}</button>
          </form>
          {loginMessage ? <p role="status">{loginMessage}</p> : null}
          <Link href="/membership?mode=login">Use password or social sign-in</Link>
        </HeaderDialog>
      ) : null}
    </>
  );
}
