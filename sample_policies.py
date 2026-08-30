import math

import click
import os

from paynt.dt._utils import feature_binarization
from paynt.dt.decision_tree import DtVariable
import paynt.parser.sketch

import stormpy
import random
import numpy as np
import time
import json

from sklearn import tree, svm
import matplotlib.pyplot as plt

from get_predicates import get_atomic_predicate_evals


def get_mdp_features_list(dt_colored_mdp_factory, additional_atomic_predicates={}, only_relevant_states=False, ignore_original_features=False, binarize_features=True):

    features = dt_colored_mdp_factory.relevant_state_valuations
    variables = dt_colored_mdp_factory.variables

    if binarize_features:
        variables, binarized_valuations = feature_binarization(variables, features)
        features = [[x[1] for x in y] for y in binarized_valuations]

    if ignore_original_features:
        features = [[] for _ in range(len(features))]
        variables = []

    if only_relevant_states:
        features = [features[i] for i in range(len(features)) if dt_colored_mdp_factory.state_is_relevant_bv.get(i)]


    for predicate_name, predicate_eval in additional_atomic_predicates.items():
        rel_state = 0
        for state in range(dt_colored_mdp_factory.state_is_relevant_bv.size()):
            if not only_relevant_states or (only_relevant_states and dt_colored_mdp_factory.state_is_relevant_bv.get(state)):
                features[rel_state].append(1 if predicate_eval.get(rel_state) else 0)
                rel_state += 1
        variables.append(DtVariable(predicate_name, [0,1]))

    return features, variables


def sample_to_list(sample, dt_colored_mdp_factory, model_info):
    bitvector, unreachable_states = sample
    state_to_choice = bitvector_to_state_to_choice(bitvector, model_info)
    result_list = []
    for state, choice in enumerate(state_to_choice):
        if unreachable_states.get(state) or not dt_colored_mdp_factory.state_is_relevant_bv.get(state):
            result_list.append(-1)
        else:
            result_list.append(dt_colored_mdp_factory.choice_to_action[choice])
    
    return result_list


def permissive_sample_to_action_sets(permissive_bitvector, dt_colored_mdp_factory, model_info):
    unreachable_choices = compute_permissive_unreachable_choices(permissive_bitvector, dt_colored_mdp_factory, model_info)
    result_list = []
    for state in range(model_info["nr_states"]):
        first_choice = model_info["nondeterministic_choice_indices"][state]
        if unreachable_choices.get(first_choice) or not dt_colored_mdp_factory.state_is_relevant_bv.get(state):
            result_list.append(-1)
            continue
        allowed_actions = set()
        for choice in range(first_choice, model_info["nondeterministic_choice_indices"][state + 1]):
            if permissive_bitvector.get(choice):
                allowed_actions.add(dt_colored_mdp_factory.choice_to_action[choice])
        result_list.append(sorted(allowed_actions))
    return result_list


def get_optimality_specification(specification):
    specification.constraints[0].threshold = 0
    specification.constraints[0].property.raw_formula.set_bound(specification.constraints[0].formula.comparison_type, stormpy.ExpressionManager().create_rational(stormpy.Rational(0)))
    opt_property = stormpy.Property("", specification.constraints[0].formula.clone())

    paynt_opt_property = paynt.verification.property.construct_property(opt_property, 0, False)
    properties = [paynt_opt_property]

    return paynt.verification.property.Specification(properties)

def get_constraint_specification(specification):

    rf = specification.optimality.property.raw_formula

    optimality_type = rf.optimality_type
    is_probability_operator = rf.is_probability_operator
    is_reward_operator = rf.is_reward_operator
    subformula = rf.subformula

    if is_reward_operator:
        if rf.has_reward_name:
            reward_name = rf.reward_name
        reward_part = f'{{"{reward_name}"}}' if rf.has_reward_name else ''
        comparison_op = '>=' if optimality_type == stormpy.OptimizationDirection.Maximize else '<='
        constraint_formula_str = f"R{reward_part}{comparison_op}0 [{subformula}]"
    elif is_probability_operator:
        constraint_formula_str = f"P{'>=' if optimality_type == stormpy.OptimizationDirection.Maximize else '<='}0 [{subformula}]"
    else:
        assert False, "currently only probability and reward operators are supported for optimality checking"

    constraint_property = stormpy.parse_properties_without_context(constraint_formula_str)[0]

    paynt_opt_property = paynt.verification.property.construct_property(constraint_property, 0, False)
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

