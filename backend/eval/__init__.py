"""Agent Eval 评测框架包。

职责：
    提供意图识别 / 风控拦截 / 检索命中三条链路的离线评测能力：
    - datasets/：人工合成的 JSONL 评测数据集（intent_cases / retrieval_cases / safety_cases）；
    - run_eval.py：CLI 评测入口（python -m eval.run_eval），产出 JSON 报告 + Markdown 摘要。
"""
