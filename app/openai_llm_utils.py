import os
import sys
import time
import json
from typing import List, Tuple, Optional

from datauri import DataURI
import requests

from app.database_utils import get_task
from app.xml_utils import texts_to_xml_cdata

def call_response_api(
        openai_model: str,
        openai_api_key: str,
        openai_api_url: str,
        openai_max_output_tokens: int,
        openai_api_request_timeout: int,
        conversation: List[dict],
        response_id: str = None
    ) -> dict:
    payload = {
        "model": openai_model,
        "input": conversation,
        "max_output_tokens": openai_max_output_tokens,
        "reasoning": {"effort": "minimal"}
    }
    if response_id is not None:
        payload['previous_response_id'] = response_id
    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(openai_api_url, headers=headers, json=payload, timeout=openai_api_request_timeout)
    response.raise_for_status()
    return response.json()


def extract_text_and_finish_reason(response_json: dict) -> Tuple[str, str, Optional[str]]:
    """
    The Response API may expose finish information under output[].status.
    This function extracts the text chunks and the finish reason from the response JSON.
    """

    text_chunks = []
    finish_reason = None

    response_id = response_json.get("id", None)
    if "output" in response_json:
        for block in response_json["output"]:
            finish_reason = finish_reason or block.get("status")
            for piece in block.get("content", []):
                if piece.get("type") == "output_text":
                    text_chunks.append(piece.get("text", ""))

    return response_id, "".join(text_chunks), finish_reason


def request_llm_and_get_output(system_prompt: str, user_prompt: str) -> str:

    # Load environment variables
    openai_model = os.getenv("OPENAI_MODEL")
    openai_max_output_tokens = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS"))
    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_api_url = os.getenv("OPENAI_API_URL")
    openai_api_request_timeout = int(os.getenv("OPENAI_API_REQUEST_TIMEOUT"))
    openai_max_continuations = int(os.getenv("OPENAI_MAX_CONTINUATIONS"))

    if not all([openai_model, openai_max_output_tokens, openai_api_key, openai_api_url]):
        print("Error: Missing one or more required environment variables for OpenAI API.", file=sys.stderr)
        raise RuntimeError("Missing OpenAI API configuration.")
    
    conversation = [
        {
            "role": "system",
            "content": [
                {
                    "type": "input_text",
                    "text": system_prompt
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": user_prompt,
                }
            ],
        },
    ]

    continuation_attempts = 0
    full_text = ""

    response_id = None
    start_time = time.time()
    while continuation_attempts <= openai_max_continuations:
        resp_json = call_response_api(
            openai_model, openai_api_key, openai_api_url,
            int(openai_max_output_tokens), int(openai_api_request_timeout),
            conversation, response_id
        )
        response_id, chunk, finish_reason = extract_text_and_finish_reason(resp_json)
        full_text += chunk

        if finish_reason and finish_reason.lower() != "completed":
            continuation_attempts += 1
            new_conversation = []
            new_conversation.append(
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Please continue exactly where you left off."}],
                }
            )
            time.sleep(0.1)  # polite backoff
            continue

        break
    end_time = time.time()
    if finish_reason and finish_reason.lower() != "completed":
        print(f"Warning: LLM response finished with reason '{finish_reason}' after {continuation_attempts} continuations.")
    print(f"LLM response time: {end_time - start_time:.2f} seconds")
    return full_text.strip()

def default_system_prompt() -> str:
    system_prompt =\
"""
You are an expert full-stack developer specializing in creating production-ready web applications. Your core strengths include:

## Your Expertise
- Writing clean, well-commented code
- Building complete, functional applications without placeholders or TODOs
- Selecting appropriate libraries and tools for each task
- Creating professional documentation and README files
- Ensure that you do not use deprecated libraries or functions
- Use 3rd party libraries wherever possible, fetching them from CDNs but only include <script> and <link> tags, with no integrity, no crossorigin, no SRI attributes.


## Response Format Requirements
When asked to generate project files:
1. You MUST respond with ONLY valid XML containing file data
2. Your response MUST start with <files> and end with </files>
3. Do NOT include any explanatory text, greetings, or commentary outside the XML tags
4. Do NOT use phrases like "Here's the code..." or "I've created..."
5. Your entire response is parsed by an automated XML parser

## Code Quality Standards
- Write complete, working code - never use placeholder comments like "// Add logic here"
- Include concise, meaningful comments explaining complex logic
- Use appropriate error handling and edge case management
- Ensure all external dependencies are loaded from CDNs when specified
- Make code readable and maintainable

## File Generation Guidelines
- Use CDATA sections for all text-based code files (HTML, CSS, JS, JSON, Markdown, etc.)
- Use base64 encoding for binary files (images, fonts, etc.) when needed
- Each file must have a "path" attribute indicating its location in the project structure
- Create proper project documentation (README.md) with setup and usage instructions
- Include appropriate license files when requested

## Problem-Solving Approach
- Understand the complete requirements before generating code
- Choose the most appropriate and reliable solutions
- Implement features that actually work, not just demonstrations
- Consider the deployment target and constraints
- Test edge cases mentally before outputting code

Remember: Your output will be directly parsed and deployed. Code quality and correctness are paramount.
"""
    return system_prompt

def construct_user_prompt_for_round_01(task: str) -> str:
    user_prompt_template =\
