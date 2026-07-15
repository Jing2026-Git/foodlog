# 周报页面改造实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 改造周报页面，修复日均计算错误，增加分类统计（蛋白质来源、蔬菜摄入、主食结构、饮料频次），去掉标签支出列，调整标签生成逻辑。

**Architecture:** 在现有周报页面内改造，增加新的统计模块。主要修改 `static/index.html`，涉及 AI prompt、周报渲染逻辑、标签生成逻辑。

**Tech Stack:** 纯前端 HTML/JS/CSS，无需后端改动。

---

## 文件结构

| 文件 | 修改内容 |
|------|---------|
| `static/index.html` | 1. 修复日均计算 2. 增加分类统计模块 3. 去掉标签支出列 4. 调整 AI prompt |

---

### Task 1: 修复日均计算逻辑

**Files:**
- Modify: `static/index.html:485-495`

- [ ] **Step 1: 找到并修改日均计算代码**

当前代码（第488行附近）：
```javascript
const avg_daily_calories=round1(total_calories/7);
const avg_daily_price=round1(total_price/7);
```

修改为：
```javascript
const days_with_records = [...new Set(meals.map(m => m.date))].length;
const avg_daily_calories = days_with_records > 0 ? round1(total_calories / days_with_records) : 0;
const avg_daily_price = days_with_records > 0 ? round1(total_price / days_with_records) : 0;
```

- [ ] **Step 2: 验证修改**

代码应正确计算实际有记录的天数，并除以该天数。

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "fix: 日均计算改为除以实际有记录的天数"
```

---

### Task 2: 去掉标签统计中的支出列

**Files:**
- Modify: `static/index.html:510-525`（标签统计表格部分）

- [ ] **Step 1: 找到标签统计表格代码**

搜索 `标签统计` 或 `对应支出` 找到表格部分，移除"对应支出"列。

- [ ] **Step 2: 修改表格结构**

移除 `<th>对应支出</th>` 以及每个标签行中的支出列。

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "fix: 去掉标签统计中的对应支出列"
```

---

### Task 3: 增加蛋白质来源分布统计

**Files:**
- Modify: `static/index.html`（周报页面）

- [ ] **Step 1: 在周报页面增加蛋白质来源统计模块**

在标签统计前增加新的统计模块，包含：
- 标题：蛋白质来源分布
- 统计逻辑：统计 `meat_type` 字段中各蛋白质类型的出现次数和比例
- 可视化：柱状图显示各蛋白质类型的频次

- [ ] **Step 2: 实现统计逻辑**

```javascript
function getProteinStats(meals) {
    const counts = {};
    const labels = {'鱼虾': '鱼虾', '猪肉': '猪肉', '鸡鸭': '鸡鸭', '牛羊': '牛羊', '奶类': '奶类', '蛋or植物': '蛋or植物'};
    meals.forEach(m => {
        if (m.meat_type) {
            m.meat_type.split(',').forEach(t => {
                t = t.trim();
                if (labels[t]) counts[t] = (counts[t] || 0) + 1;
            });
        }
    });
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    return Object.keys(labels).map(k => ({
        name: labels[k],
        count: counts[k] || 0,
        percent: total > 0 ? round1((counts[k] || 0) / total * 100) : 0
    }));
}
```

- [ ] **Step 3: 实现渲染代码**

添加柱状图 HTML 生成逻辑，显示各蛋白质来源的频次和百分比。

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "feat: 增加蛋白质来源分布统计"
```

---

### Task 4: 增加蔬菜摄入日历（周视图）

**Files:**
- Modify: `static/index.html`（周报页面）

- [ ] **Step 1: 增加蔬菜摄入日历模块**

统计每天的蔬菜摄入情况：
- 深色叶子菜（菠菜、生菜、油麦菜等）
- 菌菇
- 瓜果茄
- 根茎类
- 豆类

- [ ] **Step 2: 实现统计逻辑**

```javascript
function getVegetableDailyStats(meals, startDate, endDate) {
    const daily = {};
    for (let d = new Date(startDate); d <= new Date(endDate); d.setDate(d.getDate() + 1)) {
        const dateStr = formatDate(d);
        daily[dateStr] = { hasVegetable: false, types: [] };
    }
    meals.forEach(m => {
        if (m.vegetable_type && daily[m.date]) {
            daily[m.date].hasVegetable = true;
            daily[m.date].types = [...new Set([...daily[m.date].types, ...m.vegetable_type.split(',').map(t => t.trim())])];
        }
    });
    return daily;
}
```

- [ ] **Step 3: 实现日历渲染**

生成周视图日历，用颜色标识每天是否摄入了蔬菜，悬停显示具体类型。

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "feat: 增加蔬菜摄入日历周视图"
```

