"""Promote the first production administrator through an auditable one-time command."""

from __future__ import annotations

import argparse
import asyncio

from orna_atlas.app.db.session import AsyncSessionLocal, engine
from orna_atlas.app.modules.users.service import bootstrap_first_admin


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote an existing active user when no admin account exists."
    )
    parser.add_argument("--email", required=True, help="Email of an already registered user")
    return parser.parse_args()


async def run(email: str) -> None:
    try:
        async with AsyncSessionLocal() as session:
            user = await bootstrap_first_admin(session, email)
    finally:
        await engine.dispose()
    print(f"Bootstrapped admin {user.email} ({user.id})")


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run(args.email))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
