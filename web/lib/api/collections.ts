import { apiUrl } from "./sessions";
import type { components } from "./generated";
import { fetchJson } from "./client";

export type CollectionSummary = components["schemas"]["CollectionSummaryRead"];
type GeneratedCollectionDetail = components["schemas"]["CollectionDetailRead"];
export type CollectionDetail = Omit<GeneratedCollectionDetail, "locations" | "sessions"> & {
  locations: NonNullable<GeneratedCollectionDetail["locations"]>;
  sessions: NonNullable<GeneratedCollectionDetail["sessions"]>;
};

export function fetchCollections(limit = 24): Promise<CollectionSummary[]> {
  return fetchJson<CollectionSummary[]>(apiUrl(`/api/v1/collections?limit=${limit}`), {
    next: { revalidate: 120 },
    headers: { Accept: "application/json" },
  });
}

export function fetchCollectionDetail(slug: string): Promise<CollectionDetail> {
  return fetchJson<CollectionDetail>(apiUrl(`/api/v1/collections/${slug}`), {
    next: { revalidate: 120 },
    headers: { Accept: "application/json" },
  });
}
