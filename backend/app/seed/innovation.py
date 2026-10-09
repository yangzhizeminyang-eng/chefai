"""模块 O（AI 菜品创新）种子数据模块。

职责：
    为阶段二模块 O 四表提供幂等种子数据：
    - TECHNIQUES：技法白名单 ≥20 条（炒/蒸/煮/炖/烤…，in_whitelist 标注）；
    - PAIRING_RULES：食材搭配规则 ≥60 条（recommend ≥35 / conflict ≥15 / taboo ≥8），
      rationale 一律采用烹饪学表述（口感互补/风味亲和/风味冲突），
      🔴 不使用中医性味归经/相克中毒类断言语气，禁止「会产生毒素」类表述；
    - ingredient_property：食材五属性启发式标注 ≥150 条（覆盖 10 分类），
      由「精确标注表 PRECISE_PROPERTIES → 子串规则 SUBSTRING_RULES →
      分类默认 CATEGORY_DEFAULTS」三级规则函数 derive_property 推导，
      source_note 固定「启发式标注，需专家复核」。

幂等策略：
    - ingredient_property 按 ingredient_id 已存在则跳过；
    - flavor_pairing_rule 按 (ingredient_a_id, ingredient_b_id, relation) 已存在则跳过；
    - technique_library 按 name 已存在则跳过。
"""

import re

# ---------------------------------------------------------------------
# 技法白名单（≥20 条）：(name, description, in_whitelist)
# ---------------------------------------------------------------------
TECHNIQUES: list[tuple[str, str, bool]] = [
    ("炒", "旺火快翻使食材均匀受热的家常主技法", True),
    ("蒸", "以蒸汽传导加热，保持食材原形原味", True),
    ("煮", "水体沸腾加热，适合汤羹与主食", True),
    ("炖", "小火长时间加热，汤汁醇厚肉质酥软", True),
    ("烤", "干热烘烤使表皮焦香内里多汁", True),
    ("凉拌", "生熟食材调味拌匀，清爽开胃", True),
    ("煎", "少油单面加热形成焦香外壳", True),
    ("炸", "热油浸炸，外壳酥脆内部多汁", True),
    ("烩", "多种食材与浓汁同烩，味道融合", True),
    ("焖", "加盖小火微沸，汤汁收浓入味", True),
    ("汆", "沸水快速焯烫至熟，保持鲜嫩", True),
    ("涮", "沸汤边煮边食，薄料即涮即吃", True),
    ("白灼", "沸汤或沸水快速烫熟，突出本味", True),
    ("卤", "香料卤水浸煮入味，凉热皆宜", True),
    ("腌", "盐或调味汁浸渍入味，改变质地", True),
    ("拌", "调味料与食材拌匀，冷热皆可", True),
    ("熘", "芡汁包裹炸制或滑油食材，明油亮芡", True),
    ("爆", "极旺火极短时间爆炒，脆嫩爽口", True),
    ("烧", "煎炒后加汤汁烧至入味收浓", True),
    ("清蒸", "仅以基础调味蒸制，突出食材本味", True),
    ("红烧", "老抽糖色红烧，色泽红亮味浓", True),
    ("糖醋", "糖醋汁调配，酸甜适口", True),
    ("炝", "热油激香花椒辣椒后拌入食材", True),
    ("焯", "沸水短时预熟处理，去杂保色", True),
]

