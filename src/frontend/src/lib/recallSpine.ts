import type { DayView, ItineraryItem, PhotoAsset, VisitStop } from "@/lib/types";
import { photosForItem, photosForVisitStop } from "@/lib/photos";

export type SpineLane = "axis" | "above" | "below";
export type SpineBeadKind = "plan" | "visit" | "unsorted";

export interface SpineBead {
  id: string;
  kind: SpineBeadKind;
  label: string;
  caption?: string;
  photoCount: number;
  thumbUrl: string | null;
  itemId?: string;
  visitStopId?: string;
  unsortedScope?: "day" | "trip";
  lane: SpineLane;
}

export interface RecallChapter {
  key: string;
  label: string;
}

export function dayKey(value: string | null | undefined): string | null {
  if (!value) return null;
  const match = value.match(/^(\d{4}-\d{2}-\d{2})/);
  return match ? match[1] : null;
}

export function formatChapterLabel(key: string, days: DayView[]): string {
  const [year, month, day] = key.split("-").map(Number);
  const dateText = `${year}年${month}月${day}日`;
  const plan = days.find((item) => dayKey(item.date) === key);
  return plan ? `Day ${plan.day_index} · ${dateText}` : dateText;
}

export function confirmedStopIds(stops: VisitStop[]): Set<string> {
  return new Set(stops.filter((stop) => stop.status === "confirmed").map((stop) => stop.id));
}

export function isRecallPlaced(photo: PhotoAsset, confirmedIds: Set<string>): boolean {
  const assignment = photo.assignment;
  if (!assignment) return false;
  if (assignment.item_id) {
    if (!assignment.is_confirmed && assignment.confidence < 0.85 && !photo.captured_at) {
      return false;
    }
    return true;
  }
  if (assignment.visit_stop_id && confirmedIds.has(assignment.visit_stop_id)) return true;
  return false;
}

export function visitStopChapterKey(stop: VisitStop): string | null {
  return (
    dayKey(stop.time_start) ??
    dayKey(stop.photos.find((photo) => photo.captured_at)?.captured_at) ??
    dayKey(stop.photos[0]?.captured_at)
  );
}

export function buildRecallChapters(
  days: DayView[],
  photos: PhotoAsset[],
  confirmedStops: VisitStop[],
): RecallChapter[] {
  const keys = new Set<string>();
  for (const photo of photos) {
    if (photo.status === "failed") continue;
    const key = dayKey(photo.captured_at);
    if (key) keys.add(key);
  }
  for (const stop of confirmedStops) {
    if (stop.status !== "confirmed") continue;
    const key = visitStopChapterKey(stop);
    if (key) keys.add(key);
  }
  const sorted = [...keys].sort();
  if (sorted.length === 0) {
    return days
      .map((day) => dayKey(day.date))
      .filter((key): key is string => Boolean(key))
      .map((key) => ({ key, label: formatChapterLabel(key, days) }));
  }
  return sorted.map((key) => ({ key, label: formatChapterLabel(key, days) }));
}

export function photosForItemOnChapter(
  photos: PhotoAsset[] | undefined,
  itemId: string,
  chapterKey: string,
): PhotoAsset[] {
  const assigned = photosForItem(photos, itemId).filter((photo) => {
    const assignment = photo.assignment;
    if (assignment && !assignment.is_confirmed && assignment.confidence < 0.85 && !photo.captured_at) {
      return false;
    }
    return true;
  });
  const dated = assigned.filter((photo) => dayKey(photo.captured_at) === chapterKey);
  const undated = assigned.filter((photo) => !photo.captured_at);
  return dated.length > 0 ? [...dated, ...undated] : dated;
}

export function photosForDayUnsorted(
  photos: PhotoAsset[] | undefined,
  chapterKey: string,
  confirmedIds: Set<string>,
): PhotoAsset[] {
  return (photos ?? []).filter((photo) => {
    if (photo.status === "failed") return false;
    if (isRecallPlaced(photo, confirmedIds)) return false;
    return dayKey(photo.captured_at) === chapterKey;
  });
}

export function photosForTripUnsorted(
  photos: PhotoAsset[] | undefined,
  confirmedIds: Set<string>,
): PhotoAsset[] {
  return (photos ?? []).filter((photo) => {
    if (photo.status === "failed") return false;
    if (isRecallPlaced(photo, confirmedIds)) return false;
    return !photo.captured_at;
  });
}

function firstThumb(photos: PhotoAsset[]): string | null {
  return photos.find((photo) => photo.thumbnail_url)?.thumbnail_url ?? null;
}

function parseIsoMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function itemSortMs(shots: PhotoAsset[], item: ItineraryItem): number {
  const earliest = shots
    .map((photo) => parseIsoMs(photo.captured_at))
    .filter((value): value is number => value != null)
    .sort((a, b) => a - b)[0];
  if (earliest != null) return earliest;
  return item.seq * 1_000_000;
}

function stopSortMs(stop: VisitStop, fallback: number): number {
  const fromStop = parseIsoMs(stop.time_start);
  if (fromStop != null) return fromStop;
  const fromPhoto = stop.photos
    .map((photo) => parseIsoMs(photo.captured_at))
    .filter((value): value is number => value != null)
    .sort((a, b) => a - b)[0];
  if (fromPhoto != null) return fromPhoto;
  return fallback;
}

