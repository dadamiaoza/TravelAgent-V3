/**
 * 「我的行程」分区。
 *
 * T 是目的地当地日历日：优先行程上的 IANA `timezone`，否则按城市/目的地
 * 映射（见 destinationTimezones.ts）。映射不到时才退回浏览者本地日。
 *
 * `?asOf=YYYY-MM-DD` 冻结同一个日历日，方便演示矩阵。
 * `?asOf=` 带时间的瞬间会按每条行程的目的地时区换算成日历日。
 */
import { timezoneForPlace } from "./destinationTimezones";

export type TimePartition = "upcoming" | "ongoing" | "past" | "undated";

export type LibraryFilter = "all" | TimePartition;

export interface LibraryTrip {
  id: string;
  destination: string;
  city?: string | null;
  timezone?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  people_count?: number | null;
  place_count?: number | null;
  status: string;
  created_at?: string | null;
  cover_url?: string | null;
  degradations?: string[] | null;
}

const FILTERS: { id: LibraryFilter; label: string }[] = [
  { id: "all", label: "全部" },
  { id: "upcoming", label: "即将出发" },
  { id: "ongoing", label: "进行中" },
  { id: "past", label: "往期" },
  { id: "undated", label: "未定日期" },
];

export function libraryFilters(): { id: LibraryFilter; label: string }[] {
  return FILTERS;
}

export function filterLabel(filter: LibraryFilter): string {
  return FILTERS.find((item) => item.id === filter)?.label ?? "全部";
}

/** Viewer-local calendar day. Used only when the destination timezone is unknown. */
export function viewerLocalDay(now: Date = new Date()): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function parseAsOf(raw: string | null): string | null {
  if (!raw || !/^\d{4}-\d{2}-\d{2}$/.test(raw)) return null;
  const [year, month, day] = raw.split("-").map(Number);
  const probe = new Date(year, month - 1, day);
  if (
    probe.getFullYear() !== year ||
    probe.getMonth() !== month - 1 ||
    probe.getDate() !== day
  ) {
    return null;
  }
  return raw;
}

export function resolvedTimezone(
  trip: Pick<LibraryTrip, "timezone" | "city" | "destination">,
): string | null {
  const stored = trip.timezone?.trim();
  if (stored) {
    try {
      Intl.DateTimeFormat("en-US", { timeZone: stored });
      return stored;
    } catch {
      // Invalid stored name: try the city map, then the viewer-local fallback.
    }
  }
  return timezoneForPlace(trip.city, trip.destination);
}

/** Calendar day of `instant` in an IANA zone. Null when the zone is unusable. */
export function formatCalendarDay(instant: Date, timeZone: string): string | null {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(instant);
    const year = parts.find((part) => part.type === "year")?.value;
    const month = parts.find((part) => part.type === "month")?.value;
    const day = parts.find((part) => part.type === "day")?.value;
    if (!year || !month || !day) return null;
    return `${year}-${month}-${day}`;
  } catch {
    return null;
  }
}

/**
 * Destination-local calendar day for one trip.
 * A date-only `asOf` freezes that day for every trip. An instant `asOf`
 * (or the live clock) is converted in the trip timezone when one is known.
 */
export function calendarDayForTrip(
  trip: Pick<LibraryTrip, "timezone" | "city" | "destination">,
  now: Date,
  asOf: string | null,
): string {
  const frozen = parseAsOf(asOf);
  if (frozen) return frozen;
  const instant = asOf && asOf.includes("T") ? new Date(asOf) : now;
  const when = Number.isNaN(instant.getTime()) ? now : instant;
  const zone = resolvedTimezone(trip);
  if (zone) {
    const local = formatCalendarDay(when, zone);
    if (local) return local;
  }
  return viewerLocalDay(when);
}

export function departureYear(start: string | null | undefined): number | null {
  if (!start || start.length < 4) return null;
  const year = Number(start.slice(0, 4));
  return Number.isInteger(year) ? year : null;
}

export function timePartition(
  start: string | null | undefined,
  end: string | null | undefined,
  today: string,
): TimePartition {
  if (!start) return "undated";
  const finish = end || start;
  if (start > today) return "upcoming";
  if (finish < today) return "past";
  return "ongoing";
}

/**
 * 全部 = 所选出发年的已定日期行程，再加上无出发日的行程（避免年份把它们悄悄丢掉）。
 * 即将出发 / 进行中 / 往期只含该年对应分区。
 * 未定日期忽略年份，只含无出发日的行程。
 */
export function tripVisible(
  trip: Pick<LibraryTrip, "start_date" | "end_date">,
  filter: LibraryFilter,
  year: number,
  today: string,
): boolean {
  const part = timePartition(trip.start_date, trip.end_date, today);
  if (filter === "undated") return part === "undated";
  if (part === "undated") return filter === "all";
  if (departureYear(trip.start_date) !== year) return false;
  if (filter === "all") return true;
  return part === filter;
}

export function inDepartureYear(
  trip: Pick<LibraryTrip, "start_date">,
  year: number,
): boolean {
  return departureYear(trip.start_date) === year;
}

export function countForFilter(
  trips: LibraryTrip[],
  filter: LibraryFilter,
  year: number,
  dayOf: (trip: LibraryTrip) => string,
): number {
  return trips.filter((trip) => tripVisible(trip, filter, year, dayOf(trip))).length;
}

