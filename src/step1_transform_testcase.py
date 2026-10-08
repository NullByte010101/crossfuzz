from termcolor import cprint
import random
import json5
import json
import shutil
import os
import re

from database import DBHandler
from utils.tools import *
from utils.config_loader import config

COMPILER_NAME = config.get("step1.compiler_name")
BUG_TABLE = config.get("step1.bug_table")
TABLE_NAME = config.get("step1.table_name")
SKIP_TESTCASE_DIR = config.path("step1.skip_testcase_dir")
SKIP_ISSUE_LIST = config.path("step1.skip_issue_list")
OUTPUT_DIR = config.path("step1.output_dir")

def main():
    dbhandler = DBHandler()
    
    # obtain issue ids
    dbhandler.cursor.execute(f"select id from {BUG_TABLE}")
    issue_id_list = [issue[0] for issue in dbhandler.cursor.fetchall()]
    already_writed = []
    # TMP.
    # for f in os.listdir(f"../data/testcases-{COMPILER_NAME}-2-v1"):
    #     issue_str = f.split(".")[0].replace("Test", "")
    #     already_writed.append(int(issue_str))
    # Skipping already processed issues is optional: missing paths are ignored
    if os.path.isdir(SKIP_TESTCASE_DIR):
        for f in os.listdir(SKIP_TESTCASE_DIR):
            if f.endswith(".txt"):
                continue
            issue_str = f.split(".")[0].replace("Test", "")
            already_writed.append(int(issue_str))
    else:
        print(f"skip_testcase_dir not found, nothing skipped: {SKIP_TESTCASE_DIR}")
    if os.path.isfile(SKIP_ISSUE_LIST):
        with open(SKIP_ISSUE_LIST, "r") as f:
            already_writed += [int(line.strip()) for line in f.readlines()]
    else:
        print(f"skip_issue_list not found, nothing skipped: {SKIP_ISSUE_LIST}")
    # tmp_issue_id_list = list(set(issue_id_list)-set(already_writed))
    # selected_issue_id_list = random.sample(tmp_issue_id_list, 500)
    selected_issue_id_list = list(set(issue_id_list)-set(already_writed))
    print("issue_id_list:", len(issue_id_list))
    print("selected_issue_id_list:", len(selected_issue_id_list))
    # return
    
    # create table or obtain already generated
    new_table = TABLE_NAME
    choice = input(f"Create new table {new_table}? (y/n) ")
    if choice == "y":
        dbhandler.cursor.execute(f"drop table if exists {new_table}")
        dbhandler.cursor.execute(f"""create table {new_table} (
            id integer primary key autoincrement,
            source_issue_id integer,
            analysis text,
            transformed_analysis text,
            testcases text)""")
        dbhandler.conn.commit()
        already_generated = []
        # dbhandler.cursor.execute(f"""select source_issue_id from testcase_{COMPILER_NAME}_1""")
        # results = dbhandler.cursor.fetchall()
        # already_generated = [issue[0] for issue in results]
    else:
        dbhandler.cursor.execute(f"select source_issue_id from {new_table}")
        results = dbhandler.cursor.fetchall()
        already_generated = [issue[0] for issue in results]
        # dbhandler.cursor.execute(f"""select source_issue_id from testcase_{COMPILER_NAME}_1""")
        # results = dbhandler.cursor.fetchall()
        # already_generated += [issue[0] for issue in results]
    print("already_generated:", len(already_generated))
    selected_issue_id_list = list(set(selected_issue_id_list)-set(already_generated))
    print("still need to process:", len(selected_issue_id_list))
    # return
    
    # create result folder
    flag2 = input("Create a new result foler? (y/n) ")
    if flag2 == "y":
        if os.path.exists(OUTPUT_DIR):
            shutil.rmtree(OUTPUT_DIR)
        os.makedirs(OUTPUT_DIR)
    
    # start processing
    for issue_id in selected_issue_id_list:
        # if already generated, skip
        # if int(issue_id) in already_generated:
        #     continue
        cprint(f"processing {issue_id}", "blue")
        # obtain bug report content
        dbhandler.cursor.execute(f"""select title, description, comment from {BUG_TABLE} where id=?""", (issue_id,))
        rows = dbhandler.cursor.fetchall()
        if len(rows) == 0:
            print("already removed")
            continue
        title, description, comment = rows[0]
        if description is None and comment is None:
            continue
        elif description is None:
            bug_report_content = title+"\n"+comment
        elif comment is None:
            bug_report_content = title+"\n"+description
        else:
            bug_report_content = title+"\n"+description+"\n"+comment
        if count_tokens(bug_report_content) > 10000:
            print("too long")
            continue
        # call llm to analyze
        analysis = call_llm(1, COMPILER_NAME, bug_report_content)
        if analysis is None or len(analysis) == 0:
            print("analysis is empty")
            continue
        dbhandler.cursor.execute(f"insert into {new_table} (source_issue_id, analysis) values (?, ?)", (issue_id, analysis))
        dbhandler.conn.commit()
        with open(os.path.join(OUTPUT_DIR, f"analysis{issue_id}.txt"), "w") as f:
            f.write(analysis)
        if "\"root_cause\": \"\"" in analysis:
            # dbhandler.cursor.execute(f"delete from {BUG_TABLE} where id={issue_id}")
            continue
        # call llm to transform
        transformed_analysis = call_llm(2, COMPILER_NAME, analysis)
        if transformed_analysis is None or len(transformed_analysis) == 0:
            print("transformed_analysis is empty")
            continue
        dbhandler.cursor.execute(f"update {new_table} set transformed_analysis=? where source_issue_id=?", (transformed_analysis, issue_id))
        dbhandler.conn.commit()
        with open(os.path.join(OUTPUT_DIR, f"transformed_analysis{issue_id}.txt"), "w") as f:
            f.write(transformed_analysis)
        if "\"potential_root_cause\": \"\"" in transformed_analysis:
            continue
        # call llm to generate testcases
        testcases = call_llm(3, COMPILER_NAME, transformed_analysis)
        if len(testcases) == 0:
            print("testcases is empty")
            continue
        write_down(COMPILER_NAME, testcases, issue_id, os.path.join(OUTPUT_DIR, ""))
        dbhandler.cursor.execute(f"update {new_table} set testcases=? where source_issue_id=?", (testcases, issue_id))
        dbhandler.conn.commit()
        # break
    dbhandler.close()


if __name__ == "__main__":
    input("folder path in tools.py has been modified, check it.")
    main()
