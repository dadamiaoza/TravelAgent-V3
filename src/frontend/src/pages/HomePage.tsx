import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import TripPromptForm from "@/components/TripPromptForm";
import { api } from "@/lib/api";
import { tripDateRangeLabel, tripStatusClassName, tripStatusLabel } from "@/lib/tripStatus";
import type { Trip } from "@/lib/types";

const PREVIEW_COUNT = 5;

function listNoteClass(alert: boolean): string {
  return `rounded-2xl border px-4 py-3.5 text-center text-sm shadow-sm ${
    alert
      ? "border-line-tertiary bg-rose-50 text-rose-700"
      : "border-dashed border-line-tertiary bg-elevated text-ink-tertiary"
  }`;
}

export default function HomePage() {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [listState, setListState] = useState<"loading" | "error" | "ready">("loading");
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get<Trip[]>("/trips")
      .then((data) => {
        if (cancelled) return;
        setTrips(data);
        setListState("ready");
      })
      .catch(() => {
        if (!cancelled) setListState("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const many = trips.length > PREVIEW_COUNT;
  const visibleTrips = many && !expanded ? trips.slice(0, PREVIEW_COUNT) : trips;

  return (
    <main className="min-h-screen bg-chrome px-5 py-16 sm:px-8 sm:py-20">
      <div className="mx-auto max-w-2xl">
        <div className="mb-12 text-center">
          <h1 className="text-4xl font-semibold tracking-tight text-ink">AI 旅行规划助手</h1>
          <p className="mt-3 text-sm text-ink-tertiary">
            用一句话，开始一段旅程
          </p>
        </div>

        <TripPromptForm />

        <section className="mt-14" aria-live="polite">
          {listState === "loading" && <p className={listNoteClass(false)}>正在加载行程…</p>}
          {listState === "error" && (
            <p role="alert" className={listNoteClass(true)}>
              暂时没能加载行程，请稍后重试
            </p>
          )}
          {listState === "ready" && trips.length === 0 && (
            <p className={listNoteClass(false)}>还没有行程</p>
          )}

          {listState === "ready" && trips.length > 0 && (
            <>
              <h2 className="px-1 text-sm text-ink-tertiary">
                已有行程（{trips.length}）
              </h2>

              <div className={`mt-3 space-y-2 ${expanded && many ? "max-h-96 overflow-y-auto pr-1" : ""}`}>
                {visibleTrips.map((trip) => (
                  <Link
                    key={trip.id}
                    to={`/trips/${trip.id}`}
                    className="flex items-center justify-between gap-3 rounded-2xl border border-line-tertiary bg-elevated px-4 py-3.5 shadow-sm transition hover:border-[rgb(20_20_20/0.16)]"
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium text-ink">{trip.destination}</span>
                      <span className="mt-0.5 block text-xs text-ink-tertiary">
                        {tripDateRangeLabel(trip.start_date, trip.end_date)}
                      </span>
                    </span>
                    <span
                      className={`shrink-0 rounded-full px-2.5 py-1 text-xs ${tripStatusClassName(trip.status)}`}
                    >
                      {tripStatusLabel(trip.status)}
                    </span>
                  </Link>
                ))}
              </div>

              {many && (
                <button
                  type="button"
                  onClick={() => setExpanded((open) => !open)}
                  className="mt-3 w-full text-center text-sm text-ink-tertiary hover:text-ink-secondary"
                >
                  {expanded ? "收起" : `展开其余 ${trips.length - PREVIEW_COUNT} 个`}
                </button>
              )}
            </>
          )}
        </section>

      </div>
    </main>
  );
}
