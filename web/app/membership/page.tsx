"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";

import { SiteHeader } from "../../components/site-header";
import { ApiError, apiErrorMessage } from "../../lib/api/client";
import {
  fetchCurrentUser,
  fetchMembership,
  fetchOAuthProviders,
  login,
  logout,
  oauthStartUrl,
  register,
  requestMagicLink,
  type Membership,
  type OAuthProvider,
  type User,
} from "../../lib/api/auth";

type AuthMode = "login" | "register";
type MembershipEntryMode = "default" | AuthMode;

const providerLabels: Record<OAuthProvider, string> = {
  google: "Google",
  apple: "Apple",
  facebook: "Facebook",
};

function ProviderIcon({ provider }: { provider: OAuthProvider }) {
  if (provider === "google") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path fill="#4285F4" d="M21.6 12.2c0-.7-.1-1.4-.2-2H12v3.9h5.4a4.6 4.6 0 0 1-2 3v2.6h3.3c1.9-1.8 2.9-4.4 2.9-7.5Z" />
        <path fill="#34A853" d="M12 22c2.7 0 5-.9 6.7-2.3l-3.3-2.6c-.9.6-2.1 1-3.4 1a5.9 5.9 0 0 1-5.5-4.1H3.1v2.7A10 10 0 0 0 12 22Z" />
        <path fill="#FBBC05" d="M6.5 14a6 6 0 0 1 0-3.8V7.5H3.1a10 10 0 0 0 0 9.2L6.5 14Z" />
        <path fill="#EA4335" d="M12 6.1c1.5 0 2.8.5 3.9 1.5l2.9-2.8A9.7 9.7 0 0 0 3.1 7.5l3.4 2.7A5.9 5.9 0 0 1 12 6.1Z" />
      </svg>
    );
  }
  if (provider === "apple") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path fill="currentColor" d="M17.1 12.6c0-2.5 2.1-3.7 2.2-3.8a4.8 4.8 0 0 0-3.8-2c-1.6-.2-3.1 1-3.9 1-.8 0-2-1-3.3-1-1.7 0-3.3 1-4.2 2.5-1.8 3.1-.5 7.7 1.3 10.2.9 1.2 1.9 2.6 3.3 2.5 1.3-.1 1.8-.8 3.4-.8 1.5 0 2 .8 3.4.8 1.4 0 2.3-1.3 3.2-2.5 1-1.5 1.5-3 1.5-3.1-.1 0-3.1-1.2-3.1-3.8ZM14.4 5.1c.7-.9 1.2-2.1 1.1-3.3-1.1.1-2.4.7-3.2 1.6-.7.8-1.3 2-1.1 3.2 1.2.1 2.5-.6 3.2-1.5Z" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path fill="#1877F2" d="M22 12a10 10 0 1 0-11.6 9.9v-7H7.9V12h2.5V9.8c0-2.5 1.5-3.9 3.8-3.9 1.1 0 2.2.2 2.2.2v2.5h-1.2c-1.2 0-1.6.7-1.6 1.5V12h2.7l-.4 2.9h-2.3v7A10 10 0 0 0 22 12Z" />
      <path fill="#fff" d="m15.9 14.9.4-2.9h-2.7v-1.9c0-.8.4-1.5 1.6-1.5h1.2V6.1s-1.1-.2-2.2-.2c-2.3 0-3.8 1.4-3.8 3.9V12H7.9v2.9h2.5v7c.5.1 1 .1 1.6.1s1.1 0 1.6-.1v-7h2.3Z" />
    </svg>
  );
}

function SocialLink({ provider, returnTo }: { provider: OAuthProvider; returnTo: string }) {
  const label = providerLabels[provider];
  return (
    <a className="auth-social-link" href={oauthStartUrl(provider, returnTo)} aria-label={`Continue with ${label}`}>
      <ProviderIcon provider={provider} />
      <span>{label}</span>
    </a>
  );
}

