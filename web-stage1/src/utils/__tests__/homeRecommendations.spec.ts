import { describe, expect, it } from 'vitest'
import type { RecommendResultItem } from '@/api/types'
import { selectFeaturedRecipes } from '@/utils/homeRecommendations'

describe('selectFeaturedRecipes', () => {
  it('returns at most the first three real recommendations in ranking order', () => {
    const recipes = Array.from({ length: 5 }, (_, index) => ({
      recipe_id: index + 1,
    }) as RecommendResultItem)

    expect(selectFeaturedRecipes(recipes).map((recipe) => recipe.recipe_id)).toEqual([1, 2, 3])
  })

  it('returns an empty list when recommendations are unavailable', () => {
    expect(selectFeaturedRecipes(null)).toEqual([])
  })
})
