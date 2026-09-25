/**
 * City / destination label → IANA timezone.
 * Keep in sync with `src/backend/app/services/destination_timezone.py`.
 * Unknown places return null; the library then uses the viewer's local day.
 */
const CITY_TIMEZONES: Record<string, string> = {
  北京: "Asia/Shanghai",
  上海: "Asia/Shanghai",
  杭州: "Asia/Shanghai",
  成都: "Asia/Shanghai",
  厦门: "Asia/Shanghai",
  广州: "Asia/Shanghai",
  深圳: "Asia/Shanghai",
  西安: "Asia/Shanghai",
  重庆: "Asia/Shanghai",
  南京: "Asia/Shanghai",
  苏州: "Asia/Shanghai",
  武汉: "Asia/Shanghai",
  长沙: "Asia/Shanghai",
  青岛: "Asia/Shanghai",
  大连: "Asia/Shanghai",
  三亚: "Asia/Shanghai",
  昆明: "Asia/Shanghai",
  桂林: "Asia/Shanghai",
  丽江: "Asia/Shanghai",
  拉萨: "Asia/Shanghai",
  哈尔滨: "Asia/Shanghai",
  天津: "Asia/Shanghai",
  宁波: "Asia/Shanghai",
  福州: "Asia/Shanghai",
  珠海: "Asia/Shanghai",
  乌鲁木齐: "Asia/Urumqi",
  喀什: "Asia/Urumqi",
  香港: "Asia/Hong_Kong",
  澳门: "Asia/Macau",
  台北: "Asia/Taipei",
  东京: "Asia/Tokyo",
  東京: "Asia/Tokyo",
  大阪: "Asia/Tokyo",
  京都: "Asia/Tokyo",
  北海道: "Asia/Tokyo",
  札幌: "Asia/Tokyo",
  冲绳: "Asia/Tokyo",
  沖縄: "Asia/Tokyo",
  奈良: "Asia/Tokyo",
  福冈: "Asia/Tokyo",
  福岡: "Asia/Tokyo",
  名古屋: "Asia/Tokyo",
  横滨: "Asia/Tokyo",
  神户: "Asia/Tokyo",
  tokyo: "Asia/Tokyo",
  osaka: "Asia/Tokyo",
  kyoto: "Asia/Tokyo",
  首尔: "Asia/Seoul",
  首爾: "Asia/Seoul",
  釜山: "Asia/Seoul",
  新加坡: "Asia/Singapore",
  曼谷: "Asia/Bangkok",
  清迈: "Asia/Bangkok",
  普吉: "Asia/Bangkok",
  巴厘岛: "Asia/Makassar",
  悉尼: "Australia/Sydney",
  巴黎: "Europe/Paris",
  伦敦: "Europe/London",
  罗马: "Europe/Rome",
  巴塞罗那: "Europe/Madrid",
  迪拜: "Asia/Dubai",
  纽约: "America/New_York",
  洛杉矶: "America/Los_Angeles",
  檀香山: "Pacific/Honolulu",
  雷克雅未克: "Atlantic/Reykjavik",
  冰岛: "Atlantic/Reykjavik",
};

function normalizePlace(value: string | null | undefined): string {
  const text = (value || "").trim().toLowerCase();
  if (text.endsWith("市") && text.length > 1) return text.slice(0, -1);
  return text;
}

export function timezoneForPlace(
  city: string | null | undefined,
  destination?: string | null,
): string | null {
  for (const raw of [city, destination]) {
    const zone = CITY_TIMEZONES[normalizePlace(raw)];
    if (zone) return zone;
  }
  return null;
}
