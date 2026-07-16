import json
import os
import re
import time
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime as date_ref
from io import BytesIO
from pathlib import Path
from typing import Literal, TypedDict

import httpx
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langgraph.graph import END, START, StateGraph
from lxml import etree
from markdownify import markdownify as md
from pydantic import BaseModel, Field

DEBUG = True
README_FILENAME = "README.md"
STATE_FILENAME = "state.json"
DIAGRAM_FLOW_FILENAME = "diagram.png"
DASHBOARD_FILENAME = "dashboard.md"
HTTP_REQUEST_TIMEOUT = 240
DEFAULT_ENCODING = "utf-8"
LLM_API_KEY = os.environ["NVIDIA_BUILD_API_KEY"]
LLM_API_RATE_MAX_REQUEST_BY_MINUTES = 40
LLM_API_RATE_COOLDOWN_DELAY_IN_SECONDS = 65
LLM_API_MAX_TRY_CALL = 4
MAX_LOOP_ITERATION_COUNT = 2


class NodeLoggerCallback(BaseCallbackHandler):
    def __init__(self, node_names: set):
        super().__init__()
        self.node_names = node_names  # the graph's node names
        self._active_runs = {}

    def on_chain_start(self, serialized, inputs, **kwargs):
        name = kwargs.get("run_name") or kwargs.get("name", "unknown")
        if name in self.node_names:
            run_id = kwargs.get("run_id")
            name = name.replace("_", " ")
            name = name.title()
            self._active_runs[run_id] = name
            print(f"[{time.strftime('%H:%M:%S')} - {name}] Entering node.")

    def on_chain_end(self, outputs, **kwargs):
        run_id = kwargs.get("run_id")
        name = self._active_runs.pop(run_id, "unknown")
        if name != "unknown":
            print(f"[{time.strftime('%H:%M:%S')} - {name}] Exit node.")


@dataclass
class HeaderInfo:
    name: str
    spec_location: str | None
    rfc_location: str | None
    rfc_or_spec_content: str | None
    header_direction: str = "UNKNOWN"  # REQUEST / RESPONSE / UNKNOWN
    is_security: bool = False
    is_already_classified: bool = False  # Use to identify a header for which information were already identified
    is_security_classification_explanation: str = ""
    is_security_classification_validation_explanation: str = ""


class PipelineState(TypedDict):
    headers_info_collection: dict[str, HeaderInfo]
    last_update: str
    oshp_headers_missed: list[str]
    loop_interation_count: int
    http_response_headers_explicitly_ignored: list[str]


class HeaderDirection(BaseModel):
    type: Literal["REQUEST", "RESPONSE", "UNKNOWN"] = Field(description="Whether the HTTP header is a REQUEST header, a RESPONSE header, or UNKNOWN if it cannot be determined")


class SecurityClassification(BaseModel):
    is_security: bool = Field(description="Whether the header is security-related")
    reason: str = Field(description="Short justification, max 20 words")


class ClassificationReview(BaseModel):
    agree: bool = Field(description="Whether the reviewer agrees with the prior classifier's is_security verdict")
    reason: str = Field(description="Short justification about why the reviewer disagrees, max 20 words, empty string if agree is true")


class DataclassEncoder(json.JSONEncoder):
    def default(self, obj):
        if is_dataclass(obj):
            return asdict(obj)
        return super().default(obj)


def extract_header_section(rfc_content: str, header_name: str) -> str:
    # Find the section mentioning the header
    lines = rfc_content.split("\n")
    relevant_lines = []

    for i, line in enumerate(lines):
        if header_name.lower() in line.lower():
            # grab surrounding context (50 lines before and after)
            start = max(0, i - 50)
            end = min(len(lines), i + 50)
            relevant_lines = lines[start:end]
            break

    return "\n".join(relevant_lines)


