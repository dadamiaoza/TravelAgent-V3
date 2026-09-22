import { useEffect, useRef, useState } from "react";
import type { DayView, ItineraryItem } from "@/lib/types";
import {
  getAmapConfig,
  loadAMap,
  type AMapInfoWindow,
  type AMapMap,
  type AMapMarker,
  type AMapNamespace,
  type AMapOverlay,
} from "@/lib/amap";

interface VisitStopPin {
  id: string;
  place_name: string;
  lat: number;
  lng: number;
  count: number;
  thumbUrl: string | null;
}

interface GhostPin {
  id: string;
  kind: "plan" | "visit";
  chapterKey: string;
  place_name: string;
  lat: number;
  lng: number;
  count: number;
  thumbUrl: string | null;
  itemId?: string;
  visitStopId?: string;
}

interface TripMapProps {
  selectedDayIndex: number;
  onSelectDay: (index: number) => void;
  days: DayView[];
  focusItemId?: string | null;
  onSelectItem?: (itemId: string) => void;
  photoByItem?: Record<string, { count: number; thumbUrl: string | null }>;
  variant?: "route" | "recall";
  hideDaySwitcher?: boolean;
  visitStops?: VisitStopPin[];
  focusVisitStopId?: string | null;
  onSelectVisitStop?: (stopId: string) => void;
  showPlanLayer?: boolean;
  ghostPins?: GhostPin[];
  onSelectGhost?: (pin: GhostPin) => void;
  /** Recall only: "day" fits current-chapter pins; "all" includes other-day ghosts. */
  fitScope?: "day" | "all";
  /** Recall only: bump when the user asks the camera to move (chapter or 显示其他拍摄日). */
  fitNonce?: number;
  fitKey?: string;
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
  walking: "步行",
  hiking: "登山/步道",
  shuttle: "景区接驳车",
  cable_car: "索道/缆车",
  transit: "公交/地铁",
  driving: "驾车",
};

function buildPopupContent(
  item: ItineraryItem,
  photo?: { count: number; thumbUrl: string | null },
): string {
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
  const photoHtml = photo?.thumbUrl
    ? `<img src="${escapeHtml(photo.thumbUrl)}" alt="${escapeHtml(item.poi_name)}" style="width:100%;height:72px;object-fit:cover;border-radius:8px;margin-top:6px;" />
       <div style="font-size:12px;color:#666;margin-top:4px;">${photo.count} 张照片</div>`
    : "";

  return `
    <div style="min-width: 180px; padding: 4px 2px;">
      <div style="font-size: 14px; font-weight: 600; margin-bottom: 4px;">${escapeHtml(item.poi_name)}</div>
      <div style="font-size: 12px; color: #666;">${escapeHtml(timeText)}</div>
      ${briefParts.length ? `<div style="font-size: 12px; color: #666; margin-top: 2px;">${briefParts.join(" · ")}</div>` : ""}
      ${photoHtml}
    </div>
  `;
}

function isScenicItem(item: ItineraryItem): boolean {
  if (item.is_scenic != null) return item.is_scenic;
  const text = `${item.poi_name ?? ""} ${item.poi_type ?? ""}`;
  return /景区|风景名胜|索道|缆车|登山步道|游步道|国家级景点|山/.test(text);
}

function seqMarkerContent(seq: number, focused: boolean, isScenic = false): string {
  const baseColor = isScenic ? "#059669" : "#0284c7";
  const color = focused ? "#ea580c" : baseColor;
  const size = focused ? 34 : 26;
  return `<div style="
    width: ${size}px;
    height: ${size}px;
    border-radius: 9999px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: ${focused ? 14 : 12}px;
    font-weight: 700;
    color: #fff;
    background: ${color};
    border: 2px solid #fff;
    box-shadow: ${focused ? "0 4px 12px rgba(0,0,0,0.35)" : "0 1px 4px rgba(15,23,42,0.2)"};
    cursor: pointer;
  ">${seq}</div>`;
}

