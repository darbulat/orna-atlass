import Link from "next/link";

import { SiteHeader } from "../../components/site-header";
import { apiErrorMessage } from "../../lib/api/client";
import { fetchCollections, type CollectionSummary } from "../../lib/api/collections";

export const dynamic = "force-dynamic";

export default async function CollectionsPage() {
  let collections: CollectionSummary[] = [];
  let error: string | null = null;
  try {
    collections = await fetchCollections(48);
  } catch (cause) {
    error = apiErrorMessage(cause, "Collections could not be loaded.");
  }

  return (
    <>
      <main className="shell collection-shell" id="main-content">
        <SiteHeader active="collections" />
        <section className="session-hero">
          <p className="eyebrow">Curated listening</p>
          <h1>Collections</h1>
          <p>Follow habitats, migrations and field-recording stories across the atlas.</p>
        </section>
        {error ? <p className="atlas-data-warning" role="alert">{error}</p> : null}
        {!error && collections.length === 0 ? <p role="status">No published collections yet.</p> : null}
        <section className="panel featured-grid" aria-label="Published collections">
          {collections.map((collection) => (
            <article key={collection.id}>
              <span>{collection.session_count} sessions</span>
              <h2><Link href={`/collections/${collection.slug}`}>{collection.title}</Link></h2>
              <p>{collection.description}</p>
              <small>{collection.location_count} locations</small>
            </article>
          ))}
        </section>
      </main>
    </>
  );
}
