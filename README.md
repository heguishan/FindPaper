# FindPaper

FindPaper 是一个 Python 3.9+ 本地 Web 应用，用于按主题检索开放学术文献、下载可合法访问的 PDF，并筛选高质量论文。

## 功能

- 输入主题/关键词并设置目标下载数量。
- 上传论文 PDF 时，从 `Abstract` 段落提取关键词作为检索主题。
- 使用 OpenAlex、Crossref、Semantic Scholar、Unpaywall 和 arXiv 等开放来源。
- 只下载开放访问 PDF，不绕过付费墙。
- 生成普通 PDF 目录、高质量论文目录、不可下载论文报告和全部候选 CSV。

## 安装

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

可选创建 `.env`：

```env
CONTACT_EMAIL=your-email@example.com
SEMANTIC_SCHOLAR_API_KEY=
DEFAULT_OUTPUT_DIR=downloads
```

## 运行

```bash
uvicorn app.main:app --reload
```

浏览器打开：

```text
http://127.0.0.1:8000
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

```bash
pip install -r requirements-dev.txt
pytest
```

