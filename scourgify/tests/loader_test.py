import pandas as pd

from scourgify.load_module.load_data_cells import load_data_cells

results_path = "./test_mediate_files"
sand_box_dir = "./test_sand_box"
dirty_file_name = "dirty_clean.csv"

master_psap_df = pd.read_csv("./test_sand_box/911_Master_PSAP_Registry/dirty_clean.csv")
alcohol_use_df = pd.read_csv("./test_sand_box/Alcohol-use.g8_2014_0731_0900/dirty_clean.csv")

lake_num_cells = master_psap_df.size + alcohol_use_df.size

cells_lake_dict = load_data_cells(sand_box_dir, dirty_file_name, save_results=True, results_path=results_path)
assert len(cells_lake_dict) == lake_num_cells
print("size cells dict-test passed!")

assert cells_lake_dict[hash((0, 1, 2))] == (0, 1, 2, "Miami County E9-1-1")
print("cells dict-test, master_psap_df passed!")

assert cells_lake_dict[hash((1, 3, 311))] == (1, 3, 311, "2013")
print("cells dict-test, alcohol_use_df passed!")
