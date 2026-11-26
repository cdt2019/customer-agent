"""扩展问题：让模型把买家的话改写成更适合检索的说法，一句话问了几件事就拆开。"""

from customer_agent.llm import ChatModel

SYSTEM = """你在帮一个检索系统准备查询。把用户的问题改写成 1 到 3 条用来搜索文档的查询：

- 换成文档里更可能出现的书面说法和术语，保留原问题里的专有名词、标识符和数字。
- 一句话里问了几件事，就拆成几条，每条只问一件事。
- 只问了一件事，就只给一条改写。
- 每行一条，不要编号，不要解释。"""


def expand(llm: ChatModel, question: str) -> list[str]:
    """返回要检索的全部查询：原问题在最前，后面是模型给的改写，最多三条。"""
    lines = [line.strip(" -•\t") for line in llm.complete(SYSTEM, question).text.splitlines()]
    return list(dict.fromkeys([question, *[line for line in lines if line][:3]]))
