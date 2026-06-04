
import json

import stormpy

from .decision_tree import DtVariable

from pystreed import STreeDClassifier
import numpy as np

import logging
logger = logging.getLogger(__name__)

# TODO make this so that it works for POMDP observation valuations as well
def get_state_valuations(model):
    ''' Identify variable names and extract state valuation in the same order. '''
    assert model.has_state_valuations(), "model has no state valuations"
    # get name
    sv = model.state_valuations
    variable_names = None
    state_valuations = []
    for state in range(model.nr_states):
        valuation = json.loads(str(sv.get_json(state)))
        if variable_names is None:
            variable_names = list(valuation.keys())
        valuation = [valuation[var_name] for var_name in variable_names]
        state_valuations.append(valuation)

    return variable_names, state_valuations

def simplify_tree(tree, cmdp_factory):
    ''' Simplify the tree recursively by removing irrelavant leaf nodes.'''
    if tree is None:
        return

    relevant_state_valuations = [cmdp_factory.relevant_state_valuations[state] for state in cmdp_factory.state_is_relevant_bv]
    tree.simplify(relevant_state_valuations)

    return


def feature_binarization(variables, state_valuations):
    ''' Binarize the varibles and the state valuations '''
    
    binarized_variables = []
    for var in variables:
        for x in var.domain[:-1]:
            binarized_variables.append(DtVariable(f"{var.name}<={x}", [0,1]))

    binarized_state_valuations = []
    for valuation in state_valuations:
        binarized_valuation = []
        for i, var in enumerate(variables):
            for x in var.domain[:-1]:
                binarized_valuation.append((f"{var.name}<={x}", 1) if valuation[i] <= x else (f"{var.name}<={x}", 0))
        binarized_state_valuations.append(binarized_valuation)

    logger.info(f"Performed feature binarization. Binarized variables: {[x.name for x in binarized_variables]}")

    return binarized_variables, binarized_state_valuations


def pystreed_tree_to_tree_helper(tree, variables, action_labels, helper=[]):

    id = helper[-1]['id'] + 1 if len(helper) > 0 else 0

    # print(f"node {id}: feature {tree.feature}, label {tree.label}, is_leaf_node {tree.is_leaf_node()}, left_child {tree.left_child}, right_child {tree.right_child}")
    if tree.is_leaf_node(): # leaf node
        chosen_idx = tree.label
        helper.append({'id': id, 'leaf': True, 'chosen': [action_labels[chosen_idx]]})
    else:
        variable = variables[tree.feature].name

        helper.append({'id': id, 'leaf': False, 'chosen': (variable, 0), 'children': []})

        first_child_id = pystreed_tree_to_tree_helper(tree.left_child, variables, action_labels, helper)

        second_child_id = pystreed_tree_to_tree_helper(tree.right_child, variables, action_labels, helper)

        helper[id]['children'] = [first_child_id, second_child_id]

    return id


def pystreed_consistency_check(state_valuations, state_to_action, variables, action_labels, filter_unreachable=True, max_depth=3):

    if filter_unreachable:
        X = np.array([x for i, x in enumerate(state_valuations) if state_to_action[i] is not None])
        Y = np.array([x for x in state_to_action if x is not None])
    else:
        X = np.array(state_valuations)
        Y = np.array([x if x is not None else 0 for x in state_to_action]) # TODO (this is not important for now as filter_unreachable is True) treat the default action better not just setting it to action 0

    model = STreeDClassifier(max_depth=max_depth, n_categories=100, n_thresholds=100) # TODO handle this n_categories somehow
    model.fit(X, Y)

    fit_score = model.score(X, Y)
    consistent = fit_score == 1.0

    tree_helper = []
    pystreed_tree_to_tree_helper(model.tree_, variables, action_labels, tree_helper)

    return consistent, tree_helper
