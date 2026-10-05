interface IOptions {
  value: number;
  label: string;
}

interface FilterSelectProps {
  label: string;
  value: number | null;
  options: IOptions[];
  onChange: (value: number | null) => void;
  disabled?: boolean;
}

export default function FilterSelect({
  label,
  value,
  options,
  onChange,
  disabled = false,
}: FilterSelectProps) {
  return (
    <div>
      <label className="block uppercase text-[11px] font-bold text-[#6B7A74] tracking-wider mb-1.5">
        {label}
      </label>

      <div className="relative">
        <select
          value={value ?? ""}
          disabled={disabled}
          onChange={(event) => {
            const selectedValue = event.target.value;

            onChange(
              selectedValue === "" ? null : Number(selectedValue)
            );
          }}
          className="custom-select w-full rounded-2xl border border-[#E8E4DC] px-4 py-3 pr-11 bg-[#FAF8F4] font-medium text-sm focus:border-[#0F5F4A] focus:bg-white outline-none disabled:cursor-not-allowed disabled:bg-[#F4F1EA] disabled:text-[#8C9B94]"
        >
          <option value="">Tất cả</option>

          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>

        <span className="material-symbols-outlined pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[20px] text-[#0F5F4A]">
          expand_more
        </span>
      </div>
    </div>
  );
}