import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { PhotoAsset, Trip } from "@/lib/types";
import {
  useBatchAssignPhotos,
  useDeletePhoto,
  usePatchPhotoAssignment,
  usePatchVisitStop,
  useTripPhotos,
  useUploadTripPhotos,
} from "@/hooks/useTripPhotos";
import PhotoLightbox from "@/components/PhotoLightbox";

function isPending(photo: PhotoAsset): boolean {
  const assignment = photo.assignment;
  if (!assignment) return true;
  if (assignment.is_confirmed) return false;
  if (assignment.visit_stop_id && (assignment.visit_stop_status === "suggested" || assignment.visit_stop_status === "confirmed")) {
    return false;
  }
  return assignment.item_id == null || assignment.confidence < 0.85;
}

function neighborHintLabel(photo: PhotoAsset): string | null {
  const assignment = photo.assignment;
  if (assignment?.assignment_type !== "batch_neighbor") return null;
  const evidence = assignment.evidence ?? {};
  const fromEvidence = typeof evidence.poi_name === "string" ? evidence.poi_name.trim() : "";
  const name = fromEvidence || assignment.visit_stop_name || "";
  return name ? `邻图建议：${name}（需确认）` : "邻图建议（需确认）";
}

export default function PhotoArchivePanel({ trip }: { trip: Trip }) {
  const { photos, visitStops } = useTripPhotos(trip.id);
  const upload = useUploadTripPhotos(trip.id);
  const patch = usePatchPhotoAssignment(trip.id);
  const patchStop = usePatchVisitStop(trip.id);
  const batch = useBatchAssignPhotos(trip.id);
  const remove = useDeletePhoto(trip.id);
  const [selected, setSelected] = useState<string[]>([]);
  const [preview, setPreview] = useState<PhotoAsset | null>(null);
  const [visitStopsOpen, setVisitStopsOpen] = useState(false);
  const items = useMemo(
    () =>
      (trip.days ?? []).flatMap((day) =>
        (day.items ?? []).map((item) => ({
          id: item.id,
          label: `Day ${day.day_index} · ${item.poi_name}`,
        })),
      ),
    [trip.days],
  );

  const pending = (photos.data ?? []).filter(isPending);
  const suggestedStops = (visitStops.data ?? []).filter((stop) => stop.status === "suggested");
  const confirmedVisitStops = (visitStops.data ?? []).filter((stop) => stop.status === "confirmed");

  function onFiles(list: FileList | null, itemId?: string) {
    if (!list?.length) return;
    upload.mutate({ files: list, itemId });
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">旅行照片</h2>
          <p className="text-xs text-gray-500">
            在这里上传、确认建议停留。看拍摄日足迹请到
            <Link to={`/trips/${trip.id}/map`} className="mx-0.5 text-sky-700 hover:underline">
              回忆
            </Link>
            ，不会改写行程节点。微信图请待确认或从某个地点「上传到这里」。若和带地点的原图同一批上传，会给出邻图建议，仍需确认。
          </p>
        </div>
        <label className="cursor-pointer rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700">
          {upload.isPending ? "处理中…" : "批量上传"}
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            multiple
            className="hidden"
            disabled={upload.isPending}
            onChange={(event) => {
              onFiles(event.target.files);
              event.target.value = "";
            }}
          />
        </label>
      </div>
      {upload.isError && (
        <p className="mb-2 text-xs text-red-600">{(upload.error as Error).message}</p>
      )}
      <p className="text-sm text-gray-600">
        共 {(photos.data ?? []).length} 张
        {suggestedStops.length > 0 ? ` · ${suggestedStops.length} 处建议停留` : ""}
        {confirmedVisitStops.length > 0 ? ` · ${confirmedVisitStops.length} 处计划外停留` : ""}
        {pending.length > 0 ? ` · ${pending.length} 张待确认` : ""}
      </p>

      {suggestedStops.length > 0 && (
        <div className="mt-3 space-y-2 rounded-md border border-sky-200 bg-sky-50 p-3">
          <p className="text-sm font-medium text-sky-900">建议停留（计划外）</p>
          <ul className="space-y-3">
            {suggestedStops.map((stop) => (
              <li key={stop.id} className="rounded border border-sky-100 bg-white p-2">
                <p className="text-sm font-medium text-gray-900">{stop.place_name}</p>
                <p className="text-xs text-gray-500">
                  {stop.photo_count} 张
                  {stop.linked_item_name ? ` · 可能是计划里的「${stop.linked_item_name}」` : ""}
                </p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {stop.photos.slice(0, 6).map((photo) =>
                    photo.thumbnail_url ? (
                      <button
                        key={photo.id}
                        type="button"
                        onClick={() => setPreview(photo)}
                      >
                        <img src={photo.thumbnail_url} alt="" className="h-12 w-12 rounded object-cover" />
                      </button>
                    ) : null,
                  )}
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="rounded bg-sky-600 px-2 py-1 text-xs text-white hover:bg-sky-700"
                    onClick={() => patchStop.mutate({ stopId: stop.id, action: "confirm" })}
                  >
                    确认新地点
                  </button>
                  <select
                    className="rounded border border-gray-300 px-2 py-1 text-xs"
                    defaultValue=""
                    onChange={(event) => {
                      if (!event.target.value) return;
                      patchStop.mutate({
                        stopId: stop.id,
                        action: "attach_item",
                        itemId: event.target.value,
                      });
                    }}
                  >
                    <option value="">改挂到计划节点…</option>
                    {items.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="text-xs text-gray-500 hover:underline"
                    onClick={() => patchStop.mutate({ stopId: stop.id, action: "dismiss" })}
                  >
                    忽略
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {confirmedVisitStops.length > 0 && (
        <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3">
          <button
            type="button"
            className="flex w-full items-center justify-between gap-2 text-left"
            aria-expanded={visitStopsOpen}
            onClick={() => setVisitStopsOpen((open) => !open)}
          >
            <span className="flex items-center gap-2">
              <span className="text-sm font-medium text-slate-800">计划外停留</span>
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                {confirmedVisitStops.length} 个节点
              </span>
            </span>
            <span className="text-xs text-slate-500">{visitStopsOpen ? "收起" : "展开"}</span>
          </button>
          {visitStopsOpen && (
            <>
              <p className="mt-2 text-xs text-slate-500">挂错了也可以去掉。照片会回到未归类，不会改行程计划。</p>
              <ul className="mt-2 max-h-[13.25rem] space-y-2 overflow-y-auto overscroll-contain pr-1">
                {confirmedVisitStops.map((stop) => (
                  <li key={stop.id} className="flex min-h-9 items-center justify-between gap-2 rounded border border-slate-100 bg-white px-2 py-1.5">
                    <p className="text-sm text-gray-900">
                      {stop.place_name}
                      <span className="ml-1 text-xs text-slate-500">{stop.photo_count} 张</span>
                    </p>
                    <button
                      type="button"
                      className="shrink-0 text-xs text-red-600 hover:underline"
                      onClick={(event) => {
                        event.stopPropagation();
                        const extra = stop.photo_count > 0 ? "上面的照片会回到未归类，" : "";
                        if (!window.confirm(`去掉「${stop.place_name}」？${extra}不会改行程计划。`)) return;
                        patchStop.mutate({ stopId: stop.id, action: "dismiss" });
                      }}
                    >
                      去掉
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {pending.length > 0 && (
        <div className="mt-3 space-y-2 rounded-md border border-amber-200 bg-amber-50 p-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-amber-900">待确认</p>
            {selected.length > 0 && items[0] && (
              <select
                className="rounded border border-gray-300 px-2 py-1 text-xs"
                defaultValue=""
                onChange={(event) => {
                  if (!event.target.value) return;
                  batch.mutate({ photo_ids: selected, item_id: event.target.value });
                  setSelected([]);
                }}
              >
                <option value="">批量改挂到…</option>
                {items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            )}
          </div>
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {pending.map((photo) => {
              const neighborHint = neighborHintLabel(photo);
              return (
              <li key={photo.id} className="rounded border border-amber-100 bg-white p-2">
                <label className="mb-1 flex items-center gap-1 text-xs text-gray-500">
                  <input
                    type="checkbox"
                    checked={selected.includes(photo.id)}
                    onChange={(event) => {
                      setSelected((current) =>
                        event.target.checked
                          ? [...current, photo.id]
                          : current.filter((id) => id !== photo.id),
                      );
                    }}
                  />
                  {photo.original_filename}
                </label>
                {neighborHint && (
                  <p className="mb-1 text-[11px] text-amber-800">{neighborHint}</p>
                )}
                {photo.thumbnail_url && (
                  <button
                    type="button"
                    className="mb-1 block w-full"
                    onClick={() => setPreview(photo)}
                  >
                    <img
                      src={photo.thumbnail_url}
                      alt=""
                      className="h-20 w-full rounded object-cover"
                    />
                  </button>
                )}
                <select
                  className="w-full rounded border border-gray-300 text-xs"
                  defaultValue={photo.assignment?.item_id ?? ""}
                  onChange={(event) => {
                    if (!event.target.value) {
                      patch.mutate({ photoId: photo.id, action: "unassign" });
                      return;
                    }
                    patch.mutate({
                      photoId: photo.id,
                      action: "reassign",
                      itemId: event.target.value,
                    });
                  }}
                >
                  <option value="">选择地点</option>
                  {items.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <div className="mt-1 flex gap-2">
                  {photo.assignment?.item_id && !photo.assignment.is_confirmed && (
                    <button
                      type="button"
                      className="text-xs text-blue-600 hover:underline"
                      onClick={() =>
                        patch.mutate({
                          photoId: photo.id,
                          action: "confirm",
                          itemId: photo.assignment?.item_id ?? undefined,
                        })
                      }
                    >
                      确认
                    </button>
                  )}
                  <button
                    type="button"
                    className="text-xs text-red-600 hover:underline"
                    onClick={() => {
                      if (window.confirm("确定删除这张照片？")) {
                        remove.mutate(photo.id);
                      }
                    }}
                  >
                    删除
                  </button>
                </div>
              </li>
              );
            })}
          </ul>
        </div>
      )}

      {preview && (
        <PhotoLightbox
          photos={[preview]}
          index={0}
          alt={preview.original_filename}
          items={items}
          onClose={() => setPreview(null)}
          onReassign={(photoId, itemId) => {
            patch.mutate({ photoId, action: "reassign", itemId });
            setPreview(null);
          }}
          onUnassign={(photoId) => {
            patch.mutate({ photoId, action: "unassign" });
            setPreview(null);
          }}
          onDelete={(photoId) => {
            remove.mutate(photoId);
            setPreview(null);
          }}
        />
      )}
    </section>
  );
}

