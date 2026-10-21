"use client";

import { useMemo, useState } from "react";
import type { RoomItem } from "@/app/tim-kiem-ai/types";

interface RoomMapPanelProps {
  rooms: RoomItem[];
  selectedRoom?: RoomItem | null;
  onSelectRoom: (roomId: string) => void;
  locationText?: string;
  landmarkLat?: number;
  landmarkLng?: number;
}

import {
  parseDistanceMeters,
  formatPinDistance,
  extractDistrictOrArea,
  extractStreetOrWard,
} from "./roomMapUtils";

export { parseDistanceMeters };

export default function RoomMapPanel({
  rooms,
  selectedRoom,
  onSelectRoom,
  locationText,
  landmarkLat,
  landmarkLng,
}: RoomMapPanelProps) {
  const [zoomLevel, setZoomLevel] = useState(1);
  const [viewMode, setViewMode] = useState<"visual" | "google">("visual");

  // Determine dynamic landmark name and category icon
  const landmarkInfo = useMemo(() => {
    const raw = locationText?.trim() || (rooms[0] ? extractDistrictOrArea(rooms[0].address) : "Trung tâm");
    const lower = raw.toLowerCase();

    let icon = "school";
    let shortName = raw;

    if (/(đại học|dh|đhqg|uit|bách khoa|khtn|kinh tế|ueh|fpt|hutech|spkt|sư phạm|y dược|nhân văn)/i.test(lower)) {
      icon = "school";
      if (/uit|công nghệ thông tin/i.test(lower)) shortName = "ĐH CNTT (UIT)";
      else if (/bách khoa/i.test(lower)) shortName = "ĐH Bách Khoa";
      else if (/khoa học tự nhiên|khtn/i.test(lower)) shortName = "ĐH KHTN";
      else if (/kinh tế|ueh/i.test(lower)) shortName = "UEH";
      else if (/fpt/i.test(lower)) shortName = "ĐH FPT";
      else if (/hutech/i.test(lower)) shortName = "HUTECH";
      else if (/sư phạm kĩ thuật|sư phạm kỹ thuật|spkt/i.test(lower)) shortName = "ĐH SPKT";
    } else if (/(quận|huyện|phường|thủ đức|bình thạnh|gò vấp|tân bình|phú nhuận|tân phú|bình tân|quận 1|quận 3|quận 10)/i.test(lower)) {
      icon = "apartment";
    } else {
      icon = "pin_drop";
    }

    return { name: raw, shortName, icon };
  }, [locationText, rooms]);

  // Trích xuất danh sách tên đường / khu vực thực tế từ danh sách phòng để hiển thị lên bản đồ trực quan
  const mapRoadLabels = useMemo(() => {
    const extractedStreets: string[] = [];
    const extractedWards: string[] = [];

    for (const r of rooms) {
      if (!r.address) continue;
      const parts = r.address.split(",").map((p) => p.trim()).filter(Boolean);
      for (const p of parts) {
        if (/(đường| quốc lộ|ql\s*1|xa lộ|đại lộ|hẻm|phố|võ văn ngân|hoàng diệu|phạm văn đồng|điện biên phủ|nguyễn văn cừ|tạ quang bửu|lê văn việt)/i.test(p)) {
          const cleanStreet = p.replace(/^(hẻm\s+\S+\s+)/i, "").trim();
          if (cleanStreet && !extractedStreets.includes(cleanStreet)) {
            extractedStreets.push(cleanStreet);
          }
        } else if (/(phường|p\.|linh trung|linh xuân|linh chiểu|bình thọ|đông hòa|hiệp bình|tân phú|bến nghé|phường \d+)/i.test(p)) {
          if (!extractedWards.includes(p)) {
            extractedWards.push(p);
          }
        }
      }
    }

    const lowerLoc = landmarkInfo.name.toLowerCase();
    const defaultStreets =
      /uit|khtn|bách khoa|làng đại học|linh trung|linh xuân|thủ đức/i.test(lowerLoc)
        ? ["Quốc lộ 1A / Xa lộ Hà Nội", "Đường Hàn Thuyên", "Đường Hoàng Diệu 2", "Đường Võ Văn Ngân"]
        : /bình thạnh|hutech/i.test(lowerLoc)
          ? ["Đường Điện Biên Phủ", "Đường Nguyễn Gia Trí (D2)", "Đường Xô Viết Nghệ Tĩnh", "Đường Ung Văn Khiêm"]
          : ["Trục đường chính Khu vực", "Đường Liên Phường", "Đại lộ Trung tâm", "Đường Nội khu"];

    const defaultWards =
      /uit|khtn|bách khoa|làng đại học|linh trung|linh xuân|thủ đức/i.test(lowerLoc)
        ? ["P. Linh Trung", "P. Linh Xuân", "KĐT ĐHQG TP.HCM"]
        : ["Khu dân cư trung tâm", "Khu vực lân cận"];

    const streets = [...extractedStreets, ...defaultStreets].slice(0, 4);
    const wards = [...extractedWards, ...defaultWards].slice(0, 3);
    return { streets, wards };
  }, [rooms, landmarkInfo.name]);

  // Dynamic concentric radar scale based on actual rooms' distances
  const radarScale = useMemo(() => {
    if (!rooms || rooms.length === 0) {
      return {
        scaleMaxMeters: 3000,
        scaleMaxKmText: "3.0 km",
        ring1: { r: 52, label: "1.0 km", meters: 1000 },
        ring2: { r: 88, label: "2.0 km", meters: 2000 },
        ring3: { r: 124, label: "3.0 km", meters: 3000 },
      };
    }

    const roomDistances = rooms.map((r, i) =>
      parseDistanceMeters(r.distance, 600 + i * 400)
    );
    const maxDist = Math.max(...roomDistances, 1000);

    let scaleMaxMeters = 3000;
    if (maxDist <= 1200) scaleMaxMeters = 1500;
    else if (maxDist <= 2200) scaleMaxMeters = 2500;
    else if (maxDist <= 3200) scaleMaxMeters = 3500;
    else scaleMaxMeters = Math.ceil(maxDist / 1000) * 1000;

    const rMin = 44;
    const rMax = 125;

    const m1 = Math.round(scaleMaxMeters * 0.33);
    const m2 = Math.round(scaleMaxMeters * 0.67);
    const m3 = scaleMaxMeters;

    const calcR = (m: number) => rMin + (m / scaleMaxMeters) * (rMax - rMin);
    const fmt = (m: number) => (m < 1000 ? `${m}m` : `${(m / 1000).toFixed(1).replace(".0", "")} km`);

    return {
      scaleMaxMeters,
      scaleMaxKmText: fmt(scaleMaxMeters),
      ring1: { r: calcR(m1), label: fmt(m1), meters: m1 },
      ring2: { r: calcR(m2), label: fmt(m2), meters: m2 },
      ring3: { r: calcR(m3), label: fmt(m3), meters: m3 },
    };
  }, [rooms]);

  // Compute pin positions strictly proportional to physical distance from landmark
  const calculatedPins = useMemo(() => {
    if (!rooms || rooms.length === 0) return [];

    const count = rooms.length;
    const { scaleMaxMeters } = radarScale;
    const rMin = 44;
    const rMax = 124;

    // 1. Calculate radial distance rSvg for each room
    const parsedItems = rooms.map((room, idx) => {
      const fallbackMeters = 500 + idx * 450;
      const meters = parseDistanceMeters(room.distance, fallbackMeters);
      const clampedMeters = Math.min(scaleMaxMeters, Math.max(150, meters));
      const ratio = clampedMeters / scaleMaxMeters;
      // Monotonic radius: strictly proportional to physical distance
      const rSvg = rMin + ratio * (rMax - rMin);

      // Bearing angle from landmark if GPS coordinates exist
      let rawAngle: number | null = null;
      if (
        landmarkLat &&
        landmarkLng &&
        typeof room.lat === "number" &&
        typeof room.lng === "number" &&
        !isNaN(room.lat) &&
        !isNaN(room.lng)
      ) {
        const dLat = room.lat - landmarkLat;
        const dLng = (room.lng - landmarkLng) * Math.cos((landmarkLat * Math.PI) / 180);
        if (Math.hypot(dLat, dLng) > 0.0001) {
          // In SVG coordinates, Y points down, so -dLat maps North to top
          rawAngle = Math.atan2(-dLat, dLng);
        }
      }

      return {
        room,
        idx,
        meters,
        rSvg,
        rawAngle,
        shortStreet: extractStreetOrWard(room.address),
        pinDistText: formatPinDistance(room.distance, meters),
      };
    });

    // 2. Base harmonic angular distribution across the 360-degree compass
    // Ensuring each room has its own clean visual sector
    const baseSlots = [
      -Math.PI / 2 + 0.35,  // ~ -70 deg (North-East)
      0.15,                 // ~ 10 deg (East)
      Math.PI / 2 - 0.25,   // ~ 75 deg (South-East)
      Math.PI - 0.45,       // ~ 155 deg (South-West)
      -Math.PI + 0.5,       // ~ -150 deg (North-West)
      -0.8,
      1.8,
    ];

    const angles: number[] = parsedItems.map((item, i) => {
      if (item.rawAngle !== null) {
        return item.rawAngle;
      }
      return baseSlots[i % baseSlots.length];
    });

    // Angular relaxation: if two rooms are in the same direction, nudge angles without touching radius
    for (let iter = 0; iter < 4; iter++) {
      for (let i = 0; i < count; i++) {
        for (let j = i + 1; j < count; j++) {
          let diff = angles[j] - angles[i];
          while (diff > Math.PI) diff -= 2 * Math.PI;
          while (diff < -Math.PI) diff += 2 * Math.PI;

          const radDiff = Math.abs(parsedItems[i].rSvg - parsedItems[j].rSvg);
          const minAngle = radDiff < 25 ? 0.52 : 0.35;

          if (Math.abs(diff) < minAngle) {
            const push = (minAngle - Math.abs(diff)) / 2 + 0.05;
            const sign = diff >= 0 ? 1 : -1;
            angles[i] -= sign * push;
            angles[j] += sign * push;
          }
        }
      }
    }

    // 3. Convert (rSvg, angle) into SVG coordinates and percentages
    return parsedItems.map((item, i) => {
      const angle = angles[i];
      const xSvg = 300 + item.rSvg * Math.cos(angle);
      const ySvg = 160 + item.rSvg * Math.sin(angle);

      // Clamp inside SVG viewport
      const clampedX = Math.min(560, Math.max(40, xSvg));
      const clampedY = Math.min(285, Math.max(35, ySvg));

      const leftPercent = (clampedX / 600) * 100;
      const topPercent = (clampedY / 320) * 100;

      return {
        ...item.room,
        topPercent,
        leftPercent,
        shortStreet: item.shortStreet,
        pinDistText: item.pinDistText,
        meters: item.meters,
        rSvg: item.rSvg,
      };
    });
  }, [rooms, landmarkLat, landmarkLng, radarScale]);

  const activePin = useMemo(
    () => calculatedPins.find((p) => p.id === selectedRoom?.id) || calculatedPins[0] || null,
    [calculatedPins, selectedRoom]
  );

  // Google Maps external URL and embed URL for the selected room
  const googleUrls = useMemo(() => {
    let query = "";
    if (selectedRoom) {
      if (typeof selectedRoom.lat === "number" && typeof selectedRoom.lng === "number") {
        query = `${selectedRoom.lat},${selectedRoom.lng}`;
      } else {
        query = `${selectedRoom.address}, TP. Hồ Chí Minh`;
      }
    } else if (locationText) {
      query = `${locationText}, TP. Hồ Chí Minh`;
    } else {
      query = "Đại học Công nghệ Thông tin ĐHQG TP.HCM";
    }

    const encoded = encodeURIComponent(query);
    return {
      embed: `https://maps.google.com/maps?q=${encoded}&z=16&hl=vi&output=embed`,
      external: `https://www.google.com/maps/search/?api=1&query=${encoded}`,
    };
  }, [selectedRoom, locationText]);

  return (
    <div className="bg-white rounded-2xl border border-[#E8E4DC] shadow-[0_2px_12px_rgba(15,95,74,0.04)] flex flex-col h-full overflow-hidden">
      {/* Header with Mode Switcher & Radius */}
      <div className="px-4 py-2 border-b border-[#E8E4DC] flex items-center justify-between bg-white shrink-0">
        <h2 className="text-sm font-bold text-[#0F5F4A] flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-[#0F5F4A]"></span>
          <span>3. Bản đồ vị trí</span>
        </h2>

        <div className="flex items-center gap-2">
          <div className="flex items-center bg-[#F1F5F9] rounded-lg p-0.5 text-[10px]">
            <button
              onClick={() => setViewMode("visual")}
              className={`px-2 py-0.5 rounded-md font-medium transition cursor-pointer flex items-center gap-1 ${viewMode === "visual"
                ? "bg-white text-[#0F5F4A] shadow-2xs font-bold"
                : "text-[#64748B] hover:text-[#121E1A]"
                }`}
            >
              <span className="material-symbols-outlined text-[12px]">radar</span>
              <span>Trực quan</span>
            </button>
            <button
              onClick={() => setViewMode("google")}
              className={`px-2 py-0.5 rounded-md font-medium transition cursor-pointer flex items-center gap-1 ${viewMode === "google"
                ? "bg-white text-[#0F5F4A] shadow-2xs font-bold"
                : "text-[#64748B] hover:text-[#121E1A]"
                }`}
            >
              <span className="material-symbols-outlined text-[12px]">map</span>
              <span>Google Maps</span>
            </button>
          </div>
          <a
            href={googleUrls.external}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] font-bold text-[#0F5F4A] hover:text-white bg-white hover:bg-[#0F5F4A] border border-[#E8E4DC] hover:border-[#0F5F4A] px-2 py-0.5 rounded-full shadow-2xs transition flex items-center gap-1 shrink-0"
            title="Mở trên trang Google Maps"
          >
            <span>Google Maps</span>
            <span className="material-symbols-outlined text-[11px]">open_in_new</span>
          </a>
        </div>
      </div>

      {/* Main Map Body */}
      {viewMode === "visual" ? (
        <div className="flex-1 relative bg-[#EEF2F0] overflow-hidden flex items-center justify-center select-none">
          {/* Cartographic Base Layer: Blocks, Parks, Water, Arterial & Local Roads, Street Labels */}
          <svg
            viewBox="0 0 600 320"
            preserveAspectRatio="xMidYMid slice"
            className="absolute inset-0 w-full h-full pointer-events-none transition-transform duration-300"
            style={{ transform: `scale(${zoomLevel})` }}
            xmlns="http://www.w3.org/2000/svg"
          >
            {/* Urban Green Parks & Campus Zones */}
            <rect x="215" y="95" width="170" height="125" rx="22" fill="#DCFCE7" opacity="0.55" />
            <rect x="25" y="20" width="130" height="80" rx="14" fill="#E2E8F0" opacity="0.55" />
            <rect x="430" y="25" width="145" height="90" rx="14" fill="#DCFCE7" opacity="0.4" />
            <rect x="420" y="195" width="155" height="95" rx="14" fill="#E2E8F0" opacity="0.5" />
            <rect x="35" y="195" width="140" height="95" rx="14" fill="#DCFCE7" opacity="0.35" />

            {/* Canal / River Stream */}
            <path
              d="M 0 275 Q 160 245, 310 285 T 600 250"
              fill="none"
              stroke="#BAE6FD"
              strokeWidth="12"
              strokeLinecap="round"
              opacity="0.7"
            />

            {/* Fine Urban Street Grid */}
            <g stroke="#DDE3EA" strokeWidth="1.5" opacity="0.85">
              <line x1="90" y1="0" x2="90" y2="320" />
              <line x1="185" y1="0" x2="185" y2="320" />
              <line x1="415" y1="0" x2="415" y2="320" />
              <line x1="510" y1="0" x2="510" y2="320" />
              <line x1="0" y1="65" x2="600" y2="65" />
              <line x1="0" y1="245" x2="600" y2="245" />
            </g>

            {/* Secondary Roads (White with slate casing) */}
            <g stroke="#CBD5E1" strokeWidth="9" strokeLinecap="round" fill="none">
              <path d="M 135 0 L 245 320" />
              <path d="M 455 0 L 395 320" />
              <path d="M 0 115 Q 300 135, 600 95" />
            </g>
            <g stroke="#FFFFFF" strokeWidth="6" strokeLinecap="round" fill="none">
              <path d="M 135 0 L 245 320" />
              <path d="M 455 0 L 395 320" />
              <path d="M 0 115 Q 300 135, 600 95" />
            </g>

            {/* Primary Arterial Highway (Xa lộ Hà Nội / QL1A / Trục chính) */}
            <path
              d="M 0 225 Q 260 175, 600 135"
              fill="none"
              stroke="#F59E0B"
              strokeWidth="11"
              strokeLinecap="round"
              opacity="0.35"
            />
            <path
              d="M 0 225 Q 260 175, 600 135"
              fill="none"
              stroke="#FEF3C7"
              strokeWidth="7"
              strokeLinecap="round"
            />
            <path
              d="M 0 225 Q 260 175, 600 135"
              fill="none"
              stroke="#D97706"
              strokeWidth="1.5"
              strokeDasharray="6,6"
              strokeLinecap="round"
              opacity="0.75"
            />

            {/* Ward / Area Background Labels */}
            {mapRoadLabels.wards[0] && (
              <text
                x="85"
                y="48"
                fill="#64748B"
                fontSize="9.5"
                fontWeight="700"
                letterSpacing="0.8"
                opacity="0.75"
              >
                {mapRoadLabels.wards[0].toUpperCase()}
              </text>
            )}
            {mapRoadLabels.wards[1] && (
              <text
                x="445"
                y="52"
                fill="#0F5F4A"
                fontSize="9.5"
                fontWeight="700"
                letterSpacing="0.8"
                opacity="0.75"
              >
                {mapRoadLabels.wards[1].toUpperCase()}
              </text>
            )}
            {mapRoadLabels.wards[2] && (
              <text
                x="440"
                y="272"
                fill="#64748B"
                fontSize="9"
                fontWeight="700"
                letterSpacing="0.6"
                opacity="0.7"
              >
                {mapRoadLabels.wards[2].toUpperCase()}
              </text>
            )}



            {/* Concentric Radar Distance Rings */}
            {/* Ring 1: Inner (< 1km or < 500m) */}
            <circle
              cx="300"
              cy="160"
              r={radarScale.ring1.r}
              fill="rgba(15, 95, 74, 0.04)"
              stroke="#0F5F4A"
              strokeWidth="1.2"
              strokeDasharray="4,4"
              opacity="0.55"
            />
            <text
              x="300"
              y={Math.max(22, 160 - radarScale.ring1.r - 4)}
              textAnchor="middle"
              fill="#0F5F4A"
              fontSize="8"
              fontWeight="700"
              opacity="0.8"
            >
              {`< ${radarScale.ring1.label}`}
            </text>

            {/* Ring 2: Middle (~ 2km or ~ 1km) */}
            <circle
              cx="300"
              cy="160"
              r={radarScale.ring2.r}
              fill="rgba(15, 95, 74, 0.025)"
              stroke="#0F5F4A"
              strokeWidth="1.2"
              strokeDasharray="6,4"
              opacity="0.4"
            />
            <text
              x="300"
              y={Math.max(18, 160 - radarScale.ring2.r - 4)}
              textAnchor="middle"
              fill="#0F5F4A"
              fontSize="8"
              fontWeight="700"
              opacity="0.7"
            >
              {`~ ${radarScale.ring2.label}`}
            </text>

            {/* Ring 3: Outer (~ 3km or max scale) */}
            <circle
              cx="300"
              cy="160"
              r={radarScale.ring3.r}
              fill="rgba(15, 95, 74, 0.01)"
              stroke="#0F5F4A"
              strokeWidth="1.2"
              opacity="0.25"
            />
            <text
              x="300"
              y={Math.max(14, 160 - radarScale.ring3.r - 4)}
              textAnchor="middle"
              fill="#0F5F4A"
              fontSize="8"
              fontWeight="700"
              opacity="0.6"
            >
              {`~ ${radarScale.ring3.label}`}
            </text>

            {/* Active Route Line from Center Landmark (300, 160) to Selected Room Pin */}
            {activePin && (
              <g>
                <line
                  x1="300"
                  y1="160"
                  x2={(activePin.leftPercent / 100) * 600}
                  y2={(activePin.topPercent / 100) * 320}
                  stroke="#FF6B4A"
                  strokeWidth="2.5"
                  strokeDasharray="5,4"
                  strokeLinecap="round"
                />
                <circle
                  cx={(activePin.leftPercent / 100) * 600}
                  cy={(activePin.topPercent / 100) * 320}
                  r="14"
                  fill="rgba(255, 107, 74, 0.18)"
                />
                {/* Midpoint route distance indicator badge */}
                {(activePin.pinDistText || activePin.distance) && (
                  <g
                    transform={`translate(${(300 + (activePin.leftPercent / 100) * 600) / 2
                      }, ${(160 + (activePin.topPercent / 100) * 320) / 2
                      })`}
                  >
                    <rect
                      x="-24"
                      y="-9"
                      width="48"
                      height="16"
                      rx="8"
                      fill="#FF6B4A"
                      stroke="#FFFFFF"
                      strokeWidth="1.2"
                    />
                    <text
                      x="0"
                      y="2.5"
                      textAnchor="middle"
                      fill="#FFFFFF"
                      fontSize="8"
                      fontWeight="bold"
                    >
                      {activePin.pinDistText || activePin.distance}
                    </text>
                  </g>
                )}
              </g>
            )}
          </svg>

          {/* Center Landmark Pin (UIT / Trường ĐH / Quận) */}
          <div
            className="relative z-10 flex flex-col items-center transition-transform duration-300 pointer-events-none"
            style={{ transform: `scale(${zoomLevel})` }}
          >
            <div className="w-9 h-9 rounded-full bg-[#0F5F4A] text-white flex items-center justify-center shadow-lg border-2 border-white ring-4 ring-[#0F5F4A]/15">
              <span className="material-symbols-outlined text-[18px]">{landmarkInfo.icon}</span>
            </div>
            <span className="mt-1 px-2 py-0.5 bg-[#004635] text-white text-[9.5px] font-extrabold rounded-full shadow-xs tracking-wide max-w-[130px] truncate text-center">
              {landmarkInfo.shortName}
            </span>
          </div>

          {/* Room Pin Teardrop Markers (Google Maps style) */}
          {calculatedPins.map((room) => {
            const isSelected = selectedRoom?.id === room.id;
            return (
              <div
                key={room.id}
                onClick={() => onSelectRoom(room.id)}
                style={{
                  top: `${room.topPercent}%`,
                  left: `${room.leftPercent}%`,
                  transform: `translate(-50%, -100%) scale(${zoomLevel * (isSelected ? 1.25 : 1)})`,
                }}
                className={`absolute z-20 flex flex-col items-center cursor-pointer transition-all duration-300 origin-bottom ${isSelected
                  ? "z-30 drop-shadow-[0_4px_10px_rgba(234,179,8,0.55)]"
                  : "hover:scale-115 drop-shadow-md"
                  }`}
                title={`${room.rankText}: ${room.title} | ${room.price} | Cách ${landmarkInfo.shortName}: ${room.distance}`}
              >
                <svg
                  width={isSelected ? "30" : "26"}
                  height={isSelected ? "40" : "34"}
                  viewBox="0 0 24 32"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                  className="transition-all duration-200"
                >
                  {/* Google Maps Teardrop Shape */}
                  <path
                    d="M12 0C5.37258 0 0 5.37258 0 12C0 21 12 32 12 32C12 32 24 21 24 12C24 5.37258 18.6274 0 12 0Z"
                    fill={isSelected ? "#EAB308" : "#0F5F4A"}
                    stroke="#FFFFFF"
                    strokeWidth={isSelected ? "2" : "1.6"}
                  />
                  {/* Center Circle for Number Badge */}
                  <circle cx="12" cy="11.5" r="7.5" fill="#FFFFFF" />
                  {/* Pin Number */}
                  <text
                    x="12"
                    y="15.2"
                    textAnchor="middle"
                    fill={isSelected ? "#A16207" : "#0F5F4A"}
                    fontSize="10.5"
                    fontWeight="900"
                    fontFamily="system-ui, -apple-system, sans-serif"
                  >
                    {room.rank}
                  </text>
                </svg>
              </div>
            );
          })}

          {/* Zoom Controls */}
          <div className="absolute right-2.5 top-2.5 z-20 flex flex-col bg-white rounded-lg shadow-sm border border-[#E8E4DC] overflow-hidden text-xs">
            <button
              onClick={() => setZoomLevel((z) => Math.min(1.4, Number((z + 0.15).toFixed(2))))}
              className="w-7 h-7 flex items-center justify-center hover:bg-[#E9F7F0] text-[#121E1A] font-bold border-b border-[#E8E4DC] transition cursor-pointer"
              title="Phóng to"
            >
              +
            </button>
            <button
              onClick={() => setZoomLevel((z) => Math.max(0.85, Number((z - 0.15).toFixed(2))))}
              className="w-7 h-7 flex items-center justify-center hover:bg-[#E9F7F0] text-[#121E1A] font-bold transition cursor-pointer"
              title="Thu nhỏ"
            >
              -
            </button>
          </div>

          {/* Re-center Button */}
          <div className="absolute right-2.5 bottom-2.5 z-20 bg-white rounded-lg shadow-sm border border-[#E8E4DC]">
            <button
              onClick={() => setZoomLevel(1)}
              className="w-7 h-7 flex items-center justify-center hover:bg-[#E9F7F0] text-[#0F5F4A] transition cursor-pointer"
              title={`Đặt lại góc nhìn ${landmarkInfo.shortName}`}
            >
              <span className="material-symbols-outlined text-[16px]">my_location</span>
            </button>
          </div>
        </div>
      ) : (
        /* Google Maps Live Iframe Mode */
        <div className="flex-1 relative bg-[#E2E8F0] min-h-0 overflow-hidden">
          <iframe
            title="Google Maps Location"
            src={googleUrls.embed}
            className="w-full h-full border-0"
            loading="lazy"
            allowFullScreen
            referrerPolicy="no-referrer-when-downgrade"
          />
        </div>
      )}
    </div>
  );
}