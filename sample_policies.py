import click
import os

import paynt.parser.sketch

import stormpy
import random
import numpy as np
import time
import json


def get_mdp_features_list(dt_colored_mdp_factory, model_info):
    return dt_colored_mdp_factory.relevant_state_valuations


def sample_to_list(sample, dt_colored_mdp_factory, model_info):
    bitvector, unreachable_states = sample
    state_to_choice = bitvector_to_state_to_choice(bitvector, model_info)
    result_list = []
    for state, choice in enumerate(state_to_choice):
        if unreachable_states[state]:
            result_list.append(-1)
        else:
            result_list.append(dt_colored_mdp_factory.choice_to_action[choice])
    
    return result_list


def get_optimality_specification(specification):
    specification.constraints[0].threshold = 0
    specification.constraints[0].property.raw_formula.set_bound(specification.constraints[0].formula.comparison_type, stormpy.ExpressionManager().create_rational(stormpy.Rational(0)))
    opt_property = stormpy.Property("", specification.constraints[0].formula.clone())

    paynt_opt_property = paynt.verification.property.construct_property(opt_property, 0, False)
    properties = [paynt_opt_property]

    return paynt.verification.property.Specification(properties)


def get_scheduler(model, prop):
    formula = prop.formula
    res = stormpy.model_checking(model, formula, extract_scheduler=True)
    return res.scheduler


def get_bitvector_from_scheduler(scheduler, model_info):
    res_bitvector = stormpy.storage.BitVector(model_info["nr_choices"])
    for state in range(model_info["nr_states"]):
        choice_index = scheduler.get_choice(state).get_deterministic_choice()
        res_bitvector.set(model_info["nondeterministic_choice_indices"][state] + choice_index)

    return res_bitvector

def bitvector_to_state_to_choice(bitvector, model_info):
    state_to_choice = [None] * model_info["nr_states"]
    for state in range(model_info["nr_states"]):
        for choice in range(model_info["nr_choices_per_state"][state]):
            if bitvector.get(model_info["nondeterministic_choice_indices"][state] + choice):
                state_to_choice[state] = model_info["nondeterministic_choice_indices"][state] + choice
                break
    return state_to_choice

def state_to_choice_to_bitvector(state_to_choice, model_info):
    bitvector = stormpy.storage.BitVector(model_info["nr_choices"])
    unreachable_states = []
    for state, choice in enumerate(state_to_choice):
        if choice is not None:
            unreachable_states.append(False)
            bitvector.set(choice)
        else:
            unreachable_states.append(True)
    return bitvector, unreachable_states


def remove_unreachable_choices_from_bitvector(bitvector, dt_colored_mdp_factory, model_info):
    state_to_choice = bitvector_to_state_to_choice(bitvector, model_info)
    state_to_choice = dt_colored_mdp_factory.discard_unreachable_choices(state_to_choice)
    new_bitvector, unreachable_states = state_to_choice_to_bitvector(state_to_choice, model_info)
    return new_bitvector, unreachable_states

# maybe completing the bitvector should also be randomized so that we are closer to the uniform sampling?
def complete_bitvector_for_eval(bitvector, unreachable_states, model_info):
    completed_bitvector = stormpy.storage.BitVector(bitvector)
    for state, unreachable in enumerate(unreachable_states):
        if unreachable:
            completed_bitvector.set(model_info["nondeterministic_choice_indices"][state])

    return completed_bitvector



def mcmc_base(shed_bitvector, model_info, dt_colored_mdp_factory, specification, step_count=10000, seed=None):

    shed_bitvector, unreachable_states = remove_unreachable_choices_from_bitvector(shed_bitvector, dt_colored_mdp_factory, model_info)

    all_sat_policies = [shed_bitvector]
    unreachable_states_list = [unreachable_states]
    current_policy = shed_bitvector
    current_unreachable_states = unreachable_states

    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    for _ in range(step_count):

        # sample new policy, to keep the transformation of the policy uniform we remove all unreachable states from the sampling
        selected_state = random.randint(0, model_info["nr_states"]-1)
        while current_unreachable_states[selected_state]:
            selected_state = random.randint(0, model_info["nr_states"]-1)
        selected_state_choice = random.randint(0, model_info["nr_choices_per_state"][selected_state]-1)

        completed_bitvector = complete_bitvector_for_eval(current_policy, current_unreachable_states, model_info)

        new_bitvector = stormpy.storage.BitVector(completed_bitvector)
        for choice in range(model_info["nr_choices_per_state"][selected_state]):
            new_bitvector.set(model_info["nondeterministic_choice_indices"][selected_state] + choice, False)
        new_bitvector.set(model_info["nondeterministic_choice_indices"][selected_state] + selected_state_choice)


        # check if new policy satisfies specification
        submdp_new = dt_colored_mdp_factory.build_from_choice_mask(new_bitvector)
        mc_result_new = submdp_new.model_check_property(specification.all_properties()[0])

        # new_value = mc_result_new.value
        # print(new_value)
        # print(mc_result_new.sat)

        if mc_result_new.sat:
            new_bitvector, new_unreachable_states = remove_unreachable_choices_from_bitvector(new_bitvector, dt_colored_mdp_factory, model_info)
            if new_bitvector not in all_sat_policies:
                all_sat_policies.append(new_bitvector)
                unreachable_states_list.append(new_unreachable_states)
            current_policy = new_bitvector
            current_unreachable_states = new_unreachable_states
        
    return list(zip(all_sat_policies, unreachable_states_list)), (current_policy, current_unreachable_states)



