import type { GenerationJob, GenerationJobStage, GenerationProgress } from "./types";

export function warningStages(
  job?: GenerationJob | null,
  progress?: GenerationProgress | null,
): GenerationJobStage[] {
  const stages = job?.stages?.length ? job.stages : progress?.stages ?? [];
  return stages.filter((stage) => stage.key === "warning");
}

/** Route and verify degradations recorded on the job, in stage order. */
export function warningMessages(
  job?: GenerationJob | null,
  progress?: GenerationProgress | null,
): string[] {
  const messages: string[] = [];
  for (const stage of warningStages(job, progress)) {
    const message = stage.message?.trim();
    if (message && !messages.includes(message)) messages.push(message);
  }
  return messages;
}

/** Latest verify/route degradation, if the job recorded one. */
export function latestWarningMessage(
  job?: GenerationJob | null,
  progress?: GenerationProgress | null,
): string | null {
  const messages = warningMessages(job, progress);
  return messages.length ? messages[messages.length - 1] : null;
}

/** Short Chinese copy for a status chip. Full text stays on the title tooltip. */
export function shortWarningCopy(message: string): string {
  const text = message.replace(/\s+/g, " ").trim();
  if (!text) return "生成有降级";
  const first = text.split(/[；;]/)[0]?.trim() || text;
  if (first.length <= 24) return first;
  return `${first.slice(0, 24)}…`;
}

/** Compact library-card chip. Title keeps every full reason. */
export function libraryDegradationSignal(
  messages: string[] | null | undefined,
): { label: string; title: string } | null {
  const items = (messages ?? []).map((message) => message.trim()).filter(Boolean);
  if (!items.length) return null;
  if (items.length === 1) return { label: shortWarningCopy(items[0]), title: items[0] };
  return {
    label: `${shortWarningCopy(items[0])} 等${items.length}项`,
    title: items.join("；"),
  };
}
