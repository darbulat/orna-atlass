import type { SessionAnnotation, Waveform } from "../../lib/api/sessions";

export function AnnotationTimeline({ annotations, waveform }: { annotations: SessionAnnotation[]; waveform: Waveform }) {
  const peaks = waveform.peaks.length > 0 ? waveform.peaks.slice(0, 64) : [0.2, 0.45, 0.3, 0.6, 0.4];

  return (
    <section className="timeline-card" aria-label="Annotation timeline">
      <div>
        <p className="eyebrow">Waveform placeholder</p>
        <h2>Annotation timeline</h2>
      </div>
      <div className="waveform" aria-label={`Waveform status: ${waveform.status}`}>
        {peaks.map((peak, index) => (
          <span key={`${peak}-${index}`} style={{ height: `${Math.max(8, peak * 80)}px` }} />
        ))}
      </div>
      {annotations.length > 0 ? (
        <ol className="annotations">
          {annotations.map((annotation) => (
            <li key={`${annotation.offset_seconds}-${annotation.label}`}>
              <strong>{formatOffset(annotation.offset_seconds)}</strong>
              <span>{annotation.label}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p>No editorial annotations yet. Bird parts arrive in a later sprint.</p>
      )}
    </section>
  );
}

function formatOffset(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remaining}`;
}
