import { invoke } from '@tauri-apps/api/core';

export type Recipe = {
  name: string;
  description: string;
  version: string;
};

export type RecipeDagNode = {
  id: string;
  label: string;
  description: string;
};

export type RecipeDag = {
  nodes: RecipeDagNode[];
  edges: [string, string][];
};

export type RecipeDetail = {
  name: string;
  description: string;
  version: string;
  configSchema: Record<string, unknown>;
  dag: RecipeDag;
};

export function listRecipes(): Promise<Recipe[]> {
  return invoke<Recipe[]>('list_recipes');
}

export function getRecipeDetail(name: string): Promise<RecipeDetail> {
  return invoke<RecipeDetail>('get_recipe_detail', { name });
}
