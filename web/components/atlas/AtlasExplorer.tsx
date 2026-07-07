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
  DawnFollowResponse,
  DawnLocation,
  SearchResult,
} from "../../lib/api/sessions";
import { fetchAtlasPoints, fetchCurrentDawn, fetchFollowDawn, searchAtlas } from "../../lib/api/sessions";

type AtlasView = "globe" | "map" | "list";

type Props = {
  initialView: AtlasView;
  points: Array<AtlasPoint | AtlasCluster>;
  dawn: DawnCurrentResponse;
};

type CesiumGlobeProps = {
  points: Array<AtlasPoint | AtlasCluster>;
  selectedSlug: string | null;
  activeDawnSlugs: Set<string>;
  dawnLongitude: number;
  onSelectPoint: (point: AtlasPoint) => void;
};

const satelliteImageryUrl = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer";
const habitatOptions = ["forest", "wetland", "steppe", "coast"];

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
          destination: Cartesian3.fromDegrees(24, 34, 17000000),
        });

        const localProvider = await TileMapServiceImageryProvider.fromUrl(
          buildModuleUrl("Assets/Textures/NaturalEarthII"),
        );
        if (!isDisposed && viewer && !viewer.isDestroyed()) {
          viewer.imageryLayers.addImageryProvider(localProvider);
        }

        const satelliteProvider = await ArcGisMapServerImageryProvider.fromUrl(satelliteImageryUrl, {
          enablePickFeatures: false,
        });
        if (!isDisposed && viewer && !viewer.isDestroyed()) {
          viewer.imageryLayers.add(new ImageryLayer(satelliteProvider));
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
        material: Color.fromCssColorString("#f6c46b").withAlpha(0.92),
        clampToGround: false,
      },
    });

    points.forEach((item) => {
      const entityId = `${item.type}-${item.id}`;
      const selected = isPoint(item) && item.slug === selectedSlug;
      const dawnActive = isPoint(item) && activeDawnSlugs.has(item.slug);
      const markerColor = selected
        ? Color.fromCssColorString("#fff4c2")
        : dawnActive || item.type === "cluster"
          ? Color.fromCssColorString("#f6c46b")
          : Color.fromCssColorString("#9bd8bd");
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
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: {
          text: markerText,
          font: "600 12px Inter, sans-serif",
          fillColor: selected || item.type === "cluster" ? Color.fromCssColorString("#07110f") : Color.WHITE,
          outlineColor: Color.BLACK.withAlpha(0.55),
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          horizontalOrigin: HorizontalOrigin.CENTER,
          verticalOrigin: VerticalOrigin.CENTER,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
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
      destination: Cartesian3.fromDegrees(selected.longitude, selected.latitude, 2200000),
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

export function AtlasExplorer({ initialView, points, dawn }: Props) {
  const [view, setView] = useState<AtlasView>(initialView);
  const [atlasPoints, setAtlasPoints] = useState(points);
  const [dawnView, setDawnView] = useState<"current" | "follow">("current");
  const [currentDawn, setCurrentDawn] = useState(dawn);
  const [followDawn, setFollowDawn] = useState<DawnFollowResponse | null>(null);
  const [isLoadingDawn, setIsLoadingDawn] = useState(false);
  const [selectedHabitats, setSelectedHabitats] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const locations = useMemo(() => atlasPoints.filter(isPoint), [atlasPoints]);
  const [selectedSlug, setSelectedSlug] = useState(locations[0]?.slug ?? null);
  const selected = locations.find((point) => point.slug === selectedSlug) ?? locations[0] ?? null;
  const dawnLocations =
    dawnView === "follow" && followDawn
      ? followDawn.locations
      : [...currentDawn.active_locations, ...currentDawn.next_locations];
  const activeDawnSlugs = useMemo(
    () => new Set(currentDawn.active_locations.map((item) => item.location.slug)),
    [currentDawn.active_locations],
  );
  const dawnLongitude = useMemo(() => dawnLongitudeFromDate(currentDawn.generated_at), [currentDawn.generated_at]);
  const dawnLineLeft = `${((dawnLongitude + 180) / 360) * 100}%`;

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

  async function switchDawnView(nextView: "current" | "follow") {
    setDawnView(nextView);
    if (nextView === "follow" && !followDawn) {
      setIsLoadingDawn(true);
      try {
        setFollowDawn(await fetchFollowDawn());
      } finally {
        setIsLoadingDawn(false);
      }
    }
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
    setView("globe");
    setQuery("");
  }

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

  return (
    <section className="atlas-workspace">
      <div className="atlas-toolbar" aria-label="Atlas controls">
        <div className="segmented" role="tablist" aria-label="Atlas view">
          <button type="button" role="tab" aria-selected={view === "globe"} onClick={() => setView("globe")}>
            Globe
          </button>
          <button type="button" role="tab" aria-selected={view === "map"} onClick={() => setView("map")}>
            Map
          </button>
          <button type="button" role="tab" aria-selected={view === "list"} onClick={() => setView("list")}>
            List
          </button>
        </div>
        <div className="segmented" role="tablist" aria-label="Dawn mode">
          <button
            type="button"
            role="tab"
            aria-selected={dawnView === "current"}
            onClick={() => switchDawnView("current")}
          >
            Dawn now
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={dawnView === "follow"}
            onClick={() => switchDawnView("follow")}
          >
            Follow dawn
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
      <div className="atlas-search">
        <label htmlFor="atlas-search">Search atlas</label>
        <input
          id="atlas-search"
          type="search"
          value={query}
          placeholder="Location, habitat, or session"
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
                  disabled={isLoading}
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

      {view === "globe" ? (
        <div className="atlas-grid">
          <CesiumGlobe
            points={atlasPoints}
            selectedSlug={selectedSlug}
            activeDawnSlugs={activeDawnSlugs}
            dawnLongitude={dawnLongitude}
            onSelectPoint={selectLocation}
          />
          <LocationDrawer
            location={selected}
            dawnLocations={dawnLocations}
            isLoadingDawn={isLoadingDawn}
            onSelectLocation={selectLocation}
          />
        </div>
      ) : view === "map" ? (
        <div className="atlas-grid">
          <div className="atlas-map" aria-label="Location map">
            <div className="map-grid" />
            <div className="dawn-terminator" style={{ left: dawnLineLeft }} aria-hidden="true" />
            {atlasPoints.map((point) => (
              <button
                type="button"
                key={`${point.type}-${point.id}`}
                className={[
                  point.type === "cluster" ? "atlas-marker cluster" : "atlas-marker",
                  isPoint(point) && activeDawnSlugs.has(point.slug) ? "is-dawn" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
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
          <LocationDrawer
            location={selected}
            dawnLocations={dawnLocations}
            isLoadingDawn={isLoadingDawn}
            onSelectLocation={selectLocation}
          />
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
          <LocationDrawer
            location={selected}
            dawnLocations={dawnLocations}
            isLoadingDawn={isLoadingDawn}
            onSelectLocation={selectLocation}
          />
        </div>
      )}
    </section>
  );
}

function formatMinutes(value: number | null) {
  if (value === null) return "No sunrise today";
  if (value === 0) return "at sunrise";
  if (value > 0) return `in ${value} min`;
  return `${Math.abs(value)} min ago`;
}

function LocationDrawer({
  location,
  dawnLocations,
  isLoadingDawn,
  onSelectLocation,
}: {
  location: AtlasPoint | null;
  dawnLocations: DawnLocation[];
  isLoadingDawn: boolean;
  onSelectLocation: (point: AtlasPoint) => void;
}) {
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
      <div className="dawn-panel">
        <h3>Dawn</h3>
        {isLoadingDawn ? <p>Loading dawn path...</p> : null}
        <ol>
          {dawnLocations.slice(0, 5).map((item) => (
            <li key={`${item.location.id}-${item.state}`}>
              <button type="button" onClick={() => onSelectLocation(item.location)}>
                <strong>{item.location.name}</strong>
                <span>
                  {item.local_time} local / {formatMinutes(item.minutes_until_sunrise)}
                </span>
              </button>
            </li>
          ))}
        </ol>
      </div>
    </aside>
  );
}
