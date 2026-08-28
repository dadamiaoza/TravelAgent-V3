import { useEffect, useRef, useState } from "react";
import type { DayView, ItineraryItem } from "@/lib/types";
import {
  getAmapConfig,
  loadAMap,
  type AMapInfoWindow,
  type AMapMap,
  type AMapNamespace,
  type AMapOverlay,
} from "@/lib/amap";

interface TripMapProps {
  selectedDayIndex: number;
  onSelectDay: (index: number) => void;
  days: DayView[];
}

function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (char) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[char] ?? char,
  );
}

const TRANSPORT_LABELS: Record<string, string> = {
  walking: "🚶 步行",
  hiking: "🥾 登山/步道",
  shuttle: "🚐 景区接驳车",
  cable_car: "🚡 索道/缆车",
  transit: "🚌 公交/地铁",
  driving: "🚗 驾车",
};

function buildPopupContent(item: ItineraryItem): string {
  const timeText =
    item.start_time || item.end_time
      ? `${item.start_time?.slice(0, 5) ?? ""} - ${item.end_time?.slice(0, 5) ?? ""}`
      : "时间待定";
  const briefParts: string[] = [];
  if (item.transport_mode) {
    briefParts.push(escapeHtml(TRANSPORT_LABELS[item.transport_mode] ?? item.transport_mode));
  }
  if (item.travel_minutes != null) briefParts.push(`${item.travel_minutes} 分钟`);
  if (item.cost_estimate != null) briefParts.push(`预计花费 ¥${item.cost_estimate}`);
  if (item.travel_advice) briefParts.push(escapeHtml(item.travel_advice));

  return `
    <div style="min-width: 180px; padding: 4px 2px;">
      <div style="font-size: 14px; font-weight: 600; margin-bottom: 4px;">${escapeHtml(item.poi_name)}</div>
      <div style="font-size: 12px; color: #666;">${escapeHtml(timeText)}</div>
      ${briefParts.length ? `<div style="font-size: 12px; color: #666; margin-top: 2px;">${briefParts.join(" · ")}</div>` : ""}
    </div>
  `;
}

export default function TripMap({ days, selectedDayIndex, onSelectDay }: TripMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const overlaysRef = useRef<AMapOverlay[]>([]);
  const infoWindowRef = useRef<AMapInfoWindow | null>(null);

  const [amap, setAmap] = useState<AMapNamespace | null>(null);
  const [map, setMap] = useState<AMapMap | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { key, securityCode } = getAmapConfig();

  // 初始化地图：只创建一次
  useEffect(() => {
    if (!key || !securityCode) {
      setError("地图未配置：请在 frontend/.env 设置 VITE_AMAP_KEY 和 VITE_AMAP_SECURITY_CODE");
      return;
    }

    let cancelled = false;
    loadAMap()
      .then((AMapNS) => {
        if (cancelled || !containerRef.current) return;
        const instance = new AMapNS.Map(containerRef.current, {
          zoom: 12,
        });
        setAmap(AMapNS);
        setMap(instance);
      })
      .catch(() => {
        if (!cancelled) setError("高德地图加载失败，请检查网络和 Key");
      });

    return () => {
      cancelled = true;
    };
  }, [key, securityCode]);

  // 根据选中的 Day 渲染标记和直线
  useEffect(() => {
    if (!amap || !map) return;

    const day = days[selectedDayIndex];
    if (!day) return;

    // 关闭上一个信息窗，再清掉上一次的覆盖物
    infoWindowRef.current?.close();
    infoWindowRef.current = null;
    overlaysRef.current.forEach((overlay) => overlay.setMap(null));
    overlaysRef.current = [];

    const validItems = day.items.filter(
      (item) => item.lat != null && item.lng != null,
    );

    if (validItems.length === 0) {
      setError(`Day ${day.day_index} 暂无坐标数据`);
      return;
    }

    setError(null);

    const infoWindow = new amap.InfoWindow();
    infoWindowRef.current = infoWindow;

    validItems.forEach((item) => {
      const marker = new amap.Marker({
        position: [item.lng!, item.lat!],
        title: item.poi_name,
      });
      marker.on("click", () => {
        infoWindow.setContent(buildPopupContent(item));
        infoWindow.open(map, marker.getPosition());
      });
      marker.setMap(map);
      overlaysRef.current.push(marker);
    });

    // 每段路线：优先画后端返回的真实道路坐标；没有则回退为直线
    // 景区模式中未核实的索道/接驳车/步道用虚线示意，提示以现场指引为准
    const isScenic = day.route_type === "scenic";
    for (let i = 1; i < validItems.length; i++) {
      const prev = validItems[i - 1];
      const curr = validItems[i];
      const realPath = curr.route_polyline && curr.route_polyline.length > 0
        ? curr.route_polyline
        : [[prev.lng!, prev.lat!], [curr.lng!, curr.lat!]];
      const isUnverified = isScenic && !curr.route_verified;
      const strokeColor =
        curr.transport_mode === "transit"
          ? "#16a34a"
          : curr.transport_mode === "cable_car"
            ? "#ea580c"
            : curr.transport_mode === "shuttle"
              ? "#9333ea"
              : "#2563eb";

      const legLine = new amap.Polyline({
        path: realPath,
        strokeColor,
        strokeWeight: 4,
        strokeOpacity: isUnverified ? 0.6 : 0.85,
        strokeStyle: isUnverified ? "dashed" : "solid",
      });
      legLine.setMap(map);
      overlaysRef.current.push(legLine);
    }

    map.setFitView(overlaysRef.current);
  }, [amap, map, selectedDayIndex, days]);

  // 组件卸载时销毁地图，避免内存泄漏
  useEffect(() => {
    return () => {
      map?.destroy();
    };
  }, [map]);

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {days.map((day, index) => (
          <button
            key={day.id}
            type="button"
              onClick={() => onSelectDay(index)}
            className={`rounded-md px-3 py-1 text-sm ${
              selectedDayIndex === index
                ? "bg-blue-600 text-white"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            Day {day.day_index}
          </button>
        ))}
      </div>

      <div
        ref={containerRef}
        className="h-[400px] w-full rounded-md border border-gray-200 bg-gray-50"
      />

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </section>
  );
}
