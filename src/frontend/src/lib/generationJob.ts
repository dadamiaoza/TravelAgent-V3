import { api } from "@/lib/api";
import type { GenerationJob, GenerationJobStage, GenerationProgress, Trip } from "@/lib/types";

export function isTerminalJobStatus(status: string | undefined): boolean {
  return status === "succeeded" || status === "failed";
}

export function isActiveJobStatus(status: string | undefined): boolean {
  return status === "pending" || status === "running" || status === "retry_wait";
}

export function warningStages(
  job?: GenerationJob | null,
  progress?: GenerationProgress | null,
): GenerationJobStage[] {
  const stages = job?.stages?.length ? job.stages : progress?.stages ?? [];
  return stages.filter((stage) => stage.key === "warning");
}

/** Latest verify/route degradation, if the job recorded one. */
export function latestWarningMessage(
  job?: GenerationJob | null,
  progress?: GenerationProgress | null,
): string | null {
  const stages = warningStages(job, progress);
  const message = stages.length ? stages[stages.length - 1]?.message?.trim() : "";
  return message || null;
}

/** Short Chinese copy for a status chip. Full text stays on the title tooltip. */
export function shortWarningCopy(message: string): string {
  const text = message.replace(/\s+/g, " ").trim();
  if (!text) return "生成有降级";
  const first = text.split(/[；;]/)[0]?.trim() || text;
  if (first.length <= 24) return first;
  return `${first.slice(0, 24)}…`;
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
