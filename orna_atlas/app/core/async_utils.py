import asyncio
from collections.abc import Awaitable
from typing import Any

CANCELLATION_COMPENSATION_TIMEOUT_SECONDS = 2.0
CANCELLATION_UNWIND_TIMEOUT_SECONDS = 0.1


def _consume_task_result(task: asyncio.Future[Any]) -> None:
    try:
        task.result()
    except BaseException:
        pass


async def finish_cancelled_compensation(
    awaitable: Awaitable[Any],
    *,
    timeout_seconds: float = CANCELLATION_COMPENSATION_TIMEOUT_SECONDS,
) -> None:
    """Bound compensation without replacing an already-recorded cancellation."""
    task = asyncio.ensure_future(awaitable)
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while not task.done():
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=remaining)
        except TimeoutError:
            break
        except asyncio.CancelledError:
            if task.done():
                break
            continue
        except BaseException:
            break
    if task.done():
        _consume_task_result(task)
        return
    task.cancel()
    unwind_deadline = asyncio.get_running_loop().time() + CANCELLATION_UNWIND_TIMEOUT_SECONDS
    while not task.done():
        remaining = unwind_deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=remaining)
        except TimeoutError:
            break
        except asyncio.CancelledError:
            if task.done():
                break
            continue
        except BaseException:
            break
    if task.done():
        _consume_task_result(task)
        return
    task.add_done_callback(_consume_task_result)
