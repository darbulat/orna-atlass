import { apiUrl, withBrowserAuthRefresh } from "./sessions";
import type { components } from "./generated";
import { fetchJson } from "./client";

export type CollectionSummary = components["schemas"]["CollectionSummaryRead"];
type GeneratedCollectionDetail = components["schemas"]["CollectionDetailRead"];
export type CollectionDetail = Omit<GeneratedCollectionDetail, "locations" | "sessions"> & {
  locations: NonNullable<GeneratedCollectionDetail["locations"]>;
  sessions: NonNullable<GeneratedCollectionDetail["sessions"]>;
};

export function fetchCollections(
  limit = 24,
  headers: HeadersInit = {},
): Promise<CollectionSummary[]> {
  return withBrowserAuthRefresh(() =>
    fetchJson<CollectionSummary[]>(apiUrl(`/api/v1/collections?limit=${limit}`), {
      cache: "no-store",
      credentials: "include",
      headers: { Accept: "application/json", ...headers },
    }),
  );
}

export function fetchCollectionDetail(
  slug: string,
  headers: HeadersInit = {},
): Promise<CollectionDetail> {
  return withBrowserAuthRefresh(() =>
    fetchJson<CollectionDetail>(apiUrl(`/api/v1/collections/${slug}`), {
      cache: "no-store",
      credentials: "include",
      headers: { Accept: "application/json", ...headers },
    }),
  );
}
