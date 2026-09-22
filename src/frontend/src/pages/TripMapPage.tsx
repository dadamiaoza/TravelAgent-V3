import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import TripMap from "@/components/TripMap";
import PhotoDrawer from "@/components/PhotoDrawer";
import PhotoLightbox from "@/components/PhotoLightbox";
import {
  buildOtherDayGhosts,
  buildRecallChapters,
  buildRecallSpine,
  buildDayPhotoFrames,
  playableRecallBeads,
  chapterKeyForItem,
  confirmedStopIds,
  photosForBead,
  photosForItemOnChapter,
  planDayIndexForChapter,
  visitStopChapterKey,
  type SpineBead,
} from "@/lib/recallSpine";
import { useTripPhotos, useDeletePhoto, usePatchPhotoAssignment, usePatchVisitStop } from "@/hooks/useTripPhotos";
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
  const patchStop = usePatchVisitStop(trip.id);
  const removePhoto = useDeletePhoto(trip.id);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [focusVisitStopId, setFocusVisitStopId] = useState<string | null>(null);
  const [showPlanLayer, setShowPlanLayer] = useState(true);
  const [showOtherDays, setShowOtherDays] = useState(true);
  const [fitScope, setFitScope] = useState<"day" | "all">("day");
  const [fitNonce, setFitNonce] = useState(0);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerView, setDrawerView] = useState<"spine" | "album">("spine");
  const [selectedBeadId, setSelectedBeadId] = useState<string | null>(null);
  const [chapterKey, setChapterKey] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [playStopIndex, setPlayStopIndex] = useState(0);
  const appliedItemQuery = useRef(false);

  const confirmedStops = useMemo(
    () => (visitStops.data ?? []).filter((stop) => stop.status === "confirmed"),
    [visitStops.data],
  );
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
    setSelectedBeadId(`item:${itemFromQuery}`);
    setFocusItem(itemFromQuery);
    setDrawerView("album");
    setDrawerOpen(true);
    appliedItemQuery.current = true;
  }, [chapters, itemFromQuery, photoList, setFocusItem]);

  const photoByItem = useMemo(
    () =>
      Object.fromEntries(
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
      ),
    [activeKey, days, photoList],
  );

  const chapterStops = useMemo(
    () =>
      confirmedStops.filter((stop) => {
        const key = visitStopChapterKey(stop);
        if (key) return key === activeKey;
        return isLastChapter;
      }),
    [activeKey, confirmedStops, isLastChapter],
  );
  const visitStopPins = useMemo(
    () =>
      chapterStops
        .filter((stop) => stop.lat != null && stop.lng != null)
        .map((stop) => ({
          id: stop.id,
          place_name: stop.place_name,
          lat: stop.lat,
          lng: stop.lng,
          count: stop.photo_count,
          thumbUrl: stop.photos.find((photo) => photo.thumbnail_url)?.thumbnail_url ?? null,
        })),
    [chapterStops],
  );

  const otherDayGhosts = useMemo(
    () =>
      buildOtherDayGhosts({
        activeKey,
        chapters,
        days,
        photos: photoList,
        confirmedStops,
      }),
    [activeKey, chapters, confirmedStops, days, photoList],
  );
  const ghostPins = useMemo(
    () => (showOtherDays ? otherDayGhosts : []),
    [otherDayGhosts, showOtherDays],
  );
  const dayFitKey = useMemo(
    () =>
      [activeKey ?? "", ...Object.keys(photoByItem).sort(), ...visitStopPins.map((pin) => pin.id)].join("|"),
    [activeKey, photoByItem, visitStopPins],
  );
  const itemOptions = useMemo(() => planItemOptions(days), [days]);
  const hasFootprint = photoList.some((photo) => photo.status === "completed") || confirmedStops.length > 0;

  const selectedBead: SpineBead | null = useMemo(() => {
    if (selectedBeadId) {
      const hit = beads.find((bead) => bead.id === selectedBeadId);
      if (hit) return hit;
    }
    if (focusVisitStopId) return beads.find((bead) => bead.visitStopId === focusVisitStopId) ?? null;
    if (focusItemId) return beads.find((bead) => bead.itemId === focusItemId) ?? null;
    return null;
  }, [beads, focusItemId, focusVisitStopId, selectedBeadId]);

  const confirmedIds = useMemo(() => confirmedStopIds(confirmedStops), [confirmedStops]);
  const playableBeads = useMemo(() => playableRecallBeads(beads), [beads]);
  const dayFrames = useMemo(() => {
    if (!activeKey) return [];
    return buildDayPhotoFrames(beads, photoList, activeKey, confirmedIds);
  }, [activeKey, beads, confirmedIds, photoList]);
  const lightboxPhotos = dayFrames.map((frame) => frame.photo);
  const lightboxFrame = lightboxIndex != null ? (dayFrames[lightboxIndex] ?? null) : null;
  const focusedStop = confirmedStops.find((stop) => stop.id === focusVisitStopId);
  const activeVisitStopId = selectedBead?.visitStopId ?? focusVisitStopId;
  const focusedItem = days.flatMap((day) => day.items).find((item) => item.id === focusItemId);
  const dayLabel = activeChapter?.label ?? "当天";
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

  function requestFit(scope: "day" | "all") {
    setFitScope(scope);
    setFitNonce((nonce) => nonce + 1);
  }

  function clearNodeFocus() {
    setPlaying(false);
    setFocusItem(null);
    setFocusVisitStopId(null);
    setSelectedBeadId(null);
    setLightboxIndex(null);
    setDrawerView("spine");
  }

  function backToSpine() {
    setPlaying(false);
    setLightboxIndex(null);
    setDrawerView("spine");
  }

  function selectChapter(key: string) {
    setChapterKey(key);
    requestFit("day");
    clearNodeFocus();
  }

  function toggleOtherDays() {
    if (showOtherDays && fitScope !== "all") {
      requestFit("all");
      return;
    }
    if (showOtherDays) {
      setShowOtherDays(false);
      requestFit("day");
      return;
    }
    setShowOtherDays(true);
    requestFit("all");
  }

  const onSelectPlanPin = useCallback(
    (itemId: string) => {
      setPlaying(false);
      setFocusVisitStopId(null);
      setSelectedBeadId(`item:${itemId}`);
      setFocusItem(itemId);
      setDrawerView("album");
      setDrawerOpen(true);
    },
    [setFocusItem],
  );

  const onSelectVisitPin = useCallback(
    (stopId: string) => {
      setPlaying(false);
      setFocusItem(null);
      setSelectedBeadId(`visit:${stopId}`);
      setFocusVisitStopId(stopId);
      setDrawerView("album");
      setDrawerOpen(true);
    },
    [setFocusItem],
  );

  const onSelectGhostPin = useCallback(
    (pin: { chapterKey: string; kind: "plan" | "visit"; visitStopId?: string; itemId?: string }) => {
      setPlaying(false);
      setChapterKey(pin.chapterKey);
      setLightboxIndex(null);
      if (pin.kind === "visit" && pin.visitStopId) {
        setFocusItem(null);
        setSelectedBeadId(`visit:${pin.visitStopId}`);
        setFocusVisitStopId(pin.visitStopId);
      } else if (pin.itemId) {
        setFocusVisitStopId(null);
        setSelectedBeadId(`item:${pin.itemId}`);
        setFocusItem(pin.itemId);
      }
      setDrawerView("album");
      setDrawerOpen(true);
    },
    [setFocusItem],
  );

  function selectBead(bead: SpineBead, keepLightbox = false) {
    if (!keepLightbox) setLightboxIndex(null);
    setSelectedBeadId(bead.id);
    const playIdx = playableBeads.findIndex((row) => row.id === bead.id);
    if (playIdx >= 0) setPlayStopIndex(playIdx);
    if (bead.kind === "plan" && bead.itemId) {
      setFocusVisitStopId(null);
      setFocusItem(bead.itemId);
    } else if (bead.kind === "visit" && bead.visitStopId) {
      setFocusItem(null);
      setFocusVisitStopId(bead.visitStopId);
    } else {
      setFocusItem(null);
      setFocusVisitStopId(null);
    }
    setDrawerView("album");
    setDrawerOpen(true);
  }

  function onUserSelectBead(bead: SpineBead) {
    setPlaying(false);
    selectBead(bead);
  }

  function goToPlayStop(index: number) {
    const bead = playableBeads[index];
    if (!bead) {
      setPlaying(false);
      return;
    }
    setPlayStopIndex(index);
    selectBead(bead, true);
  }

  function startPlayback() {
    if (playableBeads.length === 0) return;
    setLightboxIndex(null);
    const current = selectedBead
      ? playableBeads.findIndex((bead) => bead.id === selectedBead.id)
      : -1;
    const start = current >= 0 && current < playableBeads.length - 1 ? current : 0;
    goToPlayStop(start);
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setPlaying(!reduceMotion);
  }

  useEffect(() => {
    setPlaying(false);
  }, [activeKey]);

  useEffect(() => {
    if (!selectedBeadId) return;
    const idx = playableBeads.findIndex((bead) => bead.id === selectedBeadId);
    if (idx >= 0) setPlayStopIndex(idx);
  }, [selectedBeadId, playableBeads]);


  useEffect(() => {
    if (!playing) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) return;
    const timer = window.setTimeout(() => {
      const next = playStopIndex + 1;
      if (next >= playableBeads.length) {
        setPlaying(false);
        return;
      }
      goToPlayStop(next);
    }, 2200);
    return () => window.clearTimeout(timer);
  }, [playStopIndex, playableBeads, playing]);

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
          onSelectItem={onSelectPlanPin}
          photoByItem={photoByItem}
          visitStops={visitStopPins}
          focusVisitStopId={focusVisitStopId}
          onSelectVisitStop={onSelectVisitPin}
          showPlanLayer={showPlanLayer}
          ghostPins={ghostPins}
          onSelectGhost={onSelectGhostPin}
          fitScope={fitScope}
          fitNonce={fitNonce}
          fitKey={dayFitKey}
        />
      ) : (
        <p className="flex h-full items-center justify-center text-slate-500">该行程暂无内容</p>
      )}

      <div className="pointer-events-none absolute left-3 right-3 top-20 z-20 sm:top-24">
        <div className="pointer-events-auto mx-auto flex max-w-full items-center gap-1.5 overflow-x-auto rounded-full border border-white/70 bg-white/80 p-1 shadow-sm backdrop-blur-md scrollbar-none">
          {chapters.length > 0 && (
            <div className="flex shrink-0 items-center gap-1">
              {chapters.map((chapter) => (
                <button
                  key={chapter.key}
                  type="button"
                  onClick={() => selectChapter(chapter.key)}
                  className={`h-8 shrink-0 rounded-full px-2.5 text-xs font-medium transition duration-200 ${
                    activeKey === chapter.key
                      ? "bg-sky-600 text-white"
                      : "text-slate-600 hover:bg-white"
                  }`}
                >
                  {chapter.label}
                </button>
              ))}
              <span className="mx-0.5 h-4 w-px shrink-0 bg-slate-200" aria-hidden />
            </div>
          )}

          <button
            type="button"
            aria-pressed={showPlanLayer}
            title="对照计划路线"
            className={`h-8 shrink-0 rounded-full border px-2.5 text-xs font-medium ${
              showPlanLayer
                ? "border-sky-300 bg-sky-100 text-sky-800"
                : "border-transparent text-slate-600 hover:bg-white"
            }`}
            onClick={() => setShowPlanLayer((on) => !on)}
          >
            对照计划
          </button>

          {otherDayGhosts.length > 0 && (
            <button
              type="button"
              aria-pressed={showOtherDays}
              title={showOtherDays && fitScope !== "all" ? "看全部拍摄日" : "显示其他拍摄日"}
              className={`h-8 shrink-0 rounded-full border px-2.5 text-xs font-medium ${
                showOtherDays
                  ? "border-sky-300 bg-sky-100 text-sky-800"
                  : "border-transparent text-slate-600 hover:bg-white"
              }`}
              onClick={toggleOtherDays}
            >
              {showOtherDays && fitScope !== "all" ? "全部拍摄日" : "其他拍摄日"}
            </button>
          )}

          {playableBeads.length > 0 && (
            <>
              <span className="mx-0.5 h-4 w-px shrink-0 bg-slate-200" aria-hidden />
              {playing ? (
                <button
                  type="button"
                  className="h-8 shrink-0 rounded-full px-2.5 text-xs font-medium text-sky-800 hover:bg-white"
                  onClick={() => setPlaying(false)}
                >
                  暂停
                </button>
              ) : (
                <button
                  type="button"
                  className="h-8 shrink-0 rounded-full px-2.5 text-xs font-medium text-sky-800 hover:bg-white"
                  onClick={startPlayback}
                >
                  回放
                </button>
              )}
              <button
                type="button"
                className="h-8 shrink-0 rounded-full px-2 text-xs hover:bg-white disabled:text-slate-300"
                disabled={playStopIndex <= 0 || playableBeads.length < 2}
                onClick={() => {
                  setPlaying(false);
                  goToPlayStop(Math.max(0, playStopIndex - 1));
                }}
              >
                上一站
              </button>
              <span className="max-w-[7.5rem] shrink truncate px-1 text-[11px] text-slate-500">
                {playableBeads[playStopIndex]?.label ?? playableBeads[0]?.label}
                {playableBeads.length > 0
                  ? ` ${Math.min(playStopIndex + 1, playableBeads.length)}/${playableBeads.length}`
                  : ""}
              </span>
              <button
                type="button"
                className="h-8 shrink-0 rounded-full px-2 text-xs hover:bg-white disabled:text-slate-300"
                disabled={playStopIndex >= playableBeads.length - 1 || playableBeads.length < 2}
                onClick={() => {
                  setPlaying(false);
                  goToPlayStop(Math.min(playableBeads.length - 1, playStopIndex + 1));
                }}
              >
                下一站
              </button>
            </>
          )}

          <span className="mx-0.5 h-4 w-px shrink-0 bg-slate-200" aria-hidden />
          <button
            type="button"
            aria-expanded={helpOpen}
            aria-label="地图操作说明"
            className={`h-8 w-8 shrink-0 rounded-full text-sm font-semibold ${
              helpOpen ? "bg-sky-100 text-sky-800" : "text-slate-500 hover:bg-white"
            }`}
            onClick={() => setHelpOpen((open) => !open)}
          >
            ?
          </button>
        </div>

        {helpOpen && (
          <div className="pointer-events-auto mx-auto mt-2 max-w-lg rounded-2xl border border-white/70 bg-white/90 px-3 py-2 text-center text-[11px] leading-relaxed text-slate-600 shadow-sm backdrop-blur-md">
            {hasFootprint ? (
              <>
                按拍摄日翻足迹；点某一天只看该日。要看多日距离，再点「其他拍摄日」。对照计划可叠一层路线；回放只沿停留点，不画计划路。
                <Link to={`/trips/${trip.id}`} className="ml-1 text-sky-700 hover:underline">
                  去行程上传
                </Link>
              </>
            ) : (
              <>
                当前是计划日视图，还没有足迹。去行程页上传带地点的照片后，这里会长出真实停留点。
                <Link to={`/trips/${trip.id}`} className="ml-1 text-sky-700 hover:underline">
                  去行程上传
                </Link>
              </>
            )}
          </div>
        )}
      </div>

      <PhotoDrawer
        open={drawerOpen}
        onOpenChange={(next) => {
          setDrawerOpen(next);
          if (!next) setLightboxIndex(null);
        }}
        mode={drawerView}
        dayLabel={dayLabel}
        title={drawerTitle}
        beads={beads}
        selectedBeadId={selectedBead?.id ?? null}
        onSelectBead={onUserSelectBead}
        onBack={backToSpine}
        photos={drawerPhotos}
        onPhotoClick={(photoId) => {
          const index = dayFrames.findIndex((frame) => frame.photo.id === photoId);
          if (index >= 0) {
            setPlaying(false);
            setLightboxIndex(index);
          }
        }}
        onDismissVisitStop={
          activeVisitStopId
            ? () => {
                const stopName = selectedBead?.label ?? focusedStop?.place_name ?? "这个停留";
                const extra = drawerPhotos.length > 0 ? "上面的照片会回到未归类，" : "";
                if (!window.confirm(`去掉「${stopName}」？${extra}不会改行程计划。`)) return;
                patchStop.mutate({ stopId: activeVisitStopId, action: "dismiss" });
                clearNodeFocus();
              }
            : undefined
        }
      />

      {lightboxIndex != null && lightboxFrame && (
        <PhotoLightbox
          photos={lightboxPhotos}
          index={lightboxIndex}
          alt={`${lightboxFrame.bead.label} ${lightboxFrame.indexInBead + 1}/${lightboxFrame.beadCount}`}
          hint={`当天 ${lightboxIndex + 1}/${dayFrames.length}`}
          items={itemOptions}
          onClose={() => setLightboxIndex(null)}
          onIndexChange={(index) => {
            const frame = dayFrames[index];
            if (frame) {
              selectBead(frame.bead, true);
              const stop = playableBeads.findIndex((bead) => bead.id === frame.bead.id);
              if (stop >= 0) setPlayStopIndex(stop);
            }
            setLightboxIndex(index);
          }}
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
