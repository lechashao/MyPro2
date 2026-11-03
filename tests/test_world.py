from copy import deepcopy
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.engine import evaluate_actions, initial_state, step

module = importlib.import_module("backend.app")


class WorldTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_path = module.DB_PATH
        module.DB_PATH = Path(self.temp.name) / "test.sqlite3"
        self.client = TestClient(module.app)

    def tearDown(self):
        self.client.close()
        module.DB_PATH = self.original_path
        self.temp.cleanup()

    def create(self, **kwargs):
        response = self.client.post("/api/branches", json=kwargs)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def advance(self, branch, days=1, **kwargs):
        response = self.client.post(f"/api/branches/{branch['id']}/advance", json={
            "expected_day": branch["state"]["day"], "days": days, **kwargs,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_complete_seven_day_world_and_replay(self):
        branch = self.create(policy="balanced", seed=17)
        result = self.advance(branch, days=7)
        self.assertEqual(result["state"]["day"], 7)
        self.assertEqual(len(result["events"]), 7)
        replay = deepcopy(branch)
        for event in result["events"]:
            self.assertEqual(sum(event["schedule"].values()), 24)
            step(replay, event["action"] if event["controlled_by"] == "user" else None)
        self.assertEqual(replay["state"], result["state"])
        self.assertEqual(replay["events"], result["events"])
        response = self.client.get(f"/api/branches/{branch['id']}/export")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], result["state"])

    def test_fork_preserves_history_and_does_not_change_parent(self):
        parent = self.advance(self.create(policy="career"), days=4)
        response = self.client.post(f"/api/branches/{parent['id']}/fork", json={"day": 2, "policy": "recovery"})
        self.assertEqual(response.status_code, 201)
        child = response.json()
        self.assertEqual(child["events"], parent["events"][:2])
        self.assertEqual(child["state"], parent["events"][1]["after"])
        self.assertEqual(child["snapshot"], parent["snapshot"])
        child = self.advance(child, days=5)
        unchanged = self.client.get(f"/api/branches/{parent['id']}/export").json()
        self.assertEqual(unchanged["events"], parent["events"])
        self.assertNotEqual(child["state"]["energy"], parent["state"]["energy"])
        invalid = self.client.post(f"/api/branches/{parent['id']}/fork", json={"day": 7, "policy": "balanced"})
        self.assertEqual(invalid.status_code, 422)

    def test_manual_action_replays_with_its_control_mode(self):
        original = self.create(policy="recovery")
        manual = self.advance(original, action="focus")
        self.assertEqual(manual["events"][0]["controlled_by"], "user")
        self.assertEqual(manual["events"][0]["schedule"]["work"], 11)
        replay = deepcopy(original)
        step(replay, manual["events"][0]["action"])
        self.assertEqual(replay["events"], manual["events"])
        self.assertEqual(replay["state"], manual["state"])

    def test_same_seed_same_external_events_across_policies(self):
        results = [self.advance(self.create(policy=p, seed=100), 7) for p in ("balanced", "career", "recovery")]
        schedules = [[e["external_event"] for e in r["events"]] for r in results]
        self.assertEqual(schedules[0], schedules[1])
        self.assertEqual(schedules[1], schedules[2])
        self.assertGreater(results[1]["state"]["progress"], results[2]["state"]["progress"])
        self.assertGreater(results[2]["state"]["energy"], results[1]["state"]["energy"])

    def test_import_deduplication_snapshot_and_delete(self):
        demo = self.create()
        record = {"source": "health_assistant", "content": "希望每天散步", "observed_at": "2026-11-03T09:00:00+03:00", "type": "goal", "confidence": .9}
        first = self.client.post("/api/memories/import", json={"memories": [record, record]})
        self.assertEqual(first.json(), {"added": 1, "duplicates": 1})
        equivalent = {**record, "observed_at": "2026-11-03T06:00:00Z"}
        self.assertEqual(self.client.post("/api/memories/import", json={"memories": [equivalent]}).json()["added"], 0)
        real = self.advance(self.create(use_demo=False))
        self.assertEqual(len(real["snapshot"]["memories"]), 1)
        self.assertFalse(real["snapshot"]["memories"][0]["is_demo"])
        self.assertTrue(all(m["is_demo"] for m in demo["snapshot"]["memories"]))
        memory_id = real["snapshot"]["memories"][0]["id"]
        self.assertEqual(self.client.delete(f"/api/memories/{memory_id}").status_code, 200)
        result = self.client.get(f"/api/branches/{real['id']}/export").json()
        self.assertEqual(result["snapshot"]["memories"], [])
        self.assertNotIn(memory_id, json.dumps(result["events"]))
        self.assertEqual(result["state"], real["state"])

    def test_profile_changes_only_affect_new_branches(self):
        old = self.create()
        updated = {"name": "鲍勃", "occupation": "设计师", "goal": "专注创作", "sleep_target": 9}
        self.assertEqual(self.client.put("/api/profile", json=updated).status_code, 200)
        new = self.create()
        self.assertNotEqual(old["snapshot"]["profile"], new["snapshot"]["profile"])
        saved = self.client.get(f"/api/branches/{old['id']}/export").json()
        self.assertEqual(saved["snapshot"], old["snapshot"])

    def test_reject_invalid_inputs_and_stale_mutations(self):
        invalid = {"source": "unknown", "content": "", "observed_at": "not a date"}
        self.assertEqual(self.client.post("/api/memories/import", json={"memories": [invalid]}).status_code, 422)
        b = self.create()
        self.assertEqual(self.client.post(f"/api/branches/{b['id']}/advance", json={"action": "invented", "expected_day": 0}).status_code, 422)
        done = self.advance(b, 7)
        self.assertEqual(self.client.post(f"/api/branches/{b['id']}/advance", json={"expected_day": 0}).status_code, 409)
        self.assertEqual(self.client.post(f"/api/branches/{b['id']}/advance", json={"expected_day": 7}).status_code, 409)
        self.assertEqual(done["state"]["day"], 7)
        self.assertEqual(self.client.get("/api/world").json()["memories"], [])

    def test_storage_survives_client_restart(self):
        b = self.advance(self.create(), 2)
        with TestClient(module.app) as another:
            self.assertEqual(another.get("/api/world").json()["branches"][0]["state"], b["state"])

    def test_full_auto_simulation_is_reproducible_and_uses_only_prior_state(self):
        response = self.client.post("/api/simulations/auto", json={"seed": 123})
        self.assertEqual(response.status_code, 201, response.text)
        first = response.json()
        second = self.client.post("/api/simulations/auto", json={"seed": 123}).json()
        self.assertEqual(first["state"]["day"], 7)
        self.assertEqual(first["summary"]["automatic_days"], 7)
        self.assertEqual(first["summary"]["manual_days"], 0)
        self.assertEqual(first["snapshot"]["memory_mode"], "demo")
        self.assertEqual(first["events"], second["events"])
        for event in first["events"]:
            expected = evaluate_actions(event["before"], first["snapshot"])
            self.assertEqual(event["decision_scores"], expected)
            self.assertEqual(event["action"], expected[0]["action"])
            self.assertEqual(sum(event["schedule"].values()), 24)
        self.assertEqual(self.client.get("/api/world").json()["memories"], [])

    def test_auto_prefers_imported_memory_without_changing_existing_branch(self):
        previous = self.advance(self.create(), 2)
        record = {"source": "work_assistant", "content": "希望集中工作", "observed_at": "2026-11-03", "type": "goal"}
        self.client.post("/api/memories/import", json={"memories": [record]})
        auto = self.client.post("/api/simulations/auto", json={}).json()
        self.assertEqual(auto["snapshot"]["memory_mode"], "imported")
        self.assertEqual(auto["snapshot"]["memories"][0]["content"], record["content"])
        self.assertFalse(auto["snapshot"]["memories"][0]["is_demo"])
        unchanged = self.client.get(f"/api/branches/{previous['id']}/export").json()
        self.assertEqual(unchanged["state"], previous["state"])
        self.assertEqual(unchanged["events"], previous["events"])

    def test_adaptive_policy_responds_to_explicit_sleep_target_and_energy(self):
        b = self.create(policy="adaptive")
        relaxed = deepcopy(b["snapshot"])
        strict = deepcopy(b["snapshot"])
        relaxed["profile"]["sleep_target"] = 6
        strict["profile"]["sleep_target"] = 9
        self.assertNotEqual(evaluate_actions(initial_state(), relaxed)[0]["action"],
                            evaluate_actions(initial_state(), strict)[0]["action"])
        tired = {**initial_state(), "energy": 20}
        self.assertEqual(evaluate_actions(tired, strict)[0]["action"], "rest")

    def test_local_web_and_cross_origin_protection(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("鲍勃的世界", response.text)
        self.assertEqual(self.client.get("/assets/build/app.js").status_code, 200)
        self.assertEqual(self.client.get("/assets/styles.css").status_code, 200)
        self.assertIn("script-src 'self'", response.headers["content-security-policy"])
        self.assertEqual(self.client.post("/api/branches", json={}, headers={"origin": "https://other.example"}).status_code, 403)
        self.assertEqual(self.client.post("/api/branches", json={}, headers={"origin": "http://testserver"}).status_code, 201)


if __name__ == "__main__":
    unittest.main()
