# 简化餐次选项与优化视图体验 Spec

## Why
用户反馈当前餐次选项过于复杂（早/午/晚餐 + 三个时间段加餐），希望简化为早、中、晚、加餐四项。同时发现月视图标签筛选异常、记录无法编辑、周视图配色单一、统计数据不实时更新等问题，需要全面修复并优化用户体验。

## What Changes
- 简化餐次选项：从6个（早餐/午餐/晚餐/上午加餐/下午加餐/晚上加餐）简化为4个（早餐/午餐/晚餐/加餐）
- **BREAKING**: 将 `snack-am`/`snack-pm`/`snack-ev` 统一为 `snack`，需处理数据迁移
- 新增"水果"标签到自定义标签模块（蔬菜-水果标签）
- 修复月视图标签筛选逻辑
- 修复记录无法点开编辑的问题
- 移除周视图营养缺口分析模块
- 新增"分析"页面和导航按钮，支持用户选择分析模型
- 统计数据改为实时计算（非假数字）
- 周视图配色优化：早餐/午餐/晚餐/加餐使用不同配色卡片

## Impact
- Affected specs: 表单结构、数据模型、视图渲染逻辑、标签系统、导航结构
- Affected code: [static/index.html](file:///workspace/foodlog/static/index.html) 核心文件，涉及 MEAL_TYPE_LABELS、TAG_FILTERS、renderDayView、renderWeekView、renderMonthView、mealFormHtml、openEditMealModal 等函数

---

## ADDED Requirements

### Requirement: 简化餐次选项
系统 SHALL 提供简化的餐次选项，只包含早餐、午餐、晚餐、加餐四项。

#### Scenario: 用户选择餐次
- **WHEN** 用户创建或编辑记录时
- **THEN** 餐次下拉列表仅显示：早餐、午餐、晚餐、加餐

### Requirement: 新增水果标签
系统 SHALL 在自定义标签模块提供水果标签选项。

#### Scenario: 用户选择水果标签
- **WHEN** 用户编辑记录的标签时
- **THEN** 可看到"水果"标签选项，包含：浆果类、柑橘类、热带水果、瓜果类

### Requirement: 分析页面
系统 SHALL 提供独立的统计分析页面，用户可手动触发AI营养分析。

#### Scenario: 用户触发分析
- **WHEN** 用户点击"开始分析"按钮
- **THEN** 系统调用AI模型（可在设置中配置）进行营养分析，返回健康建议

### Requirement: 实时统计数据
系统 SHALL 基于真实记录实时计算统计数据。

#### Scenario: 统计数据更新
- **WHEN** 用户添加、编辑或删除记录后
- **THEN** 日/周/月视图的统计数据立即更新为实际值

### Requirement: 周视图配色优化
系统 SHALL 为周视图不同餐次使用不同配色卡片。

#### Scenario: 周视图卡片显示
- **WHEN** 用户查看周视图时
- **THEN** 早餐卡片为晨曦橙、午餐卡片为阳光黄、晚餐卡片为月光蓝、加餐卡片为薄荷绿

---

## MODIFIED Requirements

### Requirement: 标签筛选逻辑
系统 SHALL 在周视图和月视图正确筛选含指定标签的记录。

**变更说明**: 原月视图无法正确识别新结构化标签（vegetable/drink/evaluation数组），需更新筛选逻辑以兼容新旧数据结构。

### Requirement: 记录编辑功能
系统 SHALL 允许用户点击记录卡片进行编辑。

**变更说明**: 原功能因JS错误导致无法打开编辑弹窗，需修复点击事件绑定。

---

## REMOVED Requirements

### Requirement: 周视图营养缺口分析
**Reason**: 分析功能移至独立页面，用户可主动触发而非自动显示。
**Migration**: 移除 renderWeekView 中的营养缺口分析渲染代码。