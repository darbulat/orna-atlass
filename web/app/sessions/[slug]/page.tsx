import { cookies } from "next/headers";

import { SiteHeader } from "../../../components/site-header";
import { ApiError, apiErrorMessage } from "../../../lib/api/client";
import { fetchSessionDetail } from "../../../lib/api/sessions";
import { SessionDetailContent } from "./SessionDetailContent";
import { SessionRefreshRecovery } from "./SessionRefreshRecovery";

export const dynamic = "force-dynamic";

export default async function SessionPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const cookieHeader = (await cookies())
    .getAll()
    .map(({ name, value }) => `${name}=${value}`)
    .join("; ");
  try {
    const session = await fetchSessionDetail(
      slug,
      cookieHeader ? { Cookie: cookieHeader } : {},
    );
    return <SessionDetailContent session={session} />;
  } catch (error) {
    const fallback = <SessionLoadState slug={slug} error={error} />;
    if (error instanceof ApiError && error.status === 401) {
      return <SessionRefreshRecovery slug={slug} fallback={fallback} />;
    }
    return fallback;
  }
}

function SessionLoadState({ slug, error }: { slug: string; error: unknown }) {
  const status = error instanceof ApiError ? error.status : null;
  const heading = status === 404
    ? "Session not found"
    : status === 403
      ? "Session access is restricted"
      : status === 409 || status === 425
        ? "Session is not ready"
        : "Session unavailable";
  const message = status === 404
    ? "This recording does not exist or is no longer published."
    : apiErrorMessage(error, "This recording could not be loaded.");

  return (
    <main className="shell session-shell" id="main-content">
      <SiteHeader />
      <section className="panel unavailable-panel" role={status === 404 ? "status" : "alert"}>
        <p className="eyebrow">Session</p>
        <h1>{heading}</h1>
        <p>{message}</p>
        <small>{slug.replaceAll("-", " ")}</small>
      </section>
    </main>
  );
}
