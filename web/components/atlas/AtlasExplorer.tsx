"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArcGisMapServerImageryProvider,
  Cartesian3,
  Color,
  EllipsoidTerrainProvider,
  Entity,
  HorizontalOrigin,
  ImageryLayer,
  LabelStyle,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  TileMapServiceImageryProvider,
  VerticalOrigin,
  Viewer,
  buildModuleUrl,
} from "cesium";
import type {
  AtlasCluster,
  AtlasPoint,
  DawnCurrentResponse,
  SearchResult,
  SessionDetail,
} from "../../lib/api/sessions";
import { fetchCurrentDawn, fetchSessionDetail, searchAtlas } from "../../lib/api/sessions";
import { SessionPlayer } from "../audio/SessionPlayer";

type AtlasView = "globe" | "map" | "list";

type Props = {
  initialView: AtlasView;
  points: Array<AtlasPoint | AtlasCluster>;
  dawn: DawnCurrentResponse;
  sidePanelSession: SessionDetail | null;
};

type CesiumGlobeProps = {
  points: Array<AtlasPoint | AtlasCluster>;
  selectedSlug: string | null;
  activeDawnSlugs: Set<string>;
  dawnLongitude: number;
  onSelectPoint: (point: AtlasPoint) => void;
};

const satelliteImageryUrl = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer";
const listeningModes = ["Dawn", "Day", "Dusk", "Night"];

function isPoint(item: AtlasPoint | AtlasCluster): item is AtlasPoint {
  return item.type === "point";
}

function markerStyle(point: AtlasPoint | AtlasCluster) {
  return {
    left: `${((point.longitude + 180) / 360) * 100}%`,
    top: `${((90 - point.latitude) / 180) * 100}%`,
  };
}

function dawnLongitudeFromDate(value: string) {
  const generatedAt = new Date(value);
  const utcHours =
    generatedAt.getUTCHours() + generatedAt.getUTCMinutes() / 60 + generatedAt.getUTCSeconds() / 3600;
  const sunriseLongitude = 90 - utcHours * 15;
  return ((((sunriseLongitude + 180) % 360) + 360) % 360) - 180;
}

function dawnPolylinePositions(longitude: number) {
  const positions = [];
  for (let latitude = -88; latitude <= 88; latitude += 2) {
    positions.push(Cartesian3.fromDegrees(longitude, latitude, 7000));
  }
  return positions;
}

function configureCesiumBaseUrl() {
  const urlBuilder = buildModuleUrl as typeof buildModuleUrl & { setBaseUrl?: (value: string) => void };
  urlBuilder.setBaseUrl?.("/cesium/");
}

