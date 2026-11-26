import os

# 在导入 demo_shop 之前定好配置，不读本机的 .env
os.environ.update(AGENT_URL="http://agent.test", AGENT_KEY="agent-key", SHOP_API_KEY="shop-key", TOKEN_SECRET="test-secret", INDEX_ID="7")
