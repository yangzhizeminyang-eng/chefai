/**
 * 文件职责：src/utils/voiceCommand.ts 单测（F 模块免手语音）。
 * 覆盖：parseVoiceCommand 白名单全指令与近义命中、关键冲突（「继续做」优先于
 *       「继续」）、大小写不敏感、带标点/前缀噪声、无命中返回 null；
 *       createVoiceCommandController 在无 Web Speech 环境的降级（supported=false、
 *       start/stop 幂等不抛、不触发 onCommand）。
 * 运行方式：npm run test（vitest run，node 环境即天然无 window/SpeechRecognition）。
 */
import { describe, expect, it, vi } from 'vitest'
import { createVoiceCommandController, parseVoiceCommand } from '../voiceCommand'

describe('parseVoiceCommand 指令白名单本地解析', () => {
  it('「下一步」及近义命中 next', () => {
    expect(parseVoiceCommand('下一步')).toBe('next')
    expect(parseVoiceCommand('下一')).toBe('next')
    expect(parseVoiceCommand('继续做')).toBe('next')
    expect(parseVoiceCommand('接下来')).toBe('next')
  })

  it('「上一步」及近义命中 prev', () => {
    expect(parseVoiceCommand('上一步')).toBe('prev')
    expect(parseVoiceCommand('上一')).toBe('prev')
    expect(parseVoiceCommand('退回')).toBe('prev')
  })

  it('「暂停」及近义命中 timer_pause', () => {
    expect(parseVoiceCommand('暂停')).toBe('timer_pause')
    expect(parseVoiceCommand('暂停计时')).toBe('timer_pause')
    expect(parseVoiceCommand('停一下')).toBe('timer_pause')
  })

  it('「继续」及近义命中 timer_resume', () => {
    expect(parseVoiceCommand('继续')).toBe('timer_resume')
    expect(parseVoiceCommand('继续计时')).toBe('timer_resume')
    expect(parseVoiceCommand('恢复')).toBe('timer_resume')
  })

  it('关键冲突：「继续做」优先归 next 而非 timer_resume（规则表顺序保证）', () => {
    expect(parseVoiceCommand('继续做')).toBe('next')
  })

  it('中英文键不区分大小写', () => {
    expect(parseVoiceCommand('NEXT')).toBe('next')
    expect(parseVoiceCommand('Next')).toBe('next')
    expect(parseVoiceCommand('Pause')).toBe('timer_pause')
    expect(parseVoiceCommand('RESUME')).toBe('timer_resume')
    expect(parseVoiceCommand('Back')).toBe('prev')
  })

  it('识别文本带标点/前缀噪声仍按包含命中', () => {
    expect(parseVoiceCommand('下一步。')).toBe('next')
    expect(parseVoiceCommand('厨娘厨娘，下一步')).toBe('next')
    expect(parseVoiceCommand('  停一下  ')).toBe('timer_pause')
  })

  it('无命中返回 null（空串/空白/无关语句/纯数字）', () => {
    expect(parseVoiceCommand('')).toBeNull()
    expect(parseVoiceCommand('   ')).toBeNull()
    expect(parseVoiceCommand('打开步骤列表')).toBeNull()
    expect(parseVoiceCommand('番茄炒蛋怎么做')).toBeNull()
    expect(parseVoiceCommand('12345')).toBeNull()
  })
})

describe('createVoiceCommandController 降级（node 无 Web Speech）', () => {
  it('supported=false，start/stop 幂等不抛错且不触发指令', () => {
    const onCommand = vi.fn()
    const controller = createVoiceCommandController({ onCommand })
    expect(controller.supported).toBe(false)
    expect(() => {
      controller.start()
      controller.start()
      controller.stop()
      controller.stop()
    }).not.toThrow()
    expect(onCommand).not.toHaveBeenCalled()
  })

  it('onError 未传时错误路径也不抛出（start/stop 空操作）', () => {
    const controller = createVoiceCommandController({ onCommand: vi.fn() })
    expect(() => {
      controller.start()
      controller.stop()
    }).not.toThrow()
  })
})
