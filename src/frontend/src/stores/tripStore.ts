import { create } from "zustand";

interface ChatContext {
  dayIndex?: number;
  itemId?: string;
}

interface TripState {
  selectedDayIndex: number;
  focusItemId: string | null;
  chatContext: ChatContext;
  setSelectedDayIndex: (index: number) => void;
  setFocusItem: (itemId: string | null) => void;
  setChatContext: (ctx: ChatContext) => void;
}

export const useTripStore = create<TripState>()((set) => ({
  selectedDayIndex: 0,
  focusItemId: null,
  chatContext: {},
  setSelectedDayIndex: (index) => set({ selectedDayIndex: index }),
  setFocusItem: (itemId) => set({ focusItemId: itemId }),
  setChatContext: (ctx) => set({ chatContext: ctx }),
}));