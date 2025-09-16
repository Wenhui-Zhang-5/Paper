import gradio as gr
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import zipfile
import tempfile
import os
from pathlib import Path
import matplotlib.font_manager as fm


# ---------- 中文字体支持 ----------
def set_chinese_font():
    for font in fm.findSystemFonts(fontpaths=None, fontext='ttf'):
        if any(kw in font for kw in ["Heiti", "PingFang", "STSong", "YaHei"]):
            prop = fm.FontProperties(fname=font)
            plt.rcParams['font.family'] = prop.get_name()
            print(f"✅ 使用中文字体: {prop.get_name()}")
            return
    print("⚠️ 未找到中文字体，中文可能无法显示")

set_chinese_font()


# ---------- 自动选择“最值得测”的点（SPXY算法 Placeholder） ----------
def compute_spxy_index(wafer_data):
    # ⚠️ 这里你可以替换为真正的算法逻辑
    return 2 if len(wafer_data["spectra_data"]) > 2 else 0


# ---------- 解析ZIP ----------
def parse_spectra_zip(zip_file):
    if zip_file is None:
        return {}, [], None, []

    parsed_data = {}

    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(zip_file.name, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        search_path = Path(temp_dir)
        wafer_dirs = [d for d in search_path.iterdir() if d.is_dir()]

        for wafer_dir in wafer_dirs:
            wafer_id = wafer_dir.name
            spec_files = sorted(wafer_dir.glob("*.csv"))
            if not spec_files:
                continue

            wafer_data = {"ids": [], "spectra_data": []}
            for i, spec_file in enumerate(spec_files):
                try:
                    df = pd.read_csv(spec_file)
                    wafer_data["ids"].append(f"点 {i+1} ({spec_file.name})")
                    wafer_data["spectra_data"].append(df)
                except Exception:
                    continue

            if wafer_data["ids"]:
                parsed_data[wafer_id] = wafer_data

    if not parsed_data:
        raise gr.Error("没有找到有效的Wafer或光谱文件。")

    wafer_list = list(parsed_data.keys())
    return parsed_data, wafer_list, wafer_list[0], parsed_data[wafer_list[0]]["ids"]


# ---------- 画三通道光谱 ----------
def plot_spectra(wafer_data, highlight_id):
    if not wafer_data or not highlight_id:
        return None

    fig, axes = plt.subplots(3, 1, figsize=(8, 6), sharex=True)
    fig.suptitle("三通道光谱")

    try:
        highlight_idx = wafer_data['ids'].index(highlight_id)
    except ValueError:
        highlight_idx = -1

    for i, df in enumerate(wafer_data["spectra_data"]):
        is_highlight = (i == highlight_idx)
        for ch, channel in enumerate(['Channel1', 'Channel2', 'Channel3']):
            axes[ch].plot(
                df['Wavelength'], df[channel],
                alpha=1.0 if is_highlight else 0.3,
                linewidth=2.5 if is_highlight else 1.0,
                label=f"光谱 {i+1}" if is_highlight else None
            )

    for ch in range(3):
        axes[ch].set_ylabel(f"通道 {ch+1}")
        axes[ch].grid(True)
        if ch == 0 and highlight_idx != -1:
            axes[ch].legend()

    axes[2].set_xlabel("波长 (nm)")
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    return fig


# ---------- 画 Wafer Map 或 SPXY Map ----------
def plot_wafer_map(wafer_data, highlight_id=None, title="Wafer Map"):
    if not wafer_data:
        return None

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.set_title(title)

    ax.add_artist(plt.Circle((0, 0), 150, color='lightblue', alpha=0.2))

    coords = []
    for df in wafer_data["spectra_data"]:
        x = df['X'].iloc[0] if 'X' in df.columns else 0
        y = df['Y'].iloc[0] if 'Y' in df.columns else 0
        coords.append((x, y))

    wafer_data['coords'] = coords

    x_vals, y_vals = zip(*coords)
    ax.scatter(x_vals, y_vals, color='black', s=50)

    for i, (xi, yi) in enumerate(coords):
        ax.text(xi, yi + 5, str(i + 1), ha='center', va='bottom', fontsize=8)

    if title == 'SPXY map' and len(coords) > 2:
        lpi_idx = compute_spxy_index(wafer_data)
        ax.scatter(coords[lpi_idx][0], coords[lpi_idx][1],
                   color='red', s=100, zorder=10, edgecolors='black',
                   label=f'Auto Point {lpi_idx+1}')
        ax.legend(loc='lower right', fontsize=9, frameon=True)

    if title == 'Wafer Map' and highlight_id:
        try:
            highlight_idx = wafer_data["ids"].index(highlight_id)
            ax.scatter(coords[highlight_idx][0], coords[highlight_idx][1],
                       color='orange', s=100, zorder=10, edgecolors='black',
                       label=f'Selected Point {highlight_idx+1}')
            ax.legend(loc='lower right', fontsize=9, frameon=True)
        except (ValueError, IndexError):
            pass

    ax.set_xlim(-160, 160)
    ax.set_ylim(-160, 160)
    ax.set_aspect('equal')
    ax.axis('off')
    return fig

def set_baseline(wafer_id, spec_id, state):
    if not wafer_id or not spec_id:
        return "未选择光谱"

    # 提取文件名
    try:
        spec_list = state[wafer_id]["ids"]
        idx = spec_list.index(spec_id)
        filename = state[wafer_id]["spectra_data"][idx].get("filename", None)
        if filename:
            return f"{wafer_id}: {filename}"
        else:
            # fallback 方式从光谱名中提取
            raw_name = spec_id.split("(")[-1].replace(")", "").split('.')[0]
            return f"{wafer_id}: {raw_name}"
    except Exception as e:
        return f"获取光谱名失败: {e}"


def parse_film_stack(file):
    if file is None:
        return gr.update(value=[], visible=True)

    try:
        ext = Path(file.name).suffix.lower()
        if ext == ".csv":
            df = pd.read_csv(file.name)
        elif ext in [".xls", ".xlsx"]:
            df = pd.read_excel(file.name)
        else:
            raise ValueError("不支持的文件类型")

        # 添加交互列
        df['Fitting'] = True
        df['Library'] = False
        df['Reg'] = False
        df['Name'] = df['Mat']

        # 设置列顺序
        columns = ['Mat', 'THK', 'Fitting', 'Library', 'Reg', 'Name']

        print(df.dtypes)

        return df[columns]

    except Exception as e:
        raise gr.Error(f"解析 Film Stack 文件失败: {e}")

def parse_reference_csv(file):
    if file is None:
        return gr.update(visible=False),  # 不显示 preview
    try:
        df = pd.read_csv(file.name)
        return gr.update(visible=True, value=df)
    except Exception as e:
        raise gr.Error(f"Reference 文件解析失败: {e}")
    


# ---------- Gradio App ----------
def build_demo():
    with gr.Blocks(title="光谱分析与优化") as demo:
        app_state = gr.State({})

        gr.Markdown("## 上传光谱 ZIP，并查看光谱和 Wafer Map / SPXY Map")

        with gr.Row():
            zip_input = gr.File(label="上传光谱ZIP", file_types=[".zip"])

        with gr.Row():
            wafer_selector = gr.Radio(label="选择 Wafer")
            spec_selector = gr.Dropdown(label="选择光谱编号")

        with gr.Row():
            with gr.Column(scale=2):
                spectra_plot = gr.Plot(label="三通道光谱图")
                baseline_button = gr.Button("设为Baseline光谱", variant="primary")
                baseline_output = gr.Textbox(label="Baseline 光谱名称", interactive=False)
            with gr.Column(scale=1):
                wafer_map_plot = gr.Plot(label="Wafer Map")
                spxy_map_plot = gr.Plot(label="SPXY Map")

        with gr.Row():
            film_stack_upload = gr.File(label="上传Film Stack（CSV或Excel）", file_types=[".csv", ".xlsx"])

        with gr.Row():
            # ⬅️ 左侧主列（Film Stack + 保存）
            with gr.Column(scale=3):  # 主体内容占大头
                film_stack_table = gr.Dataframe(
                    headers=["Mat", "THK", "Fitting", "Library", "Reg", "Name"],
                    datatype=["str", "number", "bool", "bool", "bool", "str"],
                    label="Film Stack 结构",
                    interactive=True,
                    value=[],
                    row_count=0
                )
                save_btn = gr.Button("保存设置", variant="primary")
                save_output = gr.Textbox(label="保存结果", interactive=False)

            # ➡️ 右侧小列（Reference 上传）
            with gr.Column(scale=1):  # 比例较小
                gr.Markdown("#### Reference 文件上传 (可选)")
                reference_upload = gr.File(
                    label="上传 Reference CSV",
                    file_types=[".csv"],
                    interactive=True
                )
                reference_preview = gr.Dataframe(
                    label="Reference 内容预览",
                    interactive=False,
                    visible=False
                )

        gr.Markdown("### 实验设计参数设置")  # 标题（代替 Box）

        with gr.Row():
            lib_seed_input = gr.Number(
                label="Lib_Seed_Num",
                value=5,
                precision=0,
                interactive=True
            )

            bo_seed_input = gr.Number(
                label="BO_Seed_Num",
                value=5,
                precision=0,
                interactive=True
            )

            # 💾 保存按钮 & 输出
            save_design_btn = gr.Button("保存实验设计参数")
            save_message = gr.Markdown("", visible=True)  # ✅ 添加这一行，作为提示文字显示区
            start_optimization_btn = gr.Button("开始优化")
            opt_message = gr.Markdown("", visible=True)  # ✅ 添加这一行，作为提示文字显示区

        # ✅ 回调函数：保存实验设计
        def save_design_params(lib_val, bo_val):
            print(f"已保存：Lib_Seed_Num = {lib_val}, BO_Seed_Num = {bo_val}")
            return f"已保存：Lib_Seed_Num = {lib_val}, BO_Seed_Num = {bo_val}"

        save_design_btn.click(
            fn=save_design_params,
            inputs=[lib_seed_input, bo_seed_input],
            outputs=[save_message]
        )


        # 调用你的优化算法
        def run_optimization():
            print("[开始优化] 调用了优化算法！")
            # 调用你的真实算法入口，例如：
            # result = my_optimizer(lib_val, bo_val)
            return f'[开始优化] 调用了优化算法！'

        start_optimization_btn.click(
            fn=run_optimization,
            inputs=[],
            outputs=[opt_message]
        )

        # 事件：上传 ZIP
        def load_zip(zip_file):
            parsed_data, wafer_list, first_wafer, spec_ids = parse_spectra_zip(zip_file)
            first_spec = spec_ids[0] if spec_ids else None
            wafer_data = parsed_data[first_wafer]
            fig = plot_spectra(wafer_data, first_spec)
            fig_map = plot_wafer_map(wafer_data, first_spec, title="Wafer Map")
            fig_spxy = plot_wafer_map(wafer_data, None, title="SPXY map")
            return parsed_data, gr.update(choices=wafer_list, value=first_wafer), gr.update(choices=spec_ids, value=first_spec), fig, fig_map, fig_spxy

        zip_input.upload(fn=load_zip, inputs=[zip_input],
                         outputs=[app_state, wafer_selector, spec_selector, spectra_plot, wafer_map_plot, spxy_map_plot])

        # 事件：切换 Wafer
        def change_wafer(wafer_id, state):
            wafer_data = state.get(wafer_id, {})
            spec_ids = wafer_data["ids"]
            first_spec = spec_ids[0] if spec_ids else None
            fig = plot_spectra(wafer_data, first_spec)
            fig_map = plot_wafer_map(wafer_data, first_spec, title="Wafer Map")
            fig_spxy = plot_wafer_map(wafer_data, None, title="SPXY map")
            return gr.update(choices=spec_ids, value=first_spec), fig, fig_map, fig_spxy

        wafer_selector.change(fn=change_wafer, inputs=[wafer_selector, app_state],
                              outputs=[spec_selector, spectra_plot, wafer_map_plot, spxy_map_plot])

        # 事件：切换光谱点
        def highlight_spec(spec_id, wafer_id, state):
            wafer_data = state.get(wafer_id, {})
            fig = plot_spectra(wafer_data, spec_id)
            fig_map = plot_wafer_map(wafer_data, spec_id, title="Wafer Map")
            fig_spxy = plot_wafer_map(wafer_data, None, title="SPXY map")
            return fig, fig_map, fig_spxy

        spec_selector.change(fn=highlight_spec, inputs=[spec_selector, wafer_selector, app_state],
                             outputs=[spectra_plot, wafer_map_plot, spxy_map_plot])
        
        baseline_button.click(
            fn=set_baseline,
            inputs=[wafer_selector, spec_selector, app_state],
            outputs=[baseline_output]
        )

        film_stack_upload.upload(
            fn=parse_film_stack,
            inputs=[film_stack_upload],
            outputs=[film_stack_table]
        )

        def save_film_stack(film_data):
            try:
                df = pd.DataFrame(film_data, columns=["Mat", "THK", "Fitting", "Library", "Reg", "Name"])
                print(df.dtypes)
                selected_mats = df["Name"].tolist()
                return f"成功保存 {len(selected_mats)} 层薄膜结构：\n" + ", ".join(selected_mats)
            except Exception as e:
                return f"保存失败：{e}"
        
        save_btn.click(
                fn=save_film_stack,
                inputs=[film_stack_table],
                outputs=[save_output]
            )
        
        reference_upload.upload(
            fn=parse_reference_csv,
            inputs=[reference_upload],
            outputs=[reference_preview]
        )
                

    return demo


# ---------- 运行 ----------
if __name__ == "__main__":
    app = build_demo()
    app.launch(server_port=1111)