import { useEffect, useMemo, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Trip } from "@/lib/types";
import { api } from "@/lib/api";
import { useTripStore } from "@/stores/tripStore";
import { debounce } from "@/lib/debounce";

function buildSyncPayload(trip: Trip) {
  return {
    days:
      trip.days?.map((day) => ({
        day_id: day.id,
        item_ids: day.items.map((item) => item.id),
      })) ?? [],
    items:
      trip.days?.flatMap((day) =>
        day.items.map((item) => ({
          item_id: item.id,
          poi_name: item.poi_name,
        })),
      ) ?? [],
  };
}

export function useTripDraftSync(tripId: string, serverTrip?: Trip) {
  const queryClient = useQueryClient();
  const dirtyTrip = useTripStore((s) => s.dirtyTrip);
  const isDirty = useTripStore((s) => s.isDirty);
  const setDirtyTrip = useTripStore((s) => s.setDirtyTrip);
  const applyServerTrip = useTripStore((s) => s.applyServerTrip);
  const resetDirty = useTripStore((s) => s.resetDirty);

  const dirtyTripRef = useRef(dirtyTrip);
  const isDirtyRef = useRef(isDirty);
  useEffect(() => {
    dirtyTripRef.current = dirtyTrip;
  }, [dirtyTrip]);
  useEffect(() => {
    isDirtyRef.current = isDirty;
  }, [isDirty]);

  // 初始化：React Query 拿到服务器数据时，写入编辑快照（不覆盖已有脏数据）
  useEffect(() => {
    if (serverTrip && !isDirty) {
      setDirtyTrip(serverTrip);
    }
  }, [serverTrip, isDirty, setDirtyTrip]);

  const syncNow = useMemo(() => {
    return async (draft: Trip) => {
      try {
        const payload = buildSyncPayload(draft);
        const serverTrip = await api.post<Trip>(
          `/trips/${tripId}/sync`,
          payload,
        );
        queryClient.setQueryData(["trip", tripId], serverTrip);
        applyServerTrip(serverTrip);
      } catch {
        // 失败保留 isDirty，UI 显示“未保存”
        return;
      }
    };
  }, [queryClient, tripId, applyServerTrip]);

  const debouncedSync = useMemo(
    () =>
      debounce((draft: Trip) => {
        void syncNow(draft);
      }, 1500),
    [syncNow],
  );

  // 脏数据变化 → 防抖 1.5s 后同步
  useEffect(() => {
    if (!isDirty || !dirtyTrip) return;
    debouncedSync(dirtyTrip);
  }, [dirtyTrip, isDirty, debouncedSync]);

  // 一旦清空脏状态（服务器回写/重量操作成功），取消仍在等待的防抖任务
  useEffect(() => {
    if (!isDirty) {
      debouncedSync.cancel();
    }
  }, [isDirty, debouncedSync]);

  // 页面离开：强制 flush，尽量不丢未保存修改
  useEffect(() => {
    return () => {
      if (isDirtyRef.current && dirtyTripRef.current) {
        const draft = dirtyTripRef.current;
        debouncedSync.cancel();
        void syncNow(draft);
      } else {
        debouncedSync.cancel();
      }
    };
  }, [debouncedSync, syncNow]);

  return {
    dirtyTrip,
    isDirty,
    resetDirty,
    applyServerTrip,
  };
}