import ListingCardSkeleton from "@/components/skeleton/ListingCardSkeleton";
import SkeletonBlock from "@/components/skeleton/SkeletonBlock";

export default function ListingSectionSkeleton() {
  return (
    <section className="mb-10 w-full" aria-busy="true" role="status">
      <div className="mb-4 space-y-2">
        <SkeletonBlock className="h-7 w-64" />
        <SkeletonBlock className="h-4 w-80 max-w-full" />
      </div>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => <ListingCardSkeleton key={index} />)}
      </div>
    </section>
  );
}