type PhotoBadgeProps = {
  thumbnailUrl: string;
  photoCount: number;
  alt?: string;
  onClick?: () => void;
  size?: "small" | "medium";
};

export default function PhotoBadge({
  thumbnailUrl,
  photoCount,
  alt = "已归档照片",
  onClick,
  size = "small",
}: PhotoBadgeProps) {
  const edge = size === "medium" ? "h-14 w-14" : "h-12 w-12";
  const label = `${photoCount} 张照片`;

  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        onClick?.();
      }}
      aria-label={label}
      className={`relative shrink-0 overflow-hidden rounded-xl border border-white shadow-sm ring-1 ring-sky-100 transition duration-200 hover:ring-sky-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500 ${edge}`}
    >
      <img src={thumbnailUrl} alt={alt} className="h-full w-full object-cover" />
      <span className="absolute bottom-0.5 right-0.5 min-w-5 rounded-full bg-sky-600 px-1 text-center text-[10px] font-semibold leading-4 text-white">
        {photoCount}
      </span>
    </button>
  );
}