def parse_iana_xml(xml_content: bytes) -> dict:
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        dtd_validation=False,
        load_dtd=False,
    )
    root = etree.parse(BytesIO(xml_content), parser=parser).getroot()
    NS = "http://www.iana.org/assignments"
    headers = {}
    for record in root.iter(f"{{{NS}}}record"):
        name_el = record.find(f"{{{NS}}}value")
        if name_el is None or not name_el.text:
            continue
        name = name_el.text.strip()
        xref_info = {"type": "NA"}
        for xref in record.iterfind(f"{{{NS}}}xref"):
            xref_type = xref.get("type", "")
            if xref_type == "rfc":
                # We want RFC in priority
                xref_id = xref.get("data")
                xref_info = {"type": xref_type, "id": xref_id}
                break
            elif xref_type in ["uri", "draft"]:
                xref_id = xref.get("data")
                if xref_type == "draft":
                    # Handle the case for DRAFT RFC for which the ID is not the same than the target URL
                    # ID in the XML         => RFC-ietf-httpbis-unencoded-digest-05
                    # ID to use for the URL => draft-ietf-httpbis-unencoded-digest-05
                    xref_id = "draft" + xref_id[3:]
                xref_info = {"type": xref_type, "id": xref_id}
        headers[name] = xref_info
    return headers


def handle_structured_model_call(model_name: str, structured_model, messages: list) -> BaseModel | None:
    # Uses with_structured_output (NIM guided decoding), so the model output is
    # constrained to the schema at generation time and cannot be invalid JSON,
    # miss required fields, or contain leading/trailing prose.
    result = None
    for _ in range(LLM_API_MAX_TRY_CALL):
        try:
            result = structured_model.invoke(messages)
            if result is not None:
                break
        except Exception as e:
            error_msg_str = str(e)
            if DEBUG:
                print(f"⚠️ {error_msg_str}")
            if "429" in error_msg_str or "500" in error_msg_str:
                time.sleep(LLM_API_RATE_COOLDOWN_DELAY_IN_SECONDS)
            else:
                raise
    return result


def init_http_response_headers_explicitly_ignored_collection(state: PipelineState) -> PipelineState:
    http_response_headers_expliclity_ignored_collection = []
    # Load the list of headers to ignore from the README file from a dedicated section
    headers_table_extraction_regex = r"<!--IGNORED_HEADERS_SECTION_START-->(.*)<!--IGNORED_HEADERS_SECTION_END-->"
    with open(README_FILENAME, mode="r", encoding=DEFAULT_ENCODING) as f:
        content = f.read()
    table_lines = re.findall(headers_table_extraction_regex, content, re.IGNORECASE | re.DOTALL)
    for line in table_lines[0].split("\n"):
        if "`" not in line:
            continue
        header_name = line.split("|")[1].strip("` ").upper()
        http_response_headers_expliclity_ignored_collection.append(header_name)
    state["http_response_headers_explicitly_ignored"] = http_response_headers_expliclity_ignored_collection
    return state


