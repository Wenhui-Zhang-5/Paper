import gradio as gr
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import os
import zipfile
import tempfile
import shutil
from pathlib import Path

# --- 1. 数据生成函数 (用于演示) ---
def create_dummy_data():
    """
    生成用于演示的虚拟光谱数据和film stack文件。
    运行此函数后，会创建一个 'dummy_data' 文件夹。
    """
    print("正在创建虚拟数据...")
    dummy_dir = Path("dummy_data")
    spectra_dir = dummy_dir / "dummy_spectra"
    
    # 清理旧数据
    if dummy_dir.exists():
        shutil.rmtree(dummy_dir)
    
    os.makedirs(spectra_dir, exist_ok=True)

    # 创建虚拟Film Stack CSV
    film_data = {
        'Mat': ['SiO2', 'SiN', 'Poly', 'Si'],
        'THK': [100, 200, 150, 0]
    }
    pd.DataFrame(film_data).to_csv(dummy_dir / "dummy_film_stack.csv", index=False)
    print(f"已创建虚拟Film Stack: {dummy_dir / 'dummy_film_stack.csv'}")

    # 创建虚拟光谱数据
    num_wafers = 3
    points_per_wafer = 15
    wavelength = np.linspace(200, 800, 300)

    for i in range(1, num_wafers + 1):
        wafer_id = f"WAF_ID_A{i:02d}"
        wafer_dir = spectra_dir / wafer_id
        os.makedirs(wafer_dir, exist_ok=True)
        
        # 为每个wafer生成随机的测量点坐标
        angles = np.linspace(0, 2 * np.pi, points_per_wafer, endpoint=False)
        radii = np.sqrt(np.random.rand(points_per_wafer)) * 140 # 假设wafer半径为150mm
        x_coords = radii * np.cos(angles) + np.random.randn(points_per_wafer) * 5
        y_coords = radii * np.sin(angles) + np.random.randn(points_per_wafer) * 5

        for j in range(1, points_per_wafer + 1):
            spec_name = f"point_{j:02d}.csv"
            # 创建3个通道的光谱数据，加入一些变化和噪声
            ch1 = 0.5 + 0.2 * np.sin(wavelength / (50 + i*5)) + np.random.rand(300) * 0.05
            ch2 = 0.8 * np.exp(-((wavelength - (450 + j*10))**2) / (2 * (50**2))) + np.random.rand(300) * 0.03
            ch3 = ch1 * ch2 + np.random.rand(300) * 0.02
            
            spec_df = pd.DataFrame({
                'Wavelength': wavelength,
                'Channel1': ch1,
                'Channel2': ch2,
                'Channel3': ch3,
                'X': [x_coords[j-1]] * 300, # 坐标信息也保存在文件里
                'Y': [y_coords[j-1]] * 300
            })
            spec_df.to_csv(wafer_dir / spec_name, index=False)

    # 将光谱文件夹打包成ZIP
    shutil.make_archive(dummy_dir / "dummy_spectra", 'zip', spectra_dir)
    print(f"已创建虚拟光谱ZIP包: {dummy_dir / 'dummy_spectra.zip'}")
    print("虚拟数据创建完成！")


# --- 2. 后端处理函数 ---

def parse_film_stack(file):
    """解析上传的film stack文件，并添加额外的交互列"""
    if file is None:
        return None
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file.name)
        else:
            df = pd.read_excel(file.name)
        
        # 添加新列
        df['Fitting'] = True  # 默认为是浮动的
        df['Library'] = False
        df['Reg'] = False
        df['Name'] = ''
        
        # 调整列顺序
        cols = df.columns.tolist()
        new_order = ['Mat', 'THK', 'Fitting', 'Library', 'Reg', 'Name']
        # 确保原始列之外的列也保留
        other_cols = [c for c in cols if c not in ['Mat', 'THK', 'Fitting', 'Library', 'Reg', 'Name']]
        return df[new_order + other_cols]

    except Exception as e:
        raise gr.Error(f"解析Film Stack文件失败: {e}")


