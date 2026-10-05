interface SelectOption {
  value: number;
  label: string;
}

interface FilterSelectProps {
  options: SelectOption[];
  value: number | null;
  onChange: (value: number | null) => void;
  /** Ô có nhãn phía trên (bộ lọc trong modal); pill thì bỏ trống */
  label?: string;
  variant?: "field" | "pill";
  /** Nhãn của lựa chọn rỗng; null = không hiện lựa chọn rỗng */
  emptyLabel?: string | null;
}

const VARIANT_STYLES = {
  field: {
    select: "custom-select w-full rounded-2xl border border-[#E8E4DC] px-4 py-3 pr-11 bg-[#FAF8F4] font-medium text-sm focus:border-[#0F5F4A] focus:bg-white outline-none",
    icon: "right-3 text-[20px]",
  },
  pill: {
    select: "custom-select px-4 py-2.5 pr-10 rounded-full bg-[#FAF8F4] border border-[#E8E4DC] text-xs outline-none font-bold text-[#0F5F4A]",
    icon: "right-2.5 text-[18px]",
  },
} as const;

export default function FilterSelect({
  options,
  value,
  onChange,
  label,
  variant = "field",
  emptyLabel = "Tất cả",
}: FilterSelectProps) {
  const styles = VARIANT_STYLES[variant];

  return (
    <div>
      {label && (
        <label className="block uppercase text-[11px] font-bold text-[#6B7A74] tracking-wider mb-1.5">
          {label}
        </label>
      )}

      <div className="relative">
        <select
          value={value ?? ""}
          onChange={(event) => {
            const selectedValue = event.target.value;

            onChange(selectedValue === "" ? null : Number(selectedValue));
          }}
          className={styles.select}
        >
          {emptyLabel !== null && <option value="">{emptyLabel}</option>}

          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>

        <span
          className={`material-symbols-outlined pointer-events-none absolute top-1/2 -translate-y-1/2 text-[#0F5F4A] ${styles.icon}`}
        >
          expand_more
        </span>
      </div>
    </div>
  );
}