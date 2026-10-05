import type {
  CityDto,
  DistrictDto,
  ListingDetailDto,
  ListingCountDto,
  ListingDto,
  ListingQueryDto,
  PriceStatsDto,
  ResponseDto,
  RoomTypeDto,
  WardDto,
} from "@shared/dto";
import { API_BASE_URL } from "./config";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
    public readonly requestId?: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function buildQuery<T extends object>(params: T) {
  const query = new URLSearchParams();

  Object.entries(params as Record<string, number | string | undefined>).forEach(([key, value]) => {
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
    const error = await response.json().catch(() => null) as {
      message?: string;
      code?: string;
      request_id?: string | null;
    } | null;
    throw new ApiError(
      error?.message || `API request failed: ${response.status} ${response.statusText}`,
      response.status,
      error?.code,
      error?.request_id,
    );
  }

  const envelope = (await response.json()) as ResponseDto<T>;
  return envelope.data;
}

export const listingsApi = {
  list(params: ListingQueryDto = {}) {
    return request<ListingDto[]>(`/listings/${buildQuery(params)}`);
  },

  count(params: Omit<ListingQueryDto, "limit" | "offset"> = {}) {
    return request<ListingCountDto>(`/listings/total${buildQuery(params)}`);
  },

  getById(listingId: string) {
    return request<ListingDetailDto>(`/listings/${encodeURIComponent(listingId)}`);
  },
};

export const locationsApi = {
  cities(search?: string) {
    return request<CityDto[]>(`/locations/cities${search ? `?search=${encodeURIComponent(search)}` : ""}`);
  },

  districts(params: { city_id?: number; search?: string } = {}) {
    return request<DistrictDto[]>(`/locations/districts${buildQuery(params)}`);
  },

  wards(params: { district_id?: number; search?: string } = {}) {
    return request<WardDto[]>(`/locations/wards${buildQuery(params)}`);
  },
};

export const roomTypesApi = {
  list(search?: string) {
    return request<RoomTypeDto[]>(`/room-types/${search ? `?search=${encodeURIComponent(search)}` : ""}`);
  },
};

export const priceStatsApi = {
  get(params: { city_id?: number; district_id?: number; room_type_id?: number } = {}) {
    return request<PriceStatsDto>(`/listings/price-stats${buildQuery(params)}`);
  },
};
