import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import type { Trip, TripSuggestOut } from "@/lib/types";

export default function TripPromptForm() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [suggestion, setSuggestion] = useState<TripSuggestOut | null>(null);
  const [destination, setDestination] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [peopleCount, setPeopleCount] = useState("1");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleOptimize() {
    if (!text.trim()) {
      setError("请先输入你的旅行想法");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await api.post<TripSuggestOut>("/trips/suggest", { text });
      setSuggestion(result);
      setDestination(result.destination ?? "");
      setStartDate(result.start_date ?? "");
      setEndDate(result.end_date ?? "");
      setPeopleCount(String(result.people_count ?? 1));
    } catch {
      setError("提示词优化失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerate() {
    if (!destination.trim()) {
      setError("请填写目的地");
      return;
    }
    if (!startDate || !endDate) {
      setError("请填写出发和结束日期");
      return;
    }
    const count = Number(peopleCount);
    if (!Number.isInteger(count) || count < 1 || count > 20) {
      setError("人数必须是 1-20 的整数");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const trip = await api.post<Trip>("/trips", {
        destination: destination.trim(),
        start_date: startDate,
        end_date: endDate,
        people_count: count,
      });
      navigate(`/trips/${trip.id}`);
    } catch {
      setError("生成失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  const inputClass =
    "w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none";

  return (
    <div className="space-y-4 rounded-lg border bg-white p-6 shadow-sm">
      <div>
        <label className="mb-1 block text-sm font-medium">
          用一句话描述你的旅行需求
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          placeholder="例如：帮我规划杭州3日游，2个人，喜欢历史和美食，预算不要太高"
          className={inputClass}
        />
      </div>

      <button
        type="button"
        onClick={handleOptimize}
        disabled={loading}
        className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
      >
        {loading ? "正在优化提示词…" : "优化提示词"}
      </button>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {suggestion && (
        <div className="space-y-3 rounded-md border border-blue-100 bg-blue-50/50 p-4">
          <div>
            <h3 className="text-sm font-semibold text-gray-900">优化后的提示词</h3>
            <p className="mt-1 text-sm text-gray-600">{suggestion.optimized_prompt}</p>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs text-gray-500">目的地</label>
              <input
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-500">人数</label>
              <input
                type="number"
                min={1}
                max={20}
                value={peopleCount}
                onChange={(e) => setPeopleCount(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-500">出发日期</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-500">结束日期</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className={inputClass}
              />
            </div>
          </div>

          <button
            type="button"
            onClick={handleGenerate}
            disabled={loading}
            className="w-full rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-60"
          >
            {loading ? "正在生成行程…" : "确认并生成行程"}
          </button>
        </div>
      )}
    </div>
  );
}
