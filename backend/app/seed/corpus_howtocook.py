"""HowToCook 公开菜谱语料导入模块（spec: fix-onestart-align-v11 Task 4）。

职责：
    对齐 05-V1.1 §5.1④「导入菜谱语料（362 篇结构化）」与 §5.6 流水线：
    1. ensure_corpus()：语料缓存目录不存在时按「GitHub 直连 → 镜像加速」顺序
       git clone --depth 1 拉取 HowToCook 仓库（Unlicense 许可，禁止复用其图片）；
    2. 解析 dishes/**/*.md：菜名 / 分类 / 难度 / 卡路里 / 必备原料与工具 /
       计算用量 / 操作步骤（跳过模板、README、tips 等非菜谱文件）；
    3. 用量清洗（PRD CT-6：调味料不得「适量/少许」）：
       区间 → amount_min/amount_max；单值+克毫升级单位 → amount_value；
       数字+量词 → amount_value+unit；「N 勺」→ amount_value+勺（1 勺 ≈ 15ml）；
       「适量/少许/若干/半」→ 按调料量化映射表取常用量，amount_note 注明来源；
    4. 食材映射：原料名 → ingredient 主名/别名精确匹配；未命中自动建 minimal
       ingredient（category 启发式：调味词表 → seasoning，否则 other，
       allergen_verified=false），并统计映射命中率；
       DEF-04 脏名防护：清洗后为空/纯数字/纯符号的配料行（语料表格序号行
       「| 1 | 2 人份 |」产物）在 parse_amount_text 即记 skipped 不入库，
       入库前再兜底过滤并单独计数（dirty_name_skipped）；
    5. 导入：title 幂等去重（与手写 45 道及本批已导入重名即跳过），
       status='published'，source_label/source_license 全量标注，
       cover_image_url 留空（不引用语料图片）；
       allergen_codes / ingredient_allergen_codes 由所引食材并集聚合；
       amount_type 启发式：前 N_MAIN 个非调味项 → main，调味词表 → seasoning，
       其余 → minor。

幂等：
    recipe 按 title 存在则跳过（连带食材行与步骤行）；重复执行零新增。

被引用方：
    app/seed/__main__.py（seed 总流程在 seed_recipes 之后调用 import_corpus）。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import Ingredient, IngredientAlias, Recipe, RecipeIngredient, RecipeStep

logger = get_logger("app.seed.corpus")

# ==================== 路径与来源常量 ====================

# 语料缓存根目录：backend/data/（.gitignore 已忽略，不入库不进版本管理）
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CORPUS_DIR = DATA_DIR / "HowToCook"
DISHES_DIR = CORPUS_DIR / "dishes"

# HowToCook 仓库地址（Unlicense 公共领域）与镜像加速前缀（直连失败时依次重试）
REPO_URL = "https://github.com/Anduin2017/HowToCook.git"
MIRROR_URLS = [
    "https://gh-proxy.com/https://github.com/Anduin2017/HowToCook.git",
    "https://ghproxy.com/https://github.com/Anduin2017/HowToCook.git",
]

SOURCE_LABEL = "HowToCook / 公开家常菜语料"
SOURCE_LICENSE = "Unlicense"

# 导入规模下限（05-V1.1 §5.1④ 目标 ≥300 篇，362 篇为上限目标）
CORPUS_TARGET_MIN = 300

# amount_type 启发式：排序后前 N_MAIN 个非调味项标记为主料
N_MAIN = 3

# 跳过的非菜谱文件关键词（模板 / 仓库说明 / 烹饪技巧知识页）
SKIP_FILE_KEYWORDS = ("template", "readme", "tips")

# dishes 一级目录 → cuisine 中文分类（兼容新旧目录结构：meat_dish/vegetable_dish
# 为现行结构，dishes 为早期「主菜」目录）
CATEGORY_CUISINE: dict[str, str] = {
    "aquatic": "水产",
    "breakfast": "早餐",
    "condiment": "调味",
    "dessert": "甜点",
    "drink": "饮品",
    "meat_dish": "家常菜",
    "vegetable_dish": "家常菜",
    "soup": "汤羹",
    "staple": "主食",
    "semi-finished": "半成品",
    "dishes": "家常菜",
}

# ==================== 原料名归一化（语料名 → 食材库主名） ====================
# 仅覆盖语料高频泛称/变体写法；未收录名称走 alias 精确匹配，再未命中自动建条。
NAME_NORMALIZE_MAP: dict[str, str] = {
    # 葱姜蒜变体
    "姜": "生姜", "姜片": "生姜", "姜末": "生姜", "姜块": "生姜", "姜丝": "生姜",
    "蒜": "大蒜", "蒜瓣": "大蒜", "蒜末": "大蒜", "蒜泥": "大蒜",
    "葱": "小葱", "葱花": "小葱", "香葱": "小葱", "葱绿": "小葱",
    "葱白": "大葱", "葱段": "大葱", "葱丝": "大葱",
    # 调味泛称
    "盐": "食盐", "食用盐": "食盐", "海盐": "食盐",
    "食用油": "花生油", "油": "花生油", "色拉油": "花生油", "大豆油": "花生油",
    "菜籽油": "花生油", "玉米油": "花生油",
    "酱油": "生抽", "味极鲜": "生抽", "生抽酱油": "生抽",
    "醋": "香醋", "糖": "白糖", "白砂糖": "白糖", "绵白糖": "白糖", "细砂糖": "白糖",
    "淀粉": "玉米淀粉", "生粉": "玉米淀粉", "水淀粉": "玉米淀粉",
    "胡椒粉": "白胡椒粉", "白胡椒": "白胡椒粉", "黑胡椒": "黑胡椒碎",
    "黑胡椒粉": "黑胡椒碎", "黑胡椒粒": "黑胡椒碎",
    "芝麻油": "芝麻香油", "香油": "芝麻香油", "麻油": "芝麻香油", "小磨香油": "芝麻香油",
    "植物油": "花生油", "青葱": "小葱",
    "辣椒面": "辣椒粉", "红辣椒粉": "辣椒粉", "花椒粒": "花椒", "小米椒": "小米辣",
    "青辣椒": "青椒", "红油豆瓣酱": "豆瓣酱", "豆瓣酱 ": "豆瓣酱",
    "大蒜粒": "大蒜", "蒜粒": "大蒜", "虾": "基围虾", "河虾": "河虾",
    # 乳制品变体
    "奶油": "淡奶油", "鲜奶油": "淡奶油", "稀奶油": "淡奶油",
    # 主食变体
    "面粉": "中筋面粉", "白面": "中筋面粉",
    "剩米饭": "熟米饭", "白米饭": "熟米饭",
    "面条": "挂面",
    # 常见异名
    "西红柿": "番茄", "洋芋": "土豆", "包菜": "卷心菜", "豆角": "四季豆",
    "鸡脯肉": "鸡胸肉", "鸡腿肉": "鸡腿",
    "猪肉末": "猪肉馅", "肉末": "猪肉馅", "肉馅": "猪肉馅",
    "鲜虾": "基围虾",
    "酵母粉": "酵母", "老姜": "生姜", "蒜头": "大蒜",
    "香菜碎": "香菜", "洋葱碎": "洋葱", "洋葱丝": "洋葱",
    "蛋液": "鸡蛋", "蛋黄": "鸡蛋", "蛋白": "鸡蛋", "蛋清": "鸡蛋",
    "姜片 ": "生姜",
}

# ==================== 调味词表（amount_type=seasoning 判定 + 自动建分类启发式） ====================
# 精确匹配归一化后的原料名；用于区分调味料与主辅料（CT-6 量化口径的前提）。
SEASONING_WORDS: set[str] = {
    "食盐", "白糖", "红糖", "冰糖", "生抽", "老抽", "蚝油", "料酒", "黄酒", "白酒",
    "米酒", "花雕酒", "味淋", "香醋", "米醋", "陈醋", "白醋", "苹果醋", "香油",
    "花生油", "玉米油", "菜籽油", "橄榄油", "黄油", "辣椒油", "花椒油",
    "藤椒油", "葱油", "虾油", "玉米淀粉", "红薯淀粉", "木薯淀粉", "豌豆淀粉",
    "鸡精", "味精", "鸡粉", "鸡汁", "白胡椒粉", "黑胡椒粉", "花椒粉", "孜然粉",
    "五香粉", "十三香", "椒盐", "辣椒粉", "咖喱粉", "咖喱块", "咖喱酱", "豆瓣酱",
    "黄豆酱", "甜面酱", "番茄酱", "番茄沙司", "沙拉酱", "千岛酱", "芝麻酱",
    "花生酱", "老干妈", "腐乳", "南乳", "剁椒", "泡椒", "野山椒", "小米辣",
    "干辣椒", "青花椒", "花椒", "麻椒", "八角", "大料", "桂皮", "香叶", "草果",
    "丁香", "陈皮", "小茴香", "白芝麻", "熟芝麻", "蜂蜜", "酵母", "泡打粉",
    "小苏打", "食用碱", "炼乳", "鱼露", "蒸鱼豉油", "照烧汁", "韩式辣酱",
    "蒜蓉辣酱", "辣椒酱", "黄灯笼椒酱", "芥末", "青芥辣", "黄芥末酱",
    "味噌", "美极鲜", "卤水汁", "糟卤", "糖桂花", "麦芽糖", "白凉粉",
    "孜然粒", "黑胡椒碎", "迷迭香", "百里香", "罗勒叶", "薄荷", "香茅",
    "甜辣酱", "酸辣酱", "排骨酱", "叉烧酱", "柱侯酱", "海鲜酱", "沙茶酱",
    "XO酱", "酸梅酱", "虾酱", "调味料", "调料",
}

# ==================== 「适量」量化映射表（CT-6：调味料不得适量/少许） ====================
# 归一化名 → (常用量数值, 单位)；任务规格给定基准值，扩展常见变体同值；
# 未收录调味词兜底 FALLBACK_QUANTIZED（5g）。
PINNED_AMOUNTS: dict[str, tuple[float, str]] = {
    "食盐": (3, "g"), "白糖": (5, "g"), "冰糖": (5, "g"), "红糖": (5, "g"),
    "生抽": (10, "ml"), "酱油": (10, "ml"), "蒸鱼豉油": (10, "ml"),
    "老抽": (5, "ml"),
    "料酒": (10, "ml"), "黄酒": (10, "ml"), "白酒": (10, "ml"), "米酒": (10, "ml"),
    "香醋": (5, "ml"), "米醋": (5, "ml"), "陈醋": (5, "ml"), "白醋": (5, "ml"),
    "食用油": (15, "ml"), "花生油": (15, "ml"), "油": (15, "ml"),
    "芝麻香油": (5, "ml"), "香油": (5, "ml"), "芝麻油": (5, "ml"),
    "辣椒油": (10, "ml"), "花椒油": (5, "ml"), "藤椒油": (5, "ml"),
    "玉米淀粉": (5, "g"), "淀粉": (5, "g"), "生粉": (5, "g"), "水淀粉": (5, "g"),
    "鸡精": (2, "g"), "味精": (2, "g"), "鸡粉": (2, "g"),
    "胡椒粉": (1, "g"), "白胡椒粉": (1, "g"), "黑胡椒粉": (1, "g"), "黑胡椒碎": (1, "g"),
    "十三香": (1, "g"), "五香粉": (1, "g"), "孜然粉": (1, "g"),
    "辣椒粉": (1, "g"), "花椒粉": (1, "g"), "椒盐": (1, "g"), "咖喱粉": (5, "g"),
    "豆瓣酱": (15, "g"), "黄豆酱": (15, "g"), "甜面酱": (15, "g"),
    "蚝油": (10, "ml"),
    "白芝麻": (3, "g"), "熟芝麻": (3, "g"), "芝麻": (3, "g"),
    "蜂蜜": (10, "g"),
    "番茄酱": (15, "g"), "番茄沙司": (15, "g"), "辣椒酱": (15, "g"),
    "芝麻酱": (10, "g"), "花生酱": (10, "g"),
    "花椒": (2, "g"), "八角": (2, "g"), "干辣椒": (3, "g"), "小米辣": (5, "g"),
}
# 未收录调料兜底量（任务规格：未收录调料兜底 5g）
FALLBACK_QUANTIZED = (5.0, "g")
# 「适量」量化行的 amount_note 固定措辞（向用户披露量化依据）
QUANTIZE_NOTE = "原语料为适量，按常用量量化；请以实际食材包装标签为准"
# 量化表短泛称别名补查（NAME_NORMALIZE_MAP 未覆盖时兜底）
_NAME_ALIAS_FOR_QUANT: dict[str, str] = {
    "盐": "食盐", "糖": "白糖", "醋": "香醋", "酱油": "生抽",
    "油": "花生油", "淀粉": "玉米淀粉", "胡椒粉": "白胡椒粉", "芝麻": "白芝麻",
}

# ==================== 工具识别词表 ====================
# 「必备原料和工具」混合清单中判定为设备的关键词（包含式）；命中即计入 equipment。
TOOL_KEYWORDS: tuple[str, ...] = (
    "锅", "刀", "砧板", "筷子", "勺", "铲", "擀面杖", "锡纸", "保鲜膜", "模具",
    "烤盘", "蒸笼", "料理机", "破壁机", "榨汁机", "搅拌机", "打蛋器", "滤网",
    "滤布", "筛", "刷", "剪刀", "厨房纸", "牙签", "竹签", "温度计", "油纸",
    "纱布", "电磁炉", "灶台", "裱花", "刮刀", "漏勺", "网架", "烤架", "蒸布",
    "量杯", "厨房秤", "电子秤", "密封袋", "保鲜袋", "食品袋", "不锈钢碗", "大碗", "盆",
)

# ==================== 忽略词（水类行不入 recipe_ingredient） ====================
# 语料计算节大量出现「水/清水 200ml」——水非食材亦非营养来源，忽略并单独计数。
WATER_WORDS: set[str] = {
    "水", "清水", "开水", "热水", "温水", "凉水", "冷水", "冰水", "凉白开",
    "饮用水", "纯净水", "冰块", "冰", "冰粒",
}

# ==================== 烹饪方式启发式（标题关键词 → cooking_method） ====================
# 按关键词在标题中的出现位置取最先者；未命中为 None（列可空）。
COOKING_METHOD_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("炒", "炒"), ("蒸", "蒸"), ("煮", "煮"), ("汆", "煮"), ("氽", "煮"), ("烫", "煮"),
    ("炖", "炖"), ("煨", "炖"), ("煲", "炖"), ("烤", "烤"), ("烘", "烤"), ("炸", "炸"),
    ("煎", "煎"), ("焖", "焖"), ("烧", "烧"), ("卤", "卤"), ("拌", "拌"),
    ("腌", "腌"), ("泡", "泡"), ("冻", "冻"), ("焗", "焗"), ("酿", "蒸"), ("烩", "烩"),
)

# ==================== 用量解析正则 ====================
# 中文数字（含「两」「半」）转数值；支持 0~99 常见写法
_CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNIT = {"十": 10, "百": 100}

# 数值片段：阿拉伯数字或中文数字
_NUM = r"(?:\d+(?:\.\d+)?|[零一二两三四五六七八九十百]+)"
# 重量/容积单位
_WEIGHT_UNIT = r"(?:千克|公斤|kg|KG|克|g|G|斤|两|升|L|毫升|ml|mL|ML|cc)"
# 量词集合（含勺类与常见大小修饰组合，勺类单独走换算口径）
_COUNT_UNIT = (r"(?:(?:小|大|半|整)?(?:个|根|片|块|颗|只|瓣|条|把|段|张|包|盒|瓶|罐|杯|碗|朵|枝|支|袋|"
               r"卷|枚|粒|滴|圈|层|份|人份|勺|小勺|大勺|汤匙|茶匙|棵|头|尾|碟|撮|双|串|束|听|扎|板|锅|点|节|角|叶))")

# 区间型用量：「10-15ml」「3~4 个」「2 至 3 克」「300g 至 500g」（单位可在区间任一侧；
# 优先于单值匹配，防止截断）
RE_INTERVAL = re.compile(
    rf"(?P<min>{_NUM})\s*(?P<u1>{_WEIGHT_UNIT})?\s*[-~～至]{{1,2}}\s*(?P<max>{_NUM})\s*(?P<unit>{_WEIGHT_UNIT}|{_COUNT_UNIT})?"
)
# 单值型用量（重量/容积单位，归一化 g/ml）
RE_VALUE = re.compile(rf"(?P<val>{_NUM})\s*(?P<unit>{_WEIGHT_UNIT})")
# 量词型用量：「3 个」「1 条」「半根」「2 勺」「1 小块」
RE_COUNT = re.compile(rf"(?P<val>{_NUM})\s*(?P<unit>{_COUNT_UNIT})")
# 「适量/少许/若干/半/个人口味/几X」模糊用量（兜底量化，保证 CT-6 全量化）
RE_VAGUE = re.compile(r"适量|少许|若干|个人口味|几[滴片根颗粒瓣块勺包条个]|半")
# 说明行（计算节中的引导语/标题语，非用量行，忽略且不记 skipped）
RE_PROSE_HEAD = re.compile(r"^(每份|每\s*[0-9一两二三四五六七八九十]|一份|总量|注意|说明|备注|参考|原料|工具|成品|份量|提示|小贴士|参数|配方)")
RE_PROSE_CONTAIN = re.compile(r"计划做几份|使用上述条件|人食用|人份的版本|^\d+\s*人份|按照.{0,8}份量|以上原料|如下|以下|份量表|营养")
# 括号注释（用量匹配前剥离，防止「（大约 300g）」中的数字被误当用量）
RE_PAREN_COMMENT = re.compile(r"[（(【\[].*?[）)】\]]")

# 步骤时长抽取：小时 / 分钟 / 秒（阿拉伯数字）
RE_DURATION_HOUR = re.compile(r"(\d+(?:\.\d+)?)\s*(?:个\s*)?(?:小时|h|hr)", re.IGNORECASE)
RE_DURATION_MIN = re.compile(r"(\d+(?:\.\d+)?)\s*分钟|(\d+(?:\.\d+)?)\s*min", re.IGNORECASE)
RE_DURATION_SEC = re.compile(r"(\d+(?:\.\d+)?)\s*(?:秒|s|sec)", re.IGNORECASE)

# 语料元信息行
RE_DIFFICULTY = re.compile(r"难度[：:]\s*([★✦☆]+)")
RE_KCAL = re.compile(r"(?:卡路里|热量)[：:]?\s*约?\s*(\d+)\s*(?:大卡|千卡|kcal)?", re.IGNORECASE)

# 图片行（不落库：语料图片禁止复用）
RE_IMAGE_LINE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# markdown 内联链接（仅保留锚文本）
RE_INLINE_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
# emoji/杂项符号（部分语料行带 ☕🍫 等装饰符，剥离后清洗名称）
RE_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\ufe0f]"
)


def _cn_to_num(text: str | None) -> float | None:
    """中文数字串转数值（函数）。

    说明：
        支持 0~99 的常见中文写法与「半」（0.5）、纯阿拉伯数字；
        解析失败返回 None（由调用方记为 skipped）。

    参数：
        text：数字片段（阿拉伯或中文数字），可为 None。

    返回值：
        float | None：对应数值；无法解析时 None。
    """
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    # 纯阿拉伯数字直接转 float
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    if text == "半":
        return 0.5
    total, num = 0.0, 0
    for ch in text:
        if ch in _CN_DIGIT:
            num = _CN_DIGIT[ch]
        elif ch in _CN_UNIT:
            # 「十」前无数字视作 1（如「十五」=15）
            num = 1 if num == 0 else num
            total += num * _CN_UNIT[ch]
            num = 0
        else:
            return None
    return float(total + num)


def _clean_name(raw: str) -> str:
    """清洗原料名称（函数）。

    说明：
        去括号注释、内联链接锚文本化、按首个句读切分（去除「其中应该包含：」
        等说明尾巴）、去首尾空白与标点。

    参数：
        raw：原始名称片段。

    返回值：
        str：清洗后的名称（可能为空串）。
    """
    name = RE_IMAGE_LINE.sub("", raw)
    name = RE_EMOJI.sub("", name)
    name = RE_INLINE_LINK.sub(r"\1", name)
    name = re.sub(r"[（(【\[].*?[）)】\]]", "", name)  # 去括号内的注释说明
    # 句读/顿号/「或」后的内容为说明或并列项（如「白砂糖或冰糖」取首项）
    name = re.split(r"[，,。;；！!？?、]|或", name)[0]
    # 空格后的文字多为说明尾巴（如「可有不同搭配」）；中文名不含空格，取首段
    name = name.split()[0] if name.strip() else ""
    name = name.strip(" \t　:：、;；.。*->—=＋+")
    return name


def _is_dirty_ingredient_name(name: str | None) -> bool:
    """判定清洗后的配料名是否为脏名（DEF-04，函数）。

    说明：
        语料表格行存在「| 1 | 2 人份 |」类写法——序号列被当作名称、份数列被
        量词型用量匹配吞掉，最终产出 name='1' 的脏 ingredient（前端表现为
        「缺 1」脏标签）。判定口径：strip 后为空，或不含任何文字字符
        （字母/汉字等 Unicode 字母，纯数字与纯符号均视为脏名）。

    参数：
        name：清洗/归一化后的配料名（可 None）。

    返回值：
        bool：True 表示脏名（应跳过并计数）；False 表示正常名称。

    异常：
        无。
    """
    if not name:
        return True
    text = str(name).strip()
    if not text:
        return True
    return not any(ch.isalpha() for ch in text)


def _normalize_name(name: str) -> str:
    """原料名归一化（函数）。

    说明：
        小写化（英文）、按「/」拆分取首段、去空白后查 NAME_NORMALIZE_MAP。

    参数：
        name：清洗后的原料名。

    返回值：
        str：归一化名称（可能仍为原名，表示无等价映射）。
    """
    key = name.strip().lower().split("/")[0].strip()
    if key in NAME_NORMALIZE_MAP:
        return NAME_NORMALIZE_MAP[key]
    return key


def _norm_unit(unit: str | None) -> str | None:
    """单位归一化（函数）。

    说明：
        重量类统一为 g、容积类统一为 ml（数值换算由 _norm_unit_value 完成）。

    参数：
        unit：原始单位串。

    返回值：
        str | None：归一化单位；入参为 None 时返回 None。
    """
    if not unit:
        return None
    u = unit.strip().lower()
    if u in ("克", "g", "千克", "公斤", "kg", "斤", "两", "吨"):
        return "g"
    if u in ("毫升", "ml", "升", "l", "cc"):
        return "ml"
    return unit.strip()


def _norm_unit_value(val: float, unit: str | None) -> tuple[float, str | None]:
    """按单位换算数值到归一化单位（函数）。

    说明：
        千克/公斤/kg → ×1000；斤 → ×500；两 → ×50；升/L → ×1000（ml）。

    参数：
        val：原始数值。
        unit：原始单位（未归一化）。

    返回值：
        tuple[float, str | None]：(换算后数值, 归一化单位)。
    """
    if unit is None:
        return (val, None)
    u = unit.strip().lower()
    if u in ("千克", "公斤", "kg"):
        return (val * 1000, "g")
    if u == "斤":
        return (val * 500, "g")
    if u == "两":
        return (val * 50, "g")
    if u in ("升", "l"):
        return (val * 1000, "ml")
    if u in ("克", "g"):
        return (val, "g")
    if u in ("毫升", "ml"):
        return (val, "ml")
    return (val, unit)


def _quantize_vague(norm_name: str) -> dict:
    """将模糊用量（适量/少许）按调料量化映射表转为常用量（函数）。

    说明：
        先查 PINNED_AMOUNTS（任务规格基准值），再查短泛称别名补查表，
        均未命中按 FALLBACK_QUANTIZED（5g）兜底——保证 CT-6 全量化。

    参数：
        norm_name：归一化后的原料名。

    返回值：
        dict：{"value": 数值, "unit": "g"|"ml", "note": QUANTIZE_NOTE}。
    """
    pinned = (
        PINNED_AMOUNTS.get(norm_name)
        or PINNED_AMOUNTS.get(_NAME_ALIAS_FOR_QUANT.get(norm_name, ""))
        or FALLBACK_QUANTIZED
    )
    return {"value": float(pinned[0]), "unit": pinned[1], "note": QUANTIZE_NOTE}


def _is_tool(name: str) -> bool:
    """判定名称是否为烹饪工具/设备（函数）。

    参数：
        name：清洗后的名称（未归一化）。

    返回值：
        bool：True 表示工具（计入 equipment 而非食材）。
    """
    if name in WATER_WORDS:
        return False
    return any(kw in name for kw in TOOL_KEYWORDS)


def _extract_duration(text: str) -> int | None:
    """从步骤文本抽取时长秒数（函数）。

    说明：
        优先小时（×3600），其次分钟（×60），再次秒（×1）；取第一个命中。

    参数：
        text：步骤文本。

    返回值：
        int | None：时长秒数；未抽取到为 None。
    """
    m = RE_DURATION_HOUR.search(text)
    if m:
        return int(float(m.group(1)) * 3600)
    m = RE_DURATION_MIN.search(text)
    if m:
        raw = m.group(1) or m.group(2)
        return int(float(raw) * 60)
    m = RE_DURATION_SEC.search(text)
    if m:
        return int(float(m.group(1)))
    return None


def _split_sections(text: str) -> dict[str, list[str]]:
    """按二级标题切分 md 正文（函数）。

    参数：
        text：md 全文。

    返回值：
        dict[str, list[str]]：节标题 → 节内行列表（保留顺序与原始缩进）。
    """
    sections: dict[str, list[str]] = {"_head": []}
    current = "_head"
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            current = m.group(1).strip()
            sections.setdefault(current, [])
        else:
            sections[current].append(line)
    return sections


def parse_amount_text(text: str) -> tuple[str, dict | None, str]:
    """解析「名称 用量」行，拆出名称并清洗用量（函数，CT-6 核心）。

    说明：
        先判说明行（每份/总量/注意等引导语，记 prose 不计失败），再在行文本上
        按优先级定位用量片段：区间型 → 单值克毫升级 → 量词型 → 适量量化；
        名称截断为用量片段之前的部分。均未命中记 skipped。水类行记 water，
        忽略不入库。勺类量词固定口径 1 勺 ≈ 15ml 写入 amount_note。

    参数：
        text：计算节列表行的原始文本（如「食用油 10-15ml」）。

    返回值：
        tuple[str, dict | None, str]：(清洗后名称, 用量字典, 行类型)。
        用量字典键：value/min/max/unit/note（按类型取舍）。
        行类型 ∈ interval/value/count/spoon/quantize/skipped/water/prose。
    """
    name = _clean_name(text)
    norm = _normalize_name(name)
    # 说明行：计算节引导语（「每份：」「总量」等），非用量行
    raw_clean = text.strip()
    if RE_PROSE_HEAD.match(raw_clean) or RE_PROSE_CONTAIN.search(raw_clean):
        return (name, None, "prose")
    # 水类行：可解析但语义上非食材，忽略并单独计数
    if norm in WATER_WORDS:
        return (name, None, "water")
    # DEF-04 脏名行：清洗后名称为空/纯数字/纯符号（如表格序号行「| 1 | 2 人份 |」
    # 被拆成 name='1' + 用量「2 人份」）→ 直接记 skipped，不再产出脏 ingredient
    if _is_dirty_ingredient_name(name):
        return (name, None, "skipped")

    # 冒号替换为空格便于「名称：用量」定位；括号注释剥离（等长无关，仅用于用量定位）
    search_src = RE_PAREN_COMMENT.sub(" ", text).replace("：", " ").replace(":", " ")

    def _as_water(head_name: str) -> bool:
        """判断截断后的名称是否为水类（内部函数）。

        参数：
            head_name：截断后的名称。

        返回值：
            bool：True 表示水类行（应忽略）。
        """
        return bool(head_name) and _normalize_name(head_name) in WATER_WORDS

    # 1) 区间型：「10-15ml」「3~4 个」「300g 至 500g」→ amount_min/amount_max
    # （单位可在 min 侧或 max 侧；要求名称非空，防「八角」被拆成量词）
    for m in RE_INTERVAL.finditer(search_src):
        mn, mx = _cn_to_num(m.group("min")), _cn_to_num(m.group("max"))
        unit = _norm_unit(m.group("u1") or m.group("unit"))
        head = _clean_name(search_src[:m.start()])
        if mn is None or mx is None or not head:
            continue
        if _as_water(head):
            return (head, None, "water")  # 水类行立即终止（不继续找其它匹配）
        return (head, {"min": mn, "max": mx, "unit": unit}, "interval")
    # 2) 单值 + 克毫升级单位 → amount_value（kg/斤/升后续统一换算）
    for m in RE_VALUE.finditer(search_src):
        val, unit = _cn_to_num(m.group("val")), _norm_unit(m.group("unit"))
        head = _clean_name(search_src[:m.start()])
        if val is None or not head:
            continue
        if _as_water(head):
            return (head, None, "water")
        return (head, {"value": val, "unit": unit}, "value")
    # 3) 数字 + 量词 → amount_value + unit；勺类走固定换算口径
    for m in RE_COUNT.finditer(search_src):
        val, unit = _cn_to_num(m.group("val")), m.group("unit")
        head = _clean_name(search_src[:m.start()])
        if val is None or not head:
            continue
        if _as_water(head):
            return (head, None, "water")
        if unit in ("勺", "小勺", "大勺", "汤匙", "茶匙"):
            return (head, {"value": val, "unit": "勺", "note": "1 勺 ≈ 15ml"}, "spoon")
        return (head, {"value": val, "unit": unit}, "count")
    # 4) 适量/少许/若干/半/个人口味 → 调料量化映射表（CT-6：不得适量；水类行不量化）
    if norm not in WATER_WORDS and RE_VAGUE.search(search_src):
        return (name, _quantize_vague(norm), "quantize")
    # 5) 无法解析 → 该行记 skipped
    return (name, None, "skipped")


def parse_dish_file(md_path: Path) -> dict | None:
    """解析单篇菜谱 md（函数）。

    说明：
        提取菜名/难度/卡路里/工具/原料用量行/步骤行；「必备原料和工具」中
        工具词项归 equipment，其余为必备原料名（计算节缺失项按适量量化补充）；
        「计算」节支持列表行与表格行，嵌套缩进行视为说明文本跳过；
        「操作」节跳过图片行后按出现顺序重排步骤号。

    参数：
        md_path：md 文件路径。

    返回值：
        dict | None：解析结果字典（键 title/cuisine/cooking_method/difficulty/
        calories_kcal/equipment/materials/steps）；无有效一级标题时返回 None。

    异常：
        文件读取异常向上抛出（由调用方按单篇失败记录并继续）。
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = md_path.read_text(encoding="gb18030", errors="ignore")
    sections = _split_sections(text)

    # 菜名：一级标题去掉「的做法」后缀；缺失时回退文件名
    title = None
    for line in sections.get("_head", []):
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            title = m.group(1).strip()
            break
    if title:
        title = re.sub(r"的做法$", "", title).strip()
    if not title:
        title = md_path.stem.strip()
    if not title:
        return None

    # 难度：★★★ → 3（1~5 截断），缺省 3
    difficulty = 3
    dm = RE_DIFFICULTY.search(text)
    if dm:
        difficulty = max(1, min(5, dm.group(1).count("★") + dm.group(1).count("✦")))

    # 卡路里：「预估卡路里：385 大卡」→ 385；无则 None（允许 NULL）
    calories_kcal: int | None = None
    km = RE_KCAL.search(text)
    if km:
        calories_kcal = int(km.group(1))

    # 分类：dishes 下第一级目录名映射；未知目录回退「家常菜」
    try:
        rel = md_path.relative_to(DISHES_DIR)
        top_dir = rel.parts[0] if len(rel.parts) > 1 else ""
    except ValueError:
        top_dir = ""
    cuisine = CATEGORY_CUISINE.get(top_dir, "家常菜")

    # 烹饪方式：标题关键词启发式，取最先出现者；未命中 None
    cooking_method = None
    best_pos = len(title)
    for kw, method in COOKING_METHOD_KEYWORDS:
        pos = title.find(kw)
        if pos >= 0 and pos < best_pos:
            best_pos, cooking_method = pos, method

    # ---- 必备原料和工具（兼容 ### 原料 / ### 工具 子节） ----
    equipment: list[str] = []
    required_names: list[str] = []
    in_tool_subsection = False
    for line in sections.get("必备原料和工具", []):
        stripped = line.strip()
        # 空行 / 引用说明 / 图片行 / 表格行跳过
        if not stripped or stripped.startswith(">") or RE_IMAGE_LINE.search(stripped):
            continue
        sm = re.match(r"^###\s+(.+?)\s*$", stripped)
        if sm:
            in_tool_subsection = "工具" in sm.group(1)  # 子节跟踪
            continue
        if stripped.startswith("#") or stripped.startswith("|") or stripped == "---":
            continue
        item = _clean_name(stripped.lstrip("-*").lstrip(" "))
        if not item or len(item) > 50:
            continue
        # 缩进的嵌套行属于说明（如袋装料包含子项），不入清单
        if line.startswith(("  ", "\t", "    ")):
            continue
        if in_tool_subsection or _is_tool(item):
            if item not in equipment:
                equipment.append(item)
        else:
            required_names.append(item)

    # ---- 计算节：原料 + 用量（列表行与表格行） ----
    materials: list[tuple[str, dict | None, str]] = []
    seen_calc_names: set[str] = set()
    skipped_rows: list[tuple[str, str]] = []  # (原始名称, 归一化名) 待二次判定
    for line in sections.get("计算", []):
        stripped = line.strip()
        if not stripped or stripped.startswith(">") or stripped.startswith("#") or stripped == "---":
            continue
        if RE_IMAGE_LINE.search(stripped):
            continue
        if stripped.startswith("|"):
            # 表格行：「| 名称 | 用量 |」；跳过分隔行与表头行
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) < 2 or set(cells[0]) <= set("-: "):
                continue
            if cells[0] in ("原料", "名称", "食材", "材料", "用量", "项目"):
                continue
            name, amount, kind = parse_amount_text(f"{cells[0]} {cells[1]}")
        else:
            # 列表行 / 普通行（支持 - * + 三种列表前缀）；嵌套缩进行为说明文本，跳过
            if line.startswith(("  ", "\t", "    ")):
                continue
            body = stripped.lstrip("+-*").lstrip(" ")
            body = re.sub(r"^\d+[.、)]\s*", "", body)  # 有序列表前缀
            if not body or body.startswith(("#", ">")):
                continue
            name, amount, kind = parse_amount_text(body)
        if kind == "prose":
            materials.append((name, None, "prose"))  # 说明行仅计数，不入库
            continue
        if kind == "skipped":
            # 暂存待二次判定：名称命中必备清单/调味词表时转适量量化
            skipped_rows.append((name, _normalize_name(name)))
            continue
        if kind == "water":
            materials.append((name, None, "water"))
            continue
        # 计算节中的工具行（如「密封袋 1 个」）→ 归设备，不入食材
        if kind != "dup" and _is_tool(name):
            if name not in equipment:
                equipment.append(name)
            materials.append((name, None, "tool"))
            continue
        # 重名行去重（同菜内归一化重名仅首次入库）
        norm = _normalize_name(name)
        if not norm or norm in seen_calc_names:
            materials.append((name, amount, "dup"))
            continue
        seen_calc_names.add(norm)
        materials.append((name, amount, kind))

    # ---- 必备原料清单中计算节缺失的项 → 尝试解析自带用量，否则适量量化 ----
    for item in required_names:
        # 先解析（清单行可能自带用量，如「鸡蛋 1 个」），再以解析后名称判重
        name2, amount2, kind2 = parse_amount_text(item)
        base_name = name2 or _clean_name(item) or item
        norm = _normalize_name(base_name)
        # 说明行 / 水类行 / 工具行不入清单；名称脏（含空白或过长、为空/纯数字，DEF-04）
        # 不量化兜底
        if (not norm or norm in seen_calc_names or norm in WATER_WORDS
                or kind2 == "prose" or _is_tool(base_name) or len(base_name) > 10
                or re.search(r"\s", base_name) or _is_dirty_ingredient_name(base_name)):
            continue
        seen_calc_names.add(norm)
        if amount2 is not None and kind2 not in ("skipped", "prose"):
            materials.append((base_name, amount2, kind2))
        else:
            materials.append((base_name, _quantize_vague(norm), "quantize"))

    # ---- 计算节 skipped 行二次判定：命中必备清单/调味词表 → 适量量化兜底 ----
    for raw_name, norm in skipped_rows:
        if norm and norm not in seen_calc_names and (
            norm in SEASONING_WORDS or norm in PINNED_AMOUNTS
            or norm in _NAME_ALIAS_FOR_QUANT
        ):
            seen_calc_names.add(norm)
            materials.append((raw_name, _quantize_vague(norm), "quantize"))
        else:
            materials.append((raw_name, None, "skipped"))  # 无法解析，保持 skipped

    # ---- 操作节：有序步骤（纯图片行丢弃，其余保留文本并重排编号） ----
    steps: list[str] = []
    for line in sections.get("操作", []):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ">", "|")) or stripped == "---":
            continue
        if RE_IMAGE_LINE.fullmatch(stripped):
            continue  # 纯图片行：语料图片禁止复用，直接丢弃
        body = stripped.lstrip("-*").lstrip(" ")
        body = re.sub(r"^\d+[.、)]\s*", "", body)
        body = RE_INLINE_LINK.sub(r"\1", body).strip()
        if body:
            steps.append(body)

    return {
        "title": title[:100],
        "cuisine": cuisine,
        "cooking_method": cooking_method,
        "difficulty": difficulty,
        "calories_kcal": calories_kcal,
        "equipment": equipment,
        "materials": materials,
        "steps": steps,
    }


