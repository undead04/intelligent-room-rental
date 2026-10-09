import type { ListingDetailDto } from "@/types/dto";
import Breadcrumbs from "@/components/Breadcrumbs";
import type { BreadcrumbItem } from "@/types";

interface DetailBreadcrumbProps {
  listing: ListingDetailDto | null;
  title: string;
}

export default function DetailBreadcrumb({ listing, title }: DetailBreadcrumbProps) {
  const items: BreadcrumbItem[] = [
    { label: "Trang chủ", href: "/" },
    { label: listing?.city?.name || "Phòng trọ", href: "/tim-kiem" },
    ...(listing?.district?.name
      ? [{ label: listing.district.name, href: `/tim-kiem?district_id=${listing.district.id}` }]
      : []),
    ...(listing?.ward?.name ? [{ label: listing.ward.name, href: `/tim-kiem?city_id=${listing.city?.id}&district_id=${listing.district?.id}&ward_id=${listing.ward.id}` }] : []),
    { label: title },
  ];

  return (
    <div className="w-full border-b border-[#E8E4DC] bg-white">
      <div className="mx-auto max-w-[1500px] px-4 py-3 lg:px-8">
        <Breadcrumbs items={items} />
      </div>
    </div>
  );
}
