#!/usr/bin/env node

/**
 * 新枝 → Get笔记 自动同步脚本
 *
 * 功能：
 * 1. 从新枝获取笔记列表
 * 2. 筛选小红书链接
 * 3. 调用 Get笔记 API 保存
 * 4. 删除新枝中的记录
 * 5. 记录已处理的笔记ID
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

// ============ 配置 ============
const XINZHI_TOKEN = process.env.XINZHI_TOKEN;
const GETNOTE_API_KEY = process.env.GETNOTE_API_KEY;
const PROCESSED_IDS_FILE = path.join(__dirname, 'processed_ids.json');

// ============ 辅助函数 ============

// 读取已处理的 ID
function loadProcessedIds() {
  try {
    if (fs.existsSync(PROCESSED_IDS_FILE)) {
      return new Set(JSON.parse(fs.readFileSync(PROCESSED_IDS_FILE, 'utf8')));
    }
  } catch (e) {
    console.log('首次运行，创建新的处理记录...');
  }
  return new Set();
}

// 保存已处理的 ID
function saveProcessedIds(ids) {
  fs.writeFileSync(PROCESSED_IDS_FILE, JSON.stringify([...ids], null, 2));
}

// HTTP 请求封装
function httpRequest(options, body = null) {
  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch {
          resolve(data);
        }
      });
    });
    req.on('error', reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

// ============ 新枝 API ============

// 获取笔记列表
async function fetchXinzhiNotes(pageIndex = 1, pageSize = 50) {
  const options = {
    hostname: 'api.xinzhi.zone',
    path: `/api/v1/notes?pageIndex=${pageIndex}&pageSize=${pageSize}`,
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      'X-CLI-Token': XINZHI_TOKEN,  // CLI 使用 X-CLI-Token 请求头
      'x-client': 'CLI'
    }
  };
  return httpRequest(options);
}

// 删除笔记
async function deleteXinzhiNote(noteId) {
  const options = {
    hostname: 'api.xinzhi.zone',
    path: `/api/v1/notes/${noteId}`,
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      'X-CLI-Token': XINZHI_TOKEN,
      'x-client': 'CLI'
    }
  };
  return httpRequest(options);
}

// ============ Get笔记 API ============

// 保存链接笔记
async function saveToGetnote(linkUrl) {
  const options = {
    hostname: 'openapi.biji.com',
    path: '/open/api/v1/resource/note/save',
    method: 'POST',
    headers: {
      'Authorization': `GETNOTE_API_KEY ${GETNOTE_API_KEY}`,
      'Content-Type': 'application/json'
    }
  };

  const body = {
    title: '从小红书同步',
    link_url: linkUrl,
    note_type: 'link'
  };

  return httpRequest(options, body);
}

// 轮询任务状态
async function pollTaskProgress(taskId, maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 3000)); // 3秒间隔

    const options = {
      hostname: 'openapi.biji.com',
      path: '/open/api/v1/resource/note/task/progress',
      method: 'POST',
      headers: {
        'Authorization': `GETNOTE_API_KEY ${GETNOTE_API_KEY}`,
        'Content-Type': 'application/json'
      }
    };

    const result = await httpRequest(options, { task_id: taskId });

    if (result.success && result.data) {
      if (result.data.status === 'success') {
        return result.data;
      } else if (result.data.status === 'failed') {
        return { status: 'failed', error: result.data.error_msg };
      }
    }
  }
  return { status: 'timeout' };
}

// ============ 主流程 ============

async function main() {
  console.log('🚀 开始检查新枝笔记...');
  console.log('='.repeat(50));

  // 加载已处理的 ID
  const processedIds = loadProcessedIds();
  console.log(`📋 已处理的笔记数: ${processedIds.size}`);

  // 获取笔记列表
  console.log('📡 正在获取新枝笔记列表...');
  const notesResponse = await fetchXinzhiNotes();

  if (!notesResponse || !notesResponse.list) {
    console.log('❌ 获取笔记失败或返回格式异常:', JSON.stringify(notesResponse).substring(0, 200));
    return;
  }

  const notes = notesResponse.list || [];
  console.log(`📦 获取到 ${notes.length} 条笔记，总计: ${notesResponse.total}`);

  // 筛选小红书链接
  const xiaohongshuNotes = notes.filter(note => {
    if (!note.link) return false;
    return note.link.includes('xiaohongshu.com') ||
           note.link.includes('xhslink.com');
  });

  console.log(`🔴 其中 ${xiaohongshuNotes.length} 条是小红书链接`);

  // 过滤已处理的
  const newNotes = xiaohongshuNotes.filter(note => !processedIds.has(note.id));

  if (newNotes.length === 0) {
    console.log('✨ 没有新的小红书链接需要处理');
    return;
  }

  console.log(`🔴 发现 ${newNotes.length} 条新的小红书链接！`);
  console.log('-'.repeat(50));

  // 处理每条笔记
  for (const note of newNotes) {
    console.log(`\n📝 处理: ${note.title || note.link}`);
    console.log(`   链接: ${note.link}`);

    try {
      // 1. 保存到 Get笔记
      console.log('   ⏳ 保存到 Get笔记...');
      const saveResult = await saveToGetnote(note.link);

      if (saveResult.success && saveResult.data && saveResult.data.tasks) {
        const taskId = saveResult.data.tasks[0].task_id;
        console.log(`   📤 任务已创建: ${taskId}`);

        // 2. 轮询等待完成
        console.log('   ⏳ 等待内容抓取和解析...');
        const progress = await pollTaskProgress(taskId);

        if (progress.status === 'success') {
          console.log('   ✅ Get笔记保存成功!');
        } else if (progress.status === 'failed') {
          console.log(`   ⚠️ Get笔记解析失败: ${progress.error}`);
        } else {
          console.log('   ⚠️ Get笔记处理超时，但继续删除新枝记录');
        }
      } else {
        console.log('   ⚠️ Get笔记保存结果异常:', JSON.stringify(saveResult).substring(0, 200));
      }

      // 3. 删除新枝记录
      console.log('   🗑️ 删除新枝记录...');
      const deleteResult = await deleteXinzhiNote(note.id);

      if (deleteResult === '' || deleteResult.success || deleteResult.code === 0) {
        console.log('   ✅ 新枝记录已删除');
        processedIds.add(note.id);
      } else {
        console.log('   ⚠️ 删除结果:', JSON.stringify(deleteResult).substring(0, 200));
        // 仍标记为已处理，避免重复尝试
        processedIds.add(note.id);
      }

    } catch (error) {
      console.log(`   ❌ 处理出错: ${error.message}`);
    }

    // API 限流保护：每次处理后等待 2 秒
    console.log('   ⏳ 等待 2 秒避免限流...');
    await new Promise(r => setTimeout(r, 2000));
  }

  // 保存已处理的 ID
  saveProcessedIds(processedIds);
  console.log('\n' + '='.repeat(50));
  console.log('🎉 本次处理完成!');
  console.log(`📊 累计已处理: ${processedIds.size} 条`);
}

// 执行
main().catch(console.error);
