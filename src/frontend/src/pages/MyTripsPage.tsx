import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  badgeLabel,
  cardMeta,
  cardTitle,
  calendarDayForTrip,
  countForFilter,
  coverBackground,
  filterLabel,
  generationBadge,
  libraryFilters,
  MATRIX_DEMO_TRIPS,
  parseAsOf,
  resolvedTimezone,
  secondaryMeta,
  tripVisible,
  viewerLocalDay,
  yearChoices,
  type LibraryFilter,
  type LibraryTrip,
} from "@/lib/tripLibrary";
import { api } from "@/lib/api";

type LoadState = "loading" | "error" | "ready";

function initialYear(today: string, options: number[]): number {
  const todayYear = Number(today.slice(0, 4));
  if (options.includes(todayYear)) return todayYear;
  return options[options.length - 1] ?? todayYear;
}

export default function MyTripsPage() {
  const [params] = useSearchParams();
  const asOf = params.get("asOf");
  const frozenDay = parseAsOf(asOf);
  const now = useMemo(() => new Date(), []);
  const referenceToday = frozenDay ?? viewerLocalDay(now);
  const demo = params.get("demo");
  const [trips, setTrips] = useState<LibraryTrip[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [filter, setFilter] = useState<LibraryFilter>("all");
  const [year, setYear] = useState(() => Number(referenceToday.slice(0, 4)));
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (demo === "matrix" || demo === "empty") {
      setTrips(demo === "matrix" ? MATRIX_DEMO_TRIPS : []);
      setLoadState("ready");
      return;
    }
    let cancelled = false;
    setLoadState("loading");
    api
      .get<LibraryTrip[]>("/trips")
      .then((data) => {
        if (cancelled) return;
        setTrips(data);
        setLoadState("ready");
      })
      .catch(() => {
        if (!cancelled) setLoadState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey, demo]);

  const years = useMemo(() => yearChoices(trips, referenceToday), [trips, referenceToday]);
  const dayOf = useMemo(
    () => (trip: LibraryTrip) => calendarDayForTrip(trip, now, asOf),
    [now, asOf],
  );
  const usesViewerFallback = trips.some((trip) => resolvedTimezone(trip) == null);

  useEffect(() => {
    if (!years.includes(year)) setYear(initialYear(referenceToday, years));
  }, [years, year, referenceToday]);

  const visible = useMemo(
    () => trips.filter((trip) => tripVisible(trip, filter, year, dayOf(trip))),
    [trips, filter, year, dayOf],
  );

  const yearIndex = Math.max(0, years.indexOf(year));
  const libraryEmpty = loadState === "ready" && trips.length === 0;
  const filterEmpty = loadState === "ready" && trips.length > 0 && visible.length === 0;

  return (
    <div className="min-h-screen bg-chrome text-ink lg:grid lg:grid-cols-[220px_1fr]">
      <aside className="hidden border-r border-line-tertiary bg-chrome px-3 py-5 lg:block">
        <Link
          to="/"
          className="mb-6 flex h-8 w-20 items-center justify-center rounded-md bg-elevated text-xs text-ink-tertiary"
        >
          Logo
        </Link>
        <Link to="/" className="mb-1 block rounded-lg px-3 py-2 text-sm text-ink-secondary hover:bg-elevated">
          创作
        </Link>
        <Link
          to="/trips"
          className="mb-3 flex items-center justify-between rounded-lg border border-line-tertiary bg-elevated px-3 py-2 text-sm font-medium"
          aria-current="page"
        >
          我的行程
          <span className="text-xs font-normal text-ink-tertiary">{trips.length}</span>
        </Link>
        <div className="space-y-0.5">
          {libraryFilters().map((item) => {
            const count = countForFilter(trips, item.id, year, dayOf);
            const active = filter === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setFilter(item.id)}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm ${
                  active ? "bg-elevated font-medium text-ink" : "text-ink-secondary hover:bg-elevated"
                }`}
              >
                {item.label}
                <span className="text-xs text-ink-tertiary">{count}</span>
              </button>
            );
          })}
        </div>
        <p className="mt-8 border-t border-line-tertiary px-3 pt-4 text-xs text-ink-tertiary">
          本设备上的行程
        </p>
      </aside>

      <main className="px-4 pb-24 pt-5 sm:px-6 lg:px-8 lg:pb-10">
        <div className="mb-4 flex items-end justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.08em] text-ink-tertiary">Library</p>
            <h1 className="text-3xl font-semibold tracking-tight">我的行程</h1>
            {demo === "matrix" && (
              <p className="mt-1 text-xs text-ink-tertiary">
                演示数据 · {frozenDay ? `基准日 ${frozenDay}` : "按目的地当地日历日"}
              </p>
            )}
            {usesViewerFallback && !frozenDay && (
              <p className="mt-1 text-xs text-ink-tertiary">
                没有目的地时区的行程，按你所在地的日期分区。
              </p>
            )}
          </div>
          <div className="flex items-center gap-1 rounded-full border border-line-tertiary bg-elevated px-1.5 py-1 text-sm">
            <button
              type="button"
              aria-label="上一年"
              disabled={yearIndex <= 0}
              onClick={() => setYear(years[yearIndex - 1])}
              className="flex h-7 w-7 items-center justify-center rounded-full text-ink-secondary disabled:opacity-30"
            >
              ‹
            </button>
            <span className="min-w-12 text-center font-medium">{year}</span>
            <button
              type="button"
              aria-label="下一年"
              disabled={yearIndex >= years.length - 1}
              onClick={() => setYear(years[yearIndex + 1])}
              className="flex h-7 w-7 items-center justify-center rounded-full text-ink-secondary disabled:opacity-30"
            >
              ›
            </button>
          </div>
        </div>

        <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
          {libraryFilters().map((item) => {
            const active = filter === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setFilter(item.id)}
                className={`shrink-0 rounded-full border px-3 py-1 text-xs ${
                  active
                    ? "border-blue-200 bg-blue-50 text-blue-700"
                    : "border-line-tertiary bg-elevated text-ink-secondary"
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </div>

        {loadState === "loading" && (
          <p className="rounded-2xl border border-dashed border-line-tertiary bg-elevated px-4 py-10 text-center text-sm text-ink-tertiary">
            正在加载行程…
          </p>
        )}

        {loadState === "error" && (
          <div role="alert" className="rounded-2xl border border-line-tertiary bg-rose-50 px-4 py-10 text-center">
            <p className="text-sm text-rose-700">暂时没能加载行程，请稍后重试</p>
            <button
              type="button"
              onClick={() => setReloadKey((key) => key + 1)}
              className="mt-4 rounded-full bg-blue-600 px-4 py-2 text-sm text-white"
            >
              重试
            </button>
          </div>
        )}

        {libraryEmpty && <LibraryEmpty />}

        {filterEmpty && (
          <div className="rounded-2xl border border-dashed border-line-tertiary bg-elevated px-4 py-16 text-center">
            <h2 className="text-base font-semibold">这个筛选下还没有行程</h2>
            <p className="mx-auto mt-2 max-w-xs text-sm text-ink-tertiary">
              {filter === "undated"
                ? "还没有未定日期的行程。换一个分区看看。"
                : `${year} 年的「${filterLabel(filter)}」是空的。换一个分区或年份看看。`}
            </p>
          </div>
        )}

        {loadState === "ready" && visible.length > 0 && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {visible.map((trip) => (
              <TripCard key={trip.id} trip={trip} />
            ))}
          </div>
        )}
      </main>

      <nav className="fixed inset-x-0 bottom-0 grid grid-cols-2 border-t border-line-tertiary bg-elevated py-2 text-center text-[11px] lg:hidden">
        <Link to="/" className="text-ink-tertiary">
          <span className="mx-auto mb-1 block h-4 w-4 rounded bg-chrome" />
          创作
        </Link>
        <Link to="/trips" className="font-semibold text-ink" aria-current="page">
          <span className="mx-auto mb-1 block h-4 w-4 rounded bg-chrome" />
          行程
        </Link>
      </nav>
    </div>
  );
}

function LibraryEmpty() {
  return (
    <div className="flex min-h-[360px] flex-col items-center justify-center rounded-2xl border border-dashed border-line-tertiary bg-elevated px-6 py-12 text-center">
      <div
        className="mb-4 flex h-[72px] w-24 items-center justify-center rounded-lg text-[11px] text-ink-tertiary"
        style={{ background: "linear-gradient(135deg, #e5e7eb, #f3f4f6)" }}
      >
        轻量插画
      </div>
      <h2 className="text-base font-semibold">还没有行程</h2>
      <p className="mt-2 max-w-[280px] text-sm text-ink-tertiary">
        用一句话或粘贴攻略开始第一段旅程。生成后会出现在这里。
      </p>
      <Link
        to="/"
        className="mt-4 rounded-full bg-blue-600 px-4 py-2 text-sm text-white"
      >
        去创作
      </Link>
    </div>
  );
}

function TripCard({ trip }: { trip: LibraryTrip }) {
  const badge = generationBadge(trip.status);
  const cover = trip.cover_url?.trim() || "";
  return (
    <Link
      to={`/trips/${trip.id}`}
      className="overflow-hidden rounded-xl border border-line-tertiary bg-elevated shadow-sm transition hover:border-[rgb(20_20_20/0.16)]"
    >
      <div className="relative h-[108px] md:h-[132px]" style={{ background: coverBackground(trip) }}>
        {cover ? (
          <img src={cover} alt="" className="absolute inset-0 h-full w-full object-cover" />
        ) : (
          <span className="absolute inset-0 flex items-center justify-center text-xs text-ink-tertiary">
            封面图 / 目的地
          </span>
        )}
        {badge && (
          <span
            className={`absolute left-2 top-2 rounded-full border px-2 py-0.5 text-[11px] ${
              badge === "retry"
                ? "border-rose-200 bg-rose-50 text-rose-700"
                : badge === "planning"
                  ? "border-blue-200 bg-blue-50 text-blue-800"
                  : "border-line-tertiary bg-elevated text-ink-secondary"
            }`}
          >
            {badgeLabel(badge)}
          </span>
        )}
      </div>
      <div className="px-3 py-3">
        <h2 className="truncate text-[15px] font-semibold">{cardTitle(trip)}</h2>
        <p className="mt-1 text-xs text-ink-secondary">{cardMeta(trip)}</p>
        <div className="mt-2.5 flex items-center justify-between text-[11px] text-ink-tertiary">
          <span>{secondaryMeta(trip)}</span>
          <span>点击进入 →</span>
        </div>
      </div>
    </Link>
  );
}
