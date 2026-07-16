"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Entity, ScreenSpaceEventHandler, Viewer as CesiumViewer } from "cesium";
import type {
  AtlasCluster,
  AtlasPoint,
  DawnCurrentResponse,
  SearchResult,
  SessionDetail,
} from "../../lib/api/sessions";
import { ApiError, apiErrorMessage } from "../../lib/api/client";
import { fetchCurrentDawn, fetchSessionDetail, searchAtlas } from "../../lib/api/sessions";
import { useGlobalPlayerSuppression } from "../audio/PlayerProvider";
import { SessionPlayer } from "../audio/SessionPlayer";
import {
  filterLocationsByMode,
  listeningModeForLocation,
  listeningModeKicker,
  listeningModes,
  type ListeningMode,
} from "./listeningModes";

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
  focusRequest: number;
  activeDawnSlugs: Set<string>;
  onSelectPoint: (point: AtlasPoint) => void;
};

const satelliteImageryUrl = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer";
const desktopLocationCardCount = 5;
const mobileLocationCardCount = 2;
const focusedLocationHeight = 1500000;

function isPoint(item: AtlasPoint | AtlasCluster): item is AtlasPoint {
  return item.type === "point";
}

function markerStyle(point: AtlasPoint | AtlasCluster) {
  return {
    left: `${((point.longitude + 180) / 360) * 100}%`,
    top: `${((90 - point.latitude) / 180) * 100}%`,
  };
}

function distanceSquaredOnSphere(
  latitude: number,
  longitude: number,
  point: Pick<AtlasPoint, "latitude" | "longitude">,
) {
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180;
  const latitudeDelta = toRadians(point.latitude - latitude);
  const longitudeDelta = toRadians(point.longitude - longitude);
  const startLatitude = toRadians(latitude);
  const endLatitude = toRadians(point.latitude);
  return Math.sin(latitudeDelta / 2) ** 2
    + Math.cos(startLatitude) * Math.cos(endLatitude) * Math.sin(longitudeDelta / 2) ** 2;
}

function useLocationCardCount() {
  const [cardCount, setCardCount] = useState(desktopLocationCardCount);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 720px)");
    const sync = () => {
      setCardCount(query.matches ? mobileLocationCardCount : desktopLocationCardCount);
    };
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  return cardCount;
}

type CesiumModule = typeof import("cesium");

let cesiumScriptPromise: Promise<CesiumModule> | undefined;

function loadCesiumScript() {
  const cesiumWindow = window as typeof window & {
    CESIUM_BASE_URL?: string;
    Cesium?: CesiumModule;
  };
  if (cesiumWindow.Cesium) return Promise.resolve(cesiumWindow.Cesium);
  if (cesiumScriptPromise) return cesiumScriptPromise;

  cesiumWindow.CESIUM_BASE_URL = "/cesium/";
  cesiumScriptPromise = new Promise<CesiumModule>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "/cesium/Cesium.js";
    script.async = true;
    script.dataset.cesiumRuntime = "true";
    script.addEventListener("load", () => {
      if (cesiumWindow.Cesium) resolve(cesiumWindow.Cesium);
      else reject(new Error("Cesium runtime loaded without exposing window.Cesium"));
    });
    script.addEventListener("error", () => reject(new Error("Failed to load Cesium runtime")));
    document.head.append(script);
  });
  return cesiumScriptPromise;
}

function configureCesiumBaseUrl({ buildModuleUrl }: CesiumModule) {
  const urlBuilder = buildModuleUrl as typeof buildModuleUrl & { setBaseUrl?: (value: string) => void };
  urlBuilder.setBaseUrl?.("/cesium/");
}

