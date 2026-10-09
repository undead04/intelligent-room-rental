"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import ListingCard from "@/components/ListingCard";
import type { ListingCardData } from "@/types";

interface SimilarListingsProps {
  listings: ListingCardData[];
}

export default function SimilarListings({ listings }: SimilarListingsProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [canPrev, setCanPrev] = useState(false);
  const [canNext, setCanNext] = useState(false);

  const updateButtons = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;
    const maxScroll = track.scrollWidth - track.clientWidth;
    setCanPrev(track.scrollLeft > 8);
    setCanNext(track.scrollLeft < maxScroll - 8);
  }, []);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;

    updateButtons();
    track.addEventListener("scroll", updateButtons, { passive: true });

    // cập nhật khi đổi kích thước màn hình hoặc đổi số lượng card
    const observer = new ResizeObserver(updateButtons);
    observer.observe(track);

    return () => {
      track.removeEventListener("scroll", updateButtons);
      observer.disconnect();
    };
  }, [updateButtons, listings.length]);

  if (listings.length === 0) return null;

  const scrollByPage = (direction: 1 | -1) => {
    const track = trackRef.current;
    if (!track) return;
    track.scrollBy({ left: direction * track.clientWidth * 0.8, behavior: "smooth" });
  };

  const navBtn =
    "w-10 h-10 rounded-full border border-[#E8E4DC] bg-white text-[#0F5F4A] flex items-center justify-center shadow-xs transition-colors " +
    "hover:bg-[#E6F4EE] disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-white";

  return (
    <section className="mt-10">
      <div className="flex items-end justify-between gap-4 mb-4">
        <div>
          <h2 className="font-['Plus_Jakarta_Sans'] font-extrabold text-xl sm:text-2xl text-[#121E1A]">
            Phòng trọ tương tự
          </h2>
          <p className="text-xs sm:text-sm text-gray-500 mt-1">
            Cùng khu vực, cùng loại phòng và mức giá tương đương
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => scrollByPage(-1)}
            disabled={!canPrev}
            aria-label="Xem phòng trước"
            className={navBtn}
          >
            <span className="material-symbols-outlined text-[20px]">chevron_left</span>
          </button>
          <button
            type="button"
            onClick={() => scrollByPage(1)}
            disabled={!canNext}
            aria-label="Xem phòng tiếp theo"
            className={navBtn}
          >
            <span className="material-symbols-outlined text-[20px]">chevron_right</span>
          </button>
        </div>
      </div>

      <div
        ref={trackRef}
        className="hide-scrollbar flex items-stretch gap-6 overflow-x-auto snap-x snap-mandatory scroll-px-1 px-1 pt-2 pb-3"
      >
        {listings.map((item) => (
          <div
            key={item.id}
            className="flex w-[85%] shrink-0 snap-start sm:w-[calc((100%-1.5rem)/2)] md:w-[calc((100%-3rem)/3)] lg:w-[calc((100%-4.5rem)/4)] [&>*]:h-full [&>*]:w-full"
          >
            <ListingCard item={item} />
          </div>
        ))}
      </div>
    </section>
  );
}