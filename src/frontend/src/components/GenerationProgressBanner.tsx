import { useState } from "react";
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
  const message =
    job?.message ?? progress?.message ?? (failed ? "行程生成失败，请稍后重试" : "正在生成行程…");
  const percent = job?.progress ?? progress?.progress ?? 0;
  const tone = failed
    ? {
        box: "border-red-200 bg-red-50",
        text: "text-red-700",
        track: "bg-red-100",
        bar: "bg-red-600",
        button: "text-red-800",
      }
    : {
        box: "border-blue-200 bg-blue-50",
        text: "text-blue-700",
        track: "bg-blue-100",
        bar: "bg-blue-600",
        button: "text-blue-800",
      };

  return (
    <div className={`mb-6 rounded-lg border p-4 ${tone.box}`}>
      <p className={`text-sm ${tone.text}`}>{message}</p>
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
