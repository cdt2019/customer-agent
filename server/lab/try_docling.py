"""试 Docling：把一篇中文帮助文章做成 Word 和文字型 PDF，再解析回 Markdown，看标题、表格、中文保住没有。

用法（在 server/ 下）：
  uv run --with docling --with python-docx --with reportlab python lab/try_docling.py
样例和解析结果写到 var/samples/。只用处理器，不开 OCR。
"""

import time
from pathlib import Path

from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docx import Document
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

OUT = Path(__file__).parents[2] / "var/samples"
TITLE = "售后处理手册"
SECTIONS = [
    ("质保范围", "质保期从交付时间开始计算。不同商品的质保天数如下，下单时页面会明确显示。"),
    ("申请流程", "在订单页点「申请售后」，选择类型并说明情况，可以附 3 张截图。USDT 付款的请附上交易哈希。"),
    ("不在质保内的情况", "卡密已被使用且无法证明异常时，由客服核对后判断。违反 OpenAI 使用规则被封号不在质保范围。"),
]
TABLE = [["商品", "质保", "补发次数"], ["Plus 月卡", "30 天", "2 次"], ["Go 月卡", "30 天", "2 次"], ["礼品卡", "未使用可换", "1 次"]]


def make_docx(path: Path) -> None:
    doc = Document()
    doc.add_heading(TITLE, level=1)
    for n, (heading, text) in enumerate(SECTIONS):
        doc.add_heading(heading, level=2)
        doc.add_paragraph(text)
        if n == 0:
            table = doc.add_table(rows=len(TABLE), cols=3)
            for r, row in enumerate(TABLE):
                for c, cell in enumerate(row):
                    table.cell(r, c).text = cell
    doc.save(path)


def make_pdf(path: Path) -> None:
    pdfmetrics.registerFont(TTFont("yahei", "C:/Windows/Fonts/msyh.ttc"))
    h1 = ParagraphStyle("h1", fontName="yahei", fontSize=20, leading=30)
    h2 = ParagraphStyle("h2", fontName="yahei", fontSize=14, leading=26)
    body = ParagraphStyle("body", fontName="yahei", fontSize=10.5, leading=18)
    flow = [Paragraph(TITLE, h1)]
    for n, (heading, text) in enumerate(SECTIONS):
        flow += [Paragraph(heading, h2), Paragraph(text, body)]
        if n == 0:
            flow.append(Table(TABLE, style=TableStyle([("FONTNAME", (0, 0), (-1, -1), "yahei"), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)])))
    SimpleDocTemplate(str(path), pagesize=A4).build(flow)


def check(markdown: str) -> dict:
    return {
        "标题": sum(h in markdown for h in [TITLE] + [s[0] for s in SECTIONS]),
        "标题带#": sum(line.startswith("#") for line in markdown.splitlines()),
        "表格行": sum(line.startswith("|") for line in markdown.splitlines()),
        "单元格": sum(cell in markdown for row in TABLE for cell in row),
        "正文句": sum(s[1][:12] in markdown for s in SECTIONS),
    }


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    make_docx(OUT / "sample.docx")
    make_pdf(OUT / "sample.pdf")
    pdf = PdfPipelineOptions(do_ocr=False, accelerator_options=AcceleratorOptions(device="cpu"))
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf)})
    print("期望：标题 4，表格行 5，单元格 12，正文句 3")
    for name in ("sample.docx", "sample.pdf", "sample.pdf"):  # PDF 跑两次：第一次含加载模型
        start = time.perf_counter()
        markdown = converter.convert(OUT / name).document.export_to_markdown()
        (OUT / f"{name}.md").write_text(markdown, encoding="utf-8")
        print(name, f"{time.perf_counter() - start:.1f}s", check(markdown))
