"use client";

import { FormEvent, useEffect, useState } from "react";

import { ApiError, apiErrorMessage } from "../../lib/api/client";
import {
  fetchCurrentUser,
  fetchMembership,
  login,
  logout,
  register,
  type Membership,
  type User,
} from "../../lib/api/auth";

export default function MembershipPage() {
  const [user, setUser] = useState<User | null>(null);
  const [membership, setMembership] = useState<Membership | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [message, setMessage] = useState<string | null>(null);
  const [accountLoadError, setAccountLoadError] = useState<string | null>(null);
  const [isLoadingAccount, setIsLoadingAccount] = useState(true);
  const [busy, setBusy] = useState(false);
  const [registrationComplete, setRegistrationComplete] = useState(false);

  useEffect(() => {
    const requestedMode = new URLSearchParams(window.location.search).get("mode");
    if (requestedMode === "register" || requestedMode === "login") {
      setMode(requestedMode);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const currentUser = await fetchCurrentUser();
        const currentMembership = await fetchMembership();
        if (!active) return;
        setUser(currentUser);
        setMembership(currentMembership);
        setAccountLoadError(null);
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          setUser(null);
          setMembership(null);
          setAccountLoadError(null);
        } else {
          setAccountLoadError(apiErrorMessage(error, "Unable to load your account."));
        }
      } finally {
        if (active) setIsLoadingAccount(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      if (mode === "register") {
        await register(email, password);
        setRegistrationComplete(true);
        window.dispatchEvent(new CustomEvent("orna:analytics", {
          detail: {
            name: "registration_completed",
            placement: "membership_form",
          },
        }));
      }
      const token = await login(email, password);
      setUser(token.user);
      const entitlement = await fetchMembership();
      setMembership(entitlement);
      setAccountLoadError(null);
      setPassword("");
    } catch (error) {
      setMessage(apiErrorMessage(error, "Authentication failed"));
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    setBusy(true);
    setMessage(null);
    try {
      await logout();
      setUser(null);
      setMembership(null);
    } catch (error) {
      setMessage(apiErrorMessage(error, "Logout failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell membership-page" id="main-content">
      <p className="eyebrow">ORNA Atlas</p>
      <h1>Membership</h1>
      <p>Listen first, then create a free account to reserve early member access. No payment is taken today.</p>
      {registrationComplete ? (
        <p className="form-message" role="status">You’re on the early access list. We’ll show pricing before any payment.</p>
      ) : null}
      {isLoadingAccount ? <p role="status">Loading account…</p> : null}
      {accountLoadError ? <p className="form-message" role="alert">{accountLoadError}</p> : null}
      {user ? (
        <section className="panel membership-card" aria-live="polite">
          <p className="eyebrow">Signed in</p>
          <h2>{user.email}</h2>
          <dl>
            <div><dt>Role</dt><dd>{user.role}</dd></div>
            <div><dt>Plan</dt><dd>{membership?.plan ?? "none"}</dd></div>
            <div><dt>Status</dt><dd>{membership?.status ?? "inactive"}</dd></div>
            <div><dt>Playback</dt><dd>{membership?.is_entitled ? "Member sessions unlocked" : "Public previews only"}</dd></div>
          </dl>
          <button type="button" onClick={signOut} disabled={busy}>Sign out</button>
        </section>
      ) : (
        <section className="panel membership-card">
          <div className="membership-tabs" aria-label="Authentication mode">
            <button type="button" aria-pressed={mode === "login"} onClick={() => setMode("login")}>Sign in</button>
            <button type="button" aria-pressed={mode === "register"} onClick={() => setMode("register")}>Create account</button>
          </div>
          <form onSubmit={submit}>
            <label htmlFor="membership-email">Email</label>
            <input id="membership-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
            <label htmlFor="membership-password">Password</label>
            <input id="membership-password" type="password" minLength={mode === "register" ? 12 : 1} maxLength={128} autoComplete={mode === "register" ? "new-password" : "current-password"} required value={password} onChange={(event) => setPassword(event.target.value)} />
            <button type="submit" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
          </form>
        </section>
      )}
      {message ? <p className="form-message" role="alert">{message}</p> : null}
    </main>
  );
}
