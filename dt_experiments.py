

import os

import paynt
import stormpy

import paynt.parser.sketch

import subprocess

import tqdm

import click


MODELS_FOLDER = "models/predicates/eval/"
RESULTS_FOLDER = "results/predicates-stuff-logs/"


# models = ['consensus-4-2', 'frozenlake_12x12', 'ij-14-single', 'maze-7', 'system_administrator_2', 'tictactoe_vs_random', 'wlan-1-2']
models = ['consensus-4-2', 'frozenlake_8x8', 'frozenlake_12x12', 'maze-7', 'maze-steps', 'system_administrator_1', 'system_administrator_2', 'wlan-1-2', 'orchard-simple', 'orchard-classic', 'pacman', 'stairs-16', 'stairs-64']

@click.command()
@click.option("--relative-eps", type=float, default=None, show_default=True, help="relative epsilon threhshold computed from random policy")
@click.option("--results-folder", type=str, default=RESULTS_FOLDER, show_default=True, help="folder to store results")
@click.option("--sampling-steps", type=int, default=1000, show_default=True, help="number of sampling steps for dtnest")
def main(relative_eps, results_folder, sampling_steps):

    if not os.path.exists(results_folder):
        os.makedirs(results_folder)


    for model in tqdm.tqdm(models):

        model_folder = MODELS_FOLDER + model + "/"
        model_path = model_folder + "sketch.templ"
        prop_path = model_folder + "sketch.props"


        if not os.path.exists(results_folder + model + "-all.log"):
            print(f"Running {model} with all predicates")
            process = subprocess.Popen(["python3", "dt_stuff.py", model_folder, "--run-dtnest", "--relative-eps", str(relative_eps), "--steps", str(sampling_steps)], stdout=subprocess.PIPE, stderr=None)

            lines = process.stdout.readlines()

            with open(results_folder + model + "-all.log", "w") as f:
                for line in lines:
                    f.write(line.decode("utf-8"))
        else:
            print(f"Skipping {model} with all predicates because log file already exists")

        if not os.path.exists(results_folder + model + "-default.log"):
            print(f"Running {model} with default predicates")
            process = subprocess.Popen(["python3", "dt_stuff.py", model_folder, "--run-dtnest", "--default-predicates", "--relative-eps", str(relative_eps), "--steps", str(sampling_steps)], stdout=subprocess.PIPE, stderr=None)

            lines = process.stdout.readlines()

            with open(results_folder + model + "-default.log", "w") as f:
                for line in lines:
                    f.write(line.decode("utf-8"))
        else:
            print(f"Skipping {model} with default predicates because log file already exists")



if __name__ == "__main__":
    main()
