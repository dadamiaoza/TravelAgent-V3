import { api } from "@/lib/api";
import type { GenerationJob, GenerationProgress, Trip } from "@/lib/types";

export function isTerminalJobStatus(status: string | undefined): boolean {
  return status === "succeeded" || status === "failed";
}

export function isActiveJobStatus(status: string | undefined): boolean {
  return status === "pending" || status === "running" || status === "retry_wait";
}

export async function waitForGenerationJob(
  trip: Pick<Trip, "id" | "job_id">,
  options?: { timeoutMs?: number; intervalMs?: number },
): Promise<GenerationJob> {
  const timeoutMs = options?.timeoutMs ?? 180_000;
  const intervalMs = options?.intervalMs ?? 1000;
  let jobId = trip.job_id ?? null;
  if (!jobId) {
    const progress = await api.get<GenerationProgress>(`/trips/${trip.id}/progress`);
    jobId = progress.job_id ?? null;
  }
  if (!jobId) {
    throw new Error("未找到生成任务，请稍后在行程页查看");
  }

  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const job = await api.get<GenerationJob>(`/jobs/${jobId}`);
    if (job.status === "succeeded") {
      return job;
    }
    if (job.status === "failed") {
      throw new Error(job.message || "行程生成失败，请稍后重试");
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("行程生成超时，请稍后在行程页查看");
}
