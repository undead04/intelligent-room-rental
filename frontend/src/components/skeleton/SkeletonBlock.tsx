interface SkeletonBlockProps {
  className: string;
}

export default function SkeletonBlock({ className }: SkeletonBlockProps) {
  return <div className={`animate-pulse rounded-lg bg-[#E8EEE9] ${className}`} />;
}