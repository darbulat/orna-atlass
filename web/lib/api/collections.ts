import { apiUrl } from "./sessions";

export type CollectionSummary = {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  sort_order: number;
  location_count: number;
  session_count: number;
};

export type CollectionDetail = CollectionSummary & {
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  locations: Array<{
    id: string;
    slug: string;
    name: string;
    description: string | null;
    habitat: string | null;
    latitude: number | null;
    longitude: number | null;
    coordinates_protected: boolean;
    coordinate_visibility: string;
    sensitivity_level: string;
  }>;
  sessions: Array<{
    id: string;
    slug: string;
    title: string;
    description: string | null;
    duration_seconds: number | null;
    is_featured: boolean;
  }>;
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
