import os
import re
import json
import shutil
import sqlite3

COMPILER = "gcc-4"
TESTCASE_DIR = f"../data/testcases-{COMPILER}/"
RESULT_DIR = f"../data/results-{COMPILER}/"

class DiffTestResult:
    def __init__(self, source_issue_id, compile_returncode, compiler_time, compile_stdout, compile_stderr, execute_returncode, execute_time, execute_stdout, execute_stderr):
        self.source_issue_id = source_issue_id
        self.compile_time = compiler_time
        self.compile_returncode = compile_returncode
        self.compile_stdout = compile_stdout
        self.compile_stderr = compile_stderr
        self.execute_time = execute_time
        self.execute_returncode = execute_returncode
        self.execute_stdout = execute_stdout
        self.execute_stderr = execute_stderr

def query_one_testcase(conn, issue_id):
    result_dict = {
        "hotspot-8": None,
        "hotspot-11": None,
        "hotspot-17": None,
        "hotspot-21": None,
        "openj9-8": None,
        "openj9-11": None,
        "openj9-17": None,
        "openj9-21": None,
        "graalvm-21": None
    }
    cursor = conn.cursor()
    table_name = f"diff_test_{COMPILER.replace("-", "_")}"
    cursor.execute(f"SELECT * FROM {table_name} WHERE source_issue_id = ?", (issue_id,))
    for row in cursor.fetchall():
        result_dict[row[2]] = DiffTestResult(row[1], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10])
    print("query result: ", result_dict)
    return result_dict

potential_bugs = {
    "jdk-21 throw exception when define the same variable in record type and generic type": [],
    "jdk21 timeouts when start and stop thread immediately which contains a large loop": [],
}

false_positives = {
    "different versions behave differently": [],
    "file operation": [],
    "random number": [],
    "time operation": [],
    "compile command": [],
    "partial versions support": [],
    "other": []
}

def compare_versions_attribute(results, attribute_name):
    """ Check if the attribute value of each version is the same """
    return (results["hotspot-8"].__dict__[attribute_name] == results["openj9-8"].__dict__[attribute_name] and
            results["hotspot-11"].__dict__[attribute_name] == results["openj9-11"].__dict__[attribute_name] and
            results["hotspot-17"].__dict__[attribute_name] == results["openj9-17"].__dict__[attribute_name] and
            results["hotspot-21"].__dict__[attribute_name] == results["openj9-21"].__dict__[attribute_name] == results["graalvm-21"].__dict__[attribute_name])

def compare_jdks_attribute(results, attribute_name):
    """ Check if the attribute value of each JDK is the same """
    return (results["hotspot-8"].__dict__[attribute_name] == results["hotspot-11"].__dict__[attribute_name] == \
            results["hotspot-17"].__dict__[attribute_name] == results["hotspot-21"].__dict__[attribute_name]) and \
            (results["openj9-8"].__dict__[attribute_name] == results["openj9-11"].__dict__[attribute_name] == \
            results["openj9-17"].__dict__[attribute_name] == results["openj9-21"].__dict__[attribute_name])

def filter_inconsistent_compile_returncode(results, testcase_content):
    if "record" in testcase_content and "instanceof" in testcase_content and "An exception has occurred in the compiler (21.0.10-internal)" in results["hotspot-21"].compile_stdout:
        potential_bugs["jdk-21 throw exception when define the same variable in record type and generic type"].append(results["hotspot-8"].source_issue_id)
        return "potential_bugs"
    if "com.sun.management.VMOption" in testcase_content and results["openj9-11"].compile_returncode == results["openj9-17"].compile_returncode == 1:
        false_positives["compile command"].append(results["hotspot-8"].source_issue_id)
        return "false_positives"
    if "getVMOption" in testcase_content and results["openj9-11"].compile_returncode == results["openj9-17"].compile_returncode == 1:
        false_positives["compile command"].append(results["hotspot-8"].source_issue_id)
        return "false_positives"
    for res in results.values():
        if "Please file a bug against the Java compiler" in res.compile_stdout:
            return "still_anomalies"
    if compare_versions_attribute(results, "compile_returncode"):
        false_positives["different versions behave differently"].append(results["hotspot-8"].source_issue_id)
        return "false_positives"
    else:
        return "still_anomalies"

