"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Cartesian2, Entity, ScreenSpaceEventHandler, Viewer as CesiumViewer } from "cesium";
import type {
  AtlasCluster,
  AtlasPoint,
  DawnCurrentResponse,
  SearchResult,
  SessionDetail,
} from "../../lib/api/sessions";
import { ApiError, apiErrorMessage } from "../../lib/api/client";
import { fetchCurrentDawn, fetchSessionDetail, includeDawnLocations, searchAtlas } from "../../lib/api/sessions";
import { useGlobalPlayerSuppression, usePlayer } from "../audio/PlayerProvider";
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
  initialSelectedSlug?: string | null;
  initialSearchQuery?: string;
  sidePanelSession: SessionDetail | null;
  showInternalNavigation?: boolean;
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
const minimumGlobeZoomDistance = 350000;
const maximumGlobeZoomDistance = 52000000;
const markerDragThresholdPixels = 8;

function isPoint(item: AtlasPoint | AtlasCluster): item is AtlasPoint {
  return item.type === "point";
}

function isLockedPoint(point: AtlasPoint | null | undefined) {
  return point?.latest_session?.access_level === "members_only";
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
  const [hoveredPoint, setHoveredPoint] = useState<{ point: AtlasPoint; x: number; y: number } | null>(null);
  const [zoomBounds, setZoomBounds] = useState({ atMinimum: false, atMaximum: false });

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
    let removeCameraMoveListener: (() => void) | null = null;
    let removeCameraChangedListener: (() => void) | null = null;
    let zoomAnimationFrame: number | null = null;
    let wheelHandler: ((event: WheelEvent) => void) | null = null;
    let pointerStart: { x: number; y: number } | null = null;
    let pointerExceededDragThreshold = false;
    const trackPointerStart = (event: PointerEvent) => {
      pointerStart = { x: event.clientX, y: event.clientY };
      pointerExceededDragThreshold = false;
    };
    const trackPointerMovement = (event: PointerEvent) => {
      if (!pointerStart) return;
      const distance = Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y);
      if (distance > markerDragThresholdPixels) pointerExceededDragThreshold = true;
    };
    host.addEventListener("pointerdown", trackPointerStart);
    host.addEventListener("pointermove", trackPointerMovement);
    setIsViewerReady(false);
    const pointByEntityId = pointByEntityIdRef.current;

    async function createViewer() {
      try {
        const cesium = await loadCesiumScript();
        if (isDisposed) return;
        cesiumRef.current = cesium;
        const {
          ArcGisMapServerImageryProvider,
          CameraEventType,
          Cartesian2,
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
        viewer.scene.screenSpaceCameraController.enableCollisionDetection = true;
        viewer.scene.screenSpaceCameraController.inertiaSpin = 0.9;
        viewer.scene.screenSpaceCameraController.inertiaTranslate = 0.9;
        viewer.scene.screenSpaceCameraController.inertiaZoom = 0.8;
        viewer.scene.screenSpaceCameraController.zoomEventTypes = [CameraEventType.PINCH];
        viewer.scene.screenSpaceCameraController.minimumZoomDistance = minimumGlobeZoomDistance;
        viewer.scene.screenSpaceCameraController.maximumZoomDistance = maximumGlobeZoomDistance;
        viewer.camera.constrainedAxis = Cartesian3.UNIT_Z;
        viewer.camera.setView({
          destination: Cartesian3.fromDegrees(74, 27, 16000000),
        });
        const syncZoomBounds = () => {
          const height = viewer?.camera.positionCartographic.height ?? 16000000;
          setZoomBounds({
            atMinimum: height <= minimumGlobeZoomDistance * 1.01,
            atMaximum: height >= maximumGlobeZoomDistance * 0.99,
          });
        };
        removeCameraMoveListener = viewer.camera.moveEnd.addEventListener(syncZoomBounds);
        const syncDistanceScaledRotation = () => {
          if (!viewer || viewer.isDestroyed()) return;
          const normalizedDistance = Math.min(
            Math.max(viewer.camera.positionCartographic.height / maximumGlobeZoomDistance, 0),
            1,
          );
          viewer.scene.screenSpaceCameraController.maximumMovementRatio = 0.03 + normalizedDistance * 0.17;
        };
        removeCameraChangedListener = viewer.camera.changed.addEventListener(syncDistanceScaledRotation);
        syncZoomBounds();
        syncDistanceScaledRotation();

        wheelHandler = (event: WheelEvent) => {
          if (!viewer || viewer.isDestroyed()) return;
          event.preventDefault();
          const ray = viewer.camera.getPickRay(new Cartesian2(event.offsetX, event.offsetY));
          const cursorTarget = ray ? viewer.scene.globe.pick(ray, viewer.scene) : undefined;
          if (!cursorTarget) return;
          const currentHeight = viewer.camera.positionCartographic.height;
          const targetHeight = Math.min(
            maximumGlobeZoomDistance,
            Math.max(
              minimumGlobeZoomDistance,
              currentHeight * (event.deltaY < 0 ? 0.76 : 1.24),
            ),
          );
          const start = Cartesian3.clone(viewer.camera.position);
          const fromTarget = Cartesian3.subtract(start, cursorTarget, new Cartesian3());
          const end = Cartesian3.add(
            cursorTarget,
            Cartesian3.multiplyByScalar(
              fromTarget,
              targetHeight / currentHeight,
              new Cartesian3(),
            ),
            new Cartesian3(),
          );
          if (zoomAnimationFrame !== null) window.cancelAnimationFrame(zoomAnimationFrame);
          const step = () => {
            if (!viewer || viewer.isDestroyed()) return;
            const next = Cartesian3.lerp(viewer.camera.position, end, 0.18, new Cartesian3());
            viewer.camera.position = next;
            viewer.scene.requestRender();
            if (Cartesian3.distance(next, end) > 100) {
              zoomAnimationFrame = window.requestAnimationFrame(step);
            } else {
              viewer.camera.position = end;
              zoomAnimationFrame = null;
              syncZoomBounds();
            }
          };
          zoomAnimationFrame = window.requestAnimationFrame(step);
        };
        viewer.scene.canvas.addEventListener("wheel", wheelHandler, { passive: false });

        const localProvider = await TileMapServiceImageryProvider.fromUrl(
          buildModuleUrl("Assets/Textures/NaturalEarthII"),
        );
        if (isDisposed || !viewer || viewer.isDestroyed()) {
          return;
        }

        viewer.imageryLayers.addImageryProvider(localProvider);
        clickHandler = new ScreenSpaceEventHandler(viewer.scene.canvas);
        clickHandler.setInputAction((event: ScreenSpaceEventHandler.PositionedEvent) => {
          if (pointerExceededDragThreshold) return;
          if (!viewer || viewer.isDestroyed()) return;
          const picked = viewer.scene.pick(event.position);
          const entity = picked?.id as Entity | undefined;
          const point = entity?.id ? pointByEntityIdRef.current.get(entity.id) : undefined;
          if (point) {
            onSelectRef.current(point);
          }
        }, ScreenSpaceEventType.LEFT_CLICK);
        clickHandler.setInputAction((event: { endPosition: Cartesian2 }) => {
          if (!viewer || viewer.isDestroyed()) return;
          const picked = viewer.scene.pick(event.endPosition);
          const entity = picked?.id as Entity | undefined;
          const point = entity?.id ? pointByEntityIdRef.current.get(entity.id) : undefined;
          setHoveredPoint(point ? { point, x: event.endPosition.x, y: event.endPosition.y } : null);
        }, ScreenSpaceEventType.MOUSE_MOVE);
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
      host.removeEventListener("pointerdown", trackPointerStart);
      host.removeEventListener("pointermove", trackPointerMovement);
      removeCameraMoveListener?.();
      removeCameraChangedListener?.();
      if (zoomAnimationFrame !== null) window.cancelAnimationFrame(zoomAnimationFrame);
      if (wheelHandler && viewer && !viewer.isDestroyed()) {
        viewer.scene.canvas.removeEventListener("wheel", wheelHandler);
      }
      clickHandler?.destroy();
      setIsViewerReady(false);
      if (viewerRef.current && !viewerRef.current.isDestroyed()) {
        viewerRef.current.destroy();
      }
      viewerRef.current = null;
      cesiumRef.current = null;
      pointByEntityId.clear();
      setHoveredPoint(null);
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
      const hovered = isPoint(item) && item.slug === hoveredPoint?.point.slug;
      const dawnActive = isPoint(item) && activeDawnSlugs.has(item.slug);
      const locked = isPoint(item) && item.latest_session?.access_level === "members_only";
      const markerColor = selected
        ? Color.fromCssColorString("#f7f5ea")
        : locked
          ? Color.fromCssColorString("#d8965b")
          : dawnActive || item.type === "cluster"
            ? Color.fromCssColorString("#d6c69b")
            : Color.fromCssColorString("#c9d7c1");
      const markerText = locked
        ? "🔒"
        : isPoint(item) ? String(item.session_count) : String(item.count);

      if (isPoint(item)) {
        pointByEntityIdRef.current.set(entityId, item);
      }

      viewer.entities.add({
        id: entityId,
        name: isPoint(item) ? item.name : `${item.count} locations`,
        position: Cartesian3.fromDegrees(item.longitude, item.latitude, selected ? 110000 : 85000),
        point: {
          pixelSize: selected ? 20 : hovered ? 17 : item.type === "cluster" ? 16 : 12,
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
  }, [activeDawnSlugs, hoveredPoint?.point.slug, isViewerReady, points, selectedSlug]);

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

  function changeZoom(direction: "in" | "out") {
    const viewer = viewerRef.current;
    const cesium = cesiumRef.current;
    if (!viewer || viewer.isDestroyed() || !cesium) return;
    const position = viewer.camera.positionCartographic;
    const multiplier = direction === "in" ? 0.76 : 1.24;
    const targetHeight = Math.min(
      maximumGlobeZoomDistance,
      Math.max(minimumGlobeZoomDistance, position.height * multiplier),
    );
    viewer.camera.flyTo({
      destination: cesium.Cartesian3.fromRadians(position.longitude, position.latitude, targetHeight),
      duration: 0.28,
    });
  }

  function resetGlobe() {
    window.dispatchEvent(new CustomEvent("orna:analytics", {
      detail: { name: "reset_view_click", placement: "globe_controls" },
    }));
    const viewer = viewerRef.current;
    const cesium = cesiumRef.current;
    if (!viewer || viewer.isDestroyed() || !cesium) return;
    viewer.camera.flyTo({
      destination: cesium.Cartesian3.fromDegrees(74, 27, 16000000),
      duration: 0.65,
    });
  }

  return (
    <div
      className="globe-stage cesium-stage"
      aria-label="Interactive Cesium globe"
      data-focus-request={focusRequest}
      data-focus-height={focusedLocationHeight}
      data-inertia-spin="0.9"
      data-inertia-zoom="0.8"
      data-marker-drag-threshold={markerDragThresholdPixels}
      data-pole-clamp="z-axis"
      data-touch-controls="native"
      data-zoom-to-cursor="native"
    >
      <div ref={containerRef} className="cesium-host" />
      {hoveredPoint ? (
        <div
          className="globe-marker-tooltip"
          role="tooltip"
          style={{ left: hoveredPoint.x, top: hoveredPoint.y }}
        >
          <strong>{hoveredPoint.point.name}</strong>
          <span>{hoveredPoint.point.session_count} recording{hoveredPoint.point.session_count === 1 ? "" : "s"}</span>
        </div>
      ) : null}
      {isWebglUnavailable ? <StaticGlobeFallback points={points} selectedSlug={selectedSlug} /> : null}
      <div className="cesium-zoom-controls" role="group" aria-label="Globe zoom controls">
        <button type="button" aria-label="Zoom in" disabled={zoomBounds.atMinimum} onClick={() => changeZoom("in")}>+</button>
        <button type="button" aria-label="Zoom out" disabled={zoomBounds.atMaximum} onClick={() => changeZoom("out")}>−</button>
        <button type="button" aria-label="Reset globe" onClick={resetGlobe}>↺</button>
      </div>
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

export function AtlasExplorer({
  initialView,
  points,
  dawn,
  initialSelectedSlug: preferredInitialSlug = null,
  initialSearchQuery = "",
  sidePanelSession,
  showInternalNavigation = true,
}: Props) {
  const { currentSession: globalPlayerSession, play } = usePlayer();
  const locationCardCount = useLocationCardCount();
  const [atlasPoints, setAtlasPoints] = useState(points);
  const [currentDawn, setCurrentDawn] = useState(dawn);
  const [view] = useState<AtlasView>(initialView);
  const [selectedMode, setSelectedMode] = useState<ListeningMode>(
    preferredInitialSlug
      && [...dawn.active_locations, ...dawn.next_locations]
        .some((item) => item.location.slug === preferredInitialSlug)
      ? "Dawn"
      : initialView === "list"
        ? "Night"
        : "Dawn",
  );
  const [query, setQuery] = useState(initialSearchQuery.trim());
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
  const dawnModeSlugs = useMemo(
    () => new Set(
      [...currentDawn.active_locations, ...currentDawn.next_locations].map((item) => item.location.slug),
    ),
    [currentDawn.active_locations, currentDawn.next_locations],
  );
  const locations = useMemo(
    () => filterLocationsByMode(allLocations, selectedMode, currentDawn.generated_at, dawnModeSlugs),
    [allLocations, currentDawn.generated_at, dawnModeSlugs, selectedMode],
  );
  const initialSelectedSlug = preferredInitialSlug && locations.some((location) => location.slug === preferredInitialSlug)
    ? preferredInitialSlug
    : sidePanelSession && locations.some((location) => location.slug === sidePanelSession.location.slug)
      ? sidePanelSession.location.slug
      : locations[0]?.slug ?? null;
  const [selectedSlug, setSelectedSlug] = useState(initialSelectedSlug);
  const [isSidePanelOpen, setIsSidePanelOpen] = useState(false);
  const [isSoftPaywallOpen, setIsSoftPaywallOpen] = useState(false);
  const [sidePanelSessionSlug, setSidePanelSessionSlug] = useState<string | null>(sidePanelSession?.slug ?? null);
  const [currentSidePanelSession, setCurrentSidePanelSession] = useState(sidePanelSession);
  const [sidePanelState, setSidePanelState] = useState<
    "idle" | "loading" | "ready" | "not_found" | "forbidden" | "not_ready" | "unavailable"
  >(sidePanelSession ? "ready" : "idle");
  const [sidePanelError, setSidePanelError] = useState<string | null>(null);
  const currentSidePanelSessionRef = useRef<SessionDetail | null>(sidePanelSession);
  const previewIntentSlugRef = useRef<string | null>(null);
  const softPaywallRef = useRef<HTMLElement | null>(null);
  const paywallTriggerRef = useRef<HTMLElement | null>(null);
  const selected = locations.find((point) => point.slug === selectedSlug)
    ?? allLocations.find((point) => point.slug === selectedSlug)
    ?? locations[0]
    ?? allLocations[0]
    ?? null;
  const selectedDawn = [...currentDawn.active_locations, ...currentDawn.next_locations]
    .find((item) => item.location.slug === selected?.slug);
  const isLocalPlayerVisible = isSidePanelOpen
    && currentSidePanelSession !== null
    && (!globalPlayerSession || globalPlayerSession.id === currentSidePanelSession.id);
  const displayedLocations = useMemo(() => {
    const count = Math.min(locationCardCount, locations.length);
    if (count === 0) {
      return [];
    }
    if (locations.length <= locationCardCount) {
      return locations;
    }
    return locations.slice(carouselStart, carouselStart + count);
  }, [carouselStart, locationCardCount, locations]);
  const maxCarouselStart = Math.max(0, locations.length - Math.min(locationCardCount, locations.length));
  const canPageLocations = locations.length > locationCardCount;
  const selectedSessionSlug = selected?.latest_session?.slug ?? null;
  const navigableLocations = locations.filter(
    (location) => location.latest_session?.access_level === "public",
  );
  const sidePanelLocationIndex = sidePanelSessionSlug
    ? navigableLocations.findIndex((location) => location.latest_session?.slug === sidePanelSessionSlug)
    : -1;

  useGlobalPlayerSuppression(isLocalPlayerVisible);

  useEffect(() => {
    const openSession = (event: Event) => {
      const detail = (event as CustomEvent<{ locationSlug?: string; sessionSlug?: string }>).detail;
      const location = detail?.locationSlug
        ? allLocations.find((candidate) => candidate.slug === detail.locationSlug)
        : allLocations.find((candidate) => candidate.latest_session?.slug === detail?.sessionSlug);
      if (!location) {
        if (detail?.sessionSlug) {
          window.location.assign(`/sessions/${encodeURIComponent(detail.sessionSlug)}`);
        }
        return;
      }
      const mode = listeningModeForLocation(location, currentDawn.generated_at, dawnModeSlugs);
      const modeLocations = filterLocationsByMode(
        allLocations,
        mode,
        currentDawn.generated_at,
        dawnModeSlugs,
      );
      setSelectedMode(mode);
      setSelectedSlug(location.slug);
      const index = Math.max(
        0,
        modeLocations.findIndex((candidate) => candidate.slug === location.slug),
      );
      setCarouselStart(Math.min(index, Math.max(0, modeLocations.length - locationCardCount)));
      const sessionSlug = detail?.sessionSlug ?? location.latest_session?.slug;
      if (!sessionSlug) return;
      setGlobeFocusRequest((current) => current + 1);
      setSidePanelSessionSlug(sessionSlug);
      setIsSidePanelOpen(true);
    };
    window.addEventListener("orna:open-session", openSession);
    return () => window.removeEventListener("orna:open-session", openSession);
  }, [allLocations, currentDawn.generated_at, dawnModeSlugs, locationCardCount]);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent("orna:analytics", {
      detail: { name: "globe_view", placement: "globe" },
    }));
  }, []);

  useEffect(() => {
    const openSearch = (event: Event) => {
      const detail = (event as CustomEvent<{ query?: string }>).detail;
      const nextQuery = detail?.query?.trim() ?? "";
      setQuery(nextQuery);
      window.setTimeout(() => {
        const input = document.querySelector<HTMLInputElement>("#atlas-search");
        input?.scrollIntoView({ behavior: "smooth", block: "center" });
        input?.focus();
      }, 0);
    };
    window.addEventListener("orna:open-search", openSearch);
    return () => window.removeEventListener("orna:open-search", openSearch);
  }, []);

  function dismissSoftPaywall() {
    window.dispatchEvent(new CustomEvent("orna:analytics", {
      detail: { name: "paywall_dismissed", placement: "soft_paywall" },
    }));
    setIsSoftPaywallOpen(false);
  }

  useEffect(() => {
    if (!isSoftPaywallOpen) return;
    const dialog = softPaywallRef.current;
    const backdrop = dialog?.parentElement;
    const backgroundElements = Array.from(backdrop?.parentElement?.children ?? [])
      .filter((element): element is HTMLElement => element instanceof HTMLElement && element !== backdrop);
    const previousOverflow = document.body.style.overflow;
    const previousBackgroundState = backgroundElements.map((element) => ({
      element,
      inert: element.inert,
      ariaHidden: element.getAttribute("aria-hidden"),
    }));
    document.body.style.overflow = "hidden";
    for (const element of backgroundElements) {
      element.inert = true;
      element.setAttribute("aria-hidden", "true");
    }
    const focusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>(
      "a[href], button:not([disabled]), [tabindex]:not([tabindex='-1'])",
    ) ?? []);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        dismissSoftPaywall();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      for (const { element, inert, ariaHidden } of previousBackgroundState) {
        element.inert = inert;
        if (ariaHidden === null) element.removeAttribute("aria-hidden");
        else element.setAttribute("aria-hidden", ariaHidden);
      }
      paywallTriggerRef.current?.focus();
    };
  }, [isSoftPaywallOpen]);

  useEffect(() => {
    if (selectedSlug && allLocations.some((point) => point.slug === selectedSlug)) {
      return;
    }
    setSelectedSlug(locations[0]?.slug ?? allLocations[0]?.slug ?? null);
  }, [allLocations, locations, selectedSlug]);

  useEffect(() => {
    if (locations.length === 0) {
      setCarouselStart(0);
      return;
    }
    setCarouselStart((current) => Math.min(current, maxCarouselStart));
  }, [locations.length, maxCarouselStart]);

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
          setAtlasPoints((currentPoints) => includeDawnLocations(currentPoints, nextDawn));
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
      if (previewIntentSlugRef.current === sidePanelSessionSlug) {
        previewIntentSlugRef.current = null;
        void play(currentSidePanelSessionRef.current);
      }
      return;
    }
    if (sidePanelSession?.slug === sidePanelSessionSlug) {
      setCurrentSidePanelSession(sidePanelSession);
      setSidePanelState("ready");
      setSidePanelError(null);
      if (previewIntentSlugRef.current === sidePanelSessionSlug) {
        previewIntentSlugRef.current = null;
        void play(sidePanelSession);
      }
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
        if (previewIntentSlugRef.current === sidePanelSessionSlug) {
          previewIntentSlugRef.current = null;
          void play(session);
        }
      })
      .catch((error) => {
        if (!isCurrent) return;
        const status = error instanceof ApiError ? error.status : null;
        const lockedLocation = allLocations.find(
          (location) => location.latest_session?.slug === sidePanelSessionSlug,
        );
        if ((status === 403 || status === 404) && isLockedPoint(lockedLocation)) {
          paywallTriggerRef.current = document.activeElement instanceof HTMLElement
            ? document.activeElement
            : null;
          setIsSidePanelOpen(false);
          setIsSoftPaywallOpen(true);
          for (const name of ["locked_point_hit", "paywall_shown"]) {
            window.dispatchEvent(new CustomEvent("orna:analytics", {
              detail: { name, placement: "soft_paywall" },
            }));
          }
          return;
        }
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
  }, [allLocations, isSidePanelOpen, play, sidePanelSession, sidePanelSessionSlug]);

  function revealLocationInCarousel(slug: string) {
    if (locations.length <= locationCardCount) {
      return;
    }
    const index = locations.findIndex((location) => location.slug === slug);
    if (index !== -1) {
      setCarouselStart(Math.min(index, maxCarouselStart));
    }
  }

  function selectLocation(point: AtlasPoint, options: { revealInCarousel?: boolean } = {}) {
    window.dispatchEvent(new CustomEvent("orna:analytics", {
      detail: {
        name: options.revealInCarousel ? "marker_click" : "card_open",
        placement: options.revealInCarousel ? "globe_marker" : "location_card",
      },
    }));
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
      setSidePanelSessionSlug(result.session_slug);
      setIsSidePanelOpen(true);
      setQuery("");
      setSearchResults([]);
      return;
    }
    const existingLocation = allLocations.find((location) => location.slug === result.slug);
    const resultLocation = existingLocation ?? result.atlas_point;
    if (!resultLocation) {
      return;
    }
    const resultMode = listeningModeForLocation(resultLocation, currentDawn.generated_at, dawnModeSlugs);
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
        dawnModeSlugs,
      );
      const resultIndex = modeLocations.findIndex((location) => location.slug === result.slug);
      const resultMaxStart = Math.max(0, modeLocations.length - locationCardCount);
      setCarouselStart(resultIndex === -1 ? 0 : Math.min(resultIndex, resultMaxStart));
    }
    setSelectedSlug(result.slug);
    setQuery("");
  }

  function pageLocations(delta: number) {
    if (!canPageLocations) {
      return;
    }
    window.dispatchEvent(new CustomEvent("orna:analytics", {
      detail: { name: "carousel_scroll", placement: "location_carousel" },
    }));
    setCarouselStart((current) => Math.min(Math.max(current + delta, 0), maxCarouselStart));
  }

  function selectMode(mode: ListeningMode) {
    window.dispatchEvent(new CustomEvent("orna:analytics", {
      detail: { name: `time_filter_${mode.toLowerCase()}`, placement: "time_filter" },
    }));
    const nextLocations = filterLocationsByMode(
      allLocations,
      mode,
      currentDawn.generated_at,
      dawnModeSlugs,
    );
    setSelectedMode(mode);
    setSelectedSlug(nextLocations[0]?.slug ?? null);
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
        const mode = listeningModeForLocation(nearest, currentDawn.generated_at, dawnModeSlugs);
        const modeLocations = filterLocationsByMode(
          allLocations,
          mode,
          currentDawn.generated_at,
          dawnModeSlugs,
        );
        setSelectedMode(mode);
        const nearestIndex = Math.max(
          0,
          modeLocations.findIndex((location) => location.slug === nearest.slug),
        );
        const visibleCardCount = window.matchMedia("(max-width: 720px)").matches
          ? mobileLocationCardCount
          : desktopLocationCardCount;
        setCarouselStart(Math.min(
          nearestIndex,
          Math.max(0, modeLocations.length - visibleCardCount),
        ));
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

  function openLocationSession(location: AtlasPoint) {
    const sessionSlug = location.latest_session?.slug;
    if (!sessionSlug) return;
    setGlobeFocusRequest((current) => current + 1);
    setSidePanelSessionSlug(sessionSlug);
    setIsSidePanelOpen(true);
  }

  function openSelectedSession() {
    if (!selectedSessionSlug) {
      return;
    }
    setGlobeFocusRequest((current) => current + 1);
    previewIntentSlugRef.current = selectedSessionSlug;
    setSidePanelSessionSlug(selectedSessionSlug);
    setIsSidePanelOpen(true);
  }

  function openAdjacentSession(offset: -1 | 1) {
    if (sidePanelLocationIndex === -1) return;
    const nextLocation = navigableLocations[sidePanelLocationIndex + offset];
    if (!nextLocation?.latest_session) return;
    setSelectedMode(listeningModeForLocation(nextLocation, currentDawn.generated_at, dawnModeSlugs));
    setSelectedSlug(nextLocation.slug);
    setSidePanelSessionSlug(nextLocation.latest_session.slug);
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
              onSelectPoint={(point) => {
                selectLocation(point, { revealInCarousel: true });
                openLocationSession(point);
              }}
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
                      onClick={() => {
                        selectLocation(location);
                        openLocationSession(location);
                      }}
                    >
                      <strong>{isLockedPoint(location) ? `🔒 ${location.name}` : location.name}</strong>
                      <span>{[location.region, location.country_code].filter(Boolean).join(" · ")}</span>
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          )}
          {showInternalNavigation ? (
            <Link className="atlas-brand" href="/" aria-label="ORNA Atlas">
              <span>ORNA</span>
              <span>Atlas</span>
            </Link>
          ) : null}
          {selectedDawn?.state === "active" ? <DawnNowBadge className="atlas-live-left" /> : null}
          <div className="dawn-copy">
            <span>{listeningModeKicker[selectedMode]}</span>
            <strong>{selected?.name ?? "No location selected"}</strong>
            <small>{selected?.region ?? selected?.country_code ?? "Published atlas site"}</small>
            {selected ? (
              <small className="dawn-coordinates">
                {selected.latitude.toFixed(3)}°, {selected.longitude.toFixed(3)}°
              </small>
            ) : null}
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
                {isLockedPoint(selected) ? "Unlock full session" : "Listen"}
                <span aria-hidden="true">›</span>
              </button>
            ) : (
              <button className="listen-pill" type="button" disabled>
                Listen
                <span aria-hidden="true">›</span>
              </button>
            )}
            {isLockedPoint(selected) ? <span className="atlas-members-label">Members only</span> : null}
          </div>
          {showInternalNavigation ? (
            <Link className="about-link" href="/about">
              About
            </Link>
          ) : null}
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
              disabled={!canPageLocations || carouselStart === 0}
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
                  onClick={() => {
                    selectLocation(location);
                    openLocationSession(location);
                  }}
                >
                  <span>{isLockedPoint(location) ? `🔒 ${location.name}` : location.name}</span>
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
              disabled={!canPageLocations || carouselStart === maxCarouselStart}
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
              onFocus={() => window.dispatchEvent(new CustomEvent("orna:analytics", {
                detail: { name: "search_opened", placement: "location_search" },
              }))}
              onChange={(event) => {
                const value = event.target.value;
                setQuery(value);
                if (value.trim().length === 2) {
                  window.dispatchEvent(new CustomEvent("orna:analytics", {
                    detail: { name: "location_search", placement: "location_search" },
                  }));
                }
              }}
            />
            {query.trim().length >= 2 ? (
              <div className="search-results" aria-live="polite">
                {isSearching ? <p>Searching...</p> : null}
                {searchError ? <p role="alert">{searchError}</p> : null}
                {!isSearching && !searchError && searchResults.length === 0 ? <p>No public results found.</p> : null}
                {searchResults.map((result) => (
                  <button
                    type="button"
                    key={`${result.type}-${result.id}`}
                    onClick={() => selectSearchResult(result)}
                  >
                    <strong>{result.title}</strong>
                    <span>{[result.subtitle, result.habitat].filter(Boolean).join(" / ")}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {isSidePanelOpen ? (
        <aside className="atlas-side-panel" id="atlas-session-player">
          {currentSidePanelSession ? (
            <SessionPlayer
              session={currentSidePanelSession}
              onClose={() => setIsSidePanelOpen(false)}
              onPrevious={sidePanelLocationIndex > 0 ? () => openAdjacentSession(-1) : undefined}
              onNext={
                sidePanelLocationIndex >= 0 && sidePanelLocationIndex < navigableLocations.length - 1
                  ? () => openAdjacentSession(1)
                  : undefined
              }
            />
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
      {isSoftPaywallOpen && selected?.latest_session ? (
        <div className="soft-paywall-backdrop" role="presentation" onMouseDown={dismissSoftPaywall}>
          <section
            ref={softPaywallRef}
            className="soft-paywall"
            role="dialog"
            aria-modal="true"
            aria-labelledby="soft-paywall-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <button
              className="soft-paywall-close"
              type="button"
              aria-label="Close"
              autoFocus
              onClick={dismissSoftPaywall}
            >
              ×
            </button>
            <span>Members-only field recording</span>
            <h2 id="soft-paywall-title">Members-only soundscape</h2>
            <p>
              Membership is planned to include complete long-form sessions and the full members catalog.
              Enrollment is not open yet, and a free ORNA account does not unlock this recording;
              public recordings remain free to explore.
            </p>
            <div className="soft-paywall-actions">
              <Link
                className="button-link"
                href={`/membership?mode=register&returnTo=${encodeURIComponent(`/sessions/${selected.latest_session.slug}`)}`}
                onClick={() => {
                  for (const name of ["paywall_signup_click", "signup_started"]) {
                    window.dispatchEvent(new CustomEvent("orna:analytics", {
                      detail: { name, placement: "soft_paywall" },
                    }));
                  }
                }}
              >
                Create a free account
              </Link>
              <Link
                href="/membership"
                onClick={() => window.dispatchEvent(new CustomEvent("orna:analytics", {
                  detail: { name: "paywall_learn_more", placement: "soft_paywall" },
                }))}
              >
                Learn about membership
              </Link>
            </div>
          </section>
        </div>
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
