import Link from "next/link";

import { fetchCollections, type CollectionDetail, type CollectionSummary } from "../lib/api/collections";
import { fetchFeaturedSessions, type FeaturedSession } from "../lib/api/sessions";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [featuredSessions, collections] = await Promise.all([
    fetchFeaturedSessions(6),
    fetchCollections(6),
  ]);

  return (
    <main className="shell" id="main-content">
      <section className="hero">
        <p className="eyebrow">ORNA Atlas</p>
        <h1>Explore long-form nature recordings through a living map.</h1>
        <p>
          A production foundation for place-first audio: coordinates, habitat context, local
          time, sunrise discovery, and immersive sessions anchored to real landscapes.
        </p>
        <div className="actions">
          <a href="/atlas">Open atlas</a>
          <a href="/about">Read the mission</a>
        </div>
      </section>

      <section className="editorial-section" aria-labelledby="featured-heading">
        <div className="section-heading">
          <p className="eyebrow">Editorial</p>
          <h2 id="featured-heading">Featured sessions</h2>
        </div>
        {featuredSessions.length > 0 ? (
          <div className="panel featured-grid">
            {featuredSessions.map((session: FeaturedSession) => (
              <article key={session.id}>
                <span>{session.location.habitat ?? "Field recording"}</span>
                <h3>
                  <Link href={`/sessions/${session.slug}`}>{session.title}</Link>
                </h3>
                <p>{session.location.name}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className="empty-state">Featured sessions will appear once editorial curation is published.</p>
        )}
      </section>

      <section className="editorial-section" aria-labelledby="collections-heading">
        <div className="section-heading">
          <p className="eyebrow">Collections</p>
          <h2 id="collections-heading">Atlas journeys</h2>
        </div>
        {collections.length > 0 ? (
          <div className="panel featured-grid">
            {collections.map((collection: CollectionSummary) => (
              <article key={collection.id}>
                <span>{collection.session_count} sessions</span>
                <h3>
                  <Link href={`/collections/${collection.slug}`}>{collection.title}</Link>
                </h3>
                <p>{collection.description}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className="empty-state">Collections are being curated for the public atlas.</p>
        )}
      </section>
    </main>
  );
}
