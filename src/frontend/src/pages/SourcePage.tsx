import { useState } from "react";
import { api } from "@/lib/api";
import type { SourceDocument } from "@/lib/types";

export default function SourcePage() {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<SourceDocument | null>(null);

  async function handleParse() {
    if (!text.trim()) {
      setError("请先输入攻略内容");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      // 1. 先保存攻略
      const created = await api.post<SourceDocument>("/sources", {
        title: title.trim() || "未命名攻略",
        text,
      });

      // 2. 再触发 Agent 解析并持久化实体
      const parsed = await api.post<SourceDocument>(`/sources/${created.id}/parse`, {});
      setSource(parsed);
    } catch {
      setError("解析失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="max-w-4xl mx-auto p-8">
      <h1 className="text-2xl font-bold text-gray-900">攻略解析</h1>
      <p className="mt-1 text-sm text-gray-500">
        粘贴攻略文本，系统会解析出候选 POI 并持久化保存。
      </p>

      <div className="mt-6 space-y-4 rounded-lg border bg-white p-6 shadow-sm">
        <div>
          <label className="mb-1 block text-sm font-medium">攻略标题</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="例如：杭州 3 日游攻略"
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">攻略内容</label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={10}
            placeholder="第一天去了西湖，下午雷峰塔；第二天灵隐寺..."
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
          />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="button"
          onClick={handleParse}
          disabled={loading}
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-60"
        >
          {loading ? "正在解析…" : "保存并解析"}
        </button>
      </div>

      {source && (
        <div className="mt-8">
          <h2 className="text-lg font-semibold text-gray-900">
            解析结果：{source.title}
          </h2>
          {source.entities && source.entities.length > 0 ? (
            <ul className="mt-4 space-y-2">
              {source.entities.map((entity) => (
                <li
                  key={`${entity.day_index}-${entity.seq}-${entity.poi_name}`}
                  className="rounded-md border bg-white p-3 text-sm"
                >
                  <p className="font-medium text-gray-900">{entity.poi_name}</p>
                  <p className="text-xs text-gray-500">
                    Day {entity.day_index} · 顺序 {entity.seq}
                    {entity.suggested_duration_h ? ` · 建议 ${entity.suggested_duration_h}h` : ""}
                    {entity.best_time ? ` · ${entity.best_time}` : ""}
                    {entity.cost_estimate ? ` · ${entity.cost_estimate}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-gray-500">暂未解析到 POI</p>
          )}
        </div>
      )}
    </main>
  );
}
