import click
import os

from paynt.dt.decision_tree import DtVariable, DecisionTree
from paynt.dt.dtnest._utils import scikit_tree_to_tree_helper
import paynt.parser.sketch

import payntbind

import stormpy
import random
import numpy as np
from scipy import sparse
import time
import json

from sklearn import tree, svm
import matplotlib.pyplot as plt

from sample_policies import mcmc_base, get_optimality_specification, get_constraint_specification, get_bitvector_from_scheduler, get_mdp_features_list, remove_unreachable_choices_from_bitvector, sample_to_list

from get_predicates import get_atomic_predicate_evals

import payntbind

from pystreed import STreeDClassifier
from sklearn.metrics import accuracy_score


def get_predicate_types(additional_atomic_predicates):

    import re
    predicate_types = []
    for predicate_name in additional_atomic_predicates.keys():
        # base: {var} <= {constant}
        # const_comp: {var} X {constant}, X != <=
        # var_comp: {var} X {var}
        # Examples: x<=3, x>2, x==y
        # base: only <= and right side is a number
        # const_comp: ==, !=, <, >, >= with right side a number
        # var_comp: ==, !=, <, >, <=, >= with right side a variable

        # Try to match base and const_comp
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*(==|!=|<|<=|>|>=)\s*([a-zA-Z0-9_]+)$", predicate_name)
        if m:
            left, op, right = m.groups()
            # Check if right is a number (constant) or variable
            is_right_number = right.replace('.', '', 1).isdigit()
            is_left_var = left.isidentifier()
            is_right_var = right.isidentifier() and not is_right_number
            if op == '<=' and is_right_number:
                predicate_types.append('base')
            elif is_right_number:
                predicate_types.append('const_comp')
            elif is_right_var:
                predicate_types.append('var_comp')
            else:
                predicate_types.append('unknown')
        else:
            predicate_types.append('unknown')
    return predicate_types


def predicate_dict_to_state_valuations(predicate_dict, dt_colored_mdp_factory=None):
    if dt_colored_mdp_factory is not None:
        orig_state_varriables = dt_colored_mdp_factory.variables
        orig_state_valuations = dt_colored_mdp_factory.relevant_state_valuations
    state_valuations = []
    nr_states = list(predicate_dict.values())[0].size()
    for state in range(nr_states):
        state_valuation = [(predicate, int(val.get(state))) for predicate, val in predicate_dict.items()]
        if dt_colored_mdp_factory is not None:
            for var_id, var in enumerate(orig_state_varriables):
                state_valuation.append((var.name, orig_state_valuations[state][var_id]))
        state_valuations.append(state_valuation)
    return state_valuations


def preorder_index_to_depth(index, tree_depth):
    def helper(idx, cur_idx, cur_depth, cur_tree_depth):
        if cur_tree_depth == 0:
            return -1  # Not found
        if idx == cur_idx:
            return cur_depth
        left_size = 2**(cur_tree_depth - 1) - 1
        left_root = cur_idx + 1
        right_root = cur_idx + 1 + left_size
        if idx < right_root:
            return helper(idx, left_root, cur_depth + 1, cur_tree_depth - 1)
        else:
            return helper(idx, right_root, cur_depth + 1, cur_tree_depth - 1)
    return helper(index, 0, 0, tree_depth)

# added_predicates is used to fix some predicates in the upper levels of the tree
# fixed_predicates_depth specifies up to which depth in the tree predicates should be fixed, e.g. if set to 0 then only the root predicate will be fixed, if set to 1 then predicates in the root and its children will be fixed, etc.
def run_dt_paynt_with_partial_family_init(dt_colored_mdp_factory, tree_depth, added_predicates=None, fixed_predicates_depth=None):
    synthesizer = paynt.dt.DtSynthesizer(dt_colored_mdp_factory)
    synthesizer.quotient.reset_tree(tree_depth)

    family = synthesizer.quotient.family
    # print(dir(synthesizer.quotient.family))
    if added_predicates is not None and fixed_predicates_depth is not None:
        for parameter_id in range(family.num_holes):
            parameter_node_id = family.hole_name(parameter_id).split('_')[-1]
            parameter_node_depth = preorder_index_to_depth(int(parameter_node_id), tree_depth)
            if synthesizer.quotient.is_decision_parameter[parameter_id] and parameter_node_depth <= fixed_predicates_depth:
                options = []
                for option_id, option_label in enumerate(family.hole_to_option_labels[parameter_id]):
                    if option_label in added_predicates:
                        options.append(option_id)
                family = family.assume_hole_options_copy(parameter_id, options)

        print(family)
        # exit()

    synthesizer.counters_reset()
    synthesizer.synthesize(family=family)

    # print(added_predicates)
    # exit()



