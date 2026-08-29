import { useState } from "react";
import type { ItineraryItem } from "@/lib/types";
import { useUpdateItineraryItem } from "@/hooks/useItineraryMutations";

// 把后端可能返回的英文交通方式转成中文 + 图标展示
const TRANSPORT_LABELS: Record<string, string> = {
  walking: "🚶 步行",
  hiking: "🥾 登山/步道",
  shuttle: "🚐 景区接驳车",
  cable_car: "🚡 索道/缆车",
  transit: "🚌 公交/地铁",
  driving: "🚗 驾车",
};

function formatTime(value?: string | null): string {
  if (!value) return "";
  // 后端返回可能是 "09:00:00" 或 "09:00"
  return value.slice(0, 5);
}

function buildBrief(item: ItineraryItem): string {
  const parts: string[] = [];
  const transport = item.transport_mode
    ? TRANSPORT_LABELS[item.transport_mode] ?? item.transport_mode
    : null;

  if (transport && item.travel_minutes != null) {
    parts.push(`${transport} ${item.travel_minutes} 分钟`);
  } else if (transport) {
    parts.push(transport);
  } else if (item.travel_minutes != null) {
    parts.push(`预计交通 ${item.travel_minutes} 分钟`);
  }

  if (item.cost_estimate != null) {
    parts.push(`预计花费 ¥${item.cost_estimate}`);
  }

  // 没有结构化补充信息时，也不显示“简介：无”这类生硬文案
  return parts.length > 0 ? parts.join(" · ") : "待补充详细信息";
}

export default function ItineraryItemCard({
  item,
  tripId,
  sequence,
  selected,
  onSelect,
}: {
  item: ItineraryItem;
  tripId: string;
  sequence?: number;
  selected?: boolean;
  onSelect?: () => void;
}) {
  const updateItem = useUpdateItineraryItem(tripId);

  const [isEditing, setIsEditing] = useState(false);
  const [poiName, setPoiName] = useState(item.poi_name);
  const [startTime, setStartTime] = useState(item.start_time?.slice(0, 5) ?? "");
  const [endTime, setEndTime] = useState(item.end_time?.slice(0, 5) ?? "");
  const [notes, setNotes] = useState(item.notes ?? "");

  const start = formatTime(item.start_time);
  const end = formatTime(item.end_time);
  const timeText =
    start && end
      ? `${start} - ${end}`
      : start
        ? `${start} 开始`
        : end
          ? `至 ${end}`
          : "时间待定";

  function toTimeValue(value: string): string | null {
    if (!value) return null;
    return value.length === 5 ? `${value}:00` : value;
  }

  function handleSave() {
    updateItem.mutate(
      {
        itemId: item.id,
        payload: {
          poi_name: poiName.trim() || item.poi_name,
          start_time: toTimeValue(startTime),
          end_time: toTimeValue(endTime),
          notes: notes.trim() || null,
        },
      },
      {
        onSuccess: () => setIsEditing(false),
      },
    );
  }

  const inputClass =
    "w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none";

  return (
    <div
      className={`rounded-md border p-3 transition ${
        selected
          ? "border-blue-500 bg-blue-50 shadow-sm"
          : "border-gray-200 bg-gray-50"
      } ${isEditing ? "" : "cursor-pointer hover:border-blue-300"}`}
      onClick={() => {
        if (!isEditing) onSelect?.();
      }}
    >
      {!isEditing ? (
        <>
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-2">
              {sequence != null && (
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-semibold text-white">
                  {sequence}
                </span>
              )}
              <div>
                <p className="text-sm font-medium text-gray-900">{item.poi_name}</p>
                <p className="mt-1 text-xs text-gray-500">{buildBrief(item)}</p>
              {item.travel_advice && (
                <p className="mt-1 text-xs text-amber-700">提示：{item.travel_advice}</p>
              )}
                {item.notes && (
                  <p className="mt-1 text-xs text-gray-600">备注：{item.notes}</p>
                )}
              </div>
            </div>
            <span className="shrink-0 text-xs tabular-nums text-gray-500">
              {timeText}
            </span>
          </div>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setIsEditing(true);
            }}
            className="mt-2 text-xs text-blue-600 hover:underline"
          >
            编辑
          </button>
        </>
      ) : (
        <div className="space-y-2">
          <div>
            <label className="mb-1 block text-xs text-gray-500">名称</label>
            <input
              value={poiName}
              onChange={(e) => setPoiName(e.target.value)}
              className={inputClass}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs text-gray-500">开始时间</label>
              <input
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-500">结束时间</label>
              <input
                type="time"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-gray-500">备注</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className={inputClass}
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={updateItem.isPending}
              className="rounded bg-blue-600 px-3 py-1 text-xs text-white disabled:opacity-60"
            >
              保存
            </button>
            <button
              type="button"
              onClick={() => setIsEditing(false)}
              className="rounded bg-gray-200 px-3 py-1 text-xs"
            >
              取消
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
