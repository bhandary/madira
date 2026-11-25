"use client";

import type { ReminderItem, SensorStatusItem } from "@/a2ui/sensorSchema";

function metricLabel(metric: string) {
  return metric === "humidity_pct" ? "% RH" : "°C";
}

export function SensorStatusView({ sensors }: { sensors: SensorStatusItem[] }) {
  if (!sensors.length) {
    return <p className="text-sm text-[var(--muted)]">No sensors yet.</p>;
  }
  return (
    <ul className="space-y-2">
      {sensors.map((sensor) => (
        <li key={sensor.id} className="min-w-0 break-words text-sm" data-testid="sensor-status" data-sensor={sensor.external_id}>
          <span className="font-medium">{sensor.name}</span>
          {" · "}
          {sensor.zone_name}
          {sensor.location_name ? ` · ${sensor.location_name}` : ""}
          {" · "}
          {sensor.last_value ? `${sensor.last_value}${metricLabel(sensor.metric)}` : "No reading yet"}
          {sensor.stale ? ` · stale after ${sensor.stale_after_hours}h` : ""}
        </li>
      ))}
    </ul>
  );
}

export function ReminderListView({ reminders }: { reminders: ReminderItem[] }) {
  if (!reminders.length) {
    return <p className="text-sm text-[var(--muted)]">No reminders are due.</p>;
  }
  return (
    <ul className="space-y-2">
      {reminders.map((row) => (
        <li key={`${row.source_type}-${row.source_id}`} className="min-w-0 break-words text-sm" data-testid="reminder-row">
          <span className="font-medium">{row.title}</span>
          {" · "}
          {row.label}
          <span className="block text-[var(--muted)]">{row.detail}</span>
        </li>
      ))}
    </ul>
  );
}
