import { Link } from "react-router-dom";
import type { Trip } from "@/lib/types";
import ItineraryDayCard from "@/components/ItineraryDayCard";
import TripMap from "@/components/TripMap";
import GuideImportPanel from "@/components/GuideImportPanel";

export default function TripDetail({ trip }: { trip: Trip }) {
  const days = trip.days ?? [];

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">
              {trip.destination} · {trip.start_date} 至 {trip.end_date}
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              {trip.people_count} 人 · 状态：{trip.status}
            </p>
          </div>
          <Link
            to={`/sources?tripId=${trip.id}`}
            className="shrink-0 rounded border border-blue-600 px-3 py-1 text-sm text-blue-600 hover:bg-blue-50"
          >
            导入攻略到当前行程
          </Link>
        </div>
      </section>

      {days.length > 0 && <TripMap days={days} />}

      {days.length > 0 ? (
        <div className="space-y-4">
          {days.map((day) => (
            <ItineraryDayCard key={day.id} day={day} tripId={trip.id} />
          ))}
        </div>
      ) : (
        <p className="rounded-lg border border-dashed border-gray-300 bg-white p-6 text-center text-gray-500">
          暂无行程内容
        </p>
      )}

      <GuideImportPanel tripId={trip.id} />
    </div>
  );
}
