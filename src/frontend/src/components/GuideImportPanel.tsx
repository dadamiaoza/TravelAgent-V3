import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { SourceDocument, Trip } from "@/lib/types";

export default function GuideImportPanel({ tripId }: { tripId: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function handleParseAndAppend() {
    if (!text.trim()) {
      setError("请先粘贴攻略内容");
      return;
    }

    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      // 1. 保存攻略
      const created = await api.post<SourceDocument>("/sources", {
        title: "",
        text,
      });

      // 2. 解析攻略
      const parsed = await api.post<SourceDocument>(`/sources/${created.id}/parse`, {});

      // 3. 简单追加所有解析出的 POI 到当前行程
      const entityIds = (parsed.entities ?? [])
        .map((entity) => entity.id)
        .filter((id): id is string => Boolean(id));

      if (entityIds.length === 0) {
        setError("未解析到任何地点");
        return;
      }

      await api.post<Trip>(`/trips/${tripId}/entities/import`, {
        entity_ids: entityIds,
      });

      await queryClient.invalidateQueries({ queryKey: ["trip", tripId] });

      setMessage(`已追加 ${entityIds.length} 个地点到当前行程`);
      setText("");
    } catch {
      setError("解析或导入失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="font-medium text-gray-900">导入攻略并追加地点</span>
        <span className="text-gray-500">{open ? "收起 ▲" : "展开 ▼"}</span>
      </button>

      {open && (
        <div className="mt-4 space-y-3">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
            placeholder="粘贴攻略内容，例如：第一天去了西湖，下午雷峰塔..."
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          {message && <p className="text-sm text-green-700">{message}</p>}
          <button
            type="button"
            onClick={handleParseAndAppend}
            disabled={loading}
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-60"
          >
            {loading ? "解析并追加中…" : "解析并追加到当前行程"}
          </button>
        </div>
      )}
    </section>
  );
}
