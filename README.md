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

The versions of the target JVMs are listed below:

|JVM instance|Version|
|---|---|
|[HotSpot JDK8](https://github.com/openjdk/jdk8u/tags)|8u492-b00|
|[HotSpot JDK11](https://github.com/openjdk/jdk11u/tags)|11.0.31-0|
|[HotSpot JDK17](https://github.com/openjdk/jdk17u/tags)|17.0.18-7|
|[HotSpot JDK21](https://github.com/openjdk/jdk21u/tags)|21.0.10-6|
|[OpenJ9 JDK8](https://github.com/ibmruntimes/semeru8-binaries/releases)|8u472b08_openj9-0.56.0|
|[OpenJ9 JDK11](https://github.com/ibmruntimes/semeru11-binaries/releases)|11.0.29_7_openj9-0.56.0|
|[OpenJ9 JDK17](https://github.com/ibmruntimes/semeru17-binaries/releases)|jdk-17.0.17_10_openj9-0.56.0|
|[OpenJ9 JDK21](https://github.com/ibmruntimes/semeru21-binaries/releases)|21.0.9_10_openj9-0.56.0|
|[GraalVM JDK21](https://www.graalvm.org/downloads)|21.0.9|

Please create the directory crossfuzz/jvms and place all downloaded JVMs in this folder.

Note that OpenJ9 and GraalVM distributions include prebuilt binaries. In contrast, the HotSpot JDK packages are provided as source code and must be compiled manually using the following commands:

```bash
bash ./configure
make all
```

### 3. Run CrossFuzz

3-1. Test case transpiling

We design a three-step prompt chain for test case transpiling: (1) bug report distillation, (2) cross-language semantic bridge, and (3) test case synthesis. All these steps are implemented in `step1_transform_testcase.py`. The results are stored in table `testcase_xxx`.

```bash
python step1_transform_testcase.py
```

3-2. Test case diversification

In this phase, we enlarge the test cases by searching for semantically similar APIs and generating new test cases. This step is implemented in `step2_enlarge_testcase.py`. The results are stored in table `enlargement_xxx`.

```bash
python step2_enlarge_testcase.py
```

3-3. Differential testing

In this phase, we run the test cases on different JVMs and identify anomalous behaviors. This step is implemented in `step3_differential_testing_multi_threads.py`. The results are stored in table `diff_test_xxx`.

```bash
python step3_differential_testing_multi_threads.py
```

### Auxiliary Tools

`clean.sh`: Cleans files generated during differential testing (e.g., crash reports and temporary files created by file operations).

`step4_1_filter.py`: Filters analyzed anomalous behaviors from testing results.

`step4_2_run_one.py`: Reproduces identified anomalous behaviors.

