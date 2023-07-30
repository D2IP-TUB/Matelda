import logging
import math
from statistics import mode

import numpy as np
import pandas as pd
from scipy.spatial.distance import euclidean
from sklearn.cluster import MiniBatchKMeans


def get_n_labels(cluster_sizes_df, labeling_budget, min_num_labes_per_col_cluster):
    cluster_sizes_df["n_labels"] = cluster_sizes_df.apply(
        lambda x: min(min_num_labes_per_col_cluster, x["n_cells"]), axis=1
    )
    cluster_sizes_df["sampled"] = cluster_sizes_df.apply(lambda x: False, axis=1)
    used_labels = cluster_sizes_df["n_labels"].sum()
    num_total_cells = cluster_sizes_df["n_cells"].sum()
    if labeling_budget > used_labels:
        remaining_labels = labeling_budget - used_labels
        cluster_sizes_df["n_labels"] = cluster_sizes_df.apply(
            lambda x: x["n_labels"]
            + math.floor(
                min(
                    x["n_cells"] - x["n_labels"],
                    (x["n_cells"] / num_total_cells) * remaining_labels,
                )
            ),
            axis=1,
        )
    i = 0
    cluster_sizes_df.sort_values(by=["n_cells"], ascending=False, inplace=True)
    while labeling_budget > cluster_sizes_df["n_labels"].sum():
        if cluster_sizes_df["n_labels"].iloc[i] < cluster_sizes_df["n_cells"].iloc[i]:
            cluster_sizes_df["n_labels"].iloc[i] = (
                cluster_sizes_df["n_labels"].iloc[i] + 1
            )
            i += 1
    return cluster_sizes_df


def cell_clustering(table_cluster, col_cluster, x, y, n_cell_clusters_per_col_cluster, n_cores):
    # logging.info(
    #     "Cell Clustering - table_cluster: %s, col_cluster: %s",
    #     table_cluster,
    #     col_cluster,
    # )
    clustering = None
    cells_per_cluster = {}
    errors_per_cluster = {}
    cell_clustering_dict = {
        "table_cluster": [],
        "col_cluster": [],
        "n_cells": [],
        "n_init_labels": [],
        "n_produced_cell_clusters": [],
        "n_current_requiered_labels": [],
        "remaining_labels": [],
        "cells_per_cluster": [],
        "errors_per_cluster": [],
    }
    n_cell_clusters_per_col_cluster = min(len(x), n_cell_clusters_per_col_cluster)
    logging.debug(
        "KMeans - n_cell_clusters_per_col_cluster: %s", n_cell_clusters_per_col_cluster
    )
    clustering = MiniBatchKMeans(
        n_clusters=int(n_cell_clusters_per_col_cluster),
        batch_size=256 * n_cores,
    ).fit(x)
    logging.debug("KMeans - n_cell_clusters_generated: %s", len(set(clustering.labels_)))
    clustering_labels = clustering.labels_
    for cell in enumerate(clustering_labels):
        if cell[1] in cells_per_cluster:
            cells_per_cluster[cell[1]].append(cell[0])
            if y[cell[0]] == 1:
                errors_per_cluster[cell[1]] += 1
        else:
            cells_per_cluster[cell[1]] = [cell[0]]
            errors_per_cluster[cell[1]] = y[cell[0]]

    cell_clustering_dict["table_cluster"] = table_cluster
    cell_clustering_dict["col_cluster"] = col_cluster
    cell_clustering_dict["n_cells"] = len(x)
    cell_clustering_dict["n_init_labels"] = n_cell_clusters_per_col_cluster
    cell_clustering_dict["n_produced_cell_clusters"] = len(set(clustering.labels_))
    cell_clustering_dict["n_current_requiered_labels"] = len(set(clustering.labels_))
    
    cell_clustering_dict["remaining_labels"] = (
        cell_clustering_dict["n_init_labels"]
        - cell_clustering_dict["n_current_requiered_labels"]
    )
    cell_clustering_dict["cells_per_cluster"] = cells_per_cluster
    cell_clustering_dict["errors_per_cluster"] = errors_per_cluster

    return cell_clustering_dict


