/**
 * 文件职责：虚拟支付平台适配——iOS 支付限制（RL-21 方案 B）+ 微信虚拟支付封装。
 * - iOS 一切付费入口完全隐藏（canShowMemberEntry 恒 false，而非置灰），规避审核风险；
 * - createVirtualOrder：创建会员订单（pending）；
 * - requestVirtualPay：调起微信 requestVirtualPayment（微信专属 API，uni 类型可能缺失，
 *   用防御式访问 (uni as …).requestVirtualPayment ?? wx.requestVirtualPayment 兜底）；
 * - 支付失败归一为 { code, message } 对象 reject，由调用方 toast。
 */
import { postMemberOrder } from '@/api/endpoints'
import type { MemberOrderCreateResponse, MemberPlanResponse } from '@shared/types'

/** 套餐类型（复用会员套餐契约的 product_type 联合） */
export type PlanType = MemberPlanResponse['plans'][number]['product_type']

/** 微信虚拟支付函数的最小结构（防御式类型，规避平台类型缺失） */
type VirtualPaymentFn = (option: Record<string, unknown>) => void

/**
 * 虚拟支付参数（后端下单后签发的微信支付签名要素）。
 */
export interface VirtualPayParams {
  /** 支付模式（缺省 'short_series_goods'） */
  mode?: string
  /** 签名数据（JSON 串，后端签发） */
  signData: string
  /** 签名（paySig，后端签发） */
  paySig: string
  /** 商品 package（可选，视后端契约） */
  package?: string
}

/**
 * 判断当前平台是否 iOS。
 * @returns platform === 'ios' 返回 true；获取失败按非 iOS 处理（返回 false 前先尝试，异常回落 false）
 * @throws 不抛出
 */
export function isIos(): boolean {
  try {
    return uni.getSystemInfoSync().platform === 'ios'
  } catch {
    return false
  }
}

/**
 * 创建会员虚拟支付订单（POST /v1/member/orders）。
 * @param planId 套餐类型（monthly / quarterly / yearly）
 * @returns 新建订单（order_no + amount_cents + status=pending）
 * @throws 归一化 ApiError（网络 / 风控失败由调用方处理）
 */
export function createVirtualOrder(planId: PlanType): Promise<MemberOrderCreateResponse> {
  return postMemberOrder(planId)
}

/**
 * 调起微信虚拟支付（requestVirtualPayment）。
 * @param orderNo 订单号（支付失败时随错误对象带出，便于排查对账）
 * @param payParams 后端签发的支付签名要素
 * @returns 支付成功（微信 success 回调）即 resolve
 * @throws 以 { code: 'PAY_UNSUPPORTED' | 'PAY_FAILED', message, detail? } 对象 reject
 *         （code=PAY_UNSUPPORTED：当前运行环境无该专属 API）
 */
export function requestVirtualPay(orderNo: string, payParams: VirtualPayParams): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    // 微信专属 API：uni 运行时可能未暴露、@dcloudio 类型可能缺失，双重防御式访问
    const uniApi = uni as unknown as { requestVirtualPayment?: VirtualPaymentFn }
    const wxApi = (globalThis as unknown as { wx?: { requestVirtualPayment?: VirtualPaymentFn } }).wx
    const payFn = uniApi.requestVirtualPayment ?? wxApi?.requestVirtualPayment
    if (!payFn) {
      reject({ code: 'PAY_UNSUPPORTED', message: '当前环境不支持虚拟支付', detail: { order_no: orderNo } })
      return
    }
    try {
      payFn({
        mode: payParams.mode ?? 'short_series_goods',
        signData: payParams.signData,
        paySig: payParams.paySig,
        package: payParams.package,
        success: () => resolve(),
        fail: (err: { errMsg?: string }) => {
          reject({ code: 'PAY_FAILED', message: err?.errMsg ?? '支付未完成', detail: { order_no: orderNo } })
        },
      })
    } catch (e) {
      // 调用同步异常（参数非法/宿主异常）：归一为支付失败
      reject({ code: 'PAY_FAILED', message: '支付调用异常', detail: { order_no: orderNo, raw: String(e) } })
    }
  })
}

/**
 * 会员购买入口是否可见（RL-21 方案 B）：iOS 完全隐藏（恒 false，规避审核），
 * 非 iOS 取远程开关值（false → 置灰/隐藏由页面层决定，本函数只给可见性）。
 * @param switchPayEnabled 远程支付开关（/v1/config/switches.payment_enabled）
 * @returns 可见返回 true
 * @throws 不抛出
 */
export function canShowMemberEntry(switchPayEnabled: boolean): boolean {
  return !isIos() && switchPayEnabled
}
