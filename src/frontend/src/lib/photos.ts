import type { PhotoAsset } from "@/lib/types";

export function photosForItem(all: PhotoAsset[] | undefined, itemId: string): PhotoAsset[] {
  return (all ?? []).filter((photo) => photo.assignment?.item_id === itemId);
}

export function photosForVisitStop(all: PhotoAsset[] | undefined, stopId: string): PhotoAsset[] {
  return (all ?? []).filter((photo) => photo.assignment?.visit_stop_id === stopId);
}
