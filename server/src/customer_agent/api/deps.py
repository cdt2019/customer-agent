"""接口共用的依赖。"""

from collections.abc import Iterator

from sqlalchemy.orm import Session as DbSession

from customer_agent.db import Session


def db() -> Iterator[DbSession]:
    with Session() as session:
        yield session
