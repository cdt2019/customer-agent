"""造几份用来试导入的文件，写到 var/import-samples/：Word、文字型 PDF、GBK 的 TXT、HTML、没有文字的 PDF。

用法（在 server/ 下）：uv run --with python-docx --with reportlab python lab/make_import_samples.py
"""

from pathlib import Path

from docx import Document
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

OUT = Path(__file__).parents[2] / "var/import-samples"
TITLE = "导入测试手册"
SECTIONS = [
    ("质保范围", "紫藤计划的质保期从交付时间开始计算，不同商品的天数如下。"),
    ("申请流程", "在订单页点申请售后，选择类型并说明情况，紫藤计划的工单一般十二小时内回复。"),
    ("例外情况", "卡密已被使用且无法证明异常时，由客服核对后判断。"),
]
TABLE = [["商品", "质保", "补发次数"], ["Plus 月卡", "30 天", "2 次"], ["礼品卡", "未使用可换", "1 次"]]


def word(path: Path) -> None:
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


def pdf(path: Path) -> None:
    pdfmetrics.registerFont(TTFont("yahei", "C:/Windows/Fonts/msyh.ttc"))
    h1, h2 = ParagraphStyle("h1", fontName="yahei", fontSize=20, leading=30), ParagraphStyle("h2", fontName="yahei", fontSize=14, leading=26)
    body = ParagraphStyle("body", fontName="yahei", fontSize=10.5, leading=18)
    flow = [Paragraph(TITLE + " PDF 版", h1)]
    for n, (heading, text) in enumerate(SECTIONS):
        flow += [Paragraph(heading, h2), Paragraph(text, body)]
        if n == 0:
            flow.append(Table(TABLE, style=TableStyle([("FONTNAME", (0, 0), (-1, -1), "yahei"), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)])))
    SimpleDocTemplate(str(path), pagesize=A4).build(flow)


def blank_pdf(path: Path) -> None:
    page = canvas.Canvas(str(path), pagesize=A4)
    page.setFillGray(0.8)
    page.rect(80, 300, 430, 400, fill=1)  # 只有图形，没有文字层，相当于扫描件
    page.showPage()
    page.save()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    word(OUT / "导入测试手册.docx")
    pdf(OUT / "导入测试手册.pdf")
    blank_pdf(OUT / "扫描件.pdf")
    (OUT / "GBK说明.txt").write_bytes("这是一份 GBK 编码的说明文字，紫藤计划的客服工作时间是早九点到晚十一点。".encode("gbk"))
    (OUT / "网页说明.html").write_text("<html><body><h1>网页说明</h1><p>紫藤计划也支持 HTML 文件导入，脚本不会运行。</p><script>alert(1)</script></body></html>", encoding="utf-8")
    print(sorted(p.name for p in OUT.iterdir()))
