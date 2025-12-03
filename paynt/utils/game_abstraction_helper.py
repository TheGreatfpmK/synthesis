import molehill
import payntbind

import z3


def run_molehill_for_game_abstraction(quotient):

    quotient.family.hole_to_name = [
            "sketch_hole_" + x for x in quotient.family.hole_to_name
        ]  # feel free to change the prefix, this should just make it easier to creat exists forall queries
    
    choice_to_hole_options = quotient.coloring.getChoiceToAssignment()
    family = quotient.family

    nci = quotient.quotient_mdp.nondeterministic_choice_indices.copy()
    for state in range(quotient.quotient_mdp.nr_states):
        if (
            len(quotient.state_to_actions[state]) > 1
        ):  # again if there's only one action in a state there's no point in adding a hole
            option_labels = [
                quotient.action_labels[i]
                for i in quotient.state_to_actions[state]
            ]
            hole_name = f"A(S{state//2},M{state%2})"
            hole_index = quotient.family.num_holes
            quotient.family.add_hole(hole_name, option_labels)
            for choice in range(nci[state], nci[state + 1]):
                action_hole_index = quotient.state_to_actions[state].index(
                    quotient.choice_to_action[choice]
                )
                choice_to_hole_options[choice].append(
                    (hole_index, action_hole_index)
                )

    quotient.coloring = payntbind.synthesis.Coloring(
        family.family,
        quotient.quotient_mdp.nondeterministic_choice_indices,
        choice_to_hole_options,
    )

    family = quotient.family

    print(family)

    s = z3.Solver()

    exit()