"""
## Task
 - Create a javascript website that can be as-is deployed by Github Pages.

## Task brief
<<brief>>

## Checks - The website will be evaluated based on the below given checks via Playwright
<<checks>>

## Input attachements available in the repository:
<<attachments>>

## Content of input attachments that are text based, encoded in XML tags:
<<attachments_text_xml>>

## What files to return and not to return:
 - Return the website's code files and README.md
 - Return a file "commit_message" that contains appropriate commit message
 - Do NOT return LICENSE or any attachment file that was passed
 - Do NOT return any text outside XML tags as the output will be parsed by a XML parser

## Repo Details
 - repo url is: <<repo_url>>
"""
    def make_list(items: List[str]) -> str:
        if not items:
            return " - None"
        return "\n".join(f" - {item}" for item in items)
    payload = get_task(task)
    brief_line = make_list([payload['brief'].strip()])
    checks_lines = make_list(json.loads(payload['checks']) if payload['checks'] else [])
    loaded_attachments = json.loads(payload['attachments']) or []
    attachments_lines_list = []
    text_attachments_dict = {
        'text': [],
        'name': [],
        'mime_type': []
    }
    for ld_att in loaded_attachments:
        att_name = ld_att.get("name", "unnamed")
        print('constructing llm query, processing:', att_name)
        att_uri = DataURI(ld_att.get("url"))
        _mime_type = str(att_uri.mimetype)
        attachments_lines_list.append(f'path: {att_name}, mime_type: {_mime_type}')
        if _mime_type and _mime_type.startswith('text'):
            text_attachments_dict['text'].append(att_uri.data.decode('utf-8'))
            text_attachments_dict['name'].append(att_name)
            text_attachments_dict['mime_type'].append(_mime_type)

    attachments_lines = make_list(attachments_lines_list)
    if len(text_attachments_dict['name']) > 0:
        attachments_text_data = texts_to_xml_cdata(
            text_list=text_attachments_dict['text'],
            name_list=text_attachments_dict['name'],
            mime_type_list=text_attachments_dict['mime_type']
        )
    else:
        attachments_text_data = '<attachments>\n</attachments>'
    repo_url = payload.get('repo_clone_url')
    user_prompt = user_prompt_template.replace("<<brief>>", brief_line)\
                                     .replace("<<checks>>", checks_lines)\
                                     .replace("<<attachments>>", attachments_lines)\
                                     .replace("<<attachments_text_xml>>", attachments_text_data)\
                                     .replace("<<repo_url>>", repo_url)
    print(user_prompt)
    return user_prompt


def construct_user_prompt_for_round_02(task: str) -> str:
    user_prompt_template =\
"""
## Task
 - Update the below given javascript website according to the Task brief
 - Make sure that the udpated website can be as-is deployed by Github Pages.
 - Only edit what is required, and make sure that existing flow is NOT broken.

## Task brief
<<brief>>

## Checks - The website will be evaluated based on the below given checks via Playwright
<<checks>>

## Input attachments available in the repository:
<<attachments>>

## Content of input attachments that are text based, encoded in XML tags:
<<attachments_text_xml>>

## What files to return and not to return:
 - Return the website's code files and README.md
 - Return a file "commit_message" that contains appropriate commit message
 - Do NOT return LICENSE or any attachment file that was passed
 - Do NOT return any text outside XML tags as the output will be parsed by a XML parser

## Current state of repository encoded in XML tags:
<<repo_files_xml>>
"""
    def make_list(items: List[str]) -> str:
        if not items:
            return " - None"
        return "\n".join(f" - {item}" for item in items)
    payload = get_task(task)
    brief_line = make_list([payload['brief'].strip()])
    checks_lines = make_list(json.loads(payload['checks']) if payload['checks'] else [])
    loaded_attachments_round_01 = json.loads(payload['round1_attachments']) or []
    loaded_attachments_round_02 = json.loads(payload['attachments']) or []
    loaded_attachments = loaded_attachments_round_01 + loaded_attachments_round_02
    attachments_lines_list = []
    text_attachments_dict = {
        'text': [],
        'name': [],
        'mime_type': []
    }
    for ld_att in loaded_attachments:
        att_name = ld_att.get("name", "unnamed")
        print('constructing llm query, processing:', att_name)
        att_uri = DataURI(ld_att.get("url"))
        _mime_type = str(att_uri.mimetype)
        attachments_lines_list.append(f'path: {att_name}, mime_type: {_mime_type}')
        if _mime_type and _mime_type.startswith('text'):
            text_attachments_dict['text'].append(att_uri.data.decode('utf-8'))
            text_attachments_dict['name'].append(att_name)
            text_attachments_dict['mime_type'].append(_mime_type)

    attachments_lines = make_list(attachments_lines_list)
    if len(text_attachments_dict['name']) > 0:
        attachments_text_data = texts_to_xml_cdata(
            text_list=text_attachments_dict['text'],
            name_list=text_attachments_dict['name'],
            mime_type_list=text_attachments_dict['mime_type']
        )
    else:
        attachments_text_data = '<attachments>\n</attachments>'
    repo_files_xml = open(f"{payload.get('round1_llm_output_path')}", 'r', encoding='utf-8').read()
    user_prompt = user_prompt_template.replace("<<brief>>", brief_line)\
                                     .replace("<<checks>>", checks_lines)\
                                     .replace("<<attachments>>", attachments_lines)\
                                     .replace("<<attachments_text_xml>>", attachments_text_data)\
                                     .replace("<<repo_files_xml>>", repo_files_xml)
    print(user_prompt)
    return user_prompt
