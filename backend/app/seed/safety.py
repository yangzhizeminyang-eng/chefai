"""风控规则与话术种子数据模块。

职责：
    定义阶段一风控规则（risk_rule）与配套话术模板（risk_message）：
    - FS-001~FS-011：11 类食品安全高危（input 闸门，block=true，critical/high）；
    - SP-001~SP-002：特殊人群（蜂蜜+婴儿 / 孕妇+生食）；
    - MR-001~MR-004：医疗拒答（body 用 PRD TXT-G04 固定口径）；
    - PS-001~PS-002：伪科学澄清（body 用 PRD TXT-G05 口径）；
    - OB-001~OB-005：输出侧禁令（stage_scope=output：法定营养声称/医疗宣称/安全承诺/绝对化/减肥承诺）；
    - INNO-001~INNO-003：L.12 创新风控规则（输入侧医疗红线 regex + 输出侧安全承诺/
      伪科学表述拦截，配套模块 O AI 菜品创新输出）。

trigger_condition JSONB 结构（由 Task 3 风控引擎消费）：
    任意命中：{"keywords": [...], "any": true}
    组合命中（组内任一、组间全中）：{"keywords": [...], "any": true, "mode": "all_groups", "groups": [[...], ...]}
    正则命中（大小写不敏感，re.search）：{"regex": [r"..."]}（与 keywords 为「或」关系）

专家签字说明：
    阶段一 signed_by_expert 恒为 false（架构文档 §10.4.19）；话术不由模型生成（RL-1）。
"""

DISCLAIMER_ID = "DISC-V1.0"  # 风控话术统一附着的免责声明 ID（阶段一固定版本）
RULE_VERSION = "rules-v1.0"

# PRD TXT-G04 医疗拒答固定口径（【假设，待甲方+法务+专家定稿】假设值）
TXT_G04 = (
    "这个问题涉及医疗与治疗范畴，我不能提供建议。请咨询执业医师或临床营养师。"
    "我可以帮你的是：告诉你这道菜每份大约含多少热量和营养，或帮你做一道菜的步骤引导。"
)
# PRD TXT-G05 伪科学澄清固定口径（⚠️ 待专家确认）
TXT_G05 = "此类说法缺乏科学依据。真正需要注意的是：食材是否新鲜、是否彻底加热、是否有个人过敏情况。"

