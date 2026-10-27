import { describe, expect, it, vi } from 'vitest'
import { completeAccountDeletion } from '../completeAccountDeletion'

describe('账号注销完成流程', () => {
  it('先清理账号数据和登录态，再离开当前页面', async () => {
    const order: string[] = []

    await completeAccountDeletion({
      clearAccountData: () => order.push('clear-data'),
      logout: () => order.push('logout'),
      navigateToLogin: async () => { order.push('navigate') },
    })

    expect(order).toEqual(['clear-data', 'logout', 'navigate'])
  })

  it('导航失败时仍已清理账号数据并注销', async () => {
    const order: string[] = []
    const navigateToLogin = vi.fn(async () => { throw new Error('navigation failed') })

    await expect(completeAccountDeletion({
      clearAccountData: () => order.push('clear-data'),
      logout: () => order.push('logout'),
      navigateToLogin,
    })).rejects.toThrow('navigation failed')

    expect(order).toEqual(['clear-data', 'logout'])
    expect(navigateToLogin).toHaveBeenCalledOnce()
  })
})
