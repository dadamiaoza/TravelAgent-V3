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
  route_type?: string;
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
  route_verified?: boolean | null;
  travel_advice?: string | null;
  notes?: string | null;
  cost_estimate?: number | null;
  is_locked: boolean;
}


export interface SourceEntity {
  id?: string;
  poi_name: string;
  day_index: number;
  seq: number;
  lat?: number | null;
  lng?: number | null;
  suggested_duration_h?: number | null;
  best_time?: string | null;
  cost_estimate?: string | null;
}

export interface SourceDocument {
  id: string;
  title: string;
  url?: string | null;
  content: string;
  created_at?: string;
  entities?: SourceEntity[];
}

export interface TripSuggestOut {
  destination?: string | null;
  city?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  people_count?: number;
  optimized_prompt?: string;
  must_visit?: string[];
}



export interface ItineraryDeltaTarget {
  day_index?: number | null;
  item_id?: string | null;
  seq?: number | null;
}

export interface ItineraryDeltaPayload {
  poi_name?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  duration_h?: number | null;
  notes?: string | null;
  lat?: number | null;
  lng?: number | null;
  item_ids?: string[] | null;
}

export interface ItineraryDelta {
  suggestion_id?: string | null;
  action: "add" | "update" | "delete" | "move" | "reorder" | string;
  target?: ItineraryDeltaTarget | null;
  payload?: ItineraryDeltaPayload | null;
}

export interface TripChatOut {
  reply: string;
  thread_id: string;
  suggestions: ItineraryDelta[];
}
