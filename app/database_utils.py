import sqlite3
import os
from typing import Dict, Any, Optional
from contextlib import contextmanager
from datetime import datetime

# Database configuration from environment variables
DB_PATH = os.getenv("DB_PATH", "tasks.db")


@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # This enables column access by name
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def initialize_db():
    """
    Initialize the database with the tasks table.
    Call this function once when your application starts.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS tasks")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                ----------------------------- Task based fields
                task_id TEXT PRIMARY KEY,
                email TEXT,
                round INTEGER,
                nonce TEXT,
                brief TEXT,
                evaluation_url TEXT,
                checks TEXT DEFAULT '[]', -- JSON array of checklist items
                attachments TEXT DEFAULT '[]', -- JSON array of attachments
                ----------------------------- Data returned by LLM
                llm_output_path TEXT,
                created_files TEXT,
                commit_message TEXT,
                ----------------------------- Mutable fields for repository details
                commit_hash TEXT,
                ----------------------------- Time fields
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                -------------------------------------------------------------------------------------
                ----------------------------- Round 1 archive fields
                round1_email TEXT,
                round1_nonce TEXT,
                round1_brief TEXT,
                round1_evaluation_url TEXT,
                round1_checks TEXT DEFAULT '[]', -- JSON array of checklist items
                round1_attachments TEXT DEFAULT '[]', -- JSON array of attachments
                round1_llm_output_path TEXT,
                round1_created_files TEXT,
                round1_commit_message TEXT,
                round1_commit_hash TEXT,
                round1_created_at TIMESTAMP,
                round1_updated_at TIMESTAMP,
                -------------------------------------------------------------------------------------
                -------------------------------------------------------------------------------------
                ----------------------------- Immutable fields for repository details
                repo_name TEXT,
                repo_clone_url TEXT,
                base_path TEXT, -- Base folder where repos are stored
                owner TEXT,
                repo_local_path TEXT,
                pages_url TEXT
                -------------------------------------------------------------------------------------
            )
        """)
        
        # Create trigger to auto-update the updated_at timestamp
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS update_task_timestamp 
            AFTER UPDATE ON tasks
            FOR EACH ROW
            BEGIN
                UPDATE tasks SET updated_at = CURRENT_TIMESTAMP
                WHERE task_id = NEW.task_id;
            END
        """)
        print("Database initialized successfully")


def upsert_task(task_id: str, data: Dict[str, Any]) -> bool:
    """
    Insert or update task data in the database.
    
    Args:
        task_id: Unique identifier for the task (primary key)
        data: Dictionary containing the fields to update/insert
              Example: {"status": "completed", "result": "success"}
    
    Returns:
        bool: True if operation was successful
    
    Example usage:
        upsert_task("task_123", {"status": "pending"})
        upsert_task("task_123", {"status": "completed", "result": "Processing done"})
    """
    if not data:
        raise ValueError("Data dictionary cannot be empty")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Build the column names and placeholders
        columns = list(data.keys())
        placeholders = ["?" for _ in columns]
        
        # Build the UPDATE clause for ON CONFLICT
        update_clause = ", ".join([f"{col} = excluded.{col}" for col in columns])
        
        # SQL query with UPSERT (INSERT ... ON CONFLICT)
        query = f"""
            INSERT INTO tasks (task_id, {', '.join(columns)})
            VALUES (?, {', '.join(placeholders)})
            ON CONFLICT(task_id) 
            DO UPDATE SET {update_clause}
        """
        
        values = [task_id] + [data[col] for col in columns]
        cursor.execute(query, values)
        
    return True


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve task data from the database by task_id.
    
    Args:
        task_id: Unique identifier for the task
    
    Returns:
        Dict containing all task data, or None if task doesn't exist
    
    Example usage:
        task = get_task("task_123")
        if task:
            print(f"Status: {task['status']}")
            print(f"Result: {task['result']}")
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        
        if row:
            # Convert sqlite3.Row to dictionary
            return dict(row)
        return None

def archive_task_round_01(task_id: str) -> bool:
    """
    Archive the current round of a task by copying current fields to round1_ fields.
    
    Args:
        task_id: Unique identifier for the task
    
    Returns:
        bool: True if operation was successful, False if task does not exist
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Check if task exists
        cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        if not row:
            return False
        
        # Prepare the UPDATE statement to copy current fields to round1_ fields
        update_query = """
            UPDATE tasks
            SET 
                round1_email = email,
                round1_nonce = nonce,
                round1_brief = brief,
                round1_evaluation_url = evaluation_url,
                round1_checks = checks,
                round1_attachments = attachments,
                round1_llm_output_path = llm_output_path,
                round1_created_files = created_files,
                round1_commit_message = commit_message,
                round1_commit_hash = commit_hash,
                round1_created_at = created_at,
                round1_updated_at = updated_at
            WHERE task_id = ?
        """
        
        cursor.execute(update_query, (task_id,))
        
    return True

def parse_db_timestamp(timestamp_str: str) -> Optional[Any]:
    """
    Parse a timestamp string from the database into a Python datetime object.
    
    Args:
        timestamp_str: Timestamp string in 'YYYY-MM-DD HH:MM:SS' format
    """
    if not timestamp_str:
        return None
    try:
        return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

# Example usage in FastAPI
if __name__ == "__main__":
    from .common_utils import get_current_utc_time
    import time

    # Initialize database (do this once at app startup)
    initialize_db()
    
    # Example 1: Create a new task
    print("\n--- Example 1: Creating new task ---")
    upsert_task("task_001", {
        "status": "pending",
        "result": None,
        "error_message": None,
        "created_at": get_current_utc_time(),
        "updated_at": get_current_utc_time(),
    })
    print("Task created")
    
    # Example 2: Retrieve the task
    time.sleep(2)  # Just to ensure timestamp difference
    print("\n--- Example 2: Retrieving task ---")
    task = get_task("task_001")
    print(f"Task data: {task}")
    print(f"Created at: {task['created_at']}, Updated at: {task['updated_at']}")
    print(f"Created at: {type(task['created_at'])}, Updated at: {type(task['updated_at'])}")
    
    # Example 3: Update only specific fields
    print("\n--- Example 3: Updating task status ---")
    upsert_task("task_001", {"status": "processing"})
    task = get_task("task_001")
    print(f"Updated task: {task}")
    
    # Example 4: Update with result
    print("\n--- Example 4: Completing task ---")
    upsert_task("task_001", {
        "status": "completed",
        "result": "Task processed successfully"
    })
    task = get_task("task_001")
    print(f"Completed task: {task}")
    
    # Example 5: Handle error case
    print("\n--- Example 5: Task with error ---")
    upsert_task("task_002", {
        "status": "failed",
        "error_message": "Connection timeout"
    })
    task = get_task("task_002")
    print(f"Failed task: {task}")
    
    # Example 6: Non-existent task
    print("\n--- Example 6: Non-existent task ---")
    task = get_task("task_999")
    print(f"Non-existent task: {task}")