# ---------------------------------------------------------------------
# 食材搭配规则（≥60 条）：(食材A, 食材B, relation, 建议技法, rationale, weight)
# relation ∈ recommend（推荐搭配）/ conflict（风味冲突，不建议同烹）/
#            taboo（强烈不建议，任何烹法均不推荐）
# 🔴 rationale 一律烹饪学表述；不含中医相克、中毒类断言。
# ---------------------------------------------------------------------
_PAIR = tuple[str, str, str, str | None, str, float]
PAIRING_RULES: list[_PAIR] = [
    # ---- recommend（40 条）：口感互补 / 风味亲和 ----
    ("番茄", "鸡蛋", "recommend", "炒", "酸甜汁衬嫩滑蛋香，口感互补，经典家常风味", 1.00),
    ("青椒", "土豆", "recommend", "炒", "脆椒与绵薯口感互补，咸香下饭", 0.90),
    ("番茄", "牛腩", "recommend", "炖", "果酸软化牛肉纤维，汤汁浓郁开胃", 1.00),
    ("土豆", "牛腩", "recommend", "炖", "薯香吸饱肉汁，口感醇厚融合", 1.00),
    ("香菇", "土鸡", "recommend", "炖", "菌香提升禽肉鲜味，风味亲和", 0.95),
    ("虾仁", "黄瓜", "recommend", "炒", "清爽瓜香衬出虾仁弹嫩，口感清鲜", 0.90),
    ("干木耳", "山药", "recommend", "炒", "脆爽与脆嫩叠加，口感层次分明", 0.85),
    ("韭菜", "鸡蛋", "recommend", "炒", "辛香与蛋香融合，经典风味亲和", 0.95),
    ("洋葱", "猪里脊", "recommend", "炒", "甜香去腻提味，风味亲和", 0.90),
    ("猪排骨", "莲藕", "recommend", "炖", "藕粉吸汤，汤色浓香菜香融合", 0.95),
    ("冬瓜", "猪排骨", "recommend", "煮", "清甜解腻，汤感平衡不浊", 0.90),
    ("豆腐", "鲈鱼", "recommend", "烩", "鱼鲜渗入豆制品，鲜味叠加", 0.95),
    ("鸡腿", "香菇", "recommend", "焖", "菌香入肉，焖汁浓郁", 0.90),
    ("羊肉片", "白萝卜", "recommend", "炖", "萝卜清甜化解膻感，风味更清亮", 0.95),
    ("鲫鱼", "豆腐", "recommend", "煮", "鱼鲜与豆香融合，汤色乳白鲜醇", 1.00),
    ("南瓜", "小米", "recommend", "煮", "清甜与米香融合，口感绵润", 0.85),
    ("绿豆", "干百合", "recommend", "煮", "豆沙清润与百合粉糯互补", 0.85),
    ("干百合", "红枣", "recommend", "炖", "粉糯与枣甜互补，甜汤经典组合", 0.85),
    ("香蕉", "牛奶", "recommend", "拌", "果香与奶香融合，甜润顺滑", 0.90),
    ("芒果", "糯米", "recommend", "蒸", "果香衬糯米软糯，甜点经典组合", 0.85),
    ("菠萝", "猪里脊", "recommend", "熘", "果酸解腻衬肉香，酸甜开胃", 0.95),
    ("鸡蛋", "虾仁", "recommend", "炒", "嫩滑与弹嫩双重口感，鲜味互补", 0.95),
    ("丝瓜", "鸡蛋", "recommend", "煮", "清淡瓜鲜与蛋香互补，汤感清润", 0.85),
    ("芹菜", "豆腐干", "recommend", "炒", "爽脆与干韧豆香互补", 0.85),
    ("西兰花", "虾仁", "recommend", "炒", "脆嫩与弹嫩相衬，清爽不腻", 0.90),
    ("番茄", "卷心菜", "recommend", "炒", "酸甜汁衬菜叶清甜，开胃下饭", 0.80),
    ("黄瓜", "干木耳", "recommend", "凉拌", "脆爽与爽脆叠加，凉菜开胃", 0.85),
    ("豆腐", "花蛤", "recommend", "煮", "海鲜鲜味与豆香融合，汤鲜味厚", 0.90),
    ("白萝卜", "牛腩", "recommend", "炖", "萝卜吸牛腩脂香，清甜入味", 0.90),
    ("竹笋", "腊肉", "recommend", "炒", "笋鲜吸附烟熏咸香，风味浓郁", 0.95),
    ("蒜苗", "腊肉", "recommend", "炒", "蒜香与腊香互相成就，下饭经典", 0.95),
    ("莴笋", "猪里脊", "recommend", "炒", "脆嫩与肉嫩互补，清香解腻", 0.80),
    ("金针菇", "羊肉片", "recommend", "涮", "菌鲜吸附羊肉脂香，涮菜经典", 0.90),
    ("平菇", "鸡蛋", "recommend", "炒", "菌鲜蛋香，软嫩口感互补", 0.85),
    ("杏鲍菇", "猪里脊", "recommend", "炒", "菌肉双鲜，口感互衬", 0.85),
    ("蒜苔", "猪里脊", "recommend", "炒", "脆嫩蒜香衬肉鲜，风味浓郁", 0.85),
    ("生菜", "大蒜", "recommend", "炒", "蒜香提味衬生菜脆嫩", 0.80),
    ("大米", "小米", "recommend", "蒸", "双米同煮，米香层次更丰富", 0.75),
    ("干贝", "冬瓜", "recommend", "煮", "干贝鲜味吊出冬瓜清甜，汤感清雅", 0.90),
    ("土豆", "胡萝卜", "recommend", "炖", "绵糯与清甜根茎互补，炖色浓香", 0.85),
    # ---- conflict（15 条）：风味冲突，不建议同烹（烹饪学表述）----
    ("菠菜", "豆腐", "conflict", None,
     "草酸易与钙结合析出影响口感，风味冲突，不建议同烹（菠菜焯水后可缓解）", 0.60),
    ("酸奶", "菠萝", "conflict", None,
     "果酸使酸奶蛋白凝絮结块，口感发渣，风味冲突，不建议同烹", 0.60),
    ("巧克力", "大蒜", "conflict", None,
     "甜苦风味与辛辣蒜香互冲，风味冲突，不建议同烹", 0.60),
    ("咸鱼", "牛奶", "conflict", None,
     "浓腥咸香与奶甜互冲，风味冲突，不建议同烹", 0.60),
    ("臭豆腐", "牛奶", "conflict", None,
     "发酵浓香与奶甜互冲，风味冲突，不建议同烹", 0.60),
    ("皮蛋", "酸奶", "conflict", None,
     "碱香蛋味与酸奶奶香相冲，风味冲突，不建议同烹", 0.60),
    ("芥末酱", "牛奶", "conflict", None,
     "辛辣刺激与奶味互冲，风味冲突，不建议同烹", 0.60),
    ("榴莲", "牛奶", "conflict", None,
     "浓烈果香与奶甜叠腻，风味冲突，不建议同烹", 0.60),
    ("榴莲", "咖啡", "conflict", None,
     "浓烈果香与苦香互冲，风味冲突，不建议同烹", 0.60),
    ("薄荷", "大蒜", "conflict", None,
     "清凉与辛辣互相干扰，风味冲突，不建议同烹", 0.60),
    ("苦瓜", "蜂蜜", "conflict", None,
     "重苦与甜腻互相干扰，风味冲突，不建议同烹", 0.60),
    ("西瓜", "腐乳", "conflict", None,
     "清甜瓜味与咸鲜酱味互冲，风味冲突，不建议同烹", 0.60),
    ("辣椒油", "酸奶", "conflict", None,
     "辛辣油润与冰凉奶甜反差不适，风味冲突，不建议同烹", 0.60),
    ("榨菜", "香蕉", "conflict", None,
     "咸鲜与甜糯反差突兀，风味冲突，不建议同烹", 0.60),
    ("蜂蜜", "大蒜", "conflict", None,
     "甜润与辛辣互冲，风味冲突，不建议同烹", 0.60),
    # ---- taboo（8 条）：强烈不建议，任何烹法均不推荐（烹饪学表述）----
    ("榴莲", "韭菜", "taboo", None,
     "两股浓烈气味叠加冲撞，任何烹法均不建议同烹", 1.00),
    ("榴莲", "臭豆腐", "taboo", None,
     "发酵浓香与浓甜果香剧烈互冲，任何烹法均不建议同烹", 1.00),
    ("榴莲", "大蒜", "taboo", None,
     "浓甜果香与辛辣蒜味剧烈互冲，任何烹法均不建议同烹", 1.00),
    ("臭豆腐", "咖啡", "taboo", None,
     "发酵浓香与苦香剧烈互冲，任何烹法均不建议同烹", 1.00),
    ("臭豆腐", "香蕉", "taboo", None,
     "咸鲜发酵味与甜糯果香剧烈反差，任何烹法均不建议同烹", 1.00),
    ("皮蛋", "西瓜", "taboo", None,
     "碱香蛋味与清甜瓜味剧烈互冲，任何烹法均不建议同烹", 1.00),
    ("咸鱼", "酸奶", "taboo", None,
     "浓腥咸香与奶甜剧烈互冲，任何烹法均不建议同烹", 1.00),
    ("韭菜", "酸奶", "taboo", None,
     "辛香与奶甜剧烈互冲，任何烹法均不建议同烹", 1.00),
]

