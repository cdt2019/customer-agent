"""Alembic 入口：表结构以 customer_agent.db 里的模型为准，连接地址来自 settings。"""

from alembic import context

from customer_agent.db import Base, engine

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
