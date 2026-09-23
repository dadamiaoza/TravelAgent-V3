import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import TripPromptForm from "@/components/TripPromptForm";
import { api } from "@/lib/api";
import { tripStatusClassName, tripStatusLabel } from "@/lib/tripStatus";
import type { Trip } from "@/lib/types";

const PREVIEW_COUNT = 5;

export default function HomePage() {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    api.get<Trip[]>("/trips")
      .then(setTrips)
      .catch(() => {
        // 列表加载失败不阻塞页面
      });
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

        {trips.length > 0 && (
          <section className="mt-14">
            <h2 className="px-1 text-sm text-ink-tertiary">
              已有行程（{trips.length}）
            </h2>

            <div className={`mt-3 space-y-2 ${expanded && many ? "max-h-96 overflow-y-auto pr-1" : ""}`}>
              {visibleTrips.map((trip) => (
                <Link
                  key={trip.id}
                  to={`/trips/${trip.id}`}
                  className="flex items-center justify-between gap-3 rounded-2xl border border-line-tertiary bg-white px-4 py-3.5 transition hover:border-[rgb(20_20_20/0.16)]"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-ink">{trip.destination}</span>
                    <span className="mt-0.5 block text-xs text-ink-tertiary">
                      {trip.start_date} 至 {trip.end_date}
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
          </section>
        )}

        <p className="mt-12 text-center">
          <Link
            to="/sources"
            className="text-sm text-ink-tertiary underline-offset-4 hover:text-ink-secondary hover:underline"
          >
            去解析攻略
          </Link>
        </p>
      </div>
    </main>
  );
}
