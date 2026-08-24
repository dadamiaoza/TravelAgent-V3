// Shared TypeScript types for the travel assistant

export interface Trip {
  id: string;
  destination: string;
  start_date: string;
  end_date: string;
  people_count: number;
  budget_min?: number | null;
  budget_max?: number | null;
  status: string;
  created_at?: string;
  updated_at?: string;
  days?: DayView[];
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
  seq: number;
  poi_name: string;
  start_time?: string | null;
  end_time?: string | null;
  lat?: number | null;
  lng?: number | null;
  transport_mode?: string | null;
  travel_minutes?: number | null;
  route_polyline?: number[][] | null;
  notes?: string | null;
  cost_estimate?: number | null;
  is_locked: boolean;
}
