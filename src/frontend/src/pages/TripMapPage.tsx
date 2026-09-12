import { useMemo, useState } from "react";
import TripMap from "@/components/TripMap";
import PhotoDrawer from "@/components/PhotoDrawer";
import PhotoLightbox from "@/components/PhotoLightbox";
import { photosForItem, photosForVisitStop } from "@/lib/photos";
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
  const { photos, summary, visitStops } = useTripPhotos(trip.id);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [focusVisitStopId, setFocusVisitStopId] = useState<string | null>(null);
  const [showPlanLayer, setShowPlanLayer] = useState(true);

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

  const confirmedStops = (visitStops.data ?? []).filter((stop) => stop.status === "confirmed");
  const visitStopPins = confirmedStops
    .filter((stop) => stop.lat != null && stop.lng != null)
    .map((stop) => ({
      id: stop.id,
      place_name: stop.place_name,
      lat: stop.lat,
      lng: stop.lng,
      count: stop.photo_count,
      thumbUrl: stop.photos.find((photo) => photo.thumbnail_url)?.thumbnail_url ?? null,
    }));

  const hasFootprint =
    confirmedStops.length > 0 ||
    (summary.data ?? []).some((row) => row.kind !== "visit_stop" && row.count > 0);

  const currentDay = days[selectedDayIndex];
  const focusedItem = currentDay?.items.find((item) => item.id === focusItemId);
  const focusedStop = confirmedStops.find((stop) => stop.id === focusVisitStopId);
  const drawerPhotos = useMemo(() => {
    if (focusVisitStopId) return photosForVisitStop(photos.data, focusVisitStopId);
    if (focusItemId) return photosForItem(photos.data, focusItemId);
    return [];
  }, [focusItemId, focusVisitStopId, photos.data]);
  const drawerTitle = focusedStop
    ? `${focusedStop.place_name} · ${drawerPhotos.length} 张`
    : focusedItem
      ? `${focusedItem.poi_name} · ${drawerPhotos.length} 张`
      : "";

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
            setFocusVisitStopId(null);
            setLightboxIndex(null);
          }}
          focusItemId={focusItemId}
          onSelectItem={(itemId) => {
            setFocusVisitStopId(null);
            setFocusItem(itemId);
          }}
          photoByItem={photoByItem}
          visitStops={visitStopPins}
          focusVisitStopId={focusVisitStopId}
          onSelectVisitStop={(stopId) => {
            setFocusItem(null);
            setFocusVisitStopId(stopId);
          }}
          showPlanLayer={showPlanLayer}
        />
      ) : (
        <p className="flex h-full items-center justify-center text-slate-500">该行程暂无内容</p>
      )}

      <div className="pointer-events-none absolute left-3 right-3 top-20 z-20 flex flex-col items-center gap-2 sm:top-24">
        <div className="pointer-events-auto flex max-w-full flex-wrap justify-center gap-2 rounded-2xl border border-white/70 bg-white/70 p-1 shadow-sm backdrop-blur-md">
          {days.map((day, index) => (
            <button
              key={day.id}
              type="button"
              onClick={() => {
                setSelectedDayIndex(index);
                setFocusItem(null);
                setFocusVisitStopId(null);
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
        <label className="pointer-events-auto flex items-center gap-2 rounded-full border border-white/70 bg-white/80 px-3 py-1 text-xs text-slate-600 shadow-sm backdrop-blur-md">
          <input
            type="checkbox"
            checked={showPlanLayer}
            onChange={(event) => setShowPlanLayer(event.target.checked)}
          />
          显示计划路线
        </label>
        {!hasFootprint && (
          <p className="pointer-events-auto max-w-md rounded-2xl border border-white/70 bg-white/85 px-4 py-2 text-center text-xs text-slate-600 shadow-sm backdrop-blur-md">
            这是计划路线，还不是足迹。在行程页上传带地点的照片后，这里会长出实际停留。
          </p>
        )}
      </div>

      {(focusedItem || focusedStop) && (
        <PhotoDrawer
          title={drawerTitle}
          photos={drawerPhotos}
          onClose={() => {
            setFocusItem(null);
            setFocusVisitStopId(null);
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
          alt={focusedStop?.place_name ?? focusedItem?.poi_name}
          onClose={() => setLightboxIndex(null)}
          onIndexChange={setLightboxIndex}
        />
      )}
    </div>
  );
}