def ensure_corpus() -> bool:
    """确保 HowToCook 语料缓存就绪（函数）。

    说明：
        dishes 目录存在即返回 True；否则按「GitHub 直连 → 镜像加速前缀」顺序
        执行 git clone --depth 1（缓存到 backend/data/HowToCook，.gitignore 已
        忽略）。全部失败打印告警并返回 False（调用方降级继续，不阻断 seed）。

    返回值：
        bool：语料是否就绪。

    异常：
        不向上抛出（git 失败仅告警）。
    """
    if DISHES_DIR.is_dir():
        return True
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    for url in (REPO_URL, *MIRROR_URLS):
        print(f"[seed][corpus] 尝试克隆 HowToCook 语料：{url}")
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", url, str(CORPUS_DIR)],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0 and DISHES_DIR.is_dir():
                print(f"[seed][corpus] 语料克隆成功：{url}")
                return True
            logger.warning("corpus_clone_failed url=%s stderr=%s", url, (result.stderr or "")[-300:])
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("corpus_clone_error url=%s err=%s", url, exc)
        # 失败清理半成品目录后重试下一镜像
        if CORPUS_DIR.exists():
            shutil.rmtree(CORPUS_DIR, ignore_errors=True)
    print("[seed][corpus][warn] 语料下载失败（网络不可达），本轮跳过语料导入。")
    return False


