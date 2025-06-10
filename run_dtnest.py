import paynt.quotient
import paynt.quotient.mdp
import paynt.synthesizer
import paynt.synthesizer.synthesizer
import stormpy
import payntbind
import paynt.parser.sketch
import os

model_folder = "models/dts-helpers/qcomp/firewire-3"

# Paths to the required files
model_file_path = os.path.join(model_folder, 'model.prism')
props_file_path = os.path.join(model_folder, 'model.props')
tree_helper_path = os.path.join(model_folder, 'decision_trees/default/scheduler/default.json') # this is now expected as an input but theoretically it can be computed before the main loop starts via dtcontrol

paynt.quotient.mdp.MdpQuotient.add_dont_care_action = True # this is needed to compute the random policy and know the epsilon correctness of the constructed trees

paynt.utils.timer.GlobalTimer.start() # needed for the synthesis to work

# Load the sketch using PAYNT and choose the synthesizer
# if you already have quotient constructed for your model just set the property: 
# quotient.tree_helper = paynt.utils.tree_helper.parse_tree_helper(tree_helper_path)
quotient = paynt.parser.sketch.Sketch.load_sketch(model_file_path, props_file_path, tree_helper_path=tree_helper_path)
synthesizer = paynt.synthesizer.synthesizer.Synthesizer.choose_synthesizer(quotient, 'ar')

synthesizer.run()

# print the tree
print(synthesizer.best_tree.to_string())