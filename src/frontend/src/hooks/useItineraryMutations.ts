import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ItineraryItem, DayView, Trip } from "@/lib/types";

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


export function useCreateItineraryItem(tripId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      day_id: string;
      poi_name: string;
      start_time?: string | null;
      end_time?: string | null;
      notes?: string | null;
      lat?: number | null;
      lng?: number | null;
    }) =>
      api.post<Trip>(`/trips/${tripId}/items`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trip", tripId] });
    },
  });
}

export function useDeleteItineraryItem(tripId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (itemId: string) =>
      api.delete<{ ok: boolean }>(`/trips/${tripId}/items/${itemId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trip", tripId] });
    },
  });
}

export function useReoptimizeItineraryDay(tripId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (dayId: string) =>
      api.post<Trip>(`/trips/${tripId}/days/${dayId}/reoptimize`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trip", tripId] });
    },
  });
}


export function useRegenerateItineraryDay(tripId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (dayId: string) =>
      api.post<Trip>(`/trips/${tripId}/days/${dayId}/regenerate`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trip", tripId] });
    },
  });
}
