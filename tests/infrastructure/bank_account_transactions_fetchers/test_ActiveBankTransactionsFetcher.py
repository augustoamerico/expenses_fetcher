import glob
import os
import pathlib
import shutil

import pytest


class TestActiveBankTransactionsFetcher:
    @staticmethod
    def __get_integration_tests_assets_path():
        return os.path.join(pathlib.Path(__file__).parent.absolute(), "assets")

    def setup_target_directory(self):
        self.clean_tests_outputs()
        os.mkdir(
            os.path.join(
                self.__get_integration_tests_assets_path(), TARGET_DIRECTORY_NAME
            )
        )

    def clean_tests_outputs(self):
        output_folder = os.path.join(
            self.__get_integration_tests_assets_path(), TARGET_DIRECTORY_NAME
        )
        try:
            if os.path.exists(output_folder) and os.path.isdir(output_folder):
                shutil.rmtree(output_folder)
        except Exception as e:
            raise Exception("Failed to delete %s. Reason: %s" % (output_folder, e))

    @pytest.fixture
    def spark(self):
        spark = (
            SparkSession.builder.master("local[1]")
            .appName("IntegrationTests")
            .getOrCreate()
        )
        return spark

    @pytest.fixture
    def file_system_driver(self, spark):
        return FileSystemDriver(
            spark=spark, base_path=self.__get_integration_tests_assets_path()
        )

    @pytest.fixture
    def partition_selector(self, file_system_driver):
        base_path = os.path.join(
            self.__get_integration_tests_assets_path(), SOURCE_DIRECTORY_NAME
        )
        compaction_path = os.path.join(
            self.__get_integration_tests_assets_path(), TARGET_DIRECTORY_NAME
        )

        return DailyPartitionSelector(
            filesystem=file_system_driver,
            base_path=base_path,
            compaction_path=compaction_path,
        )

    @pytest.fixture
    def spark_data_driver(self, spark):
        return SparkDataDriver(spark)

    @pytest.fixture
    def directory_compactor(self, file_system_driver, spark_data_driver):
        base_path = os.path.join(
            self.__get_integration_tests_assets_path(), SOURCE_DIRECTORY_NAME
        )
        compaction_path = os.path.join(
            self.__get_integration_tests_assets_path(), TARGET_DIRECTORY_NAME
        )

        return DirectoryCompactor(
            filesystem=file_system_driver,
            data_driver=spark_data_driver,
            base_path=base_path,
            compaction_path=compaction_path,
        )

    @pytest.fixture
    def datalake_compaction_manager(
        self, file_system_driver, partition_selector, directory_compactor
    ):
        base_path = os.path.join(
            self.__get_integration_tests_assets_path(), SOURCE_DIRECTORY_NAME
        )

        return DataLakeCompactionManager(
            filesystem=file_system_driver,
            partition_selector=partition_selector,
            directory_compactor=directory_compactor,
            base_path=base_path,
        )

    def test_compact_shouldCompactCertainPartitions(self, datalake_compaction_manager):
        self.setup_target_directory()

        datalake_compaction_manager.compact()
        target_directories = {
            path.replace(f"tests/integration_tests/assets/{TARGET_DIRECTORY_NAME}", "")
            for path in glob.glob(
                f"tests/integration_tests/assets/{TARGET_DIRECTORY_NAME}/*/*/*/*"
            )
        }
        source_directories = {
            path.replace(f"tests/integration_tests/assets/{SOURCE_DIRECTORY_NAME}", "")
            for path in glob.glob(
                f"tests/integration_tests/assets/{SOURCE_DIRECTORY_NAME}/*/*/*/*"
            )
        }

        source_directories.discard("/defined.crowd.topic4/year=2020/month=03/day=20")

        self.clean_tests_outputs()

        assert target_directories == source_directories
