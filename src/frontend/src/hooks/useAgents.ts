import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { isTerminalJobStatus } from "@/lib/generationJob";
import type { GenerationJob } from "@/lib/types";

export function useJobStatus(jobId: string | null) {
  return useQuery<GenerationJob>({
    queryKey: ["job", jobId],
    queryFn: () => api.get<GenerationJob>(`/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) =>
      isTerminalJobStatus(query.state.data?.status) ? false : 2000,
  });
}
