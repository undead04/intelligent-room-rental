import SkeletonBlock from "@/components/skeleton/SkeletonBlock";

export default function PriceStatsSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" role="status">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }, (_, index) => (
          <div key={index} className="rounded-2xl border border-[#E8E4DC] bg-white p-5">
            <SkeletonBlock className="mb-4 h-4 w-24" />
            <SkeletonBlock className="h-8 w-32" />
          </div>
        ))}
      </div>
      <div className="overflow-hidden rounded-2xl border border-[#E8E4DC] bg-white p-5">
        <SkeletonBlock className="mb-5 h-6 w-56" />
        <div className="space-y-4">
          {Array.from({ length: 5 }, (_, index) => (
            <SkeletonBlock key={index} className="h-10 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}