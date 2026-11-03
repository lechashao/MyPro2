from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .engine import ACTIONS, ENGINE_VERSION, POLICIES, describe, initial_state, step

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("BOB_DB_PATH", ROOT / ".data" / "bob.sqlite3"))
LOCK = RLock()
app = FastAPI(title="Bob's World", version="0.1.0")


@contextmanager
def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK:
        db = sqlite3.connect(DB_PATH)
        try:
            db.execute("CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def load(db, key, default=None):
    row = db.execute("SELECT body FROM documents WHERE id=?", (key,)).fetchone()
    return json.loads(row[0]) if row else deepcopy(default)


def save(db, key, value):
    db.execute("INSERT INTO documents VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
               (key, json.dumps(value, ensure_ascii=False)))


DEFAULT_PROFILE = {"name": "鲍勃", "occupation": "产品经理", "goal": "在工作进展与生活余裕之间找到自己的节奏", "sleep_target": 8}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Profile(StrictModel):
    name: str = Field(default="鲍勃", min_length=1, max_length=30)
    occupation: str = Field(default="产品经理", min_length=1, max_length=80)
    goal: str = Field(min_length=1, max_length=500)
    sleep_target: float = Field(default=8, ge=4, le=12)


class Memory(StrictModel):
    source: Literal["health_assistant", "work_assistant"]
    content: str = Field(min_length=1, max_length=2000)
    type: Literal["reported_fact", "preference", "goal", "hypothesis"] = "reported_fact"
    observed_at: datetime
    confidence: float = Field(default=1, ge=0, le=1)

    @field_validator("content")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("记忆内容不能为空")
        return value.strip()

    @field_validator("observed_at")
    @classmethod
    def normalize_time(cls, value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ImportRequest(StrictModel):
    memories: list[Memory] = Field(min_length=1, max_length=200)


class CreateBranch(StrictModel):
    policy: Literal["adaptive", "balanced", "career", "recovery"] = "balanced"
    seed: int = Field(default=42, ge=0, le=2147483647)
    name: str | None = Field(default=None, min_length=1, max_length=60)
    use_demo: bool = True


class Advance(StrictModel):
    days: int = Field(default=1, ge=1, le=7)
    action: Literal["focus", "negotiate", "rest"] | None = None
    expected_day: int = Field(ge=0, le=7)


class Fork(StrictModel):
    day: int = Field(ge=0, le=7)
    policy: Literal["adaptive", "balanced", "career", "recovery"]
    name: str | None = Field(default=None, min_length=1, max_length=60)


class AutoSimulation(StrictModel):
    seed: int = Field(default=42, ge=0, le=2147483647)
    use_demo: bool | None = None


DEMO = [
    {"id": "demo-health-1", "source": "health_assistant", "type": "reported_fact", "content": "最近一周经常工作到很晚，希望重新安排作息。", "observed_at": "2026-11-01T08:00:00+00:00", "confidence": 1, "is_demo": True},
    {"id": "demo-health-2", "source": "health_assistant", "type": "goal", "content": "希望每周留出三次散步或运动的时间。", "observed_at": "2026-11-02T08:00:00+00:00", "confidence": 1, "is_demo": True},
    {"id": "demo-work-1", "source": "work_assistant", "type": "reported_fact", "content": "上司邀请鲍勃接手新项目，现有任务还没有结束。", "observed_at": "2026-11-01T08:00:00+00:00", "confidence": 1, "is_demo": True},
    {"id": "demo-work-2", "source": "work_assistant", "type": "goal", "content": "希望获得更多成长机会，同时避免长期加班。", "observed_at": "2026-11-02T08:00:00+00:00", "confidence": 1, "is_demo": True},
]


@app.middleware("http")
async def local_access(request: Request, call_next):
    # A local single-user app: reject cross-origin mutations from browser pages.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "不允许跨来源写入"}, status_code=403)
    if request.url.path == "/api/memories/import":
        body = await request.body()
        if len(body) > 1_000_000:
            return JSONResponse({"detail": "导入文件不能超过 1 MB"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/world")
def world():
    with database() as db:
        branches = [describe(json.loads(row[0])) for row in db.execute("SELECT body FROM documents WHERE id LIKE 'branch:%' ORDER BY rowid DESC")]
        return {"profile": load(db, "profile", DEFAULT_PROFILE), "memories": load(db, "memories", []),
                "demo_memories": DEMO, "branches": branches, "policies": POLICIES, "actions": ACTIONS,
                "engine_version": ENGINE_VERSION, "coach_mode": "local_rules"}


@app.put("/api/profile")
def update_profile(profile: Profile):
    with database() as db:
        save(db, "profile", profile.model_dump())
    return profile


@app.post("/api/memories/import")
def import_memories(payload: ImportRequest):
    with database() as db:
        memories = load(db, "memories", [])
        keys = {(m["source"], m["content"], m["observed_at"], m["type"], m["confidence"]) for m in memories}
        added = 0
        for item in payload.memories:
            data = item.model_dump(mode="json")
            key = (data["source"], data["content"], data["observed_at"], data["type"], data["confidence"])
            if key in keys:
                continue
            keys.add(key)
            memories.append({**data, "id": str(uuid4()), "is_demo": False})
            added += 1
        if len(memories) > 2000:
            raise HTTPException(422, "本地记忆库最多保存 2000 条，请先删除不需要的记录。")
        save(db, "memories", memories)
    return {"added": added, "duplicates": len(payload.memories) - added}


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: str):
    with database() as db:
        memories = load(db, "memories", [])
        if not any(m["id"] == memory_id for m in memories):
            raise HTTPException(404, "记忆不存在")
        save(db, "memories", [m for m in memories if m["id"] != memory_id])
        # Delete copied evidence too; derived schedules contain no imported text.
        rows = list(db.execute("SELECT id, body FROM documents WHERE id LIKE 'branch:%'"))
        for key, body in rows:
            branch = json.loads(body)
            branch["snapshot"]["memories"] = [m for m in branch["snapshot"]["memories"] if m["id"] != memory_id]
            for event in branch["events"]:
                for advisor in event["advisors"]:
                    advisor["memory_ids"] = [i for i in advisor["memory_ids"] if i != memory_id]
            save(db, key, branch)
    return {"deleted": True}


def get_branch(db, branch_id):
    result = load(db, f"branch:{branch_id}")
    if result is None:
        raise HTTPException(404, "分支不存在")
    return result


@app.post("/api/branches", status_code=201)
def create_branch(payload: CreateBranch):
    with database() as db:
        memories = load(db, "memories", [])
        branch = {"id": str(uuid4()), "name": payload.name or POLICIES[payload.policy]["name"],
                  "policy": payload.policy, "seed": payload.seed, "engine_version": ENGINE_VERSION,
                  "created_at": datetime.now(timezone.utc).isoformat(), "parent_id": None, "fork_day": None,
                  "snapshot": {"profile": load(db, "profile", DEFAULT_PROFILE),
                               "memories": deepcopy(DEMO if payload.use_demo else memories),
                               "memory_mode": "demo" if payload.use_demo else "imported"},
                  "state": initial_state(), "events": []}
        save(db, f"branch:{branch['id']}", branch)
    return describe(branch)


@app.post("/api/branches/{branch_id}/advance")
def advance(branch_id: str, payload: Advance):
    with database() as db:
        branch = get_branch(db, branch_id)
        if branch["state"]["day"] != payload.expected_day:
            raise HTTPException(409, "分支已发生变化，请刷新后再试。")
        if branch["state"]["day"] + payload.days > 7:
            raise HTTPException(409, "超过七天上限，请减少推进天数。")
        for _ in range(payload.days):
            step(branch, payload.action)
        save(db, f"branch:{branch_id}", branch)
    return describe(branch)


@app.post("/api/simulations/auto", status_code=201)
def auto_simulation(payload: AutoSimulation):
    # One transaction: either the entire seven-day story exists, or none of it.
    with database() as db:
        memories = load(db, "memories", [])
        use_demo = payload.use_demo if payload.use_demo is not None else not bool(memories)
        branch = {"id": str(uuid4()), "name": "鲍勃的全自动人生", "policy": "adaptive",
                  "seed": payload.seed, "engine_version": ENGINE_VERSION,
                  "created_at": datetime.now(timezone.utc).isoformat(), "parent_id": None, "fork_day": None,
                  "snapshot": {"profile": load(db, "profile", DEFAULT_PROFILE),
                               "memories": deepcopy(DEMO if use_demo else memories),
                               "memory_mode": "demo" if use_demo else "imported"},
                  "state": initial_state(), "events": []}
        for _ in range(7):
            step(branch)
        save(db, f"branch:{branch['id']}", branch)
    return describe(branch)


@app.post("/api/branches/{branch_id}/fork", status_code=201)
def fork(branch_id: str, payload: Fork):
    with database() as db:
        branch = get_branch(db, branch_id)
        if payload.day > branch["state"]["day"]:
            raise HTTPException(422, "不能从尚未发生的日期创建分支。")
        child = deepcopy(branch)
        child.update(id=str(uuid4()), parent_id=branch_id, fork_day=payload.day,
                     policy=payload.policy, name=payload.name or POLICIES[payload.policy]["name"],
                     created_at=datetime.now(timezone.utc).isoformat())
        child["events"] = child["events"][:payload.day]
        child["state"] = deepcopy(child["events"][-1]["after"]) if payload.day else initial_state()
        save(db, f"branch:{child['id']}", child)
    return describe(child)


@app.get("/api/branches/{branch_id}/export")
def export_branch(branch_id: str):
    with database() as db:
        return JSONResponse(get_branch(db, branch_id), headers={"Content-Disposition": 'attachment; filename="bob-branch.json"'})


@app.delete("/api/branches/{branch_id}")
def delete_branch(branch_id: str):
    with database() as db:
        get_branch(db, branch_id)
        db.execute("DELETE FROM documents WHERE id=?", (f"branch:{branch_id}",))
    return {"deleted": True}


@app.get("/api/health")
def health():
    with database() as db:
        db.execute("SELECT 1")
    return {"status": "ok", "engine_version": ENGINE_VERSION}


app.mount("/assets", StaticFiles(directory=ROOT / "web"), name="assets")


@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html")