def state_to_choice_to_bitvector(state_to_choice, dt_colored_mdp_factory, model_info):
    bitvector = stormpy.storage.BitVector(model_info["nr_choices"])
    unreachable_states = stormpy.storage.BitVector(model_info["nr_states"])
    for state, choice in enumerate(state_to_choice):
        if choice is not None:
            if dt_colored_mdp_factory.state_is_relevant_bv.get(state):
                bitvector.set(choice)
        else:
            unreachable_states.set(state)
    return bitvector, unreachable_states


def remove_unreachable_choices_from_bitvector(bitvector, dt_colored_mdp_factory, model_info):
    state_to_choice = bitvector_to_state_to_choice(bitvector, model_info)
    state_to_choice = dt_colored_mdp_factory.discard_unreachable_choices(state_to_choice)
    new_bitvector, unreachable_states = state_to_choice_to_bitvector(state_to_choice, dt_colored_mdp_factory, model_info)
    return new_bitvector, unreachable_states

# maybe completing the bitvector should also be randomized so that we are closer to the uniform sampling?
def complete_bitvector_for_eval(bitvector, unreachable_states, dt_colored_mdp_factory, model_info):
    completed_bitvector = stormpy.storage.BitVector(bitvector)
    for state in range(model_info["nr_states"]):
        if unreachable_states.get(state):
            selected_state_choice = random.randint(0, model_info["nr_choices_per_state"][state]-1)
            completed_bitvector.set(model_info["nondeterministic_choice_indices"][state] + selected_state_choice)
        elif not dt_colored_mdp_factory.state_is_relevant_bv.get(state):
            completed_bitvector.set(model_info["nondeterministic_choice_indices"][state] + 0) # take the first choice for irrelevant states, should not matter which one we take as they do not influence the behavior of the system

    return completed_bitvector



def mcmc_base(shed_bitvector, model_info, dt_colored_mdp_factory, specification, step_count=10000, burn_in=None, sample_steps=None, seed=None, solution_cache=None):

    shed_bitvector, unreachable_states = remove_unreachable_choices_from_bitvector(shed_bitvector, dt_colored_mdp_factory, model_info)

    if burn_in is None:
        all_sat_policies = [shed_bitvector]
        unreachable_states_list = [unreachable_states]
    else:
        all_sat_policies = []
        unreachable_states_list = []
    current_policy = shed_bitvector
    current_unreachable_states = unreachable_states

    if solution_cache is None:
        solution_cache_sat = set()
        solution_cache_unsat = set()
    else:
        solution_cache_sat = solution_cache["sat"]
        solution_cache_unsat = solution_cache["unsat"]

    cache_hits = 0

    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    for current_step in range(step_count):

        # sample new policy, to keep the transformation of the policy uniform we remove all unreachable states from the sampling
        selected_state = random.randint(0, model_info["nr_states"]-1)
        while current_unreachable_states.get(selected_state) or not dt_colored_mdp_factory.state_is_relevant_bv.get(selected_state):
            selected_state = random.randint(0, model_info["nr_states"]-1)
        selected_state_choice = random.randint(0, model_info["nr_choices_per_state"][selected_state]-1)

        completed_bitvector = complete_bitvector_for_eval(current_policy, current_unreachable_states, dt_colored_mdp_factory, model_info)

        new_bitvector = stormpy.storage.BitVector(completed_bitvector)
        for choice in range(model_info["nr_choices_per_state"][selected_state]):
            new_bitvector.set(model_info["nondeterministic_choice_indices"][selected_state] + choice, False)
        new_bitvector.set(model_info["nondeterministic_choice_indices"][selected_state] + selected_state_choice)

        new_bitvector_reachable, new_unreachable_states = remove_unreachable_choices_from_bitvector(new_bitvector, dt_colored_mdp_factory, model_info)
        cached_sat = False

        if new_bitvector_reachable in solution_cache_sat:
            cached_sat = True
            cache_hits += 1
        elif new_bitvector_reachable in solution_cache_unsat:
            cache_hits += 1
            continue

        # check if new policy satisfies specification
        if not cached_sat:
            submdp_new = dt_colored_mdp_factory.build_from_choice_mask(new_bitvector)
            mc_result_new = submdp_new.model_check_property(specification.all_properties()[0])

        # new_value = mc_result_new.value
        # print(new_value)
        # print(mc_result_new.sat)

        if cached_sat or mc_result_new.sat:
            if (burn_in is None or current_step >= burn_in) and (sample_steps is None or current_step % sample_steps == 0):
                if new_bitvector_reachable not in all_sat_policies:
                    all_sat_policies.append(new_bitvector_reachable)
                    unreachable_states_list.append(new_unreachable_states)
            current_policy = new_bitvector_reachable
            current_unreachable_states = new_unreachable_states
            if not cached_sat:
                solution_cache_sat.add(new_bitvector_reachable)
        else:
            solution_cache_unsat.add(new_bitvector_reachable)
        
    print(f"cache hit percentage: {(cache_hits/step_count*100 if step_count!=0 else 0.0):.2f}%")
    return list(zip(all_sat_policies, unreachable_states_list)), (current_policy, current_unreachable_states)


