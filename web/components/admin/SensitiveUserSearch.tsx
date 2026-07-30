"use client";

import { useState } from "react";

import type { AdminUserRow } from "../../lib/api/admin";

export type SensitiveUserSearchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "empty" }
  | { kind: "error"; message: string }
  | { kind: "ok"; items: AdminUserRow[] };

type SensitiveUserSearchProps = {
  action: (formData: FormData) => Promise<SensitiveUserSearchState>;
};

export function SensitiveUserSearch({ action }: SensitiveUserSearchProps) {
  const [state, setState] = useState<SensitiveUserSearchState>({ kind: "idle" });

  async function submit(formData: FormData) {
    setState({ kind: "loading" });
    setState(await action(formData));
  }

  return (
    <section className="admin-sensitive-search" aria-labelledby="admin-sensitive-user-search-title">
      <h3 id="admin-sensitive-user-search-title">Поиск пользователя по email</h3>
      <p className="admin-empty">
        Email отправляется POST-запросом и не сохраняется в URL, browser history или client storage.
      </p>
      <form action={submit} className="admin-action-form">
        <label>
          <span>Email</span>
          <input name="email" type="email" required maxLength={100} autoComplete="off" />
        </label>
        <button type="submit" disabled={state.kind === "loading"}>
          {state.kind === "loading" ? "Поиск…" : "Найти"}
        </button>
      </form>
      <div aria-live="polite">
        {state.kind === "empty" ? <p className="admin-empty">Пользователь не найден.</p> : null}
        {state.kind === "error" ? <p className="admin-empty">{state.message}</p> : null}
        {state.kind === "ok" ? (
          <ul className="admin-list">
            {state.items.map((user) => (
              <li key={user.id}>
                <strong>{user.email ?? "—"}</strong>
                <span>{user.role ?? "—"} · {user.membership_status ?? "inactive"}</span>
                <code>{user.id}</code>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
