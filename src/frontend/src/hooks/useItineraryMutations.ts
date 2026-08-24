import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ItineraryItem, DayView } from "@/lib/types";

export function useUpdateItineraryItem(tripId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      itemId,
      payload,
    }: {
      itemId: string;
      payload: {
        poi_name?: string;
        start_time?: string | null;
        end_time?: string | null;
        notes?: string | null;
      };
    }) =>
      api.patch<ItineraryItem>(`/trips/${tripId}/items/${itemId}`, payload),
    onSuccess: () => {
      // 更新成功后刷新整个行程，保证卡片和地图同步
      queryClient.invalidateQueries({ queryKey: ["trip", tripId] });
    },
  });
}

export function useReorderItineraryDay(tripId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ dayId, itemIds }: { dayId: string; itemIds: string[] }) =>
      api.post<DayView>(`/trips/${tripId}/days/${dayId}/reorder`, {
        item_ids: itemIds,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trip", tripId] });
    },
  });
}
