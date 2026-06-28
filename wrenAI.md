这是 WrenAI 最有价值的四个核心，也是它和普通 Text-to-SQL 项目最大的区别。

我建议不要把它理解成 「一个 AI 帮你写 SQL」，而是理解成 「给 AI 构建一个数据库操作系统（Data Operating System）」。

它解决的其实是一个问题：

LLM 会推理，但是它没有企业知识（Business Knowledge）。

所以 WrenAI做的是：

               企业知识
                   │
        ┌──────────┴──────────┐
        │                     │
   Semantic Layer        Context Layer
        │                     │
        └──────────┬──────────┘
                   │
            Planning Engine
                   │
            Validation Engine
                   │
                SQL Engine
                   │
               Database

下面我们一层一层拆开。

⸻

第一部分：Semantic Modeling（MDL）

这是整个 Wren 的灵魂。

官方甚至把它称为 Semantic Contract（语义契约）。 

⸻

为什么需要 MDL？

假设数据库是这样的：

orders
--------
order_id
user_id
price
discount
refund
status
users
--------
id
nickname
level

对于 AI 来说：

什么叫 Revenue？

不知道。

可能：

SUM(price)

也可能：

SUM(price-discount)

或者

SUM(price-discount-refund)

LLM 根本不知道。

⸻

于是 Wren 引入一层：

Physical Table
        │
        ▼
Semantic Model
        │
        ▼
Business Model

例如：

orders
↓
Sales
↓
Revenue

这时候：

AI 不需要理解数据库。

它理解的是：

Revenue

⸻

MDL 到底是什么？

MDL（Modeling Definition Language）可以理解成：

数据库的业务说明书。

不是：

数据库怎么存

而是：

业务怎么看数据库

官方文档把它定义为把物理数据转换成结构化、可查询的业务模型。 

例如：

model:
  name: customers
table:
  public.users
columns:
- customer_id
- customer_name
- total_revenue
- vip_level

注意：

这里已经没有：

users.id

而是：

customer_id

⸻

MDL 干了哪些事情？

它其实做了六件事情。

① Rename（重命名）

数据库：

cust_nm

MDL：

Customer Name

⸻

数据库：

o_amt

MDL：

Revenue

AI 不需要猜。

⸻

② Hide（隐藏）

数据库可能有：

password
internal_note
salary

AI 不应该看到。

MDL：

Expose:
customer_name
email
city

剩下全部隐藏。

⸻

③ Relationship（关系）

数据库：

orders.user_id
users.id

AI 不知道 Join。

MDL：

Customer
1:N
Orders

以后：

AI 自动知道：

Customer
↓
Orders

应该怎么 Join。

⸻

④ Metric（指标）

这是 BI 最重要的一层。

例如：

Revenue
GMV
Profit
Active User

全部提前定义。

例如：

Revenue =
SUM(amount-refund)

以后：

用户问：

本月 Revenue

AI 根本不用推导。

直接引用 Metric。

⸻

⑤ Calculated Field（计算字段）

例如：

数据库：

birth_date

AI 想算：

Age

MDL：

Age =
today-birth_date

以后：

Age 就变成一个字段。

⸻

⑥ Governance（治理）

例如：

Marketing
不能看
Salary

MDL 可以限制。

所以：

AI 即使知道 SQL，

也访问不了。

⸻

为什么 MDL 比 dbt Semantic Layer 更适合 AI？

很多人会想到 dbt Semantic Layer。

区别在于：

dbt	Wren MDL
给 BI 用	给 AI 用
Metric	Metric
Model	Model
Dimension	Dimension
Prompt Context	✅
Agent Planning	✅
Validation	✅
Memory	✅

Wren 的目标不是替代 BI，而是让 Agent 理解业务语义。 

⸻

第二部分：Context Retrieval

这是 Wren 我认为最先进的部分。

很多 Text2SQL：

Schema
↓
Prompt
↓
GPT

结束。

但是如果：

数据库：

300 tables
5000 columns

Prompt：

120000 Tokens

LLM 根本放不进去。

⸻

于是 Wren 做了：

Question
↓
Retriever
↓
Top-K Context
↓
LLM

官方把这个称为 Schema Context Retrieval + Query Recall，不仅检索模型和关系，还会检索历史成功案例。 

⸻

Retriever 检索什么？

不是只检索 Table。

而是：

Question
↓
Model
↓
Metric
↓
Relationship
↓
Business Rule
↓
Instruction
↓
Example SQL
↓
History

例如：

用户：

Which VIP customers spent the most last month?

Retriever：

返回：

Customer Model
VIP Definition
Revenue Metric
Orders Relation
Example SQL

而不是：

整个数据库

⸻

为什么要 Example Retrieval？

假设：

历史有人问过：

Monthly Revenue

SQL：

SELECT ...

以后：

问：

