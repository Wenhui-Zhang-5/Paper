# pip install aiohttp
import asyncio, aiohttp
from collections import defaultdict

MAX_PORTS = 50
MAX_ACTIVE_CASES = 10
CASE_CAP = 5   # 竞争时每个 case 的上限

class FairLimiter:
    def __init__(self, max_ports=MAX_PORTS, case_cap=CASE_CAP, max_cases=MAX_ACTIVE_CASES):
        self.max_ports = max_ports
        self.case_cap = case_cap
        self.max_cases = max_cases
        self.inflight_total = 0
        self.inflight_case = defaultdict(int)
        self.active_cases = set()
        self.cv = asyncio.Condition()

    def _allowed_for(self, cid):
        k = max(1, len(self.active_cases))  # 至少 1
        if k == 1:
            return self.max_ports
        return min(self.case_cap, max(1, self.max_ports // k))

    async def acquire(self, cid):
        async with self.cv:
            if cid not in self.active_cases:
                if len(self.active_cases) >= self.max_cases:
                    raise RuntimeError("Too many active cases")
                self.active_cases.add(cid)
                # 刚注册的 case 立刻参与分配
            while True:
                allowed = self._allowed_for(cid)
                if self.inflight_total < self.max_ports and self.inflight_case[cid] < allowed:
                    self.inflight_total += 1
                    self.inflight_case[cid] += 1
                    return
                await self.cv.wait()

    async def release(self, cid):
        async with self.cv:
            self.inflight_total -= 1
            self.inflight_case[cid] -= 1
            # 如果该 case 没有在跑的任务了且不再需要，可在外部调用 remove_case
            self.cv.notify_all()

    async def remove_case(self, cid):
        async with self.cv:
            if self.inflight_case[cid] == 0 and cid in self.active_cases:
                self.active_cases.remove(cid)
                self.cv.notify_all()

limiter = FairLimiter()

async def call_dispatcher(payload):
    """把这里换成你现有的 submit/status 逻辑即可。"""
    DISPATCHER = "http://dispatcher:8000"
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{DISPATCHER}/submit", json={"params": payload}) as r:
            jid = (await r.json())["job_id"]
        while True:
            await asyncio.sleep(0.4)
            async with s.post(f"{DISPATCHER}/status", json={"job_id": jid}) as r:
                st = await r.json()
            if st["state"] == "done":
                return st["result"]
            if st["state"] == "error":
                raise RuntimeError(st.get("error"))

async def eval_once(case_id, payload):
    await limiter.acquire(case_id)
    try:
        return await call_dispatcher(payload)
    finally:
        await limiter.release(case_id)

# ==== 用法：把你 BO/LM 的评估都改成 eval_once ====

async def run_case(case_id, bo_iters=10, bo_batch=8, lm_seeds=5):
    # --- BO：每轮并发 bo_batch 个评估 ---
    for _ in range(bo_iters):
        cands = ask_BO(case_id, bo_batch)  # 你已有
        tasks = [asyncio.create_task(eval_once(case_id, c)) for c in cands]
        results = await asyncio.gather(*tasks)
        tell_BO(case_id, results)          # 你已有
        if bo_converged(case_id): break

    # --- LM：5 个 seed 并发，每个 seed 内部串行 ---
    async def lm_seed(seed):
        state = init_lm(case_id, seed)
        while not state.converged:
            payload = build_lm_step(case_id, state)
            res = await eval_once(case_id, payload)  # 每步借端口
            state = lm_update(case_id, state, res)
        return state.best

    bests = await asyncio.gather(*[asyncio.create_task(lm_seed(s)) for s in select_seeds(case_id, lm_seeds)])
    commit_final(case_id, bests)
    await limiter.remove_case(case_id)

async def main(all_cases, max_cases=10):
    # 同时最多 10 个 case，其余等位
    sem_cases = asyncio.Semaphore(max_cases)
    async def run_guarded(cfg):
        async with sem_cases:
            await run_case(**cfg)
    await asyncio.gather(*[asyncio.create_task(run_guarded(c)) for c in all_cases])

# ===== 下面这些都是你已有的函数，占位而已 =====
def ask_BO(case_id, batch): ...
def tell_BO(case_id, results): ...
def bo_converged(case_id): return False
def select_seeds(case_id, n): return list(range(n))
def init_lm(case_id, seed): ...
def build_lm_step(case_id, state): ...
def lm_update(case_id, state, res): ...
def commit_final(case_id, bests): ...