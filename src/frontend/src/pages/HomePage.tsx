import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import TripCreateForm from "@/components/TripCreateForm";
import { api } from "@/lib/api";
import type { Trip } from "@/lib/types";

export default function HomePage() {
  const [trips, setTrips] = useState<Trip[]>([]);

  useEffect(() => {
    api.get<Trip[]>("/trips")
      .then(setTrips)
      .catch(() => {
        // 列表加载失败不阻塞页面
      });
  }, []);

  return (
    <main className="max-w-2xl mx-auto p-8">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-gray-900">AI 旅行规划助手</h1>
        <p className="mt-2 text-gray-500">
          创建新行程，或从已有行程继续规划
        </p>
      </div>

      <TripCreateForm />

      {trips.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-3 text-lg font-semibold text-gray-900">已有行程</h2>
          <div className="space-y-2">
            {trips.slice(0, 10).map((trip) => (
              <Link
                key={trip.id}
                to={`/trips/${trip.id}`}
                className="block rounded-lg border bg-white px-4 py-3 shadow-sm transition hover:border-blue-400"
              >
                <p className="font-medium text-gray-900">{trip.destination}</p>
                <p className="text-xs text-gray-500">
                  {trip.start_date} 至 {trip.end_date} · {trip.status}
                </p>
              </Link>
            ))}
          </div>
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