def parse_spectra_zip(zip_path):
    """解析上传的光谱ZIP包，提取wafer信息和光谱数据"""
    if zip_path is None:
        return {}, [], "请先上传光谱数据", "请先上传光谱数据"
    
    parsed_data = {}
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            with zipfile.ZipFile(zip_path.name, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
        except Exception as e:
            raise gr.Error(f"解压ZIP文件失败: {e}")

        # 寻找包含光谱文件的wafer文件夹
        root_dirs = [d for d in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, d))]
        if not root_dirs:
            # 可能是zip内直接是wafer文件夹
            search_path = Path(temp_dir)
        else:
            search_path = Path(temp_dir)

        wafer_dirs = sorted([d for d in search_path.iterdir() if d.is_dir()])
        if not wafer_dirs:
             raise gr.Error("在ZIP包中没有找到Wafer文件夹。请确保ZIP包内直接包含各Wafer的文件夹。")

        for wafer_dir in wafer_dirs:
            wafer_id = wafer_dir.name
            spec_files = sorted([f for f in wafer_dir.glob('*.csv')])
            
            if not spec_files:
                continue

            wafer_data = {"ids": [], "coords": [], "spectra_data": []}
            for i, spec_file in enumerate(spec_files):
                try:
                    df = pd.read_csv(spec_file)
                    wafer_data["ids"].append(f"序号 {i+1} ({spec_file.name})")
                    # 使用文件中的第一个坐标作为该点的坐标
                    wafer_data["coords"].append((df['X'].iloc[0], df['Y'].iloc[0]))
                    wafer_data["spectra_data"].append(df)
                except Exception:
                    # 跳过无法解析的文件
                    continue
            
            if wafer_data["ids"]:
                parsed_data[wafer_id] = wafer_data
    
    if not parsed_data:
        raise gr.Error("解析光谱数据失败，未找到有效的Wafer或光谱文件。")

    wafer_list = list(parsed_data.keys())
    return parsed_data, wafer_list, wafer_list[0], parsed_data[wafer_list[0]]["ids"]


def plot_spectra(wafer_data, highlight_id):
    """绘制所有光谱，并高亮显示选定的光谱"""
    if not wafer_data or not highlight_id:
        return None
    
    fig, axes = plt.subplots(3, 1, figsize=(8, 6), sharex=True)
    fig.suptitle("Spectra (三个信道)", fontsize=14)

    try:
        highlight_idx = wafer_data['ids'].index(highlight_id)
    except ValueError:
        highlight_idx = -1 # 如果找不到，则不高亮

    # 绘制所有光谱
    for i, (spec_id, df) in enumerate(zip(wafer_data['ids'], wafer_data['spectra_data'])):
        is_highlight = (i == highlight_idx)
        for ch_idx, channel in enumerate(['Channel1', 'Channel2', 'Channel3']):
            axes[ch_idx].plot(
                df['Wavelength'], df[channel],
                alpha=1.0 if is_highlight else 0.3,
                linewidth=3.0 if is_highlight else 1.0,
                zorder=10 if is_highlight else 1,
                label=spec_id if is_highlight else None
            )

    for i in range(3):
        axes[i].set_ylabel(f'Channel {i+1}')
        axes[i].grid(True, linestyle='--', alpha=0.5)
        if i==0 and highlight_idx != -1:
             axes[i].legend()

    axes[2].set_xlabel('Wavelength (nm)')
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    return fig


def plot_wafer_map(wafer_data, highlight_id, title):
    """绘制Wafer Map并高亮选定的点"""
    if not wafer_data:
        return None

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.set_title(title)
    
    # 绘制wafer边界
    wafer_circle = plt.Circle((0, 0), 150, color='lightblue', alpha=0.2)
    ax.add_artist(wafer_circle)
    
    # 提取坐标
    coords = wafer_data['coords']
    x = [c[0] for c in coords]
    y = [c[1] for c in coords]
    
    # 绘制所有点
    ax.scatter(x, y, color='black', s=50)
    
    # 标注所有点的序号
    for i, (xi, yi) in enumerate(coords):
        ax.text(xi, yi + 5, str(i + 1), ha='center', va='bottom', fontsize=8)
        
    # 高亮SPXY Map的特定点 (这里我们固定选择第3个点)
    if title == 'SPXY map' and len(coords) > 2:
        lpi_idx = 2 
        ax.scatter(coords[lpi_idx][0], coords[lpi_idx][1], color='red', s=100, zorder=10, edgecolors='black', label=f'Auto-selected Point {lpi_idx+1}')
        ax.legend()
    
    # 高亮Wafer Map中的选定点
    if title == 'Wafer map' and highlight_id:
        try:
            highlight_idx = wafer_data['ids'].index(highlight_id)
            ax.scatter(coords[highlight_idx][0], coords[highlight_idx][1], color='gold', s=100, zorder=10, edgecolors='black', label=f'Selected Point {highlight_idx+1}')
            ax.legend()
        except (ValueError, IndexError):
            pass

    ax.set_xlim(-160, 160)
    ax.set_ylim(-160, 160)
    ax.set_aspect('equal', adjustable='box')
    ax.axis('off')
    
    return fig