def update_n_labels(cell_clustering_recs):
    logging.info("Update n_labels")
    cell_clustering_df = pd.DataFrame(cell_clustering_recs)
    remaining_labels = cell_clustering_df["remaining_labels"].sum()
    cell_clustering_df["n_labels_updated"] = cell_clustering_df[
        "n_current_requiered_labels"
    ]
    if remaining_labels == 0:
        return cell_clustering_df
    elif remaining_labels < 0:
        # The ones with less clusters are more homogeneous and need less labels
        cell_clustering_df.sort_values(
            by=["n_produced_cell_clusters"], ascending=True, inplace=True
        )
        i = 0
        while remaining_labels < 0 and i < len(cell_clustering_df):
            if (
                cell_clustering_df["n_produced_cell_clusters"].iloc[i] > 1
                and cell_clustering_df["n_labels_updated"].iloc[i] > 1
            ):
                cell_clustering_df["n_labels_updated"].iloc[i] -= 1
                remaining_labels += 1
                i = 0
            i += 1

    else:
        cell_clustering_df.sort_values(
            by=["n_produced_cell_clusters"], ascending=False, inplace=True
        )
        i = 0
        while remaining_labels > 0 and i < len(cell_clustering_df):
            if cell_clustering_df["remaining_labels"].iloc[i] > 0:
                if (
                    cell_clustering_df["n_cells"].iloc[i]
                    > cell_clustering_df["n_labels_updated"].iloc[i]
                ):
                    cell_clustering_df["n_labels_updated"].iloc[i] += 1
                    remaining_labels -= 1
                    i = 0
            i += 1        
    logging.info("Update n_labels - remaining_labels: {}".format(remaining_labels))
    return cell_clustering_df


def sort_points_by_distance(feature_vectors):
    centroid = np.mean(feature_vectors, axis=0)
    sorted_indices = sorted(
        range(len(feature_vectors)),
        key=lambda i: euclidean(feature_vectors[i], centroid),
    )
    return sorted_indices


