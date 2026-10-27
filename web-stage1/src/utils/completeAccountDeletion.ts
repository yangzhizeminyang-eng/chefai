interface AccountDeletionSteps {
  clearAccountData: () => void
  logout: () => void
  navigateToLogin: () => Promise<unknown>
}

/** 注销成功后清空本地账号态，再离开可能展示旧数据的页面。 */
export async function completeAccountDeletion(steps: AccountDeletionSteps): Promise<void> {
  steps.clearAccountData()
  steps.logout()
  await steps.navigateToLogin()
}
