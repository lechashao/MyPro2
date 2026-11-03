"""A reproducible scheduling sandbox. Energy is a game resource, not a health metric."""
from copy import deepcopy
from hashlib import sha256

ENGINE_VERSION = "1.1"
POLICIES = {
    "adaptive": {"name": "鲍勃自主决策", "color": "green"},
    "balanced": {"name": "寻找平衡", "color": "green"},
    "career": {"name": "事业优先", "color": "orange"},
    "recovery": {"name": "留出余裕", "color": "blue"},
}
ACTIONS = {
    "focus": {"name": "全力推进项目", "work": 11, "sleep": 6.5, "exercise": 0, "progress": 19, "energy": -13},
    "negotiate": {"name": "协商范围，稳步推进", "work": 8, "sleep": 8, "exercise": .5, "progress": 12, "energy": -2},
    "rest": {"name": "减少工作，留出休息", "work": 5, "sleep": 8.5, "exercise": 1, "progress": 6, "energy": 9},
}


def evidence(snapshot, source):
    records = [m for m in snapshot["memories"] if m["source"] == source]
    return sorted(records, key=lambda m: (m["observed_at"], m["id"]), reverse=True)[:2]


def advisors(state, snapshot):
    target = snapshot["profile"]["sleep_target"]
    health_action = "rest" if state["energy"] < 45 else "negotiate"
    work_action = "focus" if state["progress"] < 70 else "negotiate"
    return [
        {"role": "health", "name": "健康顾问", "action": health_action,
         "reason": f"你的作息目标是每晚 {target:g} 小时。建议为休息保留时间。" +
                   ("当前模拟精力偏低，可以减少一天的工作安排。" if state["energy"] < 45 else "避免让项目持续挤占生活时间。"),
         "memory_ids": [m["id"] for m in evidence(snapshot, "health_assistant")]},
        {"role": "work", "name": "工作顾问", "action": work_action,
         "reason": f"项目当前完成 {state['progress']}%。" +
                   ("可以集中推进，但需要承担额外时间成本。" if work_action == "focus" else "已有进展，建议控制范围并持续交付。"),
         "memory_ids": [m["id"] for m in evidence(snapshot, "work_assistant")]},
    ]


def evaluate_actions(state, snapshot):
    """Score only information available before today's external event."""
    target = snapshot["profile"]["sleep_target"]
    results = []
    for action, plan in ACTIONS.items():
        progress_value = min(100 - state["progress"], plan["progress"]) / 19 * 30 * (1 + state["day"] / 14)
        next_energy = max(0, min(100, state["energy"] + plan["energy"]))
        health_value = (next_energy - state["energy"]) * .65 - max(0, target - plan["sleep"]) * 6 - max(0, 45 - next_energy) * 1.2
        free_hours = 24 - plan["work"] - plan["sleep"] - plan["exercise"] - 3
        results.append({"action": action, "work_score": round(progress_value, 2),
                        "health_score": round(health_value, 2), "free_time_score": round(free_hours * .8, 2),
                        "score": round(progress_value + health_value + free_hours * .8, 2)})
    return sorted(results, key=lambda r: r["score"], reverse=True)


def choose(state, policy, snapshot=None):
    if policy == "adaptive":
        return evaluate_actions(state, snapshot)[0]["action"]
    if policy == "career":
        return "focus" if state["energy"] >= 25 and state["progress"] < 100 else "negotiate"
    if policy == "recovery":
        return "rest" if state["energy"] < 85 else "negotiate"
    return "rest" if state["energy"] < 45 else "negotiate"


def step(branch, action=None):
    if branch["state"]["day"] >= 7:
        raise ValueError("七天模拟已结束，请创建新分支。")
    before = deepcopy(branch["state"])
    day = before["day"] + 1
    action_id = action or choose(before, branch["policy"], branch["snapshot"])
    plan = ACTIONS[action_id]
    # Independent of policy: same seed/day => same external event across branches.
    roll = int(sha256(f"{branch['seed']}:{day}".encode()).hexdigest()[:8], 16) % 3
    events = [
        ("同事提供了一份可复用的资料", 3),
        ("项目出现一次额外的需求沟通", -2),
        ("今天没有新增的外部任务", 0),
    ]
    event, delta = events[roll]
    after = {
        "day": day,
        "energy": max(0, min(100, before["energy"] + plan["energy"])),
        "progress": max(0, min(100, before["progress"] + plan["progress"] + delta)),
        "sleep_total": before["sleep_total"] + plan["sleep"],
        "work_total": before["work_total"] + plan["work"],
        "exercise_total": before["exercise_total"] + plan["exercise"],
        "free_total": before["free_total"] + 24 - plan["work"] - plan["sleep"] - plan["exercise"] - 3,
    }
    advice = advisors(before, branch["snapshot"])
    scores = evaluate_actions(before, branch["snapshot"]) if not action and branch["policy"] == "adaptive" else []
    reason = "由你决定今天的行动。" if action else (f"鲍勃比较了三种安排：当前精力 {before['energy']}，项目进度 {before['progress']}%，"
              f"作息目标 {branch['snapshot']['profile']['sleep_target']:g} 小时。"
              f"「{plan['name']}」的综合规则得分最高（{scores[0]['score']}），因此选择这个安排。" if scores else {
        "balanced": "鲍勃以持续推进和生活余裕为目标，在精力较低时安排恢复。",
        "career": "鲍勃优先考虑交付进度，精力过低时降低负荷。",
        "recovery": "鲍勃优先保留休息时间，精力充足时稳步工作。",
    }[branch["policy"]])
    branch["events"].append({
        "day": day, "action": action_id, "action_name": plan["name"],
        "controlled_by": "user" if action else "policy",
        "decision_scores": scores,
        "external_event": event, "reason": reason, "advisors": advice,
        "schedule": {"work": plan["work"], "sleep": plan["sleep"], "exercise": plan["exercise"],
                     "daily_life": 3, "free": 24 - plan["work"] - plan["sleep"] - plan["exercise"] - 3},
        "before": before, "after": deepcopy(after),
    })
    branch["state"] = after
    return branch


def initial_state():
    return {"day": 0, "energy": 65, "progress": 0, "sleep_total": 0,
            "work_total": 0, "exercise_total": 0, "free_total": 0}


def describe(branch):
    result = deepcopy(branch)
    state = result["state"]
    result["advisors"] = advisors(state, branch["snapshot"])
    result["metrics"] = {
        "average_sleep": round(state["sleep_total"] / state["day"], 1) if state["day"] else None,
        "sleep_goal_days": sum(e["schedule"]["sleep"] >= branch["snapshot"]["profile"]["sleep_target"] for e in branch["events"]),
    }
    result["summary"] = {
        "automatic_days": sum(e.get("controlled_by") == "policy" for e in branch["events"]),
        "manual_days": sum(e.get("controlled_by") == "user" for e in branch["events"]),
        "action_counts": {key: sum(e["action"] == key for e in branch["events"]) for key in ACTIONS},
    }
    return result
