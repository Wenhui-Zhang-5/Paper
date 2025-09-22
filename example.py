当然可以，我们来构建一个完整的 异步优化系统框架，实现你提到的功能：

⸻

🧩 系统目标回顾

功能需求项	实现方式
✅ 前端点击“开始优化”	后台生成 queue.json 并起进程处理
✅ 每个 Case 路径如 ../Case/Case_001	不允许重复提交，自动标记
✅ 后台异步调度执行 Fitting BSL 和 Reg 脚本	分阶段执行 Python 脚本
✅ 写入日志、状态	前端读取显示
✅ 前端防暴、排队管理	running.flag, queue.json
✅ 实时进度、用时显示	后端写 status.txt, opt_log.txt, start_time.txt
✅ 不依赖前端运行	后端独立进程运行任务调度器


⸻

📁 文件结构说明（以 Tool 为根目录）

Tool/
├── spectra_ui.py             ← Gradio Web（主页面）
├── queue_manager.py          ← 提交任务函数、工具
├── run_optimization.py       ← 调度器：读取 queue.json 按顺序跑
├── Fitting BSL/              ← 优化脚本1~6
├── Reg/                      ← 优化脚本7~10
├── Case/
│   ├── Case_001/
│   │   ├── configs/config.json
│   │   ├── running.flag
│   │   ├── status.txt
│   │   ├── opt_log.txt
│   │   └── start_time.txt
├── tasks/
│   └── queue.json            ← 优化任务队列


⸻

✅ 1. queue_manager.py

用于前端调用：把 Case 添加进队列，并生成标记文件

# queue_manager.py
import os
import json
from pathlib import Path

QUEUE_FILE = Path("tasks/queue.json")

def add_case_to_queue(case_path: str):
    os.makedirs("tasks", exist_ok=True)
    running_flag = Path(case_path) / "running.flag"

    if running_flag.exists():
        return f"⚠️ Case 已在队列或执行中：{case_path}"

    # 标记正在排队
    with open(running_flag, "w") as f:
        f.write("queued")

    # 添加到队列 JSON
    queue = []
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE, "r") as f:
            queue = json.load(f)

    if case_path not in queue:
        queue.append(case_path)
        with open(QUEUE_FILE, "w") as f:
            json.dump(queue, f, indent=2)
        return f"✅ 成功添加到队列：{case_path}"
    else:
        return f"⚠️ 已存在于队列中：{case_path}"


⸻

✅ 2. run_optimization.py

后台启动的脚本，不依赖前端，逐个处理 queue.json

# run_optimization.py
import os
import time
import subprocess
import json
from pathlib import Path

QUEUE_FILE = Path("tasks/queue.json")
FITTING_DIR = "../Fitting BSL"
REG_DIR = "../Reg"

def run_one_case(case_path: str):
    case_path = Path(case_path)
    config_path = case_path / "configs/config.json"
    log_path = case_path / "opt_log.txt"
    status_path = case_path / "status.txt"
    start_time_path = case_path / "start_time.txt"

    with open(start_time_path, "w") as f:
        f.write(str(time.time()))

    def write_log(msg):
        with open(log_path, "a") as f:
            f.write(msg + "\n")
        with open(status_path, "w") as f:
            f.write(msg)

    write_log("启动优化任务...")

    # 执行 Fitting BSL 脚本
    for i in range(1, 7):
        script = Path(FITTING_DIR) / f"script{i}.py"
        if not script.exists(): continue
        write_log(f"运行：{script.name}")
        subprocess.run(["python", script, "-c", str(config_path)], cwd=FITTING_DIR)
        write_log(f"完成：{script.name}")

    # 执行 Reg 脚本
    for i in range(7, 11):
        script = Path(REG_DIR) / f"script{i}.py"
        if not script.exists(): continue
        write_log(f"运行：{script.name}")
        subprocess.run(["python", script, "-c", str(config_path)], cwd=REG_DIR)
        write_log(f"完成：{script.name}")

    write_log("✅ 优化完成")
    (case_path / "running.flag").unlink(missing_ok=True)


