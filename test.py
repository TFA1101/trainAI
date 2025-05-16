import urllib.request, urllib.error
from bs4 import BeautifulSoup
import re
import xlwt
import urllib.parse

# 正则规则：匹配票价信息
findStd = re.compile(r"Standard[\s\S]*?£(\d+(?:\.\d+)?)")
findFirst = re.compile(r"First[\s\S]*?£(\d+(?:\.\d+)?)")


def askURL(url):
    """
    获取指定URL的HTML内容，模拟浏览器请求。
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.122 Safari/537.36"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        print(f"请求失败：{e.reason}")
        return None


def build_system_prompt(tools_schema: list[dict]) -> str:
    """
    tools_schema -> list of tool definition dicts (OpenAI format)
    returns the giant English system prompt.
    """
    # ---- fake example tools (to prevent confusion) ----
    TOOL_EXAMPLE = (
        'You will receive a JSON string containing a list of callable tools. '
        'Please parse this JSON string and return a JSON object containing '
        'the tool name and tool parameters. Here is an example tool list:\n\n'
        '{"tools": ['
        '{"name": "plus_one", "description": "Add one to a number",'
        '"parameters":{"type":"object","properties":{"number":{"type":"string"}},"required":["number"]}},'
        '{"name": "minus_one", "description": "Minus one to a number",'
        '"parameters":{"type":"object","properties":{"number":{"type":"string"}},"required":["number"]}}]}\n\n'
        'For instance, if you need to add one to 77, output:\n\n'
        '{"tool": "plus_one", "parameters": {"number": "77"}}\n\n'
        'The above is **just an example** – only choose tools that really exist in the list below.'
    )

    RETURN_FORMAT = '{"tool": "tool name", "parameters": {"param": "value"}}'

    # ---- build readable description for each real tool ----
    tools_instructions = []
    for tool in tools_schema:
        fn = tool["function"]
        tools_instructions.append(
            f'{fn["name"]}: Call this tool to interact with the API. '
            f'Purpose: {fn["description"]}. '
            f'Parameters: {json.dumps(fn["parameters"])} | '
            f'Required: {fn["parameters"].get("required", [])}'
        )
    joined = "\n".join(tools_instructions)

    return (
        f"{TOOL_EXAMPLE}\n"
        f"\n"
        "Answer the user as best you can. You have access to the following APIs:\n"
        f"{joined}\n"
        f"\n"
        "Use the following format to call a tool:\n"
        "```tool_json\n"
        f"{RETURN_FORMAT}\n"
        "```\n"
        "\n"
        "Choose the appropriate tool according to the user's question. "
        "If no tool is needed, reply directly. "
        "When you have enough information from the tool results, answer the user without calling the tool again."
        "Only use the following exact parameter names when calling a tool:\n"
        "- departure\n"
        "- destination\n"
        "- date\n"
        "- time\n"
        "- ticket_type\n"
        "- adults\n"
        "- children\n"
        "\n"
        "Do not invent or combine parameters (e.g., do not use \"adults_children\", \"passenger_count\", or \"from_to\").\n"
        "Use only the official parameter names listed above, or the tool will not work.\n"
        "\n"
        "Choose the appropriate tool according to the user's question. "
        "If no tool is needed, reply directly. "
        "When you have enough information from the tool results, answer the user without calling the tool again."
    )

SYSTEM_PROMPT = build_system_prompt(tools_schema)
TOOL_REGEX = re.compile(
    r'\{\s*"tool"\s*:\s*"(?P<name>[^"]+)"\s*,\s*"parameters"\s*:\s*\{(?P<params>.*?)\}\s*\}',
    re.DOTALL
)

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "get_train_ticket_info",
            "description": "Fetch the cheapest UK train tickets between two stations",
            "parameters": {
                "type": "object",
                "properties": {
                    "departure": {"type": "string"},
                    "destination": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "optional HH:MM"},
                    "ticket_type": {"type": "string", "enum": ["single", "return", "open return"]},
                    "adults": {"type": "integer"},
                    "children": {"type": "integer"},
                    # Return‐trip fields: only required if ticket_type=="return"
                    "return_date": {"type": "string", "description": "YYYY-MM-DD (for return tickets)"},
                    "return_time": {"type": "string", "description": "HH:MM (for return tickets)"},
                },
                "required": ["departure", "destination", "date", "ticket_type", "adults", "children"]
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
                    "departure": {"type": "string"},
                    "destination": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "HH:MM"},
                    "train_number": {"type": "string", "description": "E.g. '12345'"},
                },
                "required": ["departure", "destination", "date", "time", "train_number"]
            }
        }
    }
]


def start():
    # subprocess.run("conda activate mlcllm", shell=True)
    # print("env activate mlcllm")
    subprocess.run("mlc_llm serve " + MODEL, shell=True)
    print("server activated!!!")


def build_system_prompt(tools_schema):
    TOOL_EXAMPLE = (
        'You will receive a JSON string containing a list of callable tools. '
        'Please parse this JSON string and return a JSON object containing '
        'the tool name and tool parameters. Here is an example tool list:\n\n'
        '{"tools": ['
        '{"name": "plus_one", "description": "Add one to a number",'
        '"parameters":{"type":"object","properties":{"number":{"type":"string"}},"required":["number"]}},'
        '{"name": "minus_one", "description": "Minus one to a number",'
        '"parameters":{"type":"object","properties":{"number":{"type":"string"}},"required":["number"]}}]}\n\n'
        'For instance, if you need to add one to 77, output:\n\n'
        '{"tool": "plus_one", "parameters": {"number": "77"}}\n\n'
        'The above is **just an example** – only choose tools that really exist in the list below.'
    )
    RETURN_FMT = '{"tool":"tool name","parameters":{"param":"value"}}'
    instr = [TOOL_EXAMPLE, "\nAnswer the user as best you can. You have access to the following APIs:"]
    for t in tools_schema:
        fn = t["function"]
        instr.append(
            f"{fn['name']}: {fn['description']}\n"
            f"Parameters: {json.dumps(fn['parameters'])}"
        )
    instr.append(
        "Use the following format to call a tool:"
        "```tool_json\n" + RETURN_FMT + "\n```\n"
                                        "Choose the appropriate tool according to the user's question. "
                                        "If no tool is needed, reply directly. "
                                        "When you have enough information from the tool results, answer the user without calling the tool again."
                                        "Only use the following exact parameter names when calling a tool:\n"
                                        "- departure\n"
                                        "- destination\n"
                                        "- date\n"
                                        "- time\n"
                                        "- ticket_type\n"
                                        "- adults\n"
                                        "- children\n"
                                        "\n"
                                        "Do not invent or combine parameters (e.g., do not use \"adults_children\", \"passenger_count\", or \"from_to\").\n"
                                        "Use only the official parameter names listed above, or the tool will not work.\n"
                                        "\n"
                                        "Choose the appropriate tool according to the user's question. "
                                        "If no tool is needed, reply directly. "
                                        "When you have enough information from the tool results, answer the user without calling the tool again."
                                        "- Always use parameter names exactly as listed.\n"
                                        "- If ticket_type is \"return\", you must collect BOTH return_date and return_time before calling get_train_ticket_info. If missing, ask the user.\n"
                                        "- If the scraper returns an error, reply to the user with that error message.\n"
                                        "- When calling a tool, reply ONLY with a JSON block using this format:\n"

                                        "- Do NOT include natural language or explanations around tool calls.\n"
                                        "- If no tool is needed, just answer normally.\n"
                                        "- ALWAYS write proper JSON with double-quoted keys and strings."
                                        "After the tool call is complete and results are available, continue the conversation using the tool result."

    )
    return "\n\n".join(instr)


SYSTEM_PROMPT = build_system_prompt(tools_schema)
TOOL_REGEX = re.compile(
    r'\{\s*"tool"\s*:\s*"(?P<name>[^"]+)"\s*,\s*"parameters"\s*:\s*\{(?P<params>.*?)\}\s*\}',
    re.DOTALL
)