def classnotfound(line):
    if "not find or load main class" in line:
        return True
    if "java.lang.ClassNotFoundException" in line:
        return True
    return False

def filter_inconsistent_execute_outputs(results, testcase_content):
    if "EliminateNullChecks" in testcase_content:
        return "false_positives"
    elif "java.nio.file" in testcase_content:
        false_positives["file operation"].append(results["hotspot-8"].source_issue_id)
        return "false_positives"
    elif "Math.random()" in testcase_content:
        false_positives["random number"].append(results["hotspot-8"].source_issue_id)
        return "false_positives"
    elif "System.nanoTime();" in testcase_content:
        false_positives["time operation"].append(results["hotspot-8"].source_issue_id)
        return "false_positives"
    # all jdk outputs are totally different (random operation, time information, ...)
    output_set = set()
    output_list = []
    for res in results.values():
        output_set.add(res.execute_stdout)
        lines = res.execute_stdout.splitlines()
        # if "CompileCommand:" in lines[0] or "CompilerOracle:" in lines[0]:
        #     lines = lines[1:]
        output_list.append(lines)
    if len(output_set) == 9:
        return "false_positives"
    # print(len(output_list[0]), len(output_list[1]), len(output_list[2]), len(output_list[3]), len(output_list[4]), len(output_list[5]), len(output_list[6]), len(output_list[7]), len(output_list[8]))
    if len(output_list[0]) ==  len(output_list[1]) == len(output_list[2]) == len(output_list[3]) == \
        len(output_list[4]) == len(output_list[5]) == len(output_list[6]) == len(output_list[7]) == len(output_list[8]):
        for line1, line2, line3, line4, line5, line6, line7, line8, line9 in zip(output_list[0], output_list[1], output_list[2], output_list[3], output_list[4], output_list[5], output_list[6], output_list[7], output_list[8]):
            if "version" in line1.lower() or "file path" in line1.lower() or "(ms)" in line1.lower():
                continue
            print(line1)
            if line1 == line2 == line3 == line4 == line5 == line6 == line7 == line8 == line9:
                continue
            elif classnotfound(line1) and classnotfound(line2) and classnotfound(line3) and classnotfound(line4) and classnotfound(line5) and classnotfound(line6) and classnotfound(line7) and classnotfound(line8) and classnotfound(line9):
                continue
            elif "error" in line1.lower() or "exception" in line1.lower():
                regex_error = r"([\w.]+(Error|Exception))"
                match1 = re.search(regex_error, line1)
                match2 = re.search(regex_error, line2)
                match3 = re.search(regex_error, line3)
                match4 = re.search(regex_error, line4)
                match5 = re.search(regex_error, line5)
                match6 = re.search(regex_error, line6)
                match7 = re.search(regex_error, line7)
                match8 = re.search(regex_error, line8)
                match9 = re.search(regex_error, line9)
                # print(line1)
                # print(line2)
                print(match1, match2, match3, match4, match5, match6, match7, match8, match9)
                if match1 and match2 and match3 and match4 and match5 and match6 and match7 and match8 and match9:
                    # print(match1.group(), match2.group(), match3.group(), match4.group(), match5.group(), match6.group(), match7.group(), match8.group(), match9.group())
                    # print("im here2")
                    if match1.group() == match2.group() == match3.group() == match4.group() == match5.group() == match6.group() == match7.group() == match8.group() == match9.group():
                        continue
                else:
                    # print("im here3")
                    return "still_anomalies"
            else:
                # print("im here4")
                return "still_anomalies"
        return "false_positives"
    # -XX:CompileCommand=compileonly,BitwiseIGVNTest.compute have output in hotspot and graalvm, but not in openjdk
    if "-XX:CompileCommand=" in testcase_content and \
        results["hotspot-17"].execute_stdout == results["hotspot-21"].execute_stdout == results["graalvm-21"].execute_stdout and \
        results["openj9-8"].execute_stdout == results["openj9-11"].execute_stdout == results["openj9-17"].execute_stdout == results["openj9-21"].execute_stdout:
        false_positives["compile command"].append(results["hotspot-8"].source_issue_id)
        return "false_positives"
    if compare_versions_attribute(results, "execute_stdout"):
        false_positives["different versions behave differently"].append(results["hotspot-8"].source_issue_id)
        return "false_positives"
    else:
        return "still_anomalies"

