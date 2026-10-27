import { describe, expect, it } from 'vitest'
import { validateMemberWizardStep } from '../memberWizard'

describe('validateMemberWizardStep', () => {
  it('requires a non-empty name before leaving basic information', () => {
    expect(validateMemberWizardStep(0, '   ', true)).toBe('name')
    expect(validateMemberWizardStep(0, '妈妈', false)).toBeNull()
  })

  it('requires an explicit allergen choice before leaving the safety step', () => {
    expect(validateMemberWizardStep(1, '妈妈', false)).toBe('allergen')
    expect(validateMemberWizardStep(1, '妈妈', true)).toBeNull()
  })

  it('does not add new validation to the final preference step', () => {
    expect(validateMemberWizardStep(2, '', false)).toBeNull()
  })
})