# --- 3. Gradio UI 布局与逻辑 ---

def build_app():
    with gr.Blocks(theme=gr.themes.Soft(), title="光谱Fitting助手") as app:
        
        # 存储解析后的数据
        app_state = gr.State({})

        gr.Markdown("# 半导体光谱Fitting应用演示")
        
        with gr.Row():
            # 左侧上传列
            with gr.Column(scale=1, min_width=200):
                gr.Markdown("### 上传区域")
                # 改为接受ZIP压缩包，更符合Gradio的上传机制
                spectra_upload = gr.File(label="1. 上传光谱文件夹 (ZIP格式)", file_types=[".zip"])
                film_stack_upload = gr.File(label="2. 上传Film Stack文件", file_types=[".csv", ".xlsx"])
                reference_upload = gr.File(label="3. 上传Reference文件 (可选)", file_types=[".csv"])
                
                # 添加一个按钮用于加载示例数据，方便用户测试
                load_example_btn = gr.Button("加载示例数据", variant="secondary")

            # 中间显示列
            with gr.Column(scale=4):
                gr.Markdown("### 光谱解析与可视化")
                with gr.Row():
                    # WaferID 可以附在Wafer1 下方加括号
                    wafer_selector = gr.Radio(label="选择Wafer", choices=["请先上传光谱数据"], interactive=True)
                    spec_selector = gr.Dropdown(label="选择光谱序号 (可高亮)", choices=["请先选择Wafer"], interactive=True)
                
                with gr.Row():
                    spectra_plot = gr.Plot(label="Spectra")
                    with gr.Column():
                        wafer_map_plot = gr.Plot(label="Wafer map")
                        spxy_map_plot = gr.Plot(label="SPXY map")
            
            # 右侧Film Stack列
            with gr.Column(scale=2, min_width=400):
                gr.Markdown("### Film Stack")
                film_stack_df = gr.DataFrame(
                    headers=["Mat", "THK", "Fitting", "Library", "Reg", "Name"],
                    datatype=["str", "number", "bool", "bool", "bool", "str"],
                    interactive=True,
                    label="薄膜结构"
                )

        # --- 4. 事件处理逻辑 ---
        
        def load_spectra_data(zip_file):
            """处理光谱数据上传的核心函数"""
            if zip_file is None:
                return {}, "请先上传光谱数据", None, None, None, None, None
                
            parsed_data, wafer_list, first_wafer, first_spec_list = parse_spectra_zip(zip_file)
            
            if not parsed_data:
                 return {}, "解析失败", None, None, None, None, None
            
            # 默认选择第一个wafer和第一个光谱
            selected_wafer_data = parsed_data.get(first_wafer, {})
            first_spec_id = first_spec_list[0] if first_spec_list else None
            
            # 更新所有相关的UI组件
            fig_spectra = plot_spectra(selected_wafer_data, first_spec_id)
            fig_wafer_map = plot_wafer_map(selected_wafer_data, first_spec_id, "Wafer map")
            fig_spxy_map = plot_wafer_map(selected_wafer_data, None, "SPXY map") # SPXY map的高亮是独立的

            return (
                parsed_data,
                gr.Radio(choices=wafer_list, value=first_wafer),
                gr.Dropdown(choices=first_spec_list, value=first_spec_id),
                fig_spectra,
                fig_wafer_map,
                fig_spxy_map
            )

        def change_wafer(wafer_id, state):
            """当用户切换Wafer时触发"""
            if not wafer_id or not state:
                return None, None, None, None
            
            wafer_data = state.get(wafer_id, {})
            spec_ids = wafer_data.get("ids", [])
            first_spec_id = spec_ids[0] if spec_ids else None

            fig_spectra = plot_spectra(wafer_data, first_spec_id)
            fig_wafer_map = plot_wafer_map(wafer_data, first_spec_id, "Wafer map")
            fig_spxy_map = plot_wafer_map(wafer_data, None, "SPXY map")

            return (
                gr.Dropdown(choices=spec_ids, value=first_spec_id),
                fig_spectra,
                fig_wafer_map,
                fig_spxy_map
            )

        def highlight_spectrum(spec_id, wafer_id, state):
            """当用户从下拉菜单选择光谱时触发"""
            if not all([spec_id, wafer_id, state]):
                return None, None
            
            wafer_data = state.get(wafer_id, {})
            fig_spectra = plot_spectra(wafer_data, spec_id)
            fig_wafer_map = plot_wafer_map(wafer_data, spec_id, "Wafer map")
            
            # SPXY map保持不变，因为它的高亮逻辑是独立的
            return fig_spectra, fig_wafer_map
        
        # 绑定上传事件
        spectra_upload.upload(
            fn=load_spectra_data,
            inputs=[spectra_upload],
            outputs=[app_state, wafer_selector, spec_selector, spectra_plot, wafer_map_plot, spxy_map_plot]
        )
        
        film_stack_upload.upload(
            fn=parse_film_stack,
            inputs=[film_stack_upload],
            outputs=[film_stack_df]
        )

        # 绑定UI组件变化事件
        wafer_selector.change(
            fn=change_wafer,
            inputs=[wafer_selector, app_state],
            outputs=[spec_selector, spectra_plot, wafer_map_plot, spxy_map_plot]
        )

        spec_selector.change(
            fn=highlight_spectrum,
            inputs=[spec_selector, wafer_selector, app_state],
            outputs=[spectra_plot, wafer_map_plot]
        )

        # 绑定示例数据加载按钮
        def load_example():
            dummy_zip = "dummy_data/dummy_spectra.zip"
            dummy_csv = "dummy_data/dummy_film_stack.csv"
            if not os.path.exists(dummy_zip) or not os.path.exists(dummy_csv):
                 raise gr.Error("示例文件不存在！请先运行 create_dummy_data() 函数。")

            film_df = parse_film_stack(gr.File(value=dummy_csv))
            
            # 模拟上传光谱数据
            parsed_data, wafer_list, first_wafer, first_spec_list = parse_spectra_zip(gr.File(value=dummy_zip))
            selected_wafer_data = parsed_data.get(first_wafer, {})
            first_spec_id = first_spec_list[0] if first_spec_list else None
            
            fig_spectra = plot_spectra(selected_wafer_data, first_spec_id)
            fig_wafer_map = plot_wafer_map(selected_wafer_data, first_spec_id, "Wafer map")
            fig_spxy_map = plot_wafer_map(selected_wafer_data, None, "SPXY map")
            
            return (
                film_df,
                parsed_data,
                gr.Radio(choices=wafer_list, value=first_wafer),
                gr.Dropdown(choices=first_spec_list, value=first_spec_id),
                fig_spectra,
                fig_wafer_map,
                fig_spxy_map
            )

        load_example_btn.click(
            fn=load_example,
            inputs=[],
            outputs=[film_stack_df, app_state, wafer_selector, spec_selector, spectra_plot, wafer_map_plot, spxy_map_plot]
        )

    return app