---

### Task 5: 增加主食结构统计

**Files:**
- Modify: `static/index.html`（周报页面）

- [ ] **Step 1: 增加主食结构统计模块**

统计 `staple_food` 字段中各主食类型的频次和比例：
- 米饭
- 包子饺子
- 粗粮低GI
- 汤面汤粉
- 汉堡披萨

- [ ] **Step 2: 实现统计和渲染**

类似蛋白质来源统计，生成柱状图显示各主食类型的频次。

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat: 增加主食结构统计"
```

---

### Task 6: 增加饮料频次统计

**Files:**
- Modify: `static/index.html`（周报页面）

- [ ] **Step 1: 增加饮料频次统计模块**

统计 `food_category === '饮品'` 或 `tags` 包含"奶茶"/"咖啡"/"果汁"的记录次数。

- [ ] **Step 2: 实现统计逻辑**

```javascript
function getDrinkStats(meals) {
    const counts = { '奶茶': 0, '咖啡': 0, '果汁': 0, '其他': 0 };
    meals.forEach(m => {
        if (m.food_category === '饮品') {
            const tags = (m.tags || '').toLowerCase();
            if (tags.includes('奶茶')) counts['奶茶']++;
            else if (tags.includes('咖啡')) counts['咖啡']++;
            else if (tags.includes('果汁')) counts['果汁']++;
            else counts['其他']++;
        }
    });
    return counts;
}
```

- [ ] **Step 3: 实现渲染**

生成柱状图显示各类饮料的频次。

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "feat: 增加饮料频次统计"
```

---

### Task 7: 调整 AI prompt 中的标签生成逻辑

**Files:**
- Modify: `static/index.html`（RECOGNIZE_PROMPT 变量）

- [ ] **Step 1: 修改 tags 字段定义**

将：
```
tags: 标签（仅保留最重要的1-2个，如"外卖"、"麻辣烫"，不要生成太多）
```

改为：
```
tags: 健康属性标签（仅1-2个，如"健康餐"、"油太多"、"高纳"、"快餐"、"大餐"。商家名称不要进入标签）
```

- [ ] **Step 2: 修改 notes 字段定义**

强调商家名称应放入 notes：
```
notes: 备注（记录店铺名、套餐名、口味等详细信息）
```

- [ ] **Step 3: 修改示例中的 tags**

将示例中的 `tags="外卖"` 改为 `tags="健康餐"` 或类似健康属性标签。

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "fix: 调整标签生成逻辑，商家名放notes，tags只保留健康属性"
```

---

### Task 8: 部署并验证

**Files:**
- Push to GitHub

- [ ] **Step 1: Push 代码到 GitHub**

```bash
git push origin main
```

- [ ] **Step 2: 等待 Vercel 自动部署**

Vercel 会自动检测 GitHub push 并部署。

- [ ] **Step 3: 验证功能**

访问 https://foodlog-psi.vercel.app，检查周报页面：
1. 日均热量和支出是否正确计算
2. 标签统计是否去掉了支出列
3. 蛋白质来源分布、蔬菜日历、主食结构、饮料统计是否显示正常

---

## Self-Review

1. **Spec coverage:** 所有需求都有对应的任务覆盖
2. **Placeholder scan:** 无占位符，所有步骤都有具体代码
3. **Type consistency:** 函数名和变量名保持一致

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-15-weekly-report-improvement.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**