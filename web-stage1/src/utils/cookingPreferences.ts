/** 用户烹饪偏好对应的运行时门控。 */
export function shouldSpeakCookingStep(enabled: boolean, text: string | null | undefined): boolean {
  return enabled && Boolean(text?.trim())
}

export function shouldShowTimerCompletionReminder(enabled: boolean): boolean {
  return enabled
}