export function yearChoices(trips: Pick<LibraryTrip, "start_date">[], today: string): number[] {
  const years = new Set<number>();
  const todayYear = Number(today.slice(0, 4));
  if (Number.isInteger(todayYear)) years.add(todayYear);
  for (const trip of trips) {
    const year = departureYear(trip.start_date);
    if (year != null) years.add(year);
  }
  const sorted = [...years].sort((a, b) => a - b);
  const min = sorted[0] - 1;
  const max = sorted[sorted.length - 1] + 1;
  const span: number[] = [];
  for (let year = min; year <= max; year += 1) span.push(year);
  return span;
}

export function inclusiveDayCount(start: string, end: string): number {
  const startMs = Date.parse(`${start}T00:00:00Z`);
  const endMs = Date.parse(`${end}T00:00:00Z`);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return 1;
  return Math.max(1, Math.round((endMs - startMs) / 86_400_000) + 1);
}

function shortDate(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${month}/${day}`;
}

export function cardTitle(trip: Pick<LibraryTrip, "destination" | "city">): string {
  const destination = trip.destination.trim();
  const city = trip.city?.trim();
  if (city && city !== destination && !destination.startsWith(city)) {
    return `${city} · ${destination}`;
  }
  return destination;
}

export function cardMeta(trip: Pick<LibraryTrip, "start_date" | "end_date" | "people_count">): string {
  const start = trip.start_date;
  const end = trip.end_date;
  if (!start || !end) return "日期待定 · 人数未定";
  const days = inclusiveDayCount(start, end);
  const people = trip.people_count ?? 1;
  const sameYear = start.slice(0, 4) === end.slice(0, 4);
  const range = sameYear
    ? `${shortDate(start)} – ${shortDate(end)}`
    : `${start.replace(/-/g, "/")} – ${end.replace(/-/g, "/")}`;
  return `${range} · ${days} 天 · ${people} 人`;
}

export type GenerationBadge = "planning" | "retry" | "draft";

export function generationBadge(status: string): GenerationBadge | null {
  if (status === "generating") return "planning";
  if (status === "generation_failed") return "retry";
  if (status === "draft") return "draft";
  return null;
}

export function badgeLabel(badge: GenerationBadge): string {
  if (badge === "planning") return "规划中";
  if (badge === "retry") return "可重试";
  return "草稿";
}

export function secondaryMeta(
  trip: Pick<LibraryTrip, "status" | "place_count">,
): string {
  if (trip.status === "generating") return "规划中…";
  if (trip.status === "generation_failed") return "可重试";
  if (trip.status === "draft") return "尚未生成";
  const count = trip.place_count ?? 0;
  return `${count} 个地点`;
}

/** Generic cities from the status matrix. Not a personal itinerary. */
export const MATRIX_DEMO_TRIPS: LibraryTrip[] = [
  { id: "demo-a", destination: "京都", start_date: null, end_date: null, status: "draft", people_count: 1, place_count: 0 },
  { id: "demo-b", destination: "美食", city: "大阪", start_date: "2026-09-25", end_date: "2026-09-28", status: "generating", people_count: 2, place_count: 0 },
  { id: "demo-c", destination: "火锅", city: "成都", start_date: "2026-10-01", end_date: "2026-10-05", status: "generation_failed", people_count: 2, place_count: 0 },
  { id: "demo-d", destination: "周末", city: "杭州", start_date: "2026-05-01", end_date: "2026-05-05", status: "generated", people_count: 2, place_count: 8 },
  { id: "demo-e", destination: "跨年", city: "北海道", start_date: "2026-12-28", end_date: "2027-01-05", status: "generated", people_count: 2, place_count: 6 },
  { id: "demo-f", destination: "海岛", city: "厦门", start_date: "2026-11-10", end_date: "2026-11-14", status: "generated", people_count: 1, place_count: 5 },
  { id: "demo-g", destination: "秋日", city: "东京", start_date: "2026-09-20", end_date: "2026-09-28", status: "generated", people_count: 2, place_count: 7 },
  { id: "demo-gp", destination: "秋日", city: "东京", start_date: "2026-09-20", end_date: "2026-09-28", status: "generation_failed", people_count: 2, place_count: 0 },
];

const COVER_STOPS = [
  ["#dbeafe", "#bfdbfe"],
  ["#fce7f3", "#fbcfe8"],
  ["#d1fae5", "#a7f3d0"],
  ["#ffedd5", "#fed7aa"],
  ["#e0e7ff", "#c7d2fe"],
  ["#fef3c7", "#fde68a"],
  ["#ccfbf1", "#99f6e4"],
  ["#fae8ff", "#f5d0fe"],
];

/** Gradient used when the trip has no single cover photo. */
export function coverBackground(trip: Pick<LibraryTrip, "city" | "destination">): string {
  const key = `${trip.city || ""} ${trip.destination}`;
  let hash = 0;
  for (const char of key) hash = (hash + char.charCodeAt(0)) % COVER_STOPS.length;
  const [from, to] = COVER_STOPS[hash];
  return `linear-gradient(135deg, ${from}, ${to})`;
}
