import os
import sys
import paynt.parser.sketch
import paynt.models.model_builder
from paynt.parser.prism_parser import PrismParser
import stormpy
import json
import payntbind

def process_folders(base_path):
    for folder_name in os.listdir(base_path):
        if folder_name != '3d_navigation':
            continue
        folder_path = os.path.join(base_path, folder_name)
        file = os.path.join(folder_path, 'model-random.drn')
        props_file = os.path.join(folder_path, 'discounted.props')
        if os.path.isdir(folder_path):
            print(f"Processing folder: {folder_path}")
            mdp = paynt.models.model_builder.ModelBuilder.from_drn(file)
            specification = PrismParser.parse_specification(props_file, 0)

            valuations_path = folder_path + "/state_valuations.json"
            state_valuations = None
            if os.path.exists(valuations_path) and os.path.isfile(valuations_path):
                with open(valuations_path) as file:
                    state_valuations = json.load(file)
            if state_valuations is not None:
                mdp = payntbind.synthesis.addStateValuations(mdp,state_valuations)

            result = stormpy.model_checking(mdp, specification.optimality.formula, extract_scheduler=True)

            scheduler_file = folder_path + "/scheduler.storm.json"

            with open(scheduler_file, "w") as file:
                file.write(result.scheduler.to_json_str(mdp))

            with open(scheduler_file, 'r') as json_file:
                scheduler = json.load(json_file)

            for item in scheduler:
                if 'c' in item and item['c']:
                    action_label = item['c'][0]['labels'][0]
                    item['c'][0]['origin'] = {'action-label': action_label}

            with open(scheduler_file, 'w') as json_file:
                json.dump(scheduler, json_file, indent=4)

if __name__ == "__main__":
    base_path = 'models/omdt-mdp'
    process_folders(base_path)