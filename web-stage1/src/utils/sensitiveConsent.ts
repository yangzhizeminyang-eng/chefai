export async function saveAfterSensitiveConsent(
  persistConsent: () => Promise<unknown>,
  saveSensitiveData: () => Promise<void>,
): Promise<void> {
  await persistConsent()
  await saveSensitiveData()
}