function CesiumGlobe({ points, selectedSlug, activeDawnSlugs, dawnLongitude, onSelectPoint }: CesiumGlobeProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const pointByEntityIdRef = useRef(new Map<string, AtlasPoint>());
  const onSelectRef = useRef(onSelectPoint);
  const [isWebglUnavailable, setIsWebglUnavailable] = useState(false);

  useEffect(() => {
    onSelectRef.current = onSelectPoint;
  }, [onSelectPoint]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const host = container;

    let isDisposed = false;
    let clickHandler: ScreenSpaceEventHandler | null = null;
    let viewer: Viewer | null = null;
    const pointByEntityId = pointByEntityIdRef.current;

    async function createViewer() {
      try {
        configureCesiumBaseUrl();
        viewer = new Viewer(host, {
          animation: false,
          baseLayer: false,
          baseLayerPicker: false,
          fullscreenButton: false,
          geocoder: false,
          homeButton: false,
          infoBox: false,
          navigationHelpButton: false,
          sceneModePicker: false,
          selectionIndicator: false,
          shouldAnimate: true,
          timeline: false,
          terrainProvider: new EllipsoidTerrainProvider(),
          useBrowserRecommendedResolution: true,
          vrButton: false,
        });

        if (isDisposed) {
          viewer.destroy();
          return;
        }

        viewerRef.current = viewer;
        setIsWebglUnavailable(false);

        viewer.scene.globe.enableLighting = true;
        viewer.scene.globe.showGroundAtmosphere = true;
        if (viewer.scene.skyAtmosphere) {
          viewer.scene.skyAtmosphere.show = true;
        }
        viewer.scene.screenSpaceCameraController.enableTilt = true;
        viewer.scene.screenSpaceCameraController.minimumZoomDistance = 350000;
        viewer.scene.screenSpaceCameraController.maximumZoomDistance = 52000000;
        viewer.camera.setView({
          destination: Cartesian3.fromDegrees(74, 27, 16000000),
        });

        const localProvider = await TileMapServiceImageryProvider.fromUrl(
          buildModuleUrl("Assets/Textures/NaturalEarthII"),
        );
        if (!isDisposed && viewer && !viewer.isDestroyed()) {
          viewer.imageryLayers.addImageryProvider(localProvider);
        }

        try {
          const satelliteProvider = await ArcGisMapServerImageryProvider.fromUrl(satelliteImageryUrl, {
            enablePickFeatures: false,
          });
          if (!isDisposed && viewer && !viewer.isDestroyed()) {
            viewer.imageryLayers.add(new ImageryLayer(satelliteProvider));
          }
        } catch {
          // Keep the local NaturalEarth globe interactive when satellite imagery is unavailable.
        }
      } catch {
        if (!isDisposed) {
          setIsWebglUnavailable(true);
        }
        if (viewer && !viewer.isDestroyed()) {
          viewer.destroy();
        }
        viewerRef.current = null;
        return;
      }

      if (!viewer || viewer.isDestroyed()) return;
      clickHandler = new ScreenSpaceEventHandler(viewer.scene.canvas);
      clickHandler.setInputAction((event: ScreenSpaceEventHandler.PositionedEvent) => {
        if (!viewer || viewer.isDestroyed()) return;
        const picked = viewer.scene.pick(event.position);
        const entity = picked?.id as Entity | undefined;
        const point = entity?.id ? pointByEntityIdRef.current.get(entity.id) : undefined;
        if (point) {
          onSelectRef.current(point);
        }
      }, ScreenSpaceEventType.LEFT_CLICK);
    }

    void createViewer();

    return () => {
      isDisposed = true;
      clickHandler?.destroy();
      if (viewerRef.current && !viewerRef.current.isDestroyed()) {
        viewerRef.current.destroy();
      }
      viewerRef.current = null;
      pointByEntityId.clear();
    };
  }, []);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;

    viewer.entities.removeAll();
    pointByEntityIdRef.current.clear();

    viewer.entities.add({
      id: "dawn-meridian",
      polyline: {
        positions: dawnPolylinePositions(dawnLongitude),
        width: 3,
        material: Color.fromCssColorString("#f2d7a0").withAlpha(0.95),
        clampToGround: false,
      },
    });

    points.forEach((item) => {
      const entityId = `${item.type}-${item.id}`;
      const selected = isPoint(item) && item.slug === selectedSlug;
      const dawnActive = isPoint(item) && activeDawnSlugs.has(item.slug);
      const markerColor = selected
        ? Color.fromCssColorString("#f7f5ea")
        : dawnActive || item.type === "cluster"
          ? Color.fromCssColorString("#d6c69b")
          : Color.fromCssColorString("#c9d7c1");
      const markerText = isPoint(item) ? String(item.session_count) : String(item.count);

      if (isPoint(item)) {
        pointByEntityIdRef.current.set(entityId, item);
      }

      viewer.entities.add({
        id: entityId,
        name: isPoint(item) ? item.name : `${item.count} locations`,
        position: Cartesian3.fromDegrees(item.longitude, item.latitude, selected ? 110000 : 85000),
        point: {
          pixelSize: selected ? 18 : item.type === "cluster" ? 16 : 12,
          color: markerColor,
          outlineColor: Color.WHITE.withAlpha(0.86),
          outlineWidth: 2,
        },
        label: {
          text: markerText,
          font: "600 12px Georgia, serif",
          fillColor: Color.fromCssColorString("#11120f"),
          outlineColor: Color.BLACK.withAlpha(0.45),
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          horizontalOrigin: HorizontalOrigin.CENTER,
          verticalOrigin: VerticalOrigin.CENTER,
        },
      });
    });

    viewer.scene.requestRender();
  }, [points, selectedSlug, activeDawnSlugs, dawnLongitude]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed() || !selectedSlug) return;

    const selected = points.find((item) => isPoint(item) && item.slug === selectedSlug);
    if (!selected || !isPoint(selected)) return;

    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(selected.longitude, selected.latitude, 2100000),
      duration: 0.85,
    });
  }, [points, selectedSlug]);

  return (
    <div className="globe-stage cesium-stage" aria-label="Interactive Cesium globe">
      <div ref={containerRef} className="cesium-host" />
      {isWebglUnavailable ? <StaticGlobeFallback points={points} selectedSlug={selectedSlug} /> : null}
      <div className="globe-hint">Drag to rotate / scroll to zoom / click a marker</div>
    </div>
  );
}

