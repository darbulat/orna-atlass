"use client";

import { useState, useTransition } from "react";

import type { AdminAuditRow, AdminSessionRow } from "../../lib/api/admin";

export type SensitiveOperationalSearchState =
  | { kind: "idle" }
  | { kind: "error"; message: string }
  | { kind: "sessions"; items: AdminSessionRow[] }
  | { kind: "audits"; items: AdminAuditRow[] };

type SensitiveOperationalSearchProps = {
  action: (formData: FormData) => Promise<SensitiveOperationalSearchState>;
};

export function SensitiveOperationalSearch({ action }: SensitiveOperationalSearchProps) {
  const [state, setState] = useState<SensitiveOperationalSearchState>({ kind: "idle" });
  const [pending, startTransition] = useTransition();

  return (
    <section className="admin-sensitive-search" aria-labelledby="sensitive-operational-title">
      <h2 id="sensitive-operational-title">Transient operational ID filters</h2>
      <p className="admin-muted">Идентификаторы отправляются только POST server action и не сохраняются в URL или browser history.</p>
      <form
        className="admin-filters"
        action={(formData) => {
          startTransition(async () => setState(await action(formData)));
        }}
      >
        <label>
          <span>Тип поиска</span>
          <select name="sensitive_filter_kind" defaultValue="sessions">
            <option value="sessions">Сессии по Location ID</option>
            <option value="audits">Audit по actor/subject ID</option>
          </select>
        </label>
        <label><span>Location ID</span><input name="session_location_id" maxLength={80} autoComplete="off" /></label>
        <label><span>Audit actor ID</span><input name="audit_actor_user_id" maxLength={80} autoComplete="off" /></label>
        <label><span>Audit subject ID</span><input name="audit_subject_id" maxLength={120} autoComplete="off" /></label>
        <button type="submit" disabled={pending}>{pending ? "Поиск…" : "Выполнить transient-поиск"}</button>
      </form>
      <div aria-live="polite">
        {state.kind === "error" ? <p className="admin-empty">{state.message}</p> : null}
        {state.kind === "sessions" ? (
          <ul className="admin-list">
            {state.items.map((item) => <li key={item.id}><strong>{item.title}</strong><br /><code>{item.id}</code></li>)}
          </ul>
        ) : null}
        {state.kind === "audits" ? (
          <ul className="admin-list">
            {state.items.map((item) => <li key={item.id}><strong>{item.event_type}</strong> · {item.subject_type}<br /><code>{item.id}</code></li>)}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