@click.command()
@click.argument('project', type=click.Path(exists=True))
@click.option("--sketch", default="sketch.templ", show_default=True,
    help="name of the sketch file in the project")
@click.option("--props", default="sketch.props", show_default=True,
    help="name of the properties file in the project")
@click.option("--relative-eps", type=float, default=None, show_default=True, help="relative epsilon threhshold computed from random policy")
@click.option("--seed", type=int, default=None, show_default=True, help="random seed for policy sampling")
@click.option("--steps", type=int, default=10000, show_default=True, help="number of MCMC steps")
@click.option("--burn-in", type=int, default=None, show_default=True, help="number of burn in steps for MCMC sampling")
@click.option("--sample-steps", type=int, default=None, show_default=True, help="interval for collecting samples during MCMC sampling, e.g. if set to 10 then every 10th step after burn in will be collected as a sample")
@click.option("--ccp-alpha", type=float, default=0.0, show_default=True, help="ccp_alpha parameter for decision tree learning, higher values lead to more pruning and thus simpler trees")
@click.option("--output", type=click.Path(), default=None, show_default=True, help="file to write the sampled policies to json")
@click.option("--append-stats", is_flag=True, default=False, show_default=True, help="whether to append sampling and learning stats to results/sampling_stats.csv")
@click.option("--save-features", type=click.Path(), default=None, show_default=True, help="json file where to write the state features")
@click.option("--load-features", type=click.Path(exists=True), default=None, show_default=True, help="json file from which to load state features instead of computing them from the MDP")
def main(project, sketch, props, relative_eps, seed, steps, burn_in, sample_steps, ccp_alpha, output, append_stats, save_features, load_features):
    sketch_path = os.path.join(project, sketch)
    props_path = os.path.join(project, props)

    project_name = os.path.basename(project)

    if append_stats:
        stats_file = 'results/sampling_stats.csv'
        if not os.path.exists(stats_file):
            os.makedirs(os.path.dirname(stats_file), exist_ok=True)
            with open(stats_file, 'w') as f:
                f.write("model,sampling_steps,eps,sampling_time,dt_learning_time,sampled_policies,initial_tree_size,smallest_tree_size\n")
    
    sketch_path = os.path.join(project, sketch)
    properties_path = os.path.join(project, props)
    dt_colored_mdp_factory = paynt.parser.sketch.Sketch.load_sketch(sketch_path, properties_path)

    underlying_mdp = dt_colored_mdp_factory.quotient_mdp
    specification = dt_colored_mdp_factory.specification

    if len(specification.constraints) == 0:
        # assert False, "currently only specifications with constraints are supported for optimality checking"
        optimality_specification = specification
        specification = get_constraint_specification(optimality_specification)
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

    sampling_start_time = time.time()
    all_samples, last_sample = mcmc_base(shed_bitvector, model_info, dt_colored_mdp_factory, specification, step_count=steps, burn_in=burn_in, sample_steps=sample_steps, seed=seed)
    # # all_samples, last_sample = rejection_sampling(model_info, dt_colored_mdp_factory, specification, step_count=steps, seed=seed)
    sampling_end_time = time.time()
    print(f"sampling took {sampling_end_time - sampling_start_time:.2f} seconds")

    # print(f"number of policies satisfying specification found: {len(all_samples)}")

    # additional_atomic_predicates = get_atomic_predicate_evals(dt_colored_mdp_factory)
    # additional_atomic_predicates = get_atomic_predicate_evals(dt_colored_mdp_factory, default_predicates=True)
    # additional_atomic_predicates = {}

    # output_dict = {"X" : get_mdp_features_list(dt_colored_mdp_factory, additional_atomic_predicates, ignore_original_features=False), "Y" : [sample_to_list(sample, dt_colored_mdp_factory, model_info) for sample in all_samples]}

    # exit()


    # print(output_dict['X'])
    # exit()
    # for x in output_dict["Y"]:
    #     print(x)

    # state_feature_to_considered_actions = {tuple(x): set() for x in output_dict["X"]}
    # for i in range(len(output_dict["Y"])):
    #     for j in range(len(output_dict["Y"][i])):
    #         if output_dict["Y"][i][j] != -1:
    #             state_feature_to_considered_actions[tuple(output_dict["X"][j])].add(output_dict["Y"][i][j])
    # print(state_feature_to_considered_actions)
    # product = 1
    # for action_set in state_feature_to_considered_actions.values():
    #     product *= len(action_set)
    # print(product)
    # exit()


    # clf = svm.SVC(kernel="linear")
    # clf = clf.fit(output_dict["X"], output_dict["Y"][0])

    if load_features is not None:
        with open(load_features, 'r') as f:
            loaded_json = json.load(f)
        loaded_X = sparse.csr_matrix(loaded_json[0], dtype=np.uint8)
        variables = [DtVariable(name, domain) for name, domain in loaded_json[1]]
        output_dict = {"X": loaded_X, "Y": [sample_to_list(sample, dt_colored_mdp_factory, model_info) for sample in all_samples]}

    else:

        shed_bitvector = get_bitvector_from_scheduler(scheduler, model_info)
        sample = remove_unreachable_choices_from_bitvector(shed_bitvector, dt_colored_mdp_factory, model_info)

        get_predicates_time_start = time.time()
        additional_atomic_predicates = payntbind.synthesis.get_atomic_predicate_evals(dt_colored_mdp_factory.quotient_mdp.nr_states, [var.name for var in dt_colored_mdp_factory.variables], [var.domain for var in dt_colored_mdp_factory.variables], dt_colored_mdp_factory.relevant_state_valuations)
        get_predicates_time_end = time.time()
        print(f"getting predicate evaluations took {get_predicates_time_end - get_predicates_time_start:.2f} seconds")
        # print(len(additional_atomic_predicates))

        # get_predicates_time_start = time.time()
        # additional_atomic_predicates = get_atomic_predicate_evals(dt_colored_mdp_factory)
        # get_predicates_time_end = time.time()
        # print(f"getting predicate evaluations took {get_predicates_time_end - get_predicates_time_start:.2f} seconds")
        # print(len(additional_atomic_predicates))
        # exit()
        features, variables = get_mdp_features_list(dt_colored_mdp_factory, additional_atomic_predicates, ignore_original_features=True)
        # features, variables = get_mdp_features_list(dt_colored_mdp_factory, {}, ignore_original_features=False)

        # output_dict = {"X" : get_mdp_features_list(dt_colored_mdp_factory, additional_atomic_predicates, ignore_original_features=False), "Y" : [sample_to_list(sample, dt_colored_mdp_factory, model_info)]}
        output_dict = {"X" : features, "Y" : [sample_to_list(sample, dt_colored_mdp_factory, model_info) for sample in all_samples]}

        if save_features is not None:
            variables_json = [[var.name, var.domain] for var in variables]
            with open(save_features, 'w') as f:
                saved_X = output_dict["X"].toarray().tolist() if sparse.issparse(output_dict["X"]) else output_dict["X"]
                json.dump([saved_X, variables_json], f)


    print(f"Number of features: {len(output_dict['X'])}")

    filter_unreachable_class = True
    smallest_tree = None
    smallest_tree_nodes = None

    initial_tree = None
    initial_tree_nodes = None

    average_tree_depth = 0
    average_tree_nodes = 0

    learning_start_time = time.time()

    used_predicate_indices = set()
    predicate_indeces_to_lowest_depth = {}
    used_predicate_frequencies_total = {i: 0 for i in range(len(output_dict['X']))}
    used_predicate_frequencies_per_tree = {i: set() for i in range(len(output_dict['X']))}

    tree_base = DecisionTree(dt_colored_mdp_factory.action_labels, variables)
    
    for i in range(len(output_dict["Y"])):
        clf = tree.DecisionTreeClassifier(criterion="gini", max_depth=None, random_state=0, ccp_alpha=ccp_alpha) # if random_state is None (default) then scikit does not have to be deterministic
        # Filter out points with class -1
        X = output_dict["X"]
        Y = output_dict["Y"][i]
        if filter_unreachable_class:
            reachable_mask = np.array(Y) != -1
            if sparse.issparse(X):
                X = X[reachable_mask]
            else:
                X = [x for j, x in enumerate(X) if reachable_mask[j]]
            Y = np.array(Y)[reachable_mask]

        adjusted_action_labels = [x for i, x in enumerate(dt_colored_mdp_factory.action_labels) if i in Y]

        # print(X)
        # print(Y)

        X = np.array(X)
        Y = np.array(Y)




        # model = STreeDClassifier(max_depth=4, time_limit=10)
        # model.fit(X, Y)

        # model.print_tree()

        # yhat = model.predict(X)

        # accuracy = accuracy_score(Y, yhat)
        # print(f"Train Accuracy Score: {accuracy * 100}%")

        # exit()
        
        clf = clf.fit(X, Y)
        num_nodes = clf.tree_.node_count - clf.tree_.n_leaves
        print(f"Scikit tree depth: {clf.get_depth()}, Number of nodes: {num_nodes}")

        # scikit_tree_helper = scikit_tree_to_tree_helper(clf, variables, adjusted_action_labels)
        # tree_base.build_from_tree_helper(scikit_tree_helper)

        # print(tree_base.to_string())
        # exit()

        # model = STreeDClassifier(max_depth=3, n_categories=100, n_thresholds=100) # TODO handle this n_categories somehow
        # model.fit(X, Y)

        # fit_score = model.score(X, Y)
        # print(f"Streed tree depth: {model.get_depth()}, Number of nodes: {model.tree_.get_num_branching_nodes()}, Fit score: {fit_score}")
        # exit()

        # init_node = (0,0)
        # nodes_to_process = [init_node]
        # while nodes_to_process:
        #     node_id, depth = nodes_to_process.pop()
        #     if clf.tree_.children_left[node_id] != -1: # -2 means it's a leaf node
        #         used_predicate_indices.add(int(clf.tree_.feature[node_id]))
        #         used_predicate_frequencies_total[int(clf.tree_.feature[node_id])] += 1
        #         used_predicate_frequencies_per_tree[int(clf.tree_.feature[node_id])].add(i)
        #         if int(clf.tree_.feature[node_id]) not in predicate_indeces_to_lowest_depth.keys():
        #             predicate_indeces_to_lowest_depth[int(clf.tree_.feature[node_id])] = depth
        #         else:
        #             predicate_indeces_to_lowest_depth[int(clf.tree_.feature[node_id])] = min(predicate_indeces_to_lowest_depth[int(clf.tree_.feature[node_id])], depth)
        #         nodes_to_process.append((clf.tree_.children_left[node_id], depth+1))
        #         nodes_to_process.append((clf.tree_.children_right[node_id], depth+1))

        # # for j in range(clf.tree_.node_count):
        # #     if clf.tree_.children_left[j] != -1: # -2 means it's a leaf node
        # #         used_predicate_indices.add(clf.tree_.feature[j])

        # average_tree_depth += clf.get_depth()
        # average_tree_nodes += num_nodes
        
        # if smallest_tree_nodes is None or num_nodes < smallest_tree_nodes:
        #     smallest_tree_nodes = num_nodes
        #     smallest_tree = clf
        #     smallest_tree_policy = output_dict["Y"][i]

        # if i == 0:
        #     initial_tree = clf
        #     initial_tree_nodes = num_nodes

    exit()

    learning_end_time = time.time()
    print(f"learning took {learning_end_time - learning_start_time:.2f} seconds")

    predicate_indeces_to_lowest_depth = dict(sorted(predicate_indeces_to_lowest_depth.items()))

    print(f"Number of used predicates: {len(used_predicate_indices)} out of {len(output_dict['X'][0])}")

    # print("Smallest tree policy:", smallest_tree_policy)
    print(f"Initial tree has depth {initial_tree.get_depth()} and {initial_tree_nodes} nodes")
    print(f"Smallest tree has depth {smallest_tree.get_depth()} and {smallest_tree_nodes} nodes")
    print(f"Average tree depth: {average_tree_depth/len(output_dict['Y'])}, Average number of nodes: {average_tree_nodes/len(output_dict['Y'])}")
    # tree.plot_tree(smallest_tree)
    # plt.savefig("tree_output.png", dpi=300, bbox_inches='tight')

    used_predicate_frequencies = {i: len(v) / len(output_dict["Y"]) for i, v in used_predicate_frequencies_per_tree.items()}
    flipped_used_predicate_frequencies = {i: 1 - freq for i, freq in used_predicate_frequencies.items()}

    predicate_value = {i: flipped_used_predicate_frequencies[i] * predicate_indeces_to_lowest_depth[i] for i in used_predicate_indices}
    predicate_value = dict(sorted(predicate_value.items(), key=lambda item: item[1]))
    
    considered_predicates_percentage = 0.2
    top_predicates_indices = [i for i in predicate_value.keys() if predicate_value[i] == 0.0]
    for i, value in predicate_value.items():
        if i in top_predicates_indices:
            continue
        if len(top_predicates_indices) < int(len(additional_atomic_predicates)*considered_predicates_percentage):
            top_predicates_indices.append(i)
        else:
            break

    top_predicates = {list(additional_atomic_predicates.keys())[i] : additional_atomic_predicates[list(additional_atomic_predicates.keys())[i]] for i in top_predicates_indices}

    # print(top_predicates)

    new_state_valuations = predicate_dict_to_state_valuations(top_predicates, dt_colored_mdp_factory=dt_colored_mdp_factory)
    # print(new_state_valuations)

    # new_mdp = payntbind.synthesis.addStateValuations(dt_colored_mdp_factory.quotient_mdp, new_state_valuations)
    # new_colored_mdp_factory_dt = paynt.dt.DtColoredMdpFactory(new_mdp)
    # new_colored_mdp_factory_dt.specification = optimality_specification

    # run_dt_paynt_with_partial_family_init(new_colored_mdp_factory_dt, tree_depth=4, added_predicates=list(top_predicates.keys()), fixed_predicates_depth=2)
    # run_dt_paynt_with_partial_family_init(new_colored_mdp_factory_dt, tree_depth=4, added_predicates=None, fixed_predicates_depth=2)

    # synthesizer = paynt.dt.DtSynthesizer(new_colored_mdp_factory_dt)

    # synthesizer.synthesize_tree(3)

    # if synthesizer.best_tree is not None:
    #     print(synthesizer.best_tree.to_string())


    




    # for top_predicate in top_predicates_indices:
    #     print(f"{list(additional_atomic_predicates.keys())[top_predicate]}")



    # print(predicate_indeces_to_lowest_depth)
    # print(used_predicate_frequencies)


    # predicate_types = get_predicate_types(additional_atomic_predicates)
    # # print(list(zip(additional_atomic_predicates.keys(), predicate_types)))
    # # print(predicate_types)
    # # exit()


    # # Assign a color to each predicate type
    # import matplotlib.colors as mcolors
    # type_to_color = {'base': 'tab:blue', 'const_comp': 'tab:orange', 'var_comp': 'tab:green', 'unknown': 'tab:red'}
    # # For each used predicate index, get its type and color
    # colors = [type_to_color.get(predicate_types[i], 'tab:red') for i in predicate_indeces_to_lowest_depth.keys()]

    # plt.figure(figsize=(10, 6))
    # x_vals = list(predicate_indeces_to_lowest_depth.values())
    # y_vals = [flipped_used_predicate_frequencies[i] for i in predicate_indeces_to_lowest_depth.keys()]
    # keys = list(predicate_indeces_to_lowest_depth.keys())
    # scatter = plt.scatter(
    #     x_vals,
    #     y_vals,
    #     c=colors,
    #     label=None,
    #     zorder=2
    # )

    # # Highlight top_predicates with a black edge and larger marker
    # highlight_x = [x_vals[j] for j, i in enumerate(keys) if i in top_predicates_indices]
    # highlight_y = [y_vals[j] for j, i in enumerate(keys) if i in top_predicates_indices]
    # if highlight_x:
    #     plt.scatter(
    #         highlight_x,
    #         highlight_y,
    #         facecolors='none', edgecolors='black', s=120, linewidths=2, marker='o', zorder=3, label='Top Predicates'
    #     )

    # # Create legend manually
    # import matplotlib.patches as mpatches
    # legend_handles = [mpatches.Patch(color=color, label=ptype) for ptype, color in type_to_color.items()]
    # legend_handles.append(mpatches.Patch(facecolor='none', edgecolor='black', label='Top Predicates', linewidth=2))
    # plt.legend(handles=legend_handles, title="Predicate Type")
    # plt.xlabel('Lowest Depth')
    # plt.ylabel('Frequency')
    # plt.title('Predicate Frequency vs Lowest Depth')
    # plt.grid(True)
    # # plt.savefig('predicate_analysis.png', dpi=300, bbox_inches='tight')
    # plt.show()
    # plt.close()

    if append_stats:
        with open(stats_file, 'a') as f:
            f.write(f"{project_name},{steps},{relative_eps},{sampling_end_time - sampling_start_time:.2f},{learning_end_time - learning_start_time:.2f},{len(all_samples)},{initial_tree_nodes},{smallest_tree_nodes}\n")

if __name__ == "__main__":
    main()