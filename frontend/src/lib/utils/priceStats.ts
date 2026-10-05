import type { PriceStatsDto } from "@shared/dto";
import { formatPrice } from "./listing";

export interface PriceStatRow {
  id: number;
  name: string;
  avgPrice: string;
  range: string;
  trend: string;
  status: "up" | "down";
  total: number;
}

export function toPriceStatRows(stats: PriceStatsDto | null): PriceStatRow[] {
  return (stats?.price_stats_by_area || []).map((item) => ({
    id: item.area_id,
    name: item.area,
    avgPrice: formatPrice(item.average_price_vnd),
    range: `${formatPrice(item.minimum_price_vnd)} - ${formatPrice(item.maximum_price_vnd)}`,
    trend:
      item.fluctuation_month === null
        ? "--"
        : `${item.fluctuation_month > 0 ? "+" : ""}${item.fluctuation_month}%`,
    status: (item.fluctuation_month || 0) >= 0 ? "up" : "down",
    total: item.total_listings,
  }));
}