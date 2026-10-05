function SkeletonBlock({ className }: { className: string }) {
  return <div className={`animate-pulse rounded-lg bg-[#E8EEE9] ${className}`} />;
}

export function ListingCardSkeleton() {
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

export function ListingSectionSkeleton({ title = true }: { title?: boolean }) {
  return (
    <section className="mb-10 w-full" aria-busy="true" role="status">
      {title && (
        <div className="mb-4 space-y-2">
          <SkeletonBlock className="h-7 w-64" />
          <SkeletonBlock className="h-4 w-80 max-w-full" />
        </div>
      )}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => <ListingCardSkeleton key={index} />)}
      </div>
    </section>
  );
}

export function DetailPageSkeleton() {
  return (
    <main className="mx-auto w-full max-w-[1380px] flex-1 px-4 py-6 lg:px-8" aria-busy="true" role="status">
      <div className="mb-5 flex items-center gap-2">
        <SkeletonBlock className="h-3 w-16" />
        <SkeletonBlock className="h-3 w-3 rounded-full" />
        <SkeletonBlock className="h-3 w-28" />
        <SkeletonBlock className="h-3 w-3 rounded-full" />
        <SkeletonBlock className="h-3 w-40" />
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
      <div className="space-y-6 lg:col-span-8">
        <div className="rounded-2xl border border-[#E8E4DC] bg-white p-4">
          <SkeletonBlock className="aspect-[16/10] w-full rounded-xl" />
          <div className="mt-3 grid grid-cols-5 gap-2">
            {Array.from({ length: 5 }, (_, index) => (
              <SkeletonBlock key={index} className="aspect-[4/3] rounded-xl" />
            ))}
          </div>
        </div>
        <div className="space-y-4 rounded-2xl border border-[#E8E4DC] bg-white p-6">
          <div className="flex gap-2">
            <SkeletonBlock className="h-6 w-28" />
            <SkeletonBlock className="h-6 w-24" />
          </div>
          <SkeletonBlock className="h-8 w-11/12" />
          <SkeletonBlock className="h-4 w-8/12" />
          <SkeletonBlock className="h-16 w-full" />
        </div>
      </div>
      <div className="space-y-4 lg:col-span-4">
        <div className="space-y-5 rounded-2xl border border-[#E8E4DC] bg-white p-6">
          <div className="flex items-center gap-3">
            <SkeletonBlock className="h-14 w-14 rounded-full" />
            <div className="flex-1 space-y-2">
              <SkeletonBlock className="h-4 w-32" />
              <SkeletonBlock className="h-3 w-44" />
              <SkeletonBlock className="h-3 w-24" />
            </div>
          </div>
          <SkeletonBlock className="h-12 w-full rounded-full" />
          <SkeletonBlock className="h-12 w-full rounded-full" />
          <SkeletonBlock className="h-10 w-full rounded-full" />
        </div>
        <SkeletonBlock className="h-28 w-full rounded-2xl" />
      </div>
      </div>
      <p className="mt-6 text-center text-xs font-medium text-[#6F7974]">Đang tải thông tin phòng...</p>
    </main>
  );
}

export function PriceStatsSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" role="status">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
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