# ---------------------------------------------------------------------
# 食材五属性启发式规则（覆盖 10 分类）
# 五属性：texture 质地 / moisture 含水量档 / flavor 风味标签（逗号分隔）/
#         heat_tolerance 耐热档 / oil_absorption 吸油档
# 档位取值：moisture/heat_tolerance/oil_absorption ∈ high/mid/low
# ---------------------------------------------------------------------
PreciseProperty = dict[str, str | None]

# 一级规则：常见食材精确标注（优先级最高）
PRECISE_PROPERTIES: dict[str, PreciseProperty] = {
    "番茄":   {"texture": "软嫩", "moisture": "high", "flavor": "酸甜,多汁", "heat_tolerance": "low", "oil_absorption": "low"},
    "茄子":   {"texture": "绵软", "moisture": "mid", "flavor": "清淡", "heat_tolerance": "mid", "oil_absorption": "high"},
    "土豆":   {"texture": "绵糯", "moisture": "mid", "flavor": "清淡", "heat_tolerance": "high", "oil_absorption": "mid"},
    "莲藕":   {"texture": "脆", "moisture": "mid", "flavor": "清甜", "heat_tolerance": "high", "oil_absorption": "low"},
    "山药":   {"texture": "黏滑", "moisture": "mid", "flavor": "清淡", "heat_tolerance": "mid", "oil_absorption": "low"},
    "香菇":   {"texture": "韧", "moisture": "mid", "flavor": "鲜香", "heat_tolerance": "high", "oil_absorption": "mid"},
    "金针菇": {"texture": "韧", "moisture": "high", "flavor": "鲜", "heat_tolerance": "mid", "oil_absorption": "low"},
    "豆腐":   {"texture": "嫩滑", "moisture": "high", "flavor": "豆香", "heat_tolerance": "mid", "oil_absorption": "low"},
    "猪里脊": {"texture": "嫩", "moisture": "mid", "flavor": "鲜", "heat_tolerance": "high", "oil_absorption": "low"},
    "牛腩":   {"texture": "韧", "moisture": "mid", "flavor": "醇香", "heat_tolerance": "high", "oil_absorption": "mid"},
    "基围虾": {"texture": "弹嫩", "moisture": "high", "flavor": "鲜甜", "heat_tolerance": "low", "oil_absorption": "low"},
    "鸡蛋":   {"texture": "嫩滑", "moisture": "mid", "flavor": "蛋香", "heat_tolerance": "mid", "oil_absorption": "low"},
    "苦瓜":   {"texture": "脆", "moisture": "high", "flavor": "苦,清爽", "heat_tolerance": "mid", "oil_absorption": "low"},
    "黄瓜":   {"texture": "脆嫩", "moisture": "high", "flavor": "清爽", "heat_tolerance": "low", "oil_absorption": "low"},
    "冬瓜":   {"texture": "软嫩", "moisture": "high", "flavor": "清淡", "heat_tolerance": "mid", "oil_absorption": "low"},
    "南瓜":   {"texture": "粉糯", "moisture": "mid", "flavor": "清甜", "heat_tolerance": "high", "oil_absorption": "low"},
    "糯米":   {"texture": "黏糯", "moisture": "mid", "flavor": "谷香", "heat_tolerance": "high", "oil_absorption": "low"},
    "猪排骨": {"texture": "韧", "moisture": "mid", "flavor": "肉香", "heat_tolerance": "high", "oil_absorption": "mid"},
    "榴莲":   {"texture": "软糯", "moisture": "mid", "flavor": "浓甜,浓香", "heat_tolerance": "low", "oil_absorption": "low"},
    "臭豆腐": {"texture": "外脆内嫩", "moisture": "mid", "flavor": "发酵咸鲜", "heat_tolerance": "high", "oil_absorption": "high"},
}

