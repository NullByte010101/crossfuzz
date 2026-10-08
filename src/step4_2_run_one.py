# -*- coding: utf-8 -*-
import re
import os
import time
import shutil
import random
import tempfile
import subprocess
from termcolor import cprint

from utils.config_loader import config

JVMS_DIR = config.get("paths.jvms_dir")
JDK_BIN_PATHS = config.path("step4_2.jdk_bin_paths", base=JVMS_DIR)
TESTCASE_DIR = config.path("step4_2.testcase_dir")
JAVA_FILES = config.get("step4_2.java_files")

def get_jdk_name(jdk_path):
    """
    Extract the JDK name from the bin path of JDK.
    """

    return os.path.relpath(jdk_path, JVMS_DIR).split(os.sep)[0]

def run_javac(compile_cmd, env):
    """
    Run a javac command.
    """

    try:
        compile_start_time = time.time()
        compile_proc = subprocess.run(
            compile_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=60
        )
        compile_end_time = time.time()
        compile_time = compile_end_time - compile_start_time
        compile_success = compile_proc.returncode == 0
        compile_output = compile_proc.stderr.decode("utf-8", errors="replace").strip()
        print(compile_output)
    except subprocess.TimeoutExpired:
        compile_success = False
        compile_output = "Compilation timed out."
        compile_time = 60
    return {
        "compile_success": compile_success,
        "compile_output": compile_output,
        "compile_time": compile_time
    }

def extract_exception_classes(stderr_output: str) :
    """
    Extract the first Java exception class name from stderr.

    Parameters:
        stderr_output (str): The standard error output string.

    Returns:
        Optional[str]: The first extracted exception class name, or None if not found.
    """

    pattern = re.compile(
        r'(?:Exception in thread ".*?" |Caused by: |^)([\w\.]+(?:Exception|Error|Throwable))'
    )
    match = pattern.search(stderr_output)
    if match:
        return match.group(1)
    return stderr_output

def run_java(execute_cmd, env):
    """
    Run a Java command.
    """

    try:
        execute_start_time = time.time()
        execute_proc = subprocess.run(
            execute_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout = 60
        )
        execute_end_time = time.time()
        execute_time = execute_end_time - execute_start_time
        execute_success = execute_proc.returncode == 0
        execute_stdout = execute_proc.stdout.decode("utf-8", errors="replace").strip()
        stderr_output = execute_proc.stderr.decode("utf-8", errors="replace").strip()
        print(execute_stdout)
        print(stderr_output)
        stderr_output = extract_exception_classes(stderr_output)
    except subprocess.TimeoutExpired:
        execute_success = False
        execute_stdout = ""
        stderr_output = "Execution timed out."
        execute_time = 60
    return {
        "execute_success": execute_success,
        "execute_stdout": execute_stdout,
        "execute_stderr": stderr_output,
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
        shutil.copy(java_file_path, temp_dir)
        java_filename = os.path.basename(java_file_path)
        temp_java_path = os.path.join(temp_dir, java_filename)
        os.chdir(temp_dir)

        # Compile Java file
        compile_cmd = ["javac","-encoding", "UTF-8", java_filename]
        javac_results = run_javac(compile_cmd, env)

        if not javac_results["compile_success"]:
            final_results = {
                "compile_success": False,
                "compile_output": javac_results["compile_output"],
                "execute_success": False,
                "execute_stdout": "",
                "execute_stderr": "",
                "compile_time": javac_results["compile_time"],
                "execute_time": None
            }
            return final_results, True

        # Run compiled class
        execute_cmd = ["java"] + options + [class_name]
        print(execute_cmd)
        java_results = run_java(execute_cmd, env)

        final_results = {**javac_results, **java_results}
        return final_results, True

def main():
    # Obtain the list of Java files in the input directory
    selected_java_files = JAVA_FILES
    
    # Iterate over each Java file
    for java_file in selected_java_files:
        java_file_path = os.path.join(TESTCASE_DIR, java_file)
        class_name = os.path.splitext(java_file)[0]
        source_issue_id = class_name.replace("Test", "")
        cprint(f"Processing {java_file}", "cyan")
        # Get execution options from test case file
        # with open(java_file_path, "r", encoding="utf-8") as f:
        #     options = f.readline().strip().split()[1:]
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
        # options = default_options
        options = []

        results = {}
        # Iterate over each JDK
        execute_outputs = set()
        execute_stderr = set()
        execute_returncodes = set()
        for jdk_bin in JDK_BIN_PATHS:
            if not os.path.isdir(jdk_bin):
                raise Error(f"JDK path not exists: {jdk_bin}")
            jdk_name = get_jdk_name(jdk_bin)
            cprint(f"Running with JDK: {jdk_name}", "cyan")
            res, options_are_valid = compile_and_run(java_file_path, class_name, jdk_bin, options)
            execute_outputs.add(res["execute_stdout"])
            execute_returncodes.add(res["execute_success"])
            execute_stderr.add(res["execute_stderr"])
            # print(res["execute_stdout"])
            print(res["execute_time"])
            # print(res["execute_success"])
            # print(res)

    print("len(execute_outputs):", len(execute_outputs))
    print("len(execute_returncodes):", len(execute_returncodes))
    print("len(execute_stderr):", len(execute_stderr))
    cprint("Finish", "cyan")

if __name__ == "__main__":
    main()
