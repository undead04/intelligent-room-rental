import Link from "next/link";
import type { BreadcrumbItem } from "@/types";

interface BreadcrumbsProps {
  items: BreadcrumbItem[];
  className?: string;
}

export default function Breadcrumbs({ items, className = "" }: BreadcrumbsProps) {
  return (
    <nav className={`flex items-center gap-1.5 overflow-x-auto text-xs text-gray-500 hide-scrollbar ${className}`} aria-label="Breadcrumb">
      {items.map((item, index) => (
        <span key={`${item.label}-${index}`} className="flex shrink-0 items-center gap-1.5">
          {index > 0 && <span className="material-symbols-outlined text-[14px]">chevron_right</span>}
          {item.href ? (
            <Link href={item.href} className="hover:text-[#0F5F4A]">{item.label}</Link>
          ) : (
            <span className={index === items.length - 1 ? "max-w-[280px] truncate font-semibold text-[#121E1A]" : ""}>
              {item.label}
            </span>
          )}
        </span>
      ))}
    </nav>
  );
}
