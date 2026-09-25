import { badgeLabel, generationBadge } from "./tripLibrary.ts";
import { tripStatusLabel } from "./tripStatus.ts";

export type TripDetailShell = "generating" | "failed" | "draft" | "ready";

export interface TripShellInput {
  status: string;
  start_date?: string | null;
  end_date?: string | null;
}

/** Which detail surface to show. Failed wins only on the failed status, so a fresh retry stays on the generating shell. */
export function tripDetailShell(trip: TripShellInput): TripDetailShell {
  if (trip.status === "generating") return "generating";
  if (trip.status === "generation_failed") return "failed";
  if (trip.status === "draft" || !trip.start_date || !trip.end_date) return "draft";
  return "ready";
}

export function canRetryGeneration(trip: TripShellInput): boolean {
  return trip.status === "generation_failed" && Boolean(trip.start_date) && Boolean(trip.end_date);
}

/** Library badge wording when the trip is still in progress, otherwise the plain status label. */
export function detailStatusLabel(status: string): string {
  const badge = generationBadge(status);
  return badge ? badgeLabel(badge) : tripStatusLabel(status);
}

export function detailStatusClassName(status: string): string {
  switch (status) {
    case "generating":
      return "border-blue-200 bg-blue-50 text-blue-800";
    case "generation_failed":
      return "border-rose-200 bg-rose-50 text-rose-700";
    default:
      return "border-line-tertiary bg-elevated text-ink-secondary";
  }
}
