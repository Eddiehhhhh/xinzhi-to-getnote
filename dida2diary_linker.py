#!/usr/bin/env python3
"""
滴答清单任务 → 日记中心自动关联
功能：根据滴答清单的任务，自动关联到Notion日记中心

流程：
1. 获取滴答清单指定日期的任务（含日期范围匹配）
2. 在任务中心搜索匹配的任务
3. 将匹配的任务关联到日记中心
"""

import requests
import json
from datetime import datetime, timedelta

# ============== 配置 ==============
# 从环境变量读取敏感信息
import os
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
DIDA_TOKEN = os.environ.get("DIDA_TOKEN", "")

if not NOTION_TOKEN or not DIDA_TOKEN:
    raise ValueError("请设置环境变量 NOTION_TOKEN 和 DIDA_TOKEN")

# Notion数据库ID
DIARY_DB_ID = "4e6607f4-7140-4317-8fc9-d52102337869"  # 日记中心
TASK_DB_ID = "18133b33-7f23-8032-8f8e-e9e7c821f021"   # 任务中心（事件与任务）

# API基础配置
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


def get_dida_tasks_for_date(target_date: str) -> list:
    """
    获取滴答清单指定日期的任务
    包括：截止日期在当天的任务 + 日期范围覆盖当天的任务
    """
    url = f"{DIDA_BASE}/open/v1/project/inbox/data"
    response = requests.get(url, headers=DIDA_HEADERS)
    
    if response.status_code != 200:
        print(f"获取滴答任务失败: {response.status_code}")
        return []
    
    data = response.json()
    tasks = data.get("tasks", [])
    
    matched_tasks = []
    for task in tasks:
        task_id = task.get("id", "")
        title = task.get("title", "")
        due_date = task.get("dueDate", "")[:10] if task.get("dueDate") else ""
        start_date = task.get("startDate", "")[:10] if task.get("startDate") else ""
        
        # 匹配条件：
        # 1. 截止日期 = 目标日期
        # 2. 开始日期 = 目标日期
        # 3. 日期范围包含目标日期
        is_match = False
        
        if due_date == target_date or start_date == target_date:
            is_match = True
        elif start_date and due_date:
            # 检查目标日期是否在[start_date, due_date]范围内
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                end = datetime.strptime(due_date, "%Y-%m-%d")
                target = datetime.strptime(target_date, "%Y-%m-%d")
                if start <= target <= end:
                    is_match = True
            except:
                pass
        
        if is_match:
            matched_tasks.append({
                "id": task_id,
                "title": title.strip(),
                "startDate": start_date,
                "dueDate": due_date
            })
    
    return matched_tasks


def search_task_center_tasks(query: str, target_date: str = None) -> list:
    """
    在任务中心搜索匹配的任务
    按标题搜索，支持日期筛选
    """
    # 构建筛选条件
    filter_obj = {
        "property": "名称",
        "rich_text": {
            "contains": query
        }
    }
    
    payload = {
        "filter": filter_obj
    }
    
    # 如果指定了日期，添加日期筛选
    if target_date:
        payload["filter"] = {
            "and": [
                {"property": "名称", "rich_text": {"contains": query}},
                {"property": "日期", "date": {"equals": target_date}}
            ]
        }
    
    url = f"https://api.notion.com/v1/databases/{TASK_DB_ID}/query"
    response = requests.post(url, headers=NOTION_HEADERS, json=payload)
    
    if response.status_code != 200:
        print(f"搜索任务中心失败: {response.status_code} - {response.text[:200]}")
        return []
    
    data = response.json()
    tasks = []
    
    for page in data.get("results", []):
        props = page.get("properties", {})
        name_data = props.get("名称") or {}
        name_list = name_data.get("title") or []
        name = name_list[0].get("plain_text") if name_list else ""
        
        date_data = props.get("日期") or {}
        date_obj = date_data.get("date") or {}
        date_str = date_obj.get("start", "")[:10] if date_obj.get("start") else ""
        
        tasks.append({
            "id": page["id"],
            "title": name,
            "date": date_str
        })
    
    return tasks


def get_diary_entry(target_date: str) -> dict:
    """获取日记中心指定日期的条目"""
    url = f"https://api.notion.com/v1/databases/{DIARY_DB_ID}/query"
    payload = {
        "filter": {
            "property": "日期",
            "date": {"equals": target_date}
        },
        "page_size": 1
    }
    
    response = requests.post(url, headers=NOTION_HEADERS, json=payload)
    
    if response.status_code != 200:
        print(f"获取日记条目失败: {response.status_code}")
        return None
    
    data = response.json()
    results = data.get("results", [])
    
    if not results:
        print(f"未找到日期为 {target_date} 的日记条目")
        return None
    
    return results[0]


def get_existing_event_relations(diary_page_id: str) -> set:
    """获取日记当前关联的事件ID集合"""
    url = f"https://api.notion.com/v1/pages/{diary_page_id}"
    response = requests.get(url, headers=NOTION_HEADERS)
    
    if response.status_code != 200:
        return set()
    
    data = response.json()
    props = data.get("properties", {})
    events_data = props.get("事件与任务") or {}
    relations = events_data.get("relation") or []
    
    return {r.get("id") for r in relations}


