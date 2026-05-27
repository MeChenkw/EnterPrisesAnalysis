# 求职企业速查

一键输入企业名称，DeepSeek 联网搜索中文互联网信息，自动生成多维度企业分析报告。

## 功能

- **业务范围分析**：主营业务、服务领域、收入来源
- **主要客户分析**：目标客户群体、行业分布
- **核心产品与竞品**：产品矩阵、竞争格局
- **近三年经营情况**：发展趋势、营收估算、融资/上市动态
- **员工评价与应聘须知**：口碑、薪资水平、面试经验、注意事项

## 技术栈

- 后端：Python 3.12 + Flask
- AI：DeepSeek API（deepseek-v4-flash）
- 搜索引擎：DeepSeek 内置联网搜索
- 前端：原生 HTML/CSS/JS + Jinja2 模板

## 快速开始

```bash
# 1. 进入项目目录
cd EnterPrisesAnalysis

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置 API 密钥
echo "OPENAI_API_KEY=your-deepseek-api-key" > .env

# 5. 启动服务
python3 app.py
```

访问 http://localhost:5099

## 目录结构

```
EnterPrisesAnalysis/
├── app.py              # Flask 主入口
├── analyzer.py         # 分析引擎，调用 DeepSeek 分析五维度
├── searcher.py         # 搜索模块
├── analyzer_prompt.py  # 提示词配置
├── file_writer.py      # 文件写入工具
├── templates/          # Jinja2 模板
├── static/             # 静态资源
├── requirements.txt    # Python 依赖
└── .env                # API 密钥（已排除，不提交）
```

## 分析示例

输入"海信星海科技"等企业名称，即可获得详细的薪资、文化、面试等维度的分析报告。

## License

MIT
