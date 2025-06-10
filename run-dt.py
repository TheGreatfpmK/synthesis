import os
import sys
import subprocess
from datetime import datetime

# Define directories
dir1 = '/home/fpmk/synthesis-playground/models/dts-helpers/omdt/'
dir2 = '/home/fpmk/synthesis-playground/models/dts-helpers/qcomp/'
dir3 = '/home/fpmk/synthesis-playground/models/dts-helpers/maze/'

# Get the first program argument or default to "experiment"
experiment_name = sys.argv[1] if len(sys.argv) > 1 else "experiment"

# Create the experiments directory and timestamped subdirectory
timestamp = datetime.now().strftime("%d%m%y")
experiment_dir = f"experiments/{timestamp}-{experiment_name}"
os.makedirs(experiment_dir, exist_ok=True)

# Function to run command in each folder of a directory
def run_command_in_folders(directory, command_template):
    for folder in os.listdir(directory):
        folder_path = os.path.join(directory, folder)
        if os.path.isdir(folder_path):
            command = command_template.replace('x', folder)
            stdout_file = os.path.join(experiment_dir, f"{folder}_stdout.txt")
            stderr_file = os.path.join(experiment_dir, f"{folder}_stderr.txt")
            
            # Skip if output file already exists
            if os.path.exists(stdout_file):
                print(f"Skipping {folder} as output file already exists.")
                continue
            
            with open(stdout_file, 'w') as out:
                process = subprocess.Popen(command, shell=True, stdout=out, stderr=subprocess.PIPE)
                _, stderr = process.communicate()
                
                # Only create stderr file if there is an error
                if stderr:
                    with open(stderr_file, 'w') as err:
                        print(f"Error running {folder}")
                        err.write(stderr.decode())
            
            print(f"Finished running {folder}")

# Commands for each directory
command1 = "python3 paynt.py models/dts-helpers/omdt/x --sketch model.drn --props discounted.props"
command2 = "python3 paynt.py models/dts-helpers/qcomp/x --sketch model.prism --props model.props --tree-depth 1"
command3 = "python3 paynt.py models/dts-helpers/maze/x --sketch model.prism --props discounted.props"

# Run commands in each directory
# run_command_in_folders(dir1, command1)
# run_command_in_folders(dir2, command2)
run_command_in_folders(dir3, command3)