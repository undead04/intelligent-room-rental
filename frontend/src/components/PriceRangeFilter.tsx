interface PriceRangeFilterProps {
  minPrice: number;
  maxPrice: number;
  onMinChange: (value: number) => void;
  onMaxChange: (value: number) => void;
}

const MAX_PRICE = 15;
const STEP = 0.5;

function formatPrice(value: number) {
  return Number.isInteger(value) ? `${value}` : value.toFixed(1);
}

export default function PriceRangeFilter({
  minPrice,
  maxPrice,
  onMinChange,
  onMaxChange,
}: PriceRangeFilterProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-['Plus_Jakarta_Sans'] font-bold text-base text-[#14201C]">Giá thuê</h3>
        <span className="text-xs text-[#8C9B94] font-medium">Đơn vị: triệu / tháng</span>
      </div>

      <div className="text-center py-2">
        <div className="font-['Plus_Jakarta_Sans'] font-extrabold text-2xl tracking-tight text-[#14201C] flex items-center justify-center gap-3">
          <span>{formatPrice(minPrice)}tr</span>
          <span className="text-gray-400 font-normal">—</span>
          <span className="text-[#0F5F4A]">{maxPrice === MAX_PRICE ? "15tr+" : `${formatPrice(maxPrice)}tr`}</span>
        </div>
      </div>

      <div className="relative h-8 flex items-center">
        <div className="absolute left-0 right-0 h-1.5 rounded-full bg-[#DDE9E3]" />
        <div
          className="absolute h-1.5 rounded-full bg-[#0F5F4A]"
          style={{
            left: `${(minPrice / MAX_PRICE) * 100}%`,
            right: `${100 - (maxPrice / MAX_PRICE) * 100}%`,
          }}
        />
        <input
          aria-label="Giá tối thiểu"
          type="range"
          min={0}
          max={MAX_PRICE}
          step={STEP}
          value={minPrice}
          onChange={(event) => onMinChange(Math.min(Number(event.target.value), maxPrice - STEP))}
          className="price-range-input"
        />
        <input
          aria-label="Giá tối đa"
          type="range"
          min={0}
          max={MAX_PRICE}
          step={STEP}
          value={maxPrice}
          onChange={(event) => onMaxChange(Math.max(Number(event.target.value), minPrice + STEP))}
          className="price-range-input"
        />
      </div>

      <div className="grid grid-cols-[1fr,auto,1fr] items-center gap-3">
        <div>
          <label className="block uppercase text-[11px] font-bold text-[#6B7A74] tracking-wider mb-1.5">
            Tối thiểu
          </label>
          <input
            type="text"
            value={`${formatPrice(minPrice)} triệu`}
            readOnly
            className="w-full rounded-2xl border border-[#E8E4DC] px-4 py-2.5 bg-white text-sm font-semibold"
          />
        </div>
        <div className="text-gray-400 font-bold self-end pb-3 text-lg">—</div>
        <div>
          <label className="block uppercase text-[11px] font-bold text-[#6B7A74] tracking-wider mb-1.5">
            Tối đa
          </label>
          <input
            type="text"
            value={maxPrice === MAX_PRICE ? "Không giới hạn" : `${formatPrice(maxPrice)} triệu`}
            readOnly
            className="w-full rounded-2xl border border-[#E8E4DC] px-4 py-2.5 bg-white text-sm font-semibold"
          />
        </div>
      </div>
    </div>
  );
}
