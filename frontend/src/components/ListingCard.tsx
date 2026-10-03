import Link from "next/link";

export interface Listing {
  id: string;
  title: string;
  location: string;
  price: string;
  tag: string;
  source: string;
  image: string;
  time: string;
}

interface ListingCardProps {
  item: Listing;
}

export default function ListingCard({ item }: ListingCardProps) {
  return (
    <Link
      href={`/phong-tro/${item.id}`}
      className="bg-white rounded-[20px] p-3 border border-[#ECE8E0] shadow-xs hover:shadow-md transition-all group flex flex-col"
    >
      <div className="relative w-full aspect-[4/3] rounded-[16px] overflow-hidden bg-gray-100">
        <img
          src={item.image}
          alt={item.title}
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
        />
        <span className="absolute top-2.5 left-2.5 px-2.5 py-1 rounded-full bg-white/95 text-xs font-semibold shadow-xs">
          {item.tag}
        </span>
        <button
          type="button"
          onClick={(event) => event.preventDefault()}
          className="absolute top-2.5 right-2.5 w-8 h-8 rounded-full bg-white/90 text-gray-600 hover:text-[#FF6B4A] flex items-center justify-center shadow-xs"
          aria-label={`Lưu ${item.title}`}
        >
          <span className="material-symbols-outlined text-[18px]">bookmark</span>
        </button>
      </div>
      <div className="pt-3 px-1 flex-1 flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
            <span className="font-semibold text-[#0F5F4A]">{item.source}</span>
            <span>{item.time}</span>
          </div>
          <h3 className="font-['Plus_Jakarta_Sans'] font-bold text-sm text-[#121E1A] line-clamp-1 group-hover:text-[#0F5F4A] transition-colors">
            {item.title}
          </h3>
          <p className="text-xs text-[#3F4944] flex items-center gap-1 mt-1 line-clamp-1">
            <span className="material-symbols-outlined text-[14px] text-[#0F5F4A]">location_on</span>
            <span>{item.location}</span>
          </p>
        </div>
        <div className="mt-3 pt-2 border-t border-gray-100 flex items-center justify-between">
          <span className="font-['Plus_Jakarta_Sans'] text-base font-extrabold text-[#FF6B4A]">
            {item.price}<span className="text-xs font-normal text-gray-500">/tháng</span>
          </span>
          <span className="text-xs text-[#0F5F4A] font-semibold group-hover:translate-x-0.5 transition-transform">
            Chi tiết →
          </span>
        </div>
      </div>
    </Link>
  );
}
