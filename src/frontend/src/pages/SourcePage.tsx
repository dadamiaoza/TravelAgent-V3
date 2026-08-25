import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import type { SourceDocument, Trip } from "@/lib/types";

export default function SourcePage() {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<SourceDocument | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [trips, setTrips] = useState<Trip[]>([]);
  const [tripId, setTripId] = useState("");
  const [importedTrip, setImportedTrip] = useState<Trip | null>(null);

  useEffect(() => {
    api.get<Trip[]>("/trips")
      .then(setTrips)
      .catch(() => {
        // 列表加载失败不阻塞页面
      });
  }, []);

  async function handleParse() {
    if (!text.trim()) {
      setError("请先输入攻略内容");
      return;
    }

    setLoading(true);
    setError(null);
    setImportedTrip(null);
    try {
      const created = await api.post<SourceDocument>("/sources", {
        title: title.trim() || "未命名攻略",
        text,
      });
      const parsed = await api.post<SourceDocument>(`/sources/${created.id}/parse`, {});
      setSource(parsed);
      setSelectedIds(new Set(parsed.entities?.map((e) => `${e.day_index}-${e.seq}-${e.poi_name}`) ?? []));
    } catch {
      setError("解析失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  function toggleEntity(key: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  async function handleImport() {
    if (!tripId) {
      setError("请选择目标行程");
      return;
    }
    if (selectedIds.size === 0) {
      setError("请至少勾选一个 POI");
      return;
    }

    const entityIds = (source?.entities ?? [])
      .filter((e) => selectedIds.has(`${e.day_index}-${e.seq}-${e.poi_name}`))
      .map((e) => e.id)
      .filter((id): id is string => Boolean(id));

    if (entityIds.length === 0) {
      setError("请至少勾选一个 POI");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const trip = await api.post<Trip>(`/trips/${tripId}/entities/import`, {
        entity_ids: entityIds,
      });
      setImportedTrip(trip);
    } catch {
      setError("导入失败，请检查行程 ID 是否正确");
    } finally {
      setLoading(false);
    }
  }

  const inputClass = "w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none";

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
            className={inputClass}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">攻略内容</label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={10}
            placeholder="第一天去了西湖，下午雷峰塔；第二天灵隐寺..."
            className={inputClass}
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
        <div className="mt-8 space-y-4">
          <h2 className="text-lg font-semibold text-gray-900">
            解析结果：{source.title}
          </h2>

          {source.entities && source.entities.length > 0 ? (
            <ul className="mt-4 space-y-2">
              {source.entities.map((entity) => {
                const key = `${entity.day_index}-${entity.seq}-${entity.poi_name}`;
                const checked = selectedIds.has(key);
                return (
                  <li
                    key={key}
                    className="flex items-start gap-3 rounded-md border bg-white p-3 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleEntity(key)}
                    />
                    <div>
                      <p className="font-medium text-gray-900">{entity.poi_name}</p>
                      <p className="text-xs text-gray-500">
                        Day {entity.day_index} · 顺序 {entity.seq}
                        {entity.suggested_duration_h ? ` · 建议 ${entity.suggested_duration_h}h` : ""}
                        {entity.best_time ? ` · ${entity.best_time}` : ""}
                        {entity.cost_estimate ? ` · ${entity.cost_estimate}` : ""}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-gray-500">暂未解析到 POI</p>
          )}

          <div className="space-y-3 rounded-lg border bg-white p-4 shadow-sm">
            <div>
              <label className="mb-1 block text-sm font-medium">选择目标行程</label>
              <select
                value={tripId}
                onChange={(e) => setTripId(e.target.value)}
                className={inputClass}
              >
                <option value="">请选择行程</option>
                {trips.map((trip) => (
                  <option key={trip.id} value={trip.id}>
                    {trip.destination} · {trip.start_date} 至 {trip.end_date}
                  </option>
                ))}
              </select>
              {trips.length === 0 && (
                <p className="mt-1 text-xs text-gray-500">
                  还没有行程，请先{" "}
                  <Link to="/" className="text-blue-600 hover:underline">
                    创建行程
                  </Link>
                </p>
              )}
            </div>

            <button
              type="button"
              onClick={handleImport}
              disabled={loading || selectedIds.size === 0 || !tripId}
              className="rounded bg-green-600 px-4 py-2 text-sm text-white disabled:opacity-60"
            >
              {loading ? "正在导入…" : `导入 ${selectedIds.size} 个 POI 到行程`}
            </button>

            {importedTrip && (
              <p className="text-sm text-green-700">
                已导入到行程：
                <Link
                  to={`/trips/${importedTrip.id}`}
                  className="ml-1 text-blue-600 hover:underline"
                >
                  查看行程
                </Link>
              </p>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
