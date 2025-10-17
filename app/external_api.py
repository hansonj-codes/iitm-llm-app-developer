import requests
import time

from app.database_utils import get_task

def exponential_backoff_retry(func, max_retries=20, initial_delay=1, backoff_factor=2, *args, **kwargs):
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as exc :
            print(f"Attempt {attempt + 1} failed, retrying after delay...")
            print(f"Error: {exc}")
            if attempt == max_retries - 1:
                raise
            time.sleep(delay)
            delay *= backoff_factor

def exponential_backoff_jitter_retry(func, max_retries=20, initial_delay=1, backoff_factor=1.8, jitter=0.5, *args, **kwargs):
    import random
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            print(f"Attempt {attempt + 1} failed, retrying after delay...")
            print(f"Error: {exc}")
            if attempt == max_retries - 1:
                raise
            sleep_time = delay + random.uniform(-jitter, jitter)
            time.sleep(max(0, sleep_time))
            delay *= backoff_factor

def send_round_completion_notification(task: str) -> None:
    task_payload = get_task(task)
    submit_payload = {
        "email": task_payload.get("email"),
        "task": task,
        "round": task_payload.get("round"),
        "nonce": task_payload.get("nonce"),
        "repo_url": task_payload.get("repo_clone_url"),
        "commit_sha": task_payload.get("commit_hash"),
        "pages_url": task_payload.get("pages_url"),
    }
    evaluation_url = task_payload.get("evaluation_url")
    headers = {
        "Content-Type": "application/json",
    }
    def post_request():
        print(f"Sending round completion notification to {evaluation_url} for task {task}")
        print(f"Evaluation URL payload: {submit_payload}")
        response = requests.post(evaluation_url, json=submit_payload, headers=headers, timeout=10)
        # Safely print the response data
        print('Safely printing the response: ')
        try:
            print(response.text.encode('utf-8', errors='replace').decode('utf-8'))
        except Exception as exx:
            print(f"Printing response errored out. Error: {exx}")
        response.raise_for_status()
        return response

    success_response = exponential_backoff_retry(post_request)
    print(f"Successfully notified evaluation service for task {task}, response: {success_response.text}")


