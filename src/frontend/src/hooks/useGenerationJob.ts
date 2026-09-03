import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { isTerminalJobStatus } from "@/lib/generationJob";
import type { GenerationJob, GenerationProgress } from "@/lib/types";

export function useGenerationJob(
  tripId: string | undefined,
  tripStatus: string | undefined,
) {
  const queryClient = useQueryClient();
  const shouldTrack =
    !!tripId &&
    (tripStatus === "generating" || tripStatus === "generation_failed");

  const progressQuery = useQuery({
    queryKey: ["progress", tripId],
    queryFn: () => api.get<GenerationProgress>(`/trips/${tripId}/progress`),
    enabled: shouldTrack,
    refetchInterval: tripStatus === "generating" ? 2000 : false,
  });

  const jobId = progressQuery.data?.job_id ?? null;

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.get<GenerationJob>(`/jobs/${jobId}`),
    enabled: shouldTrack && !!jobId,
    refetchInterval: (query) =>
      isTerminalJobStatus(query.state.data?.status) ? false : 1000,
  });

  useEffect(() => {
    if (!shouldTrack || !jobId || isTerminalJobStatus(jobQuery.data?.status)) {
      return;
    }
    const source = new EventSource(`/api/v1/jobs/${jobId}/events`);
    const apply = (event: MessageEvent) => {
      try {
        queryClient.setQueryData(["job", jobId], JSON.parse(event.data));
      } catch {
        // Notification frames are optional; GET polling remains the fallback.
      }
    };
    source.addEventListener("snapshot", apply);
    source.addEventListener("update", apply);
    source.onerror = () => {
      source.close();
    };
    return () => {
      source.close();
    };
  }, [shouldTrack, jobId, jobQuery.data?.status, queryClient]);

  useEffect(() => {
    if (jobQuery.data?.status === "succeeded") {
      queryClient.invalidateQueries({ queryKey: ["trip", tripId] });
    }
  }, [jobQuery.data?.status, queryClient, tripId]);

  return {
    jobId,
    job: jobQuery.data,
    progress: progressQuery.data,
  };
}
