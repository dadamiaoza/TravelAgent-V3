import GenerationProgressBanner from "@/components/GenerationProgressBanner";
import { canRetryGeneration, type TripDetailShell } from "@/lib/tripDetailState";
import type { GenerationJob, GenerationProgress, Trip } from "@/lib/types";

function failureNote(job?: GenerationJob, progress?: GenerationProgress): string | null {
  const message = (job?.message || progress?.message || "").trim();
  if (!message || message === "等待生成" || message === "暂无进度信息") return null;
  return message;
}

export default function TripStatusShell({
  trip,
  shell,
  job,
  progress,
  retrying,
  retryError,
  onRetry,
}: {
  trip: Trip;
  shell: Exclude<TripDetailShell, "ready">;
  job?: GenerationJob;
  progress?: GenerationProgress;
  retrying: boolean;
  retryError: string | null;
  onRetry: () => void;
}) {
  if (shell === "generating") {
    return (
      <section className="space-y-4" aria-live="polite">
        <GenerationProgressBanner job={job} progress={progress} />
        <div className="rounded-2xl border border-dashed border-line-tertiary bg-elevated px-6 py-10 text-center">
          <h2 className="text-base font-semibold text-ink">正在规划这趟行程</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-ink-tertiary">
            地点、地图和对话会在生成完成后出现。你可以先回到我的行程，完成后再进来看。
          </p>
        </div>
      </section>
    );
  }

  if (shell === "failed") {
    const note = failureNote(job, progress);
    const retryable = canRetryGeneration(trip);
    return (
      <section className="rounded-2xl border border-line-tertiary bg-elevated px-6 py-10 text-center shadow-sm">
        <span className="inline-flex rounded-full border border-rose-200 bg-rose-50 px-2.5 py-0.5 text-[11px] text-rose-700">
          可重试
        </span>
        <h2 className="mt-3 text-base font-semibold text-ink">行程没有生成成功</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-ink-secondary">
          规划中断了。在这里重新生成即可，列表上的「可重试」只表示状态，不会从卡片直接重试。
        </p>
        {note && <p className="mx-auto mt-3 max-w-md text-sm text-rose-700">{note}</p>}
        {retryError && (
          <p role="alert" className="mx-auto mt-3 max-w-md text-sm text-rose-700">
            {retryError}
          </p>
        )}
        {retryable ? (
          <button
            type="button"
            onClick={onRetry}
            disabled={retrying}
            className="mt-5 rounded-full bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-60"
          >
            {retrying ? "正在重新生成…" : "重新生成"}
          </button>
        ) : (
          <p className="mx-auto mt-4 max-w-md text-sm text-ink-tertiary">
            出发和返程日期还不完整，现在还不能重新生成。
          </p>
        )}
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-dashed border-line-tertiary bg-elevated px-6 py-10 text-center">
      <span className="inline-flex rounded-full border border-line-tertiary bg-chrome px-2.5 py-0.5 text-[11px] text-ink-secondary">
        草稿
      </span>
      <h2 className="mt-3 text-base font-semibold text-ink">这还是一份草稿</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-ink-tertiary">
        出发和返程日期还没定，所以还不会生成路线。确定日期之后才能开始规划，这里没有重新生成。
      </p>
    </section>
  );
}