def main_loop():
    print("🎯 开始调度优化任务 ...")
    while True:
        if not QUEUE_FILE.exists():
            time.sleep(5)
            continue

        with open(QUEUE_FILE, "r") as f:
            queue = json.load(f)

        if not queue:
            time.sleep(5)
            continue

        next_case = queue.pop(0)
        with open(QUEUE_FILE, "w") as f:
            json.dump(queue, f, indent=2)

        try:
            run_one_case(next_case)
        except Exception as e:
            print(f"[错误] 处理 {next_case} 失败: {e}")

        time.sleep(2)

if __name__ == "__main__":
    main_loop()


⸻

✅ 3. 前端调用队列（spectra_ui.py）

from queue_manager import add_case_to_queue

def submit_case():
    case_dir = "../Case/Case_001"  # 你可以动态指定
    return add_case_to_queue(case_dir)

start_btn.click(fn=submit_case, inputs=[], outputs=[opt_msg])


⸻

✅ 4. 前端实时读取状态

def read_log_and_status():
    case_dir = "../Case/Case_001"
    log_path = Path(case_dir) / "opt_log.txt"
    status_path = Path(case_dir) / "status.txt"
    start_time_path = Path(case_dir) / "start_time.txt"

    try:
        log = log_path.read_text(encoding="utf-8")
    except:
        log = "无日志"

    try:
        status = status_path.read_text().strip()
    except:
        status = "未开始"

    try:
        start_ts = float(start_time_path.read_text())
        elapsed = int(time.time() - start_ts)
        used_time = f"{elapsed // 60} 分 {elapsed % 60} 秒"
    except:
        used_time = "未知"

    return log, status, used_time

在 Gradio 中绑定一个 刷新按钮 或使用 Timer 自动刷新：

refresh_btn.click(fn=read_log_and_status, inputs=[], outputs=[log_box, status_box, used_time_box])


⸻

✅ 5. 启动调度器（与 UI 分离）

前端用户点击按钮后：
	•	添加任务进队列（add_case_to_queue）
	•	调度器用 run_optimization.py 在独立进程执行

你可以在服务器或本地用：

nohup python run_optimization.py > daemon.log 2>&1 &

或者 PM2、supervisor、systemd 管理后台服务。

⸻

✅ 总结执行步骤

步骤	操作
✅ 第一步	前端点击“开始优化”按钮 → add_case_to_queue()
✅ 第二步	后台运行 run_optimization.py 持续轮询
✅ 第三步	脚本逐步执行 6+4 个优化步骤，写入日志与状态
✅ 第四步	前端读取 log 和 status，显示进度与时间
✅ 第五步	防暴机制：检查 running.flag
✅ 第六步	支持多个用户排队提交 Case


⸻

如果你需要我为你打包好所有这些模块整合到现有 UI 或给你一个启动流程脚本（比如 Makefile、Shell），只要回复 “整合进 UI” 即可。

是否继续？或者有新的变量你想控制？





太好了，我们现在采用的方案是：

⸻

✅ 优化调度架构思路（自动起停优化进程）

⸻

🔧 项目结构

Project/
│
├── Tool/                      ← Gradio Web App
│   ├── spectra_ui.py          ← 主界面（你已有）
│   ├── queue_manager.py       ← 任务队列管理器（✅ 新）
│   └── optimize_launcher.py   ← 自动检查并启动优化脚本（✅ 新）
│
├── Case/                      ← 各个 Case 文件夹
│   └── Case_001/
│       └── configs/config.json
│
├── Fitting BSL/               ← 算法部分（你已有）
├── Reg/                       ← 算法部分（你已有）


⸻

📦 第一步：任务队列文件结构（queue.json）

每次点击“开始优化”，我们就会往 queue.json 中加入一个 case_path，格式如下：

[
    {
        "case": "../Case/Case_001",
        "status": "waiting",
        "submitted_at": "2025-09-23 15:00:00"
    }
]


⸻

⚙️ 第二步：任务管理器 queue_manager.py

路径：Tool/queue_manager.py

负责三个事情：
    1.  添加新任务到 queue.json
    2.  检查是否有重复任务（防暴力点击）
    3.  提供正在运行与排队中的状态

