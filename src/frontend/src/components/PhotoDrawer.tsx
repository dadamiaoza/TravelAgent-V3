import type { PhotoAsset } from "@/lib/types";

export default function PhotoDrawer({
  title,
  photos,
  onClose,
  onPhotoClick,
}: {
  title: string;
  photos: PhotoAsset[];
  onClose: () => void;
  onPhotoClick: (photoId: string) => void;
}) {
  return (
    <aside
      className="pointer-events-auto absolute inset-x-0 bottom-0 z-20 max-h-[42vh] overflow-hidden rounded-t-3xl border border-white/70 bg-white/90 shadow-[0_-8px_40px_rgba(15,23,42,0.12)] backdrop-blur-md"
      aria-label={title}
    >
      <div className="flex items-center justify-between px-4 pb-2 pt-3">
        <div>
          <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-slate-300 sm:hidden" />
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
        </div>
        <button
          type="button"
          className="min-h-11 min-w-11 rounded-full text-sm text-slate-500 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500"
          aria-label="关闭照片墙"
          onClick={onClose}
        >
          关闭
        </button>
      </div>
      <div className="max-h-[34vh] overflow-y-auto px-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        {photos.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-500">
            这个地点还没有归档照片。可在行程页上传或改挂。
          </p>
        ) : (
          <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-5">
            {photos.map((photo) => {
              const src = photo.thumbnail_url ?? photo.preview_url;
              if (!src) return null;
              return (
                <li key={photo.id}>
                  <button
                    type="button"
                    className="block w-full overflow-hidden rounded-2xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500"
                    onClick={() => onPhotoClick(photo.id)}
                  >
                    <img
                      src={src}
                      alt={title}
                      loading="lazy"
                      className="aspect-square w-full object-cover"
                    />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
