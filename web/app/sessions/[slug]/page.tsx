import { SessionPlayer } from "../../../components/audio/SessionPlayer";
import { AnnotationTimeline } from "../../../components/sessions/AnnotationTimeline";
import { RecordingIntegrityPanel } from "../../../components/sessions/RecordingIntegrityPanel";
import { fetchSessionDetail, type SessionDetail } from "../../../lib/api/sessions";

export const dynamic = "force-dynamic";

export default async function SessionPage({ params }: { params: { slug: string } }) {
  const session = await fetchSessionDetail(params.slug);

  if (!session) {
    return (
      <main className="shell session-shell">
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
    <main className="shell session-shell">
      <section className="session-hero">
        <p className="eyebrow">ORNA Session</p>
        <h1>{session.title}</h1>
        <p>{session.description ?? "A long-form field recording from the atlas."}</p>
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
      <RecordingIntegrityPanel integrity={session.recording_integrity} />
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
