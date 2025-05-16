import json
import uuid

from mlc_llm import MLCEngine
from scraping import*
import subprocess
import requests
from fastapi import FastAPI,  HTTPException
from pydantic import BaseModel
import json, re, uuid
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()
# 跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 前端地址
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法，包括 OPTIONS
    allow_headers=["*"],  # 允许所有请求头
)
sessions: dict[str, list[dict]] = {}
SERVER = "http://127.0.0.1:8000/v1/chat/completions"
MODEL  = "HF://mlc-ai/Llama-3.2-1B-Instruct-q0f16-MLC"
engine = MLCEngine("HF://mlc-ai/Llama-3.2-1B-Instruct-q0f16-MLC")
#mlc-ai/gemma-3-12b-it-q0bf16-MLC
#mlc-ai/Hermes-3-Llama-3.2-3B-q0f16-MLC
#mlc-ai/Llama-3.2-1B-Instruct-q0f16-MLC
#mlc-ai/Qwen3-1.7B-q0f16-MLC
#mlc-ai/Llama-3.1-8B-Instruct-q0f16-MLC
#mlc-ai/gemma-3-1b-it-q0f16-MLC


tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "get_train_ticket_info",
            "description": "Fetch the cheapest UK train tickets between two stations",
            "parameters": {
                "type": "object",
                "properties": {
                    "departure":   {"type": "string"},
                    "destination": {"type": "string"},
                    "date":        {"type": "string", "description": "YYYY-MM-DD"},
                    "time":        {"type": "string", "description": "optional HH:MM"},
                    "ticket_type": {"type": "string", "enum": ["single","return","open return"]},
                    "adults":      {"type": "integer"},
                    "children":    {"type": "integer"},
                    # Return‐trip fields: only required if ticket_type=="return"
                    "return_date": {"type": "string", "description": "YYYY-MM-DD (for return tickets)"},
                    "return_time": {"type": "string", "description": "HH:MM (for return tickets)"},
                },
                "required": ["departure","destination","date","ticket_type","adults","children"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "predict_delay",
            "description": "Predict the delay probability for a given UK train journey",
            "parameters": {
                "type": "object",
                "properties": {
                    "current_station":   {"type": "string"},
                    "current_delay": {"type": "string"},
                    "target_station":        {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["departure","destination","date","time","train_number"]
            }
        }
    }
]



def start():
   #subprocess.run("conda activate mlcllm", shell=True)
   #print("env activate mlcllm")
   subprocess.run("mlc_llm serve "+MODEL, shell=True)
   print("server activated!!!")

def build_system_prompt(tools_schema):
    TOOL_EXAMPLE = (
        "You can call tools by outputting a JSON object like this:\n"
        "```tool_json\n"
        '{"tool": "get_train_ticket_info", "parameters": {"departure": "Norwich", "destination": "London", "date": "2025-06-08"}}\n'
        "```\n"
        "Only use tools that are listed below.\n"
        "Do NOT write explanations before or after the JSON block.\n"
    )

    RETURN_FMT = '{"tool": "tool name", "parameters": {"param": "value"}}'

    tool_descriptions = []
    for t in tools_schema:
        fn = t["function"]
        tool_descriptions.append(
            f"- {fn['name']}: {fn['description']}\n"
            f"  Parameters: {json.dumps(fn['parameters'], indent=2)}"
        )

    post_tool = (
        "Once a tool returns data, switch to NATURAL LANGUAGE.\n"
        "Summarize the ticket information or prediction result for the user.\n"
        "Include key details such as prices, times, or delay probability.\n"
        "If the tool returns an error, rephrase and explain it nicely to the user."
    )

    return "\n".join([
        "You are a helpful assistant for train ticket booking and delay prediction.",
        TOOL_EXAMPLE,
        "Available tools:",
        *tool_descriptions,
        "",
        post_tool,
        "Never invent tools. Always use double-quoted JSON keys and string values."
    ])


SYSTEM_PROMPT = build_system_prompt(tools_schema)
TOOL_REGEX = re.compile(
    r'\{\s*"tool"\s*:\s*"(?P<name>[^"]+)"\s*,\s*"parameters"\s*:\s*\{(?P<params>.*?)\}\s*\}',
    re.DOTALL
)

import datetime
from scraping import call_scraping, find_cheapest_ticket, load_crs_list, check_crs

def get_train_ticket_info(params):
    """
    {
        "departure": "Norwich",
        "destination": "London Blackfriars",
        "date": "2025-06-08",
        "time": "08:00",
        "ticket_type": "return",
        "return_date": "2025-06-10",
        "return_time": "17:30",
        "adults": 2,
        "children": 1
    }
    """

    if params.get("ticket_type") == "return":
        if not params.get("return_date") or not params.get("return_time"):
            return {"error": "Return tickets require both return_date and return_time. Please provide them."}

    try:
        dt = datetime.datetime.strptime(params["date"], "%Y-%m-%d")
        hour, minute = ("09", "00")  # 默认时间
        if "time" in params and params["time"]:
            hour, minute = params["time"].split(":")
            if hour== "00" :
                hour = "09"

        query_params = {
            "type": params.get("ticket_type", "single"),
            "origin": params["departure"],
            "destination": params["destination"],
            "leavingType": "departing",
            "leavingDate": dt.strftime("%d%m%y"),
            "leavingHour": hour,
            "leavingMin": minute,
            "adults": params.get("adults", 1),
            "children": params.get("children", 0)
        }

        if params["ticket_type"] == "return":
            rdt = datetime.datetime.strptime(params["return_date"], "%Y-%m-%d")
            rh, rm = params["return_time"].split(":")
            query_params.update({
                "returnType": "departing",
                "returnDate": rdt.strftime("%d%m%y"),
                "returnHour": rh,
                "returnMin": rm
            })

        crs_dict = load_crs_list("stations.csv")
        if not check_crs(query_params, crs_dict):
            return {"error": "Station name not recognised"}

        xls_path,url = call_scraping(query_params, outfile="latest_prices.xls")
        if isinstance(xls_path, dict) and "error" in xls_path:
            return xls_path

        cheapest = find_cheapest_ticket(xls_path, ticket_type=params["ticket_type"])

        return {
            "cheapest": cheapest,
            "file": xls_path,
            "link": url
        }

    except Exception as e:
        return {"error": f"Exception during processing: {e}"}





class ChatRequest(BaseModel):
    session_id: str | None
    message: str


def dispatch_tool(name, params):
    if name == "get_train_ticket_info":
        return get_train_ticket_info(params)
    if name == "predict_delay":
        # placeholder for future function
        return {"prediction": "Function not implemented yet."}
    return {"error": f"Unknown tool: {name}"}

def llm_request(messages):
    print("Input messages：")
    for m in messages:
        print(f"  - {m['role']}: {m['content'][:120]}...")
    resp = engine.chat.completions.create(
        messages=messages,
        model=MODEL,
        stream=False,
        max_tokens=1024,
    )
    print("LLM response:\n", resp.choices[0].message.content)
    return {
        "choices": [{"message": {"content": resp.choices[0].message.content}}]
    }





@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    print("Received JSON:", req.model_dump())

    sid = req.session_id or str(uuid.uuid4())
    if sid not in sessions:
        sessions[sid] = [{"role": "system", "content": SYSTEM_PROMPT}]
    history = sessions[sid]
    history.append({"role": "user", "content": req.message})

    #call tools
    resp1 = llm_request(history)
    if "choices" not in resp1:
        raise HTTPException(500, detail=f"LLM error: {resp1}")
    msg1 = resp1["choices"][0]["message"]["content"]
    history.append({"role": "assistant", "content": msg1})

    #
    m = TOOL_REGEX.search(msg1)
    if not m:
        # no tool call → immediate reply
        return {"session_id": sid, "reply": msg1}

    tool_name = m.group("name")
    raw = "{" + m.group("params") + "}"
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as e:
        return {
            "session_id": sid,
            "reply": (
                "I tried to interpret your tool call but the parameters seem incomplete or malformed. "
                "Could you try again with more specific or properly structured info?"
            )
        }

    #error if
    obs = dispatch_tool(tool_name, params)
    if "error" in obs:
        # respond directly with error, do NOT call LLM again
        sessions[sid].append({"role": "assistant", "content": obs["error"]})
        return {"session_id": sid, "reply": obs["error"]}

    #
    history.append({
        "role": "user",
        "content": f"Tool {tool_name} returned:\n{json.dumps(obs, ensure_ascii=False)}\n,\"Summarize ticket you found and provide links.\""

    })
    resp2 = llm_request(history)
    if "choices" not in resp2:
        raise HTTPException(500, detail=f"LLM error: {resp2}")
    reply = resp2["choices"][0]["message"]["content"]
    history.append({"role": "assistant", "content": reply+"\nSummarize ticket you found and provide links."})

    return {"session_id": sid, "reply": reply}


'''

if __name__ == "__main__":
    # server = launch_mlc_server()
    try:
        question = "I want to book a single train from Norwich to London Blackfriars on 2025-06-08 morning, 2 adults."

        answer = chat(question)
        print("\n Final answer:\n", answer)
    finally:
        None # server.terminate()

def test():
   # Create engine
   # mlc_llm serve HF://mlc-ai/Llama-3.2-1B-Instruct-q0f16-MLC
   model = "HF://mlc-ai/Llama-3.2-1B-Instruct-q0f16-MLC"
   engine = MLCEngine(model)
   
   
I want to book a single train from Norwich to London Blackfriars on 2025-06-08 morning, 2 adults.
'''
