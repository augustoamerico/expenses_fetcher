#!/bin/bash

#####
# $1 is path for tests folder. If empty, assumes it is ./tests
#
#
####

if [ -z "$1" ]
then
 UNIT_TESTS_PATH="$(pwd)/tests"
else
 UNIT_TESTS_PATH="$1"
fi

echo "UNIT_TESTS_PATH=$UNIT_TESTS_PATH"

TEST_COVERAGE_PATH=$(dirname $UNIT_TESTS_PATH)/test_coverage
COVERAGE_REPORT_XML_OUTPUT_PATH="${TEST_COVERAGE_PATH}/coverage.xml"
COVERAGE_REPORT_HTML_OUTPUT_PATH="${TEST_COVERAGE_PATH}/htmlcov"
COVERAGE_REPORT_JUNIT_OUTPUT_PATH="${TEST_COVERAGE_PATH}/junit/test-unit-results.xml"
COVERED_CODE=$(dirname $UNIT_TESTS_PATH)/src

mkdir $TEST_COVERAGE_PATH
python -m pytest ${UNIT_TESTS_PATH} --rootdir="./tests/integration_tests" --doctest-modules --junitxml=$COVERAGE_REPORT_JUNIT_OUTPUT_PATH --cov=$COVERED_CODE --cov-report=xml:$COVERAGE_REPORT_XML_OUTPUT_PATH --cov-report=html:$COVERAGE_REPORT_HTML_OUTPUT_PATH
