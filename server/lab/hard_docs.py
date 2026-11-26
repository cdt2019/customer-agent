"""造两份版式复杂的文件（双栏 PDF、带合并单元格和嵌套表格的 Word），用每个可选的解析器解析，逐项检查：
阅读顺序、段落有没有被拆散、页眉页脚有没有混进正文、跨页长表的行齐不齐、合并单元格、标题层级。

文件是脚本生成的，不是真实资料；真实的扫描件、手写批注、图片里的字这里测不到。
用法（在 server/ 下）：uv run --with reportlab python lab/hard_docs.py
文件和解析结果写到 var/lab/hard-docs/。
"""

import re
import time
from pathlib import Path

from docx import Document
from docx.enum.text import WD_BREAK
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Table, TableStyle

from customer_agent import settings
from customer_agent.rag.parsers import PARSERS

OUT = settings.ROOT / "var/lab/hard-docs"
HEADER = "示例商店售后手册 · 内部资料"
TOPICS = ["付款", "到货", "兑换", "质保", "补发", "退款", "封号", "工单", "邮件", "合伙人", "佣金", "提现", "发票", "隐私", "客服时间", "批量采购"]
# 每段一句能单独认出来的话：段落编号写在开头，检查顺序和有没有被拆开
PARAGRAPHS = [
    f"（段{n:02d}）关于{topic}：买家在订单页可以看到{topic}的当前状态，遇到问题先按帮助文章里的步骤自查，"
    f"超过资料写的等待时间仍未解决再联系客服，客服会在工单里回复处理结果，并说明下一步需要买家做什么。"
    for n, topic in enumerate(TOPICS, 1)
]
LONG_ROWS = [[f"SKU-{n:03d}", f"商品 {n}", f"{(n % 5 + 1) * 7} 天", f"{n % 3 + 1} 次", "自动发货" if n % 2 else "人工交付"] for n in range(1, 61)]
LONG_HEAD = ["编号", "商品", "质保", "补发次数", "交付方式"]
MERGED = [["类型", "情况", "处理"], ["卡密", "未使用", "可退"], ["", "已使用", "按质保处理"], ["账号", "能登录", "不退"], ["", "被封", "转人工核实"]]


def norm(text: str) -> str:
    return re.sub(r"\s+", "", text)


# ---------- 造文件 ----------


