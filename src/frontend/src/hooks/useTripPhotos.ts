import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { PhotoAsset, PhotoJobOut, PhotoMapSummaryItem, PhotoUploadOut, VisitStop } from "@/lib/types";

function invalidatePhotoQueries(queryClient: ReturnType<typeof useQueryClient>, tripId: string) {
  queryClient.invalidateQueries({ queryKey: ["trip-photos", tripId] });
  queryClient.invalidateQueries({ queryKey: ["trip-photo-summary", tripId] });
  queryClient.invalidateQueries({ queryKey: ["trip-visit-stops", tripId] });
}

export function useTripPhotos(tripId: string) {
  const photos = useQuery({
    queryKey: ["trip-photos", tripId],
    queryFn: () => api.get<PhotoAsset[]>(`/trips/${tripId}/photos`),
    enabled: Boolean(tripId),
    refetchInterval: (query) =>
      query.state.data?.some((photo) => photo.status === "pending" || photo.status === "processing")
        ? 1000
        : false,
  });
  const summary = useQuery({
    queryKey: ["trip-photo-summary", tripId],
    queryFn: () => api.get<PhotoMapSummaryItem[]>(`/trips/${tripId}/photos/map-summary`),
    enabled: Boolean(tripId),
  });
  const visitStops = useQuery({
    queryKey: ["trip-visit-stops", tripId],
    queryFn: () => api.get<VisitStop[]>(`/trips/${tripId}/visit-stops`),
    enabled: Boolean(tripId),
  });
  return { photos, summary, visitStops };
}

export function useUploadTripPhotos(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ files, itemId }: { files: FileList; itemId?: string }) => {
      const form = new FormData();
      Array.from(files).forEach((file) => form.append("files", file));
      if (itemId) form.append("item_id", itemId);
      const uploaded = await api.upload<PhotoUploadOut>(`/trips/${tripId}/photos`, form);
      const deadline = Date.now() + 120_000;
      while (Date.now() < deadline) {
        const job = await api.get<PhotoJobOut>(`/trips/${tripId}/photo-jobs/${uploaded.job_id}`);
        if (job.status === "succeeded" || job.status === "failed") {
          return { uploaded, job };
        }
        await new Promise((resolve) => setTimeout(resolve, 800));
      }
      return { uploaded, job: null };
    },
    onSuccess: () => invalidatePhotoQueries(queryClient, tripId),
  });
}

export function usePatchPhotoAssignment(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      photoId,
      action,
      itemId,
    }: {
      photoId: string;
      action: "confirm" | "reassign" | "unassign";
      itemId?: string;
    }) =>
      api.patch<PhotoAsset>(`/trips/${tripId}/photos/${photoId}/assignment`, {
        action,
        item_id: itemId ?? null,
      }),
    onSuccess: () => invalidatePhotoQueries(queryClient, tripId),
  });
}

export function useDeletePhoto(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (photoId: string) => api.delete(`/trips/${tripId}/photos/${photoId}`),
    onSuccess: () => invalidatePhotoQueries(queryClient, tripId),
  });
}

export function useBatchAssignPhotos(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { photo_ids: string[]; item_id: string }) =>
      api.post<PhotoAsset[]>(`/trips/${tripId}/photos/batch-assign`, body),
    onSuccess: () => invalidatePhotoQueries(queryClient, tripId),
  });
}

export function usePatchVisitStop(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      stopId,
      action,
      itemId,
      placeName,
    }: {
      stopId: string;
      action: "confirm" | "dismiss" | "attach_item";
      itemId?: string;
      placeName?: string;
    }) =>
      api.patch<VisitStop>(`/trips/${tripId}/visit-stops/${stopId}`, {
        action,
        item_id: itemId ?? null,
        place_name: placeName ?? null,
      }),
    onSuccess: () => invalidatePhotoQueries(queryClient, tripId),
  });
}
