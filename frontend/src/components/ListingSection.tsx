import Link from "next/link";
import ListingCard from "@/components/ListingCard";
import type { ListingCardData } from "@/types";

interface ListingSectionProps {
  title: string;
  description: string;
  listings: ListingCardData[];
}

export default function ListingSection({ title, description, listings }: ListingSectionProps) {
  return (
    <section className="w-full mb-10">
      <div className="flex items-end justify-between gap-4 mb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="h-6 w-1 rounded-full bg-[#FF6B4A]" />
            <h2 className="font-['Plus_Jakarta_Sans'] text-xl sm:text-2xl font-extrabold text-[#121E1A]">{title}</h2>
          </div>
          <p className="text-xs sm:text-sm text-[#6F7974] mt-1.5 ml-3">{description}</p>
        </div>
        <Link href="/tim-kiem" className="shrink-0 inline-flex items-center gap-1 rounded-full border border-[#CFE4D9] bg-[#F1FBF6] px-3.5 py-2 text-xs font-bold text-[#0F5F4A] hover:bg-[#0F5F4A] hover:text-white transition-colors">
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