def make_pdf(path: Path) -> None:
    pdfmetrics.registerFont(TTFont("yahei", "C:/Windows/Fonts/msyh.ttc"))
    h1 = ParagraphStyle("h1", fontName="yahei", fontSize=18, leading=26, spaceAfter=8)
    h2 = ParagraphStyle("h2", fontName="yahei", fontSize=13, leading=20, spaceBefore=6, spaceAfter=4)
    body = ParagraphStyle("body", fontName="yahei", fontSize=9.5, leading=15, spaceAfter=6)
    width, height = A4
    margin, gap = 50, 18
    column = (width - 2 * margin - gap) / 2

    def chrome(canvas, doc):
        canvas.saveState()
        canvas.setFont("yahei", 8)
        canvas.drawString(margin, height - 30, HEADER)
        canvas.drawRightString(width - margin, 25, f"第 {doc.page} 页")
        canvas.restoreState()

    two = [Frame(margin, margin, column, height - 2 * margin, id="left"), Frame(margin + column + gap, margin, column, height - 2 * margin, id="right")]
    one = [Frame(margin, margin, width - 2 * margin, height - 2 * margin, id="full")]
    doc = BaseDocTemplate(str(path), pagesize=A4, pageTemplates=[PageTemplate("two", two, onPage=chrome), PageTemplate("one", one, onPage=chrome)])
    grid = [("FONTNAME", (0, 0), (-1, -1), "yahei"), ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]
    flow = [Paragraph("售后处理手册（双栏版）", h1)]
    for n, text in enumerate(PARAGRAPHS):
        if n % 4 == 0:
            flow.append(Paragraph(f"第 {n // 4 + 1} 部分", h2))
        flow.append(Paragraph(text, body))
    flow += [NextPageTemplate("one"), PageBreak(), Paragraph("附表一：商品质保和补发次数", h2)]
    flow.append(Table([LONG_HEAD, *LONG_ROWS], repeatRows=1, style=TableStyle([*grid, ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)])))
    flow.append(Paragraph("附表二：退款规则（合并单元格）", h2))
    flow.append(Table(MERGED, style=TableStyle([*grid, ("SPAN", (0, 1), (0, 2)), ("SPAN", (0, 3), (0, 4)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")])))
    doc.build(flow)


def make_docx(path: Path) -> None:
    doc = Document()
    section = doc.sections[0]
    section.header.paragraphs[0].text = HEADER
    section.footer.paragraphs[0].text = "页脚：仅供客服内部使用"
    doc.add_heading("售后处理手册（Word 版）", level=1)
    for n, text in enumerate(PARAGRAPHS):
        if n % 8 == 0:
            doc.add_heading(f"第 {n // 8 + 1} 章", level=2)
        if n % 4 == 0:
            doc.add_heading(f"第 {n // 4 + 1} 节", level=3)
        doc.add_paragraph(text)
    doc.add_heading("申请售后的步骤", level=2)
    for step in ["打开订单页", "点「申请售后」", "选择问题类型并说明情况", "等待客服在工单里回复"]:
        doc.add_paragraph(step, style="List Number")
    doc.paragraphs[-1].add_run().add_break(WD_BREAK.PAGE)
    doc.add_heading("附表一：商品质保和补发次数", level=2)
    table = doc.add_table(rows=1 + len(LONG_ROWS), cols=len(LONG_HEAD), style="Table Grid")
    for r, row in enumerate([LONG_HEAD, *LONG_ROWS]):
        for c, value in enumerate(row):
            table.cell(r, c).text = value
    doc.add_heading("附表二：退款规则（合并单元格）", level=2)
    merged = doc.add_table(rows=len(MERGED), cols=3, style="Table Grid")
    for r, row in enumerate(MERGED):
        for c, value in enumerate(row):
            if value:
                merged.cell(r, c).text = value
    merged.cell(1, 0).merge(merged.cell(2, 0))
    merged.cell(3, 0).merge(merged.cell(4, 0))
    doc.add_heading("附表三：表格里套表格", level=2)
    outer = doc.add_table(rows=1, cols=2, style="Table Grid")
    outer.cell(0, 0).text = "礼品卡地区"
    inner = outer.cell(0, 1).add_table(rows=2, cols=2)
    for r, row in enumerate([["美区", "可兑换"], ["国区", "不可兑换"]]):
        for c, value in enumerate(row):
            inner.cell(r, c).text = value
    doc.save(path)


# ---------- 检查 ----------


def check(markdown: str, headings: list[tuple[int, str]]) -> dict:
    flat = norm(markdown)
    positions = [flat.find(norm(p)) for p in PARAGRAPHS]
    intact = [pos >= 0 for pos in positions]
    tags = [flat.find(f"（段{n:02d}）") for n in range(1, len(PARAGRAPHS) + 1)]
    found = [t for t in tags if t >= 0]
    in_order = sum(a < b for a, b in zip(found, found[1:])) + 1 if found else 0
    rows_found = sum(norm(row[0]) in flat for row in LONG_ROWS)
    rows_whole = sum(bool(re.search(r"\|\s*" + re.escape(row[0]) + r"\s*\|\s*" + re.escape(row[1]) + r"\s*\|\s*" + re.escape(row[2]), markdown)) for row in LONG_ROWS)
    lines = markdown.splitlines()
    heading_ok = sum(any(line.strip() == "#" * level + " " + text for line in lines) for level, text in headings)
    heading_any = sum(any(line.lstrip("#").strip() == text and line.startswith("#") for line in lines) for _, text in headings)
    return {
        "段落完整": f"{sum(intact)}/{len(PARAGRAPHS)}",
        "段落顺序对": f"{in_order}/{len(found)}",
        "页眉混进正文": markdown.count("内部资料"),
        "页脚或页码混进正文": len(re.findall(r"第 ?\d+ ?页|页脚", markdown)),
        "长表的行在": f"{rows_found}/{len(LONG_ROWS)}",
        "长表的行是完整一行": f"{rows_whole}/{len(LONG_ROWS)}",
        "长表表头出现次数": len(re.findall(r"\|\s*编号\s*\|\s*商品\s*\|", markdown)),
        "合并单元格的值在": all(norm(v) in flat for row in MERGED for v in row if v),
        "嵌套表格的值在": all(norm(v) in flat for v in ["美区", "可兑换", "国区", "不可兑换"]),
        "标题找到（任意级别）": f"{heading_any}/{len(headings)}",
        "标题级别也对": f"{heading_ok}/{len(headings)}",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pdf, docx = OUT / "双栏手册.pdf", OUT / "复杂表格手册.docx"
    make_pdf(pdf)
    make_docx(docx)
    pdf_headings = [(1, "售后处理手册（双栏版）"), *[(2, f"第 {n} 部分") for n in range(1, 5)], (2, "附表一：商品质保和补发次数"), (2, "附表二：退款规则（合并单元格）")]
    docx_headings = [
        (1, "售后处理手册（Word 版）"),
        *[(2, f"第 {n} 章") for n in range(1, 3)],
        *[(3, f"第 {n} 节") for n in range(1, 5)],
        (2, "申请售后的步骤"),
        (2, "附表一：商品质保和补发次数"),
        (2, "附表二：退款规则（合并单元格）"),
        (2, "附表三：表格里套表格"),
    ]
    for path, headings in [(pdf, pdf_headings), (docx, docx_headings)]:
        for parser in PARSERS[path.suffix]:
            started = time.perf_counter()
            markdown = parser.parse(path)
            took = time.perf_counter() - started
            (OUT / f"{path.stem}.{parser.name}.md").write_text(markdown, encoding="utf-8")
            print(f"\n{path.name}（{path.stat().st_size // 1024} KB）用 {parser.label} 解析 {took:.1f} 秒，{len(markdown)} 字")
            for key, value in check(markdown, headings).items():
                print(f"  {key}：{value}")
    print(f"\n解析结果：{OUT}")


if __name__ == "__main__":
    main()
