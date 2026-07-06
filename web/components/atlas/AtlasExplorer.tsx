"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { AtlasCluster, AtlasPoint } from "../../lib/api/sessions";
import { fetchAtlasPoints } from "../../lib/api/sessions";

type Props = {
  initialView: "map" | "list";
  points: Array<AtlasPoint | AtlasCluster>;
};

function isPoint(item: AtlasPoint | AtlasCluster): item is AtlasPoint {
  return item.type === "point";
}

function markerStyle(point: AtlasPoint | AtlasCluster) {
  return {
    left: `${((point.longitude + 180) / 360) * 100}%`,
    top: `${((90 - point.latitude) / 180) * 100}%`,
  };
}

const habitatOptions = ["forest", "wetland", "steppe", "coast"];

export function AtlasExplorer({ initialView, points }: Props) {
  const [view, setView] = useState(initialView);
  const [atlasPoints, setAtlasPoints] = useState(points);
  const [selectedHabitats, setSelectedHabitats] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const locations = useMemo(() => atlasPoints.filter(isPoint), [atlasPoints]);
  const [selectedSlug, setSelectedSlug] = useState(locations[0]?.slug ?? null);
  const selected = locations.find((point) => point.slug === selectedSlug) ?? locations[0] ?? null;

  useEffect(() => {
    if (selectedSlug && locations.some((point) => point.slug === selectedSlug)) {
      return;
    }
    setSelectedSlug(locations[0]?.slug ?? null);
  }, [locations, selectedSlug]);

  async function toggleHabitat(habitat: string) {
    const nextHabitats = selectedHabitats.includes(habitat)
      ? selectedHabitats.filter((item) => item !== habitat)
      : [...selectedHabitats, habitat];
    setSelectedHabitats(nextHabitats);
    setIsLoading(true);
    try {
      const atlas = await fetchAtlasPoints(view, nextHabitats);
      setAtlasPoints(atlas.points);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="atlas-workspace">
      <div className="atlas-toolbar" aria-label="Atlas controls">
        <div className="segmented" role="tablist" aria-label="Atlas view">
          <button type="button" role="tab" aria-selected={view === "map"} onClick={() => setView("map")}>
            Map
          </button>
          <button type="button" role="tab" aria-selected={view === "list"} onClick={() => setView("list")}>
            List
          </button>
        </div>
        <div className="filter-row" aria-label="Habitat filters">
          {habitatOptions.map((habitat) => (
            <button
              type="button"
              key={habitat}
              aria-pressed={selectedHabitats.includes(habitat)}
              disabled={isLoading}
              onClick={() => toggleHabitat(habitat)}
            >
              {habitat}
            </button>
          ))}
        </div>
      </div>

      {view === "map" ? (
        <div className="atlas-grid">
          <div className="atlas-map" aria-label="Location map">
            <div className="map-grid" />
            {atlasPoints.map((point) => (
              <button
                type="button"
                key={`${point.type}-${point.id}`}
                className={point.type === "cluster" ? "atlas-marker cluster" : "atlas-marker"}
                style={markerStyle(point)}
                onClick={() => {
                  if (isPoint(point)) setSelectedSlug(point.slug);
                }}
                title={isPoint(point) ? point.name : `${point.count} locations`}
              >
                {isPoint(point) ? point.session_count : point.count}
              </button>
            ))}
          </div>
          <LocationDrawer location={selected} />
        </div>
      ) : (
        <div className="atlas-list-layout">
          <ol className="atlas-list">
            {locations.map((location) => (
              <li key={location.id}>
                <button type="button" onClick={() => setSelectedSlug(location.slug)}>
                  <strong>{location.name}</strong>
                  <span>{[location.region, location.habitat].filter(Boolean).join(" / ")}</span>
                </button>
              </li>
            ))}
          </ol>
          <LocationDrawer location={selected} />
        </div>
      )}
    </section>
  );
}

function LocationDrawer({ location }: { location: AtlasPoint | null }) {
  if (!location) {
    return (
      <aside className="atlas-drawer">
        <p>No public atlas locations found.</p>
      </aside>
    );
  }

  return (
    <aside className="atlas-drawer">
      <p className="eyebrow">{location.habitat ?? "Field site"}</p>
      <h2>{location.name}</h2>
      <p>{location.description ?? "Published field recordings from this location."}</p>
      <dl className="drawer-meta">
        <div>
          <dt>Region</dt>
          <dd>{[location.region, location.country_code].filter(Boolean).join(", ") || "Unknown"}</dd>
        </div>
        <div>
          <dt>Local time</dt>
          <dd>{location.timezone}</dd>
        </div>
        <div>
          <dt>Public sessions</dt>
          <dd>{location.session_count}</dd>
        </div>
      </dl>
      {location.latest_session ? (
        <Link className="drawer-link" href={`/sessions/${location.latest_session.slug}`}>
          Open session
        </Link>
      ) : null}
    </aside>
  );
}