# 二级规则：子串模式（按顺序首个命中生效）
# (名称子串正则, 属性覆盖 dict)
SUBSTRING_RULES: list[tuple[str, PreciseProperty]] = [
    (r"菇|菌|木耳", {"texture": "韧", "moisture": "mid", "flavor": "鲜香", "heat_tolerance": "mid", "oil_absorption": "mid"}),
    (r"白菜|菠菜|油菜|生菜|苋菜|茼蒿|空心菜|油麦菜|鸡毛菜|娃娃菜|卷心菜|芥蓝|芥菜|韭菜|芹菜|香菜|雪里蕻",
     {"texture": "嫩", "moisture": "high", "flavor": "清香", "heat_tolerance": "low", "oil_absorption": "low"}),
    (r"鱼", {"texture": "嫩", "moisture": "high", "flavor": "鲜", "heat_tolerance": "low", "oil_absorption": "low"}),
    (r"虾|蟹|贝|蛤|蛏|鱿|干贝|海参", {"texture": "弹嫩", "moisture": "high", "flavor": "鲜甜", "heat_tolerance": "low", "oil_absorption": "low"}),
    (r"牛|腱", {"texture": "韧", "moisture": "mid", "flavor": "醇香", "heat_tolerance": "high", "oil_absorption": "mid"}),
    (r"羊", {"texture": "嫩", "moisture": "mid", "flavor": "膻香", "heat_tolerance": "high", "oil_absorption": "mid"}),
    (r"猪|排|腊|肉|鸡|鸭|鹅|鸽|蹄|肚|肝|肠|爪|翅",
     {"texture": "嫩", "moisture": "mid", "flavor": "肉香", "heat_tolerance": "high", "oil_absorption": "mid"}),
    (r"蛋", {"texture": "嫩滑", "moisture": "mid", "flavor": "蛋香", "heat_tolerance": "mid", "oil_absorption": "low"}),
    (r"奶|乳|酪|黄油", {"texture": "滑", "moisture": "high", "flavor": "奶香", "heat_tolerance": "low", "oil_absorption": "low"}),
    (r"豆(腐|干|丝|皮|乳|竹|瓣)|豆豉|豆瓣酱|黄豆芽|绿豆芽|毛豆|腐",
     {"texture": "软嫩", "moisture": "mid", "flavor": "豆香", "heat_tolerance": "mid", "oil_absorption": "mid"}),
    (r"萝卜", {"texture": "脆", "moisture": "high", "flavor": "辛甜", "heat_tolerance": "mid", "oil_absorption": "low"}),
    (r"笋", {"texture": "脆嫩", "moisture": "mid", "flavor": "清鲜", "heat_tolerance": "mid", "oil_absorption": "low"}),
    (r"瓜", {"texture": "脆", "moisture": "high", "flavor": "清甜", "heat_tolerance": "low", "oil_absorption": "low"}),
    (r"椒|蒜|葱|姜|韭|茴|薄荷|紫苏|孜然|十三香|五香粉|芥末|胡椒|花椒|辣椒",
     {"texture": "脆", "moisture": "mid", "flavor": "辛香", "heat_tolerance": "high", "oil_absorption": "low"}),
    (r"米|面|粉|麦|饭|粥|苞谷|玉米", {"texture": "绵软", "moisture": "mid", "flavor": "谷香", "heat_tolerance": "high", "oil_absorption": "low"}),
    (r"枣|桃|梨|蕉|芒|荔|龙眼|葡萄|莓|橙|橘|柚|柠|瓜",
     {"texture": "软", "moisture": "high", "flavor": "果香,甜", "heat_tolerance": "low", "oil_absorption": "low"}),
    (r"干|皮|豉|酱|露|卤|渍|榨|梅|盐|糖|醋|酒|油|茶|咖",
     {"texture": "韧硬", "moisture": "low", "flavor": "咸鲜", "heat_tolerance": "high", "oil_absorption": "mid"}),
]

