import { apiUrl } from "./sessions";
import type { components } from "./generated";

export type CollectionSummary = components["schemas"]["CollectionSummaryRead"];
type GeneratedCollectionDetail = components["schemas"]["CollectionDetailRead"];
export type CollectionDetail = Omit<GeneratedCollectionDetail, "locations" | "sessions"> & {
  locations: NonNullable<GeneratedCollectionDetail["locations"]>;
  sessions: NonNullable<GeneratedCollectionDetail["sessions"]>;
};

export async function fetchCollections(limit = 24): Promise<CollectionSummary[]> {
  try {
    const response = await fetch(apiUrl(`/api/v1/collections?limit=${limit}`), {
      next: { revalidate: 120 },
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return [];
    }
    return (await response.json()) as CollectionSummary[];
  } catch {
    return [];
  }
}

export async function fetchCollectionDetail(slug: string): Promise<CollectionDetail | null> {
  try {
    const response = await fetch(apiUrl(`/api/v1/collections/${slug}`), {
      next: { revalidate: 120 },
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as CollectionDetail;
  } catch {
    return null;
  }
}
