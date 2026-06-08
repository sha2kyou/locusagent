import asyncio

import pytest

from agentpod_agent.core import post_run as post_run_module


@pytest.mark.asyncio
async def test_post_run_jobs_execute_serially(monkeypatch: pytest.MonkeyPatch) -> None:
    await post_run_module.shutdown_post_run_worker()
    post_run_module._post_run_queue = None
    post_run_module._post_run_worker = None

    active = 0
    peak = 0
    lock = asyncio.Lock()

    async def fake_execute(job: post_run_module._PostRunJob) -> None:
        nonlocal active, peak
        async with lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(0.05)
        async with lock:
            active -= 1
        if job.done is not None and not job.done.done():
            job.done.set_result(None)

    monkeypatch.setattr(post_run_module, "_execute_post_tasks", fake_execute)

    done_a: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    done_b: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    queue = await post_run_module._ensure_post_run_worker()
    await queue.put(
        post_run_module._PostRunJob(
            session_id="sess-a",
            loop_rounds=1,
            model=None,
            messages=[],
            done=done_a,
        )
    )
    await queue.put(
        post_run_module._PostRunJob(
            session_id="sess-b",
            loop_rounds=1,
            model=None,
            messages=[],
            done=done_b,
        )
    )

    await asyncio.wait_for(asyncio.gather(done_a, done_b), timeout=2.0)
    assert peak == 1

    await post_run_module.shutdown_post_run_worker()