def add_event_relation(diary_page_id: str, event_id: str) -> bool:
    """添加事件到日记的关联"""
    url = f"https://api.notion.com/v1/pages/{diary_page_id}"
    
    # 先获取当前关联
    existing = get_existing_event_relations(diary_page_id)
    
    if event_id in existing:
        return True  # 已经关联，跳过
    
    # 添加新关联
    new_relations = list(existing) + [event_id]
    
    payload = {
        "properties": {
            "事件与任务": {
                "relation": [{"id": rid} for rid in new_relations]
            }
        }
    }
    
    response = requests.patch(url, headers=NOTION_HEADERS, json=payload)
    
    if response.status_code == 200:
        return True
    else:
        print(f"添加关联失败: {response.status_code} - {response.text[:200]}")
        return False


def link_dida_tasks_to_diary(target_date: str, dry_run: bool = True) -> dict:
    """
    主函数：将滴答任务关联到日记中心
    
    Args:
        target_date: 目标日期 (YYYY-MM-DD)
        dry_run: True=模拟运行，False=实际执行
    
    Returns:
        执行结果统计
    """
    results = {
        "date": target_date,
        "dida_tasks": [],
        "matched_tasks": [],
        "already_linked": [],
        "newly_linked": [],
        "failed": []
    }
    
    print(f"\n{'='*60}")
    print(f"📅 日期: {target_date}")
    print(f"{'='*60}")
    
    # 1. 获取滴答任务
    print(f"\n📋 获取滴答清单任务...")
    dida_tasks = get_dida_tasks_for_date(target_date)
    results["dida_tasks"] = dida_tasks
    print(f"   找到 {len(dida_tasks)} 个滴答任务:")
    for t in dida_tasks:
        print(f"   - {t['title']} (ID: {t['id']})")
    
    if not dida_tasks:
        print("   没有找到滴答任务，退出")
        return results
    
    # 2. 获取日记条目
    print(f"\n📓 获取日记条目...")
    diary = get_diary_entry(target_date)
    if not diary:
        print("   没有找到日记条目，退出")
        return results
    
    diary_id = diary["id"]
    print(f"   日记条目ID: {diary_id}")
    
    # 3. 获取已有关联
    existing_ids = get_existing_event_relations(diary_id)
    print(f"   已有 {len(existing_ids)} 个事件关联")
    
    # 4. 匹配并关联
    print(f"\n🔗 匹配任务中心记录...")
    for dida_task in dida_tasks:
        task_title = dida_task["title"]
        
        # 在任务中心搜索
        matched = search_task_center_tasks(task_title, target_date)
        
        if not matched:
            # 如果精确匹配没找到，尝试模糊匹配（只看标题）
            matched = search_task_center_tasks(task_title)
            # 筛选日期最接近的
            if matched:
                matched = [m for m in matched if m.get("date") == target_date]
        
        if not matched:
            print(f"   ⚠️  {task_title}: 在任务中心未找到匹配")
            results["failed"].append(task_title)
            continue
        
        # 找到匹配的任务
        for task in matched:
            task_id = task["id"]
            
            if task_id in existing_ids:
                print(f"   ✅ {task_title}: 已关联")
                results["already_linked"].append(task["title"])
            else:
                if dry_run:
                    print(f"   🔄 {task_title}: 将关联 (dry_run)")
                    results["newly_linked"].append(task["title"])
                else:
                    if add_event_relation(diary_id, task_id):
                        print(f"   ✅ {task_title}: 关联成功")
                        results["newly_linked"].append(task["title"])
                    else:
                        print(f"   ❌ {task_title}: 关联失败")
                        results["failed"].append(task["title"])
            
            results["matched_tasks"].append(task)
    
    # 5. 汇总
    print(f"\n{'='*60}")
    print(f"📊 执行结果汇总")
    print(f"{'='*60}")
    print(f"   滴答任务数: {len(dida_tasks)}")
    print(f"   任务中心匹配: {len(results['matched_tasks'])}")
    print(f"   已有关联: {len(results['already_linked'])}")
    print(f"   新增关联: {len(results['newly_linked'])}")
    print(f"   失败: {len(results['failed'])}")
    
    if dry_run:
        print(f"\n⚠️  当前是模拟运行模式，如需实际执行请设置 dry_run=False")
    
    return results


def main():
    """入口函数"""
    import sys
    
    # 默认处理昨天
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 解析命令行参数
    date = yesterday
    dry_run = True
    
    if len(sys.argv) > 1:
        date = sys.argv[1]
    if len(sys.argv) > 2:
        dry_run = sys.argv[2].lower() != "run"
    
    print(f"🤖 滴答任务 → 日记中心自动关联")
    print(f"   目标日期: {date}")
    print(f"   模式: {'模拟运行' if dry_run else '实际执行'}")
    
    link_dida_tasks_to_diary(date, dry_run=dry_run)


if __name__ == "__main__":
    main()
