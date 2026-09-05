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
  job_id?: string | null;
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
  is_scenic?: boolean;
  poi_address?: string | null;
  poi_type?: string | null;
  notes?: string | null;
  suggested_duration_h?: number | null;
  best_time?: string | null;
  cost_estimate?: number | null;
  cost_note?: string | null;
  opening_hours?: string | null;
  visit_tips?: string | null;
  fact_warning?: string | null;
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
  visit_tips?: string | null;
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
  visit_tips?: string | null;
  best_time?: string | null;
  cost_note?: string | null;
  lat?: number | null;
  lng?: number | null;
  item_ids?: string[] | null;
}

export interface ItineraryDelta {
  suggestion_id?: string | null;
  action: "add" | "update" | "delete" | "move" | "reorder" | "replace" | string;
  target?: ItineraryDeltaTarget | null;
  payload?: ItineraryDeltaPayload | null;
  preview_before?: string | null;
  preview_after?: string | null;
}

export interface TripChatOut {
  reply: string;
  thread_id: string;
  suggestions: ItineraryDelta[];
  applied?: ItineraryDelta[];
}

export type TripChatWriteMode = "propose" | "auto_apply";


export interface GenerationJobStage {
  key: string;
  progress: number;
  message: string;
  at: string;
}

export interface GenerationProgress {
  status: string;
  progress: number;
  message: string;
  stages?: GenerationJobStage[];
  job_id?: string | null;
}

export type GenerationJobStatus =
  | "pending"
  | "running"
  | "retry_wait"
  | "succeeded"
  | "failed";

export interface GenerationJob {
  id: string;
  trip_id: string;
  status: GenerationJobStatus;
  progress: number;
  message?: string | null;
  stages?: GenerationJobStage[];
  error_code?: string | null;
  attempts: number;
  max_attempts: number;
  status_version?: number;
  created_at?: string;
  updated_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
  next_run_at?: string | null;
}
