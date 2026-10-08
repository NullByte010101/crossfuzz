from sentence_transformers import SentenceTransformer, util
from termcolor import cprint
import sqlite3
import json
import os
import re

# from utils.tools import *
from utils.tools import write_down, parse_output, call_llm

COMPILER_NAME = "gcc"
TABLE_NAME = "gcc_2"
OUTPUT_DIR = f"../data/testcases-gcc-4"

def find_similar_methods(model, merged_info, source_issue_id, description, class_embeddings, cursor):
    # use sentence-transformer to calculate cosine similarity
    description_embeddings = model.encode([description])
    cosine_scores = util.pytorch_cos_sim(description_embeddings, class_embeddings)
    for j, merged_name in enumerate(merged_info.keys()):
        score = cosine_scores[0][j].item()
        if score > 0.5:
            cursor.execute(f"INSERT INTO enlargement_{TABLE_NAME} (source_issue_id, merged_info_id, merged_name, score) VALUES ('{source_issue_id}', '{j}', '{merged_name}', {score})")

def enlarge():
    # prepare necessary data
    cprint("Prepare necessary data...", "blue")
    choice = input("Delete the analyzed record? [y/n] ")
    analyzed_issues_path = "../data/analyzed_issues.txt"
    if choice == "y":
        if os.path.exists(analyzed_issues_path):
            os.remove(analyzed_issues_path)
        analyzed_issues = []
    else:
        with open(analyzed_issues_path, "r") as f:
            analyzed_issues = f.readlines()
    # model = SentenceTransformer('../model/minilm-l6-v2')
    model = SentenceTransformer('../model/all-mpnet-base-v2', device='cuda')
    with open("../data/method_description.json", "r") as f:
        merged_info = json.load(f)
    class_embeddings = model.encode(list(merged_info.values()))
    cprint("Finished preparing necessary data", "blue")
    
    db = sqlite3.connect('../data/db/crossfuzz.db')
    cursor = db.cursor()
    cursor.execute(f"DROP TABLE IF EXISTS enlargement_{TABLE_NAME}")
    cursor.execute(f"CREATE TABLE enlargement_{TABLE_NAME} (source_issue_id INT, merged_info_id INT, merged_name TEXT, score REAL)")
    cursor.execute(f"SELECT source_issue_id, transformed_analysis FROM testcase_{TABLE_NAME}")
    results = cursor.fetchall()
    processed = 0
    for row in results:
        source_issue_id = row[0]
        if source_issue_id in analyzed_issues:
            continue
        if row[1] is None:
            continue
        cprint(f"Processing: {source_issue_id}", "blue")
        try:
            transformed_analysis = parse_output(row[1])
        except Exception as e:
            print(f"Error: {e}")
            continue
        find_similar_methods(model, merged_info, source_issue_id, transformed_analysis["potential_root_cause"], class_embeddings, cursor)
        db.commit()
        with open(analyzed_issues_path, "a+") as f:
            f.write(f"{source_issue_id}\n")
        processed += 1
        # if processed == 10:
        #     break

def one_step(user_input, merged_name, source_issue_id, merged_info_id):
    new_testcase = call_llm(4, COMPILER_NAME, user_input)
    if new_testcase is None:
        raise Exception("new_testcase is None")
    comment = "// "+merged_name
    try:
        write_down(COMPILER_NAME, new_testcase, f"{source_issue_id}_{merged_info_id}", f"../data/testcases-{COMPILER_NAME}-4/", comment)
    except Exception as e:
        print(e)

def generate_new_testcases():
    with open("../data/method_description.json", "r") as f:
        merged_info = json.load(f)
    db = sqlite3.connect('../data/db/crossfuzz.db')
    cursor = db.cursor()
    cursor.execute(f"SELECT * FROM enlargement_{TABLE_NAME} WHERE score > 0.65")
    #  ORDER BY score DESC
    results = cursor.fetchall()
    print("size of results:", len(results))
    already_generated = []
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    for f in os.listdir(OUTPUT_DIR):
        match = re.search(r'(\d+)_(\d+)', f)
        if match:
            already_generated.append((match.group(1), match.group(2)))
    print("size of already_generated:", len(already_generated))
    for row in results:
        source_issue_id = row[0]
        merged_info_id = row[1]
        print("source_issue_id:", source_issue_id)
        print("merged_info_id:", merged_info_id)
        if (str(source_issue_id), str(merged_info_id)) in already_generated:
            print("skip")
            continue
        merged_name = row[2]
        cursor.execute(f"SELECT source_issue_id, transformed_analysis FROM testcase_{TABLE_NAME} WHERE source_issue_id = {source_issue_id}")
        testcase_results = cursor.fetchall()
        print("size of testcase_results:", len(testcase_results))
        for testcase_result in testcase_results:
            source_issue_id = testcase_result[0]
            transformed_analysis = testcase_result[1]
            user_input = "Provided bug description:\n"+transformed_analysis+"\nSimilar method:\n"+merged_name+merged_info[merged_name]
            # print("user_input:\n", user_input)
            one_step(user_input, merged_name, source_issue_id, merged_info_id)
            # break
        # break
    db.close()

if __name__ == "__main__":
    choice = input("(1) enlarge (2) generate new testcases: ")
    if choice == "1":
        enlarge()
    elif choice == "2":
        generate_new_testcases()
