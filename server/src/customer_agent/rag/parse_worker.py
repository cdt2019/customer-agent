"""常驻的解析子进程：python -m customer_agent.rag.parse_worker。

从标准输入一行读一个任务 {"source", "target", "parser"}，把结果写进 target，再在标准输出回一行 {"ok": true} 或 {"ok": false, "error": "…"}。
模型加载一次一直用；标准输入关了就退出。空闲多久关掉由服务那头管（rag/imports.py）。

只在两个任务之间读标准输入，解析时不能有线程同时在读：Windows 上一个线程卡在读管道时，别处再碰这根管道的句柄（解析器里起子进程、查终端）会一起卡死。
"""

import json
import sys
from pathlib import Path

from customer_agent.rag.parsers import pick


def main() -> None:
    replies, sys.stdout = sys.stdout, sys.stderr  # 解析器自己打印的东西去标准错误，标准输出只留给回复
    for line in sys.stdin:
        task = json.loads(line)
        source = Path(task["source"])
        try:
            markdown = pick(source.suffix.lower(), task["parser"]).parse(source)
            Path(task["target"]).write_bytes(markdown.encode("utf-8"))  # 按字节写，Windows 不会改换行
            reply = {"ok": True}
        except Exception as error:  # 解析器的任何错误都报回去，进程接着用
            reply = {"ok": False, "error": f"{type(error).__name__}: {error}"[:300]}
        replies.write(json.dumps(reply, ensure_ascii=False) + "\n")
        replies.flush()


if __name__ == "__main__":
    main()
