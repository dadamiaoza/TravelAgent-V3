"""Self-hosting test: start server, test all endpoints, stop server."""
import subprocess
import time
import sys

PORT = 8001
BASE = f"http://127.0.0.1:{PORT}/api/v1"

# Start server
print("Starting server...")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
    stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True
)
time.sleep(4)

try:
    import requests

    # Test 1: Health
    r = requests.get(f"{BASE}/health", timeout=5)
    print(f"[1] Health: {r.status_code} - {r.json()['status']}")
    assert r.status_code == 200

    # Test 2: Create trip
    payload = {
        "destination": "杭州",
        "start_date": "2026-07-01",
        "end_date": "2026-07-02",
        "people_count": 1,
    }
    r = requests.post(f"{BASE}/trips", json=payload, timeout=10)
    print(f"[2] POST trips: {r.status_code}")
    if r.status_code != 201:
        print(f"    ERROR: {r.text}")
        sys.exit(1)
    data = r.json()
    trip_id = data["id"]
    print(f"    ID={trip_id}, Days={len(data['days'])}")
    assert len(data["days"]) == 2

    # Test 3: Get trip
    r = requests.get(f"{BASE}/trips/{trip_id}", timeout=5)
    print(f"[3] GET trip: {r.status_code}")
    assert r.status_code == 200

    # Test 4: List trips
    r = requests.get(f"{BASE}/trips", timeout=5)
    print(f"[4] GET trips list: {r.status_code}, Count={len(r.json())}")
    assert r.status_code == 200

    print("\nAll API tests passed!")

except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)

finally:
    proc.terminate()
    proc.wait(timeout=5)