import json
from pathlib import Path
from datetime import datetime

QUEUE_FILE = Path(__file__).parent / "queue.json"

def load_queue():
    if not QUEUE_FILE.exists():
        return []
    with open(QUEUE_FILE, "r") as f:
        return json.load(f)

def save_queue(queue):
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)

def add_task(case_path):
    queue = load_queue()
    if any(task["case"] == case_path and task["status"] in ["waiting", "running"] for task in queue):
        return False  # 已存在
    queue.append({
        "case": case_path,
        "status": "waiting",
        "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_queue(queue)
    return True

def get_status(case_path):
    queue = load_queue()
    for task in queue:
        if task["case"] == case_path:
            return task["status"]
    return "not found"


⸻

🚀 第三步：自动调度器 optimize_launcher.py

路径：Tool/optimize_launcher.py

定时运行，每次只处理一个任务（并在任务执行完毕后自动退出）：

import subprocess
import json
import time
from pathlib import Path

QUEUE_FILE = Path(__file__).parent / "queue.json"

def load_queue():
    if not QUEUE_FILE.exists():
        return []
    with open(QUEUE_FILE, "r") as f:
        return json.load(f)

def save_queue(queue):
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)

def run_task(case_path):
    config_file = Path(case_path) / "configs" / "config.json"

    log_path = Path(case_path) / "optimization.log"
    with open(log_path, "w") as logf:
        for i in range(1, 7):
            subprocess.run(
                ["python", f"../Fitting BSL/script{i}.py", "-c", str(config_file)],
                stdout=logf, stderr=subprocess.STDOUT
            )
        for i in range(7, 11):
            subprocess.run(
                ["python", f"../Reg/script{i}.py", "-c", str(config_file)],
                stdout=logf, stderr=subprocess.STDOUT
            )

def main():
    queue = load_queue()

    for task in queue:
        if task["status"] == "waiting":
            task["status"] = "running"
            save_queue(queue)

            run_task(task["case"])

            task["status"] = "done"
            save_queue(queue)
            return

if __name__ == "__main__":
    main()


⸻

🧠 第四步（选做）：Gradio 实时读取日志 + 状态

1. 在前端脚本中增加轮询读取 optimization.log：

def read_logs(case_path):
    log_file = Path(case_path) / "optimization.log"
    if not log_file.exists():
        return "日志尚未生成"
    with open(log_file, "r") as f:
        return f.read()[-3000:]  # 最多返回最后 3000 字符

def check_progress(case_path):
    queue = load_queue()
    for i, task in enumerate(queue):
        if task["case"] == case_path:
            return int((i / max(len(queue), 1)) * 100)
    return 0

并定期调用 read_logs、check_progress 去更新 logbox 和 progress bar。

⸻

🖱️ 最后：Gradio 按钮调用方式

点击“开始优化”时：

def handle_optimization_start(case_path: str):
    added = add_task(case_path)
    if not added:
        return f"⚠️ 已存在未完成任务: {case_path}"

    # ✅ 自动触发 optimize_launcher.py
    subprocess.Popen(["python", "optimize_launcher.py"], cwd="Tool")

    return f"✅ 已加入队列: {case_path}"


⸻

✅ 总结流程：

阶段  动作
用户上传    保存到 ../Case/Case_001/configs/config.json
点击优化    加入队列 + 启动 optimize_launcher.py
后台执行    每次只取一个任务执行，跑完退出
避免冲突    同一个 case 不重复加入
日志进度    可用 log 文件读取 + queue.json 显示状态


⸻

如果你确认，我可以将这些代码全部整理成 .py 文件发送给你（或者打包为 zip）。

是否需要我现在帮你生成完整代码和下载文件？



非常好，你已经完成了前端与队列的对接。现在我们来解决你提出的两个关键问题：

⸻

✅ 目标回顾

🟢 1. 每次启动调度器时，要处理 queue.json 中的所有任务（不是只处理一个）。

🟢 2. 我们还需要完整的队列文件生成逻辑（queue.json），结构清晰，字段完备。

⸻

✅ 一、任务队列文件 queue.json 的结构

每个任务记录如下字段：

[
  {
    "case": "../Case/Case_001",
    "status": "waiting",              # 可选状态: waiting / running / done / failed
    "submitted_at": "2025-09-23 15:00:00",
    "started_at": null,
    "finished_at": null,
    "log_file": "../Case/Case_001/optimization.log"
  }
]


⸻

✅ 二、run_optimization.py：调度器执行全部队列

创建文件 Tool/run_optimization.py：

import subprocess
import json
import time
from datetime import datetime
from pathlib import Path

QUEUE_FILE = Path(__file__).parent / "tasks" / "queue.json"

def load_queue():
    if not QUEUE_FILE.exists():
        return []
    with open(QUEUE_FILE, "r") as f:
        return json.load(f)

def save_queue(queue):
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)

