import stormpy
import payntbind
import paynt.parser.sketch
import os


model_folder = "models/dts-helpers/qcomp/wlan-1-2"

# Paths to the required files
model_file_path = os.path.join(model_folder, 'model.prism')
props_file_path = os.path.join(model_folder, 'model.props')
tree_helper_path = os.path.join(model_folder, 'decision_trees/default/scheduler/default.json')

# Load the sketch using PAYNT
quotient = paynt.parser.sketch.Sketch.load_sketch(model_file_path, props_file_path, tree_helper_path=tree_helper_path)

decision_tree = quotient.build_tree_helper_tree()
quotient.tree_helper_tree = decision_tree

print(decision_tree)

# To use the current implementation of to_scheduler_json() you need to know the reachable states, because I already filter out the unreachable states
# and have asserts there to know everything is correct. So you can change the implementation to not filter the unreachable states or
# this way you can get the submdp induced by the tree and compute the reachable states from that
submpd = quotient.get_submdp_from_unfixed_states()
reachable_states = stormpy.BitVector(quotient.quotient_mdp.nr_states, False)
for state in range(submpd.model.nr_states):
    reachable_states.set(submpd.quotient_state_map[state], True)

print(decision_tree.to_scheduler_json(reachable_states))