def filter_execution_timeout(results, testcase_content):
    print("check:", results["hotspot-21"].execute_time)
    if ".start" in testcase_content and ".stop" in testcase_content and results["hotspot-21"].execute_time == 60.00:
        potential_bugs["jdk21 timeouts when start and stop thread immediately which contains a large loop"].append(results["hotspot-8"].source_issue_id)
        return "potential_bugs"
    return "still_anomalies"

def filter_inconsistent_stderrs(results, testcase_content):
    return "still_anomalies"
    # stderr_list = []
    # for res in results.values():
    #     stderr_list.append(res.execute_stderr.splitlines())
    # if len(stderr_list[0]) ==  len(stderr_list[1]) == len(stderr_list[2]) == len(stderr_list[3]) == \
    #     len(stderr_list[4]) == len(stderr_list[5]) == len(stderr_list[6]) == len(stderr_list[7]) == len(stderr_list[8]):
    #     for line1, line2, line3, line4, line5, line6, line7, line8, line9 in zip(stderr_list[0], stderr_list[1], stderr_list[2], stderr_list[3], stderr_list[4], stderr_list[5], stderr_list[6], stderr_list[7], stderr_list[8]):
    #         if classnotfound(line1) and classnotfound(line2) and classnotfound(line3) and classnotfound(line4) and classnotfound(line5) and classnotfound(line6) and classnotfound(line7) and classnotfound(line8) and classnotfound(line9):
    #             continue
    #         elif line1 == line2 == line3 == line4 == line5 == line6 == line7 == line8 == line9:
    #             continue
    #         else:
    #             return "still_anomalies"
    #     return "false_positives"
    # else:
    #     return "still_anomalies"

partial_version_support = [ ["jdk.incubator"], ["java.lang.foreign.Arena"], ["java.lang.reflect.Field", "setAccessible"],
                            ["java.io.Reader", "transferTo"], ["java.lang.reflect.Method", "invoke"], ["var "], ["java.lang.foreign.Linker"], 
                            ["com.sun.source.util"], ["jdk.nashorn"], ["public record"], ["com.sun.tools.javac.tree"], ["java.lang.Object"]]

def filter(anomaly_type, anomaly_results, testcase_content):
    if "package com.example;" in testcase_content:
        false_positives["other"].append(anomaly_results["hotspot-8"].source_issue_id)
        return "false_positives"
    for keyword_group in partial_version_support:
        flag = False
        for keyword in keyword_group:
            if keyword not in testcase_content:
                flag = False
                break
            else:
                flag = True
        if flag:
            false_positives["partial versions support"].append(anomaly_results["hotspot-8"].source_issue_id)
            return "false_positives"

    print("anomaly_type:", anomaly_type)
    if anomaly_type == "some compile successfully, some failed":
        return filter_inconsistent_compile_returncode(anomaly_results, testcase_content)
    elif anomaly_type == "inconsistent outputs":
        return filter_inconsistent_execute_outputs(anomaly_results, testcase_content)
    elif anomaly_type == "some execution timeout":
        return filter_execution_timeout(anomaly_results, testcase_content)
    elif anomaly_type == "inconsistent exceptions or errors":
        return filter_inconsistent_stderrs(anomaly_results, testcase_content)
    return "still_anomalies"

