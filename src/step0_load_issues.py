import pandas as pd
import numpy as np
import sqlite3
import re


def connect_db():
    conn = sqlite3.connect("../data/db/oopsla-tmp.db")
    cursor = conn.cursor()
    return conn, cursor

""" CHECK IF ISSUE IS COMPILER BUG """

def is_gcc_bugs(status, title):
    if status in ["RESOLVED\n          WONTFIX", "RESOLVED\n          INVALID"]:
        return False
    if title is None:
        return False
    title = title.lower()
    filter_keywords = ["add ", "feature request"]
    if any(keyword in title for keyword in filter_keywords):
        return False
    return True

def is_clang_bug(label):
    if label is None:
        return True
    if "question" in label or "enhancement" in label or "wontfix" in label:
        return False
    return False

def is_rustc_bug(keyword, component):
    if keyword is None or component is None:
        return False
    if "T-compiler" in component and "C-bug" in keyword:
        return True
    return False

def is_cpython_bug(label):
    if label is None:
        return False
    return "type-bug" in label or "type-security" in label or "type-crash" in label or "performance" in label

def is_pypy_bug(label):
    if label is None:
        return False
    return "bug" in label

""" FILTER ISSUES WHICH ARE NOT IN CORE MODULES """

def reject_by_title(title: str):
    title = title.lower()
    filter_keywords = ["is not supported on", "makefile", "comment", "documentation", "build", "install", "deprecated", "ftbfs"]
    return any(keyword in title for keyword in filter_keywords)

def reject_for_clang(label):
    if "documentation" in label:
        return True
    return False

def reject_for_cpython(label):
    if label is None:
        return True
    useless_label = ["build", "invalid"]
    for k in useless_label:
        if k in label:
            return True
    return False

""" MAIN METHODS """

