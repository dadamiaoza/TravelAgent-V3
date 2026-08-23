// 高德 JS API 的轻量加载器：避免额外 npm 依赖，按官方 v2 方式动态注入 script。
const AMAP_KEY = import.meta.env.VITE_AMAP_KEY as string | undefined;
const AMAP_SECURITY_CODE = import.meta.env.VITE_AMAP_SECURITY_CODE as string | undefined;

export interface AMapOverlay {
  setMap(map: AMapMap | null): void;
}

export interface AMapMarker extends AMapOverlay {
  on(event: string, handler: () => void): void;
  getPosition(): { lng: number; lat: number };
}

export type AMapPolyline = AMapOverlay;

export interface AMapMap {
  destroy(): void;
  setFitView(overlays?: AMapOverlay[]): void;
}

export interface AMapInfoWindow {
  close(): void;
  setContent(content: string): void;
  open(map: AMapMap, position: { lng: number; lat: number }): void;
}

export interface AMapNamespace {
  Map: new (container: HTMLElement, options?: Record<string, unknown>) => AMapMap;
  Marker: new (options: Record<string, unknown>) => AMapMarker;
  Polyline: new (options: Record<string, unknown>) => AMapPolyline;
  InfoWindow: new (options?: Record<string, unknown>) => AMapInfoWindow;
}

declare global {
  interface Window {
    _AMapSecurityConfig?: { securityJsCode: string };
    AMap?: AMapNamespace;
  }
}

let amapPromise: Promise<AMapNamespace> | null = null;

export function getAmapConfig() {
  return {
    key: AMAP_KEY,
    securityCode: AMAP_SECURITY_CODE,
  };
}

export function loadAMap(): Promise<AMapNamespace> {
  if (window.AMap) {
    return Promise.resolve(window.AMap);
  }
  if (amapPromise) {
    return amapPromise;
  }

  amapPromise = new Promise((resolve, reject) => {
    // 安全密钥必须在加载高德 script 之前设置
    window._AMapSecurityConfig = {
      securityJsCode: AMAP_SECURITY_CODE ?? "",
    };

    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(AMAP_KEY ?? "")}&plugin=AMap.Marker,AMap.Polyline,AMap.InfoWindow`;
    script.async = true;

    script.onload = () => {
      if (window.AMap) {
        resolve(window.AMap);
      } else {
        reject(new Error("高德地图 SDK 加载后未找到 AMap 对象"));
      }
    };
    script.onerror = () => {
      reject(new Error("高德地图 SDK 加载失败"));
    };

    document.head.appendChild(script);
  });

  return amapPromise;
}
