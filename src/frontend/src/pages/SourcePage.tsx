import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import type { SourceDocument, Trip } from "@/lib/types";

export default function SourcePage() {
  const [searchParams] = useSearchParams();
  const initialTripId = searchParams.get("tripId") ?? "";

  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<SourceDocument | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [trips, setTrips] = useState<Trip[]>([]);
  const [tripId, setTripId] = useState(initialTripId);
  const [importedTrip, setImportedTrip] = useState<Trip | null>(null);

  useEffect(() => {
    api.get<Trip[]>("/trips")
      .then((list) => {
        setTrips(list);
        // 如果 URL 带了 tripId，且不在列表中，也保留该值用于导入
        if (initialTripId && !list.some((trip) => trip.id === initialTripId)) {
          setTripId(initialTripId);
        }
      })
      .catch(() => {
        // 列表加载失败不阻塞页面
      });
  }, [initialTripId]);

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

  function getSelectedEntityIds(): string[] {
    return (source?.entities ?? [])
      .filter((e) => selectedIds.has(`${e.day_index}-${e.seq}-${e.poi_name}`))
      .map((e) => e.id)
      .filter((id): id is string => Boolean(id));
  }

  async function importToTrip(targetTripId: string, entityIds: string[]) {
    const trip = await api.post<Trip>(`/trips/${targetTripId}/entities/import`, {
      entity_ids: entityIds,
    });
    setImportedTrip(trip);
    return trip;
  }

  async function handleImport() {
    if (!tripId) {
      setError("请选择目标行程");
      return;
    }
    const entityIds = getSelectedEntityIds();
    if (entityIds.length === 0) {
      setError("请至少勾选一个 POI");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await importToTrip(tripId, entityIds);
    } catch {
      setError("导入失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateAndImport() {
    if (!source) {
      setError("请先解析攻略");
      return;
    }
    const entityIds = getSelectedEntityIds();
    if (entityIds.length === 0) {
      setError("请至少勾选一个 POI");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      // 1. 根据攻略内容自动推断目的地和天数
      const inferred = await api.post<{ destination: string; city?: string | null; day_count: number }>(
        `/sources/${source.id}/infer-trip`,
        {},
      );

      // 2. 创建新行程：默认从今天开始
      const today = new Date();
      const startDate = today.toISOString().slice(0, 10);
      const endDate = new Date(today.getTime() + (inferred.day_count - 1) * 86400000)
        .toISOString()
        .slice(0, 10);

      const newTrip = await api.post<Trip>("/trips", {
        destination: inferred.destination,
          city: inferred.city ?? undefined,
        start_date: startDate,
        end_date: endDate,
        people_count: 1,
      });

      // 3. 把选中的 POI 导入新行程
      await importToTrip(newTrip.id, entityIds);
      setTripId(newTrip.id);
      setTrips((prev) => [newTrip, ...prev.filter((t) => t.id !== newTrip.id)]);
    } catch {
      setError("创建新行程并导入失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  const inputClass = "w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none";

  return (
    <main className="max-w-4xl mx-auto p-8">
      <h1 className="text-2xl font-bold text-gray-900">攻略解析</h1>
      <p className="mt-1 text-sm text-gray-500">
        可以先把攻略导入到一个已有行程，也可以直接根据攻略创建新行程。
      </p>

      <div className="mt-6 space-y-4 rounded-lg border bg-white p-6 shadow-sm">
        <div>
          <label className="mb-1 block text-sm font-medium">选择目标行程（可选）</label>
          <select
            value={tripId}
            onChange={(e) => setTripId(e.target.value)}
            className={inputClass}
          >
            <option value="">不选择，稍后根据攻略创建新行程</option>
            {trips.map((trip) => (
              <option key={trip.id} value={trip.id}>
                {trip.destination} · {trip.start_date} 至 {trip.end_date}
              </option>
            ))}
          </select>
          {trips.length === 0 && (
            <p className="mt-1 text-xs text-gray-500">
              当前还没有行程，可以直接解析攻略后自动创建。
            </p>
          )}
        </div>

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
            {tripId ? (
              <button
                type="button"
                onClick={handleImport}
                disabled={loading || selectedIds.size === 0}
                className="rounded bg-green-600 px-4 py-2 text-sm text-white disabled:opacity-60"
              >
                {loading ? "正在导入…" : `导入 ${selectedIds.size} 个 POI 到所选行程`}
              </button>
            ) : (
              <button
                type="button"
                onClick={handleCreateAndImport}
                disabled={loading || selectedIds.size === 0}
                className="rounded bg-green-600 px-4 py-2 text-sm text-white disabled:opacity-60"
              >
                {loading ? "正在创建…" : `根据攻略创建新行程并导入 ${selectedIds.size} 个 POI`}
              </button>
            )}

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