# 三级规则：分类默认（10 分类全覆盖兜底）
CATEGORY_DEFAULTS: dict[str, PreciseProperty] = {
    "veg":       {"texture": "嫩", "moisture": "high", "flavor": "清甜", "heat_tolerance": "low", "oil_absorption": "low"},
    "meat":      {"texture": "嫩", "moisture": "mid", "flavor": "肉香", "heat_tolerance": "high", "oil_absorption": "mid"},
    "seafood":   {"texture": "弹嫩", "moisture": "high", "flavor": "鲜", "heat_tolerance": "low", "oil_absorption": "low"},
    "egg_milk":  {"texture": "嫩滑", "moisture": "high", "flavor": "醇香", "heat_tolerance": "low", "oil_absorption": "low"},
    "soy":       {"texture": "软嫩", "moisture": "mid", "flavor": "豆香", "heat_tolerance": "mid", "oil_absorption": "mid"},
    "staple":    {"texture": "绵软", "moisture": "mid", "flavor": "谷香", "heat_tolerance": "high", "oil_absorption": "low"},
    "seasoning": {"texture": None, "moisture": "low", "flavor": "辛香", "heat_tolerance": "high", "oil_absorption": "low"},
    "dry":       {"texture": "韧", "moisture": "low", "flavor": "鲜香", "heat_tolerance": "high", "oil_absorption": "mid"},
    "frozen":    {"texture": "嫩", "moisture": "high", "flavor": "清淡", "heat_tolerance": "low", "oil_absorption": "low"},
    "other":     {"texture": "软糯", "moisture": "mid", "flavor": "果香", "heat_tolerance": "low", "oil_absorption": "low"},
}

