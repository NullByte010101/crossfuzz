import re
import time
import json
import json5
import httpx
import random
import logging
import tiktoken
from openai import OpenAI
from termcolor import cprint
from functools import wraps
from multiprocessing import Lock, Value

logging.basicConfig(filename='step1_transform_testcase_deepseek.log', level=logging.INFO)

request_lock = Lock()
last_request_time = Value('d', 0.0)
MIN_REQUEST_INTERVAL = 1.5

def count_tokens(text: str, model_name: str = "o3") -> int:
    encoding = tiktoken.encoding_for_model(model_name)
    tokens = encoding.encode(text)
    return len(tokens)

def retry_with_backoff(max_retries=5, initial_delay=10):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries):
                try:
                    # 速率限制
                    with request_lock:
                        current_time = time.time()
                        time_since_last = current_time - last_request_time.value
                        if time_since_last < MIN_REQUEST_INTERVAL:
                            time.sleep(MIN_REQUEST_INTERVAL - time_since_last)
                        last_request_time.value = time.time()
                    
                    return func(*args, **kwargs)
                    
                except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                    if attempt == max_retries - 1:
                        cprint(f"API调用失败，已达最大重试次数: {str(e)}", "red")
                        return None
                    
                    cprint(f"尝试 {attempt + 1}/{max_retries} 失败: {str(e)}", "yellow")
                    cprint(f"等待 {delay} 秒后重试...", "yellow")
                    time.sleep(delay)
                    delay *= 2
                    
                except Exception as e:
                    cprint(f"未预期的错误: {str(e)}", "red")
                    return None
            return None
        return wrapper
    return decorator

@retry_with_backoff(max_retries=5, initial_delay=10)
def call_llm(stage, compiler_name, user_input, model_name, temperature):
    api_keys = [
        "sk-qsBH3eZLojOoPQuDiR8LSPw8tw2cU2EWeKrGfeBVxUMPrFlc", 
        "sk-G4XhKgHt5tCkjKI0EHY26ymrF5xjwY2MKUIqFWFK1IMvOcH1"
    ]
    client = OpenAI(
        api_key= random.choice(api_keys),
        base_url="https://api.huiyan-ai.cn/v1",
        http_client=httpx.Client(timeout=300.0)
        )
    with open("prompt/three-step-generation-v4.txt", "r") as f:
        all_prompt = f.read()
    prompt = all_prompt.split("===prompt===")[stage-1].strip().replace("{compiler_name}", compiler_name)
    response = client.chat.completions.create( model=model_name, 
                                                messages=[  {"role": "system", "content": prompt},
                                                            {"role": "user", "content": user_input}], 
                                                temperature=temperature,
                                                stream=False)
    # print("response:", response)
    answer = response.choices[0].message.content
    # return parse_output(answer)
    cprint("answer:", "green")
    print(answer)
    return answer

def simple_fix_json_quotes(json_str):
    """
    简单版本：在字符串值内部的引号前添加转义符
    """
    # 匹配 "key": "value" 其中value可能包含未转义的引号
    def fix_value(match):
        prefix = match.group(1)  # "key":
        value = match.group(2)    # value内容
        suffix = match.group(3)   # 结尾的"
        
        # 转义value中的引号
        value_escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        
        return f'{prefix}"{value_escaped}"{suffix}'
    
    # 匹配模式: "任意key": "任意value"
    pattern = r'("(?:[^"\\]|\\.)*?"\s*:\s*)"(.*?)"(\s*[,}\]])'
    
    fixed = json_str
    prev = ""
    
    # 多次替换直到稳定
    count = 0
    while prev != fixed and count < 1:
        prev = fixed
        fixed = re.sub(pattern, fix_value, fixed, flags=re.DOTALL)
        count += 1
    
    return fixed

def write_down(compiler_name, output, issue_id, testcase_path, testcase_comment=""):
    if output.startswith("{") and output.endswith("}"):
        pass
    # if output.startswith("```json") and output.endswith("```"):
    elif "```json" in output and "```" in output:
        output = output[output.index("```json") + 7:output.rindex("```")]
    elif output.startswith("```json"):
        output = output[output.index("```json") + 7:]
    elif "```" in output:
        output = output[output.index("```") + 3:output.rindex("```")]
    try:
        # output = json.loads(output.strip(), strict=False)
        output = json5.loads(output.strip(), strict=False)
    except ValueError as e:
        output = simple_fix_json_quotes(output.strip())
        output = json5.loads(output, strict=False)
    except json.JSONDecodeError as e:
        logging.error(f"{issue_id} Output Parsing Error: {e}")
        logging.error(f"Output:\n{output}")
        return
    class_name = f"Test{issue_id}"
    testcase = output["java_program"]
    if testcase is None or testcase == "":
        return
    if "public class " in testcase:
        match = re.compile(r"public class (\w+)").search(testcase)
        if match is None:
            return
        original_class_name = match.group(1)
    elif "class " in testcase:
        match = re.compile(r"class (\w+)").search(testcase)
        if match is None:
            return
        original_class_name = match.group(1)
    else:
        logging.error(f"{issue_id} Output Parsing Error: No class name found")
        logging.error(f"Testcase:\n{testcase}")
        return
    testcase = re.sub(original_class_name, class_name, testcase)
    # Modify the options
    java_options = output["execution_options"]
    if type(java_options) == str:
        java_options = java_options.split(" ")
    for i, opt in enumerate(java_options):
        if original_class_name in opt:
            opt = re.sub(original_class_name, class_name, opt)
        java_options[i] = opt
    modified_java_options = []
    for o in java_options:
        if (not o.startswith("-XX")) or o in ["-XX:+VerifyGraphEdges", "-XX:+UseZicond", "EliminateNullChecks"] or "Trace" in o:
            continue
        modified_java_options.append(o)
    if "-XX:+UseUnalignedAccesses" in java_options and "-XX:+UnlockDiagnosticVMOptions" not in java_options:
        modified_java_options.insert(0, "-XX:+UnlockDiagnosticVMOptions")
    java_options = " ".join(modified_java_options)
    with open(testcase_path+f"{class_name}.java", "w") as f:
        f.write(testcase_comment+"\n")
        f.write("// "+java_options+"\n")
        f.write(testcase)
    print("Testcase written down")

def parse_output(output):
    if output.startswith("{") and output.endswith("}"):
        pass
    elif "```json" in output and output.endswith("```"):
        output = output[output.index("```json") + 7:output.rindex("```")]
    elif output.startswith("```json"):
        output = output[output.index("```json") + 7:]
    elif "```" in output:
        output = output[output.index("```") + 3:output.rindex("```")]
    print("output:\n"+output)
    try:
        processed = json5.loads(output.strip(), strict=False)
    except ValueError as e:
        output = simple_fix_json_quotes(output)
        processed = json5.loads(output.strip(), strict=False)
    return processed

if __name__ == "__main__":
    print(count_tokens("Hello, world!"))
