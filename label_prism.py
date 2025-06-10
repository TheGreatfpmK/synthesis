import stormpy
import os

work_dir = "models/dts-integration/qcomp/pacman"

orig_file = os.path.join(work_dir, 'model.prism')

# Parse the PRISM file
prism_program = stormpy.parse_prism_program(orig_file)

# Label unlabeled commands
updated_program = prism_program.label_unlabelled_commands({})

# Write the original content to sketch-old.templ
with open(orig_file, 'r') as file:
    original_content = file.read()
with open(os.path.join(work_dir, "model-unlabelled.prism"), 'w') as file:
    file.write(original_content)

# Write the updated program to sketch.templ
with open(orig_file, 'w') as file:
    file.write(updated_program.__str__())

