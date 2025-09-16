import gradio as gr

def load_data():
    # 注意：必须是 Python 原生 bool 类型
    data = [
        ["SiO2", 100, True, False, False, "SiO2"],
        ["SiN",  200, True, True, False, "SiN"],
        ["Poly", 150, False, True, True, "Poly"]
    ]
    return data

with gr.Blocks() as demo:
    film_stack_table = gr.Dataframe(
        headers=["Mat", "THK", "Fitting", "Library", "Reg", "Name"],
        datatype=["str", "number", "bool", "bool", "bool", "str"],
        label="Film Stack 表格",
        value=[], row_count=0, interactive=True
    )

    load_btn = gr.Button("加载测试数据")
    load_btn.click(fn=load_data, inputs=[], outputs=[film_stack_table])

demo.launch()