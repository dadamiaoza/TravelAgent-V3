import type { DayView, PhotoAsset } from "@/lib/types";

export function photosForItem(all: PhotoAsset[] | undefined, itemId: string): PhotoAsset[] {
  return (all ?? []).filter((photo) => photo.assignment?.item_id === itemId);
}

export function photosForVisitStop(all: PhotoAsset[] | undefined, stopId: string): PhotoAsset[] {
  return (all ?? []).filter((photo) => photo.assignment?.visit_stop_id === stopId);
}

export function planItemOptions(days: DayView[] | undefined): { id: string; label: string }[] {
  return (days ?? []).flatMap((day) =>
    (day.items ?? []).map((item) => ({
      id: item.id,
      label: `Day ${day.day_index} · ${item.poi_name}`,
    })),
  );
}
