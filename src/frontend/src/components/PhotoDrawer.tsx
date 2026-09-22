import { useRef, type PointerEvent } from "react";
import type { PhotoAsset } from "@/lib/types";
import type { SpineBead } from "@/lib/recallSpine";

function BeadButton({
  bead,
  selected,
  onSelect,
}: {
  bead: SpineBead;
  selected: boolean;
  onSelect: () => void;
}) {
  const ring =
    bead.kind === "visit"
      ? selected
        ? "border-amber-500 ring-2 ring-amber-200"
        : "border-amber-400"
      : bead.kind === "unsorted"
        ? selected
          ? "border-slate-500 ring-2 ring-slate-300"
          : "border-dashed border-slate-400"
        : selected
          ? "border-sky-600 ring-2 ring-sky-200"
          : "border-sky-500";
  const src = bead.thumbUrl;
  return (
    <button
      type="button"
      onClick={onSelect}
      className="flex w-[4.5rem] shrink-0 flex-col items-center gap-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500"
    >
      <span
        className={`relative flex h-12 w-12 items-center justify-center overflow-hidden rounded-full border-2 bg-white shadow-sm ${ring}`}
      >
        {src ? (
          <img src={src} alt="" className="h-full w-full object-cover" />
        ) : (
          <span className="px-1 text-center text-[10px] font-semibold leading-tight text-slate-500">
            {bead.label.slice(0, 4)}
          </span>
        )}
        <span
          className={`absolute -bottom-1 -right-1 min-w-5 rounded-full px-1 text-[10px] font-bold leading-4 text-white ${
            bead.kind === "visit" ? "bg-amber-500" : bead.kind === "unsorted" ? "bg-slate-500" : "bg-sky-600"
          }`}
        >
          {bead.photoCount}
        </span>
      </span>
      <span className="line-clamp-2 text-center text-[11px] leading-tight text-slate-700">{bead.label}</span>
      {bead.caption && (
        <span className="text-[10px] leading-tight text-slate-400">{bead.caption}</span>
      )}
    </button>
  );
}

export default function PhotoDrawer({
  open,
  onOpenChange,
  mode,
  dayLabel,
  title,
  beads,
  selectedBeadId,
  onSelectBead,
  onBack,
  photos,
  onPhotoClick,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: "spine" | "album";
  dayLabel: string;
  title: string;
  beads: SpineBead[];
  selectedBeadId: string | null;
  onSelectBead: (bead: SpineBead) => void;
  onBack: () => void;
  photos: PhotoAsset[];
  onPhotoClick: (photoId: string) => void;
}) {
  const dragRef = useRef<{ startY: number; moved: boolean } | null>(null);

  function onHandlePointerDown(event: PointerEvent<HTMLButtonElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { startY: event.clientY, moved: false };
  }

  function onHandlePointerMove(event: PointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current;
    if (!drag) return;
    if (Math.abs(event.clientY - drag.startY) > 8) drag.moved = true;
  }

  function onHandlePointerUp(event: PointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current;
    dragRef.current = null;
    if (!drag) return;
    const delta = event.clientY - drag.startY;
    if (drag.moved) {
      if (delta < -40) onOpenChange(true);
      else if (delta > 40) onOpenChange(false);
      return;
    }
    onOpenChange(!open);
  }

  return (
    <aside
      className={`pointer-events-auto absolute inset-x-0 bottom-0 z-20 overflow-hidden rounded-t-3xl border border-white/70 bg-white/92 shadow-[0_-8px_40px_rgba(15,23,42,0.12)] backdrop-blur-md transition-[height] duration-200 ${
        open ? "h-[min(42vh,28rem)]" : "h-14"
      }`}
      aria-label={open ? title || dayLabel : "当天路线节点"}
    >
      <button
        type="button"
        className="flex w-full touch-none flex-col items-center pt-2 select-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500"
        aria-expanded={open}
        aria-label={open ? "收起当天路线" : "打开当天路线"}
        onPointerDown={onHandlePointerDown}
        onPointerMove={onHandlePointerMove}
        onPointerUp={onHandlePointerUp}
      >
        <span className="h-1 w-10 rounded-full bg-slate-300" />
        {!open && (
          <span className="mt-1.5 text-xs text-slate-600">
            {dayLabel} · 上拉查看路线节点
          </span>
        )}
      </button>

      {open && (
        <div className="flex h-[calc(100%-1.75rem)] flex-col">
          <div className="flex items-center justify-between px-4 pb-1">
            <div className="min-w-0">
              {mode === "album" ? (
                <button
                  type="button"
                  className="text-xs text-sky-700 hover:underline"
                  onClick={onBack}
                >
                  返回当天路线
                </button>
              ) : (
                <p className="text-xs text-slate-500">{dayLabel}</p>
              )}
              <h2 className="truncate text-base font-semibold text-slate-900">
                {mode === "album" ? title : "这一天的地点"}
              </h2>
            </div>
            <button
              type="button"
              className="min-h-11 min-w-11 rounded-full text-sm text-slate-500 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500"
              aria-label="收起"
              onClick={() => onOpenChange(false)}
            >
              收起
            </button>
          </div>

          {mode === "spine" ? (
            <div className="min-h-0 flex-1 overflow-x-auto overflow-y-hidden px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
              {beads.length === 0 ? (
                <p className="py-6 text-center text-sm text-slate-500">这一天还没有地点。</p>
              ) : (
                <div className="relative flex min-w-max items-center gap-3 py-12">
                  <div className="absolute left-2 right-2 top-1/2 h-0.5 -translate-y-1/2 bg-slate-200" />
                  {beads.map((bead) => (
                    <div
                      key={bead.id}
                      className={`relative z-10 ${
                        bead.lane === "above"
                          ? "-translate-y-10"
                          : bead.lane === "below"
                            ? "translate-y-10"
                            : ""
                      }`}
                    >
                      <BeadButton
                        bead={bead}
                        selected={selectedBeadId === bead.id}
                        onSelect={() => onSelectBead(bead)}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
              {photos.length === 0 ? (
                <p className="py-8 text-center text-sm text-slate-500">
                  {selectedBeadId?.startsWith("unsorted")
                    ? "没有未归类的照片。"
                    : "这个地点还没有归档照片。点开已有照片可改挂或删除。"}
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
          )}
        </div>
      )}
    </aside>
  );
}
