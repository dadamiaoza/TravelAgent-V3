/** Light checks for pasted travel guides. Not a parser — the guide API still extracts the trip. */

const GUIDE_MARK =
  /(?:^|\n)\s*(?:D\d+|Day\s*\d+|第[0-9一二三四五六七八九十]+天)/i;

export function looksLikeGuide(text: string): boolean {
  const trimmed = text.trim();
  if (trimmed.length >= 80) return true;
  if (GUIDE_MARK.test(trimmed)) return true;
  const arrowLines = trimmed.split(/\n/).filter((line) => /→|->/.test(line)).length;
  return arrowLines >= 2;
}

export function detectDayCount(text: string): number | null {
  const days = new Set<number>();
  for (const match of text.matchAll(/\bD(\d+)\b/gi)) days.add(Number(match[1]));
  for (const match of text.matchAll(/\bDay\s*(\d+)\b/gi)) days.add(Number(match[1]));
  for (const match of text.matchAll(/第([0-9]+|[一二三四五六七八九十])天/g)) {
    const value = cnNumber(match[1]);
    if (value) days.add(value);
  }
  if (days.size === 0) return null;
  return Math.max(...days);
}

export function explicitPeople(text: string): number | null {
  const match = text.match(/(\d+)\s*人/);
  if (!match) return null;
  const count = Number(match[1]);
  if (!Number.isInteger(count) || count < 1 || count > 20) return null;
  return count;
}

export function explicitDateRange(text: string): { start: string; end: string } | null {
  const isoDates = [...text.matchAll(/\b(20\d{2}-\d{2}-\d{2})\b/g)].map((match) => match[1]);
  if (isoDates.length >= 2) return { start: isoDates[0], end: isoDates[1] };
  const monthDays = [...text.matchAll(/(\d{1,2})\s*[/.月]\s*(\d{1,2})\s*日?/g)];
  if (monthDays.length < 2) return null;
  const year = new Date().getFullYear();
  return {
    start: isoDate(year, Number(monthDays[0][1]), Number(monthDays[0][2])),
    end: isoDate(year, Number(monthDays[1][1]), Number(monthDays[1][2])),
  };
}

export function guideFoldPreview(text: string, tips: string[] = []): string {
  let transport = "";
  let stay = "";
  let tip = "";
  for (const line of text.split(/\n/)) {
    const row = line.trim();
    if (!row) continue;
    const transportMatch = row.match(/交通\s*[:：]?\s*(.+)/);
    if (transportMatch && !transport) transport = clip(transportMatch[1]);
    const stayMatch = row.match(/(?:住宿|入住|住)\s*[:：]\s*(.+)/);
    if (stayMatch && !stay) stay = clip(stayMatch[1]);
    const tipMatch = row.match(/(?:tips?|提示|注意)\s*[:：]\s*(.+)/i);
    if (tipMatch && !tip) tip = clip(tipMatch[1]);
  }
  if (!tip) {
    const fromEntity = tips.map((item) => item.trim()).find(Boolean);
    if (fromEntity) tip = clip(fromEntity);
  }
  const parts = [
    transport ? `交通 ${transport}` : "",
    stay ? `住 ${stay}` : "",
    tip ? `Tips ${tip}` : "",
  ].filter(Boolean);
  if (parts.length > 0) return parts.join(" · ");
  const line = text.replace(/\s+/g, " ").trim();
  if (line.length < 12) return "";
  return line;
}

export function logisticsKind(name: string): "transport" | "stay" | null {
  if (/酒店|民宿|客栈|宾馆|住宿/.test(name)) return "stay";
  if (/火车站|高铁站|机场|汽车站|长沙南/.test(name)) return "transport";
  return null;
}

function clip(value: string): string {
  const clean = value.replace(/\s+/g, " ").split(/[，,。；;]/)[0]?.trim() ?? "";
  return clean.length > 18 ? clean.slice(0, 18).trimEnd() : clean;
}

function cnNumber(token: string): number | null {
  if (/^\d+$/.test(token)) return Number(token);
  const map: Record<string, number> = {
    一: 1,
    二: 2,
    三: 3,
    四: 4,
    五: 5,
    六: 6,
    七: 7,
    八: 8,
    九: 9,
    十: 10,
  };
  return map[token] ?? null;
}

function isoDate(year: number, month: number, day: number): string {
  const date = new Date(year, month - 1, day);
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
