import base64
import xml.etree.ElementTree as ET
from typing import Generator
from pathlib import Path

from .database_utils import upsert_task

def is_valid_xml(text):
    try:
        ET.fromstring(text)
        return True
    except ET.ParseError:
        return False

def files_parse(xml_data: str) -> Generator[dict, None, None]:
    """
    Parse a <files> XML and yield each file's metadata and content.

    Yields dictionaries of the form:
        {
            "path": str,
            "content": str,
            "encoding": Optional[str],
            "mime": Optional[str]
        }
    """
    root = ET.fromstring(xml_data)

    for file_elem in root.findall("file"):
        path = file_elem.get("path")
        encoding = file_elem.get("encoding")
        mime = file_elem.get("mime")

        # Extract inner text including CDATA contents (as raw string)
        content = (file_elem.text or "").strip()

        yield {
            "path": path,
            "content": content,
            "encoding": encoding,
            "mime": mime,
        }

def create_files_from_response(task: str, xml_file_path: str | Path, repo_path: str | Path, additional_exclude_files: list[str] | None = None) -> list[str]:
    repo_path = Path(repo_path)
    created_files = []
    for file_details in files_parse(open(xml_file_path, 'r').read()):

        # Handle file path and folder creation if necessary
        file_path_relative = file_details['path']
        file_path = repo_path / file_path_relative
        folder_path = file_path.parents[0]
        folder_path.mkdir(parents=True, exist_ok=True)

        # If file is LICENSE, skip
        if file_path.name == "LICENSE":
            continue

        # if file is "commit_message", then update the task in DB
        if file_path.name == "commit_message":
            commit_message = file_details['content']
            upsert_task(task, {"commit_message": commit_message})
            continue

        if file_path.name in (additional_exclude_files or []):
            continue

        # Handle encoding if necessary
        if file_details['encoding'] == 'base64':
            file_content = base64.b64decode(file_details['content'])
        else:
            file_content = file_details['content'].encode('utf-8')

        with open(file_path, 'wb') as f:
            f.write(file_content)
        created_files.append(str(file_path_relative))
        print(f"Created file: {file_path_relative}")
    
    return created_files
    
