// Shared TypeScript types for the travel assistant

export interface Trip {
  id: string;
  destination: string;
  start_date: string;
  end_date: string;
  people_count: number;
  status: string;
}

export interface DayView {
  id: string;
  trip_id: string;
  day_index: number;
  date: string;
  items: ItineraryItem[];
}

export interface ItineraryItem {
  id: string;
  day_id: string;
  seq: number;
  poi_name: string;
  start_time?: string;
  end_time?: string;
  transport_mode?: string;
  travel_minutes?: number;
  is_locked: boolean;
}
