import Link from "next/link";

import { ApiError, apiErrorMessage } from "../../../lib/api/client";
import { fetchCollectionDetail, type CollectionDetail } from "../../../lib/api/collections";

export const dynamic = "force-dynamic";

export default async function CollectionPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let collection: CollectionDetail;
  try {
    collection = await fetchCollectionDetail(slug);
  } catch (error) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <main className="shell" id="main-content">
        <section className="panel unavailable-panel" role={notFound ? "status" : "alert"}>
          <p className="eyebrow">Collection</p>
          <h1>{notFound ? "Collection not found" : "Collection unavailable"}</h1>
          <p>
            {notFound
              ? "This collection does not exist or is no longer published."
              : apiErrorMessage(error, "This collection could not be loaded.")}
          </p>
          <small>{formatSlug(slug)}</small>
        </section>
      </main>
    );
  }

  return (
    <main className="shell collection-shell" id="main-content">
      <section className="session-hero">
        <p className="eyebrow">Collection</p>
        <h1>{collection.title}</h1>
        <p>{collection.description}</p>
        <p className="timeline-meta">
          {collection.location_count} locations · {collection.session_count} sessions
        </p>
      </section>

      {collection.sessions.length > 0 ? (
        <section className="editorial-section" aria-labelledby="collection-sessions-heading">
          <div className="section-heading">
            <h2 id="collection-sessions-heading">Sessions</h2>
          </div>
          <div className="panel featured-grid">
            {collection.sessions.map((session: CollectionDetail["sessions"][number]) => (
              <article key={session.id}>
                <span>{session.is_featured ? "Featured" : "Session"}</span>
                <h3>
                  <Link href={`/sessions/${session.slug}`}>{session.title}</Link>
                </h3>
                <p>{formatDuration(session.duration_seconds)}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {collection.locations.length > 0 ? (
        <section className="editorial-section" aria-labelledby="collection-locations-heading">
          <div className="section-heading">
            <h2 id="collection-locations-heading">Locations</h2>
          </div>
          <div className="panel featured-grid">
            {collection.locations.map((location: CollectionDetail["locations"][number]) => (
              <article key={location.id}>
                <span>{location.habitat ?? "Location"}</span>
                <h3>{location.name}</h3>
                <p>
                  {location.coordinates_protected
                    ? "Approximate public coordinates"
                    : location.latitude != null
                      ? `${location.latitude.toFixed(2)}, ${location.longitude?.toFixed(2)}`
                      : "Coordinates withheld"}
                </p>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </main>
  );
}

function formatSlug(slug: string) {
  return slug.replaceAll("-", " ");
}

function formatDuration(seconds: number | null | undefined) {
  if (!seconds) {
    return "Duration unknown";
  }
  const minutes = Math.floor(seconds / 60);
  return `${minutes} min`;
}
