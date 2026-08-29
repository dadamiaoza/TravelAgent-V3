import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Trip } from "@/lib/types";
import { api } from "@/lib/api";
import ItineraryDayCard from "@/components/ItineraryDayCard";
import TripMap from "@/components/TripMap";
import GuideImportPanel from "@/components/GuideImportPanel";

export default function TripDetail({ trip }: { trip: Trip }) {
  const days = trip.days ?? [];
  const queryClient = useQueryClient();
  const [selectedDayIndex, setSelectedDayIndex] = useState(0);
  const [focusItemId, setFocusItemId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState(trip.destination);

  const updateTrip = useMutation({
    mutationFn: (destination: string) =>
      api.patch<Trip>(`/trips/${trip.id}`, { destination }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trip", trip.id] });
      setEditingTitle(false);
    },
  });

  function handleSelectItem(itemId: string) {
    setFocusItemId(itemId);
    requestAnimationFrame(() => {
      document
        .getElementById(`itinerary-item-${itemId}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  function handleSelectDay(index: number) {
    setSelectedDayIndex(index);
    setFocusItemId(null);
  }

  function handleSaveTitle() {
    const value = titleDraft.trim();
    if (!value) return;
    updateTrip.mutate(value);
  }

  const currentDay = days[selectedDayIndex];

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            {!editingTitle ? (
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-semibold text-gray-900">
                  {trip.destination} · {trip.start_date} 至 {trip.end_date}
                </h2>
                <button
                  type="button"
                  onClick={() => {
                    setTitleDraft(trip.destination);
                    setEditingTitle(true);
                  }}
                  className="text-xs text-blue-600 hover:underline"
                >
                  编辑标题
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <input
                  value={titleDraft}
                  onChange={(e) => setTitleDraft(e.target.value)}
                  className="rounded border border-gray-300 px-2 py-1 text-sm"
                />
                <button
                  type="button"
                  onClick={handleSaveTitle}
                  disabled={updateTrip.isPending}
                  className="rounded bg-blue-600 px-2 py-1 text-xs text-white disabled:opacity-60"
                >
                  保存
                </button>
                <button
                  type="button"
                  onClick={() => setEditingTitle(false)}
                  className="rounded bg-gray-200 px-2 py-1 text-xs"
                >
                  取消
                </button>
              </div>
            )}
            <p className="mt-1 text-sm text-gray-500">
              {trip.people_count} 人 · 状态：{trip.status}
            </p>
          </div>
          <Link
            to={`/sources?tripId=${trip.id}`}
            className="shrink-0 rounded border border-blue-600 px-3 py-1 text-sm text-blue-600 hover:bg-blue-50"
          >
            导入攻略到当前行程
          </Link>
        </div>
      </section>

      {days.length > 0 && (
        <TripMap
          days={days}
          selectedDayIndex={selectedDayIndex}
          onSelectDay={handleSelectDay}
          focusItemId={focusItemId}
          onSelectItem={handleSelectItem}
        />
      )}

      {currentDay ? (
        <ItineraryDayCard
          key={currentDay.id}
          day={currentDay}
          tripId={trip.id}
          focusedItemId={focusItemId}
          onSelectItem={handleSelectItem}
        />
      ) : (
        <p className="rounded-lg border border-dashed border-gray-300 bg-white p-6 text-center text-gray-500">
          该行程暂无内容
        </p>
      )}

      <GuideImportPanel tripId={trip.id} />
    </div>
  );
}
