当然可以！您的想法非常好，使用交互式图表库是提升这类应用用户体验的关键。用鼠标悬停显示数据点信息的功能，最适合的库是 **Plotly**。

Gradio 对 Plotly 有内置的良好支持，我们只需要做两处核心修改：

1.  将 `matplotlib` 的绘图函数 `plot_spectra` 替换为使用 `plotly` 的版本。
2.  在 Gradio 的界面定义中，将 `gr.Plot` 组件换成 `gr.Plotly` 组件。

使用 Plotly 的好处是：

  * **原生交互性**：支持缩放、平移和悬停（hover）提示，无需额外插件。
  * **信息丰富的提示框**：你可以自定义鼠标悬停时显示的内容，比如波长、强度、光谱序号等。
  * **美观现代**：图表外观非常专业和现代化。

下面是修改后的完整代码。

-----

### 修改后的完整 Gradio 代码 (使用 Plotly)

我已经将原代码中的 `plot_spectra` 函数完全重写，并更新了UI部分。其他函数（如数据生成和文件解析）保持不变。

```python
import gradio as gr
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt # 仍然用于Wafer Map
# MODIFIED: 导入Plotly库
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import zipfile
import tempfile
import shutil
from pathlib import Path

# --- 1. 数据生成函数 (与之前相同) ---
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
                'X': [x_coords[j-1]] * 300, 
                'Y': [y_coords[j-1]] * 300
            })
            spec_df.to_csv(wafer_dir / spec_name, index=False)

    shutil.make_archive(dummy_dir / "dummy_spectra", 'zip', spectra_dir)
    print(f"已创建虚拟光谱ZIP包: {dummy_dir / 'dummy_spectra.zip'}")
    print("虚拟数据创建完成！")


# --- 2. 后端处理函数 ---

# parse_film_stack 和 parse_spectra_zip 函数与之前相同
def parse_film_stack(file):
    if file is None: return None
    try:
        df = pd.read_csv(file.name) if file.name.endswith('.csv') else pd.read_excel(file.name)
        df['Fitting'], df['Library'], df['Reg'], df['Name'] = True, False, False, ''
        return df[['Mat', 'THK', 'Fitting', 'Library', 'Reg', 'Name']]
    except Exception as e: raise gr.Error(f"解析Film Stack文件失败: {e}")

def parse_spectra_zip(zip_path):
    if zip_path is None: return {}, [], "请先上传光谱数据", "请先上传光谱数据"
    parsed_data = {}
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            with zipfile.ZipFile(zip_path.name, 'r') as z: z.extractall(temp_dir)
        except Exception as e: raise gr.Error(f"解压ZIP文件失败: {e}")
        search_path = Path(temp_dir)
        wafer_dirs = sorted([d for d in search_path.iterdir() if d.is_dir()])
        if not wafer_dirs: raise gr.Error("ZIP包中未找到Wafer文件夹。")
        for wafer_dir in wafer_dirs:
            wafer_id, spec_files = wafer_dir.name, sorted([f for f in wafer_dir.glob('*.csv')])
            if not spec_files: continue
            wafer_data = {"ids": [], "coords": [], "spectra_data": []}
            for i, spec_file in enumerate(spec_files):
                try:
                    df = pd.read_csv(spec_file)
                    wafer_data["ids"].append(f"序号 {i+1} ({spec_file.name})")
                    wafer_data["coords"].append((df['X'].iloc[0], df['Y'].iloc[0]))
                    wafer_data["spectra_data"].append(df)
                except Exception: continue
            if wafer_data["ids"]: parsed_data[wafer_id] = wafer_data
    if not parsed_data: raise gr.Error("解析光谱数据失败。")
    wafer_list = list(parsed_data.keys())
    return parsed_data, wafer_list, wafer_list[0], parsed_data[wafer_list[0]]["ids"]


# MODIFIED: 使用Plotly重写光谱绘图函数
def plot_spectra_plotly(wafer_data, highlight_id):
    """使用Plotly绘制交互式光谱图"""
    if not wafer_data or not highlight_id:
        # 返回一个空的Plotly figure对象
        return go.Figure().update_layout(
            title_text="请选择Wafer和光谱", 
            xaxis_visible=False, 
            yaxis_visible=False,
            annotations=[dict(text="无数据显示", xref="paper", yref="paper", showarrow=False, font=dict(size=20))]
        )
    
    # 创建带3个子图的figure
    fig = make_subplots(
        rows=3, cols=1, 
        shared_xaxes=True, 
        subplot_titles=('Channel 1', 'Channel 2', 'Channel 3'),
        vertical_spacing=0.1
    )

    try:
        highlight_idx = wafer_data['ids'].index(highlight_id)
    except ValueError:
        highlight_idx = -1

    # 遍历所有光谱数据并添加到图中
    for i, (spec_id, df) in enumerate(zip(wafer_data['ids'], wafer_data['spectra_data'])):
        is_highlight = (i == highlight_idx)
        
        # 定义线条样式
        line_style = dict(width=4) if is_highlight else dict(width=1.5)
        opacity = 1.0 if is_highlight else 0.4
        
        # 为每个通道添加一条轨迹(trace)
        for ch_idx, channel in enumerate(['Channel1', 'Channel2', 'Channel3']):
            fig.add_trace(go.Scatter(
                x=df['Wavelength'],
                y=df[channel],
                mode='lines',
                line=line_style,
                opacity=opacity,
                name=spec_id if is_highlight else None, # 只为高亮的光谱显示图例
                legendgroup=f"group_{i}", # 让3个通道的图例联动
                showlegend=is_highlight and (ch_idx==0), # 只为第一个通道显示图例
                # 这是核心：自定义悬停信息
                hovertemplate=(
                    f"<b>{spec_id}</b><br>"
                    "Wavelength: %{x:.2f} nm<br>"
                    f"{channel}: %{{y:.4f}}<extra></extra>" # <extra></extra> 隐藏多余信息
                )
            ), row=ch_idx + 1, col=1)

    # 更新整体布局
    fig.update_layout(
        title_text=f"光谱图 (高亮: {highlight_id})",
        height=600,
        # margin=dict(l=20, r=20, t=50, b=20),
        xaxis3_title="Wavelength (nm)", # 只显示最下面X轴的标题
        legend_title="Selected Spectrum"
    )
    
    return fig

# Wafer Map 仍然使用 Matplotlib，因为它不需要交互
def plot_wafer_map(wafer_data, highlight_id, title):
    if not wafer_data: return None
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.set_title(title)
    ax.add_artist(plt.Circle((0, 0), 150, color='lightblue', alpha=0.2))
    coords = wafer_data['coords']
    x, y = [c[0] for c in coords], [c[1] for c in coords]
    ax.scatter(x, y, color='black', s=50)
    for i, (xi, yi) in enumerate(coords):
        ax.text(xi, yi + 5, str(i + 1), ha='center', va='bottom', fontsize=8)
    if title == 'SPXY map' and len(coords) > 2:
        lpi_idx = 2 
        ax.scatter(coords[lpi_idx][0], coords[lpi_idx][1], color='red', s=100, zorder=10, edgecolors='black', label=f'Auto Point {lpi_idx+1}')
        ax.legend()
    if title == 'Wafer map' and highlight_id:
        try:
            highlight_idx = wafer_data['ids'].index(highlight_id)
            ax.scatter(coords[highlight_idx][0], coords[highlight_idx][1], color='gold', s=100, zorder=10, edgecolors='black', label=f'Selected Point {highlight_idx+1}')
            ax.legend()
        except (ValueError, IndexError): pass
    ax.set_xlim(-160, 160); ax.set_ylim(-160, 160)
    ax.set_aspect('equal', adjustable='box'); ax.axis('off')
    return fig

# --- 3. Gradio UI 布局与逻辑 ---

def build_app():
    with gr.Blocks(theme=gr.themes.Soft(), title="光谱Fitting助手") as app:
        app_state = gr.State({})
        gr.Markdown("# 半导体光谱Fitting应用演示")
        with gr.Row():
            with gr.Column(scale=1, min_width=200):
                gr.Markdown("### 上传区域")
                spectra_upload = gr.File(label="1. 上传光谱文件夹 (ZIP格式)", file_types=[".zip"])
                film_stack_upload = gr.File(label="2. 上传Film Stack文件", file_types=[".csv", ".xlsx"])
                reference_upload = gr.File(label="3. 上传Reference文件 (可选)", file_types=[".csv"])
                load_example_btn = gr.Button("加载示例数据", variant="secondary")
            with gr.Column(scale=4):
                gr.Markdown("### 光谱解析与可视化")
                with gr.Row():
                    wafer_selector = gr.Radio(label="选择Wafer", choices=["请先上传光谱数据"], interactive=True)
                    spec_selector = gr.Dropdown(label="选择光谱序号 (可高亮)", choices=["请先选择Wafer"], interactive=True)
                with gr.Row():
                    # MODIFIED: 使用 gr.Plotly 替代 gr.Plot
                    spectra_plot = gr.Plotly(label="Spectra")
                    with gr.Column():
                        wafer_map_plot = gr.Plot(label="Wafer map")
                        spxy_map_plot = gr.Plot(label="SPXY map")
            with gr.Column(scale=2, min_width=400):
                gr.Markdown("### Film Stack")
                film_stack_df = gr.DataFrame(
                    headers=["Mat", "THK", "Fitting", "Library", "Reg", "Name"],
                    datatype=["str", "number", "bool", "bool", "bool", "str"],
                    interactive=True, label="薄膜结构"
                )

        # --- 4. 事件处理逻辑 (函数调用关系不变) ---
        def load_spectra_data(zip_file):
            if zip_file is None: return {}, "请先上传光谱数据", None, None, None, None, None
            parsed_data, wafer_list, first_wafer, first_spec_list = parse_spectra_zip(zip_file)
            if not parsed_data: return {}, "解析失败", None, None, None, None, None
            selected_wafer_data = parsed_data.get(first_wafer, {})
            first_spec_id = first_spec_list[0] if first_spec_list else None
            # MODIFIED: 调用新的Plotly绘图函数
            fig_spectra = plot_spectra_plotly(selected_wafer_data, first_spec_id)
            fig_wafer_map = plot_wafer_map(selected_wafer_data, first_spec_id, "Wafer map")
            fig_spxy_map = plot_wafer_map(selected_wafer_data, None, "SPXY map")
            return (parsed_data, gr.Radio(choices=wafer_list, value=first_wafer), gr.Dropdown(choices=first_spec_list, value=first_spec_id), fig_spectra, fig_wafer_map, fig_spxy_map)

        def change_wafer(wafer_id, state):
            if not wafer_id or not state: return None, None, None, None
            wafer_data = state.get(wafer_id, {})
            spec_ids = wafer_data.get("ids", [])
            first_spec_id = spec_ids[0] if spec_ids else None
            fig_spectra = plot_spectra_plotly(wafer_data, first_spec_id)
            fig_wafer_map = plot_wafer_map(wafer_data, first_spec_id, "Wafer map")
            fig_spxy_map = plot_wafer_map(wafer_data, None, "SPXY map")
            return (gr.Dropdown(choices=spec_ids, value=first_spec_id), fig_spectra, fig_wafer_map, fig_spxy_map)

        def highlight_spectrum(spec_id, wafer_id, state):
            if not all([spec_id, wafer_id, state]): return None, None
            wafer_data = state.get(wafer_id, {})
            fig_spectra = plot_spectra_plotly(wafer_data, spec_id)
            fig_wafer_map = plot_wafer_map(wafer_data, spec_id, "Wafer map")
            return fig_spectra, fig_wafer_map
        
        # 事件绑定关系与之前相同
        spectra_upload.upload(fn=load_spectra_data, inputs=[spectra_upload], outputs=[app_state, wafer_selector, spec_selector, spectra_plot, wafer_map_plot, spxy_map_plot])
        film_stack_upload.upload(fn=parse_film_stack, inputs=[film_stack_upload], outputs=[film_stack_df])
        wafer_selector.change(fn=change_wafer, inputs=[wafer_selector, app_state], outputs=[spec_selector, spectra_plot, wafer_map_plot, spxy_map_plot])
        spec_selector.change(fn=highlight_spectrum, inputs=[spec_selector, wafer_selector, app_state], outputs=[spectra_plot, wafer_map_plot])
        
        def load_example():
            dummy_zip, dummy_csv = "dummy_data/dummy_spectra.zip", "dummy_data/dummy_film_stack.csv"
            if not os.path.exists(dummy_zip) or not os.path.exists(dummy_csv): raise gr.Error("示例文件不存在！请先运行 create_dummy_data()。")
            film_df = parse_film_stack(gr.File(value=dummy_csv))
            parsed_data, wafer_list, first_wafer, first_spec_list = parse_spectra_zip(gr.File(value=dummy_zip))
            selected_wafer_data = parsed_data.get(first_wafer, {})
            first_spec_id = first_spec_list[0] if first_spec_list else None
            fig_spectra = plot_spectra_plotly(selected_wafer_data, first_spec_id)
            fig_wafer_map = plot_wafer_map(selected_wafer_data, first_spec_id, "Wafer map")
            fig_spxy_map = plot_wafer_map(selected_wafer_data, None, "SPXY map")
            return (film_df, parsed_data, gr.Radio(choices=wafer_list, value=first_wafer), gr.Dropdown(choices=first_spec_list, value=first_spec_id), fig_spectra, fig_wafer_map, fig_spxy_map)
        load_example_btn.click(fn=load_example, inputs=[], outputs=[film_stack_df, app_state, wafer_selector, spec_selector, spectra_plot, wafer_map_plot, spxy_map_plot])

    return app

# --- 5. 运行App ---
if __name__ == "__main__":
    if not os.path.exists("dummy_data"):
        create_dummy_data()
    my_app = build_app()
    my_app.launch()

```

### 如何运行新版本

1.  **安装Plotly**：如果您的环境中没有安装 `plotly`，请先安装它。

    ```bash
    pip install plotly
    ```

    您可能也需要 `kaleido` 来支持静态图片的导出，虽然在这个应用中不是必须的，但安装上没有坏处。

    ```bash
    pip install kaleido
    ```

2.  **保存并运行代码**：将以上代码保存为 `.py` 文件并运行。

    ```bash
    python your_app_name.py
    ```

3.  **体验交互功能**：

      * 打开浏览器中的Gradio应用。
      * 加载示例数据。
      * 现在，当您将鼠标移动到光谱图上时，会**自动出现一个提示框**，显示该点的详细信息（光谱序号、波长、强度），正如您所期望的那样。
      * 您还可以使用图表右上角的工具栏进行**缩放**和**平移**，以便更仔细地检查光谱的细节。