import { useEffect, useState } from "react";
import type { ListingDetailDto, ListingQueryDto } from "@/types/dto";
import type { ListingCardData } from "@/types";
import { listingsApi } from "@/lib/api/client";
import { toListingCard } from "@/lib/utils/listing";

const SIMILAR_LIMIT = 8;
// Lấy dư 1 bản ghi vì tin đang xem có thể nằm trong chính kết quả trả về
const FETCH_LIMIT = SIMILAR_LIMIT + 1;

type Attempt = Partial<Pick<ListingQueryDto, "room_type_id" | "city_id" | "district_id">>;

interface SimilarSnapshot {
  requestKey: string;
  items: ListingCardData[];
}

export function useSimilarListings(listing: ListingDetailDto | null) {
  const [snapshot, setSnapshot] = useState<SimilarSnapshot | null>(null);

  const listingId = listing?.id ?? null;
  const roomTypeId = listing?.room_type?.id ?? null;
  const cityId = listing?.city?.id ?? null;
  const districtId = listing?.district?.id ?? null;

  const requestKey = `${listingId}|${roomTypeId}|${cityId}|${districtId}`;

  useEffect(() => {
    if (!listingId) return;

    let cancelled = false;

    // Ưu tiên phòng cùng khu vực và cùng loại, nới dần khi không đủ kết quả
    const attempts: Attempt[] = [];
    if (roomTypeId && districtId) attempts.push({ room_type_id: roomTypeId, district_id: districtId });
    if (roomTypeId && cityId) attempts.push({ room_type_id: roomTypeId, city_id: cityId });
    if (roomTypeId) attempts.push({ room_type_id: roomTypeId });
    attempts.push({});

    const fetchSimilar = async () => {
      for (const attempt of attempts) {
        try {
          const data = await listingsApi.list({
            ...attempt,
            limit: FETCH_LIMIT,
            order_by: "posted_date",
            sort_desc: true,
          });
          const similar = data
            .filter((item) => item.id !== listingId)
            .map(toListingCard)
            .slice(0, SIMILAR_LIMIT);
          if (similar.length > 0) return similar;
        } catch {
          // Bỏ qua attempt này và thử bước nới rộng hơn
        }
      }
      return [];
    };

    fetchSimilar().then((items) => {
      if (!cancelled) setSnapshot({ requestKey, items });
    });

    return () => {
      cancelled = true;
    };
  }, [listingId, roomTypeId, cityId, districtId, requestKey]);

  return { listings: snapshot?.requestKey === requestKey ? snapshot.items : [] };
}