function StaticGlobeFallback({
  points,
  selectedSlug,
}: {
  points: Array<AtlasPoint | AtlasCluster>;
  selectedSlug: string | null;
}) {
  return (
    <div className="static-globe" aria-label="Static globe fallback">
      <span className="static-continent north-america" />
      <span className="static-continent south-america" />
      <span className="static-continent africa" />
      <span className="static-continent eurasia" />
      <span className="static-continent australia" />
      {points.slice(0, 18).map((point) => (
        <span
          key={`${point.type}-${point.id}`}
          className={[
            "static-globe-marker",
            point.type === "cluster" ? "cluster" : "",
            isPoint(point) && point.slug === selectedSlug ? "selected" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          style={markerStyle(point)}
        />
      ))}
    </div>
  );
}

export function AtlasExplorer({ initialView, points, dawn, sidePanelSession }: Props) {
  const [atlasPoints, setAtlasPoints] = useState(points);
  const [currentDawn, setCurrentDawn] = useState(dawn);
  const [view] = useState<AtlasView>(initialView);
  const [selectedMode, setSelectedMode] = useState(initialView === "list" ? "Night" : "Dawn");
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const locations = useMemo(() => atlasPoints.filter(isPoint), [atlasPoints]);
  const initialSelectedSlug =
    sidePanelSession && locations.some((location) => location.slug === sidePanelSession.location.slug)
      ? sidePanelSession.location.slug
      : locations[0]?.slug ?? null;
  const [selectedSlug, setSelectedSlug] = useState(initialSelectedSlug);
  const [currentSidePanelSession, setCurrentSidePanelSession] = useState(sidePanelSession);
  const selected = locations.find((point) => point.slug === selectedSlug) ?? locations[0] ?? null;
  const activeDawnSlugs = useMemo(
    () => new Set(currentDawn.active_locations.map((item) => item.location.slug)),
    [currentDawn.active_locations],
  );
  const dawnLongitude = useMemo(() => dawnLongitudeFromDate(currentDawn.generated_at), [currentDawn.generated_at]);
  const selectedDawn =
    currentDawn.active_locations.find((item) => item.location.slug === selected?.slug) ??
    currentDawn.next_locations.find((item) => item.location.slug === selected?.slug) ??
    null;
  const displayedLocations = locations.length > 0 ? locations.slice(0, 5) : [];
  const selectedSessionSlug = selected?.latest_session?.slug ?? null;

  useEffect(() => {
    if (selectedSlug && locations.some((point) => point.slug === selectedSlug)) {
      return;
    }
    setSelectedSlug(locations[0]?.slug ?? null);
  }, [locations, selectedSlug]);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSearchResults([]);
      setIsSearching(false);
      return;
    }

    let isCurrent = true;
    setIsSearching(true);
    const timeoutId = window.setTimeout(async () => {
      const results = await searchAtlas(trimmed);
      if (isCurrent) {
        setSearchResults(results);
        setIsSearching(false);
      }
    }, 250);

    return () => {
      isCurrent = false;
      window.clearTimeout(timeoutId);
    };
  }, [query]);

  useEffect(() => {
    let isCurrent = true;
    const refreshMs = Math.max(currentDawn.window.refresh_seconds, 1) * 1000;
    const intervalId = window.setInterval(async () => {
      const nextDawn = await fetchCurrentDawn();
      if (isCurrent) {
        setCurrentDawn(nextDawn);
      }
    }, refreshMs);

    return () => {
      isCurrent = false;
      window.clearInterval(intervalId);
    };
  }, [currentDawn.window.refresh_seconds]);

  useEffect(() => {
    if (!selectedSessionSlug) {
      setCurrentSidePanelSession(null);
      return;
    }
    if (currentSidePanelSession?.slug === selectedSessionSlug) {
      return;
    }

    let isCurrent = true;
    setCurrentSidePanelSession(null);
    void fetchSessionDetail(selectedSessionSlug).then((session) => {
      if (!isCurrent) {
        return;
      }
      setCurrentSidePanelSession(session ?? null);
    });

    return () => {
      isCurrent = false;
    };
  }, [currentSidePanelSession?.slug, selectedSessionSlug]);

  function selectLocation(point: AtlasPoint) {
    if (!locations.some((location) => location.slug === point.slug)) {
      setAtlasPoints((currentPoints) =>
        currentPoints.some((item) => isPoint(item) && item.slug === point.slug)
          ? currentPoints
          : [point, ...currentPoints],
      );
    }
    setSelectedSlug(point.slug);
  }

  function selectSearchResult(result: SearchResult) {
    if (result.type === "session" && result.session_slug) {
      return;
    }
    if (!locations.some((location) => location.slug === result.slug)) {
      const atlasPoint = result.atlas_point;
      if (!atlasPoint) {
        return;
      }
      setAtlasPoints((currentPoints) => [atlasPoint, ...currentPoints]);
    }
    setSelectedSlug(result.slug);
    setQuery("");
  }

  return (
    <section className="atlas-workspace atlas-reference-ui" aria-label="Birdsong atlas">
      <div className="atlas-main-panel">
        <div className="atlas-globe-panel">
          {view === "globe" ? (
            <CesiumGlobe
              points={atlasPoints}
              selectedSlug={selectedSlug}
              activeDawnSlugs={activeDawnSlugs}
              dawnLongitude={dawnLongitude}
              onSelectPoint={selectLocation}
            />
          ) : view === "map" ? (
            <div className="globe-stage" aria-label="Static atlas map">
              <StaticGlobeFallback points={atlasPoints} selectedSlug={selectedSlug} />
              <div className="globe-hint">Map view (static) · select a marker</div>
            </div>
          ) : (
            <div className="globe-stage" aria-label="Atlas list view">
              <ol className="atlas-list-view">
                {locations.map((location) => (
                  <li key={location.id}>
                    <button
                      type="button"
                      className={location.slug === selectedSlug ? "selected" : ""}
                      onClick={() => selectLocation(location)}
                    >
                      <strong>{location.name}</strong>
                      <span>{[location.region, location.country_code].filter(Boolean).join(" · ")}</span>
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          )}
          <div className="atlas-brand">
            <span>Birdsong</span>
            <span>Earth</span>
          </div>
          <LiveBadge className="atlas-live-left" />
          <div className="dawn-copy">
            <span>Now at dawn</span>
            <strong>{selected?.name ?? "No location selected"}</strong>
            <small>{selected?.region ?? selected?.country_code ?? "Published atlas site"}</small>
            <time>{selectedDawn?.local_time ?? formatLocalTime(selected?.timezone, currentDawn.generated_at)}</time>
            <small>local time</small>
            {selected?.latest_session ? (
              <Link className="listen-pill" href={`/sessions/${selected.latest_session.slug}`}>
                Listen
                <span aria-hidden="true">›</span>
              </Link>
            ) : (
              <button className="listen-pill" type="button">
                Listen
                <span aria-hidden="true">›</span>
              </button>
            )}
          </div>
          <button className="about-link" type="button">
            About
            <span aria-hidden="true">○</span>
          </button>
          <div className="globe-tools" aria-label="Globe tools">
            <button type="button" aria-label="Use current location">⌖</button>
            <button type="button" aria-label="Tune filters">≋</button>
            <button type="button" aria-label="Search">⌕</button>
          </div>
        </div>

        <div className="atlas-discovery-panel">
          <p>Where would you like to listen?</p>
          <div className="time-tabs" role="tablist" aria-label="Listening time">
            {listeningModes.map((mode) => (
              <button
                key={mode}
                type="button"
                role="tab"
                aria-selected={selectedMode === mode}
                onClick={() => setSelectedMode(mode)}
              >
                {mode}
              </button>
            ))}
          </div>
          <div className="location-carousel" aria-label="Featured locations">
            <button type="button" className="carousel-arrow" aria-label="Previous locations">
              ‹
            </button>
            {displayedLocations.map((location, index) => (
              <button
                type="button"
                key={location.id}
                className={[
                  "location-card",
                  `location-card-${index % 5}`,
                  location.slug === selectedSlug ? "selected" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() => selectLocation(location)}
              >
                <span>{location.name}</span>
                <small>{location.country_code ?? location.region ?? "Atlas site"}</small>
                <i aria-hidden="true" />
              </button>
            ))}
            <button type="button" className="carousel-arrow" aria-label="Next locations">
              ›
            </button>
          </div>
          <div className="atlas-search">
            <label htmlFor="atlas-search">Search location</label>
            <input
              id="atlas-search"
              type="search"
              value={query}
              placeholder="Search location"
              onChange={(event) => setQuery(event.target.value)}
            />
            {query.trim().length >= 2 ? (
              <div className="search-results" aria-live="polite">
                {isSearching ? <p>Searching...</p> : null}
                {!isSearching && searchResults.length === 0 ? <p>No public results found.</p> : null}
                {searchResults.map((result) =>
                  result.type === "session" && result.session_slug ? (
                    <Link key={`${result.type}-${result.id}`} href={`/sessions/${result.session_slug}`}>
                      <strong>{result.title}</strong>
                      <span>{[result.subtitle, result.habitat].filter(Boolean).join(" / ")}</span>
                    </Link>
                  ) : (
                    <button
                      type="button"
                      key={`${result.type}-${result.id}`}
                      onClick={() => selectSearchResult(result)}
                    >
                      <strong>{result.title}</strong>
                      <span>{[result.subtitle, result.habitat].filter(Boolean).join(" / ")}</span>
                    </button>
                  ),
                )}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <aside className="atlas-side-panel">
        {currentSidePanelSession ? (
          <SessionPlayer session={currentSidePanelSession} />
        ) : (
          <section className="atlas-side-empty">
            <h2>No session selected</h2>
            <p>Select a public atlas point with a published recording to load the player.</p>
          </section>
        )}
      </aside>
    </section>
  );
}

function LiveBadge({ className = "" }: { className?: string }) {
  return (
    <span className={["live-badge", className].filter(Boolean).join(" ")}>
      Live
      <i aria-hidden="true" />
    </span>
  );
}

function formatLocalTime(timezone: string | undefined, baseTime: string) {
  const generatedAt = new Date(baseTime);
  if (Number.isNaN(generatedAt.getTime())) {
    return "05:42";
  }
  if (!timezone) return "05:42";
  try {
    return new Intl.DateTimeFormat("en", {
      hour: "2-digit",
      hour12: false,
      minute: "2-digit",
      timeZone: timezone,
    }).format(generatedAt);
  } catch {
    return "05:42";
  }
}
