import os
import subprocess
import signal
import sys

dir_path = os.path.dirname(os.path.realpath(__file__))

# If you feel like your PC is struggling to achieve correct values in the given timeout
# because of performance issues try incresing this multiplier
# default = 1, if you set it to 2 all timeout settings will be multiplied by 2
timeout_multiplier = 1

# If true overwrite existing logs, if false only run experiments for missing log files
overwrite_logs = False

# If true FSCs will be exported alongside the log files
export_fsc = False

# SETTINGS FOR EXPERIMENTS
# use_storm = False                   # False if you want just PAYNT result
# iterative_storm = False   # False if you dont want iterative loop, otherwise (timeout, paynt_timeout, storm_timeout)
# get_storm_result = 0            # Put integer to represent number of seconds to just get storm result, False to turn off
# storm_options = "2mil"               # False to use default, otherwise one of [cutoff,clip2,clip4...]
# prune_storm = True                 # Family pruning based on storm, default False
# unfold_strategy = "cutoff"            # False to use default, otherwise one of [paynt,storm,cutoff]
# use_storm_cutoff = True            # Use Storm cutoff schedulers to prioritize family exploration, default False
# aposteriori_unfolding = False       # Enables new unfolding

# Parsing options to options string
# example options string: "--storm-pomdp --iterative-storm 600 12 12"
# if use_storm:
#     options_string = "--storm-pomdp"
#     if iterative_storm:
#         options_string += " --iterative-storm {} {} {}".format(iterative_storm[0], iterative_storm[1], iterative_storm[2])
#     if get_storm_result:
#         options_string += " --get-storm-result {}".format(get_storm_result)
#     if storm_options:
#         options_string += " --storm-options {}".format(storm_options)
#     if prune_storm:
#         options_string += " --prune-storm"
#     if unfold_strategy:
#         options_string += " --unfold-strategy-storm {}".format(unfold_strategy)
#     if use_storm_cutoff:
#         options_string += " --use-storm-cutoffs"
#     if aposteriori_unfolding:
#         options_string += " --posterior-aware"
# else:
#     options_string = ""

# CHANGE THIS TO CHANGE WHAT MODELS SHOULD BE USED
directory = os.fsencode(dir_path + '/../models/archive/cav23-saynt')
models = [ f.path for f in os.scandir(directory) if f.is_dir() ]

def run_experiment(options, logs_string, experiment_models, timeout, fld="", special={}):
    
    logs_dir = os.fsencode(dir_path + "/{}/".format(logs_string))

    print(f'\nRunning experiment {logs_string}. The logs will be saved in folder {logs_dir.decode("utf-8")}')
    print(f'The options used: "{options}"\n')

    real_timeout = int(timeout*timeout_multiplier)

    for model in experiment_models:

        model_name = model[:-6]
        model_name = model_name.replace(".", "-")

        if model in special.keys():
            model_options = special[model]
        else:
            model_options = options

        # THE REST OF THE MODELS
        # command = "python3 paynt.py --project {} --fsc-synthesis {}".format(project_name, model_options)
        command = "python3 paynt.py --project ../sarsop/models/{} --sketch {} --fsc-synthesis {}".format(fld, model, model_options)


        if not overwrite_logs:
            if os.path.isfile(logs_dir.decode("utf-8") + model_name + "/" + "logs.txt"):
                print(model_name, "LOG EXISTS")
                continue

        process = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            # TIMEOUT HERE TO TERMINATE EXPERIMENT
            # timeout should be higher than the expected running time of a given experiment
            output, error = process.communicate(timeout=real_timeout)
            output, error = process.communicate()
            process.wait()
        except subprocess.TimeoutExpired:
            process.send_signal(signal.SIGKILL)
            output, error = process.communicate()
            process.wait()

        if os.path.isfile(logs_dir.decode("utf-8") + model_name + "/" + "logs.txt"):
            print(model_name, "OVERWRITEN LOG")
            os.remove(logs_dir.decode("utf-8") + model_name + "/" + "logs.txt")
        else:
            print(model_name)

        if os.path.isfile(logs_dir.decode("utf-8") + model_name + "/" + "stderr.txt"):    
            os.remove(logs_dir.decode("utf-8") + model_name + "/" + "stderr.txt")

        os.makedirs(os.path.dirname(logs_dir.decode("utf-8") + model_name + "/" + "logs.txt"), exist_ok=True)
        with open(logs_dir.decode("utf-8") + model_name + "/" + "logs.txt", "w") as text_file:
            text_file.write(output.decode("utf-8"))

        # TODO remove after
        if error:
            with open(logs_dir.decode("utf-8") + model_name + "/" + "stderr.txt", "w") as text_file:
                text_file.write(error.decode("utf-8"))

    print(f'\nExperiment {logs_string} completed. The logs are saved in folder {logs_dir.decode("utf-8")}')