def import_corpus(session: Session) -> dict:
    """解析并导入 HowToCook 语料菜谱（函数，幂等）。

    说明：
        流程：ensure_corpus → 遍历 dishes/**/*.md（跳过模板/README/tips）→
        parse_dish_file → title 去重（与库内全部菜谱 + 本批已导入比对）→
        食材映射（主名/别名精确匹配，未命中自动建 minimal ingredient）→
        构造 Recipe/RecipeIngredient/RecipeStep（status=published、来源标注、
        封面留空）→ 致敏原聚合 → 落库。统计随返回值输出（映射命中率 /
        用量清洗分类计数 / 跳过清单）。

    参数：
        session：SQLAlchemy 会话（由调用方管理事务）。

    返回值：
        dict：导入统计（键含 md_total/parsed/imported/skipped/ing_refs/
        ing_hits/ing_new/amount_* / water_ignored / skipped_samples）。

    异常：
        数据库操作异常向上抛出（由调用方回滚）。
    """
    stats: dict = {
        "corpus_ready": False,
        "md_total": 0, "parsed": 0, "imported": 0,
        "ing_refs": 0, "ing_hits": 0, "ing_new": 0,
        "new_ingredient_names": [],
        "amount_interval": 0, "amount_value": 0, "amount_count": 0,
        "amount_spoon": 0, "amount_quantize": 0, "amount_skipped": 0,
        "prose_ignored": 0, "tool_ignored": 0, "water_ignored": 0,
        "dirty_name_skipped": 0,
        "skipped": [],
    }
    if not ensure_corpus():
        return stats
    stats["corpus_ready"] = True

    # 收集全部菜谱 md（递归：部分菜谱带同名图片子目录）
    md_files = sorted(
        p for p in DISHES_DIR.rglob("*.md")
        if not any(kw in p.name.lower() for kw in SKIP_FILE_KEYWORDS)
    )
    stats["md_total"] = len(md_files)

    # 食材映射表：主名 → Ingredient；别名 → Ingredient
    by_name: dict[str, Ingredient] = {obj.name: obj for obj in session.query(Ingredient).all()}
    id_to_ing: dict[int, Ingredient] = {obj.id: obj for obj in session.query(Ingredient).all()}
    by_alias: dict[str, Ingredient] = {}
    for alias in session.query(IngredientAlias).all():
        ing = id_to_ing.get(alias.ingredient_id)
        if ing is not None:
            by_alias[alias.alias] = ing

    # 幂等：与库内全部菜谱标题比对（含手写 45 道 + 历史语料）
    existing_titles: set[str] = {row[0] for row in session.query(Recipe.title).all()}

    def _resolve_or_create(norm_name: str) -> tuple[Ingredient | None, bool]:
        """按归一化名解析食材，未命中自动建 minimal ingredient（内部函数）。

        参数：
            norm_name：归一化原料名（入库时截断至 50 字符）。

        返回值：
            tuple[Ingredient | None, bool]：(食材 ORM, 是否命中既有词条)；
            名称清洗后为空时返回 (None, False)。

        异常：
            数据库操作异常向上抛出。
        """
        if not norm_name:
            return (None, False)
        # DEF-04：脏名（空/纯数字/纯符号）绝不建词条——防止「缺 1」类 ingredient 落库
        if _is_dirty_ingredient_name(norm_name):
            return (None, False)
        if norm_name in by_name:
            return (by_name[norm_name], True)
        if norm_name in by_alias:
            return (by_alias[norm_name], True)
        # 未命中：自动建 minimal ingredient（category 启发式：调味词 → seasoning，
        # 否则 other；致敏原未核实 → allergen_verified=false）
        category = "seasoning" if norm_name in SEASONING_WORDS else "other"
        ing = Ingredient(
            name=norm_name[:50], category=category,
            allergen_codes=[], allergen_verified=False,
        )
        session.add(ing)
        session.flush()  # 立即取 id 供 recipe_ingredient 外键引用
        by_name[norm_name] = ing
        stats["ing_new"] += 1
        if len(stats["new_ingredient_names"]) < 50:
            stats["new_ingredient_names"].append(norm_name)
        return (ing, False)

    for md_path in md_files:
        try:
            dish = parse_dish_file(md_path)
        except Exception as exc:  # 单篇解析失败不阻断整批导入
            stats["skipped"].append((md_path.name, f"解析异常: {exc}"))
            continue
        if dish is None:
            stats["skipped"].append((md_path.name, "结构不可解析"))
            continue
        stats["parsed"] += 1

        title = dish["title"]
        # title 幂等去重：库内已存在或本批已导入 → 跳过并记录
        if title in existing_titles:
            stats["skipped"].append((title, "重名跳过（库内已存在）"))
            continue

        # 水类忽略 / 说明行 / 工具行 / 无法解析行计数（报告口径）
        for _n, _a, kind in dish["materials"]:
            if kind == "water":
                stats["water_ignored"] += 1
            elif kind == "prose":
                stats["prose_ignored"] += 1
            elif kind == "tool":
                stats["tool_ignored"] += 1
            elif kind == "skipped":
                stats["amount_skipped"] += 1

        # 有效食材行：过滤 skipped/water/dup/prose/tool + DEF-04 脏名行
        # （清洗后为空/纯数字/纯符号，单独计数便于排查语料质量）
        all_rows = [
            r for r in dish["materials"] if r[2] not in ("skipped", "water", "dup", "prose", "tool")
        ]
        rows = [r for r in all_rows if not _is_dirty_ingredient_name(r[0])]
        stats["dirty_name_skipped"] += len(all_rows) - len(rows)
        if not rows:
            stats["skipped"].append((title, "无有效食材行"))
            continue

        # 构造菜谱（默认口径：difficulty=3 / time=30min / servings=2 / equipment 缺省炒锅）
        recipe = Recipe(
            title=title,
            cuisine=dish["cuisine"],
            cooking_method=dish["cooking_method"],
            difficulty=dish["difficulty"],
            time_minutes=30,
            servings=2,
            calories_kcal=dish["calories_kcal"],
            allergen_codes=[],
            ingredient_allergen_codes=[],
            dietary_flags=[],
            equipment=dish["equipment"] or ["炒锅"],
            cover_image_url=None,  # 🔴 语料图片禁止复用（05-V1.1 §5.6），封面留空
            source_label=SOURCE_LABEL,
            source_license=SOURCE_LICENSE,
            status="published",
            version=1,
            tips=None,
            substitutes=[],
        )

        # 食材行：致敏原聚合 + amount_type 启发式
        aggregated: set[str] = set()
        # 调味判定预计算（按行序）：归一化名命中调味词表 → seasoning
        seasoning_flags = [_normalize_name(n) in SEASONING_WORDS for n, _a, _k in rows]
        main_quota = N_MAIN  # 前 N_MAIN 个非调味项标记为主料
        for idx, (name, amount, kind) in enumerate(rows):
            norm = _normalize_name(name)
            ing, hit = _resolve_or_create(norm)
            if ing is None:
                continue
            stats["ing_refs"] += 1
            if hit:
                stats["ing_hits"] += 1
            aggregated.update(ing.allergen_codes or [])
            # amount_type：调味词表 → seasoning；非调味项按序前 N_MAIN 个 → main；其余 minor
            if seasoning_flags[idx]:
                amount_type = "seasoning"
            elif main_quota > 0:
                amount_type, main_quota = "main", main_quota - 1
            else:
                amount_type = "minor"
            unit = (amount or {}).get("unit")
            note = (amount or {}).get("note")
            # 区间型 → amount_min/amount_max（单位归一化换算）
            if kind == "interval" and amount:
                mn, mn_u = _norm_unit_value(amount["min"], unit)
                mx, _mx_u = _norm_unit_value(amount["max"], unit)
                recipe.ingredients.append(RecipeIngredient(
                    ingredient_id=ing.id, amount_min=mn, amount_max=mx,
                    amount_unit=mn_u, amount_note=note, amount_type=amount_type,
                    sort_order=len(recipe.ingredients),
                ))
                stats["amount_interval"] += 1
            # 单值克毫升级 → amount_value（kg/斤/升统一换算）
            elif kind == "value" and amount:
                val, val_u = _norm_unit_value(amount["value"], unit)
                recipe.ingredients.append(RecipeIngredient(
                    ingredient_id=ing.id, amount_value=val, amount_unit=val_u,
                    amount_note=note, amount_type=amount_type,
                    sort_order=len(recipe.ingredients),
                ))
                stats["amount_value"] += 1
            # 量词型 / 勺型 → amount_value + 原量词单位
            elif kind in ("count", "spoon") and amount:
                recipe.ingredients.append(RecipeIngredient(
                    ingredient_id=ing.id, amount_value=amount["value"],
                    amount_unit=unit, amount_note=note,
                    amount_type=amount_type, sort_order=len(recipe.ingredients),
                ))
                stats["amount_spoon" if kind == "spoon" else "amount_count"] += 1
            # 适量量化型 → 映射表常用量 + 固定披露 note
            elif kind == "quantize" and amount:
                recipe.ingredients.append(RecipeIngredient(
                    ingredient_id=ing.id, amount_value=amount["value"],
                    amount_unit=amount["unit"], amount_note=amount["note"],
                    amount_type=amount_type, sort_order=len(recipe.ingredients),
                ))
                stats["amount_quantize"] += 1
            else:
                # 理论不可达（rows 已过滤 skipped），防御性计数
                stats["amount_skipped"] += 1

        # 步骤行：description + 从文本抽取时长秒数；key_point/failure_tips 留空可后补
        for step_no, desc in enumerate(dish["steps"], start=1):
            recipe.steps.append(RecipeStep(
                step_no=step_no, description=desc,
                duration_seconds=_extract_duration(desc),
                key_point=None, failure_tips=None, amount_hint=None,
            ))

        # 致敏原回填（菜谱级 = 所引食材 codes 并集，与 ingredient_allergen_codes 同源）
        codes = sorted(aggregated)
        recipe.allergen_codes = codes
        recipe.ingredient_allergen_codes = codes

        session.add(recipe)
        existing_titles.add(title)
        stats["imported"] += 1

    # 跳过清单抽样（报告 ≤10 条示例）
    stats["skipped_samples"] = stats["skipped"][:10]
    return stats