def first_filter():
    conn = sqlite3.connect("../data/crossfuzz-enlargement.db")
    with open("anomalies_crossfuzz_gcc_4.json", "r") as f:
        anomalies = json.load(f)
    still_anomalies = {
        "some compile successfully, some failed": [],
        "some compile timeout": [],
        "compile crash": [],
        "inconsistent outputs": [],
        "inconsistent exceptions or errors": [],
        "some execution timeout": [],
        "execute crash": []
    }
    # os.makedirs(RESULT_DIR+"still_anomalies", exist_ok=True)
    # os.makedirs(RESULT_DIR+"false_positives", exist_ok=True)
    # os.makedirs(RESULT_DIR+"potential_bugs", exist_ok=True)
    for anomaly_type, anomaly_list in anomalies.items():
        for anomaly_id in anomaly_list:
            file_path = RESULT_DIR+f"Test{anomaly_id}.txt"
            # print(file_path)
            if not os.path.exists(file_path):
                continue
            with open(TESTCASE_DIR+f"Test{anomaly_id}.java", "r") as f:
                testcase_content = f.read()
            anomaly_results = query_one_testcase(conn, anomaly_id)
            folder = filter(anomaly_type, anomaly_results, testcase_content)
            if folder == "still_anomalies":
                still_anomalies[anomaly_type].append(anomaly_id)
            shutil.move(RESULT_DIR+f"Test{anomaly_id}.txt", f"{RESULT_DIR}{folder}/Test{anomaly_id}.txt")
            shutil.move(RESULT_DIR+f"Test{anomaly_id}.java", f"{RESULT_DIR}{folder}/Test{anomaly_id}.java")
        #     break
        # break
    with open("still_anomalies_cpython.json", "w") as f:
        json.dump(still_anomalies, f, indent=4)
    conn.close()

def second_filter():
    conn = sqlite3.connect("../data/crossfuzz.db")
    with open(RESULT_DIR+"still_anomalies.json", "r") as f:
        anomalies = json.load(f)
    # anomalies = {
    #     "inconsistent outputs": [],
    #     "inconsistent exceptions or errors": [],
    #     "some execution timeout": ["108214"]
    # }
    still_anomalies = {
        "some compile successfully, some failed": [],
        "some compile timeout": [],
        "compile crash": [],
        "inconsistent outputs": [],
        "inconsistent exceptions or errors": [],
        "some execution timeout": [],
        "execute crash": []
    }
    for anomaly_type, anomaly_list in anomalies.items():
        # if anomaly_type == "some compile timeout":
        #     for anomaly_id in anomaly_list:
        #         try:
        #             shutil.move(RESULT_DIR+f"still_anomalies/Test{anomaly_id}.txt", RESULT_DIR+f"compile_timeout/Test{anomaly_id}.txt")
        #             shutil.move(RESULT_DIR+f"still_anomalies/Test{anomaly_id}.java", RESULT_DIR+f"compile_timeout/Test{anomaly_id}.java")
        #         except FileNotFoundError:
        #             continue
        #     continue
        for anomaly_id in anomaly_list:
            f = RESULT_DIR+f"still_anomalies/Test{anomaly_id}.java"
            if not os.path.exists(f):
                continue
            with open(f, "r") as f:
                testcase_content = f.read()
            anomaly_results = query_one_testcase(conn, anomaly_id)
            new_folder = filter(anomaly_type, anomaly_results, testcase_content)
            # print(anomaly_id, new_folder)
            if new_folder != "still_anomalies":
                shutil.move(RESULT_DIR+f"still_anomalies/Test{anomaly_id}.txt", RESULT_DIR+f"{new_folder}/Test{anomaly_id}.txt")
                shutil.move(RESULT_DIR+f"still_anomalies/Test{anomaly_id}.java", RESULT_DIR+f"{new_folder}/Test{anomaly_id}.java")
            else:
                still_anomalies[anomaly_type].append(anomaly_id)
        #     break
        # break
    with open("still_anomalies.json", "w") as f:
        json.dump(still_anomalies, f, indent=4)
    conn.close()
    still_anomaly_num = 0
    max_key_length = max(len(k) for k in still_anomalies.keys())
    for k, v in still_anomalies.items():
        print(f"{k:<{max_key_length}} : {len(v):>4}")
        still_anomaly_num += len(v)
    print(f"still anomalies: {still_anomaly_num}")
    with open("potential_bugs.json", "w") as f:
        json.dump(potential_bugs, f, indent=4)
    with open("false_positives.json", "w") as f:
        json.dump(false_positives, f, indent=4)

if __name__ == "__main__":
    first_filter()
    # second_filter()