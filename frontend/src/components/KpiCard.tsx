interface KpiCardProps {
  label: string;
  value: string;
  icon: string;
  footer: React.ReactNode;
  unit?: string;
  tone?: "emerald" | "coral";
  compactValue?: boolean;
}

const TONE_STYLES = {
  emerald: { icon: "bg-[#E6F4EE] text-[#0F5F4A]", value: "text-[#0F5F4A]" },
  coral: { icon: "bg-[#FFF0ED] text-[#FF6B4A]", value: "text-[#FF6B4A]" },
} as const;

export default function KpiCard({
  label,
  value,
  icon,
  footer,
  unit,
  tone = "emerald",
  compactValue = false,
}: KpiCardProps) {
  const styles = TONE_STYLES[tone];

  return (
    <div className="bg-white rounded-2xl p-5 border border-[#E8E4DC] shadow-xs flex flex-col justify-between">
      <div className="flex items-start justify-between">
        <div>
          <span className="text-xs uppercase font-bold text-gray-400 tracking-wider">{label}</span>
          <div className="flex items-baseline gap-1 mt-1">
            <span
              className={`font-['Plus_Jakarta_Sans'] font-extrabold ${styles.value} ${
                compactValue ? "text-2xl" : "text-3xl"
              }`}
            >
              {value}
            </span>
            {unit && <span className="text-xs text-gray-500">{unit}</span>}
          </div>
        </div>
        <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${styles.icon}`}>
          <span className="material-symbols-outlined text-[24px]">{icon}</span>
        </div>
      </div>
      <div className="flex items-center gap-2 mt-4 pt-3 border-t border-gray-100">{footer}</div>
    </div>
  );
}