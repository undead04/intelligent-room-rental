"use client";

import { useState } from "react";
import AmenityChips from "@/components/AmenityChips";
import FilterSelect from "@/components/FilterSelect";
import PriceRangeFilter from "@/components/PriceRangeFilter";

export interface FilterValues {
  province: string;
  district: string;
  ward: string;
  roomType: string;
  listingType: string;
  publisher: string;
  minPrice: string;
  maxPrice: string;
  source: string;
  amenities: string[];
  sort: string;
}

interface FilterModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApply?: (filters: FilterValues) => void;
}

export default function FilterModal({ isOpen, onClose, onApply }: FilterModalProps) {
  const [province, setProvince] = useState("TP. Hồ Chí Minh");
  const [district, setDistrict] = useState("Quận 1");
  const [ward, setWard] = useState("Tất cả phường/xã");
  const [roomType, setRoomType] = useState("Tất cả");
  const [listingType, setListingType] = useState("Tất cả");
  const [publisher, setPublisher] = useState("Tất cả");
  const [minPrice, setMinPrice] = useState(0);
  const [maxPrice, setMaxPrice] = useState(15);
  const [source, setSource] = useState("Tất cả nguồn");
  const [sort, setSort] = useState("Tin mới nhất");

  const [amenities, setAmenities] = useState<string[]>([
    "Có máy lạnh",
    "Không chung chủ",
  ]);

  const toggleAmenity = (name: string) => {
    if (amenities.includes(name)) {
      setAmenities(amenities.filter((a) => a !== name));
    } else {
      setAmenities([...amenities, name]);
    }
  };

  const amenityOptions = [
    "Có máy lạnh",
    "Giờ tự do 24/7",
    "Không chung chủ",
    "Gác lửng",
    "Ban công / Cửa sổ lớn",
    "Có máy giặt chung",
    "Cho nuôi thú cưng",
    "Có thang máy",
    "Bảo vệ 24/7",
  ];

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0F201C]/60 backdrop-blur-sm p-4 sm:p-6 animate-in fade-in duration-200">
      <div className="w-full max-w-[720px] bg-white rounded-[28px] shadow-[0_24px_60px_-12px_rgba(15,95,74,0.2)] border border-[#E8E4DC] overflow-hidden flex flex-col max-h-[92vh]">
        {/* Header */}
        <div className="h-[72px] px-7 border-b border-[#F0ECE4] flex items-center justify-between shrink-0 bg-white relative">
          <button
            onClick={onClose}
            aria-label="Đóng bộ lọc"
            className="w-10 h-10 rounded-full flex items-center justify-center hover:bg-[#FAF8F4] text-[#14201C] transition-colors focus:outline-none"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
          <h2 className="font-['Plus_Jakarta_Sans'] font-extrabold text-xl text-[#14201C] absolute left-1/2 -translate-x-1/2 tracking-tight">
            Bộ lọc tìm kiếm
          </h2>
          <button
            onClick={() => {
              setProvince("TP. Hồ Chí Minh");
              setDistrict("Quận 1");
              setWard("Tất cả phường/xã");
              setRoomType("Tất cả");
              setListingType("Tất cả");
              setPublisher("Tất cả");
              setMinPrice(0);
              setMaxPrice(15);
              setSource("Tất cả nguồn");
              setSort("Tin mới nhất");
              setAmenities([]);
            }}
            className="text-xs text-[#0F5F4A] hover:underline font-semibold"
          >
            Đặt lại
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-7 py-6 space-y-6">
          {/* SECTION 1: Khu vực */}
          <div className="space-y-3.5">
            <h3 className="font-['Plus_Jakarta_Sans'] font-bold text-base text-[#14201C] flex items-center justify-between">
              <span>Khu vực</span>
              <span className="text-xs text-[#0F5F4A] font-semibold">{province}</span>
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
              <FilterSelect
                label="Tỉnh / Thành"
                value={province}
                onChange={setProvince}
                options={["TP. Hồ Chí Minh", "Hà Nội", "Đà Nẵng", "Bình Dương"]}
              />
              <FilterSelect
                label="Quận / Huyện"
                value={district}
                onChange={setDistrict}
                options={["Quận 1", "Quận 7", "Bình Thạnh", "Gò Vấp", "TP. Thủ Đức", "Tân Bình"]}
              />
              <FilterSelect
                label="Phường / Xã"
                value={ward}
                onChange={setWard}
                options={["Tất cả phường/xã", "Phường Bến Nghé", "Phường Đa Kao", "Phường 5"]}
              />
            </div>
          </div>

          <div className="border-t border-[#F0ECE4]" />

          {/* SECTION 2: Thuộc tính phòng & Tin đăng */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
            <FilterSelect label="Loại phòng" value={roomType} onChange={setRoomType} options={["Tất cả", "Phòng trọ / KTX", "Căn hộ dịch vụ", "Chung cư mini", "Nhà nguyên căn", "Duplex / Gác lửng"]} />
            <FilterSelect label="Loại tin" value={listingType} onChange={setListingType} options={["Tất cả", "Cho thuê phòng", "Tìm người ở ghép", "Sang nhượng trọ"]} />
            <FilterSelect label="Người đăng" value={publisher} onChange={setPublisher} options={["Tất cả", "Chủ nhà trực tiếp", "Môi giới chuyên nghiệp", "Homigo Quản lý"]} />
          </div>

          <div className="border-t border-[#F0ECE4]" />

          {/* SECTION 3: Giá thuê */}
          <PriceRangeFilter
            minPrice={minPrice}
            maxPrice={maxPrice}
            onMinChange={setMinPrice}
            onMaxChange={setMaxPrice}
          />

          <div className="border-t border-[#F0ECE4]" />

          {/* SECTION 4: Nguồn tin & Sắp xếp */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            <FilterSelect label="Nguồn tin" value={source} onChange={setSource} options={["Tất cả nguồn", "Homigo Verified (Xác thực 100%)", "Chợ Tốt", "Người thuê nhượng lại"]} />
            <FilterSelect label="Sắp xếp" value={sort} onChange={setSort} options={["Tin mới nhất", "Giá: Thấp đến cao", "Giá: Cao đến thấp", "Gần trường ĐH / Trung tâm nhất"]} />
          </div>

          <div className="border-t border-[#F0ECE4]" />

          {/* SECTION 5: Tiện ích nổi bật */}
          <AmenityChips options={amenityOptions} selected={amenities} onToggle={toggleAmenity} />
        </div>

        {/* Footer */}
        <div className="h-20 px-7 border-t border-[#F0ECE4] bg-white flex items-center justify-between shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="px-6 py-3 rounded-full border border-[#E8E4DC] text-sm font-semibold text-[#14201C] hover:bg-[#FAF8F4]"
          >
            Hủy bỏ
          </button>
          <button
            type="button"
            onClick={() => {
              onApply?.({
                province,
                district,
                ward,
                roomType,
                listingType,
                publisher,
                minPrice: String(minPrice),
                maxPrice: String(maxPrice),
                source,
                amenities,
                sort,
              });
              onClose();
            }}
            className="px-8 py-3 rounded-full bg-[#0F5F4A] hover:bg-[#004635] text-white text-sm font-bold shadow-md transition-all"
          >
            Áp dụng bộ lọc (1.240 kết quả)
          </button>
        </div>
      </div>
    </div>
  );
}
