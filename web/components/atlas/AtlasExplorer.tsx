"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
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

type GlobeProps = {
  points: Array<AtlasPoint | AtlasCluster>;
  selectedSlug: string | null;
  activeDawnSlugs: Set<string>;
  dawnLongitude: number;
  onSelectPoint: (point: AtlasPoint) => void;
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

function dawnLongitudeFromDate(value: string) {
  const generatedAt = new Date(value);
  const utcHours =
    generatedAt.getUTCHours() + generatedAt.getUTCMinutes() / 60 + generatedAt.getUTCSeconds() / 3600;
  const sunriseLongitude = 90 - utcHours * 15;
  return ((((sunriseLongitude + 180) % 360) + 360) % 360) - 180;
}

function latLonToVector3(latitude: number, longitude: number, radius: number) {
  const phi = THREE.MathUtils.degToRad(90 - latitude);
  const theta = THREE.MathUtils.degToRad(longitude + 180);
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  );
}

function makeEarthTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 2048;
  canvas.height = 1024;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const ocean = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
  ocean.addColorStop(0, "#176979");
  ocean.addColorStop(0.45, "#0f4c5a");
  ocean.addColorStop(1, "#0a2634");
  ctx.fillStyle = ocean;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const drawPolygon = (points: Array<[number, number]>, color: string) => {
    ctx.beginPath();
    points.forEach(([lon, lat], index) => {
      const x = ((lon + 180) / 360) * canvas.width;
      const y = ((90 - lat) / 180) * canvas.height;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = "rgba(237,247,242,0.24)";
    ctx.lineWidth = 3;
    ctx.stroke();
  };

  const land = "#69a878";
  const highland = "#c0bd73";
  [
    [
      [-168, 70],
      [-138, 72],
      [-105, 58],
      [-82, 48],
      [-66, 28],
      [-82, 12],
      [-108, 20],
      [-126, 34],
      [-150, 48],
    ],
    [
      [-82, 12],
      [-66, 10],
      [-50, -8],
      [-56, -28],
      [-66, -54],
      [-78, -38],
      [-84, -10],
    ],
    [
      [-18, 35],
      [26, 38],
      [48, 20],
      [44, -34],
      [18, -36],
      [-6, -12],
      [-18, 10],
    ],
    [
      [-10, 72],
      [48, 70],
      [102, 60],
      [150, 50],
      [166, 18],
      [128, 4],
      [100, 22],
      [62, 8],
      [38, 30],
      [12, 44],
      [-10, 38],
    ],
    [
      [112, -12],
      [154, -18],
      [148, -42],
      [116, -38],
      [108, -24],
    ],
    [
      [-52, 82],
      [-24, 78],
      [-32, 62],
      [-56, 60],
      [-72, 72],
    ],
  ].forEach((shape) => drawPolygon(shape as Array<[number, number]>, land));

  [
    [
      [-130, 52],
      [-102, 46],
      [-92, 30],
      [-116, 30],
    ],
    [
      [70, 44],
      [104, 36],
      [95, 20],
      [60, 26],
    ],
    [
      [12, 4],
      [34, -6],
      [28, -24],
      [4, -16],
    ],
  ].forEach((shape) => drawPolygon(shape as Array<[number, number]>, highland));

  ctx.strokeStyle = "rgba(237,247,242,0.14)";
  ctx.lineWidth = 1;
  for (let lon = -180; lon <= 180; lon += 30) {
    const x = ((lon + 180) / 360) * canvas.width;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, canvas.height);
    ctx.stroke();
  }
  for (let lat = -60; lat <= 60; lat += 30) {
    const y = ((90 - lat) / 180) * canvas.height;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(canvas.width, y);
    ctx.stroke();
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

function addGraticule(group: THREE.Group, radius: number) {
  const material = new THREE.LineBasicMaterial({ color: 0x9bd8bd, transparent: true, opacity: 0.2 });

  for (let lat = -60; lat <= 60; lat += 30) {
    const points = [];
    for (let lon = -180; lon <= 180; lon += 3) {
      points.push(latLonToVector3(lat, lon, radius));
    }
    group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), material));
  }

  for (let lon = -150; lon <= 180; lon += 30) {
    const points = [];
    for (let lat = -85; lat <= 85; lat += 3) {
      points.push(latLonToVector3(lat, lon, radius));
    }
    group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), material));
  }
}

