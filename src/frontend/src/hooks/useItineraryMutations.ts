import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Trip } from "@/lib/types";
import { useTripStore } from "@/stores/tripStore";

function applyTripResult(
  queryClient: ReturnType<typeof useQueryClient>,
  tripId: string,
  data: Trip,
) {
  queryClient.setQueryData(["trip", tripId], data);
  useTripStore.getState().applyServerTrip(data);
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
    onSuccess: (data) => {
      applyTripResult(queryClient, tripId, data);
    },
  });
}

export function useDeleteItineraryItem(tripId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (itemId: string) =>
      api.delete<Trip>(`/trips/${tripId}/items/${itemId}`),
    onSuccess: (data) => {
      applyTripResult(queryClient, tripId, data);
    },
  });
}

export function useReoptimizeItineraryDay(tripId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (dayId: string) =>
      api.post<Trip>(`/trips/${tripId}/days/${dayId}/reoptimize`, {}),
    onSuccess: (data) => {
      applyTripResult(queryClient, tripId, data);
    },
  });
}