def compute_permissive_unreachable_choices(permissive_bitvector, dt_colored_mdp_factory, model_info):
    visited_states = stormpy.storage.BitVector(model_info["nr_states"], False)
    initial_state = dt_colored_mdp_factory.quotient_mdp.initial_states[0]
    visited_states.set(initial_state, True)
    queue = [initial_state]

    unreachable_choices = stormpy.storage.BitVector(model_info["nr_choices"], False)

    while queue:
        current_state = queue.pop()
        for choice in range(model_info["nondeterministic_choice_indices"][current_state], model_info["nondeterministic_choice_indices"][current_state+1]):
            if permissive_bitvector.get(choice):
                for dest in dt_colored_mdp_factory.choice_destinations[choice]:
                    if not visited_states.get(dest):
                        visited_states.set(dest, True)
                        queue.append(dest)

    for state in range(model_info["nr_states"]):
        if not visited_states.get(state):
            for choice in range(model_info["nondeterministic_choice_indices"][state], model_info["nondeterministic_choice_indices"][state+1]):
                unreachable_choices.set(choice, True)

    return unreachable_choices


def _print_permissive_convergence_stats(converged, steps_used, step_budget, result_bitvector, rejected_bitvector, unreachable_choices, model_info):
    ''' Shared stats print for mcmc_permissive and mcmc_permissive_optimized. '''
    nr_choices = model_info["nr_choices"]
    accepted = result_bitvector.number_of_set_bits()
    rejected = rejected_bitvector.number_of_set_bits()
    currently_unreachable = (unreachable_choices & ~result_bitvector & ~rejected_bitvector).number_of_set_bits()
    reachable_undecided = nr_choices - accepted - rejected - currently_unreachable

    if converged:
        print(f"converged after {steps_used} steps (budget was {step_budget})")
    else:
        print(f"stopped after exhausting the step budget of {step_budget} without converging")
    print(f"choices: {accepted} accepted, {rejected} rejected, {currently_unreachable} currently unreachable, "
          f"{reachable_undecided} reachable but undecided (out of {nr_choices} total)")


