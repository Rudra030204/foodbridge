export type Role = "donor" | "ngo" | "volunteer" | "admin";

export interface User {
  id: number; name: string; email: string; phone: string | null; role: Role;
  is_verified: boolean; is_active: boolean; reliability: number | null; rating_count: number;
}
export interface Me { user: User; profile: Record<string, any> | null }

export interface MatchInfo {
  score: number; rank: number; distance_km: number; notified: boolean; response: string;
  components: { distance: number; time: number; capacity: number; preference: number; history: number; travel_minutes?: number };
}
export interface Listing {
  id: number; title: string; description: string | null; food_category: string; is_veg: boolean;
  quantity_meals: number; claimed_meals: number; remaining_meals: number; storage_condition: string; hot_day: boolean;
  cooked_at: string; safe_until: string; minutes_left: number; urgency: "green" | "amber" | "red";
  status: string; escalation_level: number; photo_url: string | null; pickup_window_start: string; pickup_window_end: string;
  created_at: string; area_cell: string; donor_org: string | null; donor_verified: boolean; exact_location: boolean;
  pickup_address: string | null; lat: number; lng: number; donor_id: number | null;
  my_match?: MatchInfo; my_claim_id?: number | null; notified_count?: number;
}
export interface Pickup {
  id: number; claim_id: number; status: string; quantity: number; is_diversion: boolean;
  assigned_at: string | null; picked_up_at: string | null; delivered_at: string | null; route_id: number | null;
  otp_locked_until: string | null; can_rate?: boolean;
  listing: { id: number; title: string; status: string; safe_until: string; minutes_left: number; is_veg: boolean;
    donor_id: number; donor_org: string | null; pickup_address: string | null; lat: number; lng: number; pickup_window_end: string };
  ngo: { id: number; org_name: string | null; address: string | null; lat: number | null; lng: number | null };
  volunteer: { id: number; name: string; phone: string | null } | null;
  pickup_otp: string | null; delivery_otp: string | null; volunteer_location: { lat: number; lng: number } | null;
}
export interface Stop { seq: number; kind: "pickup" | "delivery"; label: string; lat: number; lng: number; pickup_id: number; eta: string; deadline: string | null; leg_km: number }
export interface RouteInfo { route_id: number | null; stops: Stop[]; total_distance_km: number; estimated_minutes: number; feasible: boolean }
export interface Match {
  ngo_id: number; org_name: string; rank: number; score: number; distance_km: number; notified: boolean; response: string;
  components: MatchInfo["components"];
}
export interface Notice { id: number; type: string; title: string; body: string; is_read: boolean; created_at: string; data: Record<string, any> | null }
export interface Impact {
  meals_rescued: number; meals_diverted: number; kg_saved: number; co2e_avoided_kg: number;
  delivery_success_rate: number | null; avg_time_to_claim_min: number | null; escalation_rate: number | null;
  listings_total: number; listings_by_status: Record<string, number>; deliveries: number; by_day: { date: string; meals: number }[];
}
export interface ForecastCell { area_cell: string; lat: number; lng: number; week_total: number; days: { date: string; weekday: string; event_flag: string; expected_meals: number }[] }
export interface Forecast {
  is_synthetic: boolean; note: string; trained_at: string; cells: ForecastCell[];
  metrics: Record<string, { mae: number; rmse: number } | number | string>;
}