def gather_http_header_names(state: PipelineState) -> PipelineState:
    headers_collections = state["headers_info_collection"]
    # Step 1: Use MDN data source
    source_url = "https://unpkg.com/@mdn/browser-compat-data/data.json"
    response = httpx.get(source_url, follow_redirects=True, timeout=HTTP_REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    headers = data["http"]["headers"]
    for header_name in headers:
        header_name_upper = header_name.upper()
        # Skip header already known and that was already classified
        if header_name_upper in headers_collections and headers_collections[header_name_upper].is_already_classified:
            continue
        # If a spec url is available then use it in priority
        spec_url = None
        if "spec_url" in headers[header_name]["__compat"]:
            ref = headers[header_name]["__compat"]["spec_url"]
            if type(ref) is list and len(ref) > 0:
                spec_url = str(ref[0]).strip()
            else:
                spec_url = str(ref).strip()
        if header_name_upper in headers_collections:
            header_info = headers_collections[header_name_upper]
            header_info.spec_location = spec_url
        else:
            header_info = HeaderInfo(header_name_upper, spec_url, None, None, "UNKNOWN", False, False)
        if header_name_upper in state["http_response_headers_explicitly_ignored"]:
            header_info.header_direction = "RESPONSE"
            header_info.is_already_classified = True
            header_info.is_security = True
            header_info.rfc_or_spec_content = ""
            header_info.is_security_classification_explanation = "Header explicitly ignored"
            header_info.is_security_classification_validation_explanation = ""
        headers_collections[header_name_upper] = header_info
    # Step 2: Use IANA data source
    source_url = "https://www.iana.org/assignments/http-fields/http-fields.xml"
    rfc_url_template = "https://www.rfc-editor.org/rfc/%s.txt"
    rfc_draft_url_template = "https://www.ietf.org/archive/id/%s.txt"
    response = httpx.get(source_url, follow_redirects=True, timeout=HTTP_REQUEST_TIMEOUT)
    response.raise_for_status()
    headers_data = parse_iana_xml(response.content)
    for header_name, rfc_spec_info in headers_data.items():
        header_name_upper = header_name.upper()
        # Skip header already known and that were already classified
        if header_name_upper in headers_collections and headers_collections[header_name_upper].is_already_classified:
            continue
        if rfc_spec_info["type"] == "rfc":
            rfc_url = rfc_url_template % rfc_spec_info["id"]
        elif rfc_spec_info["type"] == "uri":
            rfc_url = rfc_spec_info["id"]
        elif rfc_spec_info["type"] == "draft":
            rfc_url = rfc_draft_url_template % rfc_spec_info["id"]
        else:
            rfc_url = None
        if header_name_upper in headers_collections:
            header_info = headers_collections[header_name_upper]
        else:
            header_info = HeaderInfo(header_name_upper, None, None, None, "UNKNOWN", False, False)
        if rfc_url is not None:
            header_info.rfc_location = rfc_url.strip()
        headers_collections[header_name_upper] = header_info
    # Delete the header named "*"
    if "*" in headers_collections:
        del headers_collections["*"]
    # Capture the RFC or SPEC content for all headers
    for header_name, header_info in headers_collections.items():
        # Prefer the RFC over the SPEC
        if header_info.rfc_location is not None:
            target_url = header_info.rfc_location
        elif header_info.spec_location is not None:
            target_url = header_info.spec_location
        else:
            target_url = None
        if target_url is not None:
            response = httpx.get(target_url, follow_redirects=True, timeout=HTTP_REQUEST_TIMEOUT)
            response.raise_for_status()
            header_info.rfc_or_spec_content = response.text
            # Convert the HTML to markdown the help a model to process the RFC/Spec data
            if "<!doctype html>" in header_info.rfc_or_spec_content.lower():
                header_info.rfc_or_spec_content = md(header_info.rfc_or_spec_content)
            header_info.rfc_or_spec_content = header_info.rfc_or_spec_content.strip()
    # Remove all headers for which there is no specification or RFC data captured as there is no information available by MDN/IANA to classify it
    headers_collections_filtered = {header_name: header_info for header_name, header_info in headers_collections.items() if header_info.rfc_or_spec_content is not None and len(header_info.rfc_or_spec_content) > 0}
    state["headers_info_collection"] = headers_collections_filtered
    return state


def identify_http_header_directions_without_model(state: PipelineState) -> PipelineState:
    mdn_data_folder = Path("mdn/content-main/files/en-us/web/http/reference/headers")
    headers_collections = state["headers_info_collection"]
    if not mdn_data_folder.exists() or not mdn_data_folder.is_dir():
        raise Exception("MDN folder does not exists!")
    for header_name, header_info in headers_collections.items():
        if header_info.is_already_classified or header_info.header_direction in ["RESPONSE", "REQUEST"]:
            continue
        header_mdn_data_file_path = mdn_data_folder / header_name.lower() / "index.md"
        if header_mdn_data_file_path.exists():
            with open(header_mdn_data_file_path, mode="r", encoding=DEFAULT_ENCODING) as f:
                content = f.read().lower()
            if 'glossary("response header")' in content or 'glossary("cors-safelisted response header")' in content:
                header_info.header_direction = "RESPONSE"
            elif 'glossary("request header")' in content or 'glossary("cors-safelisted request header")' in content:
                header_info.header_direction = "REQUEST"
            else:
                header_info.header_direction = "UNKNOWN"
            headers_collections[header_name] = header_info
        if header_info.rfc_or_spec_content is not None and header_info.header_direction == "UNKNOWN":
            # If the header is not know by MDN then try to find marker in the RFC/SPEC if available.
            # I do not use a model to read the RFC as first method due to the number of headers to handle so RFC to process.
            # I use this technics as a shortcut prior to use a model
            rfc_content_lower = header_info.rfc_or_spec_content.lower()
            if f"{header_name.lower()} response header" in rfc_content_lower:
                header_info.header_direction = "RESPONSE"
            elif f"{header_name.lower()} request header" in rfc_content_lower:
                header_info.header_direction = "REQUEST"
            else:
                header_info.header_direction = "UNKNOWN"
            headers_collections[header_name] = header_info
    state["headers_info_collection"] = headers_collections
    return state


def identify_http_header_directions_with_model(state: PipelineState) -> PipelineState:
    # For every header for which the direction was not identified then use a model to read the rfc of the spec
    # to determine the direction
    model_name = "meta/llama-3.1-8b-instruct"
    model_maximum_context_length = 131072  # 128000 * 1024 => See https://docs.api.nvidia.com/nim/reference/meta-llama-3_1-8b#new-capabilities
    max_completion_tokens_wanted = 50
    system_prompt = """
You are a classifier that reads a RFC and an HTTP header name, and determines if the header is a REQUEST or RESPONSE header.

RULES:
1. Use only the RFC content provided as source of truth.
2. If the header can be used in both REQUEST and RESPONSE, classify it as RESPONSE.
3. If you cannot determine the type, classify it as UNKNOWN.

Return only raw JSON, no markdown, no backticks, no explanation.
Return exactly one of:
{"type": "REQUEST"}
{"type": "RESPONSE"}
{"type": "UNKNOWN"}

The user message will have this format:
Header name: `name of the header`
RFC content: `content of the RFC`
"""
    model = ChatNVIDIA(model=model_name, api_key=LLM_API_KEY, temperature=0.01, timeout=HTTP_REQUEST_TIMEOUT, max_completion_tokens=max_completion_tokens_wanted)
    structured_model = model.with_structured_output(HeaderDirection)
    headers_collections = state["headers_info_collection"]
    context_length_limit = (model_maximum_context_length - len(system_prompt)) - max_completion_tokens_wanted
    for header_name, header_info in headers_collections.items():
        if header_info.is_already_classified or header_info.header_direction in ["RESPONSE", "REQUEST"]:
            continue
        if header_info.rfc_or_spec_content is not None:
            user_prompt = f"""
Header name: `{header_name}`.
RFC content: `{extract_header_section(header_info.rfc_or_spec_content, header_name)}`.
"""
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            direction = handle_structured_model_call(model_name, structured_model, messages)
            if direction is None:
                # All attempts failed to produce a usable response; leave unclassified for a later run
                continue
            header_info.header_direction = direction.type
            # If the model cannot determine the header direction using a subset of the RFC then give a try with the full RFC content
            # using all the content that can fit in the context window of the model
            if header_info.header_direction not in ["RESPONSE", "REQUEST"]:
                user_prompt = f"""
Header name: `{header_name}`.
RFC content: `{header_info.rfc_or_spec_content[:context_length_limit]}`.
"""
                messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                direction = handle_structured_model_call(model_name, structured_model, messages)
                if direction is not None:
                    header_info.header_direction = direction.type
            headers_collections[header_name] = header_info
    state["headers_info_collection"] = headers_collections
    return state


def identify_http_header_security_relation_with_model(state: PipelineState) -> PipelineState:
    model_name = "nvidia/llama-3.3-nemotron-super-49b-v1"
    model_maximum_context_length = 131072  # 128000 * 1024 => See https://docs.api.nvidia.com/nim/reference/nvidia-llama-3_3-nemotron-super-49b-v1_5#model-overview
    max_completion_tokens_wanted = 200
    system_prompt = """
  You are a classifier that reads an RFC/specification and the name of an HTTP RESPONSE header, and determines whether the header is SECURITY-RELATED.

  Detailed thinking OFF.

  A header is SECURITY-RELATED if setting, enforcing, or omitting it has a direct impact on the security posture of the HTTP response — i.e. it does at least one of the following:
  - Mitigates a specific class of web attack (XSS, clickjacking, MIME-sniffing, CSRF, cache poisoning, protocol downgrade attacks, cross-origin data leakage, etc.)
  - Enforces transport security guarantees (e.g. requiring/upgrading to TLS)
  - Enforces an isolation, sandboxing, or cross-origin policy between the response and other origins
  - Restricts what a client/browser is permitted to do with the response (framing, MIME-type execution, referrer exposure, feature/permission access)
  - Protects or governs exposure of authentication/session artifacts (cookies, tokens)
  - Is explicitly framed by the RFC itself as a security or privacy mechanism (look for a "Security Considerations" section referencing this header)

  A header is NOT security-related if its purpose is limited to caching, content negotiation, compression, formatting, performance, or general application/protocol behavior with no direct security implication.

  RULES:
  1. Use only the RFC/spec content provided as source of truth for what the header does. Do not rely on prior knowledge of any external list (e.g. OWASP Secure Headers Project) of known "security headers" —
  decide strictly from the definition above and the text given.
  2. Give strong weight to an explicit "Security Considerations" section that names this header.
  3. If the provided content does not clearly describe the header's purpose, classify as false rather than guessing.
  4. Classify as true only if security is the header's PRIMARY purpose. If the header's primary purpose is something else (caching, content negotiation, compression, formatting, performance, general application/protocol behavior) and it merely has a secondary or indirect security effect, classify as false.
  5. If "Feedback from the validator agent" is non-empty, treat it as a specific, identified flaw in your prior verdict. Re-examine the RFC content in light of that flaw and change your verdict if the feedback is correct. Only keep your original verdict if you can explain why the feedback's objection does not hold against the RFC text. If the content is empty then ignore this rule.

  Return only raw JSON, no markdown, no backticks, no explanation.
  Return exactly one of:
  {"is_security": true, "reason": "short justification, max 20 words"}
  {"is_security": false, "reason": "short justification, max 20 words"}

  The user message will have this format:
  Header name: `name of the header`
  RFC content: `content of the RFC`
  Your prior verdict: `is_security=<true/false> — <your prior reason>`
  Feedback from the validator agent: `content of the feedback`
"""
    model = ChatNVIDIA(model=model_name, api_key=LLM_API_KEY, temperature=0.01, timeout=HTTP_REQUEST_TIMEOUT, max_completion_tokens=max_completion_tokens_wanted)
    structured_model = model.with_structured_output(SecurityClassification)
    headers_collections = state["headers_info_collection"]
    context_length_limit = (model_maximum_context_length - len(system_prompt)) - max_completion_tokens_wanted
    for header_name, header_info in headers_collections.items():
        if header_info.is_already_classified or header_info.header_direction != "RESPONSE":
            continue
        if header_info.rfc_or_spec_content is not None:
            user_prompt = f"""
Header name: `{header_name}`.
RFC content: `{header_info.rfc_or_spec_content[:context_length_limit]}`.
Your prior verdict: `is_security={header_info.is_security} - {header_info.is_security_classification_explanation}`.
Feedback from the validator agent: `{header_info.is_security_classification_validation_explanation}`.
"""
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            classification = handle_structured_model_call(model_name, structured_model, messages)
            if classification is None:
                # All attempts failed to produce a usable response; leave unclassified for a later run
                continue
            if DEBUG:
                print(f"[CLASSIFIER][{header_name}] {classification}")
            header_info.is_security = classification.is_security
            header_info.is_security_classification_explanation = classification.reason
            headers_collections[header_name] = header_info
    state["headers_info_collection"] = headers_collections
    return state


def determine_classification_state_for_non_response_header(state: PipelineState) -> PipelineState:
    headers_collections = state["headers_info_collection"]
    for header_name, header_info in headers_collections.items():
        if header_info.header_direction == "REQUEST":
            header_info.is_already_classified = True
            header_info.rfc_or_spec_content = ""  # Save space in the final json file
        elif header_info.header_direction == "UNKNOWN":
            header_info.is_already_classified = False
        headers_collections[header_name] = header_info
    state["headers_info_collection"] = headers_collections
    return state


def validate_classification_state_with_model(state: PipelineState) -> PipelineState:
    # Deliberately a different model family than the classifier's nvidia/llama-3.3-nemotron-super-49b-v1
    # (itself a Llama-3.3 derivative) so the "independent reviewer" isn't just the same weights re-rolled.
    model_name = "mistralai/mistral-medium-3.5-128b"
    model_maximum_context_length = 131072  # Empirically confirmed to accept requests at least this large on NVIDIA Build
    max_completion_tokens_wanted = 200
    system_prompt = """
  You are an independent reviewer that receives an HTTP response header, its RFC/spec content, and a prior classifier's verdict on whether the header is SECURITY-RELATED. Your job is to check that verdict against the RFC/spec content and the definition below, and say whether you agree or disagree. Do not simply defer to the prior explanation — re-derive the answer yourself from the content provided.

  Detailed thinking OFF.

  A header is SECURITY-RELATED if setting, enforcing, or omitting it has a direct impact on the security posture of the HTTP response — i.e. it does at least one of the following:
  - Mitigates a specific class of web attack (XSS, clickjacking, MIME-sniffing, CSRF, cache poisoning, protocol downgrade attacks, cross-origin data leakage, etc.)
  - Enforces transport security guarantees (e.g. requiring/upgrading to TLS)
  - Enforces an isolation, sandboxing, or cross-origin policy between the response and other origins
  - Restricts what a client/browser is permitted to do with the response (framing, MIME-type execution, referrer exposure, feature/permission access)
  - Protects or governs exposure of authentication/session artifacts (cookies, tokens)
  - Is explicitly framed by the RFC itself as a security or privacy mechanism (look for a "Security Considerations" section referencing this header)

  A header is NOT security-related if its purpose is limited to caching, content negotiation, compression, formatting, performance, or general application/protocol behavior with no direct security implication.

  RULES:
  1. Use only the "rfc_or_spec_content" field as source of truth for what the header does. Do not rely on prior knowledge of any external list (e.g. OWASP Secure Headers Project) of known "security headers".
  2. If "rfc_or_spec_content" is empty or does not clearly describe the header's purpose, you cannot verify the verdict: disagree if "is_security" is true (insufficient evidence to call it security-related), agree if "is_security" is false.
  3. Give strong weight to an explicit "Security Considerations" section that names this header.
  4. Treat "classification_explanation" as a claim to verify, not a fact — disagree if it is not actually supported by "rfc_or_spec_content".
  5. Your reason must state specifically what is wrong with the prior verdict. If your reasoning would instead support the prior verdict, set "agree" to true and leave reason empty - do not disagree with a justification that argues for agreement.
  6. If a header is indirectly influencing security then you must consider that the header is not directly security related.

  Return only raw JSON, no markdown, no backticks, no explanation.
  Return exactly one of:
  {"agree": true, "reason": ""}
  {"agree": false, "reason": "short justification about why you disagree, max 20 words"}

  The user message will have this format:
  ```
    {
        "name": "name of the HTTP response header in upper case",
        "is_security": "boolean indicating if the HTTP response header was classified as security related or not",
        "classification_explanation": "explanation about why the HTTP response header was considered a security related header or not",
        "rfc_or_spec_content": "abstract of the RFC for the HTTP response header"
    }
  ```
  """
    model = ChatNVIDIA(model=model_name, api_key=LLM_API_KEY, temperature=0.01, timeout=HTTP_REQUEST_TIMEOUT, max_completion_tokens=max_completion_tokens_wanted)
    structured_model = model.with_structured_output(ClassificationReview)
    context_length_limit = (model_maximum_context_length - len(system_prompt)) - max_completion_tokens_wanted
    headers_collections = state["headers_info_collection"]
    for header_name, header_info in headers_collections.items():
        if header_info.is_already_classified or header_info.header_direction != "RESPONSE":
            continue
        rfc_content = ""
        if header_info.rfc_or_spec_content is not None:
            rfc_content = header_info.rfc_or_spec_content[:context_length_limit]
        user_message = {"name": header_name, "is_security": header_info.is_security, "classification_explanation": header_info.is_security_classification_explanation, "rfc_or_spec_content": rfc_content}
        user_prompt = json.dumps(user_message)
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        review = handle_structured_model_call(model_name, structured_model, messages)
        if review is None:
            # All attempts failed to produce a usable response; leave unclassified for a later run
            continue
        if DEBUG:
            print(f"[REVIEWER][{header_name}] {review}")
        if review.agree:
            header_info.is_already_classified = True
            header_info.rfc_or_spec_content = ""  # Save space in the final json file
            header_info.is_security_classification_validation_explanation = ""
        else:
            header_info.is_already_classified = False
            header_info.is_security_classification_validation_explanation = review.reason
        headers_collections[header_name] = header_info
    state["headers_info_collection"] = headers_collections
    state["loop_interation_count"] = state["loop_interation_count"] + 1
    # Handle classifier <=> validator infinite conflict loop.
    # In this case consider the point of view of the validator as the right one
    if state["loop_interation_count"] >= MAX_LOOP_ITERATION_COUNT:
        for header_name, header_info in headers_collections.items():
            if header_info.header_direction != "RESPONSE" or header_info.is_already_classified:
                continue
            if header_info.is_security_classification_validation_explanation != "":  # Presence of disagreement
                print(f"[!] Forcing resolution of disputed header {header_name}: deferring to validator (classifier said is_security={header_info.is_security}).")
                header_info.is_security = not header_info.is_security
                header_info.is_already_classified = True
                header_info.rfc_or_spec_content = ""  # Save space in the final json file
                header_info.is_security_classification_validation_explanation = f"[Forced resolution] {header_info.is_security_classification_validation_explanation}"
                headers_collections[header_name] = header_info
        state["headers_info_collection"] = headers_collections
    return state


def identify_headers_missed_by_oshp(state: PipelineState) -> PipelineState:
    headers_collections = state["headers_info_collection"]
    oshp_headers_missed = []
    source_url = "https://raw.githubusercontent.com/OWASP/www-project-secure-headers/refs/heads/master/ci/headers_add.json"
    response = httpx.get(source_url, follow_redirects=False, timeout=HTTP_REQUEST_TIMEOUT)
    response.raise_for_status()
    oshp_headers = [hdr["name"].upper() for hdr in response.json()["headers"]]
    # Find security header not documented by OSHP
    for header_name, header_info in headers_collections.items():
        if header_info.header_direction == "RESPONSE" and header_info.is_security and header_name not in oshp_headers and header_name not in state["http_response_headers_explicitly_ignored"]:
            oshp_headers_missed.append(header_name)
    state["last_update"] = date_ref.now().strftime("%Y-%m-%d %H:%M:%S")
    state["oshp_headers_missed"] = oshp_headers_missed
    return state


def classification_is_over(state: PipelineState) -> str:
    headers_collections = state["headers_info_collection"]
    all_response_headers_are_classified = "yes"
    if state["loop_interation_count"] < MAX_LOOP_ITERATION_COUNT:
        for _, header_info in headers_collections.items():
            if header_info.header_direction == "RESPONSE" and header_info.is_security and not header_info.is_already_classified:
                all_response_headers_are_classified = "no"
                break
    else:
        print(f"[!] The maximum count of {MAX_LOOP_ITERATION_COUNT} iteration feedback loop was reached so force the end of the flow.")
    return all_response_headers_are_classified


def create_dashboard(state: PipelineState) -> PipelineState:
    headers_collections = state["headers_info_collection"]
    dashboard_md_tpl = """
> 🕑 Last update %s.

%s
"""
    # Use markdownify to create a table in MD format from HTML format
    header_table = """<table>
<tr>
<th>Header name</th>
<th>Header direction</th>
<th>Fully classified</th>
<th>Classifier explanation</th>
<th>Validator explanation</th>
<th>Links</th>
</tr>
    """
    for header_name, header_info in headers_collections.items():
        if header_info.is_security and header_name in state["oshp_headers_missed"] and header_name not in state["http_response_headers_explicitly_ignored"]:
            header_table += "<tr>"
            header_table += f"<td>{header_info.name}</td>"
            header_table += f"<td>{header_info.header_direction}</td>"
            header_table += f"<td>{header_info.is_already_classified}</td>"
            header_table += f"<td>{header_info.is_security_classification_explanation}</td>"
            header_table += f"<td>{header_info.is_security_classification_validation_explanation}</td>"
            header_table += "<td>"
            if header_info.rfc_location is not None:
                header_table += f'<a href="{header_info.rfc_location}">RFC</a>'
            if header_info.spec_location is not None:
                if header_info.rfc_location is not None:
                    header_table += " - "
                header_table += f'<a href="{header_info.spec_location}">SPEC</a>'
            header_table += "</td></tr>"
    header_table += "</table>"
    md_table = md(header_table)
    content = dashboard_md_tpl % (state["last_update"], md_table)
    with open(DASHBOARD_FILENAME, mode="w", encoding=DEFAULT_ENCODING) as f:
        f.write(content)
    return state


def assemble_agent() -> StateGraph:
    agent_builder = StateGraph(PipelineState)
    # Define nodes of the graph
    agent_builder.add_node("init_http_response_headers_explicitly_ignored_collection", init_http_response_headers_explicitly_ignored_collection)
    agent_builder.add_node("gather_http_header_names", gather_http_header_names)
    agent_builder.add_node("identify_http_header_directions_without_model", identify_http_header_directions_without_model)
    agent_builder.add_node("identify_http_header_directions_with_model", identify_http_header_directions_with_model)
    agent_builder.add_node("determine_classification_state_for_non_response_header", determine_classification_state_for_non_response_header)
    agent_builder.add_node("identify_http_header_security_relation_with_model", identify_http_header_security_relation_with_model)
    agent_builder.add_node("validate_classification_state_with_model", validate_classification_state_with_model)
    agent_builder.add_node("identify_headers_missed_by_oshp", identify_headers_missed_by_oshp)
    agent_builder.add_node("create_dashboard", create_dashboard)
    # Define the graph flow
    agent_builder.add_edge(START, "init_http_response_headers_explicitly_ignored_collection")
    agent_builder.add_edge("init_http_response_headers_explicitly_ignored_collection", "gather_http_header_names")
    agent_builder.add_edge("gather_http_header_names", "identify_http_header_directions_without_model")
    agent_builder.add_edge("identify_http_header_directions_without_model", "identify_http_header_directions_with_model")
    agent_builder.add_edge("identify_http_header_directions_with_model", "determine_classification_state_for_non_response_header")
    agent_builder.add_edge("determine_classification_state_for_non_response_header", "identify_http_header_security_relation_with_model")
    agent_builder.add_edge("identify_http_header_security_relation_with_model", "validate_classification_state_with_model")
    agent_builder.add_conditional_edges("validate_classification_state_with_model", classification_is_over, {"no": "identify_http_header_security_relation_with_model", "yes": "identify_headers_missed_by_oshp"})
    agent_builder.add_edge("identify_headers_missed_by_oshp", "create_dashboard")
    agent_builder.add_edge("create_dashboard", END)
    return agent_builder


if __name__ == "__main__":
    state = {"headers_info_collection": {}, "last_update": "", "oshp_headers_missed": [], "loop_interation_count": 0}
    if os.path.exists(STATE_FILENAME):
        with open(STATE_FILENAME, mode="r", encoding=DEFAULT_ENCODING) as f:
            data = json.load(f)
            state = PipelineState(headers_info_collection={k: HeaderInfo(**v) for k, v in data["headers_info_collection"].items()}, last_update=data["last_update"], oshp_headers_missed=data["oshp_headers_missed"], loop_interation_count=0, http_response_headers_explicitly_ignored=[])
    agent = assemble_agent().compile()
    node_names = set(agent.nodes.keys())
    state = agent.invoke(state, config={"callbacks": [NodeLoggerCallback(node_names=node_names)]})
    with open(STATE_FILENAME, mode="w", encoding=DEFAULT_ENCODING) as f:
        json.dump(state, f, cls=DataclassEncoder, indent=2, sort_keys=True)
    with open(DIAGRAM_FLOW_FILENAME, "wb") as f:
        f.write(agent.get_graph(xray=True).draw_mermaid_png())
