import type { DayView, PhotoAsset } from "@/lib/types";

export interface StarterPromptInput {
  days: DayView[];
  selectedDayIndex: number;
  focusItemId: string | null;
  focusPhotoId: string | null;
  focusedPhoto: PhotoAsset | null;
}

function cleanName(value: string | null | undefined): string {
  return value?.trim() ?? "";
}

function dayNumberAt(days: DayView[], index: number): number {
  const day = days[index];
  if (day && Number.isFinite(day.day_index) && day.day_index > 0) return day.day_index;
  return Math.max(1, index + 1);
}

function findItem(days: DayView[], itemId: string | null | undefined) {
  if (!itemId) return null;
  for (const day of days) {
    const item = (day.items ?? []).find((entry) => entry.id === itemId);
    if (item) return item;
  }
  return null;
}

function poiNames(days: DayView[]): string[] {
  const names: string[] = [];
  for (const day of days) {
    for (const item of day.items ?? []) {
      const name = cleanName(item.poi_name);
      if (name && !names.includes(name)) names.push(name);
    }
  }
  return names;
}

function isActiveVisitStop(photo: PhotoAsset): boolean {
  const assignment = photo.assignment;
  if (!assignment?.visit_stop_id) return false;
  const status = assignment.visit_stop_status;
  return !status || status === "suggested" || status === "confirmed";
}

function dedupe(prompts: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const prompt of prompts) {
    if (!prompt || seen.has(prompt)) continue;
    seen.add(prompt);
    result.push(prompt);
  }
  return result;
}

function photoPrompts(input: StarterPromptInput, focusedPoi: string): string[] {
  const photo =
    input.focusedPhoto && input.focusedPhoto.id === input.focusPhotoId ? input.focusedPhoto : null;
  const visitStop = photo ? isActiveVisitStop(photo) : false;
  const assignedItemId = photo?.assignment?.item_id ?? null;
  const assignedName = cleanName(findItem(input.days, assignedItemId)?.poi_name);
  const target =
    (focusedPoi && focusedPoi !== assignedName ? focusedPoi : "") ||
    poiNames(input.days).find((name) => name !== assignedName) ||
    "";

  const prompts = [target ? `把这张照片改挂到${target}` : "把这张照片改挂到别的地点"];
  const assignedToItem = Boolean(assignedItemId);
  if (!photo || (assignedToItem && !visitStop)) {
    prompts.push("取消这张照片的归属");
  }
  if (visitStop && photo) {
    const stopName = cleanName(photo.assignment?.visit_stop_name);
    prompts.push(stopName ? `去掉计划外停留「${stopName}」` : "去掉这个计划外停留");
  }
  return prompts;
}

export function buildStarterPrompts(input: StarterPromptInput): string[] {
  const days = input.days ?? [];
  const dayNumber = dayNumberAt(days, input.selectedDayIndex);
  const poi = cleanName(findItem(days, input.focusItemId)?.poi_name);

  const prompts = [
    poi ? `删掉${poi}` : "删掉当前关注的点",
    `Day ${dayNumber} 会下雨吗`,
    poi ? `把${poi}换成…` : "换成别的景点",
  ];

  if (days.length > 1) {
    const nextIndex = input.selectedDayIndex + 1 < days.length ? input.selectedDayIndex + 1 : 0;
    const targetDay = dayNumberAt(days, nextIndex);
    if (targetDay !== dayNumber) prompts.push(`挪到第 ${targetDay} 天`);
  }

  prompts.push("按这段攻略加点：");

  if (input.focusPhotoId) prompts.push(...photoPrompts(input, poi));

  return dedupe(prompts);
}

export function starterPlaceholder(prompts: string[], photoFocused: boolean): string {
  const pool = photoFocused
    ? prompts.filter((prompt) => prompt.includes("照片") || prompt.includes("计划外"))
    : prompts;
  const sample = (pool.length > 0 ? pool : prompts).slice(0, 2);
  if (sample.length === 0) return "例如：改一下当前行程";
  return `例如：${sample.join(" / ")}`;
}
