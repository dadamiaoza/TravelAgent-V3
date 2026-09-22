import type { DayView, ItineraryItem, PhotoAsset, VisitStop } from "@/lib/types";
import { photosForItem, photosForVisitStop } from "@/lib/photos";

export type SpineLane = "axis" | "above" | "below";
export type SpineBeadKind = "plan" | "visit" | "unsorted";
export type UnsortedScope = "day" | "trip" | "gap";

export interface SpineBead {
  id: string;
  kind: SpineBeadKind;
  label: string;
  caption?: string;
  photoCount: number;
  thumbUrl: string | null;
  itemId?: string;
  visitStopId?: string;
  unsortedScope?: UnsortedScope;
  photoIds?: string[];
  lane: SpineLane;
}

export interface RecallGhostPin {
  id: string;
  kind: "plan" | "visit";
  chapterKey: string;
  place_name: string;
  lat: number;
  lng: number;
  count: number;
  thumbUrl: string | null;
  itemId?: string;
  visitStopId?: string;
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
  if (bead.photoIds && bead.photoIds.length > 0) {
    const ids = new Set(bead.photoIds);
    return (photos ?? []).filter((photo) => ids.has(photo.id));
  }
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

function sortByCaptured(photos: PhotoAsset[]): PhotoAsset[] {
  return [...photos].sort((left, right) => {
    const leftMs = left.captured_at ? Date.parse(left.captured_at) : Number.POSITIVE_INFINITY;
    const rightMs = right.captured_at ? Date.parse(right.captured_at) : Number.POSITIVE_INFINITY;
    const leftSafe = Number.isNaN(leftMs) ? Number.POSITIVE_INFINITY : leftMs;
    const rightSafe = Number.isNaN(rightMs) ? Number.POSITIVE_INFINITY : rightMs;
    if (leftSafe !== rightSafe) return leftSafe - rightSafe;
    return left.id.localeCompare(right.id);
  });
}

export interface RecallPhotoFrame {
  photo: PhotoAsset;
  bead: SpineBead;
  indexInBead: number;
  beadCount: number;
}

export function buildDayPhotoFrames(
  beads: SpineBead[],
  photos: PhotoAsset[] | undefined,
  chapterKey: string,
  confirmedIds: Set<string>,
): RecallPhotoFrame[] {
  const frames: RecallPhotoFrame[] = [];
  for (const bead of beads) {
    const shots = sortByCaptured(photosForBead(bead, photos, chapterKey, confirmedIds));
    shots.forEach((photo, indexInBead) => {
      frames.push({ photo, bead, indexInBead, beadCount: shots.length });
    });
  }
  return frames;
}

export function playableRecallBeads(beads: SpineBead[]): SpineBead[] {
  return beads.filter((bead) => bead.kind === "plan" || bead.kind === "visit");
}

export function gapCaption(beforeLabel: string | null, afterLabel: string | null): string {
  if (beforeLabel && afterLabel) return `${beforeLabel} → ${afterLabel}`;
  if (afterLabel) return `${afterLabel}之前`;
  if (beforeLabel) return `${beforeLabel}之后`;
  return "待挂地点";
}

function makeGapBead(
  index: number,
  shots: PhotoAsset[],
  beforeLabel: string | null,
  afterLabel: string | null,
): SpineBead {
  return {
    id: `unsorted:gap:${index}`,
    kind: "unsorted",
    label: "空档",
    caption: gapCaption(beforeLabel, afterLabel),
    photoCount: shots.length,
    thumbUrl: firstThumb(shots),
    unsortedScope: "gap",
    photoIds: shots.map((photo) => photo.id),
    lane: "axis",
  };
}

export function interleaveUnsortedGaps(
  placed: { sortMs: number; bead: SpineBead }[],
  unsorted: PhotoAsset[],
): SpineBead[] {
  if (unsorted.length === 0) return placed.map((row) => row.bead);
  if (placed.length === 0) {
    return [
      {
        id: "unsorted:day",
        kind: "unsorted",
        label: "未归类",
        caption: "待挂地点",
        photoCount: unsorted.length,
        thumbUrl: firstThumb(unsorted),
        unsortedScope: "day",
        photoIds: unsorted.map((photo) => photo.id),
        lane: "axis",
      },
    ];
  }

  const buckets: PhotoAsset[][] = Array.from({ length: placed.length + 1 }, () => []);
  for (const photo of unsorted) {
    const capturedMs = parseIsoMs(photo.captured_at);
    let index = placed.length;
    if (capturedMs != null) {
      const hit = placed.findIndex((row) => capturedMs < row.sortMs);
      if (hit >= 0) index = hit;
    }
    buckets[index].push(photo);
  }

  const beads: SpineBead[] = [];
  for (let index = 0; index <= placed.length; index += 1) {
    const shots = buckets[index];
    if (shots.length > 0) {
      const beforeLabel = index === 0 ? null : placed[index - 1].bead.label;
      const afterLabel = index === placed.length ? null : placed[index].bead.label;
      beads.push(makeGapBead(index, shots, beforeLabel, afterLabel));
    }
    if (index < placed.length) beads.push(placed[index].bead);
  }
  return beads;
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
  const placed = rows.map((row) => {
    if (row.bead.kind !== "visit") return { sortMs: row.sortMs, bead: row.bead };
    const lane: SpineLane = visitOrdinal % 2 === 0 ? "above" : "below";
    visitOrdinal += 1;
    return { sortMs: row.sortMs, bead: { ...row.bead, lane } };
  });

  const beads = interleaveUnsortedGaps(
    placed,
    photosForDayUnsorted(photos, chapterKey, confirmedIds),
  );

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
      photoIds: tripUnsorted.map((photo) => photo.id),
      lane: "axis",
    });
  }

  return beads;
}

