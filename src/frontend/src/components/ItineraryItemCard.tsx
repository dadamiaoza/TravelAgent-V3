import type { ItineraryItem } from "@/lib/types";

// 把后端可能返回的英文交通方式转成中文展示
const TRANSPORT_LABELS: Record<string, string> = {
  walking: "步行",
  transit: "公交/地铁",
  driving: "驾车",
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

export default function ItineraryItemCard({ item }: { item: ItineraryItem }) {
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

  return (
    <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-gray-900">{item.poi_name}</p>
          <p className="mt-1 text-xs text-gray-500">{buildBrief(item)}</p>
        </div>
        <span className="shrink-0 text-xs tabular-nums text-gray-500">
          {timeText}
        </span>
      </div>
    </div>
  );
}
