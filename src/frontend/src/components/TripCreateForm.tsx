import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import type { Trip } from "@/lib/types";

interface CreateTripPayload {
  destination: string;
  start_date: string;
  end_date: string;
  people_count: number;
}

export default function TripCreateForm() {
  const navigate = useNavigate();
  const [destination, setDestination] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [peopleCount, setPeopleCount] = useState("2");
  const [formError, setFormError] = useState<string | null>(null);

  const createTrip = useMutation({
    // 只调用已存在的 POST /trips，创建后由后端自动生成模板行程
    mutationFn: (payload: CreateTripPayload) =>
      api.post<Trip>("/trips", payload),
    onSuccess: (trip) => navigate(`/trips/${trip.id}`),
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const count = Number(peopleCount);
    const trimmedDestination = destination.trim();

    // 基础防呆：日期先后、人数范围，避免把无效数据发给后端
    if (!trimmedDestination) {
      setFormError("请填写目的地");
      return;
    }
    if (!startDate || !endDate) {
      setFormError("请选择出发日期和结束日期");
      return;
    }
    if (startDate > endDate) {
      setFormError("结束日期不能早于开始日期");
      return;
    }
    if (!Number.isInteger(count) || count < 1 || count > 20) {
      setFormError("人数必须是 1-20 的整数");
      return;
    }

    setFormError(null);
    createTrip.mutate({
      destination: trimmedDestination,
      start_date: startDate,
      end_date: endDate,
      people_count: count,
    });
  }

  const inputClass =
    "w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none";

  return (
    <form onSubmit={handleSubmit} className="space-y-4 rounded-lg border bg-white p-6 shadow-sm">
      <div>
        <label htmlFor="destination" className="mb-1 block text-sm font-medium">
          目的地
        </label>
        <input
          id="destination"
          type="text"
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          placeholder="例如：杭州"
          required
          className={inputClass}
        />
      </div>

      <div>
        <label htmlFor="start-date" className="mb-1 block text-sm font-medium">
          出发日期
        </label>
        <input
          id="start-date"
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          required
          className={inputClass}
        />
      </div>

      <div>
        <label htmlFor="end-date" className="mb-1 block text-sm font-medium">
          结束日期
        </label>
        <input
          id="end-date"
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          required
          className={inputClass}
        />
      </div>

      <div>
        <label htmlFor="people-count" className="mb-1 block text-sm font-medium">
          出行人数
        </label>
        <input
          id="people-count"
          type="number"
          min={1}
          max={20}
          step={1}
          value={peopleCount}
          onChange={(e) => setPeopleCount(e.target.value)}
          required
          className={inputClass}
        />
      </div>

      {formError && <p className="text-sm text-red-600">{formError}</p>}
      {createTrip.isError && (
        <p className="text-sm text-red-600">
          创建失败，请稍后重试（可检查后端服务是否启动）
        </p>
      )}

      <button
        type="submit"
        disabled={createTrip.isPending}
        className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {createTrip.isPending ? "正在生成行程…" : "生成行程"}
      </button>
    </form>
  );
}
