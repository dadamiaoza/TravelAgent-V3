import { useState } from "react";
import { shortWarningCopy, warningMessages } from "@/lib/generationJob";
import type { GenerationJob, GenerationProgress } from "@/lib/types";

export default function GenerationProgressBanner({
  job,
  progress,
  failed,
}: {
  job?: GenerationJob;
  progress?: GenerationProgress;
  failed?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const stages = job?.stages?.length ? job.stages : progress?.stages ?? [];
  const warnings = warningMessages(job, progress);
  const message =
    job?.message ?? progress?.message ?? (failed ? "行程生成失败，请稍后重试" : "正在生成行程…");
  const percent = job?.progress ?? progress?.progress ?? 0;
  const tone = failed
    ? {
        box: "border-rose-200 bg-rose-50",
        text: "text-rose-700",
        track: "bg-rose-100",
        bar: "bg-rose-600",
        button: "text-rose-800",
      }
    : {
        box: "border-blue-200 bg-blue-50",
        text: "text-blue-800",
        track: "bg-blue-100",
        bar: "bg-blue-600",
        button: "text-blue-800",
      };

  return (
    <div className={`rounded-2xl border p-4 ${tone.box}`}>
      <p className={`text-sm ${tone.text}`}>{message}</p>
      {warnings.map((warning) => (
        <p key={warning} className="mt-2 text-sm font-medium text-amber-800" title={warning}>
          {shortWarningCopy(warning)}
        </p>
      ))}
      {!failed && (
        <div className={`mt-2 h-2 w-full overflow-hidden rounded ${tone.track}`}>
          <div
            className={`h-full rounded transition-all ${tone.bar}`}
            style={{ width: `${percent}%` }}
          />
        </div>
      )}
      {stages.length > 0 && (
        <div className="mt-3">
          <button
            type="button"
            className={`text-xs underline ${tone.button}`}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? "收起阶段说明" : "查看阶段说明"}
          </button>
          {open && (
            <ol className={`mt-2 space-y-1 text-xs ${tone.text}`}>
              {stages.map((stage, index) => (
                <li key={`${stage.key}-${stage.at}-${index}`}>
                  {stage.progress}% · {stage.message}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
