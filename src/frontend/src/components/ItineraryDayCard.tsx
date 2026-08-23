import type { DayView } from "@/lib/types";
import ItineraryItemCard from "@/components/ItineraryItemCard";

export default function ItineraryDayCard({ day }: { day: DayView }) {
  const items = day.items ?? [];

  return (
    <article className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between border-b border-gray-100 pb-2">
        <h2 className="text-lg font-semibold text-gray-900">Day {day.day_index}</h2>
        <span className="text-sm text-gray-500">{day.date}</span>
      </div>

      {items.length > 0 ? (
        <div className="space-y-2">
          {items.map((item) => (
            <ItineraryItemCard key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <p className="text-sm text-gray-500">当天暂无安排</p>
      )}
    </article>
  );
}