function AuthNotice({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <p className="auth-notice" role={error ? "alert" : "status"}>{children}</p>;
}

function oauthFailureMessage(provider: OAuthProvider | null, reason: string | null): string {
  const label = provider ? providerLabels[provider] : "Social";
  if (reason === "cancelled") return `${label} sign-in was cancelled.`;
  if (reason === "account_conflict") {
    return "An account with this email already exists. Use its original sign-in method.";
  }
  if (reason === "unavailable") {
    return `${label} sign-in is temporarily unavailable. Please try again later.`;
  }
  return `${label} sign-in could not be completed. Please try again.`;
}

function internalReturnTo(value: string | null): string {
  return value && value.startsWith("/") && !value.startsWith("//") && !value.includes("\\")
    ? value.split("#", 1)[0]
    : "/membership";
}

function MembershipInformation({ onCreateAccount }: { onCreateAccount?: () => void }) {
  return (
    <section className="membership-information" aria-labelledby="membership-options-heading">
      <p className="eyebrow">Listening options</p>
      <h2 id="membership-options-heading">Free atlas and future membership</h2>
      <div className="membership-comparison">
        <article className="panel">
          <h3>Free account</h3>
          <p><strong>Free.</strong> No payment details required.</p>
          <ul>
            <li>Explore the public globe</li>
            <li>Listen to public field recordings</li>
            <li>Sign in securely by email or password</li>
          </ul>
        </article>
        <article className="panel">
          <h3>Member access</h3>
          <p><strong>Pricing has not been announced.</strong> Checkout is not available.</p>
          <ul>
            <li>Intended for members-only long-form recordings</li>
            <li>Enrollment will be offered only after pricing is shown</li>
            <li>A free account does not unlock member recordings</li>
          </ul>
        </article>
      </div>
      {onCreateAccount ? (
        <button
          type="button"
          onClick={() => {
            window.dispatchEvent(new CustomEvent("orna:analytics", {
              detail: { name: "membership_reserve_click", placement: "membership_form" },
            }));
            window.dispatchEvent(new CustomEvent("orna:analytics", {
              detail: { name: "subscription_intent", placement: "membership_form" },
            }));
            onCreateAccount();
          }}
        >
          Create an account for future membership updates
        </button>
      ) : (
        <p role="status">Membership enrollment is not open yet. No interest reservation has been recorded.</p>
      )}
      <div className="membership-faq">
        <h2>Frequently asked questions</h2>
        <details>
          <summary>Are these sounds generated by AI?</summary>
          <p>No. ORNA Atlas presents field recordings anchored to real landscapes. Automated analysis may annotate bird activity, but it does not generate the recording.</p>
        </details>
        <details>
          <summary>What is included without membership?</summary>
          <p>You can explore the public atlas, collections, and available public sessions. A membership entitlement unlocks recordings marked for members.</p>
        </details>
        <details>
          <summary>Why are some coordinates hidden?</summary>
          <p>Exact locations can put sensitive habitats or species at risk. Public views use generalized coordinates or omit a location when protection requires it.</p>
        </details>
        <details>
          <summary>Are the sessions loops or playlists?</summary>
          <p>No. Sessions preserve the continuity and pace of field recordings instead of assembling short ambient loops.</p>
        </details>
        <details>
          <summary>Can I buy a membership here today?</summary>
          <p>Account and entitlement support is live. Checkout and public subscription pricing are not offered here, so ORNA does not present a fictional price or payment flow.</p>
        </details>
      </div>
    </section>
  );
}

export default function MembershipPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [membership, setMembership] = useState<Membership | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<AuthMode>("login");
  const [entryMode, setEntryMode] = useState<MembershipEntryMode>("default");
  const [message, setMessage] = useState<string | null>(null);
  const [oauthMessage, setOauthMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [accountLoadError, setAccountLoadError] = useState<string | null>(null);
  const [isLoadingAccount, setIsLoadingAccount] = useState(true);
  const [isLoadingMembership, setIsLoadingMembership] = useState(true);
  const [busy, setBusy] = useState(false);
  const [registrationComplete, setRegistrationComplete] = useState(false);
  const [magicLinkSent, setMagicLinkSent] = useState(false);
  const [configuredProviders, setConfiguredProviders] = useState<OAuthProvider[] | null>(null);
  const [providerLoadError, setProviderLoadError] = useState(false);
  const [authReturnTo, setAuthReturnTo] = useState("/membership");
  const authGeneration = useRef(0);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setAuthReturnTo(internalReturnTo(params.get("returnTo")));
    const requestedMode = params.get("mode");
    if (requestedMode === "register" || requestedMode === "login") {
      setMode(requestedMode);
      setEntryMode(requestedMode);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void fetchOAuthProviders()
      .then(({ providers }) => {
        if (!active) return;
        setConfiguredProviders(providers);
        setProviderLoadError(false);
      })
      .catch(() => {
        if (!active) return;
        setConfiguredProviders([]);
        setProviderLoadError(true);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    const generation = authGeneration.current;
    const isCurrent = () => active && generation === authGeneration.current;
    const params = new URLSearchParams(window.location.search);
    const oauthStatus = params.get("oauth");
    const oauthError = params.get("oauth_error");
    const magicStatus = params.get("magic");
    const magicError = params.get("magic_error");
    const providerValue = params.get("oauth_provider");
    const provider = providerValue && providerValue in providerLabels
      ? providerValue as OAuthProvider
      : null;
    const hasCallbackParams = ["oauth", "oauth_provider", "oauth_error", "magic", "magic_error"].some(
      (name) => params.has(name),
    );
    if (hasCallbackParams) {
      params.delete("oauth");
      params.delete("oauth_provider");
      params.delete("oauth_error");
      params.delete("magic");
      params.delete("magic_error");
      const query = params.toString();
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${query ? `?${query}` : ""}`,
      );
    }
    if (oauthStatus === "error" || oauthError) {
      setOauthMessage({
        text: oauthFailureMessage(provider, oauthError),
        error: true,
      });
    }
    if (magicStatus === "error" || magicError) {
      setOauthMessage({
        text: magicError === "invalid_or_expired"
          ? "That sign-in link is invalid or expired. Request a new one."
          : "Email sign-in is temporarily unavailable. Please try again.",
        error: true,
      });
    }
    void (async () => {
      try {
        const currentUser = await fetchCurrentUser();
        if (!isCurrent()) return;
        setUser(currentUser);
        setAccountLoadError(null);
        if (provider && oauthStatus === "success") {
          setOauthMessage({ text: `Signed in with ${providerLabels[provider]}.`, error: false });
        }
        if (magicStatus === "success" || magicStatus === "signup" || magicStatus === "login") {
          setOauthMessage({ text: "Signed in with your email link.", error: false });
        }
        setIsLoadingMembership(true);
        try {
          const currentMembership = await fetchMembership();
          if (!isCurrent()) return;
          setMembership(currentMembership);
        } catch (error) {
          if (!isCurrent()) return;
          setMembership(null);
          setAccountLoadError(apiErrorMessage(error, "Unable to load membership status."));
        } finally {
          if (isCurrent()) setIsLoadingMembership(false);
        }
      } catch (error) {
        if (!isCurrent() || (error instanceof DOMException && error.name === "AbortError")) return;
        setIsLoadingMembership(false);
        if (error instanceof ApiError && error.status === 401) {
          setUser(null);
          setMembership(null);
          setAccountLoadError(null);
          if (provider && oauthStatus === "success") {
            setOauthMessage({
              text: `${providerLabels[provider]} sign-in could not be confirmed. Please try again.`,
              error: true,
            });
          }
        } else {
          setAccountLoadError(apiErrorMessage(error, "Unable to load your account."));
        }
      } finally {
        if (isCurrent()) setIsLoadingAccount(false);
      }
    })();
    return () => { active = false; };
  }, []);

  async function submitMagicLink(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    setMagicLinkSent(false);
    window.dispatchEvent(new CustomEvent("orna:analytics", {
      detail: { name: "signup_email_submit", placement: "membership_form" },
    }));
    try {
      const params = new URLSearchParams(window.location.search);
      await requestMagicLink(email, internalReturnTo(params.get("returnTo")));
      setMagicLinkSent(true);
    } catch (error) {
      setMessage(apiErrorMessage(error, "Email sign-in is temporarily unavailable."));
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const returnTo = internalReturnTo(new URLSearchParams(window.location.search).get("returnTo"));
    const generation = ++authGeneration.current;
    setIsLoadingAccount(false);
    setBusy(true);
    setMessage(null);
    setOauthMessage(null);
    setAccountLoadError(null);
    if (mode !== "register") setRegistrationComplete(false);
    try {
      if (mode === "register") {
        await register(email, password);
        setRegistrationComplete(true);
        window.dispatchEvent(new CustomEvent("orna:analytics", {
          detail: { name: "signup_completed", placement: "membership_form" },
        }));
      }
      const token = await login(email, password);
      if (generation !== authGeneration.current) return;
      setUser(token.user);
      setAccountLoadError(null);
      setPassword("");
      setMembership(null);
      setIsLoadingMembership(true);
      try {
        const currentMembership = await fetchMembership();
        if (generation !== authGeneration.current) return;
        setMembership(currentMembership);
      } catch (error) {
        if (generation !== authGeneration.current) return;
        setAccountLoadError(apiErrorMessage(error, "Unable to load membership status."));
      } finally {
        if (generation === authGeneration.current) setIsLoadingMembership(false);
      }
      if (generation === authGeneration.current && returnTo !== "/membership") {
        router.replace(returnTo);
      }
    } catch (error) {
      if (generation !== authGeneration.current) return;
      setMessage(apiErrorMessage(error, "Authentication failed"));
    } finally {
      if (generation === authGeneration.current) setBusy(false);
    }
  }

  async function signOut() {
    const generation = ++authGeneration.current;
    setBusy(true);
    setMessage(null);
    try {
      await logout();
      if (generation !== authGeneration.current) return;
      setUser(null);
      setMembership(null);
      setOauthMessage(null);
      setAccountLoadError(null);
      setRegistrationComplete(false);
      setEmail("");
      setPassword("");
      setIsLoadingAccount(false);
      setIsLoadingMembership(false);
    } catch (error) {
      if (generation !== authGeneration.current) return;
      setIsLoadingAccount(false);
      setIsLoadingMembership(false);
      setMessage(apiErrorMessage(error, "Logout failed"));
    } finally {
      if (generation === authGeneration.current) setBusy(false);
    }
  }

  if (user) {
    const planLabel = membership?.plan ?? (isLoadingMembership ? "Loading…" : "Unavailable");
    const statusLabel = membership?.status ?? (isLoadingMembership ? "Loading…" : "Unavailable");
    const playbackLabel = membership
      ? (membership.is_entitled ? "Member sessions unlocked" : "Public previews only")
      : (isLoadingMembership ? "Loading…" : "Unavailable");
    return (
      <main className="shell membership-page" id="main-content">
        <SiteHeader active="membership" />
        <p className="eyebrow">ORNA Atlas</p>
        <h1>Your account</h1>
        <section className="panel membership-card" aria-live="polite">
          <p className="eyebrow">Signed in</p>
          <h2>{user.email}</h2>
          <dl>
            <div><dt>Role</dt><dd>{user.role}</dd></div>
            <div><dt>Plan</dt><dd>{planLabel}</dd></div>
            <div><dt>Status</dt><dd>{statusLabel}</dd></div>
            <div><dt>Playback</dt><dd>{playbackLabel}</dd></div>
          </dl>
          <button type="button" onClick={signOut} disabled={busy}>Sign out</button>
        </section>
        {oauthMessage ? <AuthNotice error={oauthMessage.error}>{oauthMessage.text}</AuthNotice> : null}
        {accountLoadError ? <AuthNotice error>{accountLoadError}</AuthNotice> : null}
        {!isLoadingMembership && !membership?.is_entitled ? <MembershipInformation /> : null}
        {message ? <p className="form-message" role="alert">{message}</p> : null}
      </main>
    );
  }

  const isFocusedLogin = entryMode === "login" && mode === "login";
  const authHeading = isFocusedLogin
    ? "Sign in to ORNA Atlas"
    : mode === "register"
      ? "Create your free ORNA account"
      : "Sign in or create your account";
  const authIntro = isFocusedLogin
    ? "Use your email link, password, or social account to return to your atlas listening."
    : mode === "register"
      ? "Create a free account. Payment details are not required and public listening remains anonymous."
      : "Sign in securely and create a free account while public listening remains anonymous.";

  return (
    <main className="auth-page" id="main-content">
      <SiteHeader active="membership" />
      <section className="auth-card" aria-labelledby="auth-heading">
        <div className="auth-intro">
          <p className="auth-kicker">Your ORNA account</p>
          <h1 id="auth-heading">{authHeading}</h1>
          <p>{authIntro}</p>
        </div>

        {registrationComplete ? <AuthNotice>Your free account was created. Sign in to continue.</AuthNotice> : null}
        {oauthMessage ? <AuthNotice error={oauthMessage.error}>{oauthMessage.text}</AuthNotice> : null}
        {isLoadingAccount ? <AuthNotice>Loading account…</AuthNotice> : null}
        {accountLoadError ? <AuthNotice error>{accountLoadError}</AuthNotice> : null}
        {magicLinkSent ? (
          <AuthNotice>Check your email. The one-time sign-in link expires in 15 minutes.</AuthNotice>
        ) : null}

        <form className="auth-form" onSubmit={submitMagicLink}>
          <label htmlFor="magic-link-email">Email address</label>
          <input
            id="magic-link-email"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <button className="auth-continue" type="submit" disabled={busy}>
            {busy ? "Please wait…" : "Email me a sign-in link"}
          </button>
        </form>

        <div className="auth-divider"><span>or use a password</span></div>

        <div className="auth-mode" aria-label="Authentication mode">
          <button
            type="button"
            aria-pressed={mode === "login"}
            onClick={() => {
              setMode("login");
              if (entryMode === "register") setEntryMode("default");
            }}
          >
            Sign in
          </button>
          <button
            type="button"
            aria-pressed={mode === "register"}
            onClick={() => {
              setMode("register");
              setEntryMode("register");
              window.dispatchEvent(new CustomEvent("orna:analytics", {
                detail: { name: "signup_started", placement: "membership_form" },
              }));
            }}
          >
            Create account
          </button>
        </div>

        <form className="auth-form" onSubmit={submit}>
          <label htmlFor="membership-email">Password account email</label>
          <input id="membership-email" type="email" autoComplete="email" placeholder="you@example.com" required value={email} onChange={(event) => setEmail(event.target.value)} />
          <label htmlFor="membership-password">Password</label>
          <input id="membership-password" type="password" minLength={mode === "register" ? 12 : 1} maxLength={128} autoComplete={mode === "register" ? "new-password" : "current-password"} required value={password} onChange={(event) => setPassword(event.target.value)} />
          <button className="auth-continue" type="submit" disabled={busy}>{busy ? "Please wait…" : "Continue"}</button>
        </form>

        {configuredProviders && configuredProviders.length > 0 ? (
          <>
            <div className="auth-divider"><span>or</span></div>
            <div className="auth-social" role="group" aria-label="Continue with a social account">
              {configuredProviders.map((provider) => (
                <SocialLink key={provider} provider={provider} returnTo={authReturnTo} />
              ))}
            </div>
          </>
        ) : null}
        {providerLoadError ? <AuthNotice error>Social sign-in is temporarily unavailable.</AuthNotice> : null}
        <p className="auth-legal">By continuing, you agree to the <Link href="/terms">Terms of Use</Link> and acknowledge the <Link href="/privacy">Privacy Policy</Link>.</p>
        {message ? <p className="auth-notice" role="alert">{message}</p> : null}
      </section>
      {isFocusedLogin ? (
        <p className="auth-membership-link">
          New to ORNA? <Link href="/membership?mode=register">Create a free account</Link> or <Link href="/membership">learn about future membership</Link>.
        </p>
      ) : (
        <MembershipInformation
          onCreateAccount={() => {
            setMode("register");
            setEntryMode("register");
            window.requestAnimationFrame(() => document.getElementById("membership-email")?.focus());
          }}
        />
      )}
    </main>
  );
}
