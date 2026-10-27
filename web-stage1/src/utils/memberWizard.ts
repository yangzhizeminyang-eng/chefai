export type MemberWizardStepError = 'name' | 'allergen' | null

export function validateMemberWizardStep(
  step: number,
  name: string,
  hasAllergenChoice: boolean,
): MemberWizardStepError {
  if (step === 0 && !name.trim()) return 'name'
  if (step === 1 && !hasAllergenChoice) return 'allergen'
  return null
}
