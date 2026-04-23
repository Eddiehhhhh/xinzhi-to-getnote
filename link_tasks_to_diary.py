#!/usr/bin/env python3
"""
步骤2：关联任务到日记中心
功能：根据滴答清单当天的任务，搜索任务中心对应记录，关联到日记中心

流程：
1. 获取滴答清单当天的任务
2. 在任务中心按（标题 + 日期）精确搜索匹配的任务
3. 将匹配的任务关联到日记中心
"""

import requests
from datetime import datetime, timedelta
import os

# ============== 配置 ==============
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
DIDA_TOKEN = os.environ.get("DIDA_TOKEN", "")

if not NOTION_TOKEN or not DIDA_TOKEN:
    raise ValueError("请设置环境变量 NOTION_TOKEN 和 DIDA_TOKEN")

DIARY_DB_ID = "4e6607f4-7140-4317-8fc9-d52102337869"  # 日记中心
TASK_DB_ID = "18133b33-7f23-8032-8f8e-e9e7c821f021"   # 任务中心

NOTION_VERSION = "2022-06-28"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}
DIDA_HEADERS = {
    "Authorization": f"Bearer {DIDA_TOKEN}",
    "Content-Type": "application/json"
}
DIDA_BASE = "https://api.dida365.com"

PROJECT_IDS = {
    "濠联": "5e4cfef0c7edd11da9d5d956",
    "产品AI": "6825ab4ef12d11b11d7a4438",
    "杂事": "6047b441e99211186ac946e9",
    "旅行": "6825aa6e4750d1b11d7a28a5",
    "学术": "6406ebd9ccacd1017417b974",
    "理财": "69870dfa2fae5176a082bb20",
    "shopee": "686e9aec5c5751e8c67cade5",
    "书籍": "5ff9ffd8fa6d5106156432a9",
    "工作": "6493430012fa510358848b31",
    "健康": "68027b74e3d0d1f4189d4578",
    "影剧": "5ff9fffdf313d106156432d5fc",
    "展览活动": "69a2c97dc101d162759eee4d",
    "自我管理": "65e40aed3e64110443527cf5",
    "购物": "6309c13dd063d1013009fb4e",
}


def get_dida_tasks_for_date(target_date: str) -> list:
    """
    获取滴答清单指定日期的任务
    包括：截止日期在当天的任务 + 日期范围覆盖当天的任务
    """
    all_tasks = []

    # 获取收集箱
    inbox_url = f"{DIDA_BASE}/open/v1/project/inbox/data"
    resp = requests.get(inbox_url, headers=DIDA_HEADERS)
    if resp.status_code == 200:
        all_tasks.extend(resp.json().get("tasks", []))

    # 获取所有清单
    for project_name, project_id in PROJECT_IDS.items():
        url = f"{DIDA_BASE}/open/v1/project/{project_id}/data"
        resp = requests.get(url, headers=DIDA_HEADERS)
        if resp.status_code == 200:
            all_tasks.extend(resp.json().get("tasks", []))

    # 去重
    seen_ids = set()
    unique_tasks = []
    for t in all_tasks:
        tid = t.get("id", "")
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            unique_tasks.append(t)

    # 匹配目标日期
    matched_tasks = []
    for task in unique_tasks:
        title = task.get("title", "").strip()
        due_date = task.get("dueDate", "")[:10] if task.get("dueDate") else ""
        start_date = task.get("startDate", "")[:10] if task.get("startDate") else ""

        is_match = False
        if due_date == target_date or start_date == target_date:
            is_match = True
        elif start_date and due_date:
            try:
                s = datetime.strptime(start_date, "%Y-%m-%d")
                e = datetime.strptime(due_date, "%Y-%m-%d")
                t = datetime.strptime(target_date, "%Y-%m-%d")
                if s <= t <= e:
                    is_match = True
            except:
                pass

        if is_match and title:
            matched_tasks.append({
                "id": task.get("id", ""),
                "title": title,
                "startDate": start_date,
                "dueDate": due_date
            })

    return matched_tasks


def search_task_center(query: str, target_date: str) -> list:
    """
    在任务中心搜索任务（标题 + 日期双重精确匹配）
    """
    payload = {
        "filter": {
            "and": [
                {"property": "名称", "title": {"equals": query.strip()}},
                {"property": "日期", "date": {"on_or_before": target_date}},
                {"property": "日期", "date": {"on_or_after": target_date}}
            ]
        },
        "page_size": 100
    }

    url = f"https://api.notion.com/v1/databases/{TASK_DB_ID}/query"
    resp = requests.post(url, headers=NOTION_HEADERS, json=payload)

    if resp.status_code != 200:
        print(f"搜索任务中心失败: {resp.status_code}")
        return []

    tasks = []
    for page in resp.json().get("results", []):
        props = page.get("properties", {})
        name_data = props.get("名称") or {}
        name_list = name_data.get("title") or []
        title = name_list[0].get("plain_text", "").strip() if name_list else ""
        date_data = props.get("日期") or {}
        date_obj = date_data.get("date") or {}
        date_str = date_obj.get("start", "")[:10] if date_obj.get("start") else ""
        tasks.append({"id": page["id"], "title": title, "date": date_str})

    return tasks


