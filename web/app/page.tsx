import Link from "next/link";

import { AnalyticsLink } from "../components/analytics-link";
import { AtlasExplorer } from "../components/atlas/AtlasExplorer";
import { FeaturedSessions } from "../components/featured-sessions";
import { PopularLocations } from "../components/popular-locations";
import { SiteHeader } from "../components/site-header";
import { fetchCollections, type CollectionSummary } from "../lib/api/collections";
import { fetchAtlasPoints, fetchCurrentDawn, fetchFeaturedSessions, includeDawnLocations } from "../lib/api/sessions";

export const dynamic = "force-dynamic";

async function fetchHomeAtlas() {
  const atlas = await fetchAtlasPoints("globe", [], { cache: "no-store" });
  const dawn = await fetchCurrentDawn(Math.max(250, atlas.points.length), { cache: "no-store" });
  return { points: includeDawnLocations(atlas.points, dawn), dawn };
}

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ search?: string | string[] }>;
}) {
  const params = await searchParams;
  const initialSearchQuery = typeof params.search === "string" ? params.search.slice(0, 200) : "";
  const [atlasResult, collectionsResult, featuredResult] = await Promise.allSettled([
    fetchHomeAtlas(),
    fetchCollections(6),
    fetchFeaturedSessions(3),
  ]);
  const collections = collectionsResult.status === "fulfilled" ? collectionsResult.value : null;
  const popularLocations = atlasResult.status === "fulfilled"
    ? atlasResult.value.points
      .filter((item) => item.type === "point")
      .sort((left, right) => (
        (right.session_count - left.session_count)
        || left.name.localeCompare(right.name)
      ))
      .slice(0, 5)
    : [];

  return (
    <div className="shell home-shell">
      <SiteHeader className="home-nav" active="map" />
      <main id="main-content">
        {atlasResult.status === "fulfilled" ? (
          <div className="home-atlas-entry" id="atlas-entry">
            <AtlasExplorer
              initialView="globe"
              points={atlasResult.value.points}
              dawn={atlasResult.value.dawn}
              initialSelectedSlug={
                atlasResult.value.dawn.active_locations[0]?.location.slug
                ?? atlasResult.value.dawn.next_locations[0]?.location.slug
                ?? null
              }
              initialSearchQuery={initialSearchQuery}
              sidePanelSession={null}
              showInternalNavigation={false}
            />
          </div>
        ) : (
          <section className="panel unavailable-panel home-atlas-unavailable" role="alert">
            <p className="eyebrow">Atlas unavailable</p>
            <h1>We could not load the listening globe.</h1>
            <p>The atlas is temporarily unavailable. Please try again soon.</p>
          </section>
        )}

        <section className="editorial-section" aria-labelledby="popular-locations-heading">
          <div className="section-heading">
            <p className="eyebrow">Explore by place</p>
            <h2 id="popular-locations-heading">Popular locations</h2>
            <p>Preview a public recording here, or open the location in the atlas.</p>
          </div>
          {popularLocations.length > 0
            ? <PopularLocations locations={popularLocations} />
            : <p className="empty-state">Locations are temporarily unavailable.</p>}
        </section>

        <section className="editorial-section" aria-labelledby="featured-sessions-heading">
          <div className="section-heading">
            <p className="eyebrow">Field recordings</p>
            <h2 id="featured-sessions-heading">Featured sessions</h2>
          </div>
          {featuredResult.status === "fulfilled" && featuredResult.value.length > 0
            ? <FeaturedSessions sessions={featuredResult.value} />
            : <p className="empty-state">Featured sessions are temporarily unavailable.</p>}
        </section>

        <section className="editorial-section" id="collections" aria-labelledby="collections-heading">
          <div className="section-heading">
            <p className="eyebrow">Curated listening</p>
            <h2 id="collections-heading">Featured collections</h2>
            <AnalyticsLink destination="/collections" eventName="see_all_click" placement="collections">See all collections →</AnalyticsLink>
          </div>
          {collections === null ? (
            <p className="unavailable-state" role="alert">Collections are temporarily unavailable. Please try again soon.</p>
          ) : collections.length > 0 ? (
            <div className="panel featured-grid">
              {collections.map((collection: CollectionSummary) => (
                <article key={collection.id}>
                  <span>{collection.session_count} sessions</span>
                  <h3><Link href={`/collections/${collection.slug}`}>{collection.title}</Link></h3>
                  <p>{collection.description}</p>
                </article>
              ))}
            </div>
          ) : <p className="empty-state">Collections are being curated for the public atlas.</p>}
        </section>
      </main>
    </div>
  );
}