export function planDayIndexForChapter(days: DayView[], chapterKey: string): number {
  const index = days.findIndex((day) => dayKey(day.date) === chapterKey);
  return index >= 0 ? index : 0;
}

export function buildOtherDayGhosts(input: {
  activeKey: string | null;
  chapters: RecallChapter[];
  days: DayView[];
  photos: PhotoAsset[];
  confirmedStops: VisitStop[];
}): RecallGhostPin[] {
  const { activeKey, chapters, days, photos, confirmedStops } = input;
  if (!activeKey || chapters.length < 2) return [];
  const lastKey = chapters[chapters.length - 1]?.key ?? null;
  const pins: RecallGhostPin[] = [];
  const seenItems = new Set<string>();

  for (const day of days) {
    for (const item of day.items ?? []) {
      if (seenItems.has(item.id) || item.lat == null || item.lng == null) continue;
      seenItems.add(item.id);
      if (photosForItemOnChapter(photos, item.id, activeKey).length > 0) continue;
      const other = chapters.find(
        (chapter) =>
          chapter.key !== activeKey && photosForItemOnChapter(photos, item.id, chapter.key).length > 0,
      );
      if (!other) continue;
      const shots = photosForItemOnChapter(photos, item.id, other.key);
      pins.push({
        id: `ghost:item:${item.id}`,
        kind: "plan",
        chapterKey: other.key,
        place_name: item.poi_name,
        lat: item.lat,
        lng: item.lng,
        count: shots.length,
        thumbUrl: firstThumb(shots),
        itemId: item.id,
      });
    }
  }

  for (const stop of confirmedStops) {
    if (stop.status !== "confirmed" || stop.lat == null || stop.lng == null) continue;
    const key = visitStopChapterKey(stop) ?? lastKey;
    if (!key || key === activeKey) continue;
    const shots = photosForVisitStop(photos, stop.id);
    pins.push({
      id: `ghost:visit:${stop.id}`,
      kind: "visit",
      chapterKey: key,
      place_name: stop.place_name,
      lat: stop.lat,
      lng: stop.lng,
      count: shots.length || stop.photo_count,
      thumbUrl: firstThumb(shots) ?? firstThumb(stop.photos),
      visitStopId: stop.id,
    });
  }

  return pins;
}
