import type { RecommendResultItem } from '@/api/types'

/** Select the leading daily recommendations without inventing fallback recipes. */
export function selectFeaturedRecipes(
  results: RecommendResultItem[] | null | undefined,
): RecommendResultItem[] {
  return (results ?? []).slice(0, 3)
}
