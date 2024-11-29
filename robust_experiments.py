import os
import subprocess
import time
import sys

# Define the list here
# models = ["bridge-5-3-1", "bridge-11-5-4", "mastermind-2-3-3", "mastermind-2-3-4", "pacman-6", "rocks-4-1", "rocks-4-1-prob", "rocks-4-2", "rocks-4-2-prob", "rocks-8-1", "rocks-8-1-prob"]
# models = ["avoid-8-2", "avoid-8-2-easy", "dodge-8-mod2-pull-30", "dodge-8-mod3-pull-30", "dpm-switch-q10", "dpm-switch-q10-big", "obstacles-8-6-skip", "obstacles-10-6-skip-easy", "obstacles-10-9-pull", "obstacles-demo", "rocks-6-4", "rover-100-big", "rover-1000", "uav-operator-roz-workload", "uav-roz", "virus"]
# models = ["bridge-21-7-9", "mastermind-3-4-4", "mastermind-3-4-10"]

models = ["avoid-8-2", "avoid-8-2-easy", "dpm-switch-q10", "dpm-switch-q10-big", "obstacles-10-6-skip-easy", "obstacles-demo", "rocks-6-4", "rover-100-big", "rover-1000", "uav-operator-roz-workload", "uav-roz"]
# models = ["bridge-11-5-4", "bridge-21-7-9", "catch-5" "mastermind-2-3-4", "pacman-6", "rocks-4-1", "rocks-4-1-prob", "rocks-4-2", "rocks-4-2-prob", "rocks-8-1", "rocks-8-1-prob"]

experiment_name = ""
if len(sys.argv) > 1:
    experiment_name = sys.argv[1]

# Create the folder with the current timestamp
timestamp = time.strftime("%Y%m%d")
output_folder = f"experiments/experiment_{timestamp}_{experiment_name}"
os.makedirs(output_folder, exist_ok=True)

# Iterate over the elements and call the script
for element in models:
    log_file_path = os.path.join(output_folder, f"{element}.log")
    if os.path.exists(log_file_path):
        print(f"Skipped {element} because log file already exists.")
        continue
    result = subprocess.run(["python3", "robust_policy.py", element], capture_output=True, text=True)
    with open(log_file_path, "w") as log_file:
        log_file.write(result.stdout)
    if result.stderr:
        print(f"Error in {element}: {result.stderr}")
    print(f"Finished {element}")