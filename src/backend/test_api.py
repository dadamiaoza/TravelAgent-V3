"""Test trip API endpoints on port 8001."""
import requests

BASE = "http://127.0.0.1:8001/api/v1"

# Test 1: Create trip via API
print("[1] POST /trips...")
r = requests.post(f"{BASE}/trips", json={
    "destination": "杭州", "start_date": "2026-07-01",
    "end_date": "2026-07-02", "people_count": 1
}, timeout=10)
assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
data = r.json()
trip_id = data["id"]
print(f"    OK: ID={trip_id}, Dst={data['destination']}, Days={len(data['days'])}")
assert len(data["days"]) == 2

# Test 2: Get trip
print(f"[2] GET /trips/{trip_id}...")
r = requests.get(f"{BASE}/trips/{trip_id}", timeout=5)
assert r.status_code == 200, f"Expected 200, got {r.status_code}"
print("    OK")

# Test 3: List trips
print("[3] GET /trips...")
r = requests.get(f"{BASE}/trips", timeout=5)
assert r.status_code == 200
print(f"    OK: Count={len(r.json())}")

print("All API tests passed!")
