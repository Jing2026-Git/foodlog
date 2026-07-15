# Tasks

- [x] Task 1: 简化餐次选项常量和数据迁移
  - [x] SubTask 1.1: 修改 MEAL_TYPE_LABELS 为 {breakfast:'早餐', lunch:'午餐', dinner:'晚餐', snack:'加餐'}
  - [x] SubTask 1.2: 修改 MEAL_TYPE_ICONS 和 MEAL_TYPES_ORDER
  - [x] SubTask 1.3: 修改 MAIN_MEAL_TYPES 为 ['breakfast', 'lunch', 'dinner', 'snack']
  - [x] SubTask 1.4: 更新 guessMealType 函数，将所有加餐时间段映射到 'snack'
  - [x] SubTask 1.5: 更新 AI Prompt 中的 meal_type 字段

- [x] Task 2: 新增水果标签选项
  - [x] SubTask 2.1: 添加 FRUIT_LABELS 常量 {'berry':'浆果类','citrus':'柑橘类','tropical':'热带水果','melon':'瓜果类'}
  - [x] SubTask 2.2: 在 mealFormHtml 中添加水果标签的 Chips 组件
  - [x] SubTask 2.3: 更新 readMealForm 函数读取 fruit 字段
  - [x] SubTask 2.4: 更新 AI Prompt 增加水果识别字段

- [x] Task 3: 修复月视图标签筛选逻辑
  - [x] SubTask 3.1: 确认 mealMatchesTagFilter 函数正确处理新结构化标签
  - [x] SubTask 3.2: 函数已兼容饮品、健康餐、高油/高纳标签筛选

- [x] Task 4: 修复记录编辑功能
  - [x] SubTask 4.1: 为日视图时间线卡片添加 onclick 事件
  - [x] SubTask 4.2: 确认 openEditMealModal 函数正确调用 DB.getMealById

- [x] Task 5: 移除周视图营养缺口分析
  - [x] SubTask 5.1: 删除 renderWeekView 函数中营养缺口分析渲染代码
  - [x] SubTask 5.2: 保留 analyzeNutrientGaps 函数供分析页面使用

- [x] Task 6: 新增分析页面和导航
  - [x] SubTask 6.1: 导航栏新增"分析"按钮（在推荐和搜索之间）
  - [x] SubTask 6.2: 创建 page-analysis 页面区域
  - [x] SubTask 6.3: 实现 renderAnalysis 函数，包含"开始分析"按钮和分析结果展示区
  - [x] SubTask 6.4: 实现 runAnalysis 函数，调用 analyzeNutrientGaps
  - [x] SubTask 6.5: 更新 state 初始化包含 analysisData

- [x] Task 7: 实时统计数据优化
  - [x] SubTask 7.1: 验证 dailySummary 函数计算逻辑正确
  - [x] SubTask 7.2: 验证周/月视图统计数据基于 filtered 数组计算
  - [x] SubTask 7.3: 修复 openQuickOrder 函数确保刷新统计数据

- [x] Task 8: 周视图配色优化
  - [x] SubTask 8.1: 定义餐次配色样式（.wg-breakfast/.wg-lunch/.wg-dinner/.wg-snack）
  - [x] SubTask 8.2: 更新 renderWeekView 中 wg-meal 卡片样式，根据 meal_type 应用不同背景色
  - [x] SubTask 8.3: 配色方案：早餐晨曦橙、午餐阳光黄、晚餐月光蓝、加餐薄荷绿

# Task Dependencies
- [Task 3] 依赖 [Task 2]（水果标签新增后需更新筛选逻辑）
- [Task 4] 可并行执行
- [Task 6] 依赖 [Task 5]（分析页面复用分析函数）
- [Task 7] 可并行执行
- [Task 8] 可并行执行