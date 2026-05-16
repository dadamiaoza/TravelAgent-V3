import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Trip } from "@/lib/types";

export function useTrip(tripId: string) {
  return useQuery<Trip>({
    queryKey: ["trip", tripId],
    queryFn: () => api.get<Trip>(`/trips/${tripId}`),
    enabled: !!tripId && tripId !== "demo",
  });
}
