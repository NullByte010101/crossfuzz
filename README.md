# CrossFuzz

CrossFuzz is a tool for cross-language compiler testing. Its overall workflow is illustrated below:

<!-- 插入图片 -->
![CrossFuzz Workflow](overview_01.png)

## Bug List

The detailed bug list is omitted to preserve anonymity.

## Usage

### 1. Set Up the Python Environment

First, download the source code. Then, set up the Python environment as follows:

```bash
cd crossfuzz
conda create -n crossfuzz python=3.13
conda activate crossfuzz
pip install -r requirements.txt
```

### 2. Download Compilers

The versions of the target JVMs are listed below. All versions are the latest available as of June 30, 2026.

|JVM instance|Version|
|---|---|
|[HotSpot JDK8](https://github.com/openjdk/jdk8u/tags)|8u492-b09|
|[HotSpot JDK11](https://github.com/openjdk/jdk11u/tags)|11.0.31+11|
|[HotSpot JDK17](https://github.com/openjdk/jdk17u/tags)|17.0.19+10|
|[HotSpot JDK21](https://github.com/openjdk/jdk21u/tags)|21.0.11+10|
|[HotSpot JDK25](https://github.com/openjdk/jdk25u/tags)|25.0.3+9|
|[OpenJ9 JDK8](https://github.com/ibmruntimes/semeru8-binaries/releases)|8u492b09|
|[OpenJ9 JDK11](https://github.com/ibmruntimes/semeru11-binaries/releases)|11.0.31+11|
|[OpenJ9 JDK17](https://github.com/ibmruntimes/semeru17-binaries/releases)|17.0.19+10|
|[OpenJ9 JDK21](https://github.com/ibmruntimes/semeru21-binaries/releases)|21.0.11+10|
|[OpenJ9 JDK25](https://github.com/ibmruntimes/semeru25-binaries/releases)|25.0.3+9|
|[GraalVM JDK21](https://www.graalvm.org/downloads)|21.0.11|
|[GraalVM JDK25](https://www.graalvm.org/downloads)|25.1.3|

Please create the directory crossfuzz/jvms and place all downloaded JVMs in this folder.

Note that OpenJ9 and GraalVM distributions include prebuilt binaries. In contrast, the HotSpot JDK packages are provided as source code and must be compiled manually using the following commands:

```bash
bash ./configure
make all
```

### 3. Download the Database

All scripts read and write the SQLite database `data/db/crossfuzz.db`. Because of its size (346MB), it is not stored in this repository and is instead provided as a gzip-compressed file in the [data-v1 release](https://github.com/NullByte010101/crossfuzz/releases/tag/data-v1). Download and decompress it as follows:

```bash
cd crossfuzz
mkdir -p data/db
curl -L -o data/db/crossfuzz.db.gz https://github.com/NullByte010101/crossfuzz/releases/download/data-v1/crossfuzz.db.gz
gunzip data/db/crossfuzz.db.gz
```

The SHA-256 checksum of `crossfuzz.db` is `f7e52351a1280ad492ceb586ad241a17466cc428c3ea48b4bdd131480ddf4a79`.

### 4. Run CrossFuzz

4-1. Test case transpiling

We design a three-step prompt chain for test case transpiling: (1) bug report distillation, (2) cross-language semantic bridge, and (3) test case synthesis. All these steps are implemented in `step1_transform_testcase.py`. The results are stored in table `testcase_xxx`.

```bash
python step1_transform_testcase.py
```

4-2. Test case diversification

In this phase, we enlarge the test cases by searching for semantically similar APIs and generating new test cases. This step is implemented in `step2_enlarge_testcase.py`. The results are stored in table `enlargement_xxx`.

```bash
python step2_enlarge_testcase.py
```

4-3. Differential testing

In this phase, we run the test cases on different JVMs and identify anomalous behaviors. This step is implemented in `step3_differential_testing_multi_threads.py`. The results are stored in table `diff_test_xxx`.

```bash
python step3_differential_testing_multi_threads.py
```

### Auxiliary Tools

`clean.sh`: Cleans files generated during differential testing (e.g., crash reports and temporary files created by file operations).

`step4_1_filter.py`: Filters analyzed anomalous behaviors from testing results.

`step4_2_run_one.py`: Reproduces identified anomalous behaviors.

