interface LocationMapProps {
  address: string;
  latitude?: number | null;
  longitude?: number | null;
}

export default function LocationMap({ address, latitude, longitude }: LocationMapProps) {
  const hasCoordinates = latitude !== null && latitude !== undefined
    && longitude !== null && longitude !== undefined;
  const destination = hasCoordinates
    ? `${latitude},${longitude}`
    : `${address}, Việt Nam`;
  const encodedDestination = encodeURIComponent(destination);
  const embedUrl = `https://www.google.com/maps?q=${encodedDestination}&z=17&hl=vi&output=embed`;
  const googleMapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodedDestination}`;

  return (
    <section className="rounded-2xl border border-[#E8E4DC] bg-white p-5 shadow-xs">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 font-['Plus_Jakarta_Sans'] text-lg font-bold text-[#121E1A]">
          <span className="material-symbols-outlined text-[21px] text-[#0F5F4A]">location_on</span>
          Vị trí trên bản đồ
        </h2>
        <a
          href={googleMapsUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-sm font-semibold text-[#00A86B] hover:text-[#008957]"
        >
          Mở Google Maps
          <span className="material-symbols-outlined text-[16px]">open_in_new</span>
        </a>
      </div>

      <div className="relative overflow-hidden rounded-xl border border-[#D5E2D8] bg-[#EAF2E9]">
        <iframe
          title={`Bản đồ vị trí ${address}`}
          src={embedUrl}
          loading="lazy"
          referrerPolicy="no-referrer-when-downgrade"
          className="h-64 w-full border-0 sm:h-72"
        />
        <div className="pointer-events-none absolute left-3 top-3 max-w-[min(85%,360px)] rounded-lg bg-white/95 px-3 py-2 shadow-md">
          <p className="text-xs font-bold text-[#121E1A]">Điểm cần đến</p>
          <p className="mt-0.5 truncate text-xs text-gray-600">{address}</p>
        </div>
      </div>

      <div className="mt-3 flex items-start gap-2 text-xs text-gray-600">
        <span className="material-symbols-outlined text-[17px] text-[#0F5F4A]">location_on</span>
        <span className="line-clamp-2">{address}</span>
      </div>
    </section>
  );
}
