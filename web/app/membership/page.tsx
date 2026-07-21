"use client";

import Link from "next/link";
import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";

import { ApiError, apiErrorMessage } from "../../lib/api/client";
import {
  fetchCurrentUser,
  fetchMembership,
  fetchOAuthProviders,
  login,
  logout,
  oauthStartUrl,
  register,
  type Membership,
  type OAuthProvider,
  type User,
} from "../../lib/api/auth";

type AuthMode = "login" | "register";

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

function SocialLink({ provider }: { provider: OAuthProvider }) {
  const label = providerLabels[provider];
  return (
    <a className="auth-social-link" href={oauthStartUrl(provider)} aria-label={`Continue with ${label}`}>
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

export default function MembershipPage() {
  const [user, setUser] = useState<User | null>(null);
  const [membership, setMembership] = useState<Membership | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<AuthMode>("login");
  const [message, setMessage] = useState<string | null>(null);
  const [oauthMessage, setOauthMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [accountLoadError, setAccountLoadError] = useState<string | null>(null);
  const [isLoadingAccount, setIsLoadingAccount] = useState(true);
  const [isLoadingMembership, setIsLoadingMembership] = useState(true);
  const [busy, setBusy] = useState(false);
  const [registrationComplete, setRegistrationComplete] = useState(false);
  const [configuredProviders, setConfiguredProviders] = useState<OAuthProvider[] | null>(null);
  const [providerLoadError, setProviderLoadError] = useState(false);
  const authGeneration = useRef(0);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedMode = params.get("mode");
    if (requestedMode === "register" || requestedMode === "login") setMode(requestedMode);
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
    const providerValue = params.get("oauth_provider");
    const provider = providerValue && providerValue in providerLabels
      ? providerValue as OAuthProvider
      : null;
    const hasCallbackParams = ["oauth", "oauth_provider", "oauth_error"].some(
      (name) => params.has(name),
    );
    if (hasCallbackParams) {
      params.delete("oauth");
      params.delete("oauth_provider");
      params.delete("oauth_error");
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
    void (async () => {
      try {
        const currentUser = await fetchCurrentUser();
        if (!isCurrent()) return;
        setUser(currentUser);
        setAccountLoadError(null);
        if (provider && oauthStatus === "success") {
          setOauthMessage({ text: `Signed in with ${providerLabels[provider]}.`, error: false });
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
        if (!isCurrent()) return;
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
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
          detail: { name: "registration_completed", placement: "membership_form" },
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
        {registrationComplete ? (
          <AuthNotice>You’re on the early access list. We’ll show pricing before any payment.</AuthNotice>
        ) : null}
        {message ? <p className="form-message" role="alert">{message}</p> : null}
      </main>
    );
  }

  return (
    <main className="auth-page" id="main-content">
      <Link className="auth-wordmark" href="/">ORNA ATLAS</Link>
      <section className="auth-card" aria-labelledby="auth-heading">
        <div className="auth-intro">
          <p className="auth-kicker">Your listening follows you</p>
          <h1 id="auth-heading">Sign in or create your account</h1>
          <p>Save your place across devices, receive personal listening recommendations, and reserve early member access.</p>
        </div>

        {registrationComplete ? <AuthNotice>You’re on the early access list. We’ll show pricing before any payment.</AuthNotice> : null}
        {oauthMessage ? <AuthNotice error={oauthMessage.error}>{oauthMessage.text}</AuthNotice> : null}
        {isLoadingAccount ? <AuthNotice>Loading account…</AuthNotice> : null}
        {accountLoadError ? <AuthNotice error>{accountLoadError}</AuthNotice> : null}

        <div className="auth-mode" aria-label="Authentication mode">
          <button type="button" aria-pressed={mode === "login"} onClick={() => setMode("login")}>Sign in</button>
          <button type="button" aria-pressed={mode === "register"} onClick={() => setMode("register")}>Create account</button>
        </div>

        <form className="auth-form" onSubmit={submit}>
          <label htmlFor="membership-email">Email address</label>
          <input id="membership-email" type="email" autoComplete="email" placeholder="you@example.com" required value={email} onChange={(event) => setEmail(event.target.value)} />
          <label htmlFor="membership-password">Password</label>
          <input id="membership-password" type="password" minLength={mode === "register" ? 12 : 1} maxLength={128} autoComplete={mode === "register" ? "new-password" : "current-password"} required value={password} onChange={(event) => setPassword(event.target.value)} />
          <button className="auth-continue" type="submit" disabled={busy}>{busy ? "Please wait…" : "Continue"}</button>
        </form>

        {configuredProviders && configuredProviders.length > 0 ? (
          <>
            <div className="auth-divider"><span>or</span></div>
            <div className="auth-social" role="group" aria-label="Continue with a social account">
              {configuredProviders.map((provider) => <SocialLink key={provider} provider={provider} />)}
            </div>
          </>
        ) : null}
        {providerLoadError ? <AuthNotice error>Social sign-in is temporarily unavailable.</AuthNotice> : null}
        <p className="auth-legal">By continuing, you agree to the <Link href="/terms">Terms of Use</Link> and acknowledge the <Link href="/privacy">Privacy Policy</Link>.</p>
        {message ? <p className="auth-notice" role="alert">{message}</p> : null}
      </section>
    </main>
  );
}
