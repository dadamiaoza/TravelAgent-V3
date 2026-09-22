import { useEffect, useRef, type PointerEvent } from "react";
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
  const buttonRef = useRef<HTMLButtonElement>(null);
  const ring =
    bead.kind === "visit"
      ? selected
        ? "border-amber-600 ring-2 ring-amber-400 ring-offset-2"
        : "border-amber-400"
      : bead.kind === "unsorted"
        ? selected
          ? "border-slate-600 ring-2 ring-slate-400 ring-offset-2"
          : "border-dashed border-slate-400"
        : selected
          ? "border-sky-700 ring-2 ring-sky-500 ring-offset-2"
          : "border-sky-500";
  const currentColor =
    bead.kind === "visit" ? "text-amber-800" : bead.kind === "unsorted" ? "text-slate-800" : "text-sky-800";
  const src = bead.thumbUrl;

  useEffect(() => {
    if (!selected) return;
    buttonRef.current?.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  }, [selected]);

  return (
    <button
      ref={buttonRef}
      type="button"
      aria-current={selected ? "true" : undefined}
      aria-pressed={selected}
      onClick={onSelect}
      className="flex w-[4.75rem] shrink-0 flex-col items-center gap-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500"
    >
      <span
        className={`relative flex items-center justify-center overflow-hidden rounded-full border-2 bg-white ${
          selected ? `h-14 w-14 shadow-md ${ring}` : `h-12 w-12 shadow-sm ${ring}`
        }`}
      >
        {src ? (
          <img src={src} alt="" className="h-full w-full object-cover" />
        ) : (
          <span className="px-1 text-center text-[10px] font-semibold leading-tight text-slate-500">
            {bead.label.slice(0, 4)}
          </span>
        )}
        {selected && (
          <span
            className={`absolute inset-x-0 top-0 py-0.5 text-center text-[9px] font-semibold leading-3 text-white ${
              bead.kind === "visit" ? "bg-amber-600/90" : bead.kind === "unsorted" ? "bg-slate-700/90" : "bg-sky-600/90"
            }`}
          >
            当前
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
      <span
        className={`line-clamp-2 text-center text-[11px] leading-tight ${
          selected ? `font-semibold ${currentColor}` : "text-slate-700"
        }`}
      >
        {bead.label}
      </span>
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
  onDismissVisitStop,
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
  onDismissVisitStop?: () => void;
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
              {mode === "album" && onDismissVisitStop && (
                <button
                  type="button"
                  className="mt-0.5 text-xs text-red-600 hover:underline"
                  onClick={onDismissVisitStop}
                >
                  去掉这个停留
                </button>
              )}
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
                        ? "这些照片还没有地点。点开已有照片可改挂到计划点。"
                        : selectedBeadId?.startsWith("visit:")
                          ? "这个停留已经没有照片。可以去掉它，不会改计划。"
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
