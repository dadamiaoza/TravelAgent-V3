import type { DayView } from "@/lib/types";
import ItineraryItemCard from "@/components/ItineraryItemCard";
import {
  useReorderItineraryDay,
  useReoptimizeItineraryDay,
  useRegenerateItineraryDay,
  useCreateItineraryItem,
} from "@/hooks/useItineraryMutations";

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
  const reorder = useReorderItineraryDay(tripId);
  const reoptimize = useReoptimizeItineraryDay(tripId);
  const regenerate = useRegenerateItineraryDay(tripId);
  const createItem = useCreateItineraryItem(tripId);
  const items = day.items ?? [];

  function moveItem(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= items.length) return;

    const nextIds = items.map((item) => item.id);
    [nextIds[index], nextIds[target]] = [nextIds[target], nextIds[index]];
    reorder.mutate(
      { dayId: day.id, itemIds: nextIds },
      {
        onSuccess: () => {
          // 排序成功后自动重算交通时间，保持地图/时间线一致
          reoptimize.mutate(day.id);
        },
      },
    );
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
          <button
            type="button"
            onClick={() => {
              if (window.confirm(`确定重新生成 Day${day.day_index} 吗？`)) {
                regenerate.mutate(day.id);
              }
            }}
            disabled={regenerate.isPending}
            className="rounded border border-orange-300 px-2 py-1 text-xs text-orange-600 hover:bg-orange-50 disabled:opacity-50"
          >
            {regenerate.isPending ? "生成中…" : "重新生成这天"}
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
