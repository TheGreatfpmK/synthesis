import os
import subprocess

dir_path = os.path.dirname(os.path.realpath(__file__))

directory = os.fsencode(dir_path + '/models')
logs_dir = os.fsencode(dir_path + '/base-benchmark/')
models = [ f.path for f in os.scandir(directory) if f.is_dir() ]

for model in models:
    model_name = os.path.basename(model).decode("utf-8")
    project_name = model.decode("utf-8")
    command = "python3 paynt/paynt.py --project {} --properties sketch.props ar --fsc-synthesis".format(project_name)

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