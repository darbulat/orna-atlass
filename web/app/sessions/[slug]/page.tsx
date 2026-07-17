import { SessionPlayer } from "../../../components/audio/SessionPlayer";
import { cookies } from "next/headers";
import { AnnotationTimeline } from "../../../components/sessions/AnnotationTimeline";
import { BirdPartsTimeline } from "../../../components/sessions/BirdPartsTimeline";
import { ProcessingStatusPanel } from "../../../components/sessions/ProcessingStatusPanel";
import { RecordingIntegrityPanel } from "../../../components/sessions/RecordingIntegrityPanel";
import { ApiError, apiErrorMessage } from "../../../lib/api/client";
import { fetchSessionDetail, type SessionDetail } from "../../../lib/api/sessions";

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
    return <SessionDetailView session={session} />;
  } catch (error) {
    return <SessionLoadState slug={slug} error={error} />;
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
      <section className="panel unavailable-panel" role={status === 404 ? "status" : "alert"}>
        <p className="eyebrow">Session</p>
        <h1>{heading}</h1>
        <p>{message}</p>
        <small>{formatSlug(slug)}</small>
      </section>
    </main>
  );
}

function SessionDetailView({ session }: { session: SessionDetail }) {
  return (
    <main className="shell session-shell" id="main-content">
      <section className="session-hero">
        <p className="eyebrow">ORNA Session</p>
        <h1>{session.title}</h1>
        <p>{session.description ?? "A long-form field recording from the atlas."}</p>
        {session.location.coordinates_protected ? (
          <p className="protected-badge" role="status">
            Approximate location — exact coordinates are protected for this sensitive habitat.
          </p>
        ) : null}
        <dl className="session-meta">
          <div>
            <dt>Location</dt>
            <dd>{session.location.name}</dd>
          </div>
          <div>
            <dt>Habitat</dt>
            <dd>{session.location.habitat ?? "Unknown"}</dd>
          </div>
          <div>
            <dt>Weather</dt>
            <dd>{session.weather ?? "Not recorded"}</dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd>{formatDuration(session.duration_seconds)}</dd>
          </div>
        </dl>
      </section>

      <SessionPlayer session={session} />
      <BirdPartsTimeline session={session} />
      {session.waveform ? (
        <AnnotationTimeline annotations={session.annotations ?? []} waveform={session.waveform} />
      ) : (
        <p className="not-ready-state" role="status">Waveform data is still being prepared.</p>
      )}
      {session.recording_integrity ? (
        <RecordingIntegrityPanel integrity={session.recording_integrity} />
      ) : (
        <p className="not-ready-state" role="status">Recording details have not been provided.</p>
      )}
      <ProcessingStatusPanel status={session.processing_status} assets={session.media_assets ?? []} />
    </main>
  );
}

function formatSlug(slug: string) {
  return slug.replaceAll("-", " ");
}

function formatDuration(seconds: number | null | undefined) {
  if (!seconds) {
    return "Unknown";
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours === 0) {
    return `${minutes} min`;
  }
  return `${hours}h ${minutes}m`;
}
