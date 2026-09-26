import { shortWarningCopy } from "@/lib/generationJob";

/** Same chip metrics as the trip status pill, amber so a warning sits beside 「已生成」. */
export default function GenerationWarningPill({
  message,
  label,
}: {
  message: string;
  label?: string;
}) {
  const text = label ?? shortWarningCopy(message);
  return (
    <span
      title={message}
      className="max-w-[18rem] truncate rounded-full border border-amber-300 bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-900"
    >
      {text}
    </span>
  );
}
