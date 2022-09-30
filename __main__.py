import os
from configparser import ConfigParser

from pyspark.sql import DataFrame, SparkSession

from column_clustering import col_folding_pyspark
from dataset_clustering import cluster_datasets_pyspark
from extract_labels import generate_labels_pyspark
from handle_data import generate_csv_paths


def run_experiments(
    exp_name: str,
    exp_number: int,
    labeling_budget: int,
    extract_labels_enabled: int,
    table_grouping_enabled: int,
    column_grouping_enabled: int,
    sandbox_path: str,
    output_path: str,
    labels_path: str,
    table_grouping_output_path: str,
    table_auto_clustering: int,
    cols_auto_clustering: int,
    cells_clustering_alg: str,
    cell_feature_generator_enabled: int,
) -> None:
    """_summary_

    Args:
        exp_name (str): _description_
        exp_number (int): _description_
        labeling_budget (int): _description_
        extract_labels_enabled (int): _description_
        table_grouping_enabled (int): _description_
        column_grouping_enabled (int): _description_
        sandbox_path (str): _description_
        output_path (str): _description_
        labels_path (str): _description_
        table_grouping_output_path (str): _description_
        table_auto_clustering (int): _description_
        cols_auto_clustering (int): _description_
        cells_clustering_alg (str): _description_
        cell_feature_generator_enabled (int): _description_
    """
    logger.warn("Genereting CSV paths")
    csv_paths_df = generate_csv_paths(sandbox_path)

    logger.warn("Generating labels")
    labels_df = generate_labels_pyspark(
        csv_paths_df,
        os.path.join(output_path, labels_path),
        extract_labels_enabled,
    )

    logger.warn("Creating experiment output directory")
    experiment_output_path = os.path.join(output_path, exp_name)
    if not os.path.exists(experiment_output_path):
        os.makedirs(experiment_output_path)

    logger.warn("Grouping tables")
    table_grouping_df = cluster_datasets_pyspark(
        csv_paths_df,
        os.path.join(output_path, table_grouping_output_path),
        table_grouping_enabled,
        table_auto_clustering,
    )

    logger.warn("Grouping columns")
    column_groups_path = os.path.join(
        experiment_output_path, configs["DIRECTORIES"]["column_groups_path"]
    )
    column_grouping_df = col_folding_pyspark(
        csv_paths_df=csv_paths_df,
        labels_df=labels_df,
        table_cluster_df=table_grouping_df,
        column_groups_path=column_groups_path,
        column_grouping_enabled=column_grouping_enabled,
        auto_clustering_enabled=cols_auto_clustering,
    )
    column_grouping_df.show()


if __name__ == "__main__":
    spark = SparkSession.builder.appName("ED-Scale").getOrCreate()
    # Workaround for logging. At log level INFO our log messages will be lost. Python's logging module does not work with pyspark.
    spark.sparkContext.setLogLevel("WARN")
    log4jLogger = spark._jvm.org.apache.log4j
    logger = log4jLogger.LogManager.getLogger(__name__)
    logger.warn("Pyspark initialized")

    logger.warn("Reading config")
    configs = ConfigParser()
    configs.read("config.ini")

    logger.warn("Creating output directory")
    if not os.path.exists(configs["DIRECTORIES"]["output_dir"]):
        os.makedirs(configs["DIRECTORIES"]["output_dir"])

    logger.warn("Starting experiments")
    # TODO: outsoure running the different experiments in python. Maybe better solution to submit each experiment individually for cluster execution.
    for exp_number in [
        int(number)
        for number in configs["EXPERIMENTS"]["experiment_numbers"].split(",")
    ]:
        for number_of_labels in [
            int(number)
            for number in configs["EXPERIMENTS"]["number_of_labels_list"].split(",")
        ]:
            logger.warn(
                "Runing experiment: Number:{} Labels:{}".format(
                    exp_number, number_of_labels
                )
            )
            run_experiments(
                exp_name=configs["EXPERIMENTS"]["exp_name"],
                labeling_budget=number_of_labels,
                exp_number=exp_number,
                extract_labels_enabled=int(
                    configs["EXPERIMENTS"]["extract_labels_enabled"]
                ),
                table_grouping_enabled=int(
                    configs["EXPERIMENTS"]["table_grouping_enabled"]
                ),
                column_grouping_enabled=int(
                    configs["EXPERIMENTS"]["column_grouping_enabled"]
                ),
                cell_feature_generator_enabled=int(
                    configs["EXPERIMENTS"]["cell_feature_generator_enabled"]
                ),
                table_auto_clustering=int(
                    configs["TABLE_GROUPING"]["auto_clustering_enabled"]
                ),
                cols_auto_clustering=int(
                    configs["COLUMN_GROUPING"]["auto_clustering_enabled"]
                ),
                sandbox_path=configs["DIRECTORIES"]["sandbox_dir"],
                output_path=configs["DIRECTORIES"]["output_dir"],
                labels_path=configs["DIRECTORIES"]["labels_filename"],
                table_grouping_output_path=configs["DIRECTORIES"][
                    "table_grouping_output_filename"
                ],
                cells_clustering_alg=configs["CLUSTERING"]["cells_clustering_alg"],
            )