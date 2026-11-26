"""解析：把一个文件变成 Markdown。PARSERS 按后缀列出能用的解析器，第一个是默认；每个解析器是 文件路径 -> Markdown 的函数。"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path


def plain(path: Path) -> str:
    """中文文本文件常见 UTF-8 和 GBK 两种编码。"""
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("gb18030")
    return text.replace("\r\n", "\n")


@cache
def _docling():
    # 导入很慢，用到时才加载。只用处理器、不开 OCR：显卡留给向量模型，扫描件第一版不支持。
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pdf = PdfPipelineOptions(do_ocr=False, accelerator_options=AcceleratorOptions(device="cpu"))
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf)})


def docling(path: Path) -> str:
    return _docling().convert(path).document.export_to_markdown()


def pdf_text(path: Path) -> str:
    """只取 PDF 的文字层，按页拼起来：快，但不认标题、表格和多栏，页眉页脚也会留着。"""
    import pypdfium2

    pdf = pypdfium2.PdfDocument(path)
    try:
        pages = [pdf[n].get_textpage().get_text_range().replace("\r\n", "\n").strip() for n in range(len(pdf))]
    finally:
        pdf.close()
    return "\n\n".join(page for page in pages if page) + "\n"


@dataclass(frozen=True)
class Parser:
    name: str  # 存在库里
    label: str  # 给人看
    parse: Callable[[Path], str]


PLAIN = Parser("plain", "自带", plain)
DOCLING = Parser("docling", "Docling（认版面和表格）", docling)
PDF_TEXT = Parser("pdf_text", "只取文字（快，不认表格）", pdf_text)

PARSERS: dict[str, list[Parser]] = {
    ".md": [PLAIN],
    ".txt": [PLAIN],
    ".html": [DOCLING],
    ".docx": [DOCLING],
    ".pdf": [DOCLING, PDF_TEXT],
}


def pick(suffix: str, name: str | None = None) -> Parser:
    """这种文件用哪个解析器；不指定就用默认的。名字不在这种文件的可选列表里时抛 KeyError。"""
    choices = PARSERS[suffix]
    if name is None:
        return choices[0]
    for parser in choices:
        if parser.name == name:
            return parser
    raise KeyError(name)