Revenue by Month

Retriever：

直接把：

Example SQL

一起送给 GPT。

效果提升非常明显。

⸻

为什么还要 Instruction？

Instruction 是：

业务规则。

例如：

Revenue
必须排除 Refund

或者：

所有查询默认
country='US'

Retriever 也会取出来。

官方建议把这些放在 instructions.md 等可版本管理的文件中，而不是散落在 Prompt 里。 

⸻

第三部分：Planning + Validation

这是 Wren 与很多 SQL Agent 最大的不同。

普通流程：

Question
↓
GPT
↓
SQL

结束。

Wren：

Question
↓
Planner
↓
Logical Plan
↓
Validator
↓
SQL
↓
Dry Run
↓
Execute

官方把这种设计称为“Correctness is a system（正确性是一套系统）”，而不是一次 Prompt。 

⸻

Planner 在做什么？

Planner 不写 SQL。

Planner 写的是：

Execution Plan

例如：

Goal：
Find Top Revenue Customers
Need：
Customer
Revenue
Order
Join
Sort
Limit

最后：

SQL Generator：

根据 Plan 写 SQL。

⸻

Validator 做什么？

生成 SQL 后：

不会立刻执行。

而是检查：

Column Exists?
Metric Exists?
Join Valid?
Permission?
SQL Dialect?

如果失败：

返回：

Hint

例如：

customer_name
Not Found
Did you mean
customers.name ?

然后：

Planner：

重新生成。

这比传统“报错退出”更适合 Agent 多轮修正。 

⸻

第四部分：Agent Skills

这是新版 Wren 最大的升级。

以前：

开发者：

Read README
↓
Install
↓
Configure
↓
Generate MDL
↓
Connect DB

现在：

Agent 做。

官方把 Skills 定义为可复用的工作流（Workflow Guides），安装后可以供 Claude Code、Cursor、Codex 等 AI 编程 Agent 调用。 

例如：

User：
Connect PostgreSQL

Skill：

Connect DB
↓
Read Schema
↓
Generate MDL
↓
Validate
↓
Store Context

再例如：

User：
Create semantic model

Skill：

Read Tables
↓
Infer PK
↓
Infer FK
↓
Generate Model
↓
Generate Metric
↓
Save

Skill 更像是把一套专家操作流程封装成标准步骤，而不是一次性的 Prompt。

⸻

这四部分是如何协同工作的？

把四者串起来，就得到 WrenAI 的完整闭环：

                 用户问题
                     │
                     ▼
         Context Retrieval
     （找相关模型、指标、规则、示例）
                     │
                     ▼
          Semantic Modeling (MDL)
   （提供统一业务语义，而非原始 Schema）
                     │
                     ▼
               Planner
    （生成逻辑计划，而不是直接写 SQL）
                     │
                     ▼
              SQL Generator
                     │
                     ▼
              Validator
 （校验字段、Join、指标、权限、SQL 方言）
                     │
          ┌──────────┴──────────┐
          │                     │
      校验通过              返回错误提示
          │                     │
          ▼                     ▼
      执行 SQL          Planner 修正后重试

如果把它和传统的 RAG Agent 做对比，最大的不同在于：

* RAG Agent：检索文档 → 把文档塞给 LLM → 希望 LLM 推理正确。
* WrenAI：先把企业知识建模成 MDL（结构化语义），再通过 Retriever 精准取回相关上下文，之后交给 Planner 生成计划，再由 Validator 做机器级校验。

因此，它把企业知识从“Prompt 中的自然语言”提升为“机器可理解、可版本管理、可验证的上下文层”，这也是 Wren 官方不断强调 Context Layer 而不仅仅是 Semantic Layer 的原因。 

如果你想真正理解 Wren 的设计思想，我建议下一步直接阅读源码中的 core/，重点追踪 MDL 是如何被解析（Parser）→ 编译（Planner）→ 重写 SQL（Rewriter）→ 校验（Validator） 的完整流程。这部分基本体现了 WrenAI 的核心技术实现。





这是一个非常好的问题。

实际上，部署 WrenAI 大概只占整个项目工作的 10%，真正的工作是持续建设 Context Layer（上下文层）。

很多人第一次接触 Wren，以为流程是：

部署 → 连数据库 → AI 就能回答所有问题

实际上更接近：

部署 → 建模 → 补充业务知识 → 持续优化 → AI 越来越懂你的业务。 

如果站在企业使用者的角度，我会把工作拆成 6 个阶段。

⸻

第一阶段：连接数据源（一次性工作）

这一阶段主要是技术接入。

需要做的事情包括：

* 配置数据库连接（Postgres、Snowflake、BigQuery 等）
* 测试连接
* 扫描 Schema
* 获取所有 Table
* 获取 Column
* 获取 FK / PK

