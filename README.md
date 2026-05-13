# FindPaper

FindPaper 是一个 Python 3.9+ 本地 Web 应用，用于按主题检索开放学术文献、下载可合法访问的 PDF，并筛选高质量论文。

## 功能

- 输入主题/关键词并设置目标下载数量。
- 上传论文 PDF 时，从 `Abstract` 段落提取关键词作为检索主题。
- 使用 OpenAlex、Crossref、Semantic Scholar、Unpaywall 和 arXiv 等开放来源。
- 只下载开放访问 PDF，不绕过付费墙。
- 生成普通 PDF 目录、高质量论文目录、不可下载论文报告和全部候选 CSV。

## 项目结构

```text
FindPaper/
  app/                    # FastAPI 后端、检索、下载、评分、报告逻辑
    static/               # 本地 Web 页面
  tests/                  # 单元测试
  .vscode/                # VSCode 运行、测试、调试配置
  .env.example            # 环境变量示例
  requirements.txt        # 运行依赖
  requirements-dev.txt    # 测试依赖
  pyproject.toml          # 项目元数据和测试配置
```

本地运行产生的 `.venv/`、`downloads/`、`findpaper.egg-info/`、`__pycache__/` 已在 `.gitignore` 中排除，不会推送到 GitHub。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
```

可选复制 `.env.example` 为 `.env`，并填写联系邮箱：

```env
CONTACT_EMAIL=your-email@example.com
SEMANTIC_SCHOLAR_API_KEY=
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
ENABLE_LLM_TOPIC_EXTRACTION=true
DEFAULT_OUTPUT_DIR=downloads
```

`DEEPSEEK_API_KEY` 配置后，上传 PDF 时程序会默认调用 DeepSeek：

- 从 PDF 前几页文本中识别 `Abstract / 摘要`
- 将专业术语转换为更适合学术数据库检索的英文关键词
- 生成多组检索查询，提高 OpenAlex、Semantic Scholar、arXiv、Crossref 的命中率

如果未配置 `DEEPSEEK_API_KEY`，程序会自动退回本地规则提取。

## 使用 VSCode

1. 用 VSCode 打开项目目录 `D:\Project_AI\FindPaper`。
2. 选择解释器：`.venv\Scripts\python.exe`。项目已在 `.vscode/settings.json` 中默认指定。
3. 运行服务：
   - 按 `Ctrl+Shift+P`
   - 输入 `Tasks: Run Task`
   - 选择 `Run FindPaper`
4. 或进入“运行和调试”，选择 `FindPaper: FastAPI`。
5. 浏览器打开 `http://127.0.0.1:8000`。

## 命令行运行

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 输出

假设主题为 `large language model`，输出目录为 `downloads`：

```text
downloads/
  large language model/
    *.pdf
    reports/
      all_papers.csv
      unavailable_papers.csv
      unavailable_papers.md
      high_quality_papers.md
  large language model高质量/
    *.pdf
```

## 测试

在 VSCode 中运行任务 `Run tests`，或使用命令：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## 推送到 GitHub

如果 VSCode 源代码管理面板显示有变更：

1. 打开左侧“源代码管理”。
2. 确认待提交文件不包含 `.venv/`、`downloads/`、`findpaper.egg-info/`。
3. 输入提交信息，例如 `Prepare project for VSCode and GitHub`。
4. 点击“提交”。
5. 如果尚未配置远程仓库，在 VSCode 终端运行：

```powershell
git branch -M main
git remote add origin https://github.com/heguishan/FindPaper.git
git push -u origin main
```

如果 `origin` 已存在：

```powershell
git remote set-url origin https://github.com/heguishan/FindPaper.git
git push -u origin main
```
