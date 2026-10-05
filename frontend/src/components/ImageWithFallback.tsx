interface ImageWithFallbackProps {
  src: string;
  alt: string;
  fallbackSrc: string;
  className?: string;
}

/** Ảnh tự thay bằng ảnh dự phòng khi URL hỏng, tránh vỡ layout khi tin đăng lỗi ảnh */
export default function ImageWithFallback({
  src,
  alt,
  fallbackSrc,
  className,
}: ImageWithFallbackProps) {
  return (
    <img
      src={src}
      alt={alt}
      className={className}
      onError={(event) => {
        event.currentTarget.onerror = null;
        event.currentTarget.src = fallbackSrc;
      }}
    />
  );
}