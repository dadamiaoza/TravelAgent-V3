import type { DayView } from "@/lib/types";
import ItineraryItemCard from "@/components/ItineraryItemCard";
import {
  useReoptimizeItineraryDay,
  useCreateItineraryItem,
} from "@/hooks/useItineraryMutations";
import { useTripStore } from "@/stores/tripStore";

export default function ItineraryDayCard({
  day,
  tripId,
  focusedItemId,
  onSelectItem,
}: {
  day: DayView;
  tripId: string;
  focusedItemId?: string | null;
  onSelectItem?: (itemId: string) => void;
}) {
  const updateTripLocally = useTripStore((s) => s.updateTripLocally);
  const reoptimize = useReoptimizeItineraryDay(tripId);
  const createItem = useCreateItineraryItem(tripId);
  const items = day.items ?? [];

  function moveItem(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= items.length) return;

    const nextItems = [...items];
    [nextItems[index], nextItems[target]] = [nextItems[target], nextItems[index]];
    const renumberedItems = nextItems.map((it, idx) => ({ ...it, seq: idx + 1 }));
    updateTripLocally((trip) => {
      if (!trip?.days) return trip;
      return {
        ...trip,
        days: trip.days.map((d) =>
          d.id === day.id ? { ...d, items: renumberedItems } : d,
        ),
      };
    });
  }

  return (
    <article className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="sticky top-0 z-10 mb-3 flex items-center justify-between border-b border-gray-100 bg-white pb-2">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-gray-900">Day {day.day_index}</h2>
          {(day.items ?? []).some((item) => item.is_scenic) && (
            <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700">
              含景区
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">{day.date}</span>
          <button
            type="button"
            onClick={() => {
              const name = window.prompt("新增地点名称");
              if (name?.trim()) {
                createItem.mutate({ day_id: day.id, poi_name: name.trim() });
              }
            }}
            disabled={createItem.isPending}
            className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-50"
          >
            新增地点
          </button>
          <button
            type="button"
            onClick={() => reoptimize.mutate(day.id)}
            disabled={reoptimize.isPending || items.length < 2}
            className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-50"
          >
            {reoptimize.isPending ? "重算中…" : "重新计算路线"}
          </button>
        </div>
      </div>

      {items.length > 0 ? (
        <div className="space-y-2">
          {items.map((item, index) => (
            <div
              key={item.id}
              id={`itinerary-item-${item.id}`}
              className="flex items-start gap-1"
            >
              <div className="flex flex-col items-center gap-1 pt-2">
                <button
                  type="button"
                  onClick={() => moveItem(index, -1)}
                  disabled={index === 0 || reoptimize.isPending}
                  className="rounded border px-1 text-xs text-gray-500 hover:bg-gray-100 disabled:opacity-30"
                  title="上移"
                >
                  ↑
                </button>
                <button
                  type="button"
                  onClick={() => moveItem(index, 1)}
                  disabled={index === items.length - 1 || reoptimize.isPending}
                  className="rounded border px-1 text-xs text-gray-500 hover:bg-gray-100 disabled:opacity-30"
                  title="下移"
                >
                  ↓
                </button>
              </div>
              <div className="flex-1">
                <ItineraryItemCard
                  item={item}
                  tripId={tripId}
                  sequence={index + 1}
                  selected={focusedItemId === item.id}
                  onSelect={() => onSelectItem?.(item.id)}
                />
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