@click.command()
@click.argument('project', type=click.Path(exists=True))
@click.option("--sketch", default="sketch.templ", show_default=True,
    help="name of the sketch file in the project")
@click.option("--props", default="sketch.props", show_default=True,
    help="name of the properties file in the project")
@click.option("--relative-eps", type=float, default=None, show_default=True, help="relative epsilon threhshold computed from random policy")
@click.option("--seed", type=int, default=None, show_default=True, help="random seed for policy sampling")
@click.option("--steps", type=int, default=10000, show_default=True, help="number of MCMC steps")
@click.option("--output", type=click.Path(), default=None, show_default=True, help="file to write the sampled policies to json")
def main(project, sketch, props, relative_eps, seed, steps, output):
    sketch_path = os.path.join(project, sketch)
    props_path = os.path.join(project, props)
    
    sketch_path = os.path.join(project, sketch)
    properties_path = os.path.join(project, props)
    dt_colored_mdp_factory = paynt.parser.sketch.Sketch.load_sketch(sketch_path, properties_path)

    underlying_mdp = dt_colored_mdp_factory.quotient_mdp
    specification = dt_colored_mdp_factory.specification

    if len(specification.constraints) == 0:
        assert False, "currently only specifications with constraints are supported for optimality checking"
    else:
        optimality_specification = get_optimality_specification(specification)

    all_choices = stormpy.storage.BitVector(underlying_mdp.nr_choices, True)
    full_mdp = dt_colored_mdp_factory.build_from_choice_mask(all_choices)
    full_mc_result = full_mdp.model_check_property(optimality_specification.all_properties()[0])
    opt_result_value = full_mc_result.value

    scheduler = full_mc_result.result.scheduler

    random_choices = dt_colored_mdp_factory.get_random_choices()
    submdp_random = dt_colored_mdp_factory.build_from_choice_mask(random_choices)
    mc_result_random = submdp_random.model_check_property(optimality_specification.all_properties()[0])
    random_result_value = mc_result_random.value

    print("optimal value:", opt_result_value)
    print("random value:", random_result_value)
    
    if relative_eps is not None:
        opt_random_diff = opt_result_value - random_result_value
        eps_optimum_threshold = opt_result_value - relative_eps * opt_random_diff

        specification.constraints[0].threshold = eps_optimum_threshold
        specification.constraints[0].property.raw_formula.set_bound(specification.constraints[0].formula.comparison_type, stormpy.ExpressionManager().create_rational(stormpy.Rational(eps_optimum_threshold)))
    else:
        specification.constraints[0].threshold = opt_result_value
        specification.constraints[0].property.raw_formula.set_bound(specification.constraints[0].formula.comparison_type, stormpy.ExpressionManager().create_rational(stormpy.Rational(opt_result_value)))

    # model info important for working with bitvectors
    model_info = {
        "nr_states": underlying_mdp.nr_states,
        "nr_choices": underlying_mdp.nr_choices,
        "nondeterministic_choice_indices": underlying_mdp.nondeterministic_choice_indices,
        "nr_choices_per_state": []
    }

    model_info["nr_choices_per_state"] = [model_info["nondeterministic_choice_indices"][i] - model_info["nondeterministic_choice_indices"][i-1] for i in range(1, len(model_info["nondeterministic_choice_indices"]))]


    shed_bitvector = get_bitvector_from_scheduler(scheduler, model_info)

    start_time = time.time()
    all_samples, last_sample = mcmc_base(shed_bitvector, model_info, dt_colored_mdp_factory, specification, step_count=steps, seed=seed)
    end_time = time.time()
    print(f"sampling took {end_time - start_time:.2f} seconds")

    print(f"number of policies satisfying specification found: {len(all_samples)}")

    if output is not None:
        output_dict = {"X" : get_mdp_features_list(dt_colored_mdp_factory, model_info), "Y" : [sample_to_list(sample, dt_colored_mdp_factory, model_info) for sample in all_samples]}
        with open(output, "w") as f:
            json.dump(output_dict, f, indent=4)


if __name__ == "__main__":
    main()