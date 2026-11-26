"""清洗图片的子进程：python -m customer_agent.chat.image_worker <输入> <输出>。

图片是不可信的输入，解码放在单独进程里，坏图、炸弹图拖不垮服务。按内容认格式，只收 JPG、PNG、WebP；
长边超过 MAX_SIDE 的缩小；重新编码，元数据（拍摄位置、设备）一律不带；动图只留第一帧。
成功时在标准输出打印一行 {"format", "width", "height"}；不收的图打印 {"error": "…"} 并以 2 退出。
"""

import json
import sys

from PIL import Image

MAX_SIDE = 2048
MAX_PIXELS = 40_000_000  # 比这大的按「解压炸弹」拒掉
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


def main() -> None:
    source, target = sys.argv[1], sys.argv[2]
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(source) as image:
            kind = image.format
            if kind not in FORMATS:
                raise ValueError("只收 JPG、PNG、WebP")
            image.seek(0)
            frame = image.convert("RGB" if kind == "JPEG" else "RGBA")
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        print(json.dumps({"error": str(error)[:200]}, ensure_ascii=False))
        sys.exit(2)
    frame.thumbnail((MAX_SIDE, MAX_SIDE))
    frame.save(target, format=kind, **({"quality": 85} if kind in ("JPEG", "WEBP") else {}))  # 新存的图不带原图的元数据
    print(json.dumps({"format": FORMATS[kind], "width": frame.width, "height": frame.height}))


if __name__ == "__main__":
    main()
