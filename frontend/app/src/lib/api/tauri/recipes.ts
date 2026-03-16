import { invoke } from '@tauri-apps/api/core';

export type Recipe = {
  name: string;
  description: string;
  version: string;
};

export function listRecipes(): Promise<Recipe[]> {
  return invoke<Recipe[]>('list_recipes');
}
