interface ListingKeyDetailsProps {
  area: string;
  roomType: string;
  furnishing: string;
  deposit: string;
}

export default function ListingKeyDetails({
  area,
  roomType,
  furnishing,
  deposit,
}: ListingKeyDetailsProps) {
  const details: { icon: string; label: string; value: string }[] = [
    { icon: "square_foot", label: "Diện tích", value: area },
    { icon: "bed", label: "Loại phòng", value: roomType },
    { icon: "chair", label: "Nội thất", value: furnishing },
    { icon: "payments", label: "Đặt cọc", value: deposit },
  ];

  return (
    <section className="rounded-2xl border border-[#E8E4DC] bg-white p-6 shadow-xs">
      <h2 className="mb-4 font-['Plus_Jakarta_Sans'] text-lg font-bold text-[#121E1A]">Thông tin phòng</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {details.map((detail) => (
          <div key={detail.label} className="rounded-xl bg-[#F5FBF7] p-3.5">
            <span className="material-symbols-outlined text-[20px] text-[#0F5F4A]">{detail.icon}</span>
            <p className="mt-2 text-[11px] text-gray-500">{detail.label}</p>
            <p className="mt-0.5 text-sm font-bold text-[#121E1A]">{detail.value}</p>
          </div>
        ))}
      </div>
    </section>
  );
}