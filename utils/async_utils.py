from __future__ import annotations

import asyncio
from collections.abc import Awaitable


async def gather_with_concurrency(
    limit: int, tasks: dict[str, Awaitable[str]]
) -> dict[str, str]:
    semaphore = asyncio.Semaphore(limit)

    async def _run(task: Awaitable[str]) -> str:
        async with semaphore:
            return await task

    keys = list(tasks.keys())
    results = await asyncio.gather(*[_run(task) for task in tasks.values()])
    return dict(zip(keys, results, strict=True))