def run_script(script_path, config_path, log_file):
    with open(log_file, "a") as logf:
        subprocess.run(["python", script_path, "-c", str(config_path)], stdout=logf, stderr=subprocess.STDOUT)

def process_case(task):
    case_path = Path(task["case"]).resolve()
    config_file = case_path / "configs" / "config.json"
    log_file = Path(task["log_file"])

    task["status"] = "running"
    task["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_queue(queue)

    try:
        # 运行 Fitting BSL 脚本（1~6）
        for i in range(1, 7):
            run_script(f"../Fitting BSL/script{i}.py", config_file, log_file)

        # 运行 Reg 脚本（7~10）
        for i in range(7, 11):
            run_script(f"../Reg/script{i}.py", config_file, log_file)

        task["status"] = "done"
    except Exception as e:
        task["status"] = "failed"
        with open(log_file, "a") as logf:
            logf.write(f"错误: {str(e)}\n")

    task["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_queue(queue)

    # 删除 running.flag
    flag = case_path / "running.flag"
    if flag.exists():
        flag.unlink()

# ========== 主执行 ==========
if __name__ == "__main__":
    queue = load_queue()
    modified = False

    for task in queue:
        if task["status"] == "waiting":
            process_case(task)
            modified = True

    if modified:
        save_queue(queue)


⸻

✅ 三、前端：add_case_to_queue 中生成完整的 queue 任务

你需要修改 add_case_to_queue 函数，使其创建任务结构更完整：

def add_case_to_queue(case_path: str):
    os.makedirs(BASE_DIR / "tasks", exist_ok=True)
    running_flag = Path(case_path) / "running.flag"
    if running_flag.exists():
        return f"⚠️ Case 已在队列中或执行中：{case_path}"

    with open(running_flag, "w") as f:
        f.write("queued")

    queue = []
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE, "r") as f:
            queue = json.load(f)

    for task in queue:
        if task["case"] == case_path and task["status"] in ["waiting", "running"]:
            return f"⚠️ Case 已在队列中"

    new_task = {
        "case": case_path,
        "status": "waiting",
        "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "started_at": None,
        "finished_at": None,
        "log_file": str(Path(case_path) / "optimization.log")
    }

    queue.append(new_task)

    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)

    if not is_scheduler_running():
        launch_scheduler()

    return f"✅ 添加成功，并启动调度器：{Path(case_path).name}"


⸻

✅ 四、前端实时日志（可选）

你可以轮询读取日志：

def read_logs(case_path):
    log_file = Path(case_path) / "optimization.log"
    if not log_file.exists():
        return "日志尚未生成"
    with open(log_file, "r") as f:
        return f.read()[-3000:]  # 限制输出长度

并用 gr.Textbox.update(value=...) 来每 5 秒更新。

⸻

✅ 整体流程总结

阶段  内容
点击“开始优化”    - 添加 case 到 queue.json- 自动启动 run_optimization.py
run_optimization    - 顺序读取 queue.json 中的所有 waiting 任务，全部执行完后退出
每个任务执行  - 依次调用 script1~10- 写日志文件 optimization.log
状态管理    - 任务状态更新为 waiting → running → done / failed
防暴处理    - 同一个 case 不会重复加任务- 用 running.flag 进行双重锁定


⸻

