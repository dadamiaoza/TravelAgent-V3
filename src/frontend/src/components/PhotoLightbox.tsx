import { useEffect } from "react";
import type { PhotoAsset } from "@/lib/types";

export default function PhotoLightbox({
  photos,
  index,
  alt,
  onClose,
  onIndexChange,
  onUnassign,
}: {
  photos: PhotoAsset[];
  index: number;
  alt?: string;
  onClose: () => void;
  onIndexChange?: (index: number) => void;
  onUnassign?: (photoId: string) => void;
}) {
  const photo = photos[index];
  const src = photo?.preview_url ?? photo?.thumbnail_url;

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowRight" && index < photos.length - 1) {
        onIndexChange?.(index + 1);
      }
      if (event.key === "ArrowLeft" && index > 0) {
        onIndexChange?.(index - 1);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, onClose, onIndexChange, photos.length]);

  if (!photo || !src) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={alt ?? photo.original_filename}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 p-4"
      onClick={(event) => {
        event.stopPropagation();
        onClose();
      }}
    >
      <div
        className="relative max-h-full max-w-4xl"
        onClick={(event) => event.stopPropagation()}
      >
        <img
          src={src}
          alt={alt ?? photo.original_filename}
          className="max-h-[80vh] max-w-full rounded-2xl object-contain shadow-lg"
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-white">
          <p>
            {alt ? `${alt} · ` : ""}
            {index + 1} / {photos.length}
          </p>
          <div className="flex gap-3">
            {photos.length > 1 && (
              <>
                <button
                  type="button"
                  className="min-h-11 rounded-full bg-white/15 px-3 text-white hover:bg-white/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                  disabled={index === 0}
                  onClick={() => onIndexChange?.(index - 1)}
                >
                  上一张
                </button>
                <button
                  type="button"
                  className="min-h-11 rounded-full bg-white/15 px-3 text-white hover:bg-white/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                  disabled={index === photos.length - 1}
                  onClick={() => onIndexChange?.(index + 1)}
                >
                  下一张
                </button>
              </>
            )}
            {onUnassign && (
              <button
                type="button"
                className="min-h-11 text-red-200 hover:underline"
                onClick={() => onUnassign(photo.id)}
              >
                撤销挂载
              </button>
            )}
            <button
              type="button"
              className="min-h-11 rounded-full bg-white px-4 font-medium text-slate-900"
              onClick={onClose}
            >
              关闭
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