function visitPinContent(
  photo: { count: number; thumbUrl: string | null } | undefined,
  focused: boolean,
  poiName: string,
): string {
  const size = focused ? 52 : 44;
  const ring = focused ? "#ea580c" : "#d97706";
  if (!photo?.thumbUrl) {
    return `<div style="width:${size}px;height:${size}px;border-radius:9999px;background:${ring};color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;border:3px solid #fff;box-shadow:0 4px 14px rgba(15,23,42,0.22);">${escapeHtml(poiName.slice(0, 2))}</div>`;
  }
  return `<div style="position:relative;width:${size}px;height:${size}px;cursor:pointer;">
    <img src="${escapeHtml(photo.thumbUrl)}" alt="${escapeHtml(poiName)}"
      style="width:${size}px;height:${size}px;border-radius:9999px;object-fit:cover;border:3px solid ${ring};box-shadow:0 4px 14px rgba(15,23,42,0.22);" />
    <span style="position:absolute;right:-4px;bottom:-4px;min-width:18px;padding:0 5px;border-radius:9999px;background:${ring};color:#fff;font-size:10px;font-weight:700;line-height:16px;text-align:center;border:2px solid #fff;">${photo.count}</span>
  </div>`;
}
function ghostPinContent(
  photo: { count: number; thumbUrl: string | null } | undefined,
  poiName: string,
  ring: string,
): string {
  const size = 32;
  if (!photo?.thumbUrl) {
    return `<div style="width:${size}px;height:${size}px;border-radius:9999px;background:${ring};color:#fff;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;border:2px solid #fff;box-shadow:0 2px 8px rgba(15,23,42,0.18);opacity:0.35;cursor:pointer;">${escapeHtml(poiName.slice(0, 2))}</div>`;
  }
  return `<div style="position:relative;width:${size}px;height:${size}px;cursor:pointer;opacity:0.35;">
    <img src="${escapeHtml(photo.thumbUrl)}" alt="${escapeHtml(poiName)}"
      style="width:${size}px;height:${size}px;border-radius:9999px;object-fit:cover;border:2px solid ${ring};box-shadow:0 2px 8px rgba(15,23,42,0.18);" />
    <span style="position:absolute;right:-4px;bottom:-4px;min-width:16px;padding:0 4px;border-radius:9999px;background:${ring};color:#fff;font-size:9px;font-weight:700;line-height:14px;text-align:center;border:2px solid #fff;">${photo.count}</span>
  </div>`;
}
function photoPinContent(
  seq: number,
  photo: { count: number; thumbUrl: string | null } | undefined,
  focused: boolean,
  poiName: string,
  faint = false,
): string {
  if (!photo?.thumbUrl) {
    const html = seqMarkerContent(seq, focused);
    return faint ? `<div style="opacity:0.4">${html}</div>` : html;
  }
  const size = focused ? 52 : 44;
  const opacity = faint ? "0.45" : "1";
  return `<div style="position:relative;width:${size}px;height:${size}px;cursor:pointer;opacity:${opacity};">
    <img src="${escapeHtml(photo.thumbUrl)}" alt="${escapeHtml(poiName)}"
      style="width:${size}px;height:${size}px;border-radius:9999px;object-fit:cover;border:3px solid #fff;box-shadow:0 4px 14px rgba(15,23,42,0.22);" />
    <span style="position:absolute;right:-4px;bottom:-4px;min-width:18px;padding:0 5px;border-radius:9999px;background:#0284c7;color:#fff;font-size:10px;font-weight:700;line-height:16px;text-align:center;border:2px solid #fff;">${photo.count}</span>
  </div>`;
}

