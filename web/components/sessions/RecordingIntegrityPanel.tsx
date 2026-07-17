import type { RecordingIntegrity } from "../../lib/api/sessions";

const labels: Record<keyof RecordingIntegrity, string> = {
  human_noise_level: "Human noise",
  post_processing: "Post-processing",
  microphone_setup: "Microphone setup",
  recordist_notes: "Recordist notes",
};

export function RecordingIntegrityPanel({ integrity }: { integrity: RecordingIntegrity }) {
  const provided = (Object.keys(labels) as Array<keyof RecordingIntegrity>).filter((key) => {
    const value = integrity[key]?.trim();
    return Boolean(value && value.toLowerCase() !== "unknown");
  });
  return (
    <section className="recording-details" aria-label="Recording details">
      <p className="eyebrow">Recording details</p>
      {provided.length ? <dl>{provided.map((key) => <div key={key}><dt>{labels[key]}</dt><dd>{integrity[key]}</dd></div>)}</dl> : <p>Additional recording details have not been provided.</p>}
    </section>
  );
}
