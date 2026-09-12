import type { PhotoAsset } from "@/lib/types";

export function photosForItem(all: PhotoAsset[] | undefined, itemId: string): PhotoAsset[] {
  return (all ?? []).filter((photo) => photo.assignment?.item_id === itemId);
}
