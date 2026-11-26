"""把 Hugging Face 上的模型下到 MODELS_DIR/<名字>，可断点续传。

文件清单和 sha256 取自 huggingface.co 官方接口；文件本身从 HF_ENDPOINT 下载（可以换成镜像），
下完逐个核对 sha256，对不上就删掉报错。只下推理要用的文件，不下 onnx、图片。
"""

import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

SKIP = ("onnx/", "openvino/", "imgs/", ".gitattributes", "README.md")
SKIP_SUFFIX = (".jpg", ".png", ".webp", ".onnx", ".h5", ".msgpack", ".ot")
RETRIES = 20


class BadFile(Exception):
    pass


def file_list(repo: str) -> list[dict]:
    with urllib.request.urlopen(f"https://huggingface.co/api/models/{repo}?blobs=true", timeout=60) as r:
        siblings = json.load(r)["siblings"]
    files = [s for s in siblings if not s["rfilename"].startswith(SKIP) and not s["rfilename"].endswith(SKIP_SUFFIX)]
    # 同一份权重有 safetensors 就不要 pickle 格式的 bin
    if any(s["rfilename"] == "model.safetensors" for s in files):
        files = [s for s in files if s["rfilename"] != "pytorch_model.bin"]
    return files


def _download(url: str, dest: Path, size: int) -> None:
    """断了就从断点接着下，最多重试 RETRIES 次。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    for attempt in range(RETRIES):
        done = part.stat().st_size if part.exists() else 0
        if done >= size:
            break
        request = urllib.request.Request(url, headers={"Range": f"bytes={done}-"} if done else {})
        try:
            with urllib.request.urlopen(request, timeout=60) as response, part.open("ab" if response.status == 206 else "wb") as out:
                while chunk := response.read(1 << 20):
                    out.write(chunk)
        except OSError:
            time.sleep(min(2**attempt, 30))
    if not part.exists() or part.stat().st_size < size:
        raise BadFile(f"下载没完成：{dest.name}")
    os.replace(part, dest)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 22):
            h.update(chunk)
    return h.hexdigest()


def fetch(repo: str, models_dir: Path, endpoint: str, say=print) -> Path:
    """下载 repo（如 BAAI/bge-m3）到 models_dir/bge-m3，返回这个目录。已经下好、校验对的文件跳过。"""
    target = models_dir / repo.split("/")[1]
    for item in file_list(repo):
        name, size, lfs = item["rfilename"], item["size"], item.get("lfs")
        dest = target / name
        if not (dest.exists() and dest.stat().st_size == size):
            say(f"{name}  {size >> 20}MB")
            _download(f"{endpoint}/{repo}/resolve/main/{name}", dest, size)
        if lfs and _sha256(dest) != lfs["sha256"]:
            dest.unlink()
            raise BadFile(f"校验失败，已删除：{name}")
    return target
