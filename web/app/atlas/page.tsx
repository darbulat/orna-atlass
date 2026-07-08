import { AtlasExplorer } from "../../components/atlas/AtlasExplorer";
import { fetchAtlasPoints, fetchCurrentDawn, fetchSessionDetail } from "../../lib/api/sessions";

const defaultSidePanelSessionSlug = "berezinsky-sample";

export default async function Page({ searchParams }: { searchParams?: { view?: string } }) {
  const view = searchParams?.view === "list" ? "list" : searchParams?.view === "map" ? "map" : "globe";
  const [atlas, dawn, sidePanelSession] = await Promise.all([
    fetchAtlasPoints(view),
    fetchCurrentDawn(),
    fetchSessionDetail(defaultSidePanelSessionSlug),
  ]);

  return (
    <main id="main-content" className="shell atlas-shell">
      <AtlasExplorer initialView={view} points={atlas.points} dawn={dawn} sidePanelSession={sidePanelSession} />
    </main>
  );
}