def mcmc_permissive(shed_bitvector, model_info, dt_colored_mdp_factory, specification, step_count=10000, seed=None):

    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    result_bitvector = stormpy.storage.BitVector(shed_bitvector)
    rejected_bitvector = stormpy.storage.BitVector(model_info["nr_choices"], False)
    all_choices = stormpy.storage.BitVector(model_info["nr_choices"], True)

    # feasible_choices holds exactly the choices that are still worth sampling: not yet
    # accepted, not yet rejected, and reachable under the current result_bitvector (testing an
    # unreachable choice is guaranteed to pass and tells us nothing, since build_from_choice_mask
    # already discards unreachable states before model checking). Rejecting a choice can never
    # become safe later (monotonicity), and a choice can never become unreachable again once
    # reachable, so unreachable_choices only needs recomputing after an acceptance, never after
    # a rejection.
    unreachable_choices = compute_permissive_unreachable_choices(result_bitvector, dt_colored_mdp_factory, model_info)
    feasible_choices = list(all_choices & ~result_bitvector & ~rejected_bitvector & ~unreachable_choices)

    converged = False
    current_step = 0
    while current_step < step_count:
        if not feasible_choices:
            converged = True
            break

        # sample uniformly from the still-feasible choices; swap-pop keeps removal O(1)
        index = random.randrange(len(feasible_choices))
        selected_choice = feasible_choices[index]
        feasible_choices[index] = feasible_choices[-1]
        feasible_choices.pop()

        result_bitvector.set(selected_choice)

        submdp_new = dt_colored_mdp_factory.build_from_choice_mask(result_bitvector)
        mdp_result = submdp_new.model_check_property(specification.all_properties()[0])

        if mdp_result.sat or mdp_result.value == math.inf:
            result_bitvector.set(selected_choice, False)
            rejected_bitvector.set(selected_choice, True)
        else:
            unreachable_choices = compute_permissive_unreachable_choices(result_bitvector, dt_colored_mdp_factory, model_info)
            feasible_choices = list(all_choices & ~result_bitvector & ~rejected_bitvector & ~unreachable_choices)

        current_step += 1

    if not feasible_choices:
        converged = True
    _print_permissive_convergence_stats(
        converged, current_step, step_count, result_bitvector, rejected_bitvector, unreachable_choices, model_info)

    submdp_new = dt_colored_mdp_factory.build_from_choice_mask(result_bitvector)
    mdp_result = submdp_new.model_check_property(specification.all_properties()[0])
    print(f"final permissive policy model checking result: {mdp_result.sat}, value: {mdp_result.value}")
    assert not mdp_result.sat and mdp_result.value != math.inf, "permissive policy does not satisfy specification"

    return result_bitvector


def _bellman_optimal_choices(dt_colored_mdp_factory, optimality_property, state_values, tol):
    '''
    Choices c at state s with Q(s,c) within tol of the optimal value V*(s). These are the
    actions a Bellman backup from the optimal value function would consider "just as good" as
    the actual optimal choice, so they are safe to try adding to a permissive policy without
    spending a model-checking call on each one individually.
    '''
    quotient_mdp = dt_colored_mdp_factory.quotient_mdp
    choice_q_values = dt_colored_mdp_factory.choice_values(quotient_mdp, optimality_property, state_values)
    nondeterministic_choice_indices = quotient_mdp.nondeterministic_choice_indices
    maximizing = optimality_property.maximizing

    bellman_optimal = stormpy.storage.BitVector(quotient_mdp.nr_choices, False)
    for state in range(quotient_mdp.nr_states):
        value = state_values[state]
        for choice in range(nondeterministic_choice_indices[state], nondeterministic_choice_indices[state+1]):
            q_value = choice_q_values[choice]
            if maximizing:
                if q_value >= value - tol:
                    bellman_optimal.set(choice, True)
            else:
                if q_value <= value + tol:
                    bellman_optimal.set(choice, True)
    return bellman_optimal


def _filter_mec_trap_choices(dt_colored_mdp_factory, candidate_bitvector, optimality_property, shed_bitvector):
    '''
    Remove choices that only close off maximal end components (MECs) which cannot reach the
    target, i.e. Bellman-optimal-looking actions that would let a permissive scheduler get stuck
    looping forever instead of reaching the target (a MEC's induced sub-stochastic matrix
    trivially satisfies V = P*V for any constant, so tied-looking actions can support such a
    spurious loop even though every action was individually Bellman-optimal).

    Best-effort: if the property isn't a plain reachability property, or MEC decomposition
    otherwise fails, this just returns candidate_bitvector (plus shed_bitvector) unchanged -
    correctness is still guaranteed downstream since every addition is re-verified by an actual
    model-checking call before being kept.
    '''
    filtered = stormpy.storage.BitVector(candidate_bitvector)
    filtered |= shed_bitvector

    try:
        target_label = optimality_property.get_target_label()
        target_states = dt_colored_mdp_factory.quotient_mdp.labeling.get_states(target_label)
        submdp = dt_colored_mdp_factory.build_from_choice_mask(filtered)
        decomposition = stormpy.storage.get_maximal_end_components(submdp.model)
    except Exception:
        return filtered

    for mec in decomposition:
        mec_entries = list(mec)
        contains_target = any(
            target_states.get(submdp.quotient_state_map[local_state]) for local_state, _ in mec_entries
        )
        if contains_target:
            continue
        for local_state, local_choices in mec_entries:
            for local_choice in local_choices:
                global_choice = submdp.quotient_choice_map[local_choice]
                filtered.set(global_choice, False)

    filtered |= shed_bitvector
    return filtered