官方的 onboarding/generate-mdl 工作流会帮助完成项目初始化、连接配置和首次模型生成。 

例如：

sales
customer
product
payment
inventory

这一阶段几乎没有业务人员参与。

⸻

第二阶段：生成 MDL（第一次建模）

这是最重要的一步。

假设数据库里面有：

sales_order
customer_master
sales_order_detail
t_product
m_region

AI 看到的是：

sales_order

业务看到的是：

订单

所以要建立 Mapping。

例如：

Model
Customer
↓
customer_master
Order
↓
sales_order

这一步相当于告诉 AI：

以后不要按数据库理解，而要按业务理解。

⸻

需要做哪些事情？

例如：

数据库：

cust_nm

改成：

Customer Name

数据库：

ord_amt

改成：

Revenue

数据库：

is_del

告诉 AI：

Deleted Flag

这些工作其实就是：

给数据库加”中文说明”。

⸻

第三阶段：补业务知识（Context）

这一阶段工作量最大。

因为数据库里面没有：

什么叫活跃客户？

没有：

什么叫 GMV？

没有：

什么叫退款？

这些全部要告诉 AI。

官方建议把这些知识放在可版本管理的上下文文件（例如 instructions.md）中，而不是散落在 Prompt 里。 

例如：

Revenue
=
paid_amount
-
refund

例如：

Active Customer
过去90天
至少一笔订单

例如：

VIP
累计消费
>5000元

例如：

GMV
包含优惠券
不包含退款

这一层非常像：

企业自己的 Wiki。

⸻

第四阶段：补充业务规则（Governance）

很多 SQL 都不能随便跑。

例如：

所有查询：

默认：

country='CN'

例如：

Marketing：

不能看：

salary

例如：

Finance：

不能查：

test_order

例如：

订单：

必须：

status='paid'

这些都是：

Business Rule。

数据库不会告诉 AI。

只能人为维护。

⸻

第五阶段：沉淀经验（Memory）

这是很多人忽略的一层。

例如：

老板每天都会问：

本月收入

第一次：

AI 生成 SQL。

第二次：

AI 又重新推理。

其实没必要。

Wren 的思路是把这些成功的问题、SQL 和上下文沉淀为可复用的记忆，让后续类似问题直接利用已有经验，而不是每次从零开始。 

例如：

Question
↓
SQL
↓
Good
↓
Memory

以后：

Revenue
Monthly Revenue
Revenue by Month

Retriever：

直接找到。

⸻

第六阶段：持续维护 Semantic Layer（长期工作）

数据库一定会变化。

例如：

今天：

customer

明天：

改成：

customer_v2

今天：

GMV

定义：

不包含退款

下个月：

老板决定：

包含退款

那么：

MDL：

也要改。

所以：

Semantic Layer

不是：

一次开发。

而是：

持续维护。

⸻

一个真实企业里通常是谁负责？

如果把这些工作拆给团队，一般会是这样的：

工作  负责人
连接数据库 数据工程师
生成 MDL  数据工程师 + BI
定义 Metric BI / 数据分析师
定义业务规则  业务负责人
补充 Instructions 数据分析师
审核 SQL  数据负责人
维护 Memory AI 自动 + 人工审核

所以：

真正懂业务的人，比懂 AI 的人更重要。

⸻

如果你们公司已经有 dbt，会轻松很多

很多公司已经维护了：

dbt

里面已经有：

Model
Dimension
Metric
Description

这些内容都可以作为 Wren Context Layer 的基础。

Wren 不一定要你从零开始，它更像是在已有语义层基础上增加 AI 所需的上下文（业务定义、规则、示例、记忆等）。 

⸻

我建议的落地流程（实践经验）

如果我是企业里的 AI 平台负责人，我不会一开始就把整个数仓接入 Wren，而会采用下面的节奏：

第 1 周：接一个业务域

* 选择 5–10 张核心表（例如订单、客户、商品）。
* 自动生成 MDL，并人工审核模型名称、字段名称和关联关系。

第 2 周：定义业务语义

* 补充 20–50 个核心指标（GMV、Revenue、Active User 等）。
* 编写业务规则和默认过滤条件。
* 整理 30–50 个典型问答示例。

第 3 周：试运行

* 收集业务人员的真实提问。
* 分析失败案例，是缺少业务定义、缺少示例还是模型问题。
* 持续完善 Context Layer。

第 4 周以后：扩展覆盖范围

* 从一个业务域扩展到多个业务域。
* 建立 Context 和 MDL 的版本管理与评审流程。
* 将维护 Context Layer 纳入正常的数据治理流程。

从长期来看，WrenAI 并不是一个”安装完就结束”的产品，而更像一个企业 AI 知识平台。部署完成只是起点，真正决定回答质量的，是你们持续建设和维护的 Context Layer。企业积累得越多，AI 的回答就越稳定、越符合业务口径。