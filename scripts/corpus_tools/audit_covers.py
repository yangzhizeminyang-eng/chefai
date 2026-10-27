"""封面全链路复核：覆盖所有会返回 cover_image_url 的接口。

审计范围：
    1. GET  /v1/recipes            列表分页全量（390 条）
    2. GET  /v1/recipes/{id}       详情逐条（390 条）
    3. POST /v1/recommend          多组食材组合的推荐结果
    4. POST /v1/recommend/day-menu 零输入直出
    5. GET  /v1/seasonal           时令菜谱
    6. POST /v1/recommend/filtered 布尔硬过滤重放

判定标准：
    - cover_image_url 非空；
    - 静态资源 URL 实际可访问（HTTP 200）；
    - 图片字节数 > 1KB（排除损坏文件）。

用法：
    python scripts/corpus_tools/audit_covers.py [--base http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

TIMEOUT = 60


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _check_asset(base: str, path: str, cache: dict[str, int]) -> str:
    """校验静态资源可访问，返回状态描述（函数）。"""
    if path in cache:
        return cache[path]
    try:
        with urllib.request.urlopen(f"{base}{path}", timeout=TIMEOUT) as resp:
            size = len(resp.read())
            result = "OK" if resp.status == 200 and size > 1024 else f"BAD(size={size})"
    except urllib.error.HTTPError as exc:
        result = f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        result = f"ERR {exc}"
    cache[path] = result
    return result


def _iter_items(obj, path="") -> list[tuple[str, dict]]:
    """递归收集所有含 title + cover_image_url 的条目（函数）。"""
    found: list[tuple[str, dict]] = []
    if isinstance(obj, dict):
        if "title" in obj and "cover_image_url" in obj:
            found.append((path, obj))
        for key, val in obj.items():
            found.extend(_iter_items(val, f"{path}/{key}"))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_iter_items(item, path))
    return found


def main() -> int:
    """执行全链路审计并打印结果（函数）。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    problems: list[str] = []
    cache: dict[str, int] = {}

    # ── 1/2. 列表 + 详情全量 ─────────────────────────────────────────
    items: list[dict] = []
    page = 1
    while True:
        data = _get(f"{base}/v1/recipes?page={page}&page_size=50")
        items.extend(data["items"])
        if len(items) >= data["total"] or not data["items"]:
            break
        page += 1
    print(f"[1] 列表接口 共 {len(items)} 条")
    for it in items:
        url = it.get("cover_image_url")
        if not url:
            problems.append(f"列表 {it['id']} {it['title']} 无封面")
        else:
            st = _check_asset(base, url, cache)
            if st != "OK":
                problems.append(f"列表 {it['id']} {it['title']} 资源异常 {st}")

    print(f"[2] 详情接口 逐条校验 {len(items)} 条 ...")
    for it in items:
        d = _get(f"{base}/v1/recipes/{it['id']}")
        url = d.get("cover_image_url")
        if not url:
            problems.append(f"详情 {it['id']} {it['title']} 无封面")
        else:
            st = _check_asset(base, url, cache)
            if st != "OK":
                problems.append(f"详情 {it['id']} {it['title']} 资源异常 {st}")

    # ── 3. 推荐接口 多组合 ──────────────────────────────────────────
    combos = [
        ["小白菜", "洋葱"],
        ["番茄", "鸡蛋"],
        ["土豆", "牛肉"],
        ["豆腐", "葱"],
        ["茄子", "青椒"],
        ["鸡翅", "可乐"],
        ["排骨", "冬瓜"],
        ["虾", "蒜"],
    ]
    print(f"[3] 推荐接口 {len(combos)} 组组合 ...")
    for idx, combo in enumerate(combos):
        # request_id 会进入 HTTP 响应头，必须是 ASCII（中文会导致 latin-1 编码失败）
        body = {
            "request_id": f"audit-rec-{idx:02d}",
            "ingredients": [{"name": n} for n in combo],
            "options": {"limit": 8},
        }
        d = _post(f"{base}/v1/recommend", body)
        for path, item in _iter_items(d):
            url = item.get("cover_image_url")
            tag = f"推荐[{'+'.join(combo)}]{path} {item.get('recipe_id')} {item.get('title')}"
            if not url:
                problems.append(f"{tag} 无封面")
            else:
                st = _check_asset(base, url, cache)
                if st != "OK":
                    problems.append(f"{tag} 资源异常 {st}")

    # ── 4. 今天吃什么 ───────────────────────────────────────────────
    print("[4] 今天吃什么（day-menu）...")
    d = _post(f"{base}/v1/recommend/day-menu", {"request_id": "audit-daymenu-01"})
    for path, item in _iter_items(d):
        url = item.get("cover_image_url")
        tag = f"day-menu{path} {item.get('recipe_id')} {item.get('title')}"
        if not url:
            problems.append(f"{tag} 无封面")
        else:
            st = _check_asset(base, url, cache)
            if st != "OK":
                problems.append(f"{tag} 资源异常 {st}")

    # ── 5. 时令 ─────────────────────────────────────────────────────
    print("[5] 时令接口 ...")
    try:
        d = _get(f"{base}/v1/seasonal")
        for path, item in _iter_items(d):
            url = item.get("cover_image_url")
            tag = f"时令{path} {item.get('recipe_id')} {item.get('title')}"
            if not url:
                problems.append(f"{tag} 无封面")
            else:
                st = _check_asset(base, url, cache)
                if st != "OK":
                    problems.append(f"{tag} 资源异常 {st}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"时令接口调用失败 {exc}")

    # ── 6. 被过滤掉的菜（重放） ─────────────────────────────────────
    print("[6] 硬过滤重放接口 ...")
    try:
        d = _post(
            f"{base}/v1/recommend/filtered",
            {"ingredients": [{"name": "番茄"}, {"name": "鸡蛋"}], "allergen_codes": []},
        )
        for path, item in _iter_items(d):
            url = item.get("cover_image_url")
            if not url:
                problems.append(f"filtered{path} {item.get('title')} 无封面")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"filtered 接口调用失败 {exc}")

    print(f"\n[asset] 已校验不重复资源 {len(cache)} 个")
    print(f"[result] 问题数 {len(problems)}")
    for p in problems:
        print("  ✗", p)
    if not problems:
        print("  ✓ 全部接口封面字段非空且资源可访问")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