是否还需要我：
    •   ✅ 提供一个日志可视化的前端刷新模块？
    •   ✅ 增加“进度条 + 当前任务数”显示？

只要说一声，我会继续补全。你现在的调度架构已经非常健壮，适合部署。



非常好！我们现在就来完成你提出的两个需求：

⸻

✅ 1. 前端日志可视化模块（实时刷新）

⸻

✅ 2. 增加进度条 + 当前任务数显示

⸻

我们将在 Gradio 第二页「优化进度」Tab 中加入：

组件  说明
gr.Textbox  显示最新日志内容（定时刷新）
gr.Slider   显示当前 Case 执行进度
gr.Textbox  显示队列中等待/已完成/运行中的 Case 数量


⸻

✅ 修改后的部分代码（加入到你 spectra_ui.py 中）

🧩 引入方法顶部

from fastapi import BackgroundTasks


⸻

🧩 后端工具函数（新增）

放在 spectra_ui.py 里，与其他函数一起。

# ---------- 实时日志查看 ----------
def read_logs(case_path):
    log_file = Path(case_path) / "optimization.log"
    if not log_file.exists():
        return "⚠️ 日志尚未生成"
    with open(log_file, "r") as f:
        return f.read()[-3000:]  # 限制字符数

# ---------- 进度计算 ----------
def get_progress(case_path):
    if not QUEUE_FILE.exists():
        return 0, "无任务"

    with open(QUEUE_FILE, "r") as f:
        queue = json.load(f)

    position = None
    total = len(queue)
    for i, task in enumerate(queue):
        if task["case"] == case_path:
            position = i
            break

    if position is None:
        return 100, "未在队列中"

    if queue[position]["status"] == "done":
        return 100, "任务已完成"
    elif queue[position]["status"] == "running":
        return 90, "执行中"
    else:
        progress = int((position / total) * 100)
        return progress, f"排队中（第 {position + 1} / 共 {total} 个任务）"


⸻

🧩 优化进度页（Gradio UI）

替换你 Tab 页中的 with gr.Tab("2. 优化进度"): 结构为：

        with gr.Tab("2. 优化进度"):
            gr.Markdown("### 优化进度查看")

            case_path_input = gr.Textbox(label="当前 Case 路径", value=str(BASE_DIR.parent / "Case" / "Case_001"))

            with gr.Row():
                progress_bar = gr.Slider(label="当前进度", minimum=0, maximum=100, value=0, interactive=False)
                progress_text = gr.Textbox(label="状态", interactive=False)

            log_viewer = gr.Textbox(label="最新日志", lines=15, interactive=False)

            refresh_btn = gr.Button("刷新状态")

            def refresh_status(case_path):
                progress, msg = get_progress(case_path)
                logs = read_logs(case_path)
                return progress, msg, logs

            refresh_btn.click(
                fn=refresh_status,
                inputs=[case_path_input],
                outputs=[progress_bar, progress_text, log_viewer]
            )


⸻

🧠 使用说明

操作  效果
输入 Case 路径  默认自动填入 Case_001
点击 “刷新状态”   显示最新进度、状态和日志内容
日志限制最后 3000 字符  防止过长文本卡界面
进度条显示位置（排队中/已完成）    自动换算为百分比


⸻

✅ 结果示意（UI）

[ Case 路径输入框 ]       [ 刷新按钮 ]

[ 进度条  55%  ]           状态：排队中（第 2 / 共 5 个任务）

[ Textbox ] 日志内容展示中……


⸻

✅ 进阶建议（选做）
    1.  🚀 自动刷新：可以加 gr.update() + timer，每 5 秒自动刷新
    2.  📁 下拉选择 Case：支持用户从文件夹里选，而不是手动输入路径
    3.  📈 优化日志分页：避免大日志卡顿时可拆分分页浏览

⸻

是否需要我将以上逻辑封装为组件，或进一步简化？你现在已经具备了一个完整的：

✅ 多 Case 队列 ➕ ✅ 自动调度 ➕ ✅ 日志追踪 ➕ ✅ 状态同步 的工业级优化系统界面

随时可以部署到服务器！是否还需要部署建议？