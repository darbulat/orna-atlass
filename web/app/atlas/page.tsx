import { AtlasExplorer } from "../../components/atlas/AtlasExplorer";
import { fetchAtlasPoints, fetchCurrentDawn } from "../../lib/api/sessions";

export default async function Page({ searchParams }: { searchParams?: { view?: string } }) {
  const view = searchParams?.view === "list" ? "list" : searchParams?.view === "map" ? "map" : "globe";
  const atlas = await fetchAtlasPoints(view);
  const dawnLimit = Math.max(250, atlas.points.length);
  const dawn = await fetchCurrentDawn(dawnLimit);

  return (
    <main id="main-content" className="shell atlas-shell">
      <AtlasExplorer initialView={view} points={atlas.points} dawn={dawn} sidePanelSession={null} />
    </main>
  );
}