export function chapterKeyForItem(
  itemId: string,
  photos: PhotoAsset[],
  chapters: RecallChapter[],
): string | null {
  const assigned = photosForItem(photos, itemId);
  const keys = new Set(
    assigned.map((photo) => dayKey(photo.captured_at)).filter((key): key is string => Boolean(key)),
  );
  const hit = chapters.find((chapter) => keys.has(chapter.key));
  return hit?.key ?? null;
}

export function photosForBead(
  bead: SpineBead,
  photos: PhotoAsset[] | undefined,
  chapterKey: string,
  confirmedIds: Set<string>,
): PhotoAsset[] {
  if (bead.kind === "plan" && bead.itemId) return photosForItemOnChapter(photos, bead.itemId, chapterKey);
  if (bead.kind === "visit" && bead.visitStopId) {
    return photosForVisitStop(photos, bead.visitStopId).filter((photo) => {
      const captured = dayKey(photo.captured_at);
      return captured == null || captured === chapterKey;
    });
  }
  if (bead.unsortedScope === "trip") return photosForTripUnsorted(photos, confirmedIds);
  return photosForDayUnsorted(photos, chapterKey, confirmedIds);
}

function planItems(days: DayView[]): { day: DayView; item: ItineraryItem }[] {
  return days.flatMap((day) =>
    [...day.items]
      .sort((a, b) => a.seq - b.seq)
      .map((item) => ({ day, item })),
  );
}

export function buildRecallSpine(input: {
  chapterKey: string;
  isLastChapter: boolean;
  days: DayView[];
  photos: PhotoAsset[];
  confirmedStops: VisitStop[];
}): SpineBead[] {
  const { chapterKey, isLastChapter, days, photos, confirmedStops } = input;
  const confirmedIds = confirmedStopIds(confirmedStops);
  const rows: { sortMs: number; planFirst: number; bead: SpineBead }[] = [];

  for (const { day, item } of planItems(days)) {
    const shots = photosForItemOnChapter(photos, item.id, chapterKey);
    if (shots.length === 0) continue;
    rows.push({
      sortMs: itemSortMs(shots, item),
      planFirst: 0,
      bead: {
        id: `item:${item.id}`,
        kind: "plan",
        label: item.poi_name,
        caption: `计划 Day ${day.day_index}`,
        photoCount: shots.length,
        thumbUrl: firstThumb(shots),
        itemId: item.id,
        lane: "axis",
      },
    });
  }

  const dayStops = confirmedStops.filter((stop) => {
    if (stop.status !== "confirmed") return false;
    const key = visitStopChapterKey(stop);
    if (key) return key === chapterKey;
    return isLastChapter;
  });
  dayStops.forEach((stop, index) => {
    const shots = photosForVisitStop(photos, stop.id).filter((photo) => {
      const captured = dayKey(photo.captured_at);
      return captured == null || captured === chapterKey;
    });
    const fallback = rows.length > 0 ? rows[rows.length - 1].sortMs + 1 : index;
    rows.push({
      sortMs: stopSortMs(stop, fallback),
      planFirst: 1,
      bead: {
        id: `visit:${stop.id}`,
        kind: "visit",
        label: stop.place_name,
        caption: "计划外",
        photoCount: shots.length || stop.photo_count,
        thumbUrl: firstThumb(shots) ?? firstThumb(stop.photos),
        visitStopId: stop.id,
        lane: "above",
      },
    });
  });

  rows.sort((a, b) => a.sortMs - b.sortMs || a.planFirst - b.planFirst);

  let visitOrdinal = 0;
  const beads = rows.map((row) => {
    if (row.bead.kind !== "visit") return row.bead;
    const lane: SpineLane = visitOrdinal % 2 === 0 ? "above" : "below";
    visitOrdinal += 1;
    return { ...row.bead, lane };
  });

  const dayUnsorted = photosForDayUnsorted(photos, chapterKey, confirmedIds);
  if (dayUnsorted.length > 0) {
    beads.push({
      id: "unsorted:day",
      kind: "unsorted",
      label: "未归类",
      caption: "待挂地点",
      photoCount: dayUnsorted.length,
      thumbUrl: firstThumb(dayUnsorted),
      unsortedScope: "day",
      lane: "axis",
    });
  }

  const tripUnsorted = photosForTripUnsorted(photos, confirmedIds);
  if (isLastChapter && tripUnsorted.length > 0) {
    beads.push({
      id: "unsorted:trip",
      kind: "unsorted",
      label: "未归类 · 无日期",
      caption: "待挂地点",
      photoCount: tripUnsorted.length,
      thumbUrl: firstThumb(tripUnsorted),
      unsortedScope: "trip",
      lane: "axis",
    });
  }

  return beads;
}

export function planDayIndexForChapter(days: DayView[], chapterKey: string): number {
  const index = days.findIndex((day) => dayKey(day.date) === chapterKey);
  return index >= 0 ? index : 0;
}
