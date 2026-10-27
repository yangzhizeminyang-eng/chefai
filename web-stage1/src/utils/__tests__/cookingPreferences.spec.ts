import { describe, expect, it } from 'vitest'
import { shouldSpeakCookingStep, shouldShowTimerCompletionReminder } from '../cookingPreferences'

describe('烹饪偏好行为', () => {
  it('仅在语音播报开启且步骤有内容时朗读', () => {
    expect(shouldSpeakCookingStep(true, '加入洋葱翻炒')).toBe(true)
    expect(shouldSpeakCookingStep(false, '加入洋葱翻炒')).toBe(false)
    expect(shouldSpeakCookingStep(true, '   ')).toBe(false)
  })

  it('仅在做菜提醒开启时提示计时结束', () => {
    expect(shouldShowTimerCompletionReminder(true)).toBe(true)
    expect(shouldShowTimerCompletionReminder(false)).toBe(false)
  })
})
