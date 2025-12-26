import subprocess
import concurrent.futures
import time
import os

TOTAL_SESSIONS = 10
MAX_CONCURRENT = 5
SCRIPT_PATH = "run_ad_clicker.py"

def run_session(session_id):
    """Run a single ad clicker session."""
    print(f"[Session {session_id}] Starting...")
    try:
        result = subprocess.run(
            ["python", SCRIPT_PATH],
            capture_output=True,
            text=True,
            timeout=600  # 10 min timeout per session, adjust as needed
        )
        print(f"[Session {session_id}] Finished with return code {result.returncode}")
        if result.returncode != 0:
            print(f"[Session {session_id}] stderr: {result.stderr[:500]}")
        return session_id, result.returncode
    except subprocess.TimeoutExpired:
        print(f"[Session {session_id}] Timed out")
        return session_id, -1
    except Exception as e:
        print(f"[Session {session_id}] Error: {e}")
        return session_id, -1

def main():
    print(f"Running {TOTAL_SESSIONS} sessions, {MAX_CONCURRENT} at a time...")
    start_time = time.time()
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = {executor.submit(run_session, i): i for i in range(1, TOTAL_SESSIONS + 1)}
        for future in concurrent.futures.as_completed(futures):
            session_id, return_code = future.result()
            results.append((session_id, return_code))
    
    elapsed = time.time() - start_time
    success = sum(1 for _, rc in results if rc == 0)
    print(f"\n=== Batch Complete ===")
    print(f"Total sessions: {TOTAL_SESSIONS}")
    print(f"Successful: {success}")
    print(f"Failed: {TOTAL_SESSIONS - success}")
    print(f"Time elapsed: {elapsed:.1f}s")

if __name__ == "__main__":
    main()
