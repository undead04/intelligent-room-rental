export interface ListingDto {
  listing_id: string;
  title: string;
  price_vnd: number | null;
  area_m2: number | null;
  address_raw: string | null;
  lat: number | null;
  lng: number | null;
  main_image: string | null;
  room_type: string | null;
  price_string: string | null;
  price_million_per_m2: number | null;
  deposit: number | null;
  furnishing: string | null;
  district: string | null;
  city: string | null;
  poster_id: string | null;
}

export interface ListingDetailDto extends ListingDto {
  ad_id: string | null;
  list_id: string | null;
  source: string | null;
  url: string | null;
  description: string | null;
  images: string[] | null;
  furnishing_code: number | null;
  category_id: number | null;
  street_name: string | null;
  ward: string | null;
  ward_id: number | null;
  district_id: number | null;
  region_id: number | null;
  posted_date: string | null;
  crawled_at: string | null;
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
}
