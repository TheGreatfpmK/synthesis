import os
import subprocess

dir_path = os.path.dirname(os.path.realpath(__file__))

directory = os.fsencode(dir_path + '/models')
models = [ f.path for f in os.scandir(directory) if f.is_dir() ]
os.system('rm -f {}/results/*'.format(dir_path))

for model in models:
    model_name = os.path.basename(model).decode("utf-8")
    sketch_file = model.decode("utf-8") + "/sketch.templ"
    props_file = model.decode("utf-8") + "/sketch.props"
    command = "./storm/build/bin/storm-pomdp --prism {} --prop {} --belief-exploration unfold --refine 0 --timeout 60 --gap-threshold 0 --size-threshold 0 2 --signal-timeout 600 --debug".format(sketch_file, props_file)

    process = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, error = process.communicate()
    process.wait()

    os.system('cp {}/../test.txt {}/results/{}.txt'.format(dir_path, dir_path, model_name))
    print(model_name)
    #print(command)
    if error and error != b'ERROR: The program received signal 14 and will be aborted in 600s.\n':
        print(error)