#!/usr/bin/env python3
"""
步骤1：修复任务中心清单关联
功能：查询任务中心所有没有清单关联的任务，按标题去滴答匹配，补充清单关联

流程：
1. 查询任务中心所有没有清单关联的任务
2. 对每个任务，去滴答所有清单中搜索同名任务
3. 找到后根据滴答 projectId 映射到清单中心页面，更新任务中心的清单关联
"""

import requests
from datetime import datetime
import os

# ============== 配置 ==============
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
DIDA_TOKEN = os.environ.get("DIDA_TOKEN", "")

if not NOTION_TOKEN or not DIDA_TOKEN:
    raise ValueError("请设置环境变量 NOTION_TOKEN 和 DIDA_TOKEN")

TASK_DB_ID = "18133b33-7f23-8032-8f8e-e9e7c821f021"   # 任务中心
LIST_DB_ID = "ff633b33-7f23-83a9-9d02-81e0746dc1ee"  # 清单中心

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

# ============== 清单中心映射 ==============
_LIST_CACHE = None


def get_list_center_mapping() -> dict:
    """建立滴答 projectId -> 清单中心页面ID 的映射"""
    global _LIST_CACHE
    if _LIST_CACHE is not None:
        return _LIST_CACHE

    mapping = {}
    url = f"https://api.notion.com/v1/databases/{LIST_DB_ID}/query"
    payload = {"page_size": 100}

    while url:
        resp = requests.post(url, headers=NOTION_HEADERS, json=payload)
        if resp.status_code != 200:
            print(f"拉取清单中心失败: {resp.status_code}")
            break

        data = resp.json()
        for page in data.get("results", []):
            props = page.get("properties", {})
            id_data = props.get("id") or {}
            id_texts = id_data.get("rich_text") or []
            dida_project_id = id_texts[0].get("plain_text", "") if id_texts else ""
            if dida_project_id:
                mapping[dida_project_id] = page["id"]

        next_cursor = data.get("next_cursor")
        url = f"https://api.notion.com/v1/databases/{LIST_DB_ID}/query" if next_cursor else None
        payload = {"page_size": 100, "start_cursor": next_cursor}

    _LIST_CACHE = mapping
    print(f"   清单中心映射: {len(mapping)} 个条目")
    return mapping


def get_all_tasks_without_list() -> list:
    """
    查询任务中心所有没有清单关联的任务
    """
    tasks = []
    url = f"https://api.notion.com/v1/databases/{TASK_DB_ID}/query"
    payload = {
        "filter": {
            "property": "清单",
            "relation": {"is_empty": True}
        },
        "page_size": 100
    }

    while url:
        resp = requests.post(url, headers=NOTION_HEADERS, json=payload)
        if resp.status_code != 200:
            print(f"查询任务中心失败: {resp.status_code}")
            break

        data = resp.json()
        for page in data.get("results", []):
            props = page.get("properties", {})
            name_data = props.get("名称") or {}
            name_list = name_data.get("title") or []
            title = name_list[0].get("plain_text", "").strip() if name_list else ""

            date_data = props.get("日期") or {}
            date_obj = date_data.get("date") or {}
            date_str = date_obj.get("start", "")[:10] if date_obj.get("start") else ""

            if title:
                tasks.append({
                    "id": page["id"],
                    "title": title,
                    "date": date_str
                })

        next_cursor = data.get("next_cursor")
        url = f"https://api.notion.com/v1/databases/{TASK_DB_ID}/query" if next_cursor else None
        payload = {"page_size": 100, "start_cursor": next_cursor}

    return tasks


