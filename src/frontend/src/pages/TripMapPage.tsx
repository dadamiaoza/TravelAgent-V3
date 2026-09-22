import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import TripMap from "@/components/TripMap";
import PhotoDrawer from "@/components/PhotoDrawer";
import PhotoLightbox from "@/components/PhotoLightbox";
import {
  buildRecallChapters,
  buildRecallSpine,
  chapterKeyForItem,
  confirmedStopIds,
  photosForBead,
  photosForItemOnChapter,
  planDayIndexForChapter,
  visitStopChapterKey,
  type SpineBead,
} from "@/lib/recallSpine";
import { useTripPhotos, useDeletePhoto, usePatchPhotoAssignment } from "@/hooks/useTripPhotos";
import { planItemOptions } from "@/lib/photos";
import { useTripStore } from "@/stores/tripStore";
import { useTripOutlet } from "@/pages/TripPage";

export default function TripMapPage() {
  const { trip } = useTripOutlet();
  const [searchParams] = useSearchParams();
  const itemFromQuery = searchParams.get("item");
  const days = trip.days ?? [];
  const focusItemId = useTripStore((s) => s.focusItemId);
  const setFocusItem = useTripStore((s) => s.setFocusItem);
  const { photos, visitStops } = useTripPhotos(trip.id);
  const patchPhoto = usePatchPhotoAssignment(trip.id);
  const removePhoto = useDeletePhoto(trip.id);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [focusVisitStopId, setFocusVisitStopId] = useState<string | null>(null);
  const [showPlanLayer, setShowPlanLayer] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [unsortedScope, setUnsortedScope] = useState<"day" | "trip" | null>(null);
  const [chapterKey, setChapterKey] = useState<string | null>(null);
  const appliedItemQuery = useRef(false);

  const confirmedStops = (visitStops.data ?? []).filter((stop) => stop.status === "confirmed");
  const photoList = photos.data ?? [];
  const chapters = useMemo(
    () => buildRecallChapters(days, photoList, confirmedStops),
    [confirmedStops, days, photoList],
  );
  const activeKey = chapters.some((chapter) => chapter.key === chapterKey)
    ? (chapterKey as string)
    : (chapters[0]?.key ?? null);
  const activeChapter = chapters.find((chapter) => chapter.key === activeKey) ?? null;
  const planDayIndex = activeKey ? planDayIndexForChapter(days, activeKey) : 0;
  const isLastChapter = Boolean(activeKey && chapters[chapters.length - 1]?.key === activeKey);

  const beads = useMemo(() => {
    if (!activeKey) return [];
    return buildRecallSpine({
      chapterKey: activeKey,
      isLastChapter,
      days,
      photos: photoList,
      confirmedStops,
    });
  }, [activeKey, confirmedStops, days, isLastChapter, photoList]);

  useEffect(() => {
    if (!itemFromQuery || appliedItemQuery.current || chapters.length === 0) return;
    const key = chapterKeyForItem(itemFromQuery, photoList, chapters);
    if (key) setChapterKey(key);
    setFocusVisitStopId(null);
    setUnsortedScope(null);
    setFocusItem(itemFromQuery);
    setDrawerOpen(true);
    appliedItemQuery.current = true;
  }, [chapters, itemFromQuery, photoList, setFocusItem]);

  const photoByItem = Object.fromEntries(
    activeKey
      ? days.flatMap((day) => day.items).flatMap((item) => {
          const shots = photosForItemOnChapter(photoList, item.id, activeKey);
          if (shots.length === 0) return [];
          return [
            [
              item.id,
              {
                count: shots.length,
                thumbUrl: shots.find((photo) => photo.thumbnail_url)?.thumbnail_url ?? null,
              },
            ],
          ];
        })
      : [],
  );

  const chapterStops = confirmedStops.filter((stop) => {
    const key = visitStopChapterKey(stop);
    if (key) return key === activeKey;
    return isLastChapter;
  });
  const visitStopPins = chapterStops
    .filter((stop) => stop.lat != null && stop.lng != null)
    .map((stop) => ({
      id: stop.id,
      place_name: stop.place_name,
      lat: stop.lat,
      lng: stop.lng,
      count: stop.photo_count,
      thumbUrl: stop.photos.find((photo) => photo.thumbnail_url)?.thumbnail_url ?? null,
    }));

  const itemOptions = useMemo(() => planItemOptions(days), [days]);
  const hasFootprint = photoList.some((photo) => photo.status === "completed") || confirmedStops.length > 0;

  const selectedBead: SpineBead | null = useMemo(() => {
    if (unsortedScope) return beads.find((bead) => bead.unsortedScope === unsortedScope) ?? null;
    if (focusVisitStopId) return beads.find((bead) => bead.visitStopId === focusVisitStopId) ?? null;
    if (focusItemId) return beads.find((bead) => bead.itemId === focusItemId) ?? null;
    return null;
  }, [beads, focusItemId, focusVisitStopId, unsortedScope]);

  const confirmedIds = useMemo(() => confirmedStopIds(confirmedStops), [confirmedStops]);
  const focusedStop = confirmedStops.find((stop) => stop.id === focusVisitStopId);
  const focusedItem = days.flatMap((day) => day.items).find((item) => item.id === focusItemId);
  const albumActive = Boolean(selectedBead || focusItemId || focusVisitStopId || unsortedScope);
  const drawerPhotos = activeKey
    ? selectedBead
      ? photosForBead(selectedBead, photoList, activeKey, confirmedIds)
      : focusVisitStopId
        ? photoList.filter((photo) => photo.assignment?.visit_stop_id === focusVisitStopId)
        : focusItemId
          ? photosForItemOnChapter(photoList, focusItemId, activeKey)
          : []
    : [];
  const drawerTitle = selectedBead
    ? `${selectedBead.label} · ${drawerPhotos.length} 张`
    : focusedStop
      ? `${focusedStop.place_name} · ${drawerPhotos.length} 张`
      : focusedItem
        ? `${focusedItem.poi_name} · ${drawerPhotos.length} 张`
        : "";
  const dayLabel = activeChapter?.label ?? "当天";
  const drawerMode = albumActive ? "album" : "spine";

  function clearNodeFocus() {
    setFocusItem(null);
    setFocusVisitStopId(null);
    setUnsortedScope(null);
    setLightboxIndex(null);
  }

  function selectChapter(key: string) {
    setChapterKey(key);
    clearNodeFocus();
  }

  function selectBead(bead: SpineBead) {
    setLightboxIndex(null);
    if (bead.kind === "plan" && bead.itemId) {
      setFocusVisitStopId(null);
      setUnsortedScope(null);
      setFocusItem(bead.itemId);
    } else if (bead.kind === "visit" && bead.visitStopId) {
      setFocusItem(null);
      setUnsortedScope(null);
      setFocusVisitStopId(bead.visitStopId);
    } else {
      setFocusItem(null);
      setFocusVisitStopId(null);
      setUnsortedScope(bead.unsortedScope ?? "day");
    }
    setDrawerOpen(true);
  }

  return (
    <div className="absolute inset-0">
      {days.length > 0 ? (
        <TripMap
          variant="recall"
          hideDaySwitcher
          days={days}
          selectedDayIndex={planDayIndex}
          onSelectDay={() => undefined}
          focusItemId={focusItemId}
          onSelectItem={(itemId) => {
            setFocusVisitStopId(null);
            setUnsortedScope(null);
            setFocusItem(itemId);
            setDrawerOpen(true);
          }}
          photoByItem={photoByItem}
          visitStops={visitStopPins}
          focusVisitStopId={focusVisitStopId}
          onSelectVisitStop={(stopId) => {
            setFocusItem(null);
            setUnsortedScope(null);
            setFocusVisitStopId(stopId);
            setDrawerOpen(true);
          }}
          showPlanLayer={showPlanLayer}
        />
      ) : (
        <p className="flex h-full items-center justify-center text-slate-500">该行程暂无内容</p>
      )}

      <div className="pointer-events-none absolute left-3 right-3 top-20 z-20 flex flex-col items-center gap-2 sm:top-24">
        {chapters.length > 0 && (
          <div className="pointer-events-auto flex max-w-full flex-wrap justify-center gap-2 rounded-2xl border border-white/70 bg-white/70 p-1 shadow-sm backdrop-blur-md">
            {chapters.map((chapter) => (
              <button
                key={chapter.key}
                type="button"
                onClick={() => selectChapter(chapter.key)}
                className={`min-h-11 rounded-full px-3 text-sm font-medium transition duration-200 ${
                  activeKey === chapter.key
                    ? "bg-sky-600 text-white"
                    : "text-slate-600 hover:bg-white"
                }`}
              >
                {chapter.label}
              </button>
            ))}
          </div>
        )}
        <label className="pointer-events-auto flex items-center gap-2 rounded-full border border-white/70 bg-white/80 px-3 py-1 text-xs text-slate-600 shadow-sm backdrop-blur-md">
          <input
            type="checkbox"
            checked={showPlanLayer}
            onChange={(event) => setShowPlanLayer(event.target.checked)}
          />
          对照计划路线
        </label>
        <p className="pointer-events-auto max-w-lg rounded-2xl border border-white/70 bg-white/85 px-3 py-1.5 text-center text-[11px] text-slate-600 shadow-sm backdrop-blur-md">
          按拍摄日翻足迹，不是第二份行程。点开照片可改挂或删除。
          <Link to={`/trips/${trip.id}`} className="ml-1 text-sky-700 hover:underline">
            去行程上传
          </Link>
        </p>
        {!hasFootprint && (
          <p className="pointer-events-auto max-w-md rounded-2xl border border-white/70 bg-white/85 px-4 py-2 text-center text-xs text-slate-600 shadow-sm backdrop-blur-md">
            淡线是计划对照，还不是足迹。在行程页上传带地点的照片后，这里会长出实际停留。
          </p>
        )}
      </div>

      <PhotoDrawer
        open={drawerOpen}
        onOpenChange={(next) => {
          setDrawerOpen(next);
          if (!next) setLightboxIndex(null);
        }}
        mode={drawerMode}
        dayLabel={dayLabel}
        title={drawerTitle}
        beads={beads}
        selectedBeadId={selectedBead?.id ?? null}
        onSelectBead={selectBead}
        onBack={clearNodeFocus}
        photos={drawerPhotos}
        onPhotoClick={(photoId) => {
          const index = drawerPhotos.findIndex((photo) => photo.id === photoId);
          if (index >= 0) setLightboxIndex(index);
        }}
      />

      {lightboxIndex != null && drawerPhotos[lightboxIndex] && (
        <PhotoLightbox
          photos={drawerPhotos}
          index={lightboxIndex}
          alt={selectedBead?.label}
          items={itemOptions}
          onClose={() => setLightboxIndex(null)}
          onIndexChange={setLightboxIndex}
          onReassign={(photoId, itemId) => {
            patchPhoto.mutate({ photoId, action: "reassign", itemId });
            setLightboxIndex(null);
          }}
          onUnassign={(photoId) => {
            patchPhoto.mutate({ photoId, action: "unassign" });
            setLightboxIndex(null);
          }}
          onDelete={(photoId) => {
            removePhoto.mutate(photoId);
            setLightboxIndex(null);
          }}
        />
      )}
    </div>
  );
}
