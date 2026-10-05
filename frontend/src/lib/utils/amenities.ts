import type { AmenityKey } from "@shared/dto";

export interface AmenityDisplay {
  icon: string;
  label: string;
}

export const AMENITY_LABELS: Record<AmenityKey, AmenityDisplay> = {
  private_wc: {
    icon: "wc",
    label: "WC riêng / khép kín",
  },
  aircon: {
    icon: "ac_unit",
    label: "Máy lạnh / điều hòa",
  },
  furniture: {
    icon: "chair",
    label: "Có nội thất",
  },
  window_balcony: {
    icon: "balcony",
    label: "Cửa sổ / ban công thoáng",
  },
  kitchen: {
    icon: "countertops",
    label: "Kệ bếp & chỗ nấu ăn",
  },
  mezzanine: {
    icon: "stairs",
    label: "Gác lửng / gác xép",
  },
  washing_machine: {
    icon: "local_laundry_service",
    label: "Máy giặt",
  },
  water_heater: {
    icon: "water_heater",
    label: "Máy nước nóng",
  },
  wifi: {
    icon: "wifi",
    label: "Wifi / Internet",
  },
  parking: {
    icon: "two_wheeler",
    label: "Chỗ để xe",
  },
};

const NO_AMENITY: AmenityDisplay = { icon: "block", label: "Không có tiện nghi" };

export function toAmenities(
  conceptScores: Record<AmenityKey, number> | null | undefined,
): AmenityDisplay[] {
  if (!conceptScores) return [NO_AMENITY];

  const activeAmenities = Object.entries(conceptScores)
    .filter(([key, value]) => value > 0.5 && key in AMENITY_LABELS)
    .map(([key]) => AMENITY_LABELS[key as AmenityKey]);

  if (activeAmenities.length === 0) return [NO_AMENITY];
  return activeAmenities;
}

export function toFurnishingLabel(furnishingCode: number | null | undefined): string {
  switch (furnishingCode) {
    case 1:
      return "Không có nội thất";
    case 2:
      return "Nội thất đầy đủ";
    case 3:
      return "Nội thất cao cấp";
    default:
      return "Không xác định";
  }
}