def search_dida_by_title(title: str) -> str:
    """
    在滴答所有清单中搜索同名任务，返回匹配任务的 projectId
    """
    # 先查收集箱
    inbox_url = f"{DIDA_BASE}/open/v1/project/inbox/data"
    resp = requests.get(inbox_url, headers=DIDA_HEADERS)
    if resp.status_code == 200:
        for t in resp.json().get("tasks", []):
            if t.get("title", "").strip() == title:
                return "inbox"

    # 再查各清单
    for project_name, project_id in PROJECT_IDS.items():
        url = f"{DIDA_BASE}/open/v1/project/{project_id}/data"
        resp = requests.get(url, headers=DIDA_HEADERS)
        if resp.status_code == 200:
            for t in resp.json().get("tasks", []):
                if t.get("title", "").strip() == title:
                    return project_id

    return None


def update_task_list(page_id: str, list_page_id: str) -> bool:
    """更新任务的清单关联"""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            "清单": {"relation": [{"id": list_page_id}]}
        }
    }
    resp = requests.patch(url, headers=NOTION_HEADERS, json=payload)
    return resp.status_code == 200


def get_list_name(project_id: str) -> str:
    """根据 projectId 获取清单名称"""
    for name, pid in PROJECT_IDS.items():
        if pid == project_id:
            return name
    return "收集箱" if project_id == "inbox" else project_id


def fix_list_relations(dry_run: bool = True) -> dict:
    """主函数：修复所有缺少清单关联的任务"""
    results = {
        "total": 0,
        "fixed": [],
        "not_found_in_dida": [],
        "no_mapping": [],
        "failed": []
    }

    print(f"\n{'='*60}")
    print(f"🔧 步骤1：修复任务中心清单关联")
    print(f"{'='*60}")

    # 加载清单中心映射
    print(f"\n📂 加载清单中心映射...")
    list_mapping = get_list_center_mapping()

    # 查询所有没有清单的任务
    print(f"\n🔍 查询任务中心没有清单关联的任务...")
    tasks = get_all_tasks_without_list()
    results["total"] = len(tasks)
    print(f"   找到 {len(tasks)} 个任务没有清单关联")

    if not tasks:
        return results

    # 遍历每个任务，去滴答匹配
    print(f"\n🔄 匹配滴答清单...")
    for task in tasks:
        title = task["title"]
        task_id = task["id"]
        date_str = task.get("date", "")

        # 去滴答搜索同名任务
        project_id = search_dida_by_title(title)

        if not project_id:
            print(f"   ⏭️  [{title}] [{date_str}]: 滴答中未找到，跳过")
            results["not_found_in_dida"].append(title)
            continue

        # 查找对应的清单中心页面ID
        list_page_id = list_mapping.get(project_id)
        list_name = get_list_name(project_id)

        if not list_page_id:
            print(f"   ⚠️  [{title}] [{date_str}]: 清单 [{list_name}] 在清单中心无映射，跳过")
            results["no_mapping"].append(f"{title} ({list_name})")
            continue

        # 更新清单关联
        if dry_run:
            print(f"   🔄 [{title}] [{date_str}]: 清单设为 [{list_name}]")
            results["fixed"].append(title)
        else:
            if update_task_list(task_id, list_page_id):
                print(f"   ✅ [{title}] [{date_str}]: 清单设为 [{list_name}]")
                results["fixed"].append(title)
            else:
                print(f"   ❌ [{title}] [{date_str}]: 更新失败")
                results["failed"].append(title)

    # 汇总
    print(f"\n{'='*60}")
    print(f"📊 执行结果汇总")
    print(f"{'='*60}")
    print(f"   无清单任务总数: {results['total']}")
    print(f"   修复成功: {len(results['fixed'])}")
    print(f"   滴答中未找到: {len(results['not_found_in_dida'])}")
    print(f"   清单中心无映射: {len(results['no_mapping'])}")
    print(f"   失败: {len(results['failed'])}")

    if dry_run:
        print(f"\n⚠️  当前是模拟运行，如需实际执行请设置 dry_run=False")

    return results


if __name__ == "__main__":
    import sys
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1].lower() == "run":
        dry_run = False
    print(f"🤖 修复任务中心清单关联")
    print(f"   模式: {'模拟运行' if dry_run else '实际执行'}")
    fix_list_relations(dry_run=dry_run)
