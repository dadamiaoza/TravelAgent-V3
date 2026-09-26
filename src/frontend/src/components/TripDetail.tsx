import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Trip } from "@/lib/types";
import { api } from "@/lib/api";
import { useTripStore } from "@/stores/tripStore";
import { useTripDraftSync } from "@/hooks/useTripDraftSync";
import ItineraryDayCard from "@/components/ItineraryDayCard";
import TripMap from "@/components/TripMap";
import PhotoArchivePanel from "@/components/PhotoArchivePanel";
import { photosForItem } from "@/lib/photos";
import { cardMeta, cardTitle } from "@/lib/tripLibrary";
import { detailStatusClassName, detailStatusLabel, type TripDetailShell } from "@/lib/tripDetailState";
import GenerationWarningPill from "@/components/GenerationWarningPill";
import { useTripPhotos, useUploadTripPhotos } from "@/hooks/useTripPhotos";

export function TripIdentityHeader({
  trip,
  shell,
  warningMessages = [],
}: {
  trip: Trip;
  shell: TripDetailShell;
  warningMessages?: string[];
}) {
  const queryClient = useQueryClient();
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState(trip.destination);

  const updateTrip = useMutation({
    mutationFn: (destination: string) =>
      api.patch<Trip>(`/trips/${trip.id}`, { destination }),
    onSuccess: (data) => {
      queryClient.setQueryData(["trip", trip.id], data);
      setEditingTitle(false);
    },
  });

  function handleSaveTitle() {
    const value = titleDraft.trim();
    if (!value) return;
    updateTrip.mutate(value);
  }

  return (
    <section className="mb-4 rounded-2xl border border-line-tertiary bg-elevated p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          {!editingTitle ? (
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="truncate text-2xl font-semibold tracking-tight text-ink">
                {cardTitle(trip)}
              </h1>
              <button
                type="button"
                onClick={() => {
                  setTitleDraft(trip.destination);
                  setEditingTitle(true);
                }}
                className="rounded-full px-2 py-1 text-xs text-ink-tertiary hover:bg-chrome hover:text-ink"
              >
                编辑标题
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={titleDraft}
                onChange={(e) => setTitleDraft(e.target.value)}
                className="rounded-full border border-line-tertiary bg-chrome px-3 py-1.5 text-sm text-ink"
                aria-label="行程标题"
              />
              <button
                type="button"
                onClick={handleSaveTitle}
                disabled={updateTrip.isPending}
                className="rounded-full bg-blue-600 px-3 py-1.5 text-xs text-white disabled:opacity-60"
              >
                保存
              </button>
              <button
                type="button"
                onClick={() => setEditingTitle(false)}
                className="rounded-full border border-line-tertiary px-3 py-1.5 text-xs text-ink-secondary"
              >
                取消
              </button>
            </div>
          )}
          <p className="mt-1 text-sm text-ink-secondary">
            {cardMeta(trip)}
            {updateTrip.isError && (
              <span className="ml-2 text-rose-700">标题没有保存，请再试一次</span>
            )}
          </p>
        </div>
        <div className="flex max-w-full flex-col items-end gap-2">
          <div className="flex max-w-full flex-wrap items-center justify-end gap-2">
            <span
              className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${detailStatusClassName(trip.status)}`}
            >
              {detailStatusLabel(trip.status)}
            </span>
            {shell === "ready" &&
              warningMessages.map((message) => (
                <GenerationWarningPill key={message} message={message} />
              ))}
          </div>
          {shell === "ready" && (
            <Link
              to={`/sources?tripId=${trip.id}`}
              className="rounded-full border border-line-tertiary px-3 py-1.5 text-sm text-ink-secondary hover:text-ink"
            >
              导入攻略
            </Link>
          )}
        </div>
      </div>
    </section>
  );
}

export default function TripDetail({ trip }: { trip: Trip }) {
  const { dirtyTrip, isDirty } = useTripDraftSync(trip.id, trip);
  const displayTrip = dirtyTrip ?? trip;
  const days = displayTrip.days ?? [];
  const selectedDayIndex = useTripStore((s) => s.selectedDayIndex);
  const focusItemId = useTripStore((s) => s.focusItemId);
  const setSelectedDayIndex = useTripStore((s) => s.setSelectedDayIndex);
  const setFocusItem = useTripStore((s) => s.setFocusItem);
  function handleSelectItem(itemId: string) {
    setFocusItem(itemId);
    requestAnimationFrame(() => {
      document
        .getElementById(`itinerary-item-${itemId}`)
        ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }

  function handleSelectDay(index: number) {
    setSelectedDayIndex(index);
    setFocusItem(null);
  }

  const currentDay = days[selectedDayIndex];
  const { photos, summary } = useTripPhotos(trip.id);
  const upload = useUploadTripPhotos(trip.id);
  const photoByItem = Object.fromEntries(
    (summary.data ?? [])
      .filter((row) => row.kind !== "visit_stop" && row.item_id)
      .map((row) => [
        row.item_id as string,
      {
        count: row.count,
        thumbUrl: row.thumbnail_photo_id
          ? `/api/v1/trips/${trip.id}/photos/${row.thumbnail_photo_id}/file?variant=thumbnail`
          : null,
      },
    ]),
  );

  return (
    <div className="space-y-6">
      {isDirty && (
        <p className="inline-flex rounded-full bg-rose-50 px-2.5 py-0.5 text-xs text-rose-700">
          未保存
        </p>
      )}

      {days.length > 0 && (
        <TripMap
          variant="route"
          days={days}
          selectedDayIndex={selectedDayIndex}
          onSelectDay={handleSelectDay}
          focusItemId={focusItemId}
          onSelectItem={handleSelectItem}
          photoByItem={photoByItem}
        />
      )}

      {currentDay ? (
        <div className="max-h-[60vh] overflow-y-auto overscroll-contain rounded-lg pr-1">
          <ItineraryDayCard
            key={currentDay.id}
            day={currentDay}
            tripId={trip.id}
            focusedItemId={focusItemId}
            onSelectItem={handleSelectItem}
            photosByItemId={Object.fromEntries(
              (currentDay.items ?? []).map((item) => [
                item.id,
                photosForItem(photos.data, item.id),
              ]),
            )}
            onUploadToItem={(itemId, files) => upload.mutate({ files, itemId })}
            uploading={upload.isPending}
          />
        </div>
      ) : (
        <p className="rounded-2xl border border-dashed border-line-tertiary bg-elevated px-4 py-10 text-center text-sm text-ink-tertiary">
          这趟行程还没有地点
        </p>
      )}

      <PhotoArchivePanel trip={displayTrip} />

    </div>
  );
}
