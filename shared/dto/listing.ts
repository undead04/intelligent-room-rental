export interface CityDto {
  id: number;
  name: string;
  region_id: number | null;
}

export interface DistrictDto {
  id: number;
  city_id: number;
  name: string;
  district_id: number | null;
}

export interface WardDto {
  id: number;
  district_id: number;
  name: string;
  ward_id: number | null;
}

export interface RoomTypeDto {
  id: number;
  room_type: string | null;
}

export interface ListingDto {
  list_id: number;
  title: string;
  source: string | null;
  url: string | null;
  price_vnd: number | null;
  area_m2: number | null;
  address_raw: string | null;
  lat: number | null;
  lng: number | null;
  main_image: string | null;
  price_string: string | null;
  city: CityDto | null;
  district: DistrictDto | null;
  ward: WardDto | null;
  room_type: RoomTypeDto | null;
}

export interface ListingDetailDto extends ListingDto {
  description: string | null;
  images: string[] | null;
  price_million_per_m2: number | null;
  deposit: number | null;
  furnishing_code: number | null;
  posted_date: string | null;
  crawled_at: string | null;
  safety_score: number | null;
  concept_scores: Record<string, number> | null;
  poster: UserDto | null;
}

export interface UserDto {
  id: string;
  name: string;
  avatar_url: string | null;
  live_ads: number;
  sold_ads: number;
  is_company: boolean | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ListingQueryDto {
  limit?: number;
  offset?: number;
  search?: string;
  district?: string;
  city_id?: number;
  district_id?: number;
  ward_id?: number;
  room_type_id?: number;
  min_price?: number;
  max_price?: number;
  min_area?: number;
  max_area?: number;
}

export interface PriceStatsDto {
  city: string | null;
  district: string | null;
  room_type: string | null;
  total_listings: number;
  average_price_vnd: number | null;
  minimum_price_vnd: number | null;
  maximum_price_vnd: number | null;
  average_area_m2: number | null;
}
