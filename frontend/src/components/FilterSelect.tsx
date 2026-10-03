interface FilterSelectProps {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
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
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-2xl border border-[#E8E4DC] px-4 py-3 bg-[#FAF8F4] font-medium text-sm focus:border-[#0F5F4A] focus:bg-white outline-none disabled:cursor-not-allowed disabled:bg-[#F4F1EA] disabled:text-[#8C9B94]"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}
