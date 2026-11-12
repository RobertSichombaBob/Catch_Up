/** Shapes of the JSON returned by apps/analytics/api.py. Keep in sync. */
export interface Point { x: string; y: number; label?: string }
export interface Slice { label: string; value: number; total?: number }

export interface StudentOverview {
  progress: Slice[];
  lessons_per_week: Point[];
  grades: Point[];
  insights: { week: number; streak: number; tips: string[] };
}

export interface RiskRow { student: string; course: string; risk: number; level: 'low' | 'medium' | 'high'; reasons: string[] }

export interface TutorOverview {
  enrolments: Point[];
  earnings: Point[];
  by_course: Slice[];
  attendance: Slice[];
  risk: RiskRow[];
}

export interface ForecastPoint extends Point { low: number; high: number }

export interface AdminOverview {
  revenue: Point[];
  forecast: ForecastPoint[];
  forecast_message: string;
  split: Slice[];
  networks: Slice[];
  hours: Slice[];
  signups: Point[];
  suspicious: unknown[];
  spike: unknown;
  model: { source: string; importance: { feature: string; weight: number }[]; metrics: Record<string, number | string>; trained_at: string | null };
}

export interface PaymentStatus { status: string; final: boolean; message: string; course_url: string }
