export interface LiveReading { type: "reading"; site_id: number; sensor_id: number; ts: string; value: number }

export interface SensorInfo {
  id: number; name: string; type: string; unit: string; site_id: number;
  interval_s: number; high_limit: number | null; low_limit: number | null;
}

export interface AlertItem {
  id: number; rule_name: string; severity: "warning" | "critical"; sensor_name: string; site_name: string;
  started_at: string; resolved_at: string | null; peak_value: number | null; acknowledged_at: string | null;
}

export interface Recommendation {
  title: string; action: string; reason: string; urgency: "now" | "today" | "this_week";
  confidence: "low" | "medium" | "high"; fact_ids: string[]; redacted: boolean;
}

export interface InsightResponse {
  summary: string; recommendations: Recommendation[]; facts: { id: string; text: string }[];
  ai_generated: boolean; notice: string;
}
