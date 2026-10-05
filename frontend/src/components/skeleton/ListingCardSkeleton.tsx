import SkeletonBlock from "@/components/skeleton/SkeletonBlock";

export default function ListingCardSkeleton() {
  return (
    <div className="rounded-[20px] border border-[#ECE8E0] bg-white p-3">
      <SkeletonBlock className="aspect-[4/3] w-full rounded-[16px]" />
      <div className="space-y-3 px-1 pt-3">
        <div className="flex justify-between">
          <SkeletonBlock className="h-5 w-24" />
          <SkeletonBlock className="h-4 w-16" />
        </div>
        <SkeletonBlock className="h-4 w-11/12" />
        <SkeletonBlock className="h-3 w-8/12" />
        <div className="flex justify-between border-t border-gray-100 pt-3">
          <SkeletonBlock className="h-5 w-24" />
          <SkeletonBlock className="h-4 w-16" />
        </div>
      </div>
    </div>
  );
}