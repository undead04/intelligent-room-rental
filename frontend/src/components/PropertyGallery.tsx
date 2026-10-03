interface PropertyGalleryProps {
  images: string[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}

export default function PropertyGallery({ images, selectedIndex, onSelect }: PropertyGalleryProps) {
  const previous = () => onSelect(selectedIndex > 0 ? selectedIndex - 1 : images.length - 1);
  const next = () => onSelect(selectedIndex < images.length - 1 ? selectedIndex + 1 : 0);

  return (
    <div className="bg-white rounded-2xl p-4 border border-[#E8E4DC] shadow-xs">
      <div className="relative w-full aspect-[16/10] rounded-xl overflow-hidden bg-gray-100 mb-3">
        <img src={images[selectedIndex]} alt="Ảnh phòng trọ Duplex" className="w-full h-full object-cover transition-transform duration-300" />
        <button onClick={previous} aria-label="Ảnh trước" className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/60 text-white flex items-center justify-center hover:bg-black/80 transition-colors shadow-md">
          <span className="material-symbols-outlined text-[20px]">chevron_left</span>
        </button>
        <button onClick={next} aria-label="Ảnh tiếp theo" className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/60 text-white flex items-center justify-center hover:bg-black/80 transition-colors shadow-md">
          <span className="material-symbols-outlined text-[20px]">chevron_right</span>
        </button>
        <div className="absolute bottom-3 left-3 bg-[#0F5F4A] text-white px-3 py-1.5 rounded-full flex items-center gap-1.5 shadow-md text-xs font-semibold">
          <span className="material-symbols-outlined text-[16px]">verified</span>
          <span>Đã kiểm định thực tế 100%</span>
        </div>
        <div className="absolute bottom-3 right-3 bg-black/70 text-white px-3 py-1 rounded-full text-xs font-semibold flex items-center gap-1">
          <span className="material-symbols-outlined text-[14px]">photo_camera</span>
          <span>{selectedIndex + 1} / {images.length}</span>
        </div>
      </div>
      <div className="grid grid-cols-5 gap-2">
        {images.map((image, index) => (
          <button key={image} onClick={() => onSelect(index)} aria-label={`Xem ảnh ${index + 1}`} className={`rounded-xl overflow-hidden aspect-[4/3] border-2 transition-all ${selectedIndex === index ? "border-[#0F5F4A] opacity-100" : "border-transparent opacity-60 hover:opacity-100"}`}>
            <img src={image} alt={`Thumb ${index + 1}`} className="w-full h-full object-cover" />
          </button>
        ))}
      </div>
    </div>
  );
}
