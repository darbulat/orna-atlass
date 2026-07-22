"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { SiteHeader } from "../../components/site-header";
import { isApiError } from "../../lib/api/client";
import {
  clearListeningHistory,
  fetchFavorites,
  fetchListeningHistory,
  removeFavorite,
  type Favorite,
  type ListeningHistoryItem,
} from "../../lib/api/library";

export default function LibraryPage() {
  const [favorites, setFavorites] = useState<Favorite[]>([]);
  const [history, setHistory] = useState<ListeningHistoryItem[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "login" | "error">("loading");

  useEffect(() => {
    let active = true;
    void Promise.all([fetchFavorites(), fetchListeningHistory()])
      .then(([nextFavorites, nextHistory]) => {
        if (!active) return;
        setFavorites(nextFavorites);
        setHistory(nextHistory);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (!active) return;
        setState(isApiError(error) && error.status === 401 ? "login" : "error");
      });
    return () => { active = false; };
  }, []);

  async function forgetFavorite(item: Favorite) {
    try {
      await removeFavorite(item.session.id);
      setFavorites((current) => current.filter((favorite) => favorite.session.id !== item.session.id));
    } catch {
      setState("error");
    }
  }

  async function clearHistory() {
    try {
      await clearListeningHistory();
      setHistory([]);
    } catch {
      setState("error");
    }
  }

  return (
    <main id="main-content" className="shell content-shell">
      <SiteHeader />
      <section className="panel prose-card library-page" aria-labelledby="library-heading">
        <p className="eyebrow">Account library</p>
        <h1 id="library-heading">Your library</h1>
        {state === "loading" ? <p role="status">Loading your library…</p> : null}
        {state === "login" ? (
          <p><Link href="/membership?mode=login">Sign in</Link> to see favorites and listening history synced to your account.</p>
        ) : null}
        {state === "error" ? <p role="alert">Your library is temporarily unavailable. Please try again.</p> : null}
        {state === "ready" ? (
          <div className="library-sections">
            <section aria-labelledby="favorites-heading">
              <h2 id="favorites-heading">Favorites</h2>
              {favorites.length === 0 ? <p>No saved recordings yet.</p> : (
                <ul>
                  {favorites.map((favorite) => (
                    <li key={favorite.session.id}>
                      <div><strong>{favorite.session.title}</strong><span>{favorite.session.location.name}</span></div>
                      <button type="button" onClick={() => void forgetFavorite(favorite)}>Remove</button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section aria-labelledby="history-heading">
              <div className="section-heading">
                <h2 id="history-heading">Listening history</h2>
                {history.length > 0 ? <button type="button" onClick={() => void clearHistory()}>Clear history</button> : null}
              </div>
              {history.length === 0 ? <p>No listening history yet.</p> : (
                <ul>
                  {history.map((entry) => (
                    <li key={entry.session.id}>
                      <div><strong>{entry.session.title}</strong><span>{entry.session.location.name}</span></div>
                      <span>{Math.floor(entry.last_position_seconds)} seconds listened</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        ) : null}
      </section>
    </main>
  );
}