def read_from_xlsx(conn, cursor, compiler_name):
    """
    Load issues from xlsx files.
    Filter issues by year, title, comment, and status.
    """
    
    # read xlsx file
    df = pd.read_csv(f"../data/fyt-2/{compiler_name}_bugs.csv")
    # if compiler_name in ["pypy", "cpython"]:
    #     df = pd.read_csv(f"../data/{compiler_name}_bugs.csv")
    # elif compiler_name in ["gcc", "clang", "rustc"]:
    #     df = pd.read_excel(f"../data/{compiler_name}_bugs.xlsx")
    
    # create table
    cursor.execute(f"DROP TABLE IF EXISTS {compiler_name}_bugs")
    cursor.execute(f"""
    CREATE TABLE {compiler_name}_bugs (
        id INT PRIMARY KEY,
        title TEXT,
        description LONGTEXT,
        comment LONGTEXT,
        test_case TEXT,
        created_time DATE,
        component VARCHAR(255),
        keyword VARCHAR(255),
        status VARCHAR(255)
    )""")
    # replace nan with None
    df = df.replace({np.nan: None})
    # insert data
    bug_num, filtered_bug_num, rejected = 0, 0, 0
    for index, row in df.iterrows():
        # print("row:", row)
        if pd.isnull(row['id']):
            break
        # only consider issues created in 2023.10.31 ~ 2025.10.31
        try:
            created_time = pd.to_datetime(row['created_time'])
            end = pd.to_datetime('2025-12-31')
            if created_time > end:
                continue
        except:
            continue
        # start = pd.to_datetime('2022-10-31')
        # end = pd.to_datetime('2025-10-31')
        # if created_time > end or created_time < start:
        #     continue
        # only consider bugs
        # if compiler_name == "pypy" and not is_pypy_bug(row['keyword']):
        #     continue
        if compiler_name == "rustc" and not is_rustc_bug(row['keyword'], row['component']):
            continue
        if compiler_name == "cpython" and not is_cpython_bug(row['keyword']):
            continue
        if compiler_name == "clang" and not is_clang_bug(row['keyword']):
            continue
        if compiler_name == "gcc" and not is_gcc_bugs(row['status'], row['title']):
            continue
        bug_num += 1
        # filter issues by title
        if reject_by_title(row['title']):
            rejected += 1
            continue
        # filter issues by labels
        if compiler_name == "cpython" and reject_for_cpython(row['component']):
            rejected += 1
            continue
        if compiler_name == "clang" and reject_for_clang(row['component']):
            rejected += 1
            continue
        # if compiler_name == "gcc" and reject_for_gcc(row["status"]):
        #     rejected += 1
        #     continue
        print("processing:", index)
        # print("id:", row['id'])
        # cursor.execute(f"""INSERT INTO {compiler_name}_bugs (id, title, description, comment, test_case, created_time, component, keyword, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
        #     (row['id'], row['title'], row['description'], row['comment'], row['test_case'], row['created_time'], row['component'], row['keyword'], row['status']))
        cursor.execute(f"""INSERT INTO {compiler_name}_bugs (id, title, description, comment, test_case, created_time, component, keyword, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
            (row['id'], row['title'], row['description'], row['comment'], None, row['created_time'], row['component'], row['keyword'], row['status']))
        conn.commit()
        filtered_bug_num += 1
    # close connection
    cursor.close()
    conn.close()
    print(f"Total {bug_num} bugs are loaded from {compiler_name}_bugs.xlsx")
    print(f"{filtered_bug_num} bugs are filtered by title, comment, and status")
    print(f"{rejected} bugs are rejected")


def clear_comment(conn, cursor, compiler_name):
    # create table {compiler_name}_bugs_cleared
    cursor.execute(f"DROP TABLE IF EXISTS {compiler_name}_bugs_cleared")
    cursor.execute(f"""CREATE TABLE {compiler_name}_bugs_cleared (
        id INT PRIMARY KEY,
        title VARCHAR(255),
        description TEXT,
        comment TEXT,
        test_case TEXT,
        created_time DATE,
        component VARCHAR(255),
        keyword VARCHAR(255),
        status VARCHAR(255)
    )""")
    # read data from {compiler_name}_bugs
    cursor.execute(f"SELECT * FROM {compiler_name}_bugs")
    data = cursor.fetchall()
    for row in data:
        comments = row[3]
        if comments is None:
            cursor.execute(f"""INSERT INTO {compiler_name}_bugs_cleared (id, title, description, comment, test_case, created_time, component, keyword, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (row[0], row[1], row[2], comments, row[4], row[5], row[6], row[7], row[8]))
            conn.commit()
            continue
        # 用正则表达式<<<COMMENT\_\d+>>>匹配每条评论，并进行切分
        comments = re.sub(r'<<<COMMENT_\d+>>>', '<<<>>>', comments)
        processed_comments = []
        for comment in comments.split('<<<>>>'):
            comment = comment.strip()
            if comment.startswith("Fixed") or comment.endswith("fixed."):
                continue
            elif comment.startswith("Closed"):
                continue
            elif comment.startswith("Done"):
                continue
            elif comment.startswith("Dup") or comment.startswith("dup"):
                continue
            elif comment.startswith("Thanks"):
                continue
            elif comment.startswith("Patch commited") or comment.startswith("Patch committed") or comment.startswith("Patch applied"):
                continue
            elif comment.endswith("is being closed.") or comment.endswith("is being closed"):
                continue
            elif comment.endswith("has been marked as a duplicate of this bug. ***"):
                continue
            elif comment.startswith("Is") and comment.endswith("?"):
                continue
            elif comment.startswith("Should") and comment.endswith("?"):
                continue
            comment = comment.replace("Thanks.", "").replace("Thanks!", "")
            processed_comments.append(comment)
        comments = '\n<<<>>>\n' .join(processed_comments)
        cursor.execute(f"""INSERT INTO {compiler_name}_bugs_cleared (id, title, description, comment, test_case, created_time, component, keyword, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row[0], row[1], row[2], comments, row[4], row[5], row[6], row[7], row[8]))
        conn.commit()
    # close connection
    cursor.close()
    conn.close()


if __name__ == '__main__':
    conn, cursor = connect_db()
    choice = input("1-load issues; 2-clear comments: ")
    compiler_name = input("compiler name: ")
    if choice == "1":
        read_from_xlsx(conn, cursor, compiler_name)
    elif choice == "2":
        clear_comment(conn, cursor, compiler_name)
    else:
        print("invalid choice")