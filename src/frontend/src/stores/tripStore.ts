import { create } from "zustand";
import type { Trip } from "@/lib/types";

interface ChatContext {
  dayIndex?: number;
  itemId?: string;
}

interface TripState {
  selectedDayIndex: number;
  focusItemId: string | null;
  chatContext: ChatContext;

  dirtyTrip: Trip | null;
  isDirty: boolean;

  setSelectedDayIndex: (index: number) => void;
  setFocusItem: (itemId: string | null) => void;
  setChatContext: (ctx: ChatContext) => void;
  setDirtyTrip: (trip: Trip) => void;
  applyServerTrip: (trip: Trip) => void;
  updateTripLocally: (updater: (draft: Trip) => Trip) => void;
  resetDirty: () => void;
}

export const useTripStore = create<TripState>()((set) => ({
  selectedDayIndex: 0,
  focusItemId: null,
  chatContext: {},
  dirtyTrip: null,
  isDirty: false,
  setSelectedDayIndex: (index) => set({ selectedDayIndex: index }),
  setFocusItem: (itemId) => set({ focusItemId: itemId }),
  setChatContext: (ctx) => set({ chatContext: ctx }),
  setDirtyTrip: (trip) => set({ dirtyTrip: trip, isDirty: false }),
  applyServerTrip: (trip) => set({ dirtyTrip: trip, isDirty: false }),
  updateTripLocally: (updater) =>
    set((state) => {
      if (!state.dirtyTrip) return state;
      return {
        dirtyTrip: updater(state.dirtyTrip),
        isDirty: true,
      };
    }),
  resetDirty: () => set({ dirtyTrip: null, isDirty: false }),
}));
