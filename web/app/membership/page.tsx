"use client";

import { FormEvent, useEffect, useState } from "react";

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
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([fetchCurrentUser(), fetchMembership()])
      .then(([currentUser, currentMembership]) => {
        if (active) {
          setUser(currentUser);
          setMembership(currentMembership);
        }
      })
      .catch(() => undefined);
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
      }
      const token = await login(email, password);
      const entitlement = await fetchMembership();
      setUser(token.user);
      setMembership(entitlement);
      setPassword("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Authentication failed");
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
      setMessage(error instanceof Error ? error.message : "Logout failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell membership-page" id="main-content">
      <p className="eyebrow">ORNA Atlas</p>
      <h1>Membership</h1>
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
