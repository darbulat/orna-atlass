import type { BirdPartsResponse } from "../../lib/api/sessions";

type BirdPartsTimelineProps = {
  birdParts: BirdPartsResponse | null;
  durationSeconds: number | null;
};

export function BirdPartsTimeline({ birdParts, durationSeconds }: BirdPartsTimelineProps) {
  const parts = birdParts?.parts ?? [];
  const total = Math.max(durationSeconds ?? parts.at(-1)?.ends_at_seconds ?? 1, 1);

  return (
    <section className="timeline-card bird-parts-card" aria-label="Bird vocal parts timeline">
      <div>
        <p className="eyebrow">Species timeline</p>
        <h2>Bird vocal parts</h2>
        {birdParts?.analysis_provider ? (
          <p className="timeline-meta">
            Analysis by {birdParts.analysis_provider}
            {birdParts.analysis_model_version ? ` · model ${birdParts.analysis_model_version}` : ""}
          </p>
        ) : null}
      </div>
      {parts.length > 0 ? (
        <>
          <div className="bird-parts-track" role="list" aria-label="Detected bird vocal intervals">
            {parts.map((part) => {
              const left = (part.starts_at_seconds / total) * 100;
              const width = Math.max(((part.ends_at_seconds - part.starts_at_seconds) / total) * 100, 1.5);
              return (
                <button
                  key={part.id}
                  type="button"
                  className="bird-part-marker"
                  role="listitem"
                  style={{ left: `${left}%`, width: `${width}%` }}
                  title={`${part.species_common_name} (${formatOffset(part.starts_at_seconds)})`}
                  aria-label={`${part.species_common_name}, ${part.call_type}, ${formatOffset(part.starts_at_seconds)} to ${formatOffset(part.ends_at_seconds)}`}
                >
                  <span>{part.species_common_name}</span>
                </button>
              );
            })}
          </div>
          <ol className="annotations bird-parts-list">
            {parts.map((part) => (
              <li key={part.id}>
                <strong>{formatOffset(part.starts_at_seconds)}</strong>
                <span>
                  {part.species_common_name}
                  {part.species_scientific_name ? ` · ${part.species_scientific_name}` : ""}
                  {part.confidence != null ? ` · ${Math.round(part.confidence * 100)}%` : ""}
                </span>
              </li>
            ))}
          </ol>
        </>
      ) : (
        <p>Bird vocal parts will appear here after audio analysis completes.</p>
      )}
    </section>
  );
}

function formatOffset(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remaining}`;
}