function makeDawnLine(longitude: number, radius: number) {
  const points = [];
  for (let lat = -88; lat <= 88; lat += 2) {
    points.push(latLonToVector3(lat, longitude, radius));
  }
  const material = new THREE.LineBasicMaterial({ color: 0xf6c46b, transparent: true, opacity: 0.85 });
  return new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), material);
}

function GlobeCanvas({ points, selectedSlug, activeDawnSlugs, dawnLongitude, onSelectPoint }: GlobeProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const onSelectRef = useRef(onSelectPoint);
  const [webglUnavailable, setWebglUnavailable] = useState(false);

  useEffect(() => {
    onSelectRef.current = onSelectPoint;
  }, [onSelectPoint]);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 0, 8.6);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setWebglUnavailable(true);
      return;
    }
    setWebglUnavailable(false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    mount.appendChild(renderer.domElement);

    const globe = new THREE.Group();
    globe.rotation.x = THREE.MathUtils.degToRad(-12);
    globe.rotation.y = THREE.MathUtils.degToRad(-28);
    scene.add(globe);

    scene.add(new THREE.AmbientLight(0x8fb8ad, 1.15));
    const sun = new THREE.DirectionalLight(0xfff0c2, 2.2);
    sun.position.set(-3, 1.4, 4);
    scene.add(sun);

    const stars = new THREE.Points(
      new THREE.BufferGeometry().setFromPoints(
        Array.from({ length: 140 }, (_, index) => {
          const angle = index * 2.399963;
          const radius = 3.4 + ((index * 37) % 100) / 100;
          return new THREE.Vector3(Math.cos(angle) * radius, ((index % 29) - 14) * 0.11, -1.6 - Math.sin(angle) * 0.45);
        }),
      ),
      new THREE.PointsMaterial({ color: 0x9bd8bd, transparent: true, opacity: 0.32, size: 0.012 }),
    );
    scene.add(stars);

    const earthTexture = makeEarthTexture();
    const earth = new THREE.Mesh(
      new THREE.SphereGeometry(2.08, 96, 96),
      new THREE.MeshStandardMaterial({
        color: 0xffffff,
        emissive: 0x143f38,
        emissiveIntensity: 0.32,
        map: earthTexture ?? undefined,
        metalness: 0,
        roughness: 0.64,
      }),
    );
    globe.add(earth);

    const shade = new THREE.Mesh(
      new THREE.SphereGeometry(2.086, 96, 96),
      new THREE.MeshBasicMaterial({ color: 0x020605, transparent: true, opacity: 0.1, side: THREE.BackSide }),
    );
    globe.add(shade);

    const atmosphere = new THREE.Mesh(
      new THREE.SphereGeometry(2.18, 96, 96),
      new THREE.MeshBasicMaterial({ color: 0x9bd8bd, transparent: true, opacity: 0.14, side: THREE.BackSide }),
    );
    globe.add(atmosphere);

    addGraticule(globe, 2.092);

    const markerGroup = new THREE.Group();
    globe.add(markerGroup);
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let dawnLine: THREE.Line | null = null;
    let dragStart: { x: number; y: number; rotationX: number; rotationY: number } | null = null;
    let moved = false;
    let animationId = 0;

    const rebuildMarkers = () => {
      markerGroup.clear();
      points.forEach((item) => {
        const pointSize = isPoint(item) ? Math.min(0.055 + item.session_count * 0.01, 0.105) : 0.075;
        const color =
          isPoint(item) && item.slug === selectedSlug
            ? 0xfff4c2
            : isPoint(item) && activeDawnSlugs.has(item.slug)
              ? 0xf6c46b
              : item.type === "cluster"
                ? 0xf6c46b
                : 0x9bd8bd;
        const marker = new THREE.Mesh(
          new THREE.SphereGeometry(pointSize, 18, 18),
          new THREE.MeshStandardMaterial({
            color,
            emissive: color,
            emissiveIntensity: isPoint(item) && item.slug === selectedSlug ? 0.8 : 0.38,
            roughness: 0.35,
          }),
        );
        marker.position.copy(latLonToVector3(item.latitude, item.longitude, 2.18));
        marker.userData = { point: isPoint(item) ? item : null };
        markerGroup.add(marker);
      });
    };

    const rebuildDawn = () => {
      if (dawnLine) {
        globe.remove(dawnLine);
        dawnLine.geometry.dispose();
      }
      dawnLine = makeDawnLine(dawnLongitude, 2.12);
      globe.add(dawnLine);
    };

    const resize = () => {
      const rect = mount.getBoundingClientRect();
      const width = Math.max(rect.width, 1);
      const height = Math.max(rect.height, 1);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(mount);
    resize();
    rebuildMarkers();
    rebuildDawn();

    const animate = () => {
      if (!dragStart) {
        globe.rotation.y += 0.0012;
      }
      renderer.render(scene, camera);
      animationId = window.requestAnimationFrame(animate);
    };
    animate();

    const setPointer = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    };

    const handlePointerDown = (event: PointerEvent) => {
      renderer.domElement.setPointerCapture(event.pointerId);
      dragStart = {
        x: event.clientX,
        y: event.clientY,
        rotationX: globe.rotation.x,
        rotationY: globe.rotation.y,
      };
      moved = false;
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (!dragStart) return;
      const deltaX = event.clientX - dragStart.x;
      const deltaY = event.clientY - dragStart.y;
      if (Math.abs(deltaX) + Math.abs(deltaY) > 4) moved = true;
      globe.rotation.y = dragStart.rotationY + deltaX * 0.006;
      globe.rotation.x = THREE.MathUtils.clamp(
        dragStart.rotationX + deltaY * 0.004,
        THREE.MathUtils.degToRad(-62),
        THREE.MathUtils.degToRad(62),
      );
    };

    const handlePointerUp = (event: PointerEvent) => {
      renderer.domElement.releasePointerCapture(event.pointerId);
      if (!moved) {
        setPointer(event);
        raycaster.setFromCamera(pointer, camera);
        const hit = raycaster.intersectObjects(markerGroup.children, false)[0];
        const point = hit?.object.userData.point as AtlasPoint | null | undefined;
        if (point) onSelectRef.current(point);
      }
      dragStart = null;
    };

    renderer.domElement.addEventListener("pointerdown", handlePointerDown);
    renderer.domElement.addEventListener("pointermove", handlePointerMove);
    renderer.domElement.addEventListener("pointerup", handlePointerUp);

    return () => {
      window.cancelAnimationFrame(animationId);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointerdown", handlePointerDown);
      renderer.domElement.removeEventListener("pointermove", handlePointerMove);
      renderer.domElement.removeEventListener("pointerup", handlePointerUp);
      renderer.dispose();
      earth.geometry.dispose();
      earthTexture?.dispose();
      mount.removeChild(renderer.domElement);
    };
  }, [points, selectedSlug, activeDawnSlugs, dawnLongitude]);

  return (
    <div className="globe-stage" ref={mountRef} aria-label="Interactive 3D globe">
      {webglUnavailable ? <StaticGlobeFallback points={points} selectedSlug={selectedSlug} /> : null}
      <div className="globe-hint">Drag to rotate / click a marker</div>
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

const habitatOptions = ["forest", "wetland", "steppe", "coast"];

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
          <GlobeCanvas
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
