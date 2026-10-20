/**
 * Utility functions for RoomMapPanel calculations:
 * - Parsing distance strings from Vietnamese text / API responses into meters
 * - Formatting distances for pins and labels
 * - Extracting human-readable street, ward, and district names from raw addresses
 */

export function parseDistanceMeters(distanceStr?: string, fallbackMeters = 1000): number {
  if (!distanceStr) return fallbackMeters;
  const str = distanceStr.toLowerCase().trim();

  // Pattern 1: e.g. "2.8 km", "2,8km", "~ 1.5 km", "1.5km"
  const kmMatch = str.match(/([\d]+(?:[.,]\d+)?)\s*km/);
  if (kmMatch) {
    const val = parseFloat(kmMatch[1].replace(",", "."));
    if (!isNaN(val)) return Math.round(val * 1000);
  }

  // Pattern 2: e.g. "350m", "350 m", "~ 800m"
  const mMatch = str.match(/([\d]+(?:[.,]\d+)?)\s*m\b/);
  if (mMatch) {
    const val = parseFloat(mMatch[1].replace(",", "."));
    if (!isNaN(val)) return Math.round(val);
  }

  // Pattern 3: Leading number without unit (e.g. "2.5" or "500")
  const numMatch = str.match(/^~?\s*([\d]+(?:[.,]\d+)?)/);
  if (numMatch) {
    const val = parseFloat(numMatch[1].replace(",", "."));
    if (!isNaN(val)) {
      return val < 25 ? Math.round(val * 1000) : Math.round(val);
    }
  }

  return fallbackMeters;
}

export function formatPinDistance(distanceStr?: string, meters?: number): string {
  if (distanceStr) {
    const clean = distanceStr.replace(/^~\s*/, "").trim();
    if (/\d/.test(clean)) {
      return clean.replace(/\s+/g, "");
    }
  }
  if (meters && meters > 0) {
    return meters < 1000 ? `${meters}m` : `${(meters / 1000).toFixed(1).replace(".0", "")}km`;
  }
  return "";
}

export function extractDistrictOrArea(address?: string): string {
  if (!address) return "TP.HCM";
  const parts = address.split(",").map((s) => s.trim());
  for (let i = parts.length - 1; i >= 0; i--) {
    const part = parts[i];
    if (/(quận|huyện|thành phố|tp\.|thủ đức|bình thạnh|gò vấp|tân bình|phú nhuận|tân phú|bình tân)/i.test(part)) {
      return part.replace(/^(TP\.|Thành phố|Quận|Huyện)\s*/i, "");
    }
  }
  return parts[parts.length - 1] || "TP.HCM";
}

export function extractStreetOrWard(address?: string): string {
  if (!address) return "";
  const parts = address
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (parts.length === 0) return "";
  // Trả về tên đường hoặc tên phường ngắn gọn
  const first = parts[0].replace(/^(Số\s+\S+\s+)/i, "").trim();
  if (first.length >= 3 && first.length <= 28) return first;
  if (parts[1]) return parts[1].trim();
  return first.slice(0, 26);
}
