import { SessionPlayer } from "../../../components/audio/SessionPlayer";
import { SiteHeader } from "../../../components/site-header";
import { AnnotationTimeline } from "../../../components/sessions/AnnotationTimeline";
import { BirdPartsTimeline } from "../../../components/sessions/BirdPartsTimeline";
import { ProcessingStatusPanel } from "../../../components/sessions/ProcessingStatusPanel";
import { RecordingIntegrityPanel } from "../../../components/sessions/RecordingIntegrityPanel";
import type { SessionDetail } from "../../../lib/api/sessions";

export function SessionDetailContent({ session }: { session: SessionDetail }) {
  return (
    <main className="shell session-shell" id="main-content">
      <SiteHeader />
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

function formatDuration(seconds: number | null | undefined) {
  if (!seconds) return "Unknown";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours === 0 ? `${minutes} min` : `${hours}h ${minutes}m`;
}
