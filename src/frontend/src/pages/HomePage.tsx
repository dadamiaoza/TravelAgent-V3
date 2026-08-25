import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import TripPromptForm from "@/components/TripPromptForm";
import { api } from "@/lib/api";
import type { Trip } from "@/lib/types";

const PAGE_SIZE = 5;

export default function HomePage() {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [showTrips, setShowTrips] = useState(false);
  const [page, setPage] = useState(1);

  useEffect(() => {
    api.get<Trip[]>("/trips")
      .then(setTrips)
      .catch(() => {
        // 列表加载失败不阻塞页面
      });
  }, []);

  const totalPages = Math.max(1, Math.ceil(trips.length / PAGE_SIZE));
  const pageTrips = trips.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <main className="max-w-2xl mx-auto p-8">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-gray-900">AI 旅行规划助手</h1>
        <p className="mt-2 text-gray-500">
          创建新行程，或从已有行程继续规划
        </p>
      </div>

      <TripPromptForm />

      {trips.length > 0 && (
        <section className="mt-8 rounded-lg border bg-white p-4 shadow-sm">
          <button
            type="button"
            onClick={() => setShowTrips((prev) => !prev)}
            className="flex w-full items-center justify-between text-left"
          >
            <span className="font-semibold text-gray-900">
              已有行程（{trips.length}）
            </span>
            <span className="text-sm text-gray-500">
              {showTrips ? "收起 ▲" : "展开 ▼"}
            </span>
          </button>

          {showTrips && (
            <div className="mt-4">
              <div className="space-y-2">
                {pageTrips.map((trip) => (
                  <Link
                    key={trip.id}
                    to={`/trips/${trip.id}`}
                    className="block rounded-lg border px-4 py-3 shadow-sm transition hover:border-blue-400"
                  >
                    <p className="font-medium text-gray-900">{trip.destination}</p>
                    <p className="text-xs text-gray-500">
                      {trip.start_date} 至 {trip.end_date} · {trip.status}
                    </p>
                  </Link>
                ))}
              </div>

              {totalPages > 1 && (
                <div className="mt-4 flex items-center justify-between text-sm">
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="rounded border px-3 py-1 disabled:opacity-40"
                  >
                    上一页
                  </button>
                  <span className="text-gray-500">
                    第 {page} / {totalPages} 页
                  </span>
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    className="rounded border px-3 py-1 disabled:opacity-40"
                  >
                    下一页
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      <div className="mt-6 text-center">
        <Link to="/sources" className="text-blue-600 hover:underline">
          去解析攻略
        </Link>
      </div>
    </main>
  );
}
