"""End-to-end smoke test: runs the exercise 4 graph on both demo PRs.

GitHub posting is stubbed out (nothing is written to the real PR) and the
human reviewer's answers are scripted. Usage: uv run python test_flow.py
"""

import asyncio
import uuid

from dotenv import load_dotenv
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from common.db import db_path, replay_events
from exercises import exercise_4_audit as ex4

load_dotenv()
posted: list[str] = []
ex4.post_review_comment = lambda url, body: posted.append(body)  # no real posting

PRS = {
    1: "https://github.com/VinUni-AI20k/PR-Demo/pull/1",
    2: "https://github.com/VinUni-AI20k/PR-Demo/pull/2",
}


def scripted(payload: dict):
    if payload["kind"] == "approval_request":
        return {"choice": "approve", "feedback": "LGTM, test run"}
    return {q: "Test answer: intended, will fix before release." for q in payload["questions"]}


async def run(pr_url: str):
    thread_id = str(uuid.uuid4())
    seen = []
    async with AsyncSqliteSaver.from_conn_string(db_path()) as cp:
        await cp.setup()
        app = ex4.build_graph(cp)
        cfg = {"configurable": {"thread_id": thread_id}}
        result = await app.ainvoke({"pr_url": pr_url, "thread_id": thread_id}, cfg)
        while "__interrupt__" in result:
            payload = result["__interrupt__"][0].value
            seen.append(payload["kind"])
            result = await app.ainvoke(Command(resume=scripted(payload)), cfg)
    events = await replay_events(thread_id)
    return thread_id, seen, result, events


async def main():
    import sys
    only = [int(a) for a in sys.argv[1:]] or list(PRS)
    for n, url in [(k, v) for k, v in PRS.items() if k in only]:
        tid, seen, result, events = await run(url)
        print(f"\n=== PR #{n} thread={tid}")
        print("interrupts:", seen, "| final_action:", result.get("final_action"))
        for e in events:
            print(f"  {e['action']:<15} conf={e['confidence']:.2f} risk={e['risk_level']:<4} "
                  f"decision={e['decision']:<9} reviewer={e['reviewer_id']}")
        assert events, "no audit rows written"
        assert result.get("final_action"), "graph did not finish"
    print(f"\nstubbed posts: {len(posted)}  OK")


asyncio.run(main())
