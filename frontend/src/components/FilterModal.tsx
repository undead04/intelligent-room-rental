"use client";

import FilterModalBody from "@/components/FilterModalBody";
import { CityDto, RoomTypeDto } from "@/types/dto";
import { SortOptions, FilterValues } from "@/types";

interface FilterModalProps {
  isOpen: boolean;
  provinces: CityDto[];
  roomTypes: RoomTypeDto[];
  sortOptions: SortOptions[];
  initialValues: FilterValues;
  onClose: () => void;
  onApply: (values: FilterValues) => void;
}

export default function FilterModal({ isOpen, ...bodyProps }: FilterModalProps) {
  if (!isOpen) return null;

  // Chỉ mount phần thân khi modal mở: draft bộ lọc được khởi tạo lại từ bộ lọc đang áp dụng
  return <FilterModalBody {...bodyProps} />;
}