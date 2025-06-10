import stormpy
import os
import json
import payntbind

import paynt.parser.sketch


# base_dirs = ['/home/fpmk/synthesis/models/dts/qcomp', '/home/fpmk/synthesis/models/dts/omdt', '/home/fpmk/synthesis/models/dts/maze']
base_dirs = ['/home/fpmk/synthesis-playground/models/dts-uai/discounted']
# base_dirs = ['/home/fpmk/synthesis/models/dts/qcomp']

# Iterate over all folders in base_dir
for base_dir in base_dirs:
    for folder in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder)
        if os.path.isdir(folder_path):
            
            # Paths to the required files
            possible_file_names = ['model.prism', 'model.drn', 'model.jani', 'model-random.drn']
            for file_name in possible_file_names:
                model_file_path = os.path.join(folder_path, file_name)
                if os.path.exists(model_file_path):
                    break
            # drn_file_path = os.path.join(folder_path, 'model-random-enabled.drn') # TODO this changes based on the base_dir
            # props_file_path = os.path.join(folder_path, 'model.props')
            props_file_path = os.path.join(folder_path, 'discounted.props')
            state_valuations_file_path = os.path.join(folder_path, 'state-valuations.json')
            scheduler_file = os.path.join(folder_path, 'scheduler.storm.json')

            if os.path.exists(scheduler_file):
                continue

            print("loading sketch")
            # Load the sketch using PAYNT
            quotient = paynt.parser.sketch.Sketch.load_sketch(model_file_path, props_file_path)
            print("quotient created")

            quotient_mdp = quotient.quotient_mdp
            
            print("model checking")
            # Perform model checking using stormpy
            result = stormpy.model_checking(quotient_mdp, quotient.specification.optimality.formula, extract_scheduler=True)
            print("model check complete")

            selected_choices = stormpy.BitVector(quotient_mdp.nr_choices, False)

            state_to_choice = payntbind.synthesis.schedulerToStateToGlobalChoice(result.scheduler, quotient_mdp, list(range(quotient_mdp.nr_choices)))

            nci = quotient_mdp.nondeterministic_choice_indices.copy()
            for state in range(quotient_mdp.nr_states):
                # print(result.scheduler.get_choice(state).get_deterministic_choice().__int__())
                selected_choices.set(state_to_choice[state], True)

            subsystem_builder_options = stormpy.SubsystemBuilderOptions()
            subsystem_builder_options.build_state_mapping = True
            subsystem_builder_options.build_action_mapping = True

            print("building submodel")
            all_states = stormpy.BitVector(quotient_mdp.nr_states, True)
            submodel_construction = stormpy.construct_submodel(
                quotient_mdp, all_states, selected_choices, False, subsystem_builder_options
            )

            submodel = submodel_construction.model
            state_map = submodel_construction.new_to_old_state_mapping.copy()
            choice_map = submodel_construction.new_to_old_action_mapping.copy()

            print("computing reachable choices")
            reachable_choices = stormpy.BitVector(quotient_mdp.nr_choices, False)
            for choice in range(submodel.nr_choices):
                reachable_choices.set(choice_map[choice], True)

            nci = quotient_mdp.nondeterministic_choice_indices.copy()
            # remove discount sink choice
            labeling = quotient_mdp.labeling
            if labeling.contains_label("discount_sink"):
                for state in range(quotient_mdp.nr_states):
                    if labeling.has_state_label("discount_sink", state):
                        state_row = nci[state]
                        next_state_row = nci[state+1]
                        for choice in range(state_row, next_state_row):
                            reachable_choices.set(choice, False)

            # remove irrelevant state choices
            for state in range(quotient_mdp.nr_states):
                if not quotient.state_is_relevant_bv.get(state):
                    state_row = nci[state]
                    next_state_row = nci[state+1]
                    for choice in range(state_row, next_state_row):
                        reachable_choices.set(choice, False)

            print("clearing scheduler")
            json_scheduler_full = json.loads(result.scheduler.to_json_str(quotient_mdp))
            json_final = []
            for entry in json_scheduler_full:
                json_choice = entry["c"]
                assert len(json_choice) == 1
                selected_choice = int(json_choice[0]["index"])
                if not reachable_choices.get(selected_choice):
                    continue
                if len(entry["c"][0]["labels"]) == 0:
                    continue
                json_final.append(entry)
            json_str = json.dumps(json_final, indent=4)

            print(submodel.nr_states)

            f = open(scheduler_file, 'w')
            f.write(json_str)
            f.close()