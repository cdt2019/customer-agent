"""命令行：起服务；给评测签一个会员的访客令牌。"""

import argparse
import secrets

import uvicorn

from demo_shop import settings, store, tokens


def main() -> None:
    parser = argparse.ArgumentParser(prog="demo-shop")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="起模拟店铺")
    serve.add_argument("--host", default="127.0.0.1", help="容器里用 0.0.0.0")
    serve.add_argument("--port", type=int, default=8100)
    token = commands.add_parser("token", help="签一个访客令牌，评测用")
    token.add_argument("who", choices=store.IDENTITIES)
    token.add_argument("--minutes", type=int, default=24 * 60)
    args = parser.parse_args()
    if args.command == "serve":
        uvicorn.run("demo_shop.app:app", host=args.host, port=args.port)
    else:
        print(tokens.sign(settings.TOKEN_SECRET, args.who, secrets.token_urlsafe(8), args.minutes))
