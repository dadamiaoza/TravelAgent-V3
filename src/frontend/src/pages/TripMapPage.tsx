import { useMemo, useState } from "react";
import TripMap from "@/components/TripMap";
import PhotoDrawer from "@/components/PhotoDrawer";
import PhotoLightbox from "@/components/PhotoLightbox";
import { photosForItem } from "@/lib/photos";
import { useTripPhotos } from "@/hooks/useTripPhotos";
import { useTripStore } from "@/stores/tripStore";
import { useTripOutlet } from "@/pages/TripPage";

export default function TripMapPage() {
  const { trip } = useTripOutlet();
  const days = trip.days ?? [];
  const selectedDayIndex = useTripStore((s) => s.selectedDayIndex);
  const focusItemId = useTripStore((s) => s.focusItemId);
  const setSelectedDayIndex = useTripStore((s) => s.setSelectedDayIndex);
  const setFocusItem = useTripStore((s) => s.setFocusItem);
  const { photos, summary } = useTripPhotos(trip.id);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  const photoByItem = Object.fromEntries(
    (summary.data ?? []).map((row) => [
      row.item_id,
      {
        count: row.count,
        thumbUrl: row.thumbnail_photo_id
          ? `/api/v1/trips/${trip.id}/photos/${row.thumbnail_photo_id}/file?variant=thumbnail`
          : null,
      },
    ]),
  );

  const currentDay = days[selectedDayIndex];
  const focusedItem = currentDay?.items.find((item) => item.id === focusItemId);
  const drawerPhotos = useMemo(
    () => (focusItemId ? photosForItem(photos.data, focusItemId) : []),
    [focusItemId, photos.data],
  );

  return (
    <div className="absolute inset-0">
      {days.length > 0 ? (
        <TripMap
          variant="recall"
          hideDaySwitcher
          days={days}
          selectedDayIndex={selectedDayIndex}
          onSelectDay={(index) => {
            setSelectedDayIndex(index);
            setFocusItem(null);
            setLightboxIndex(null);
          }}
          focusItemId={focusItemId}
          onSelectItem={(itemId) => setFocusItem(itemId)}
          photoByItem={photoByItem}
        />
      ) : (
        <p className="flex h-full items-center justify-center text-slate-500">该行程暂无内容</p>
      )}

      <div className="pointer-events-none absolute left-3 right-3 top-20 z-20 flex justify-center sm:top-24">
        <div className="pointer-events-auto flex max-w-full flex-wrap justify-center gap-2 rounded-2xl border border-white/70 bg-white/70 p-1 shadow-sm backdrop-blur-md">
          {days.map((day, index) => (
            <button
              key={day.id}
              type="button"
              onClick={() => {
                setSelectedDayIndex(index);
                setFocusItem(null);
                setLightboxIndex(null);
              }}
              className={`min-h-11 rounded-full px-4 text-sm font-medium transition duration-200 ${
                selectedDayIndex === index
                  ? "bg-sky-600 text-white"
                  : "text-slate-600 hover:bg-white"
              }`}
            >
              Day {day.day_index}
            </button>
          ))}
        </div>
      </div>

      {focusedItem && (
        <PhotoDrawer
          title={`${focusedItem.poi_name} · ${drawerPhotos.length} 张`}
          photos={drawerPhotos}
          onClose={() => {
            setFocusItem(null);
            setLightboxIndex(null);
          }}
          onPhotoClick={(photoId) => {
            const index = drawerPhotos.findIndex((photo) => photo.id === photoId);
            if (index >= 0) setLightboxIndex(index);
          }}
        />
      )}

      {lightboxIndex != null && drawerPhotos[lightboxIndex] && (
        <PhotoLightbox
          photos={drawerPhotos}
          index={lightboxIndex}
          alt={focusedItem?.poi_name}
          onClose={() => setLightboxIndex(null)}
          onIndexChange={setLightboxIndex}
        />
      )}
    </div>
  );
}
