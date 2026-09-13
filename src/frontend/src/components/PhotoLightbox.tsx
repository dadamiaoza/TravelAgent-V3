import { useEffect } from "react";
import type { PhotoAsset } from "@/lib/types";

export default function PhotoLightbox({
  photos,
  index,
  alt,
  onClose,
  onIndexChange,
  items,
  onReassign,
  onUnassign,
  onDelete,
}: {
  photos: PhotoAsset[];
  index: number;
  alt?: string;
  onClose: () => void;
  onIndexChange?: (index: number) => void;
  items?: { id: string; label: string }[];
  onReassign?: (photoId: string, itemId: string) => void;
  onUnassign?: (photoId: string) => void;
  onDelete?: (photoId: string) => void;
}) {
  const photo = photos[index];
  const src = photo?.preview_url ?? photo?.thumbnail_url;
  const currentItemId = photo?.assignment?.item_id ?? "";
  const otherItems = (items ?? []).filter((item) => item.id !== currentItemId);
  const canCorrect = Boolean(onReassign || onUnassign || onDelete);

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
          <div className="flex flex-wrap items-center justify-end gap-2">
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
            {onReassign && otherItems.length > 0 && (
              <select
                key={photo.id}
                className="min-h-11 rounded-full border-0 bg-white px-3 text-sm text-slate-900"
                value=""
                aria-label="改挂到其他地点"
                onChange={(event) => {
                  const itemId = event.target.value;
                  if (!itemId) return;
                  onReassign(photo.id, itemId);
                }}
              >
                <option value="">改挂到…</option>
                {otherItems.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            )}
            {onUnassign && (
              <button
                type="button"
                className="min-h-11 rounded-full bg-white/15 px-3 text-white hover:bg-white/25"
                onClick={() => onUnassign(photo.id)}
              >
                从这里拿掉
              </button>
            )}
            {onDelete && (
              <button
                type="button"
                className="min-h-11 rounded-full px-3 text-red-200 hover:bg-red-500/20 hover:underline"
                onClick={() => {
                  if (window.confirm("确定删除这张照片？原图会从这次行程里去掉。")) {
                    onDelete(photo.id);
                  }
                }}
              >
                删除
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
        {canCorrect && (
          <p className="mt-2 text-right text-[11px] text-white/70">
            改挂和删除只动这张照片，不会改行程计划。
          </p>
        )}
      </div>
    </div>
  );
}