if __name__ == '__main__':
    experiment = sys.argv[1]
    overwrite = sys.argv[2]
    overwrite_logs = overwrite == "True"
    export_fsc = len(sys.argv) > 3

    if experiment == 'default':
        # experiment_models = ["milos-aaai97.pomdp", "network.pomdp", "query.s3.pomdp", "query.s4.pomdp", "learning.c3.pomdp", "learning.c4.pomdp", "4x5x2.95.pomdp", "hanks.95.pomdp"]
        # experiment_models = ["milos-aaai97.pomdp", "network.pomdp", "query.s3.pomdp", "learning.c3.pomdp", "4x5x2.95.pomdp", "hanks.95.pomdp", "cheng.D3-1.pomdp", "cheng.D4-1.pomdp", "ejs1.pomdp"]
        # experiment_models = ["drone-4-1-95.pomdp", "drone-4-1-99.pomdp", "refuel-20-80.pomdp", "refuel-20-95.pomdp", "refuel-20-99.pomdp", "network-2-8-20-80.pomdp", "network-2-8-20-95.pomdp", "network-2-8-20-99.pomdp", "rocks-12-80.pomdp", "rocks-12-95.pomdp", "rocks-12-99.pomdp", "rocks-16-80.pomdp", "rocks-16-95.pomdp"]
        experiment_models = ["4x5x2.95.pomdp", "milos-aaai97.pomdp", "cheng.D3-1.pomdp", "network.pomdp"]

        options = "--storm-pomdp --iterative-storm 900 90 2 --enhanced-saynt 0"
        logs_string = "cassandra-def-saynt-900-90-2-enhanced"
        timeout = 1200
        run_experiment(options, logs_string, experiment_models, timeout, fld="")

        options = "--storm-pomdp --iterative-storm 900 90 2 --enhanced-saynt 0"
        logs_string = "cassandra-08-saynt-900-90-2-enhanced"
        timeout = 1200
        run_experiment(options, logs_string, experiment_models, timeout, fld="08")

        options = "--storm-pomdp --iterative-storm 900 90 2 --enhanced-saynt 0"
        logs_string = "cassandra-0999-saynt-900-90-2-enhanced"
        timeout = 1200
        run_experiment(options, logs_string, experiment_models, timeout, fld="0999")

        options = "--storm-pomdp --iterative-storm 900 90 2 --enhanced-saynt 0"
        logs_string = "cassandra-09999-saynt-900-90-2-enhanced"
        timeout = 1200
        run_experiment(options, logs_string, experiment_models, timeout, fld="09999")

        # options = "--native-discount"
        # logs_string = "cassandra-def-paynt-native"
        # timeout = 1200
        # run_experiment(options, logs_string, experiment_models, timeout, fld="")

        # options = "--storm-pomdp --get-storm-result 0 --storm-options 2mil --native-discount"
        # logs_string = "cassandra-def-storm-2mil-native"
        # timeout = 1200
        # run_experiment(options, logs_string, experiment_models, timeout, fld="")

        print("\n EXPERIMENT COMPLETE\n")

    elif experiment == 'storm':
        experiment_models = ["aloha.10.pomdp", "hallway.pomdp", "iff.pomdp", "milos-aaai97.pomdp", "network.pomdp", "query.s3.pomdp", "query.s4.pomdp", "tiger-grid.pomdp", "learning.c3.pomdp", "learning.c4.pomdp", "mit.pomdp", "pentagon.pomdp"]

        options = "--storm-pomdp --get-storm-result 0 --storm-options 5mil"
        logs_string = "cassandra-storm-5mil"
        timeout = 1200
        run_experiment(options, logs_string, experiment_models, timeout)

        print("\n EXPERIMENT COMPLETE\n")

    elif experiment == 'milos':
        experiment_models = ["milos-aaai97.pomdp"]

        options = "--storm-pomdp --get-storm-result 0 --storm-options 5mil"
        logs_string = "cassandra-storm-5mil"
        timeout = 1200
        run_experiment(options, logs_string, experiment_models, timeout)

        print("\n EXPERIMENT COMPLETE\n")

    elif experiment == 'posterior':
        experiment_models = ["drone-4-2", "network", "4x3-95"]

        options = "--storm-pomdp --iterative-storm 900 90 2 --enhanced-saynt 0 --saynt-overapprox --posterior-aware"
        logs_string = "uniform-overapp-default-90-2-posterior"
        timeout = 1200
        run_experiment(options, logs_string, experiment_models, timeout)

        print("\n EXPERIMENT COMPLETE\n")

    else:
        print("Unknown experiment")