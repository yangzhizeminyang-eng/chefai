/**
 * 文件职责：拍照 / 相册图片采集与压缩适配——识别链路的媒体入口。
 * 链路：uni.chooseMedia（单张，相机+相册，compressed）→ uni.compressImage（quality 60）→
 * uploadRecognize（postVisionRecognize 上传识别）。
 * 授权约定：errMsg 含 'auth deny'（或 'authorize'）时抛
 * { code: 'PERMISSION_DENIED', message } 的 ApiError 形状错误，页面据此渲染无权限态
 * （引导到设置开启）；用户取消 / 其他失败抛普通失败错误，页面回到空闲态即可。
 */
import { postVisionRecognize } from '@/api/endpoints'
import type { VisionRecognizeResponse } from '@shared/types'

/** 采集压缩结果（临时文件路径，仅本会话有效） */
export interface ChosenImage {
  /** 压缩后的图片临时路径 */
  tempFilePath: string
}

/**
 * 选图并压缩：单张（相机 / 相册）→ quality 60 压缩。
 * 压缩失败（个别格式不支持等）回退返回原图临时路径，不阻断识别。
 * @returns { tempFilePath } 压缩后（或回退原图）的临时路径
 * @throws ApiError 形状对象：授权拒绝 { code: 'PERMISSION_DENIED' }；
 *         未选图 / 其他失败 { code: 'MEDIA_CANCEL' | 'MEDIA_FAILED', message }
 */
export async function chooseAndCompressImage(): Promise<ChosenImage> {
  const chosen = await new Promise<string>((resolve, reject) => {
    try {
      uni.chooseMedia({
        count: 1,
        mediaType: ['image'],
        sourceType: ['camera', 'album'],
        sizeType: ['compressed'],
        success: (res) => {
          const item = res.tempFiles?.[0]
          if (item && item.tempFilePath) resolve(item.tempFilePath)
          else reject({ code: 'MEDIA_FAILED', message: '未获取到图片，请重试' })
        },
        fail: (err) => {
          const msg = err?.errMsg ?? ''
          if (msg.includes('auth deny') || msg.includes('authorize')) {
            // 授权拒绝：页面据此渲染无权限态（引导开启相机/相册权限）
            reject({ code: 'PERMISSION_DENIED', message: '未获得相机或相册权限，请在设置中开启' })
            return
          }
          if (msg.includes('cancel')) {
            reject({ code: 'MEDIA_CANCEL', message: '已取消选择' })
            return
          }
          reject({ code: 'MEDIA_FAILED', message: '选择图片失败，请重试' })
        },
      })
    } catch {
      reject({ code: 'MEDIA_FAILED', message: '选择图片失败，请重试' })
    }
  })
  // 压缩（quality 60）：失败回退原图（部分平台/格式压缩不支持），不阻断识别
  return new Promise<ChosenImage>((resolve) => {
    try {
      uni.compressImage({
        src: chosen,
        quality: 60,
        success: (res) => resolve({ tempFilePath: res.tempFilePath ?? chosen }),
        fail: () => resolve({ tempFilePath: chosen }),
      })
    } catch {
      resolve({ tempFilePath: chosen })
    }
  })
}

/**
 * 上传图片触发冰箱识别（POST /v1/vision/recognize，uni.uploadFile 临时文件上传）。
 * @param tempFilePath chooseAndCompressImage 产出的临时路径
 * @returns 识别结果 + 剩余额度 + 降级标记
 * @throws 归一化 ApiError（429 额度不足 / 超时 / 网络失败，页面按 code 分支处理）
 */
export function uploadRecognize(tempFilePath: string): Promise<VisionRecognizeResponse> {
  return postVisionRecognize(tempFilePath)
}
