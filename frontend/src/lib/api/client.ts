import type { ListingDetailDto, ListingDto, ListingQueryDto } from "@shared/dto";
import { API_BASE_URL } from "./config";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function buildQuery(params: ListingQueryDto) {
  const query = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  });

  const serialized = query.toString();
  return serialized ? `?${serialized}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    throw new ApiError(`API request failed: ${response.status} ${response.statusText}`, response.status);
  }

  return response.json() as Promise<T>;
}

export const listingsApi = {
  list(params: ListingQueryDto = {}) {
    return request<ListingDto[]>(`/listings/${buildQuery(params)}`);
  },

  getById(listingId: string) {
    return request<ListingDetailDto>(`/listings/${encodeURIComponent(listingId)}`);
  },
};
