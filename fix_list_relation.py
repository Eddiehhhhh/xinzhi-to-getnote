#!/usr/bin/env python3
"""
步骤1：修复任务中心清单关联（优化版）
功能：一次性拉取所有滴答任务建立本地索引，批量匹配任务中心的任务并更新清单关联

流程：
1. 一次性拉取滴答全部任务（收集箱 + 所有清单）
2. 查询任务中心所有没有清单关联的任务
3. 本地精确匹配（标题 + 日期），找到对应 project_id
4. 根据 project_id 映射到清单中心页面，更新任务中心
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

# ============== 滴答任务缓存 ==============
_ALL_DIDA_TASKS = None  # 全局缓存：一次性拉取的全部滴答任务


def fetch_all_dida_tasks(force_reload: bool = False) -> list:
    """
    一次性拉取所有滴答任务（收集箱 + 所有清单），
    建立本地索引列表，后续匹配全部在内存中完成。
    返回：[ {"title", "startDate", "dueDate", "_project_id"}, ... ]
    """
    global _ALL_DIDA_TASKS
    if _ALL_DIDA_TASKS is not None and not force_reload:
        return _ALL_DIDA_TASKS

    all_tasks = []
    print("   📡 拉取滴答收集箱...", end=" ")
    try:
        resp = requests.get(
            f"{DIDA_BASE}/open/v1/project/inbox/data",
            headers=DIDA_HEADERS,
            timeout=(10, 60)
        )
        if resp.status_code == 200:
            for t in resp.json().get("tasks", []):
                t["_project_id"] = "inbox"
                all_tasks.append(t)
            print(f"✅ {len(resp.json().get('tasks', []))} 条")
        else:
            print(f"❌ HTTP {resp.status_code}")
    except requests.exceptions.Timeout:
        print("⚠️ 超时")
    except Exception as e:
        print(f"❌ {e}")

    for project_name, project_id in PROJECT_IDS.items():
        print(f"   📡 拉取清单 [{project_name}]...", end=" ")
        try:
            resp = requests.get(
                f"{DIDA_BASE}/open/v1/project/{project_id}/data",
                headers=DIDA_HEADERS,
                timeout=(10, 60)
            )
            if resp.status_code == 200:
                tasks = resp.json().get("tasks", [])
                for t in tasks:
                    t["_project_id"] = project_id
                    all_tasks.append(t)
                print(f"✅ {len(tasks)} 条")
            else:
                print(f"❌ HTTP {resp.status_code}")
        except requests.exceptions.Timeout:
            print("⚠️ 超时，跳过")
        except Exception as e:
            print(f"❌ {e}，跳过")

    _ALL_DIDA_TASKS = all_tasks
    print(f"   📊 滴答任务总计: {len(all_tasks)} 条")
    return all_tasks


def find_project_id_in_cache(title: str, target_date: str, all_tasks: list) -> str:
    """
    在本地缓存中按（标题 + 日期）精确匹配，返回 project_id。
    日期匹配规则：
      1. dueDate == target_date 或 startDate == target_date
      2. startDate <= target_date <= dueDate（区间覆盖）
    """
    if not target_date:
        return None

    for t in all_tasks:
        if t.get("title", "").strip() != title:
            continue

        due_date = t.get("dueDate", "")[:10] if t.get("dueDate") else ""
        start_date = t.get("startDate", "")[:10] if t.get("startDate") else ""

        # 精确日期匹配
        if due_date == target_date or start_date == target_date:
            return t["_project_id"]

        # 日期区间覆盖匹配
        if start_date and due_date:
            try:
                s = datetime.strptime(start_date, "%Y-%m-%d")
                e = datetime.strptime(due_date, "%Y-%m-%d")
                t_date = datetime.strptime(target_date, "%Y-%m-%d")
                if s <= t_date <= e:
                    return t["_project_id"]
            except ValueError:
                pass

    return None


# ============== Notion 操作 ==============

def get_list_center_mapping() -> dict:
    """建立滴答 projectId -> 清单中心页面ID 的映射"""
    mapping = {}
    url = f"https://api.notion.com/v1/databases/{LIST_DB_ID}/query"
    payload = {"page_size": 100}

    while url:
        resp = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=30)
        if resp.status_code != 200:
            print(f"   拉取清单中心失败: {resp.status_code}，中断")
            break

        data = resp.json()
        for page in data.get("results", []):
            props = page.get("properties", {})
            id_data = props.get("id") or {}
            id_texts = id_data.get("rich_text") or []
            dida_project_id = id_texts[0].get("plain_text", "").strip() if id_texts else ""
            if dida_project_id:
                mapping[dida_project_id] = page["id"]

        next_cursor = data.get("next_cursor")
        if next_cursor:
            payload = {"page_size": 100, "start_cursor": next_cursor}
            url = f"https://api.notion.com/v1/databases/{LIST_DB_ID}/query"
        else:
            url = None

    print(f"   清单中心映射: {len(mapping)} 个条目")
    return mapping


def get_all_tasks_without_list() -> list:
    """查询任务中心所有没有清单关联的任务"""
    tasks = []
    url = f"https://api.notion.com/v1/databases/{TASK_DB_ID}/query"
    payload = {
        "filter": {"property": "清单", "relation": {"is_empty": True}},
        "page_size": 100
    }

    while url:
        resp = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=30)
        if resp.status_code != 200:
            print(f"   查询任务中心失败: {resp.status_code}，中断")
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
                tasks.append({"id": page["id"], "title": title, "date": date_str})

        next_cursor = data.get("next_cursor")
        if next_cursor:
            payload = {"page_size": 100, "start_cursor": next_cursor}
            url = f"https://api.notion.com/v1/databases/{TASK_DB_ID}/query"
        else:
            url = None

    return tasks


def update_task_list(page_id: str, list_page_id: str) -> bool:
    """更新任务的清单关联"""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            "清单": {"relation": [{"id": list_page_id}]}
        }
    }
    resp = requests.patch(url, headers=NOTION_HEADERS, json=payload, timeout=30)
    return resp.status_code == 200


def get_list_name(project_id: str) -> str:
    """根据 projectId 获取清单名称"""
    for name, pid in PROJECT_IDS.items():
        if pid == project_id:
            return name
    return "收集箱" if project_id == "inbox" else project_id


# ============== 主流程 ==============

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
    print("🔧 步骤1：修复任务中心清单关联")
    print(f"{'='*60}")

    # 1. 加载清单中心映射
    print(f"\n📂 加载清单中心映射...")
    list_mapping = get_list_center_mapping()

    # 2. 一次性拉取所有滴答任务
    print(f"\n📡 拉取滴答全部任务（仅此一次）...")
    all_tasks = fetch_all_dida_tasks()

    # 3. 查询任务中心无清单任务
    print(f"\n🔍 查询任务中心没有清单关联的任务...")
    tasks = get_all_tasks_without_list()
    results["total"] = len(tasks)
    print(f"   找到 {len(tasks)} 个任务没有清单关联")

    if not tasks:
        return results

    # 4. 本地匹配 + 更新
    print(f"\n🔗 本地匹配并关联清单...")
    for i, task in enumerate(tasks, 1):
        title = task["title"]
        task_id = task["id"]
        date_str = task.get("date", "")

        # 本地缓存匹配
        project_id = find_project_id_in_cache(title, date_str, all_tasks)

        if not project_id:
            print(f"   [{i}/{len(tasks)}] ⏭ 滴答中未找到，跳过")
            results["not_found_in_dida"].append(task["id"])
            continue

        # 查找对应的清单中心页面ID
        list_page_id = list_mapping.get(project_id)
        list_name = get_list_name(project_id)

        if not list_page_id:
            print(f"   [{i}/{len(tasks)}] ⚠ 清单[{list_name}]在清单中心无映射，跳过")
            results["no_mapping"].append(task["id"])
            continue

        # 更新清单关联
        task_id = task["id"]
        if dry_run:
            print(f"   [{i}/{len(tasks)}] 🔄 清单设为[{list_name}] (dry_run)")
            results["fixed"].append(task_id)
        else:
            if update_task_list(task_id, list_page_id):
                print(f"   [{i}/{len(tasks)}] ✅ 清单设为[{list_name}]")
                results["fixed"].append(task_id)
            else:
                print(f"   [{i}/{len(tasks)}] ❌ 更新失败")
                results["failed"].append(task_id)

    # 汇总
    print(f"\n{'='*60}")
    print("📊 执行结果汇总")
    print(f"{'='*60}")
    print(f"   无清单任务总数: {results['total']}")
    print(f"   修复成功: {len(results['fixed'])}")
    print(f"   滴答中未找到: {len(results['not_found_in_dida'])}")
    print(f"   清单中心无映射: {len(results['no_mapping'])}")
    print(f"   失败: {len(results['failed'])}")

    if dry_run:
        print(f"\n⚠️  当前是模拟运行，如需实际执行请传递 dry_run=False")

    return results


if __name__ == "__main__":
    import sys
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1].lower() == "run":
        dry_run = False
    print("🤖 修复任务中心清单关联")
    print(f"   模式: {'模拟运行' if dry_run else '实际执行'}")
    fix_list_relations(dry_run=dry_run)
