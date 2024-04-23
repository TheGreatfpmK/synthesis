import os
import subprocess
import signal

dir_path = os.path.dirname(os.path.realpath(__file__))

# CHANGE THIS TO CHANGE WHAT MODELS SHOULD BE USED
directory = os.fsencode(dir_path + '/../models/tac24/case-studies')
models = [ f.path for f in os.scandir(directory) if f.is_dir() ]
# models = [ f"{directory}/avoid/8-2/", f"{directory}/avoid/8-4/", f"{directory}/avoid/16-1/", f"{directory}/avoid/16-2/", f"{directory}/avoid/16-2-easy/", f"{directory}/obstacles/8-6-skip/", f"{directory}/obstacles/8-6-skip-easy/", f"{directory}/obstacles/10-6-skip/", f"{directory}/obstacles/10-6-skip-easy/", f"{directory}/dodge/8-mod2-pull-30/", f"{directory}/dodge/8-mod2-stagger-30/", f"{directory}/dodge/12-mod2-stagger-30/", f"{directory}/dodge/8-mod3-pull-30/", f"{directory}/uav/int-holes/operator/", f"{directory}/uav/int-holes/roz/", f"{directory}/uav/int-holes/operator-roz/", f"{directory}/rocks/6-3/", f"{directory}/rocks/6-4/", f"{directory}/rocks/16-1/", f"{directory}/dpm/int-holes/switch/", f"{directory}/dpm/int-holes/switch-big-q10-old/", f"{directory}/dpm/int-holes/switch-big-q10/", f"{directory}/rover/int-holes/100/", f"{directory}/rover/int-holes/1000-constant-success/", f"{directory}/virus/virus-int-holes/"]
# models = [ f"{directory}/avoid/16-1/", f"{directory}/avoid/5-2/", f"{directory}/avoid/6-2/", f"{directory}/avoid/8-2/", f"{directory}/avoid/8-4/", f"{directory}/avoid/16-2/", f"{directory}/avoid/16-2-easy/", f"{directory}/obstacles/16-1-pull/", f"{directory}/obstacles/6-4-pull/", f"{directory}/obstacles/6-4-skip/", f"{directory}/obstacles/6-4-pull-overlap/", f"{directory}/dodge/8-mod2-pull-30/", f"{directory}/dodge/8-mod2-stagger-30/", f"{directory}/dodge/12-mod2-stagger-30/", f"{directory}/uav/int-holes/operator-big/", f"{directory}/uav/int-holes/roz-big/", f"{directory}/uav/int-holes/operator-roz-big/", f"{directory}/rocks/32-2/", f"{directory}/dpm/int-holes/switch-q10-old/", f"{directory}/rover/int-holes/100-big/", f"{directory}/rover/int-holes/1000/", f"{directory}/rover/int-holes/1000-constant-success/"]

# models = [ f"{directory}/avoid/8-2/", f"{directory}/avoid/8-2-easy/", f"{directory}/avoid/8-4/", f"{directory}/avoid/16-2/", f"{directory}/avoid/16-2-easy/", f"{directory}/obstacles/8-6-skip/", f"{directory}/obstacles/8-6-skip-easy/", f"{directory}/obstacles/10-6-skip/", f"{directory}/obstacles/10-6-skip-easy/", f"{directory}/dodge/8-mod2-pull-30/", f"{directory}/dodge/8-mod3-pull-30/", f"{directory}/dodge/8-mod2-stagger-30/", f"{directory}/dodge/12-mod2-stagger-30/", f"{directory}/uav/int-holes/operator-big/", f"{directory}/uav/int-holes/roz-big/", f"{directory}/uav/int-holes/operator-roz-big/", f"{directory}/uav/int-holes/operator/", f"{directory}/uav/int-holes/roz/", f"{directory}/uav/int-holes/operator-roz/", f"{directory}/rocks/32-2/", f"{directory}/dpm/int-holes/switch/", f"{directory}/dpm/int-holes/switch-big-q10-old/", f"{directory}/dpm/int-holes/switch-big-q10/", f"{directory}/dpm/int-holes/switch-q10-old/", f"{directory}/rover/int-holes/100/", f"{directory}/rover/int-holes/100-big/", f"{directory}/rover/int-holes/1000/", f"{directory}/rover/int-holes/1000-constant-success/", f"{directory}/virus/virus-int-holes/"]

# models = [ f"{directory}/uav/int-holes/roz/", f"{directory}/uav/int-holes/operator-roz-workload/", f"{directory}/dpm/switch-big-q10-old/", f"{directory}/dpm/switch-q10-old/", f"{directory}/rover/100/", f"{directory}/rover/1000-constant-success/", f"{directory}/virus/virus/"]

# models = [ f"{directory}/uav/int-holes/roz/"]

# ADD ANOTHER OPTIONS STRING EXPLICITLY HERE IF YOU WANT TO RUN MULTIPLE EXPERIMENTS IN ONE GO
options = [("", 900)]
# options = [("--method onebyone", 300)]

for option in options:

    option_timeout = option[1]
    option = option[0]

    option_split = [o.strip() for o in option.split("--")][1:]
    logs_string = "tac24-case-studies"
    for o in option_split:
        o = o.split(" ")
        for add in o:
            logs_string += "-" + add
            
    print(option)

    logs_dir = os.fsencode(dir_path + "/{}/".format(logs_string))

    for model in models:
        model_name = os.path.basename(model).decode("utf-8")
        project_name = model.decode("utf-8")

        command = "python3 paynt.py --project {} {}".format(project_name, option)

        # SELECT MODELS
        if model_name in ["case-studies", "grid-meet", "maze-multi"]:
            print(f'{model_name} not selected')
            continue

        # skip if log exists
        if os.path.isfile(logs_dir.decode("utf-8") + model_name + "/" + "logs.txt"):
            print(f'{model_name} skipped')
            continue

        process = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            # TIMEOUT HERE TO TERMINATE EXPERIMENT
            output, error = process.communicate(timeout=option_timeout)
            output, error = process.communicate()
            process.wait()
        except subprocess.TimeoutExpired:
            process.send_signal(signal.SIGKILL)
            output, error = process.communicate()
            process.wait()

        if os.path.isfile(logs_dir.decode("utf-8") + model_name + "/" + "logs.txt"):
            os.remove(logs_dir.decode("utf-8") + model_name + "/" + "logs.txt")

        if os.path.isfile(logs_dir.decode("utf-8") + model_name + "/" + "stderr.txt"):    
            os.remove(logs_dir.decode("utf-8") + model_name + "/" + "stderr.txt")

        os.makedirs(os.path.dirname(logs_dir.decode("utf-8") + model_name + "/" + "logs.txt"), exist_ok=True)
        with open(logs_dir.decode("utf-8") + model_name + "/" + "logs.txt", "w") as text_file:
            text_file.write(output.decode("utf-8"))

        print(model_name)
        if error:
            with open(logs_dir.decode("utf-8") + model_name + "/" + "stderr.txt", "w") as text_file:
                text_file.write(error.decode("utf-8"))
