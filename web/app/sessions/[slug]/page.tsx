import { SessionPlayer } from "../../../components/audio/SessionPlayer";
import { cookies } from "next/headers";
import { AnnotationTimeline } from "../../../components/sessions/AnnotationTimeline";
import { BirdPartsTimeline } from "../../../components/sessions/BirdPartsTimeline";
import { ProcessingStatusPanel } from "../../../components/sessions/ProcessingStatusPanel";
import { RecordingIntegrityPanel } from "../../../components/sessions/RecordingIntegrityPanel";
import { fetchSessionDetail, type SessionDetail } from "../../../lib/api/sessions";

export const dynamic = "force-dynamic";

export default async function SessionPage({ params }: { params: { slug: string } }) {
  const cookieHeader = cookies()
    .getAll()
    .map(({ name, value }) => `${name}=${value}`)
    .join("; ");
  const session = await fetchSessionDetail(
    params.slug,
    cookieHeader ? { Cookie: cookieHeader } : {},
  );

  if (!session) {
    return (
      <main className="shell session-shell" id="main-content">
        <p className="eyebrow">Session</p>
        <h1>{formatSlug(params.slug)}</h1>
        <p>
          Session metadata is not available yet. Once the Sprint 3 API has content, this page will render the
          session hero, recording integrity, player shell, waveform, and annotation timeline.
        </p>
      </main>
    );
  }

  return <SessionDetailView session={session} />;
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
      <ProcessingStatusPanel status={session.processing_status} assets={session.media_assets} />
      <RecordingIntegrityPanel integrity={session.recording_integrity} />
      <BirdPartsTimeline birdParts={session.bird_parts} durationSeconds={session.duration_seconds} />
      <AnnotationTimeline annotations={session.annotations} waveform={session.waveform} />
    </main>
  );
}

function formatSlug(slug: string) {
  return slug.replaceAll("-", " ");
}

function formatDuration(seconds: number | null) {
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