def _batch_try_add(base_bitvector, candidate_choices, excluded_bitvector, dt_colored_mdp_factory, specification, call_counter, call_budget):
    '''
    Try enabling all of candidate_choices on top of base_bitvector in a single model-checking
    call. If the whole batch still satisfies the (negated) specification, accept it in bulk: by
    monotonicity (enabling more choices can only make an adversarial/violating scheduler easier
    to find, never harder), every subset of an accepted batch - including every singleton - is
    provably safe too, so no further checks are needed for it. If the batch fails, bisect and
    recurse; a rejected singleton is recorded in excluded_bitvector so it is never retried again
    (rejecting a choice can never become safe later, for the same monotonicity reason).
    '''
    if not candidate_choices or call_counter[0] >= call_budget:
        return base_bitvector

    trial_bitvector = stormpy.storage.BitVector(base_bitvector)
    for choice in candidate_choices:
        trial_bitvector.set(choice, True)

    submdp = dt_colored_mdp_factory.build_from_choice_mask(trial_bitvector)
    mdp_result = submdp.model_check_property(specification.all_properties()[0])
    call_counter[0] += 1

    if not mdp_result.sat and mdp_result.value != math.inf:
        return trial_bitvector

    if len(candidate_choices) == 1:
        excluded_bitvector.set(candidate_choices[0], True)
        return base_bitvector

    mid = len(candidate_choices) // 2
    base_bitvector = _batch_try_add(
        base_bitvector, candidate_choices[:mid], excluded_bitvector, dt_colored_mdp_factory, specification, call_counter, call_budget)
    base_bitvector = _batch_try_add(
        base_bitvector, candidate_choices[mid:], excluded_bitvector, dt_colored_mdp_factory, specification, call_counter, call_budget)
    return base_bitvector


