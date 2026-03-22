import { invoke } from '@tauri-apps/api/core';

export type Schedule = {
  id: string;
  recipeName: string;
  cronExpression: string;
  config: Record<string, unknown> | null;
  enabled: boolean;
  lastRunId: string | null;
  nextRunAt: string | null;
  createdAt: string;
};

export function getSchedules(recipeName?: string): Promise<Schedule[]> {
  return invoke<Schedule[]>('get_schedules', { recipeName });
}

export function createSchedule(
  recipeName: string,
  cronExpression: string,
  config?: Record<string, unknown>
): Promise<Schedule> {
  return invoke<Schedule>('create_schedule', { recipeName, cronExpression, config });
}

export function updateSchedule(
  id: string,
  cronExpression?: string,
  config?: Record<string, unknown>,
  enabled?: boolean
): Promise<Schedule> {
  return invoke<Schedule>('update_schedule', { id, cronExpression, config, enabled });
}

export function deleteSchedule(id: string): Promise<void> {
  return invoke<void>('delete_schedule', { id });
}
