/** User-facing trip status. Unknown enums stay in Chinese so the list never shows raw codes. */
const TRIP_STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  generating: "生成中",
  generated: "已生成",
  generation_failed: "生成失败",
};

export function tripStatusLabel(status: string): string {
  return TRIP_STATUS_LABELS[status] ?? "处理中";
}

export function tripStatusClassName(status: string): string {
  switch (status) {
    case "generating":
      return "bg-blue-50 text-blue-800";
    case "generation_failed":
      return "bg-rose-50 text-rose-700";
    default:
      return "bg-chrome text-ink-secondary";
  }
}