# --- 5. 运行App ---
if __name__ == "__main__":
    # 第一步：确保你已经生成了虚拟数据
    # 如果 dummy_data 文件夹不存在，就创建它
    if not os.path.exists("dummy_data"):
        create_dummy_data()

    # 第二步：启动Gradio应用
    my_app = build_app()
    my_app.launch()


####我在设计一个app，关于光谱fitting的。半导体行业量测光谱。我想用gradio实现下图的功能，请你给我代码。我来说一下下图的意思。左边是上传按钮，用户可以上传光谱batch（文件夹），film stack（厚度的结构，csv或者excel），reference（可选，csv）。然后中间是解析光谱文件夹的内容，具体来说就是一个文件夹里可能有几个文件夹（对应几个wafer，通常来说1-3片），相应的在中间show出来，waferID可以附在Wafer1 下方加括号，wafer前面给一个勾选框，或者点击，来表示选中这片wafer的光谱。同时底下会show出这片wafer上所有的光谱（三个信道）的光谱图。这里需要有一个功能，就是wafer那里有下拉框，你可以选择相应的光谱序号，选择了就在地下光谱图里highlight出来。同时光谱右边会显示两个东西，一个是wafer map，就是展示光谱的在wafer上的位置（点的上方要标序号）同时highlight出来你选的那根光谱的位置，一个是LPI-map，自动选择一个点，标红。上图最右边是对film stack的解析，表格的形式即可，材料和thk可以从csv里解析出来，后面有新家的四列，一个是fitting，library，reg，name。前三个用tick的框框表示是否浮动，name那里需要用户key in名字。