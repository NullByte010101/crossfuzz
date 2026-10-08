# -*- coding: utf-8 -*-
import re
import os
import time
import json
import shutil
import random
import tempfile
import subprocess
from termcolor import cprint
import signal
import atexit
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import sqlite3

JDK_BIN_PATHS = [
    "../jvms/hotspot-8/build/linux-x86_64-normal-server-release/jdk/bin",
    "../jvms/hotspot-11/build/linux-x86_64-normal-server-release/jdk/bin",
    "../jvms/hotspot-17/build/linux-x86_64-server-release/jdk/bin",
    "../jvms/hotspot-21/build/linux-x86_64-server-release/jdk/bin",
    "../jvms/hotspot-25/build/linux-x86_64-server-release/jdk/bin",
    "../jvms/openj9-8/bin",
    "../jvms/openj9-11/bin",
    "../jvms/openj9-17/bin",
    "../jvms/openj9-21/bin",
    "../jvms/openj9-25/bin",
    "../jvms/graalvm-21/bin",
    "../jvms/graalvm-25/bin"
]

# TESTCASE_DIRS = [ "../data/testcases-gcc-1",
#             "../data/testcases-clang-1",
#             "../data/testcases-cpython-1",
#             "../data/testcases-cpython-1-v1",
#             "../data/testcases-pypy-1",
#             "../data/testcases-pypy-1-v1",
#             "../data/testcases-rustc-1",
#             "../data/testcases-gcc-2",
#             "../data/testcases-clang-2",
#             "../data/testcases-pypy-2",
#             "../data/testcases-rustc-2",
#             "../data/testcases-rustc-2-v1",
#             "../data/testcases-cpython-2",
#             ]
# TESTCASE_DIRS = ["../data/testcases-gcc-4"]
# ANOMALIES_FILE = "anomalies_crossfuzz_gcc_4.json"

TESTCASE_DIRS = ["../old-data/testcases-xwq-gcc"]
ANOMALIES_FILE = "anomalies_crossfuzz_gcc_xwq.json"

def get_jdk_name(jdk_path):
    """
    Extract the JDK name from the bin path of JDK.
    """

    match = re.search(r"jvms\/(.*?)\/", jdk_path)
    return match.group(1)

