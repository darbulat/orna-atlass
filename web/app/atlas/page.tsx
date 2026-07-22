import { AtlasExplorer } from "../../components/atlas/AtlasExplorer";
import { SiteHeader } from "../../components/site-header";
import { apiErrorMessage } from "../../lib/api/client";
import { fetchAtlasPoints, fetchCurrentDawn, includeDawnLocations } from "../../lib/api/sessions";

export default async function Page({ searchParams }: { searchParams?: Promise<{ view?: string; location?: string }> }) {
  const resolvedSearchParams = await searchParams;
  const view = resolvedSearchParams?.view === "list"
    ? "list"
    : resolvedSearchParams?.view === "map"
      ? "map"
      : "globe";
  try {
    const requestedLocation = resolvedSearchParams?.location;
    const requestOptions = requestedLocation ? { cache: "no-store" as const } : {};
    const atlas = await fetchAtlasPoints(view, [], requestOptions);
    const dawnLimit = Math.max(250, atlas.points.length);
    const dawn = await fetchCurrentDawn(dawnLimit, requestOptions);
    const points = includeDawnLocations(atlas.points, dawn);
    const requestedLocationExists = requestedLocation
      ? points.some((item) => item.type === "point" && item.slug === requestedLocation)
      : false;

    return (
      <main id="main-content" className="shell atlas-shell">
        <SiteHeader active="map" />
        <AtlasExplorer
          initialView={view}
          points={points}
          dawn={dawn}
          initialSelectedSlug={
            (requestedLocationExists ? requestedLocation : null)
              ?? dawn.active_locations[0]?.location.slug
              ?? dawn.next_locations[0]?.location.slug
              ?? null
          }
          sidePanelSession={null}
          showInternalNavigation={false}
        />
      </main>
    );
  } catch (error) {
    return (
      <main id="main-content" className="shell atlas-shell">
        <SiteHeader active="map" />
        <section className="panel unavailable-panel" role="alert">
          <p className="eyebrow">Atlas unavailable</p>
          <h1>We could not load the listening map.</h1>
          <p>{apiErrorMessage(error, "The atlas is temporarily unavailable.")}</p>
        </section>
      </main>
    );
  }
}