# 话术模板：message_id / category / title / body / correct_action / after_consumption_advice
RISK_MESSAGES: list[dict] = [
    {
        "message_id": "MSG-FS-001",
        "category": "food_safety_high_risk",
        "title": "木耳/银耳久泡风险",
        "body": "木耳、银耳泡发时间过长（如过夜）可能滋生椰毒假单胞菌，产生米酵菌酸毒素，中毒后果严重且无特效解药。",
        "correct_action": "冷水泡发不超过 2 小时；如需久放请沥干密封冷藏，并在 24 小时内食用完毕。",
        "after_consumption_advice": "若已食用久泡木耳/银耳并出现呕吐、腹泻、头晕、乏力等症状，请立即就医并告知医生食用史。",
    },
    {
        "message_id": "MSG-FS-002",
        "category": "food_safety_high_risk",
        "title": "豆角未熟透风险",
        "body": "豆角、四季豆、扁豆含有皂苷和植物血凝素，未熟透食用可能引起恶心、呕吐、腹痛等中毒反应。",
        "correct_action": "彻底加热至颜色深绿、口感软而无生豆腥（建议焯水或干煸后充分烧煮 5 分钟以上），不做脆口口感。",
        "after_consumption_advice": "若食用后 1~5 小时出现呕吐腹泻等症状，请及时就医并补足水分。",
    },
    {
        "message_id": "MSG-FS-003",
        "category": "food_safety_high_risk",
        "title": "发芽/变青土豆风险",
        "body": "发芽或变绿的土豆含大量龙葵素，加热无法破坏，食用可能引起咽喉灼烧、腹泻、头晕等中毒反应。",
        "correct_action": "发芽明显、变青面积大的土豆建议整颗丢弃，不要只削芽眼；轻微发芽可深挖芽眼及周围组织并充分加热后少量食用。",
        "after_consumption_advice": "若食用后出现口舌发麻、恶心呕吐等症状，请立即就医。",
    },
    {
        "message_id": "MSG-FS-004",
        "category": "food_safety_high_risk",
        "title": "鲜黄花菜风险",
        "body": "鲜黄花菜含秋水仙碱，食用后在体内氧化为二秋水仙碱，可能引起恶心、呕吐、腹痛等中毒反应。",
        "correct_action": "选择干黄花菜（已脱毒）；如用鲜品，须去芯后焯水，再用清水浸泡 2 小时以上并充分加热。",
        "after_consumption_advice": "若食用后出现恶心呕吐腹泻，请多饮水并尽快就医。",
    },
    {
        "message_id": "MSG-FS-005",
        "category": "food_safety_high_risk",
        "title": "野生菌/河豚/野味高风险",
        "body": "野生菌、河豚、野味中毒风险极高，部分毒素无特效解药，家庭烹饪无法保证安全。",
        "correct_action": "不采、不买、不吃野生菌和河豚；购买菌菇请选择正规渠道的常见栽培品种。",
        "after_consumption_advice": "若食用后出现幻觉、呕吐、腹泻等症状，请立即就医，并尽量保留剩余食物样本供鉴定。",
    },
    {
        "message_id": "MSG-FS-006",
        "category": "food_safety_high_risk",
        "title": "淡水水产生食风险",
        "body": "淡水鱼虾蟹常携带肝吸虫等寄生虫，生食或半生食（生鱼片、醉虾、生腌）感染风险高。",
        "correct_action": "淡水水产务必彻底加热至熟（中心温度 70℃ 以上并保持数分钟）；生食请选择可生食等级的海产品并注意冷链。",
        "after_consumption_advice": "若生食后出现腹痛、腹泻、发热等症状，请就医并说明生食史，必要时做寄生虫筛查。",
    },
    {
        "message_id": "MSG-FS-007",
        "category": "food_safety_high_risk",
        "title": "溏心蛋/生鸡蛋与高危人群",
        "body": "溏心蛋、生鸡蛋可能携带沙门氏菌，婴幼儿、孕妇、老人及免疫力低下者感染风险和后果更严重。",
        "correct_action": "上述人群食用鸡蛋务必全熟（蛋黄凝固）；普通成人也应选择可生食等级鸡蛋并注意保质期。",
        "after_consumption_advice": "若食用后出现发热、呕吐、腹泻，请及时就医（孕妇请优先产科急诊）。",
    },
    {
        "message_id": "MSG-FS-008",
        "category": "food_safety_high_risk",
        "title": "家庭自制高风险发酵/罐头制品",
        "body": "家庭自制罐头、腊肉、发酵肉制品易受肉毒杆菌等污染，缺乏工业灭菌与检测条件，风险极高。",
        "correct_action": "建议购买正规厂家产品；如坚持自制，请严格按可靠灭菌流程操作，出现涨袋、异味立即丢弃。",
        "after_consumption_advice": "若食用后出现视物模糊、吞咽困难、乏力等肉毒中毒征兆，请立即急诊并说明食用史。",
    },
    {
        "message_id": "MSG-FS-009",
        "category": "food_safety_high_risk",
        "title": "反复解冻风险",
        "body": "食材反复解冻会破坏细胞结构、滋生细菌，加速变质，增加食品安全风险。",
        "correct_action": "按次分装冷冻，吃多少解冻多少；解冻后尽快烹饪，不复冻已解冻的生肉。",
        "after_consumption_advice": "若误食已反复解冻且出现异味变质的食材后不适，请及时就医。",
    },
    {
        "message_id": "MSG-FS-010",
        "category": "food_safety_high_risk",
        "title": "腌菜未腌透风险",
        "body": "腌制 2~15 天内的腌菜亚硝酸盐含量处于峰值，未腌透食用可能引起亚硝酸盐中毒。",
        "correct_action": "自制腌菜务必腌足 20~30 天后再食用；或选择正规厂家产品并注意开封后冷藏尽快食用。",
        "after_consumption_advice": "若食用后出现口唇发紫、头晕、恶心等症状（亚硝酸盐中毒表现），请立即就医。",
    },
    {
        "message_id": "MSG-FS-011",
        "category": "food_safety_high_risk",
        "title": "隔夜剩菜/熟食风险",
        "body": "剩菜、熟食常温放置过夜易滋生细菌并产生亚硝酸盐，尤其叶菜、海鲜、半熟蛋类风险更高。",
        "correct_action": "剩菜趁热密封冷藏（2 小时内），冷藏不超过 24 小时；再次食用须彻底加热，叶菜类建议当餐吃完不留存。",
        "after_consumption_advice": "若食用隔夜食物后出现呕吐、腹泻、发热，请及时就医并补足水分。",
    },
    {
        "message_id": "MSG-SP-001",
        "category": "special_population",
        "title": "蜂蜜与 1 岁以下婴儿",
        "body": "蜂蜜可能含有肉毒杆菌芽孢，1 岁以下婴儿肠道菌群尚未健全，食用可能引发婴儿肉毒中毒。",
        "correct_action": "1 岁以下婴儿禁止食用蜂蜜及含蜂蜜食品；1 岁以上儿童可正常适量食用。",
        "after_consumption_advice": "若婴儿误食蜂蜜后出现便秘、吮吸无力、哭声微弱等症状，请立即就医。",
    },
    {
        "message_id": "MSG-SP-002",
        "category": "special_population",
        "title": "孕妇与生食",
        "body": "孕妇免疫力相对较低，生鱼片、溏心蛋、生腌等生食携带的李斯特菌、沙门氏菌、弓形虫可能导致严重后果。",
        "correct_action": "孕期避免所有生食和半生食；食材彻底加热，生熟分开处理。",
        "after_consumption_advice": "若误食生食后出现发热、腹泻等不适，请尽快就医并告知孕周。",
    },
    {
        "message_id": "MSG-MR-001",
        "category": "medical_refusal",
        "title": "医疗类问题拒答",
        "body": TXT_G04,
        "correct_action": None,
        "after_consumption_advice": None,
    },
    {
        "message_id": "MSG-MR-002",
        "category": "medical_refusal",
        "title": "用药与治疗方案拒答",
        "body": TXT_G04,
        "correct_action": None,
        "after_consumption_advice": None,
    },
    {
        "message_id": "MSG-MR-003",
        "category": "medical_refusal",
        "title": "疾病饮食处方类拒答",
        "body": TXT_G04,
        "correct_action": None,
        "after_consumption_advice": None,
    },
    {
        "message_id": "MSG-MR-004",
        "category": "medical_refusal",
        "title": "药膳与中药配方拒答",
        "body": TXT_G04,
        "correct_action": None,
        "after_consumption_advice": None,
    },
    {
        "message_id": "MSG-PS-001",
        "category": "pseudoscience",
        "title": "食物相克说法澄清",
        "body": TXT_G05,
        "correct_action": None,
        "after_consumption_advice": None,
    },
    {
        "message_id": "MSG-PS-002",
        "category": "pseudoscience",
        "title": "致癌恐慌说法澄清",
        "body": TXT_G05,
        "correct_action": None,
        "after_consumption_advice": None,
    },
    {
        "message_id": "MSG-OB-001",
        "category": "output_ban",
        "title": "法定营养声称禁用",
        "body": "输出内容不得使用「低脂/无糖/高蛋白/富含膳食纤维」等法定营养声称，应替换为「每份约含脂肪 XXg」等具体数值表述。",
        "correct_action": None,
        "after_consumption_advice": None,
    },
    {
        "message_id": "MSG-OB-002",
        "category": "output_ban",
        "title": "医疗宣称禁用",
        "body": "输出内容不得出现「治疗/治好/痊愈」等医疗宣称，应替换为「饮食参考，慢性疾病请遵医嘱」。",
        "correct_action": None,
        "after_consumption_advice": None,
    },
    {
        "message_id": "MSG-OB-003",
        "category": "output_ban",
        "title": "安全承诺禁用",
        "body": "输出内容不得作出「绝对安全/保证不过敏/放心吃」等安全承诺，应替换为「根据当前配方未标注含 XX，请以实际食材包装标签为准」。",
        "correct_action": None,
        "after_consumption_advice": None,
    },
    {
        "message_id": "MSG-OB-004",
        "category": "output_ban",
        "title": "绝对化用语禁用",
        "body": "输出内容不得使用「最好的/第一/最健康/唯一」等绝对化用语，应替换为「适合」「较为」「可以参考」。",
        "correct_action": None,
        "after_consumption_advice": None,
    },
    {
        "message_id": "MSG-OB-005",
        "category": "output_ban",
        "title": "减肥功效宣称禁用",
        "body": "输出内容不得出现「减肥/瘦身/月瘦 N 斤」等功效宣称，应替换为「热量与营养参考」。",
        "correct_action": None,
        "after_consumption_advice": None,
    },
]

