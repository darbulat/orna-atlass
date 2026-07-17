"use client";

import { useMemo, useState } from "react";
import type { SessionDetail } from "../../lib/api/sessions";
import { usePlayer } from "../audio/PlayerProvider";
import { formatOffset, groupBirdPartsBySpecies } from "../audio/sessionPlayerUtils";

const PAGE_SIZE = 12;

export function BirdPartsTimeline({ session }: { session: SessionDetail }) {
  const { currentSession, play, seek } = usePlayer();
  const [query, setQuery] = useState("");
  const [minimumConfidence, setMinimumConfidence] = useState(0);
  const [expandedSpecies, setExpandedSpecies] = useState<string | null>(null);
  const [visibleEpisodes, setVisibleEpisodes] = useState(PAGE_SIZE);
  const tracks = useMemo(() => groupBirdPartsBySpecies(session.bird_parts?.parts ?? []), [session.bird_parts]);
  const filteredTracks = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return tracks
      .map((track) => ({
        ...track,
        parts: track.parts.filter((part) => (part.confidence ?? 0) >= minimumConfidence),
      }))
      .filter((track) => track.parts.length > 0 && (!normalizedQuery || track.label.toLocaleLowerCase().includes(normalizedQuery)))
      .sort((left, right) => right.parts.length - left.parts.length || left.label.localeCompare(right.label));
  }, [minimumConfidence, query, tracks]);

  async function listenFrom(seconds: number) {
    if (currentSession?.id !== session.id) await play(session);
    seek(seconds);
  }

  return (
    <section className="timeline-card species-explorer" aria-label="Detected species">
      <header className="species-explorer-heading">
        <div>
          <p className="eyebrow">Species timeline</p>
          <h2>{filteredTracks.length} detected species</h2>
          {session.bird_parts?.analysis_provider ? (
            <p className="timeline-meta">Analysis by {session.bird_parts.analysis_provider}{session.bird_parts.analysis_model_version ? ` · model ${session.bird_parts.analysis_model_version}` : ""}</p>
          ) : null}
        </div>
        <div className="species-filters">
          <label>Find a species<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Robin, owl…" /></label>
          <label>Minimum confidence<select value={minimumConfidence} onChange={(event) => setMinimumConfidence(Number(event.target.value))}><option value={0}>Any confidence</option><option value={0.7}>70% or higher</option><option value={0.85}>85% or higher</option><option value={0.95}>95% or higher</option></select></label>
        </div>
      </header>
      {filteredTracks.length ? (
        <ol className="species-summary-list">
          {filteredTracks.map((track) => {
            const expanded = expandedSpecies === track.key;
            const maxConfidence = Math.max(...track.parts.map((part) => part.confidence ?? 0));
            const scientificName = track.parts.find((part) => part.species_scientific_name)?.species_scientific_name;
            return <li key={track.key}>
              <button type="button" className="species-summary" aria-expanded={expanded} aria-label={`${track.label}, ${track.parts.length} detections`} onClick={() => { setExpandedSpecies(expanded ? null : track.key); setVisibleEpisodes(PAGE_SIZE); }}>
                <span><strong>{track.label}</strong><small>{track.parts.length} detections · up to {Math.round(maxConfidence * 100)}%</small></span>
                <span aria-hidden="true">{expanded ? "−" : "+"}</span>
              </button>
              {expanded ? <div className="species-episodes">
                {scientificName ? <p><em>{scientificName}</em> · first at {formatOffset(track.parts[0].starts_at_seconds)} · last at {formatOffset(track.parts.at(-1)?.starts_at_seconds ?? 0)}</p> : null}
                <ol>{track.parts.slice(0, visibleEpisodes).map((part) => <li key={part.id}><span><strong>{formatOffset(part.starts_at_seconds)}</strong><small>{part.call_type} · {Math.round((part.confidence ?? 0) * 100)}%</small></span><button type="button" onClick={() => void listenFrom(part.starts_at_seconds)} aria-label={`Listen from ${formatOffset(part.starts_at_seconds)}`}>Listen</button></li>)}</ol>
                {visibleEpisodes < track.parts.length ? <button type="button" className="show-more" onClick={() => setVisibleEpisodes((count) => count + PAGE_SIZE)}>Show {Math.min(PAGE_SIZE, track.parts.length - visibleEpisodes)} more</button> : null}
              </div> : null}
            </li>;
          })}
        </ol>
      ) : <p>No detections match these filters.</p>}
    </section>
  );
}
