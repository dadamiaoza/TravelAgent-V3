import { useState } from "react";
import type { ItineraryItem } from "@/lib/types";
import { useDeleteItineraryItem } from "@/hooks/useItineraryMutations";
import { useTripStore } from "@/stores/tripStore";

const TRANSPORT_LABELS: Record<string, string> = {
  walking: "🚶 步行",
  hiking: "🥾 登山/步道",
  shuttle: "🚐 景区接驳车",
  cable_car: "🚡 索道/缆车",
  transit: "🚌 公交/地铁",
  driving: "🚗 驾车",
};

const BEST_TIME_LABELS: Record<string, string> = {
  morning: "上午",
  afternoon: "下午",
  evening: "晚上",
  all_day: "全天",
};

function formatTime(value?: string | null): string {
  if (!value) return "";
  return value.slice(0, 5);
}

function shortHours(value?: string | null): string | null {
  if (!value) return null;
  const compact = value.replace(/\s+/g, " ").trim();
  const match = compact.match(/\d{1,2}:\d{2}\s*[-–~至到]\s*\d{1,2}:\d{2}/);
  if (match) return match[0].replace(/[至到]/, "-");
  return compact.length > 40 ? `${compact.slice(0, 39)}…` : compact;
}

function formatDuration(hours?: number | null): string | null {
  if (hours == null || Number.isNaN(hours) || hours <= 0) return null;
  const label = Number.isInteger(hours) ? String(hours) : hours.toFixed(1);
  return `建议 ${label}h`;
}

function buildSummary(item: ItineraryItem): string {
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

  const duration = formatDuration(item.suggested_duration_h);
  if (duration) parts.push(duration);

  const best = item.best_time ? BEST_TIME_LABELS[item.best_time] ?? item.best_time : null;
  if (best) parts.push(best);

  if (item.cost_note) {
    parts.push(item.cost_note);
  } else if (item.cost_estimate != null) {
    parts.push(`预计花费 ¥${item.cost_estimate}`);
  }

  if (item.opening_hours) {
    const hours = shortHours(item.opening_hours);
    if (hours) parts.push(hours);
  }

  return parts.join(" · ");
}

function isScenicItem(item: ItineraryItem): boolean {
  if (item.is_scenic != null) return item.is_scenic;
  const text = `${item.poi_name ?? ""} ${item.poi_type ?? ""}`;
  return /景区|风景名胜|索道|缆车|登山步道|游步道|国家级景点|山/.test(text);
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
  const deleteItem = useDeleteItineraryItem(tripId);
  const updateTripLocally = useTripStore((s) => s.updateTripLocally);

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
    updateTripLocally((trip) => {
      if (!trip?.days) return trip;
      return {
        ...trip,
        days: trip.days.map((day) => ({
          ...day,
          items: day.items.map((it) =>
            it.id === item.id
              ? {
                  ...it,
                  poi_name: poiName.trim() || it.poi_name,
                  start_time: toTimeValue(startTime),
                  end_time: toTimeValue(endTime),
                  notes: notes.trim() || null,
                }
              : it,
          ),
        })),
      };
    });
    setIsEditing(false);
  }

  const isScenic = isScenicItem(item);
  const summary = buildSummary(item);
  const hasDetails = Boolean(item.visit_tips || item.travel_advice || item.notes);

  const inputClass =
    "w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none";

  return (
    <div
      className={`rounded-md border p-3 transition ${
        isScenic
          ? "border-green-300 bg-green-50"
          : selected
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
                <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white ${isScenic ? "bg-green-600" : "bg-blue-600"}`}>
                  {sequence}
                </span>
              )}
              <div>
                <p className="text-sm font-medium text-gray-900">
                  {item.poi_name}
                  {isScenic && (
                    <span className="ml-1 rounded bg-green-100 px-1 py-0.5 text-xs text-green-700">
                      景区
                    </span>
                  )}
                </p>
                {summary && <p className="mt-1 text-xs text-gray-500">{summary}</p>}
                {item.fact_warning && (
                  <p className="mt-1 text-xs text-amber-700">⚠ {item.fact_warning}</p>
                )}
                {hasDetails && (
                  <details
                    className="mt-1"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <summary className="cursor-pointer text-xs text-blue-600 hover:underline">
                      怎么玩
                    </summary>
                    <div className="mt-1 space-y-1">
                      {item.visit_tips && (
                        <p className="text-xs text-gray-700">{item.visit_tips}</p>
                      )}
                      {item.travel_advice && (
                        <p className="text-xs text-amber-700">交通：{item.travel_advice}</p>
                      )}
                      {item.notes && (
                        <p className="text-xs text-gray-600">备注：{item.notes}</p>
                      )}
                    </div>
                  </details>
                )}
              </div>
            </div>
            <span className="shrink-0 text-xs tabular-nums text-gray-500">
              {timeText}
            </span>
          </div>
          <div className="mt-2 flex items-center gap-3">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setIsEditing(true);
              }}
              className="text-xs text-blue-600 hover:underline"
            >
              编辑
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                if (window.confirm(`确定删除“${item.poi_name}”吗？`)) {
                  deleteItem.mutate(item.id);
                }
              }}
              className="text-xs text-red-600 hover:underline disabled:opacity-50"
              disabled={deleteItem.isPending}
            >
              删除
            </button>
          </div>
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
              disabled={false}
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
