import type { DayView } from "@/lib/types";
import ItineraryItemCard from "@/components/ItineraryItemCard";
import { useReorderItineraryDay } from "@/hooks/useItineraryMutations";

export default function ItineraryDayCard({
  day,
  tripId,
}: {
  day: DayView;
  tripId: string;
}) {
  const reorder = useReorderItineraryDay(tripId);
  const items = day.items ?? [];

  function moveItem(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= items.length) return;

    const nextIds = items.map((item) => item.id);
    [nextIds[index], nextIds[target]] = [nextIds[target], nextIds[index]];
    reorder.mutate({ dayId: day.id, itemIds: nextIds });
  }

  return (
    <article className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between border-b border-gray-100 pb-2">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-gray-900">Day {day.day_index}</h2>
          {day.route_type === "scenic" && (
            <span className="rounded bg-orange-100 px-2 py-0.5 text-xs text-orange-700">
              景区模式
            </span>
          )}
        </div>
        <span className="text-sm text-gray-500">{day.date}</span>
      </div>

      {items.length > 0 ? (
        <div className="space-y-2">
          {items.map((item, index) => (
            <div key={item.id} className="flex items-start gap-1">
              <div className="flex flex-col items-center gap-1 pt-2">
                <button
                  type="button"
                  onClick={() => moveItem(index, -1)}
                  disabled={index === 0 || reorder.isPending}
                  className="rounded border px-1 text-xs text-gray-500 hover:bg-gray-100 disabled:opacity-30"
                  title="上移"
                >
                  ↑
                </button>
                <button
                  type="button"
                  onClick={() => moveItem(index, 1)}
                  disabled={index === items.length - 1 || reorder.isPending}
                  className="rounded border px-1 text-xs text-gray-500 hover:bg-gray-100 disabled:opacity-30"
                  title="下移"
                >
                  ↓
                </button>
              </div>
              <div className="flex-1">
                <ItineraryItemCard item={item} tripId={tripId} />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-gray-500">当天暂无安排</p>
      )}
    </article>
  );
}