def fix_dirty_ingredient_rows(session: Session) -> dict:
    """清理库内历史脏配料词条（DEF-04 一次性修复，函数，幂等）。

    说明：
        历史语料导入在 ingredient 表留下了 name 为空/纯数字/纯符号的脏词条
        （如「干煸仔鸡」缺料标签「缺 1」即源于 name='1' 的 ingredient 且
        amount_type='main' 排在主料首位）。本函数：
        1) 全量扫描 ingredient，按 _is_dirty_ingredient_name 判定脏行；
        2) 删除脏词条的 recipe_ingredient 引用行（避免外键悬挂）；
        3) 删除脏词条本身；
        幂等：重复执行时脏行已清空，返回 removed_ingredients=0。
        不修复派生字段：脏词条 allergen_codes 为空，删除后菜谱级
        allergen_codes/ingredient_allergen_codes 并集不变，无需回填。

    运行方式（手动执行，事务由调用方提交）：
        cd backend && .venv\\Scripts\\python.exe -c ^
          "from app.core.db import SessionLocal; \\
           from app.seed.corpus_howtocook import fix_dirty_ingredient_rows; \\
           s = SessionLocal(); print(fix_dirty_ingredient_rows(s)); s.commit(); s.close()"

    参数：
        session：SQLAlchemy 会话（由调用方管理事务与提交）。

    返回值：
        dict：{"removed_ingredients": int, "removed_refs": int,
               "removed_names": list[str]}——清理的词条数 / 引用行数 /
               脏名清单（≤50 条抽样）。

    异常：
        数据库操作异常向上抛出（由调用方回滚）。
    """
    stats: dict = {"removed_ingredients": 0, "removed_refs": 0, "removed_names": []}
    ingredients = session.query(Ingredient).all()
    for ing in ingredients:
        if not _is_dirty_ingredient_name(ing.name):
            continue
        refs = session.query(RecipeIngredient).filter(
            RecipeIngredient.ingredient_id == ing.id
        ).all()
        stats["removed_refs"] += len(refs)
        for ref in refs:
            session.delete(ref)
        session.delete(ing)
        stats["removed_ingredients"] += 1
        if len(stats["removed_names"]) < 50:
            stats["removed_names"].append(str(ing.name))
    return stats
