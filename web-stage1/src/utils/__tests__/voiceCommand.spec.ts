/**
 * 文件职责：src/utils/voiceCommand.ts 单测（F 模块免手语音）。
 * 覆盖：parseVoiceCommand 白名单全指令与近义命中、关键冲突（「继续做」优先于
 *       「继续」）、大小写不敏感、带标点/前缀噪声、无命中返回 null；
 *       createVoiceCommandController 在无 Web Speech 环境的降级（supported=false、
 *       start/stop 幂等不抛、不触发 onCommand）。
 * 运行方式：npm run test（vitest run，node 环境即天然无 window/SpeechRecognition）。
 */
import { describe, expect, it, vi } from 'vitest'
import {
  createVoiceCommandController,
  parseHelpQuestion,
  parseStepNumber,
  parseTimerMinutes,
  parseVoiceCommand,
} from '../voiceCommand'

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

  it('「停止计时」及近义命中 timer_stop；关键冲突：不误判为 timer_pause / timer_open', () => {
    expect(parseVoiceCommand('停止计时')).toBe('timer_stop')
    expect(parseVoiceCommand('取消计时')).toBe('timer_stop')
    expect(parseVoiceCommand('停止')).toBe('timer_stop')
    expect(parseVoiceCommand('停一下')).toBe('timer_pause')
  })

  it('「计时」及近义命中 timer_open；「求助」及近义命中 help', () => {
    expect(parseVoiceCommand('计时')).toBe('timer_open')
    expect(parseVoiceCommand('打开计时器')).toBe('timer_open')
    expect(parseVoiceCommand('倒计时')).toBe('timer_open')
    expect(parseVoiceCommand('求助')).toBe('help')
    expect(parseVoiceCommand('帮帮忙')).toBe('help')
  })

  it('「关闭」命中 close；「关闭计时」优先归 timer_stop 而非 close', () => {
    expect(parseVoiceCommand('关闭')).toBe('close')
    expect(parseVoiceCommand('关掉')).toBe('close')
    expect(parseVoiceCommand('关闭计时')).toBe('timer_stop')
    expect(parseVoiceCommand('关闭计时器抽屉')).toBe('timer_stop')
  })

  it('「焯水」等口令命中 timer_preset；「做完了」命中 finish', () => {
    expect(parseVoiceCommand('焯水')).toBe('timer_preset')
    expect(parseVoiceCommand('煎一下')).toBe('timer_preset')
    expect(parseVoiceCommand('焖十分钟')).toBe('timer_preset')
    expect(parseVoiceCommand('做完了')).toBe('finish')
    expect(parseVoiceCommand('完成做菜')).toBe('finish')
  })

  it('关键冲突：「第一次计时」优先归 timer_open（规则表顺序保证）', () => {
    expect(parseVoiceCommand('第一次计时')).toBe('timer_open')
  })

  it('关键冲突：「暂停计时」「继续计时」优先于 timer_open（规则表顺序保证）', () => {
    expect(parseVoiceCommand('暂停计时')).toBe('timer_pause')
    expect(parseVoiceCommand('继续计时')).toBe('timer_resume')
  })
})

describe('parseTimerMinutes 计时口令分钟数提取', () => {
  it('阿拉伯数字 + 分钟（ASR ITN 输出形态）', () => {
    expect(parseTimerMinutes('计时 5 分钟')).toBe(5)
    expect(parseTimerMinutes('计时3分钟')).toBe(3)
    expect(parseTimerMinutes('炖煮 30 分')).toBe(30)
  })

  it('中文数字单字与组合', () => {
    expect(parseTimerMinutes('计时三分钟')).toBe(3)
    expect(parseTimerMinutes('焖十分钟')).toBe(10)
    expect(parseTimerMinutes('十五分钟')).toBe(15)
    expect(parseTimerMinutes('二十五分钟')).toBe(25)
  })

  it('整十中文数字不被截断为 10（旧版「四十分钟」误算 10 的回归）', () => {
    expect(parseTimerMinutes('四十分钟')).toBe(40)
    expect(parseTimerMinutes('五十分钟')).toBe(50)
    expect(parseTimerMinutes('九十分钟')).toBe(90)
    expect(parseTimerMinutes('计时二十分钟')).toBe(20)
  })

  it('未提及分钟 / 超界返回 null', () => {
    expect(parseTimerMinutes('打开计时器')).toBeNull()
    expect(parseTimerMinutes('')).toBeNull()
    expect(parseTimerMinutes('计时 999 分钟')).toBeNull()
  })
})

describe('parseStepNumber 步骤跳转口令解析', () => {
  it('阿拉伯数字与中文数字步骤号', () => {
    expect(parseStepNumber('去第 3 步')).toBe(3)
    expect(parseStepNumber('第5步')).toBe(5)
    expect(parseStepNumber('跳到第五步')).toBe(5)
    expect(parseStepNumber('第二十五步')).toBe(25)
  })

  it('未提及步骤返回 null', () => {
    expect(parseStepNumber('下一步')).toBeNull()
    expect(parseStepNumber('第一次计时')).toBeNull()
    expect(parseStepNumber('')).toBeNull()
  })
})

describe('parseHelpQuestion 求助口令问题提取', () => {
  it('剥离常见前缀口令词，保留问题正文', () => {
    expect(parseHelpQuestion('帮我求助一下 火太大怎么办')).toBe('火太大怎么办')
    expect(parseHelpQuestion('帮我发送求助怎么让肉更嫩')).toBe('怎么让肉更嫩')
    expect(parseHelpQuestion('请问盐放多了怎么补救')).toBe('盐放多了怎么补救')
    expect(parseHelpQuestion('帮我问下糊锅了怎么办')).toBe('糊锅了怎么办')
  })

  it('只说「求助」无正文返回 null；首尾标点引号被剥离', () => {
    expect(parseHelpQuestion('求助')).toBeNull()
    expect(parseHelpQuestion('')).toBeNull()
    expect(parseHelpQuestion('帮我求助「太咸了怎么办」')).toBe('太咸了怎么办')
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
