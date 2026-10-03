import Link from "next/link";

export interface SearchResult {
  id: string;
  title: string;
  type: string;
  location: string;
  price: string;
  area: string;
  verified: boolean;
  source: string;
  time: string;
  image: string;
  tags: string[];
}

interface SearchResultCardProps {
  item: SearchResult;
}

export default function SearchResultCard({ item }: SearchResultCardProps) {
  return (
    <Link
      href={`/phong-tro/${item.id}`}
      className="bg-white rounded-2xl p-3 border border-[#E8E4DC] shadow-xs hover:shadow-md hover:-translate-y-1 transition-all group flex flex-col"
    >
      <div className="relative aspect-[4/3] rounded-xl overflow-hidden bg-gray-100 mb-3">
        <img src={item.image} alt={item.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
        <span className="absolute top-2.5 left-2.5 bg-white/95 px-3 py-1 rounded-full text-[11px] font-semibold shadow-xs">
          {item.type}
        </span>
        <button
          type="button"
          onClick={(event) => event.preventDefault()}
          aria-label={`Lưu ${item.title}`}
          className="absolute top-2.5 right-2.5 w-8 h-8 rounded-full bg-white/90 text-gray-600 hover:text-[#FF6B4A] flex items-center justify-center shadow-xs"
        >
          <span className="material-symbols-outlined text-[18px]">bookmark</span>
        </button>
        <div className="absolute bottom-2.5 left-2.5 bg-[#0F5F4A] text-white px-2.5 py-0.5 rounded-full text-[10px] font-bold shadow-xs">
          {item.source}
        </div>
      </div>
      <div className="flex-1 flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
            <span className="font-semibold text-[#0F5F4A]">{item.area}</span>
            <span>{item.time}</span>
          </div>
          <h3 className="font-['Plus_Jakarta_Sans'] font-bold text-base text-[#121E1A] line-clamp-2 group-hover:text-[#0F5F4A] transition-colors">
            {item.title}
          </h3>
          <p className="text-xs text-gray-600 flex items-center gap-1 mt-1 line-clamp-1">
            <span className="material-symbols-outlined text-[14px] text-[#0F5F4A]">location_on</span>
            <span>{item.location}</span>
          </p>
          <div className="flex flex-wrap gap-1.5 mt-3">
            {item.tags.map((tag) => (
              <span key={tag} className="px-2 py-0.5 rounded-md bg-[#FAF8F4] border border-[#E8E4DC] text-[11px] text-gray-700 font-medium">
                {tag}
              </span>
            ))}
          </div>
        </div>
        <div className="mt-4 pt-3 border-t border-gray-100 flex items-center justify-between">
          <span className="font-['Plus_Jakarta_Sans'] text-lg font-extrabold text-[#FF6B4A]">
            {item.price}<span className="text-xs font-normal text-gray-500">/tháng</span>
          </span>
          <span className="text-xs text-[#0F5F4A] font-bold group-hover:translate-x-0.5 transition-transform">
            Xem chi tiết →
          </span>
        </div>
      </div>
    </Link>
  );
}
