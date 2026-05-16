import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

interface JobStatus {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  error_message?: string;
}

export function useJobStatus(jobId: string | null) {
  return useQuery<JobStatus>({
    queryKey: ["job", jobId],
    queryFn: () => api.get<JobStatus>(`/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.status === "completed" || data?.status === "failed") return false;
      return 2000; // poll every 2s while running
    },
  });
}
