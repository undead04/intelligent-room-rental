import Link from "next/link";
import { useRef } from "react";

interface SimilarListingsProps {
  images: string[];
  defaultImage: string;
}

export default function SimilarListings({ images, defaultImage }: SimilarListingsProps) {
  const listingsRef = useRef<HTMLDivElement>(null);

  return (
    <section className="mt-8 border-t border-[#E8E4DC] pt-8">
      <div className="mb-4 flex items-end justify-between">
        <div>
          <h2 className="font-['Plus_Jakarta_Sans'] text-xl font-extrabold text-[#121E1A]">Phòng tương tự gần đây</h2>
          <p className="mt-1 text-sm text-gray-500">Một số lựa chọn khác có thể phù hợp với bạn</p>
        </div>
        <div className="flex gap-2">
          <CarouselButton direction="left" onClick={() => listingsRef.current?.scrollBy({ left: -320, behavior: "smooth" })} />
          <CarouselButton direction="right" onClick={() => listingsRef.current?.scrollBy({ left: 320, behavior: "smooth" })} />
        </div>
      </div>
      <div ref={listingsRef} className="flex snap-x gap-4 overflow-x-auto pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {Array.from({ length: 8 }, (_, index) => {
          const image = images[index % images.length] || defaultImage;
          return (
            <Link key={`${image}-${index}`} href="/tim-kiem" className="w-[78vw] shrink-0 snap-start overflow-hidden rounded-2xl border border-[#E8E4DC] bg-white transition-shadow hover:shadow-md sm:w-[calc(50%-8px)] lg:w-[calc(25%-12px)]">
              <img
                src={image}
                alt="Phòng tương tự"
                onError={(event) => {
                  event.currentTarget.onerror = null;
                  event.currentTarget.src = defaultImage;
                }}
                className="aspect-[4/3] w-full object-cover"
              />
              <div className="p-3">
                <p className="truncate text-sm font-bold text-[#121E1A]">Phòng đầy đủ tiện nghi gần khu vực</p>
                <p className="mt-1 text-xs text-gray-500">Gò Vấp, TP. Hồ Chí Minh</p>
                <p className="mt-2 text-sm font-extrabold text-[#FF6B4A]">{index % 2 ? "4.5 triệu" : "5.0 triệu"} / tháng</p>
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

function CarouselButton({ direction, onClick }: { direction: "left" | "right"; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={direction === "left" ? "Xem phòng tương tự trước" : "Xem phòng tương tự tiếp theo"}
      onClick={onClick}
      className="flex h-9 w-9 items-center justify-center rounded-full border border-[#DCECE4] bg-white text-[#0F5F4A] transition-colors hover:bg-[#E9F7F0]"
    >
      <span className="material-symbols-outlined text-[20px]">{direction === "left" ? "chevron_left" : "chevron_right"}</span>
    </button>
  );
}
