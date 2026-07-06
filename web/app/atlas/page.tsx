import { AtlasExplorer } from "../../components/atlas/AtlasExplorer";
import { fetchAtlasPoints } from "../../lib/api/sessions";

export default async function Page({ searchParams }: { searchParams?: { view?: string } }) {
  const view = searchParams?.view === "list" ? "list" : "map";
  const atlas = await fetchAtlasPoints(view);

  return (
    <main className="shell atlas-shell">
      <section className="atlas-heading">
        <p className="eyebrow">ORNA Atlas</p>
        <h1>Atlas</h1>
        <p>Published field locations, habitats, local context, and long-form recordings.</p>
      </section>
      <AtlasExplorer initialView={view} points={atlas.points} />
    </main>
  );
}