function CesiumGlobe({ points, selectedSlug, focusRequest, activeDawnSlugs, onSelectPoint }: CesiumGlobeProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<CesiumViewer | null>(null);
  const cesiumRef = useRef<CesiumModule | null>(null);
  const pointByEntityIdRef = useRef(new Map<string, AtlasPoint>());
  const onSelectRef = useRef(onSelectPoint);
  const [isWebglUnavailable, setIsWebglUnavailable] = useState(false);
  const [isViewerReady, setIsViewerReady] = useState(false);

  useEffect(() => {
    onSelectRef.current = onSelectPoint;
  }, [onSelectPoint]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const host = container;

    let isDisposed = false;
    let clickHandler: ScreenSpaceEventHandler | null = null;
    let viewer: CesiumViewer | null = null;
    setIsViewerReady(false);
    const pointByEntityId = pointByEntityIdRef.current;

    async function createViewer() {
      try {
        const cesium = await loadCesiumScript();
        if (isDisposed) return;
        cesiumRef.current = cesium;
        const {
          ArcGisMapServerImageryProvider,
          Cartesian3,
          EllipsoidTerrainProvider,
          ImageryLayer,
          ScreenSpaceEventHandler,
          ScreenSpaceEventType,
          TileMapServiceImageryProvider,
          Viewer,
          buildModuleUrl,
        } = cesium;
        configureCesiumBaseUrl(cesium);
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
        if (isDisposed || !viewer || viewer.isDestroyed()) {
          return;
        }

        viewer.imageryLayers.addImageryProvider(localProvider);
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
        setIsViewerReady(true);

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
    }

    void createViewer();

    return () => {
      isDisposed = true;
      clickHandler?.destroy();
      setIsViewerReady(false);
      if (viewerRef.current && !viewerRef.current.isDestroyed()) {
        viewerRef.current.destroy();
      }
      viewerRef.current = null;
      cesiumRef.current = null;
      pointByEntityId.clear();
    };
  }, []);

  useEffect(() => {
    const viewer = viewerRef.current;
    const cesium = cesiumRef.current;
    if (!isViewerReady || !viewer || viewer.isDestroyed() || !cesium) return;
    const { Cartesian3, Color, HorizontalOrigin, LabelStyle, VerticalOrigin } = cesium;

    viewer.entities.removeAll();
    pointByEntityIdRef.current.clear();

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
  }, [activeDawnSlugs, isViewerReady, points, selectedSlug]);

  useEffect(() => {
    const viewer = viewerRef.current;
    const cesium = cesiumRef.current;
    if (!isViewerReady || !viewer || viewer.isDestroyed() || !selectedSlug || !cesium) return;
    const { Cartesian3 } = cesium;

    const selected = points.find((item) => isPoint(item) && item.slug === selectedSlug);
    if (!selected || !isPoint(selected)) return;

    const animationFrame = window.requestAnimationFrame(() => {
      if (viewer.isDestroyed()) return;
      viewer.resize();
      viewer.camera.flyTo({
        destination: Cartesian3.fromDegrees(selected.longitude, selected.latitude, focusedLocationHeight),
        duration: 0.85,
      });
    });

    return () => window.cancelAnimationFrame(animationFrame);
  }, [focusRequest, isViewerReady, points, selectedSlug]);

  return (
    <div
      className="globe-stage cesium-stage"
      aria-label="Interactive Cesium globe"
      data-focus-request={focusRequest}
      data-focus-height={focusedLocationHeight}
    >
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
  const locationCardCount = useLocationCardCount();
  const [atlasPoints, setAtlasPoints] = useState(points);
  const [currentDawn, setCurrentDawn] = useState(dawn);
  const [view] = useState<AtlasView>(initialView);
  const [selectedMode, setSelectedMode] = useState<ListeningMode>(initialView === "list" ? "Night" : "Dawn");
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [dawnRefreshError, setDawnRefreshError] = useState<string | null>(null);
  const [locationStatus, setLocationStatus] = useState<string | null>(null);
  const [isLocating, setIsLocating] = useState(false);
  const [globeFocusRequest, setGlobeFocusRequest] = useState(0);
  const [carouselStart, setCarouselStart] = useState(0);
  const allLocations = useMemo(() => atlasPoints.filter(isPoint), [atlasPoints]);
  const activeDawnSlugs = useMemo(
    () => new Set(currentDawn.active_locations.map((item) => item.location.slug)),
    [currentDawn.active_locations],
  );
  const locations = useMemo(
    () => filterLocationsByMode(allLocations, selectedMode, currentDawn.generated_at, activeDawnSlugs),
    [activeDawnSlugs, allLocations, currentDawn.generated_at, selectedMode],
  );
  const initialSelectedSlug =
    sidePanelSession && locations.some((location) => location.slug === sidePanelSession.location.slug)
      ? sidePanelSession.location.slug
      : locations[0]?.slug ?? null;
  const [selectedSlug, setSelectedSlug] = useState(initialSelectedSlug);
  const [isSidePanelOpen, setIsSidePanelOpen] = useState(false);
  const [sidePanelSessionSlug, setSidePanelSessionSlug] = useState<string | null>(sidePanelSession?.slug ?? null);
  const [currentSidePanelSession, setCurrentSidePanelSession] = useState(sidePanelSession);
  const [sidePanelState, setSidePanelState] = useState<
    "idle" | "loading" | "ready" | "not_found" | "forbidden" | "not_ready" | "unavailable"
  >(sidePanelSession ? "ready" : "idle");
  const [sidePanelError, setSidePanelError] = useState<string | null>(null);
  const currentSidePanelSessionRef = useRef<SessionDetail | null>(sidePanelSession);
  const selected = locations.find((point) => point.slug === selectedSlug) ?? locations[0] ?? null;
  const selectedDawn = [...currentDawn.active_locations, ...currentDawn.next_locations]
    .find((item) => item.location.slug === selected?.slug);
  const isLocalPlayerVisible = isSidePanelOpen && currentSidePanelSession !== null;
  const displayedLocations = useMemo(() => {
    const count = Math.min(locationCardCount, locations.length);
    if (count === 0) {
      return [];
    }
    if (locations.length <= locationCardCount) {
      return locations;
    }
    return Array.from({ length: count }, (_, index) => locations[(carouselStart + index) % locations.length]);
  }, [carouselStart, locationCardCount, locations]);
  const canPageLocations = locations.length > locationCardCount;
  const selectedSessionSlug = selected?.latest_session?.slug ?? null;

  useGlobalPlayerSuppression(isLocalPlayerVisible);

  useEffect(() => {
    if (selectedSlug && locations.some((point) => point.slug === selectedSlug)) {
      return;
    }
    setSelectedSlug(locations[0]?.slug ?? null);
  }, [locations, selectedSlug]);

  useEffect(() => {
    if (locations.length === 0) {
      setCarouselStart(0);
      return;
    }
    setCarouselStart((current) => (current >= locations.length ? 0 : current));
  }, [locations.length]);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSearchResults([]);
      setIsSearching(false);
      setSearchError(null);
      return;
    }

    let isCurrent = true;
    setIsSearching(true);
    setSearchError(null);
    const timeoutId = window.setTimeout(async () => {
      try {
        const results = await searchAtlas(trimmed);
        if (isCurrent) {
          setSearchResults(results);
        }
      } catch (error) {
        if (isCurrent) {
          setSearchResults([]);
          setSearchError(apiErrorMessage(error, "Search is unavailable."));
        }
      } finally {
        if (isCurrent) setIsSearching(false);
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
      try {
        const nextDawn = await fetchCurrentDawn(Math.max(250, allLocations.length));
        if (isCurrent) {
          setCurrentDawn(nextDawn);
          setDawnRefreshError(null);
        }
      } catch (error) {
        if (isCurrent) {
          setDawnRefreshError(apiErrorMessage(error, "Dawn timing could not be refreshed."));
        }
      }
    }, refreshMs);

    return () => {
      isCurrent = false;
      window.clearInterval(intervalId);
    };
  }, [allLocations.length, currentDawn.window.refresh_seconds]);

  useEffect(() => {
    currentSidePanelSessionRef.current = currentSidePanelSession;
  }, [currentSidePanelSession]);

  useEffect(() => {
    if (!isSidePanelOpen) {
      return;
    }
    if (!sidePanelSessionSlug) {
      setCurrentSidePanelSession(null);
      setSidePanelState("idle");
      setSidePanelError(null);
      return;
    }
    if (currentSidePanelSessionRef.current?.slug === sidePanelSessionSlug) {
      setSidePanelState("ready");
      return;
    }
    if (sidePanelSession?.slug === sidePanelSessionSlug) {
      setCurrentSidePanelSession(sidePanelSession);
      setSidePanelState("ready");
      setSidePanelError(null);
      return;
    }

    let isCurrent = true;
    setCurrentSidePanelSession(null);
    setSidePanelState("loading");
    setSidePanelError(null);
    void fetchSessionDetail(sidePanelSessionSlug)
      .then((session) => {
        if (!isCurrent) return;
        setCurrentSidePanelSession(session);
        setSidePanelState("ready");
      })
      .catch((error) => {
        if (!isCurrent) return;
        const status = error instanceof ApiError ? error.status : null;
        setSidePanelState(
          status === 404
            ? "not_found"
            : status === 403
              ? "forbidden"
              : status === 409 || status === 425
                ? "not_ready"
                : "unavailable",
        );
        setSidePanelError(apiErrorMessage(error, "The session could not be loaded."));
      });

    return () => {
      isCurrent = false;
    };
  }, [isSidePanelOpen, sidePanelSession, sidePanelSessionSlug]);

  function revealLocationInCarousel(slug: string) {
    if (locations.length <= locationCardCount) {
      return;
    }
    const index = locations.findIndex((location) => location.slug === slug);
    if (index !== -1) {
      setCarouselStart(index);
    }
  }

  function selectLocation(point: AtlasPoint, options: { revealInCarousel?: boolean } = {}) {
    if (!allLocations.some((location) => location.slug === point.slug)) {
      setAtlasPoints((currentPoints) =>
        currentPoints.some((item) => isPoint(item) && item.slug === point.slug)
          ? currentPoints
          : [point, ...currentPoints],
      );
    }
    setSelectedSlug(point.slug);
    if (options.revealInCarousel) {
      revealLocationInCarousel(point.slug);
    }
  }

  function selectSearchResult(result: SearchResult) {
    if (result.type === "session" && result.session_slug) {
      return;
    }
    const existingLocation = allLocations.find((location) => location.slug === result.slug);
    const resultLocation = existingLocation ?? result.atlas_point;
    if (!resultLocation) {
      return;
    }
    const resultMode = listeningModeForLocation(resultLocation, currentDawn.generated_at, activeDawnSlugs);
    setSelectedMode(resultMode);
    if (!existingLocation) {
      const atlasPoint = result.atlas_point;
      if (!atlasPoint) {
        return;
      }
      setAtlasPoints((currentPoints) => [atlasPoint, ...currentPoints]);
      setCarouselStart(0);
    } else {
      const modeLocations = filterLocationsByMode(
        allLocations,
        resultMode,
        currentDawn.generated_at,
        activeDawnSlugs,
      );
      const resultIndex = modeLocations.findIndex((location) => location.slug === result.slug);
      setCarouselStart(resultIndex === -1 ? 0 : resultIndex);
    }
    setSelectedSlug(result.slug);
    setQuery("");
  }

  function pageLocations(delta: number) {
    if (!canPageLocations) {
      return;
    }
    setCarouselStart((current) => (current + delta + locations.length) % locations.length);
  }

  function selectMode(mode: ListeningMode) {
    setSelectedMode(mode);
    setCarouselStart(0);
  }

  function useCurrentLocation() {
    if (!window.isSecureContext) {
      setLocationStatus("Safari requires HTTPS to use your location. Open ORNA Atlas over a secure HTTPS address.");
      return;
    }
    if (!navigator.geolocation) {
      setLocationStatus("Current location is not supported by this browser.");
      return;
    }
    if (allLocations.length === 0) {
      setLocationStatus("No public listening locations are available.");
      return;
    }

    setIsLocating(true);
    setLocationStatus("Finding the nearest listening location…");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const nearest = allLocations.reduce((best, candidate) =>
          distanceSquaredOnSphere(coords.latitude, coords.longitude, candidate)
            < distanceSquaredOnSphere(coords.latitude, coords.longitude, best)
            ? candidate
            : best,
        );
        const mode = listeningModeForLocation(nearest, currentDawn.generated_at, activeDawnSlugs);
        const modeLocations = filterLocationsByMode(
          allLocations,
          mode,
          currentDawn.generated_at,
          activeDawnSlugs,
        );
        setSelectedMode(mode);
        setCarouselStart(Math.max(0, modeLocations.findIndex((location) => location.slug === nearest.slug)));
        setSelectedSlug(nearest.slug);
        setLocationStatus(`Nearest listening location: ${nearest.name}.`);
        setIsLocating(false);
      },
      (error) => {
        const message = error.code === error.PERMISSION_DENIED
          ? "Safari denied location access for this website. In Safari Settings → Websites → Location, set this site to Allow, then reload."
          : error.code === error.TIMEOUT
            ? "Safari could not determine your location in time. Check Location Services and try again."
            : "Safari could not determine your current location. Check Location Services and try again.";
        setLocationStatus(message);
        setIsLocating(false);
      },
      { enableHighAccuracy: false, maximumAge: 300_000, timeout: 10_000 },
    );
  }

  function openSelectedSession() {
    if (!selectedSessionSlug) {
      return;
    }
    setGlobeFocusRequest((current) => current + 1);
    setSidePanelSessionSlug(selectedSessionSlug);
    setIsSidePanelOpen(true);
  }

  return (
    <section
      className={["atlas-workspace atlas-reference-ui", isSidePanelOpen ? "atlas-reference-ui--player-open" : ""]
        .filter(Boolean)
        .join(" ")}
      aria-label="ORNA Atlas"
    >
      <div className="atlas-main-panel">
        <div className="atlas-globe-panel">
          {view === "globe" ? (
            <CesiumGlobe
              points={locations}
              selectedSlug={selectedSlug}
              focusRequest={globeFocusRequest}
              activeDawnSlugs={activeDawnSlugs}
              onSelectPoint={(point) => selectLocation(point, { revealInCarousel: true })}
            />
          ) : view === "map" ? (
            <div className="globe-stage" aria-label="Static atlas map">
              <StaticGlobeFallback points={locations} selectedSlug={selectedSlug} />
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
            <span>ORNA</span>
            <span>Atlas</span>
          </div>
          {selectedDawn?.state === "active" ? <DawnNowBadge className="atlas-live-left" /> : null}
          <div className="dawn-copy">
            <span>{listeningModeKicker[selectedMode]}</span>
            <strong>{selected?.name ?? "No location selected"}</strong>
            <small>{selected?.region ?? selected?.country_code ?? "Published atlas site"}</small>
            <time>{formatLocalTime(selected?.timezone, currentDawn.generated_at)}</time>
            <small>local time</small>
            {selected?.latest_session ? (
              <button
                className="listen-pill"
                type="button"
                aria-controls="atlas-session-player"
                aria-expanded={isSidePanelOpen}
                onClick={openSelectedSession}
              >
                Enter
                <span aria-hidden="true">›</span>
              </button>
            ) : (
              <button className="listen-pill" type="button" disabled>
                Enter
                <span aria-hidden="true">›</span>
              </button>
            )}
          </div>
          <Link className="about-link" href="/about">
            About
          </Link>
          <div className="globe-tools" aria-label="Globe tools">
            <button
              type="button"
              aria-label="Use current location"
              title="Find the nearest public listening location"
              aria-busy={isLocating}
              disabled={isLocating}
              onClick={useCurrentLocation}
            >
              ⌖
            </button>
            <button
              type="button"
              aria-label="Search"
              onClick={() => document.getElementById("atlas-search")?.focus()}
            >
              ⌕
            </button>
          </div>
          {locationStatus ? (
            <p className="globe-location-status" role="status">
              {locationStatus}
            </p>
          ) : null}
        </div>

        <div className="atlas-discovery-panel">
          {dawnRefreshError ? (
            <p className="atlas-data-warning" role="status">
              {dawnRefreshError} Showing the last successful dawn update.
            </p>
          ) : null}
          <p>Where would you like to listen?</p>
          <div
            className="time-tabs"
            id="atlas-listening-time"
            role="tablist"
            aria-label="Listening time"
            tabIndex={-1}
          >
            {listeningModes.map((mode) => (
              <button
                key={mode}
                type="button"
                role="tab"
                aria-selected={selectedMode === mode}
                onClick={() => selectMode(mode)}
              >
                {mode}
              </button>
            ))}
          </div>
          <div className="location-carousel" aria-label="Featured locations">
            <button
              type="button"
              className="carousel-arrow"
              aria-label="Previous locations"
              disabled={!canPageLocations}
              onClick={() => pageLocations(-1)}
            >
              ‹
            </button>
            {displayedLocations.length > 0 ? (
              displayedLocations.map((location, index) => (
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
              ))
            ) : (
              <p className="location-carousel-empty">No locations in this time window.</p>
            )}
            <button
              type="button"
              className="carousel-arrow"
              aria-label="Next locations"
              disabled={!canPageLocations}
              onClick={() => pageLocations(1)}
            >
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
                {searchError ? <p role="alert">{searchError}</p> : null}
                {!isSearching && !searchError && searchResults.length === 0 ? <p>No public results found.</p> : null}
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

      {isSidePanelOpen ? (
        <aside className="atlas-side-panel" id="atlas-session-player">
          {currentSidePanelSession ? (
            <SessionPlayer session={currentSidePanelSession} onClose={() => setIsSidePanelOpen(false)} />
          ) : (
            <section className="atlas-side-empty" aria-live="polite">
              <h2>
                {sidePanelState === "loading"
                  ? "Loading session"
                  : sidePanelState === "not_found"
                    ? "Session not found"
                    : sidePanelState === "forbidden"
                      ? "Session access is restricted"
                      : sidePanelState === "not_ready"
                        ? "Session is not ready"
                        : sidePanelState === "unavailable"
                          ? "Session unavailable"
                          : "No session selected"}
              </h2>
              <p>
                {sidePanelError
                  ?? (sidePanelState === "loading"
                    ? "Preparing the listening console…"
                    : "Select a public atlas point with a published recording to load the player.")}
              </p>
            </section>
          )}
        </aside>
      ) : null}
    </section>
  );
}

function DawnNowBadge({ className = "" }: { className?: string }) {
  return (
    <span className={["live-badge", className].filter(Boolean).join(" ")}>
      Dawn now
      <i aria-hidden="true" />
    </span>
  );
}

function formatLocalTime(timezone: string | undefined, baseTime: string) {
  const generatedAt = new Date(baseTime);
  if (Number.isNaN(generatedAt.getTime())) {
    return "--:--";
  }
  if (!timezone) return "--:--";
  try {
    return new Intl.DateTimeFormat("en", {
      hour: "2-digit",
      hour12: false,
      minute: "2-digit",
      timeZone: timezone,
    }).format(generatedAt);
  } catch {
    return "--:--";
  }
}
