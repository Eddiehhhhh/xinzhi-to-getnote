# 滴答清单任务自动同步

自动将滴答清单的任务同步到 Notion 任务中心，并关联到日记中心。

## 功能

- **滴答 → 任务中心**：根据滴答清单的任务，自动在 Notion 任务中心创建/更新任务
- **清单同步**：自动将滴答任务的所属清单（projectId）关联到任务中心的「清单」字段
- **任务 → 日记**：将当天的任务自动关联到 Notion 日记中心的「事件与任务」字段
- **标题 + 时间双重验证**：关联时同时验证任务名称和日期，避免错误匹配（如"广州"匹配到"曼谷飞广州"）
- **范围日期支持**：跨天任务（如出差 04-09 ~ 04-14），只要今天在范围内即匹配
- **每天两次**：下午 16:00 和深夜 23:30（北京时间）自动运行
- 🔒 使用 GitHub Secrets 安全存储 Token

## 定时执行

| 时间（北京时间） | 任务 |
|------|------|
| 15:50 | dida2taskcenter：同步滴答任务到任务中心 |
| 16:00 | dida2diary：把任务关联到日记中心 |
| 23:20 | dida2taskcenter：同步滴答任务到任务中心 |
| 23:30 | dida2diary：把任务关联到日记中心 |

## 触发方式

### 1. 自动定时（GitHub Schedule）
自动按上面时间表运行。

### 2. 手动触发（推荐调试用）
在 GitHub Actions 页面点击 "Run workflow"，可指定目标日期。

### 3. repository_dispatch（可靠触发）
```
POST https://api.github.com/repos/Eddiehhhhh/dida-task-sync/dispatches
Headers:
  Authorization: Bearer <你的 GitHub PAT>
  Accept: application/vnd.github.v3+json
Body:
  {"event_type": "sync"}
```

## 配置方法

### 1. Fork 本仓库

### 2. 添加 Secrets

在 GitHub 仓库的 `Settings → Secrets and variables → Actions` 中添加：

| Secret Name | 说明 |
|-------------|------|
| `NOTION_TOKEN` | Notion Integration Token |
| `DIDA_TOKEN` | 滴答清单 API Token |

### 3. 启用 Actions

在 GitHub 仓库的 `Actions` 页面启用工作流。

## 本地测试

```bash
# 设置环境变量
export NOTION_TOKEN=your_notion_token
export DIDA_TOKEN=your_dida_token

# 同步滴答任务到任务中心（dry-run 模拟）
python3 dida2taskcenter_sync.py 2026-04-21

# 同步任务到日记（dry-run 模拟）
python3 dida2diary_linker.py 2026-04-21

# 实际执行（不加 dry-run）
python3 dida2taskcenter_sync.py 2026-04-21 run
python3 dida2diary_linker.py 2026-04-21 run
```

## 工作原理

### 第一步：dida2taskcenter_sync.py
1. 从滴答清单所有清单拉取当天任务
2. 在 Notion 任务中心搜索是否已存在（精确匹配标题）
3. 不存在 → 创建新任务；日期不一致 → 更新日期

### 第二步：dida2diary_linker.py
1. 同样拉取当天滴答任务
2. 在任务中心用 `title.equals` 精确匹配标题
3. 同时验证任务的日期范围包含今天
4. 通过后把任务 ID 关联到日记当天条目的「事件与任务」字段

## 隐私说明

- 本仓库为公开仓库，所有敏感信息（Token、API Key）都存储在 GitHub Secrets 中
- 运行日志中不会输出任何敏感信息

## License

MIT