# 每分类标注条数上限：10 分类 × 16 = 160（≥150）
PER_CATEGORY_LIMIT = 16
SOURCE_NOTE = "启发式标注，需专家复核"


def derive_property(name: str, category: str) -> PreciseProperty:
    """按三级规则推导食材五属性（函数）。

    优先级：PRECISE_PROPERTIES 精确标注 > SUBSTRING_RULES 子串规则（首个命中）
    > CATEGORY_DEFAULTS 分类默认（10 分类全覆盖兜底）。

    参数：
        name：食材名称。
        category：食材分类（10 分类之一）。

    返回值：
        PreciseProperty：五属性 dict，键含 texture/moisture/flavor/
        heat_tolerance/oil_absorption，个别值可为 None（未标注）。

    异常：
        无（category 未收录时返回全 None 的空属性）。
    """
    base = dict(CATEGORY_DEFAULTS.get(category, {}))
    for pattern, overrides in SUBSTRING_RULES:
        if re.search(pattern, name):
            base = {**base, **overrides}
            break
    precise = PRECISE_PROPERTIES.get(name)
    if precise:
        base = {**base, **precise}
    # 补齐缺失键为 None，保证调用方可用 .get 稳定取值
    return {key: base.get(key) for key in
            ("texture", "moisture", "flavor", "heat_tolerance", "oil_absorption")}