def sampling(cell_clustering_dict, x, y, dirty_cell_values, datacell_uids):
    logging.debug("Sampling")
    samples_dict = {
        "cell_cluster": [],
        "samples": [],
        "n_samples": [],
        "samples_indices_cell_group": [],
        "samples_indices_global": [],
        "labels": [],
        "dirty_cell_values": [],
        "datacell_uids": datacell_uids,
    }

    cells_per_cluster = cell_clustering_dict["cells_per_cluster"].values[0]

    labeled_clusters = {
        key: value
        for key, value in cells_per_cluster.items()
    }
    sorted_clusters = sorted(labeled_clusters, key=lambda k: len(labeled_clusters[k]))
    logging.debug("Sampling - sorted_clusters: {}".format(sorted_clusters))
    cell_cluster_n_labels = {k: 0 for k in cells_per_cluster.keys()}
    values_per_cluster = {k: [] for k in cells_per_cluster.keys()}
    for k in values_per_cluster.keys():
        values_per_cluster[k] = [tuple(x[i]) for i in cells_per_cluster[k]]
    n_labels = cell_clustering_dict["n_labels_updated"].values[0]        
    i = 0
    sorted_cluster_idx = 0
    while n_labels > 0 and i < len(sorted_clusters):
        cluster = sorted_clusters[sorted_cluster_idx]
        # Compare the number of labels with the number of unique feature vectors
        if cell_cluster_n_labels[cluster] < len(set(values_per_cluster[cluster])):
            cell_cluster_n_labels[cluster] += 1
            n_labels -= 1
            i = 0
        else:
            i += 1
        if sorted_cluster_idx < len(sorted_clusters) - 1:
            sorted_cluster_idx += 1
        else:
            sorted_cluster_idx = 0

    for cluster in labeled_clusters:
        x_cluster = []
        y_cluster = []
        samples_feature_vectors = []
        samples_labels = []
        samples_indices_global = []
        samples_indices_cell_group = []
        dirty_cell_values_cluster = []
        col_group_cell_idx = cells_per_cluster[cluster]
        for cell_idx in col_group_cell_idx:
            x_cluster.append(x[cell_idx])
            y_cluster.append(y[cell_idx])

        if cell_cluster_n_labels[cluster] > 1:
            try:
                clustering = MiniBatchKMeans(n_clusters=cell_cluster_n_labels[cluster], batch_size=256 * 64).fit(x_cluster)
                logging.debug("inner cluster splitting - n_clusters: %s", len(set(clustering.labels_)))
                clustering_labels = clustering.labels_
                x_cluster_splited = []
                y_cluster_splited = []
                x_idx_cluster_splited = []
                for i in range(set(clustering_labels)):
                    x_cluster_splited.append([])
                    y_cluster_splited.append([])
                    x_idx_cluster_splited.append([])
                for x, x_idx in x_cluster:
                    x_cluster_splited[clustering_labels[x_idx]].append(x)
                    x_idx_cluster_splited[clustering_labels[x_idx]].append(x_idx)
                    y_cluster_splited[clustering_labels[x_idx]].append(y[x_idx])

                
                for mini_cluster in range(len(x_cluster_splited)):
                    x_cluster_mini = x_cluster_splited[mini_cluster]
                    sorted_points = sort_points_by_distance(x_cluster_mini)
                    sample = sorted_points[0]
                    init_idx = x_idx_cluster_splited[mini_cluster][sample]
                    if x_cluster_mini[sample] not in samples_feature_vectors:
                        samples_feature_vectors.append(x_cluster_mini[sample])
                        samples_labels.append(y_cluster_splited[mini_cluster][sample])
                        dirty_cell_values_cluster.append(
                            dirty_cell_values[col_group_cell_idx[init_idx]]
                        )
                        samples_indices_global.append(col_group_cell_idx[init_idx])
                        samples_indices_cell_group.append(init_idx)
            except Exception as e:
                logging.debug("inner cluster splitting error: %s", e)
                logging.debug("picking random samples")
                while len(samples_feature_vectors) < cell_cluster_n_labels[cluster]:
                    sample = np.random.randint(0, len(x_cluster))
                    if x_cluster[sample] not in samples_feature_vectors:
                        samples_feature_vectors.append(x_cluster[sample])
                        samples_labels.append(y_cluster[sample])
                        dirty_cell_values_cluster.append(
                            dirty_cell_values[col_group_cell_idx[sample]]
                        )
                        samples_indices_global.append(col_group_cell_idx[sample])
                        samples_indices_cell_group.append(sample)

        else:
            sorted_points = sort_points_by_distance(x_cluster)
            i = 0
            sample = sorted_points[i]
            if x_cluster[sample] not in samples_feature_vectors:
                samples_feature_vectors.append(x_cluster[sample])
                samples_labels.append(y_cluster[sample])
                dirty_cell_values_cluster.append(
                    dirty_cell_values[col_group_cell_idx[sample]]
                )
                samples_indices_global.append(col_group_cell_idx[sample])
                samples_indices_cell_group.append(sample)

        samples_dict["cell_cluster"].append(cluster)
        samples_dict["samples"].append(samples_feature_vectors)
        samples_dict["n_samples"].append(len(samples_feature_vectors))
        samples_dict["labels"].append(samples_labels)
        samples_dict["dirty_cell_values"].append(dirty_cell_values_cluster)
        samples_dict["samples_indices_cell_group"].append(samples_indices_cell_group)
        samples_dict["samples_indices_global"].append(samples_indices_global)
   
    logging.debug("Sampling done")
    logging.debug("********cell_cluster: %s", samples_dict["cell_cluster"])
    logging.debug("********n_labels_updated: %s", cell_clustering_dict["n_labels_updated"].values[0])
    logging.debug("********samples: %s", len(samples_dict["samples"]))

    if cell_clustering_dict["n_labels_updated"].values[0] != sum(samples_dict["n_samples"]):
        logging.debug("Sampling - n_labels_updated != sum(samples_dict[n_samples])")
    return samples_dict


def labeling(samples_dict):
    try:
        logging.debug("Labeling")
        samples_dict.update({"final_label_to_be_propagated": []})
        for cell_cluster_idx, _ in enumerate(samples_dict["cell_cluster"]):
            if len(samples_dict["samples"][cell_cluster_idx]) != 0:
                if len(set(samples_dict["labels"][cell_cluster_idx])) == 1:
                    samples_dict["final_label_to_be_propagated"].append(
                        samples_dict["labels"][cell_cluster_idx][0]
                    )
                else:
                    logging.debug("*******Labeling - mode: %s", mode(samples_dict["labels"][cell_cluster_idx]))
                    samples_dict["final_label_to_be_propagated"].append(
                        mode(samples_dict["labels"][cell_cluster_idx])
                    )
            else:
                samples_dict["final_label_to_be_propagated"].append(None)
        logging.debug("Labeling  done")
    except Exception as e:
        logging.error("Labeling error: %s", e)
    return samples_dict
