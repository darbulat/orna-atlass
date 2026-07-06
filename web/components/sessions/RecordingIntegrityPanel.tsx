import type { RecordingIntegrity } from "../../lib/api/sessions";

const labels: Record<keyof RecordingIntegrity, string> = {
  human_noise_level: "Human noise",
  post_processing: "Post-processing",
  microphone_setup: "Microphone setup",
  recordist_notes: "Recordist notes",
};

export function RecordingIntegrityPanel({ integrity }: { integrity: RecordingIntegrity }) {
  return (
    <section className="detail-grid" aria-label="Recording integrity">
      {(Object.keys(labels) as Array<keyof RecordingIntegrity>).map((key) => (
        <article key={key}>
          <span>{labels[key]}</span>
          <p>{integrity[key] ?? "Not provided"}</p>
        </article>
      ))}
    </section>
  );
}