def get_diary_entry(target_date: str) -> dict:
    """获取日记中心指定日期的条目"""
    url = f"https://api.notion.com/v1/databases/{DIARY_DB_ID}/query"
    payload = {
        "filter": {"property": "日期", "date": {"equals": target_date}},
        "page_size": 1
    }
    resp = requests.post(url, headers=NOTION_HEADERS, json=payload)
    if resp.status_code != 200:
        print(f"获取日记条目失败: {resp.status_code}")
        return None
    results = resp.json().get("results", [])
    return results[0] if results else None


def get_existing_relations(diary_page_id: str) -> set:
    """获取日记当前关联的任务ID集合"""
    resp = requests.get(f"https://api.notion.com/v1/pages/{diary_page_id}", headers=NOTION_HEADERS)
    if resp.status_code != 200:
        return set()
    props = resp.json().get("properties", {})
    events = props.get("事件与任务") or {}
    return {r.get("id") for r in events.get("relation") or []}


def add_task_relation(diary_page_id: str, task_id: str) -> bool:
    """添加任务关联到日记"""
    existing = get_existing_relations(diary_page_id)
    if task_id in existing:
        return True
    new_relations = list(existing) + [task_id]
    url = f"https://api.notion.com/v1/pages/{diary_page_id}"
    payload = {
        "properties": {
            "事件与任务": {"relation": [{"id": rid} for rid in new_relations]}
        }
    }
    resp = requests.patch(url, headers=NOTION_HEADERS, json=payload)
    return resp.status_code == 200


def link_tasks_to_diary(target_date: str, dry_run: bool = True) -> dict:
    """主函数：将滴答任务关联到日记中心"""
    results = {
        "date": target_date,
        "dida_tasks": [],
        "already_linked": [],
        "newly_linked": [],
        "not_found": [],
        "failed": []
    }

    print(f"\n{'='*60}")
    print(f"📅 步骤2：关联任务到日记 — 日期: {target_date}")
    print(f"{'='*60}")

    # 1. 获取滴答当天任务
    print(f"\n📋 获取滴答当天任务...")
    dida_tasks = get_dida_tasks_for_date(target_date)
    results["dida_tasks"] = dida_tasks
    print(f"   找到 {len(dida_tasks)} 个滴答任务:")
    for t in dida_tasks:
        print(f"   - {t['title']}")

    if not dida_tasks:
        return results

    # 2. 获取日记条目
    print(f"\n📓 获取日记条目...")
    diary = get_diary_entry(target_date)
    if not diary:
        print(f"   未找到日期为 {target_date} 的日记条目，退出")
        return results

    diary_id = diary["id"]
    existing_ids = get_existing_relations(diary_id)
    print(f"   日记条目ID: {diary_id}，已有 {len(existing_ids)} 个关联")

    # 3. 匹配并关联
    print(f"\n🔗 匹配任务中心记录...")
    for dida_task in dida_tasks:
        title = dida_task["title"]
        # 用截止日期或开始日期作为匹配日期
        match_date = dida_task.get("dueDate") or dida_task.get("startDate") or target_date

        matched = search_task_center(title, match_date)

        if not matched:
            print(f"   ⚠️  {title}: 任务中心未找到匹配（日期: {match_date}）")
            results["not_found"].append(title)
            continue

        task = matched[0]
        task_id = task["id"]

        if task_id in existing_ids:
            print(f"   ✅ {title}: 已关联")
            results["already_linked"].append(title)
        else:
            if dry_run:
                print(f"   🔄 {title}: 将关联 (dry_run)")
                results["newly_linked"].append(title)
            else:
                if add_task_relation(diary_id, task_id):
                    print(f"   ✅ {title}: 关联成功")
                    results["newly_linked"].append(title)
                else:
                    print(f"   ❌ {title}: 关联失败")
                    results["failed"].append(title)

    # 4. 汇总
    print(f"\n{'='*60}")
    print(f"📊 执行结果汇总")
    print(f"{'='*60}")
    print(f"   滴答任务数: {len(dida_tasks)}")
    print(f"   已有关联: {len(results['already_linked'])}")
    print(f"   新增关联: {len(results['newly_linked'])}")
    print(f"   未找到: {len(results['not_found'])}")
    print(f"   失败: {len(results['failed'])}")

    if dry_run:
        print(f"\n⚠️  当前是模拟运行，如需实际执行请设置 dry_run=False")

    return results


if __name__ == "__main__":
    import sys

    # 默认处理昨天
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    date = yesterday
    dry_run = True

    if len(sys.argv) > 1:
        date = sys.argv[1]
    if len(sys.argv) > 2:
        dry_run = sys.argv[2].lower() != "run"

    print(f"🤖 关联任务到日记中心")
    print(f"   目标日期: {date}")
    print(f"   模式: {'模拟运行' if dry_run else '实际执行'}")

    link_tasks_to_diary(date, dry_run=dry_run)
