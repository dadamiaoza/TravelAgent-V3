import { useMemo, useState } from "react";
import type { PhotoAsset, Trip } from "@/lib/types";
import {
  useBatchAssignPhotos,
  useDeletePhoto,
  usePatchPhotoAssignment,
  useTripPhotos,
  useUploadTripPhotos,
} from "@/hooks/useTripPhotos";
import PhotoLightbox from "@/components/PhotoLightbox";

function isPending(photo: PhotoAsset): boolean {
  const assignment = photo.assignment;
  if (!assignment) return true;
  if (assignment.is_confirmed) return false;
  return assignment.item_id == null || assignment.confidence < 0.85;
}

export default function PhotoArchivePanel({ trip }: { trip: Trip }) {
  const { photos } = useTripPhotos(trip.id);
  const upload = useUploadTripPhotos(trip.id);
  const patch = usePatchPhotoAssignment(trip.id);
  const batch = useBatchAssignPhotos(trip.id);
  const remove = useDeletePhoto(trip.id);
  const [selected, setSelected] = useState<string[]>([]);
  const [preview, setPreview] = useState<PhotoAsset | null>(null);
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
            照片只用于匹配当前行程。微信下载图往往没有地点和时间，请放到待确认或从某个地点「上传到这里」。
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
        {pending.length > 0 ? ` · ${pending.length} 张待确认` : ""}
      </p>

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
            {pending.map((photo) => (
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
            ))}
          </ul>
        </div>
      )}

      {preview && (
        <PhotoLightbox
          photos={[preview]}
          index={0}
          alt={preview.original_filename}
          onClose={() => setPreview(null)}
        />
      )}
    </section>
  );
}

