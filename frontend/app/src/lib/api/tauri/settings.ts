import { invoke } from '@tauri-apps/api/core';

export type CredentialPresence = {
  present: boolean;
};

export function getCredentials(
  keys: string[] = []
): Promise<Record<string, CredentialPresence>> {
  return invoke<Record<string, CredentialPresence>>('get_credentials', { keys });
}

export function saveCredentials(
  values: Record<string, string | null>
): Promise<void> {
  return invoke<void>('save_credentials', { values });
}