export default function TripMap({
  days,
  selectedDayIndex,
  onSelectDay,
  focusItemId,
  onSelectItem,
  photoByItem,
  variant = "route",
  hideDaySwitcher = false,
  visitStops = [],
  focusVisitStopId = null,
  onSelectVisitStop,
  showPlanLayer = true,
  ghostPins = [],
  onSelectGhost,
  fitScope = "day",
  fitNonce = 0,
  fitKey = "",
}: TripMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const overlaysRef = useRef<AMapOverlay[]>([]);
  const dayFitOverlaysRef = useRef<AMapOverlay[]>([]);
  const ghostFitOverlaysRef = useRef<AMapOverlay[]>([]);
  const markersRef = useRef<Map<string, AMapMarker>>(new Map());
  const highlightTimerRef = useRef<number | null>(null);
  const infoWindowRef = useRef<AMapInfoWindow | null>(null);

  const [amap, setAmap] = useState<AMapNamespace | null>(null);
  const [map, setMap] = useState<AMapMap | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { key, securityCode } = getAmapConfig();
  const isRecall = variant === "recall";

  function findItem(itemId: string): ItineraryItem | undefined {
    return days.flatMap((day) => day.items ?? []).find((item) => item.id === itemId);
  }

  function markerHtml(item: ItineraryItem, focused: boolean): string {
    if (isRecall) {
      const hasPhotos = Boolean(photoByItem?.[item.id]?.count);
      return photoPinContent(item.seq, photoByItem?.[item.id], focused, item.poi_name, !hasPhotos);
    }
    return seqMarkerContent(item.seq, focused, isScenicItem(item));
  }

  function resetMarkerHighlights() {
    markersRef.current.forEach((marker, itemId) => {
      const item = findItem(itemId);
      if (item) marker.setContent(markerHtml(item, false));
    });
  }

  function focusMarker(itemId: string) {
    if (!map) return;
    const item = findItem(itemId);
    const marker = markersRef.current.get(itemId);
    if (!item || !marker || item.lat == null || item.lng == null) return;

    resetMarkerHighlights();
    marker.setContent(markerHtml(item, true));
    map.setZoomAndCenter(16, [item.lng!, item.lat!]);

    if (highlightTimerRef.current) window.clearTimeout(highlightTimerRef.current);
    highlightTimerRef.current = null;
    if (!isRecall) {
      highlightTimerRef.current = window.setTimeout(() => {
        marker.setContent(markerHtml(item, false));
        highlightTimerRef.current = null;
      }, 2500);
    }
  }

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

  useEffect(() => {
    if (!amap || !map) return;

    const day = days[selectedDayIndex];
    if (!day) return;

    infoWindowRef.current?.close();
    infoWindowRef.current = null;
    overlaysRef.current.forEach((overlay) => overlay.setMap(null));
    overlaysRef.current = [];
    dayFitOverlaysRef.current = [];
    ghostFitOverlaysRef.current = [];
    markersRef.current.clear();

    const validItems = (day.items ?? []).filter((item) => item.lat != null && item.lng != null);
    const uniqueLocated: ItineraryItem[] = [];
    const seenIds = new Set<string>();
    for (const item of days.flatMap((row) => row.items ?? [])) {
      if (item.lat == null || item.lng == null || seenIds.has(item.id)) continue;
      seenIds.add(item.id);
      uniqueLocated.push(item);
    }
    const ghostItemIds = new Set(
      ghostPins.filter((pin) => pin.itemId).map((pin) => pin.itemId as string),
    );
    const solidItems = isRecall
      ? uniqueLocated.filter((item) => Boolean(photoByItem?.[item.id]?.count))
      : validItems;
    const faintPlanItems =
      isRecall && showPlanLayer
        ? validItems.filter((item) => !photoByItem?.[item.id]?.count && !ghostItemIds.has(item.id))
        : [];
    const pinItems = isRecall ? [...solidItems, ...faintPlanItems] : validItems;

    if (pinItems.length === 0 && visitStops.length === 0 && ghostPins.length === 0) {
      setError(`Day ${day.day_index} 暂无坐标数据`);
      return;
    }

    setError(null);

    const infoWindow = isRecall ? null : new amap.InfoWindow();
    infoWindowRef.current = infoWindow;

    pinItems.forEach((item) => {
      const marker = new amap.Marker({
        position: [item.lng!, item.lat!],
        title: item.poi_name,
        content: markerHtml(item, focusItemId === item.id),
        zIndex: photoByItem?.[item.id]?.count ? 110 : 90,
      });
      marker.on("click", () => {
        if (infoWindow) {
          infoWindow.setContent(buildPopupContent(item, photoByItem?.[item.id]));
          infoWindow.open(map, marker.getPosition());
        }
        onSelectItem?.(item.id);
      });
      marker.setMap(map);
      markersRef.current.set(item.id, marker);
      overlaysRef.current.push(marker);
      const hasPhotos = Boolean(photoByItem?.[item.id]?.count);
      if (!isRecall || hasPhotos) {
        dayFitOverlaysRef.current.push(marker);
      }
    });

    const drawPlanLine = !isRecall || showPlanLayer;
    const isScenic = day.route_type === "scenic";
    if (drawPlanLine) {
      for (let i = 1; i < validItems.length; i++) {
        const prev = validItems[i - 1];
        const curr = validItems[i];
        const realPath =
          curr.route_polyline && curr.route_polyline.length > 0
            ? curr.route_polyline
            : [
                [prev.lng!, prev.lat!],
                [curr.lng!, curr.lat!],
              ];
        const isUnverified = isScenic && !curr.route_verified;
        const isScenicLeg = isScenicItem(prev) && isScenicItem(curr);
        const strokeColor = isScenicLeg
          ? "#059669"
          : curr.transport_mode === "transit"
            ? "#16a34a"
            : curr.transport_mode === "cable_car"
              ? "#ea580c"
              : curr.transport_mode === "shuttle"
                ? "#9333ea"
                : "#0284c7";

        const legLine = new amap.Polyline({
          path: realPath,
          strokeColor,
          strokeWeight: isRecall ? 5 : 4,
          strokeOpacity: isRecall ? 0.35 : isUnverified ? 0.6 : 0.85,
          strokeStyle: isRecall || isUnverified ? "dashed" : "solid",
        });
        legLine.setMap(map);
        overlaysRef.current.push(legLine);
      }
    }

    visitStops.forEach((stop) => {
      const marker = new amap.Marker({
        position: [stop.lng, stop.lat],
        title: stop.place_name,
        content: visitPinContent(
          { count: stop.count, thumbUrl: stop.thumbUrl },
          focusVisitStopId === stop.id,
          stop.place_name,
        ),
        zIndex: 120,
      });
      marker.on("click", () => {
        onSelectVisitStop?.(stop.id);
      });
      marker.setMap(map);
      markersRef.current.set(`visit:${stop.id}`, marker);
      overlaysRef.current.push(marker);
      dayFitOverlaysRef.current.push(marker);
    });

    ghostPins.forEach((pin) => {
      const marker = new amap.Marker({
        position: [pin.lng, pin.lat],
        title: `${pin.place_name} · 其他拍摄日`,
        content: ghostPinContent(
          { count: pin.count, thumbUrl: pin.thumbUrl },
          pin.place_name,
          pin.kind === "visit" ? "#d97706" : "#0284c7",
        ),
        zIndex: 70,
      });
      marker.on("click", () => onSelectGhost?.(pin));
      marker.setMap(map);
      markersRef.current.set(pin.id, marker);
      overlaysRef.current.push(marker);
      ghostFitOverlaysRef.current.push(marker);
    });

    if (!isRecall && overlaysRef.current.length > 0) {
      map.setFitView(overlaysRef.current);
    }
  }, [
    amap,
    map,
    selectedDayIndex,
    days,
    photoByItem,
    onSelectItem,
    isRecall,
    visitStops,
    onSelectVisitStop,
    showPlanLayer,
    ghostPins,
    onSelectGhost,
  ]);

  useEffect(() => {
    if (!map || !isRecall) return;
    if (focusItemId || focusVisitStopId) return;
    const targets =
      fitScope === "all"
        ? [...dayFitOverlaysRef.current, ...ghostFitOverlaysRef.current]
        : dayFitOverlaysRef.current;
    if (targets.length > 0) {
      map.setFitView(targets);
    }
  }, [map, isRecall, fitScope, fitNonce, fitKey, focusItemId, focusVisitStopId, selectedDayIndex]);

  useEffect(() => {
    if (!map || !focusItemId) {
      if (isRecall && map && !focusItemId) resetMarkerHighlights();
      return;
    }
    focusMarker(focusItemId);
  }, [focusItemId, map, selectedDayIndex, days, isRecall]);

  useEffect(() => {
    if (!map || !focusVisitStopId) {
      if (isRecall && map) {
        visitStops.forEach((stop) => {
          const marker = markersRef.current.get(`visit:${stop.id}`);
          if (marker) {
            marker.setContent(visitPinContent({ count: stop.count, thumbUrl: stop.thumbUrl }, false, stop.place_name));
          }
        });
      }
      return;
    }
    const stop = visitStops.find((item) => item.id === focusVisitStopId);
    if (!stop) return;
    map.setZoomAndCenter(16, [stop.lng, stop.lat]);
    const marker = markersRef.current.get(`visit:${stop.id}`);
    if (marker) {
      marker.setContent(visitPinContent({ count: stop.count, thumbUrl: stop.thumbUrl }, true, stop.place_name));
      if (highlightTimerRef.current) window.clearTimeout(highlightTimerRef.current);
      highlightTimerRef.current = null;
      if (!isRecall) {
        highlightTimerRef.current = window.setTimeout(() => {
          marker.setContent(visitPinContent({ count: stop.count, thumbUrl: stop.thumbUrl }, false, stop.place_name));
          highlightTimerRef.current = null;
        }, 2500);
      }
    }
  }, [focusVisitStopId, map, visitStops, isRecall]);

  useEffect(() => {
    return () => {
      if (highlightTimerRef.current) window.clearTimeout(highlightTimerRef.current);
      map?.destroy();
    };
  }, [map]);

  const daySwitcher = !hideDaySwitcher && (
    <div className={isRecall ? "pointer-events-auto flex flex-wrap items-center gap-2" : "mb-3 flex flex-wrap items-center gap-2"}>
      {days.map((day, index) => (
        <button
          key={day.id}
          type="button"
          onClick={() => onSelectDay(index)}
          className={`min-h-11 rounded-full px-4 text-sm font-medium transition duration-200 ${
            selectedDayIndex === index
              ? "bg-sky-600 text-white shadow-sm"
              : isRecall
                ? "bg-white/80 text-slate-700 backdrop-blur-md hover:bg-white"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
          }`}
        >
          Day {day.day_index}
        </button>
      ))}
    </div>
  );

  if (isRecall) {
    return (
      <div className="relative h-full w-full">
        <div ref={containerRef} className="h-full w-full bg-sky-50" />
        {!hideDaySwitcher && (
          <div className="pointer-events-none absolute left-4 right-4 top-4 z-10 flex justify-center">
            {daySwitcher}
          </div>
        )}
        {error && (
          <p className="absolute bottom-4 left-4 z-10 rounded-full bg-white/90 px-3 py-1 text-sm text-red-600 shadow">
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      {daySwitcher}
      <div
        ref={containerRef}
        className="h-[400px] w-full rounded-md border border-gray-200 bg-gray-50"
      />
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </section>
  );
}