def run_javac(compile_cmd, env):
    """
    Run a javac command.
    """

    try:
        compile_start_time = time.time()
        compile_proc = subprocess.Popen(
            compile_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        compile_proc.wait(timeout=60)
        compile_end_time = time.time()
        compile_time = compile_end_time - compile_start_time
        compile_returncode = compile_proc.returncode
        stdout_data = compile_proc.stdout.read()
        stderr_data = compile_proc.stderr.read()
        compile_stdout = stdout_data.decode("utf-8", errors="replace").strip()
        compile_stderr = stderr_data.decode("utf-8", errors="replace").strip()
    except subprocess.TimeoutExpired:
        compile_proc.kill()
        compile_returncode = -9
        compile_stdout = compile_proc.stdout.read().decode("utf-8", errors="replace").strip()
        compile_stderr = compile_proc.stderr.read().decode("utf-8", errors="replace").strip()
        if compile_stderr:
            compile_stderr += "\n\n[Compilation timed out after 60 seconds]"
        else:
            compile_stderr = "[Compilation timed out after 60 seconds]"
        compile_time = 60
    return {
        "compile_returncode": compile_returncode,
        "compile_stdout": compile_stdout,
        "compile_stderr": compile_stderr,
        "compile_time": compile_time
    }

def extract_exception_classes(execute_stderr: str) :
    """
    Extract the first Java exception class name from stderr.

    Parameters:
        execute_stderr (str): The standard error output string.

    Returns:
        Optional[str]: The first extracted exception class name, or None if not found.
    """

    pattern = re.compile(
        r'(?:Exception in thread ".*?" |Caused by: |^)([\w\.]+(?:Exception|Error|Throwable))'
    )
    match = pattern.search(execute_stderr)
    if match:
        return match.group(1)
    return execute_stderr

def run_java(execute_cmd, env):
    """
    Run a Java command.
    """

    try:
        execute_start_time = time.time()
        execute_proc = subprocess.Popen(
            execute_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        execute_proc.wait(timeout=60)
        execute_end_time = time.time()
        execute_time = execute_end_time - execute_start_time
        execute_returncode = execute_proc.returncode
        stdout_data = execute_proc.stdout.read()
        stderr_data = execute_proc.stderr.read()
        execute_stdout = stdout_data.decode("utf-8", errors="replace").strip()
        if len(execute_stdout) > 65535:
            execute_stdout = execute_stdout[:65535] + "..."
        execute_stderr = stderr_data.decode("utf-8", errors="replace").strip()
        execute_stderr = extract_exception_classes(execute_stderr)
    except subprocess.TimeoutExpired:
        execute_proc.kill()
        execute_returncode = -9
        execute_stdout = execute_proc.stdout.read().decode("utf-8", errors="replace").strip() if execute_proc.stdout else ""
        execute_stderr = execute_proc.stderr.read().decode("utf-8", errors="replace").strip() if execute_proc.stderr else ""
        if execute_stderr:
            execute_stderr += "\n\n[Execution timed out after 60 seconds]"
        else:
            execute_stderr = "[Execution timed out after 60 seconds]"
        execute_time = 60
    return {
        "execute_returncode": execute_returncode,
        "execute_stdout": execute_stdout,
        "execute_stderr": execute_stderr,
        "execute_time": execute_time
    }

def compile_and_run(java_file_path, class_name, jdk_bin_path, options):
    """
    Compile and execute Java files using the specified JDK, and capture output and abnormal behavior.

    Returns:
        A dictionary containing the results of compilation and execution.
    """

    env = os.environ.copy()
    env["PATH"] = jdk_bin_path + os.pathsep + env.get("PATH", "")

    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Copy the Java file to the temporary directory
        java_filename = os.path.basename(java_file_path)
        temp_java_path = os.path.join(temp_dir, java_filename)
        shutil.copy(java_file_path, temp_java_path)

        # Compile Java file
        compile_cmd = ["javac", "-encoding", "UTF-8", "-d", temp_dir, temp_java_path]
        javac_results = run_javac(compile_cmd, env)

        if javac_results["compile_returncode"] != 0:
            final_results = {
                "compile_returncode": javac_results["compile_returncode"],
                "compile_stdout": javac_results["compile_stdout"],
                "compile_stderr": javac_results["compile_stderr"],
                "compile_time": javac_results["compile_time"],
                "execute_returncode": None,
                "execute_stdout": None,
                "execute_stderr": None,
                "execute_time": None
            }
            return final_results, True

        # Run compiled class
        default_options = [
            '-Xmx512m',
            '-Xms256m',
            '-XX:MaxMetaspaceSize=256m',
            '-XX:+HeapDumpOnOutOfMemoryError',
            '-XX:HeapDumpPath=/tmp/heapdump.hprof',
            '-XX:+ExitOnOutOfMemoryError',
            '-XX:+UseContainerSupport',
            '-Xss256k', 
        ]
        execute_cmd = ["java", "-cp", temp_dir] + default_options + options + [class_name]
        print(execute_cmd)
        java_results = run_java(execute_cmd, env)
        # If the execution failed due to invalid options, remove options and retry
        # print(java_results)
        if (len(options) > 0) and (java_results["execute_returncode"] != 0):
            with open(temp_java_path, "r") as f:
                java_code = f.read()
            with open(temp_java_path, "w") as f:
                f.write("// Options are invalid.\n"+java_code)
            execute_cmd = ["java", "-cp", temp_dir] + default_options + [class_name]
            java_results = run_java(execute_cmd, env)
            options_are_valid = False
        else:
            options_are_valid = True

        final_results = {**javac_results, **java_results}
        return final_results, options_are_valid

def timeout(time_list):
    """
    1. If the maximum compile time is greater than 58 seconds, it is considered to be abnormal.
    2. If the ratio of the maximum execution time to the minimum execution time is greater than 20, it is considered to be abnormal.
    """

    timeout_num = 0
    for time in time_list:
        if time > 59:
            timeout_num += 1
    if timeout_num > 1 and timeout_num < 9:
        return True
    if max(time_list) / min(time_list) > 20:
        return True
    return False

def identify_anomalies(results):
    """
    Compare compile success, compile time, execution outputs, and execution times to identify anomalies.
    """

    compile_returncode_set = set()
    compile_time_list = []
    execute_returncode_set = set()
    output_set = set()
    stderr_set = set()
    execute_time_list = []

    for res in results.values():
        if res["compile_returncode"] not in [0, 1, -9]:
            return "compile crash"
        elif res["execute_returncode"] is not None and res["execute_returncode"] not in [0, 1, -9]:
            return "execute crash"
        compile_returncode_set.add(res["compile_returncode"])
        compile_time_list.append(res["compile_time"])
        execute_returncode_set.add(res["execute_returncode"])
        if res["execute_returncode"] == 0:
            output_set.add(res["execute_stdout"])
        else:
            stderr_set.add(res["execute_stderr"])
        execute_time_list.append(res["execute_time"])
    # print("execute_time_list:", execute_time_list)
    print("execute_returncode_set:", execute_returncode_set)
    
    # If the compilation results are inconsistent
    if len(compile_returncode_set) > 1:
        return "some compile successfully, some failed"
    # If all JDK compilation results are consistent
    elif timeout(compile_time_list):
        return "some compile timeout"
    
    # If all JDK execution results are successful
    if len(execute_returncode_set) == 1 and 0 in execute_returncode_set:
        # Check if the output results are consistent
        if len(output_set) > 1 and len(output_set) != len(JDK_BIN_PATHS):
            return "inconsistent outputs" 
    # If all JDK execution results fail
    elif len(execute_returncode_set) == 1 and 0 not in execute_returncode_set:
        if len(stderr_set) > 1:
            return "inconsistent exceptions or errors"
    elif timeout(execute_time_list):
        return "some execution timeout"

    return "pass"

def cleanup():
    """ Clean up all subprocesses """

    import psutil
    try:
        current_process = psutil.Process()
        children = current_process.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                continue
        gone, alive = psutil.wait_procs(children, timeout=3)
        for child in alive:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                continue
        psutil.wait_procs(alive, timeout=2)        
    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        print(f"Error during cleanup: {str(e)}")
    finally:
        try:
            if 'children' in locals():
                for child in children:
                    try:
                        child.close()
                    except:
                        pass
        except:
            pass

def create_table_for_differential_testing(cursor, table_name):
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    if cursor.fetchone():
        cursor.execute(f"SELECT DISTINCT source_issue_id FROM {table_name}")
        result = cursor.fetchall()
        if result:
            return [int(row[0]) for row in result]
        else:
            return []
    else:
        cursor.execute(f"""CREATE TABLE {table_name} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                source_issue_id INT,
                jdk_version VARCHAR(255),
                compile_returncode INT,
                compile_time FLOAT,
                compile_stdout LONGTEXT,
                compile_stderr LONGTEXT,
                execute_returncode INT,
                execute_time FLOAT,
                execute_stdout LONGTEXT,
                execute_stderr LONGTEXT)"""
        )
        return []

def is_useless_testcase(testcase_content):
    black_list = ["\npackage ", "java.lang.foreign.Arena", "jshell", "Process", "Thread", "com.sun.tools.javac.api"]
    # TODO. jshell和Process没有报错，为什么要过滤？
    for word in black_list:
        if word in testcase_content:
            return True
    return False

def run_one_folder(conn, cursor, testcase_dir, result_dir):
    # Check if anomalies.json file exists
    if os.path.exists(ANOMALIES_FILE):
        with open(ANOMALIES_FILE, "r") as f:
            anomalies = json.load(f)
    else:
        anomalies = {
            "some compile successfully, some failed": [],
            "some compile timeout": [],
            "compile crash": [],
            "inconsistent outputs": [],
            "inconsistent exceptions or errors": [],
            "some execution timeout": [],
            "execute crash": []
        }
    
    # Create result directory
    os.makedirs(result_dir, exist_ok=True)

    # Obtain the list of Java files in the input directory
    java_files = sorted([f for f in os.listdir(testcase_dir) if f.endswith(".java")])
    selected_java_files = java_files

    if not java_files:
        cprint("No Java files found in the input directory!", "red")
        return
    
    # Create table
    folder_name = testcase_dir.split("testcases-")[-1].replace("-", "_")
    table_name= f"diff_test_{folder_name}"
    already_generate = create_table_for_differential_testing(cursor, table_name)
    print("already_generate:", already_generate)

    # Iterate over each Java file
    for java_file in selected_java_files:
        java_file_path = os.path.join(testcase_dir, java_file)
        class_name = os.path.splitext(java_file)[0]
        source_issue_id = class_name.replace("Test", "")
        if already_generate and int(source_issue_id) in already_generate:
            continue
        cprint(f"Processing {testcase_dir}/{java_file}", "cyan")
        # Read testcase content, filter some special cases
        with open(java_file_path, "r", encoding="utf-8") as f:
            testcase_content = f.read()
        if is_useless_testcase(testcase_content):
            continue
        # Get execution options from test case file
        option_str = testcase_content.split("\n")[1]
        black_list = ["-XX:+PrintInlining", "-XX:+PrintCompilation", " -XX:+PrintAssembly", "-XX:+PrintGC", "-XX:+PrintIntrinsics"]
        for word in black_list:
            option_str = option_str.replace(word, "")
        # options = option_str.split(" ")[1:]
        # if "invalid" in options:
        #     options = []
        options = []

        results = {}
        # Iterate over each JDK
        def process_jdk(jdk_bin):
            if not os.path.isdir(jdk_bin):
                raise Error(f"JDK path not exists: {jdk_bin}")
            jdk_name = get_jdk_name(jdk_bin)
            cprint(f"Running with JDK: {jdk_name}", "cyan")
            res, options_are_valid = compile_and_run(java_file_path, class_name, jdk_bin, options)
            if not options_are_valid:
                options.clear()
            print("res:")
            print(res)
            return jdk_name, res

        try:
            with ThreadPoolExecutor(max_workers=len(JDK_BIN_PATHS)) as executor:
                futures = [executor.submit(process_jdk, jdk_bin) for jdk_bin in JDK_BIN_PATHS]
                try:
                    for future in as_completed(futures):
                        jdk_name, res = future.result()
                        results[jdk_name] = res
                except Exception as e:
                    for future in futures:
                        future.cancel()
                    raise
        finally:
            executor.shutdown(wait=True)

        for jdk, res in results.items():
            cursor.execute(f"INSERT INTO {table_name} (source_issue_id, jdk_version, compile_returncode, compile_time, compile_stdout, compile_stderr, execute_returncode, execute_time, execute_stdout, execute_stderr) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                    (class_name.replace("Test", ""), jdk, res["compile_returncode"], res["compile_time"], res["compile_stdout"], res["compile_stderr"],res["execute_returncode"], res["execute_time"], res["execute_stdout"], res["execute_stderr"]))
            conn.commit()
        
        is_anomaly = identify_anomalies(results)

        if is_anomaly != "pass":
            # Record anomalies
            anomalies[is_anomaly].append(source_issue_id)
            with open(ANOMALIES_FILE, "w") as f:
                json.dump(anomalies, f, indent=4)
            # Copy the Java file to the result directory
            shutil.copy(java_file_path, os.path.join(result_dir, java_file))
            # Create a result file to record the anomalous behavior
            result_file_path = os.path.join(result_dir, f"{class_name}.txt")
            with open(result_file_path, "w", encoding="utf-8") as rf:
                rf.write(f"==Testcase: {java_file}\n\n")
                rf.write(f"==Anomalous behavior: {is_anomaly}\n")
                for jdk, res in results.items():
                    rf.write(f">>JDK: {jdk}\n")
                    rf.write(f">>Compile sucess: {res["compile_returncode"]}\n")
                    rf.write(f">>Compile time: {res["compile_time"]:.2f}s\n" if res["compile_time"] else "Compile time: N/A\n")
                    if res["compile_returncode"] != 0:
                        rf.write(f">>Compile error:\n{res["compile_stdout"]}\n\n")
                        continue
                    rf.write(f">>Execute returncode: {res["execute_returncode"]}\n")
                    rf.write(f">>Execute output:\n{res["execute_stdout"]}\n")
                    rf.write(f">>Execute time: {res["execute_time"]:.2f}s\n" if res["execute_time"] else "Execute time: N/A\n")
                    rf.write(f">>Exception or error:\n{res["execute_stderr"]}\n")
                    rf.write("\n")
                rf.write("\n")
            cprint(f"  Recorded to: {result_file_path}", "yellow")
        else:
            cprint(f"  Pass", "green")

        # break

def kill_existing_processes():
    os.system("pkill -f crossfuzz/jvms")

def main():
    # Registration cleanup function
    atexit.register(cleanup)
    # Set signal processing
    signal.signal(signal.SIGTERM, lambda signum, frame: cleanup())
    signal.signal(signal.SIGINT, lambda signum, frame: cleanup())

    input("Attention: the result folders are never cleared! Press Enter to continue...")
    
    # conn = sqlite3.connect("../data/db/crossfuzz.db")
    conn = sqlite3.connect("../data/db/crossfuzz.db")
    cursor = conn.cursor()
    for testcase_dir in TESTCASE_DIRS:
        result_dir = testcase_dir.replace("testcases", "results")
        run_one_folder(conn, cursor, testcase_dir, result_dir)
        kill_existing_processes()
    cprint("Finish", "cyan")
    cursor.close()
    conn.close()

def clean():
    # conn = sqlite3.connect("../data/db/crossfuzz.db")
    conn = sqlite3.connect("../data/db/crossfuzz.db")
    cursor = conn.cursor()
    for folder in TESTCASE_DIRS:
        result_dir = folder.replace("testcases-", "results-")
        shutil.rmtree(result_dir, ignore_errors=True)
        table_name = folder.split("testcases-")[1].replace("-", "_")
        cursor.execute(f"drop table diff_test_{table_name};")

if __name__ == "__main__":
    main()
    # clean()
