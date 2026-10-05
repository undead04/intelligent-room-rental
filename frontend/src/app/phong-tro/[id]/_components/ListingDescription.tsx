interface ListingDescriptionProps {
  description: string | null | undefined;
}

export default function ListingDescription({ description }: ListingDescriptionProps) {
  return (
    <div className="bg-white rounded-2xl p-6 border border-[#E8E4DC] shadow-xs space-y-3">
      <h2 className="font-['Plus_Jakarta_Sans'] font-bold text-lg text-[#121E1A]">
        Mô tả chi tiết
      </h2>
      <div className="text-sm text-gray-700 space-y-2 leading-relaxed">
        <p>{description || "Thông tin mô tả đang được cập nhật."}</p>
      </div>
    </div>
  );
}