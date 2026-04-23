# dida-task-sync

滴答清单 → Notion 自动化同步

## 功能

两步独立流程：

### 步骤1：修复清单关联（每天凌晨00:30）
- 查询任务中心所有没有清单关联的任务
- 按标题去滴答匹配，找到对应的清单
- 自动更新任务的清单关联

### 步骤2：关联任务到日记（每天16:00和23:30）
- 获取滴答当天所有任务
- 在任务中心按标题+日期精确搜索匹配
- 将匹配的任务关联到日记中心

## 文件说明

| 文件 | 作用 |
|------|------|
| `fix_list_relation.py` | 步骤1：修复任务中心缺失的清单关联 |
| `link_tasks_to_diary.py` | 步骤2：关联任务到日记中心 |

## 搜索匹配规则

- **标题**：精确匹配（equals）
- **日期**：目标日期在任务的日期范围内
- 同名多条时，选择日期最接近的一条

## 本地测试

```bash
# 步骤1：修复清单关联（dry_run）
python3 fix_list_relation.py

# 步骤1：实际执行
python3 fix_list_relation.py run

# 步骤2：关联到日记（dry_run，默认昨天）
python3 link_tasks_to_diary.py

# 步骤2：指定日期 dry_run
python3 link_tasks_to_diary.py 2026-04-22

# 步骤2：指定日期实际执行
python3 link_tasks_to_diary.py 2026-04-22 run
```

## GitHub Actions

| Workflow | 触发时间（北京时间） | 作用 |
|----------|-------------------|------|
| `fix-list-relation.yml` | 每天 00:30 | 修复所有缺失的清单关联 |
| `link-tasks-to-diary.yml` | 每天 16:00, 23:30 | 关联当天任务到日记 |