# 风控规则：rule_code / category / stage_scope / trigger_condition / message_id / block / risk_level / evidence_ref
RISK_RULES: list[dict] = [
    # ---- 11 类食品安全高危（input，block=true）----
    {
        "rule_code": "FS-001", "category": "food_safety_high_risk", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["木耳", "银耳", "雪耳"], "any": True, "mode": "all_groups",
            "groups": [["木耳", "银耳", "雪耳"], ["泡", "发", "浸"], ["过夜", "一晚上", "一夜", "隔夜", "久", "明天", "三天", "两天", "几天", "好几", "长时间", "太久"]],
        },
        "response_message_id": "MSG-FS-001", "block": True, "risk_level": "critical",
        "evidence_ref": "GB 2760 风险通报；米酵菌酸中毒案例通报（演示口径）",
    },
    {
        "rule_code": "FS-002", "category": "food_safety_high_risk", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["豆角", "四季豆", "扁豆", "芸豆", "刀豆", "豇豆"], "any": True, "mode": "all_groups",
            "groups": [["豆角", "四季豆", "扁豆", "芸豆", "刀豆", "豇豆"], ["脆", "没熟", "生的", "夹生", "生炒", "脆口", "断生即可"]],
        },
        "response_message_id": "MSG-FS-002", "block": True, "risk_level": "critical",
        "evidence_ref": "皂苷/植物血凝素中毒机制（演示口径）",
    },
    {
        "rule_code": "FS-003", "category": "food_safety_high_risk", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["土豆", "马铃薯", "洋芋"], "any": True, "mode": "all_groups",
            "groups": [["土豆", "马铃薯", "洋芋"], ["发芽", "变青", "发青", "变绿", "绿了", "青皮"]],
        },
        "response_message_id": "MSG-FS-003", "block": True, "risk_level": "high",
        "evidence_ref": "龙葵素（茄碱）中毒机制（演示口径）",
    },
    {
        "rule_code": "FS-004", "category": "food_safety_high_risk", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["黄花菜", "金针菜"], "any": True, "mode": "all_groups",
            "groups": [["黄花菜", "金针菜"], ["鲜", "新鲜", "刚摘", "现摘"]],
        },
        "response_message_id": "MSG-FS-004", "block": True, "risk_level": "high",
        "evidence_ref": "秋水仙碱中毒机制（演示口径）",
    },
    {
        "rule_code": "FS-005", "category": "food_safety_high_risk", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["野生菌", "野蘑菇", "野菇", "野生蘑菇", "河豚", "野味", "织纹螺"], "any": True,
        },
        "response_message_id": "MSG-FS-005", "block": True, "risk_level": "critical",
        "evidence_ref": "毒蕈碱/河豚毒素中毒风险（演示口径）",
    },
    {
        "rule_code": "FS-006", "category": "food_safety_high_risk", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["生鱼片", "刺身", "醉虾", "醉蟹", "生腌", "生蚝(生)"], "any": True, "mode": "all_groups",
            "groups": [["生鱼片", "刺身", "醉虾", "醉蟹", "生腌", "生食"], ["淡水", "草鱼", "鲫鱼", "河鱼", "鲩鱼", "自制", "家里做"]],
        },
        "response_message_id": "MSG-FS-006", "block": True, "risk_level": "critical",
        "evidence_ref": "肝吸虫（华支睾吸虫）感染风险（演示口径）",
    },
    {
        "rule_code": "FS-007", "category": "food_safety_high_risk", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["溏心蛋", "溏心", "生鸡蛋", "生蛋液", "太阳蛋", "温泉蛋"], "any": True, "mode": "all_groups",
            "groups": [["溏心蛋", "溏心", "生鸡蛋", "生蛋液", "太阳蛋", "温泉蛋"], ["婴儿", "宝宝", "幼儿", "新生儿", "孕妇", "怀孕", "老人", "哺乳", "1岁", "一岁", "免疫"]],
        },
        "response_message_id": "MSG-FS-007", "block": True, "risk_level": "high",
        "evidence_ref": "沙门氏菌感染风险（演示口径）",
    },
    {
        "rule_code": "FS-008", "category": "food_safety_high_risk", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["自制", "自己做", "家里做", "家庭自制"], "any": True, "mode": "all_groups",
            "groups": [["自制", "自己做", "家里做", "家庭自制"], ["罐头", "腊肉", "香肠", "发酵肉", "腌肉", "发酵豆制品", "肉毒"]],
        },
        "response_message_id": "MSG-FS-008", "block": True, "risk_level": "critical",
        "evidence_ref": "肉毒杆菌中毒风险（演示口径）",
    },
    {
        "rule_code": "FS-009", "category": "food_safety_high_risk", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["解冻"], "any": True, "mode": "all_groups",
            "groups": [["解冻", "化冻"], ["反复", "多次", "再次", "两次", "好几"]],
        },
        "response_message_id": "MSG-FS-009", "block": True, "risk_level": "high",
        "evidence_ref": "细菌繁殖与变质风险（演示口径）",
    },
    {
        "rule_code": "FS-010", "category": "food_safety_high_risk", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["腌菜", "酸菜", "咸菜", "泡菜", "腌萝卜"], "any": True, "mode": "all_groups",
            "groups": [["腌菜", "酸菜", "咸菜", "泡菜", "腌萝卜"], ["没腌透", "刚腌", "刚做", "刚泡", "几天", "一周内", "没到时候", "三天"]],
        },
        "response_message_id": "MSG-FS-010", "block": True, "risk_level": "high",
        "evidence_ref": "亚硝酸盐峰值期风险（演示口径）",
    },
    {
        "rule_code": "FS-011", "category": "food_safety_high_risk", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["剩菜", "剩饭", "熟食", "卤味", "凉菜隔夜"], "any": True, "mode": "all_groups",
            "groups": [["剩菜", "剩饭", "熟食", "卤味"], ["隔夜", "放了一晚", "过夜", "一晚上", "一夜", "第二天", "存放"]],
        },
        "response_message_id": "MSG-FS-011", "block": True, "risk_level": "high",
        "evidence_ref": "细菌繁殖与亚硝酸盐风险（演示口径）",
    },
    # ---- 特殊人群（input，block=true）----
    {
        "rule_code": "SP-001", "category": "special_population", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["蜂蜜"], "any": True, "mode": "all_groups",
            "groups": [["蜂蜜"], ["婴儿", "宝宝", "幼儿", "新生儿", "1岁", "一岁", "周岁"]],
        },
        "response_message_id": "MSG-SP-001", "block": True, "risk_level": "critical",
        "evidence_ref": "婴儿肉毒中毒风险（演示口径）",
    },
    {
        "rule_code": "SP-002", "category": "special_population", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["孕妇", "怀孕", "孕早", "孕晚", "孕妈", "哺乳期"], "any": True, "mode": "all_groups",
            "groups": [["孕妇", "怀孕", "孕早", "孕晚", "孕妈", "哺乳期"], ["生鱼片", "刺身", "生鸡蛋", "溏心蛋", "醉虾", "生腌", "生蚝(生)", "半熟", "五分熟", "生食", "温泉蛋"]],
        },
        "response_message_id": "MSG-SP-002", "block": True, "risk_level": "high",
        "evidence_ref": "李斯特菌/弓形虫感染风险（演示口径）",
    },
    # ---- 医疗拒答（input，block=true，TXT-G04 拒答即不生成业务内容）----
    {
        "rule_code": "MR-001", "category": "medical_refusal", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["降血糖", "降血压", "降血脂", "替代药物", "代替药", "不用吃药", "不吃药", "停药"], "any": True,
        },
        "response_message_id": "MSG-MR-001", "block": True, "risk_level": "critical",
        "evidence_ref": "PRD §10.6 医疗拒答范围（RL-7）",
    },
    {
        "rule_code": "MR-002", "category": "medical_refusal", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["治疗", "治好", "治愈", "痊愈", "根治", "疗效", "药到病除"], "any": True,
        },
        "response_message_id": "MSG-MR-002", "block": True, "risk_level": "critical",
        "evidence_ref": "PRD §10.6 医疗拒答范围（RL-7）",
    },
    {
        "rule_code": "MR-003", "category": "medical_refusal", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["治疗方案", "处方", "用药", "剂量", "胰岛素", "服药", "吃什么药"], "any": True,
        },
        "response_message_id": "MSG-MR-003", "block": True, "risk_level": "critical",
        "evidence_ref": "PRD §10.6 医疗拒答范围（RL-7）",
    },
    {
        "rule_code": "MR-004", "category": "medical_refusal", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["药膳", "食疗治病", "中药配方", "偏方"], "any": True,
        },
        "response_message_id": "MSG-MR-004", "block": True, "risk_level": "high",
        "evidence_ref": "PRD §10.6 医疗拒答范围（RL-7）",
    },
    # ---- 伪科学（input，block=false，澄清引导而非阻断）----
    {
        "rule_code": "PS-001", "category": "pseudoscience", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["相克", "相冲", "一起吃会中毒", "同食中毒", "不能一起吃", "克死"], "any": True,
        },
        "response_message_id": "MSG-PS-001", "block": False, "risk_level": "medium",
        "evidence_ref": "PRD §10.6 伪科学澄清（RL-10）",
    },
    {
        "rule_code": "PS-002", "category": "pseudoscience", "stage_scope": "input",
        "trigger_condition": {
            "keywords": ["致癌", "癌症克星", "防癌神菜", "隔夜水致癌", "千滚水致癌"], "any": True,
        },
        "response_message_id": "MSG-PS-002", "block": False, "risk_level": "medium",
        "evidence_ref": "PRD §10.6 伪科学澄清（RL-10）",
    },
    # ---- 输出侧禁令（output，block=true，命中即替换/拦截该表述）----
    {
        "rule_code": "OB-001", "category": "output_ban", "stage_scope": "output",
        "trigger_condition": {
            "keywords": ["低脂", "无糖", "高蛋白", "高膳食纤维", "富含膳食纤维", "零脂肪", "0脂肪"], "any": True,
        },
        "response_message_id": "MSG-OB-001", "block": True, "risk_level": "medium",
        "evidence_ref": "PRD §10.7 输出侧禁令表（RL-9 法定营养声称）",
    },
    {
        "rule_code": "OB-002", "category": "output_ban", "stage_scope": "output",
        "trigger_condition": {
            "keywords": ["治疗", "治好", "痊愈", "根治", "药到病除"], "any": True,
        },
        "response_message_id": "MSG-OB-002", "block": True, "risk_level": "high",
        "evidence_ref": "PRD §10.7 输出侧禁令表（RL-7 医疗宣称）",
    },
    {
        "rule_code": "OB-003", "category": "output_ban", "stage_scope": "output",
        "trigger_condition": {
            "keywords": ["绝对安全", "保证不过敏", "放心吃", "放心食用", "百分百安全", "肯定不过敏"], "any": True,
        },
        "response_message_id": "MSG-OB-003", "block": True, "risk_level": "high",
        "evidence_ref": "PRD §10.7 输出侧禁令表（RL-2 安全承诺）",
    },
    {
        "rule_code": "OB-004", "category": "output_ban", "stage_scope": "output",
        "trigger_condition": {
            "keywords": ["最好的", "第一", "最健康", "唯一", "最有效", "顶级"], "any": True,
        },
        "response_message_id": "MSG-OB-004", "block": True, "risk_level": "medium",
        "evidence_ref": "PRD §10.7 输出侧禁令表（RL-8 绝对化用语）",
    },
    {
        "rule_code": "OB-005", "category": "output_ban", "stage_scope": "output",
        "trigger_condition": {
            "keywords": ["减肥", "瘦身", "月瘦", "减脂掉秤", "瘦几斤"], "any": True,
        },
        "response_message_id": "MSG-OB-005", "block": True, "risk_level": "medium",
        "evidence_ref": "PRD §10.7 输出侧禁令表（RL-11 功效宣称）",
    },
    # ---- 创新风控（L.12，配套模块 O AI 菜品创新；输入 1 条 + 输出 2 条）----
    {
        # 输入侧医疗红线：把「创新菜」当医疗手段的请求（治/疗/降病/降压/降糖类）
        # 说明：「降血糖」等字面量已由 MR-001 关键词覆盖，本规则兜底 MR 词表未覆盖
        # 的创新语境变体（如「降糖」「控糖」），两规则同为医疗红线，命中任一即拦截。
        "rule_code": "INNO-001", "category": "medical_refusal", "stage_scope": "input",
        "trigger_condition": {
            "regex": [
                r"创新.{0,30}?(治|疗|治病|治好|治愈|疗效|降.{0,2}病|降压|降糖|降血糖|降血脂|控糖|控压|稳血糖)",
            ],
        },
        "response_message_id": "MSG-MR-001", "block": True, "risk_level": "critical",
        "evidence_ref": "L.12 创新风控：创新菜不得作为医疗手段（RL-7 医疗红线）",
    },
    {
        # 输出侧：创新输出不得作出绝对化安全承诺（「安全放心尽管吃/绝对不会出问题」类）
        "rule_code": "INNO-002", "category": "output_ban", "stage_scope": "output",
        "trigger_condition": {
            "keywords": [
                "安全放心尽管吃", "放心尽管吃", "完全可以放心吃", "绝对不会出问题",
                "绝对不会出事", "绝对不会有问题", "保证不会出问题", "绝对不会过敏",
            ],
            "any": True,
        },
        "response_message_id": "MSG-OB-003", "block": True, "risk_level": "high",
        "evidence_ref": "L.12 创新风控：创新输出禁止安全承诺（RL-2 安全承诺）",
    },
    {
        # 输出侧：创新输出不得出现「相克/解毒/排毒」类伪科学表述
        "rule_code": "INNO-003", "category": "pseudoscience", "stage_scope": "output",
        "trigger_condition": {
            "keywords": ["相克", "解毒", "排毒", "以毒攻毒", "清除毒素"], "any": True,
        },
        "response_message_id": "MSG-PS-001", "block": True, "risk_level": "medium",
        "evidence_ref": "L.12 创新风控：创新输出禁止伪科学表述（RL-10 伪科学澄清）",
    },
]
