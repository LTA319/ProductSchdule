# 生产排程智能体

基于 Python + OR-Tools CP-SAT + Streamlit 的制造企业排程智能体原型。

## 快速开始

```bash
# 1. 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行
streamlit run src/app.py
```

## 项目结构

```
├── data/           # 示例数据
├── docs/           # PRD与搭建思路文档
├── src/
│   ├── models.py   # Pydantic数据模型
│   ├── data_loader.py  # Excel数据读取与校验
│   ├── scheduler.py    # OR-Tools排程引擎
│   ├── visualizer.py   # Plotly甘特图与KPI面板
│   └── app.py          # Streamlit主入口
└── tests/
```

## 技术栈

- **求解引擎**：Google OR-Tools CP-SAT
- **数据处理**：Pandas + openpyxl
- **Web界面**：Streamlit
- **可视化**：Plotly
- **数据校验**：Pydantic
