export type House = {
  city: string;
  pv_kwp: number;
  battery_kwh: number;
  ev_kwh: number;
  ev_charger_kw: number;
  ac_kw: number;
  grid_limit_kw: number;
  comfort_c: [number, number];
  weekday_away: [string, string];
  data_range: [string, string];
};

export type Site = {
  house: House;
  headline: {
    solar_kwh_per_day: number;
    base_demand_kwh_per_day: number;
    forecast_error_pct: number;
    days_of_data: number;
  };
  average_day: { solar_kw: number[]; demand_kw: number[]; price_inr_per_kwh: number[] };
  daily_solar: { date: string[]; actual_kwh: number[]; forecast_kwh: number[] };
};

export type TraceStep = {
  step: number;
  action: string;
  params: Record<string, unknown>;
  thought: string;
  observation?: string;
  agent?: string;
  agent_answer?: Record<string, unknown>;
};

export type SystemResult = {
  electricity_cost: number;
  total_cost: number;
  comfort_dh: number;
  ev_unmet_kwh: number;
  peak_import_kw: number;
  self_consumption_pct: number;
  import_kwh: number;
  ac_kwh: number;
  violation: boolean;
  violations: string[];
};

export type Example = {
  live?: boolean; // planned during the demo via the Python server (not one of the pre-run files)
  title: string;
  date: string;
  weekday: string;
  request: string;
  ok: boolean;
  error: string | null;
  constraints: {
    ev: Record<string, string | number | boolean>;
    battery: Record<string, string | number | boolean>;
    precool: Record<string, string | number | boolean>;
  };
  agent_reasoning: { ev: string; battery: string; precool: string };
  answer: string;
  plan_summary: {
    estimated_electricity_cost: number;
    ev: { departure: string; target_kwh: number; kwh_at_departure: number; target_met: boolean; charging: string };
    room: {
      comfort_band_c: [number, number];
      someone_home: string;
      ac_on: string;
      max_temp_when_home_c: number | null;
      planned_discomfort_degC_h: number;
    };
    home_battery: { reserve_kwh: number; lowest_planned_kwh: number; charging: string; charged_from: string; discharging: string };
    grid: { peak_import_kw: number; limit_kw: number };
  };
  verification: { passed: boolean; errors: string[]; warnings_to_tell_the_person: string[] };
  replans: number;
  explanation_fixed: boolean;
  trace: TraceStep[];
  series: {
    pv: number[];
    base: number[];
    ev: number[];
    ac: number[];
    charge: number[];
    discharge: number[];
    grid_import: number[];
    grid_export: number[];
    price: number[];
    t_out: number[];
    temps: number[];
    e_bat: number[];
    e_ev: number[];
    occupied: boolean[];
    comfort: [number, number];
    import_limit_kw: number;
    battery_min_kwh: number;
    ev_target_kwh: number;
  };
  comparison: Record<string, SystemResult>;
  s3?: { format_ok: boolean; errors: number; error_examples: string[]; warnings: string[]; reasoning: string };
};

export type Results = {
  forecast_accuracy_test: { target: string; model: string; nmae_pct: number }[];
  forecast_error_by_month: { month: string[]; pv: Record<string, number[]>; load: Record<string, number[]> };
  validation_test_split: { train_end: string; val_end: string; test_end: string };
  week_comparison: {
    dates: [string, string];
    rows: { system: string; total_inr: number; electricity_inr: number; discomfort_degc_h: number; peak_kw: number; solar_used_pct: number }[];
  };
};
