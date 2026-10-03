import Link from "next/link";
import ListingCard, { Listing } from "@/components/ListingCard";

interface ListingSectionProps {
  title: string;
  description: string;
  listings: Listing[];
}

export default function ListingSection({ title, description, listings }: ListingSectionProps) {
  return (
    <section className="w-full mb-12">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-['Plus_Jakarta_Sans'] text-xl sm:text-2xl font-bold text-[#121E1A]">{title}</h2>
          <p className="text-xs sm:text-sm text-[#3F4944] mt-0.5">{description}</p>
        </div>
        <Link href="/tim-kiem" className="text-sm font-semibold text-[#0F5F4A] hover:underline flex items-center gap-1">
          <span>Xem tất cả</span>
          <span className="material-symbols-outlined text-[16px]">chevron_right</span>
        </Link>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {listings.map((item) => <ListingCard key={item.id} item={item} />)}
      </div>
    </section>
  );
}
