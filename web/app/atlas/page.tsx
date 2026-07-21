import { AtlasExplorer } from "../../components/atlas/AtlasExplorer";
import { apiErrorMessage } from "../../lib/api/client";
import { fetchAtlasPoints, fetchCurrentDawn, includeDawnLocations } from "../../lib/api/sessions";

export default async function Page({ searchParams }: { searchParams?: Promise<{ view?: string }> }) {
  const resolvedSearchParams = await searchParams;
  const view = resolvedSearchParams?.view === "list"
    ? "list"
    : resolvedSearchParams?.view === "map"
      ? "map"
      : "globe";
  try {
    const atlas = await fetchAtlasPoints(view);
    const dawnLimit = Math.max(250, atlas.points.length);
    const dawn = await fetchCurrentDawn(dawnLimit);

    return (
      <main id="main-content" className="shell atlas-shell">
        <AtlasExplorer
          initialView={view}
          points={includeDawnLocations(atlas.points, dawn)}
          dawn={dawn}
          initialSelectedSlug={
            dawn.active_locations[0]?.location.slug
              ?? dawn.next_locations[0]?.location.slug
              ?? null
          }
          sidePanelSession={null}
        />
      </main>
    );
  } catch (error) {
    return (
      <main id="main-content" className="shell atlas-shell">
        <section className="panel unavailable-panel" role="alert">
          <p className="eyebrow">Atlas unavailable</p>
          <h1>We could not load the listening map.</h1>
          <p>{apiErrorMessage(error, "The atlas is temporarily unavailable.")}</p>
        </section>
      </main>
    );
  }
}
