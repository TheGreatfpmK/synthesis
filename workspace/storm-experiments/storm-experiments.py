import os
import subprocess

dir_path = os.path.dirname(os.path.realpath(__file__))

directory = os.fsencode(dir_path + '/models')
#result_dir = os.fsencode(dir_path + '/results/')                   # MAIN EXPERIMENT
result_dir = os.fsencode(dir_path + '/results-cutoff/')            # CUT-OFFs
#result_dir = os.fsencode(dir_path + '/results-overapp/')           # OVER-APPROXIMATION
#result_dir = os.fsencode(dir_path + '/results-clip-noreach/')       # MAIN EXPERIMENT NO REACHABILITY
#result_dir = os.fsencode(dir_path + '/results-cutoff-noreach/')    # CUT-OFFs NO REACHABILITY
#result_dir = os.fsencode(dir_path + '/results-overapp-noreach/')   # OVER-APPROXIMATION NO REACHABILITY
logs_dir = os.fsencode(dir_path + '/paynt-logs/')
models = [ f.path for f in os.scandir(directory) if f.is_dir() ]

os.system('rm -rf {}/paynt-logs/*/stderr*'.format(dir_path))

for model in models:
    model_name = os.path.basename(model).decode("utf-8")
    #if model_name in ["crypt-4", "maze", "maze-alex", "nrp-8"]:
    #    continue
    project_name = model.decode("utf-8")
    storm_file = result_dir.decode("utf-8") + model_name + ".txt"
    command = "python3 paynt/paynt.py --project {} --properties sketch.props ar --fsc-synthesis --storm-result-file {}".format(project_name, storm_file)

    process = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        output, error = process.communicate(timeout=300)
        process.wait()
    except subprocess.TimeoutExpired:
        process.kill()
        output, error = process.communicate()
        process.wait()

    os.makedirs(os.path.dirname(logs_dir.decode("utf-8") + model_name + "/" + "logs.txt"), exist_ok=True)
    with open(logs_dir.decode("utf-8") + model_name + "/" + "logs.txt", "w") as text_file:
        text_file.write(output.decode("utf-8"))


    print(model_name)
    if error:
        print("Error")
        with open(logs_dir.decode("utf-8") + model_name + "/" + "stderr.txt", "w") as text_file:
            text_file.write(error.decode("utf-8"))