def mcmc_permissive_optimized(shed_bitvector, model_info, dt_colored_mdp_factory, specification,
                               optimality_property, optimal_state_values,
                               step_count=10000, seed=None, tol=1e-4, worklist_batch_size=16):
    '''
    Optimized variant of mcmc_permissive. Seeds the permissive bitvector with Bellman-optimal
    actions (filtered to avoid MEC traps), bulk-verifies them with a single model-checking call
    when possible, and only then falls back to a shuffled worklist over the remaining choices -
    each choice is tested at most once, and once a choice is rejected it is never retried, since
    rejecting it can never become safe again as more choices get enabled (monotonicity of the
    negated specification's Pmin/Pmax check).

    Note step_count here is a budget of model-checking calls (a single batched call that
    resolves several choices at once still only counts as one call), not a count of individual
    proposals like in mcmc_permissive.

    Choices sitting at states that are currently unreachable under result_bitvector are held
    back from testing entirely rather than being pre-judged safe: build_from_choice_mask already
    discards unreachable states before model checking, so testing one now would be a guaranteed
    no-op, but bulk-accepting it for free would re-introduce the MEC-trap risk the moment its
    state actually becomes reachable (see compute_permissive_unreachable_choices). Since
    reachability can only grow as more choices get enabled and never shrinks back, it only needs
    recomputing after an acceptance, never after a rejection.
    '''
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    result_bitvector = stormpy.storage.BitVector(shed_bitvector)
    excluded_bitvector = stormpy.storage.BitVector(model_info["nr_choices"], False)
    call_counter = [0]

    # bellman-optimal, MEC-filtered candidates - a structural fact about the MDP, computed once
    # regardless of which states happen to be reachable right now
    bellman_optimal = _bellman_optimal_choices(dt_colored_mdp_factory, optimality_property, optimal_state_values, tol)
    priority_bv_full = _filter_mec_trap_choices(dt_colored_mdp_factory, bellman_optimal, optimality_property, shed_bitvector)
    print(f"bellman-optimal candidates: {bellman_optimal.number_of_set_bits()}, "
          f"after MEC filtering: {priority_bv_full.number_of_set_bits()}")
    priority_bv = priority_bv_full & ~result_bitvector

    all_choices = stormpy.storage.BitVector(model_info["nr_choices"], True)
    priority_list = list(priority_bv)
    random.shuffle(priority_list)
    other_list = list(all_choices & ~result_bitvector & ~priority_bv)
    random.shuffle(other_list)
    # priority candidates come first, so the first wave attempts them as one large batch (mirrors
    # trying the whole bellman-optimal seed at once); everything else is drained afterwards with
    # a batch size that adapts to the observed rejection rate, same rationale as before: a batch
    # accepted outright grows the next one, a batch that needs any bisection shrinks the next one
    # (bisecting a mostly-bad batch of size n can cost up to 2n-1 calls, worse than testing n
    # items one at a time).
    pending = priority_list + other_list
    batch_size = max(len(priority_list), worklist_batch_size, 1)

    unreachable_choices = compute_permissive_unreachable_choices(result_bitvector, dt_colored_mdp_factory, model_info)

    converged = False
    while pending:
        if call_counter[0] >= step_count:
            break

        testable = [choice for choice in pending if not unreachable_choices.get(choice)]
        deferred = [choice for choice in pending if unreachable_choices.get(choice)]
        if not testable:
            # nothing testable right now, and nothing left pending could ever make anything else
            # reachable either - this is the converged fixed point
            converged = True
            break

        chunk = testable[:batch_size]
        pending = testable[batch_size:] + deferred

        excluded_before = excluded_bitvector.number_of_set_bits()
        accepted_before = result_bitvector.number_of_set_bits()
        result_bitvector = _batch_try_add(
            result_bitvector, chunk, excluded_bitvector, dt_colored_mdp_factory, specification, call_counter, step_count)

        if excluded_bitvector.number_of_set_bits() == excluded_before:
            batch_size *= 2
        else:
            batch_size = max(1, batch_size // 2)

        if result_bitvector.number_of_set_bits() > accepted_before:
            unreachable_choices = compute_permissive_unreachable_choices(result_bitvector, dt_colored_mdp_factory, model_info)

    if not pending:
        converged = True
    _print_permissive_convergence_stats(
        converged, call_counter[0], step_count, result_bitvector, excluded_bitvector, unreachable_choices, model_info)

    submdp_new = dt_colored_mdp_factory.build_from_choice_mask(result_bitvector)
    mdp_result = submdp_new.model_check_property(specification.all_properties()[0])
    print(f"final permissive policy model checking result: {mdp_result.sat}, value: {mdp_result.value}")
    assert not mdp_result.sat and mdp_result.value != math.inf, "permissive policy does not satisfy specification"

    return result_bitvector

# I had to test this, obviously this does not work at all
def rejection_sampling(model_info, dt_colored_mdp_factory, specification, step_count=10000, seed=None):

    all_sat_policies = []
    unreachable_states_list = []

    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    for _ in range(step_count):
        bitvector = stormpy.storage.BitVector(model_info["nr_choices"])
        for state in range(model_info["nr_states"]):
            selected_state_choice = random.randint(0, model_info["nr_choices_per_state"][state]-1)
            bitvector.set(model_info["nondeterministic_choice_indices"][state] + selected_state_choice)

        submdp = dt_colored_mdp_factory.build_from_choice_mask(bitvector)
        mc_result = submdp.model_check_property(specification.all_properties()[0])

        if mc_result.sat:
            bitvector_reachable, unreachable_states = remove_unreachable_choices_from_bitvector(bitvector, dt_colored_mdp_factory, model_info)
            if bitvector_reachable not in all_sat_policies:
                all_sat_policies.append(bitvector_reachable)
                unreachable_states_list.append(unreachable_states)

    return list(zip(all_sat_policies, unreachable_states_list)), None



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
@click.option("--permissive", is_flag=True, default=False, show_default=True, help="if set then the sampling will produce a permissive policy, i.e. a set of policies that satisfy the specification, instead of a single policy")
@click.option("--optimized", is_flag=True, default=False, show_default=True, help="if set together with --permissive, use the seeded/batched mcmc_permissive_optimized instead of mcmc_permissive")
@click.option("--output", type=click.Path(), default=None, show_default=True, help="file to write the sampled policies to json")
def main(project, sketch, props, relative_eps, seed, steps, burn_in, sample_steps, ccp_alpha, permissive, optimized, output):
    sketch_path = os.path.join(project, sketch)
    props_path = os.path.join(project, props)

    project_name = os.path.basename(project)
    
    sketch_path = os.path.join(project, sketch)
    properties_path = os.path.join(project, props)
    dt_colored_mdp_factory = paynt.parser.sketch.Sketch.load_sketch(sketch_path, properties_path)

    underlying_mdp = dt_colored_mdp_factory.quotient_mdp
    specification = dt_colored_mdp_factory.specification

    if len(specification.constraints) == 0:
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

        if permissive:
            specification.constraints[0] = specification.constraints[0].negate()
    else:
        specification.constraints[0].threshold = opt_result_value
        specification.constraints[0].property.raw_formula.set_bound(specification.constraints[0].formula.comparison_type, stormpy.ExpressionManager().create_rational(stormpy.Rational(opt_result_value)))

        if permissive:
            specification.constraints[0] = specification.constraints[0].negate()

    # model info important for working with bitvectors
    model_info = {
        "nr_states": underlying_mdp.nr_states,
        "nr_choices": underlying_mdp.nr_choices,
        "nondeterministic_choice_indices": underlying_mdp.nondeterministic_choice_indices,
        "nr_choices_per_state": []
    }

    model_info["nr_choices_per_state"] = [model_info["nondeterministic_choice_indices"][i] - model_info["nondeterministic_choice_indices"][i-1] for i in range(1, len(model_info["nondeterministic_choice_indices"]))]


    shed_bitvector = get_bitvector_from_scheduler(scheduler, model_info)

    if permissive:
        if optimized:
            permissive_sample = mcmc_permissive_optimized(
                shed_bitvector, model_info, dt_colored_mdp_factory, specification,
                optimality_specification.all_properties()[0], full_mc_result.result.get_values(),
                step_count=steps, seed=seed)
        else:
            permissive_sample = mcmc_permissive(shed_bitvector, model_info, dt_colored_mdp_factory, specification, step_count=steps, seed=seed)

        additional_atomic_predicates = get_atomic_predicate_evals(dt_colored_mdp_factory)
        features, variables = get_mdp_features_list(dt_colored_mdp_factory, additional_atomic_predicates)
        action_sets = permissive_sample_to_action_sets(permissive_sample, dt_colored_mdp_factory, model_info)

        output_dict = {"X" : features, "Y_actions_allowed" : action_sets}
        if output is not None:
            with open(output, "w") as f:
                json.dump(output_dict, f, indent=4)
    else:
        sampling_start_time = time.time()
        all_samples, last_sample = mcmc_base(shed_bitvector, model_info, dt_colored_mdp_factory, specification, step_count=steps, burn_in=burn_in, sample_steps=sample_steps, seed=seed)
        # all_samples, last_sample = rejection_sampling(model_info, dt_colored_mdp_factory, specification, step_count=steps, seed=seed)
        sampling_end_time = time.time()
        print(f"sampling took {sampling_end_time - sampling_start_time:.2f} seconds")

        print(f"number of policies satisfying specification found: {len(all_samples)}")

        additional_atomic_predicates = get_atomic_predicate_evals(dt_colored_mdp_factory)
        # additional_atomic_predicates = get_atomic_predicate_evals(dt_colored_mdp_factory, default_predicates=True)
        # additional_atomic_predicates = {}

        features, variables = get_mdp_features_list(dt_colored_mdp_factory, additional_atomic_predicates)

        output_dict = {"X" : features, "Y" : [sample_to_list(sample, dt_colored_mdp_factory, model_info) for sample in all_samples]}
        if output is not None:
            with open(output, "w") as f:
                json.dump(output_dict, f, indent=4)

if __name__ == "__main__":
    main()