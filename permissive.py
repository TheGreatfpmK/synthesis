
import paynt
import payntbind
import stormpy

import paynt.parser.sketch
from paynt.quotient.mdp import MdpQuotient
import paynt.synthesizer.synthesizer
import paynt.synthesizer.decision_tree
import paynt.utils.dtnest_helper

import os
import json

import click
import cProfile
import pstats

import logging
logger = logging.getLogger(__name__)

class PermissiveSynthesizer(paynt.synthesizer.synthesizer.Synthesizer):

    @property
    def method_name(self):
        return "Permissive"

    def __init__(self, quotient, eps_threshold=None, mc_reuse=True, cache_sat=False, cache_unsat=False):
        super().__init__(quotient)
        
        self.permissive_policies = []
        self.discarded_families = []
        self.mc_reuse = mc_reuse
        self.cache_sat = cache_sat
        self.cache_unsat = cache_unsat
        # self.safe_scheduler_count = 0

        assert len(self.quotient.specification.constraints) == 1, "only single-constraint specifications supported"

        if eps_threshold is not None:
            threshold_diff = self.quotient.specification.constraints[0].threshold * eps_threshold
            overapp_threshold = self.quotient.specification.constraints[0].threshold - threshold_diff if self.quotient.specification.constraints[0].minimizing else self.quotient.specification.constraints[0].threshold + threshold_diff
            overapp_threshold = min(max(overapp_threshold, 0.0), 1.0)
            self.overapp_threshold = overapp_threshold
        else:
            self.overapp_threshold = None

    def state_to_choice_to_choices_unreachable(self, state_to_choice):
        num_choices = self.quotient.quotient_mdp.nr_choices
        choices = stormpy.BitVector(num_choices,False)
        nci = self.quotient.quotient_mdp.nondeterministic_choice_indices
        for state, choice in enumerate(state_to_choice):
            if choice is not None and choice < num_choices:
                choices.set(choice,True)
            else:
                for state_choice in range(nci[state], nci[state+1]):
                    choices.set(state_choice,True)
        return choices

    def scheduler_selection_unreachable(self, mdp, scheduler):
        state_to_choice = self.quotient.scheduler_to_state_to_choice(mdp, scheduler)
        choices = self.state_to_choice_to_choices_unreachable(state_to_choice)
        hole_selection = self.quotient.coloring.collectHoleOptions(choices)
        return hole_selection

    def check_specification(self, family):
        ''' Check specification for mdp or smg based on self.quotient '''
        mdp = family.mdp

        if isinstance(self.quotient, paynt.quotient.posmg.PosmgQuotient):
            model = self.quotient.create_smg_from_mdp(mdp)
        else:
            model = mdp

        # check constraints
        spec = self.quotient.specification
        if family.constraint_indices is None:
            family.constraint_indices = spec.all_constraint_indices()
        results = [None for _ in spec.constraints]
        for index in family.constraint_indices:
            constraint = spec.constraints[index]
            result = paynt.verification.property_result.MdpPropertyResult(constraint)
            results[index] = result

            # if family.parent_info is not None and family.parent_info.consistent_primary:
            #     print(family.parent_info.result.primary_selection_original[family.parent_info.splitter], family.parent_info.result.secondary_selection[family.parent_info.splitter], family.hole_options(family.parent_info.splitter), family.parent_info.splitter)

            if self.mc_reuse and family.parent_info is not None and family.parent_info.consistent_primary and set(family.parent_info.result.primary_selection_original[family.parent_info.splitter]).issubset(set(family.hole_options(family.parent_info.splitter))):

                result.primary = family.parent_info.result.primary
                result.primary_selection_original = family.parent_info.result.primary_selection_original
                consistent = True
                result.primary_reused = True

            else:
                # check primary direction
                result.primary = model.model_check_property(constraint)
                self.stat.iteration(family.mdp)
                result.primary_selection_original, consistent = self.quotient.scheduler_is_consistent(mdp, constraint, result.primary.result)

            # print(f"primary: {result.primary.value}")
            if result.primary.sat is False:
                result.sat = False
                break

            if self.mc_reuse and family.parent_info is not None and family.parent_info.consistent_primary and set(family.parent_info.result.secondary_selection[family.parent_info.splitter]).issubset(set(family.hole_options(family.parent_info.splitter))):

                result.secondary = family.parent_info.result.secondary
                result.secondary_selection = family.parent_info.result.secondary_selection
                result.secondary_reused = True

            else:

                # primary direction is SAT: check secondary direction to see whether all SAT
                result.secondary = model.model_check_property(constraint, alt=True)
                self.stat.iteration(family.mdp)
                result.secondary_selection, _ = self.quotient.scheduler_is_consistent(mdp, constraint, result.secondary.result)

            if consistent:
                family.consistent_primary = True

                assert len(result.primary_selection_original) == len(result.secondary_selection)
                selection = [[] for _ in range(len(result.primary_selection_original))]
                for i in range(len(result.primary_selection_original)):
                    selection[i] = result.primary_selection_original[i].copy()
                    for x in result.secondary_selection[i]:
                        if x not in selection[i]:
                            selection[i].append(x)
                result.primary_selection = selection
            else:
                result.primary_selection = result.primary_selection_original.copy()

            # print(f"secondary: {result.secondary.value}")
            if mdp.is_deterministic and abs(result.primary.value - result.secondary.value) > 1e-4:
                logger.warning(f"WARNING: model is deterministic but min < max: {result.primary.value} {result.secondary.value}")
            if result.secondary.sat or result.primary.sat and abs(result.primary.value - result.secondary.value) <= 1e-4:
                # only count permissive schedulers that are not overly conservative as SAT
                if self.overapp_threshold is None or result.primary.value >= self.overapp_threshold:
                    result.sat = True
                    continue

            # discard overly conservative schedulers
            if self.overapp_threshold is not None and result.secondary.value < self.overapp_threshold:
                result.sat = False
                break

        spec_result = paynt.verification.property_result.MdpSpecificationResult()
        spec_result.constraints_result = paynt.verification.property_result.ConstraintsResult(results)

        family.analysis_result = spec_result

    def verify_family(self, family):
        self.quotient.build(family)

        # if isinstance(self.quotient, paynt.quotient.posmg.PosmgQuotient):
        #     self.stat.iteration_game(family.mdp.states)
        # else:
        #     self.stat.iteration(family.mdp)

        # TODO probably only save the hole assignment
        self.check_specification(family)

    def check_result(self, family):
        result = family.analysis_result
        if result is None:
            return
        elif result.constraints_result.sat is False:
            if self.cache_unsat:
                unreachable_selection = self.scheduler_selection_unreachable(family.mdp, result.constraints_result.results[0].primary.result.scheduler)
                unreachable_family = self.full_family.assume_options_copy(unreachable_selection)
                self.discarded_families.append(unreachable_family)
            return
        elif result.constraints_result.sat is True:
            if self.cache_sat:
                unreachable_selection = self.scheduler_selection_unreachable(family.mdp, result.constraints_result.results[0].secondary.result.scheduler)
                unreachable_family = self.full_family.assume_options_copy(unreachable_selection)
                self.permissive_policies.append(unreachable_family)
            else:
                self.permissive_policies.append(family)

    def split(self, family):

        mdp = family.mdp
        assert not mdp.is_deterministic

        # split family wrt last undecided result
        result = family.analysis_result.undecided_result()
        hole_assignments = result.primary_selection
        if not result.primary_reused:
            scores = self.quotient.scheduler_scores(mdp, result.prop, result.primary.result, result.primary_selection)
        elif not result.secondary_reused:
            scores = self.quotient.scheduler_scores(mdp, result.prop, result.secondary.result, result.primary_selection)
        if scores is None:
            scores = {hole:0 for hole in range(mdp.family.num_holes) if mdp.family.hole_num_options(hole) > 1}

        splitters = self.quotient.holes_with_max_score(scores)
        splitter = splitters[0]
        if len(hole_assignments[splitter]) > 1:
            core_suboptions,other_suboptions = self.quotient.suboptions_enumerate(mdp, splitter, hole_assignments[splitter])
        else:
            assert mdp.family.hole_num_options(splitter) > 1
            core_suboptions = self.quotient.suboptions_half(mdp, splitter)
            other_suboptions = []
        # print(mdp.family[splitter], core_suboptions, other_suboptions)

        if len(other_suboptions) == 0:
            suboptions = core_suboptions
        else:
            suboptions = [other_suboptions] + core_suboptions  # DFS solves core first

        # construct corresponding subfamilies
        parent_info = family.collect_parent_info(self.quotient.specification,splitter)
        subfamilies = family.split(splitter,suboptions)
        for subfamily in subfamilies:
            subfamily.add_parent_info(parent_info)
        return subfamilies

    def synthesize_one(self, family):
        self.full_family = family
        families = [family]
        while families:
            if self.resource_limit_reached():
                break
            family_explored = False
            family = families.pop(-1)
            for explored_family in self.permissive_policies if self.cache_sat else [] + self.discarded_families if self.cache_unsat else []:
                if family.family.isSubsetOf(explored_family.family):
                    family_explored = True
                    break
            if family_explored:
                self.explore(family)
                continue
            self.verify_family(family)
            self.check_result(family)
            if family.analysis_result.constraints_result.sat is False:
                self.explore(family)
                continue
            if family.analysis_result.constraints_result.sat is True:
                self.explore(family)
                # return
                continue
            # undecided
            subfamilies = self.split(family)
            families = families + subfamilies


    def print_schedulers(self):
        for i, family in enumerate(self.permissive_policies):
            print(f"Permissive scheduler {i}: {family}")


class PermissiveTreeSynthesizer(PermissiveSynthesizer):

    INITIAL_TREE_DEPTH = 0

    @property
    def method_name(self):
        return "PermissiveTree"

    def __init__(self, quotient, mdp_quotient, eps_threshold=None, mc_reuse=True, cache_sat=False, cache_unsat=False):
        super().__init__(quotient, eps_threshold, mc_reuse, cache_sat, cache_unsat)
        self.mdp_quotient = mdp_quotient

        self.unimplementable_families = []

        self.tree_scheduler_hole_selection = None

        # initialize tree template
        self.construct_tree_coloring(self.INITIAL_TREE_DEPTH)

        self.dtcontrol_metadata = self.create_dtcontrol_metadata()


    def create_dtcontrol_metadata(self):
        metadata = {
            "x_column_types": {
                "numeric": [x for x in range(len(self.mdp_quotient.variables))],
                "categorical": []
            },
            "x_column_names": [x.name for x in self.mdp_quotient.variables],
            "y_column_type": {
                "categorical": [0]
            },
            "y_category_names": {
                0: self.mdp_quotient.action_labels
            }
        }

        return json.dumps(metadata, indent=4)


    def family_to_permissive_csv(self, family):
        choices = self.quotient.coloring.selectCompatibleChoices(family.family)
        nci = self.quotient.quotient_mdp.nondeterministic_choice_indices.copy()
        csv_str = f"#PERMISSIVE\n#BEGIN {len(self.mdp_quotient.variables)} 1\n"

        for state in range(self.quotient.quotient_mdp.nr_states):
            str_val_list = [f"{x}," for x in self.mdp_quotient.relevant_state_valuations[state]]
            state_str = "".join(str_val_list)
            for choice in range(nci[state], nci[state+1]):
                if choices.get(choice):
                    action = self.mdp_quotient.choice_to_action[choice]
                    csv_str += f"{state_str}{action}\n"

        return csv_str
    
    def create_quotient_scheduler(self, family, scheduler):

        new_scheduler = payntbind.synthesis.create_scheduler(self.quotient.quotient_mdp.nr_states)
        quotient_mdp_nci = self.quotient.quotient_mdp.nondeterministic_choice_indices.copy()
        state_to_choice = self.quotient.scheduler_to_state_to_choice(family.mdp, scheduler)
        for state in range(self.quotient.quotient_mdp.nr_states):
            quotient_choice = state_to_choice[state]
            if quotient_choice is None or not self.mdp_quotient.state_is_relevant_bv.get(state):
                payntbind.synthesis.set_dont_care_state_for_scheduler(new_scheduler, state, 0, False)
                index = 0
            else:
                index = quotient_choice - quotient_mdp_nci[state]
            scheduler_choice = stormpy.storage.SchedulerChoice(index)
            new_scheduler.set_choice(scheduler_choice, state)

        return new_scheduler

    def construct_tree_coloring(self, depth):
        self.mdp_quotient.reset_tree(depth, False)
        self.mdp_quotient.build(self.mdp_quotient.family)

    def tree_from_hole_selection(self, hole_selection):
        self.last_tree_assignment = self.mdp_quotient.family.assume_options_copy(hole_selection)
        tree = None
        dtmc = self.mdp_quotient.build_assignment(self.last_tree_assignment)
        res = dtmc.check_specification(self.quotient.specification)
        sat = res.constraints_result.sat
        if sat:
            tree = self.mdp_quotient.decision_tree
            tree.root.associate_assignment(self.last_tree_assignment)
        return tree

    def check_implementability(self, family):
        choices = self.quotient.coloring.selectCompatibleChoices(family.family)
        self.mdp_quotient.coloring.selectCompatibleChoices(self.mdp_quotient.family.family)
        consistent,hole_selection = self.mdp_quotient.coloring.areChoicesConsistentPermissive(choices, self.mdp_quotient.family.family)
        tree = None

        # if implementable, check the returned tree
        if consistent:
            tree = self.tree_from_hole_selection(hole_selection)

            # get policy family from tree
            choices = self.mdp_quotient.coloring.selectCompatibleChoices(self.last_tree_assignment.family)
            self.tree_scheduler_hole_selection = self.quotient.coloring.collectHoleOptions(choices)


        return consistent, tree
    
    def split_dt(self, family):

        mdp = family.mdp
        assert not mdp.is_deterministic

        # split family wrt last undecided result
        result = family.analysis_result.undecided_result()
        hole_assignments = result.primary_selection

        # use tree scheduler hole selection to guide splitting
        if self.tree_scheduler_hole_selection is not None:
            new_hole_assignments = [[] for _ in range(len(hole_assignments))]
            for hole, options in enumerate(self.tree_scheduler_hole_selection):
                if len(options) > 0 and options[0] not in hole_assignments[hole]:
                    new_hole_assignments[hole] = hole_assignments[hole] + options
            
            max_options_count = max(len(options) for options in new_hole_assignments)
            if max_options_count > 1:
                hole_assignments = new_hole_assignments

        scores = None
        if not result.primary_reused:
            scores = self.quotient.scheduler_scores(mdp, result.prop, result.primary.result, hole_assignments)
        elif not result.secondary_reused:
            scores = self.quotient.scheduler_scores(mdp, result.prop, result.secondary.result, hole_assignments)
        if scores is None:
            scores = {hole:len(options) for hole,options in enumerate(hole_assignments) if mdp.family.hole_num_options(hole) > 1}

        # only consider scores for holes which include the decision from DT
        if self.tree_scheduler_hole_selection is not None:
            new_scores = scores.copy()
            for hole, options in enumerate(self.tree_scheduler_hole_selection):
                if len(options) == 0:
                    new_scores.pop(hole, None)
            if len(new_scores) > 0:
                scores = new_scores

        # splitting only to two subfamilies
        splitters = self.quotient.holes_with_max_score(scores)
        splitter = splitters[0]
        if len(hole_assignments[splitter]) > 1:
            if self.tree_scheduler_hole_selection is not None and len(self.tree_scheduler_hole_selection[splitter]) > 0:
                core_suboptions = [[option] for option in hole_assignments[splitter] if option not in self.tree_scheduler_hole_selection[splitter]]
                if len(core_suboptions) <= 1:
                    core_suboptions = [[option] for option in hole_assignments[splitter]]
                else:
                    core_suboptions[0] = core_suboptions[0] + self.tree_scheduler_hole_selection[splitter]
                other_suboptions = [option for option in family.hole_options(splitter) if option not in hole_assignments[splitter]]
            else:
                core_suboptions,other_suboptions = self.quotient.suboptions_enumerate(mdp, splitter, hole_assignments[splitter])
        else:
            assert mdp.family.hole_num_options(splitter) > 1
            core_suboptions = self.quotient.suboptions_half(mdp, splitter)
            other_suboptions = []
        # print(mdp.family[splitter], core_suboptions, other_suboptions)

        # split up the other_suboptions evenly to core_suboptions
        if len(other_suboptions) > 0:
            for i, option in enumerate(other_suboptions):
                core_suboptions[(i+1) % len(core_suboptions)].append(option)
            other_suboptions = []

        if len(other_suboptions) == 0:
            suboptions = core_suboptions
        else:
            suboptions = [other_suboptions] + core_suboptions  # DFS solves core first

        # construct corresponding subfamilies
        parent_info = family.collect_parent_info(self.quotient.specification,splitter)
        subfamilies = family.split(splitter,suboptions)
        for subfamily in subfamilies:
            subfamily.add_parent_info(parent_info)

        return subfamilies

    def synthesize_one(self, family):
        self.full_family = family
        families = [family]
        current_depth = self.INITIAL_TREE_DEPTH

        while True:
            while families:
                if self.resource_limit_reached():
                    break
                family_explored = False
                family = families.pop(-1)
                for explored_family in self.permissive_policies if self.cache_sat else [] + self.discarded_families if self.cache_unsat else []:
                    if family.family.isSubsetOf(explored_family.family):
                        family_explored = True
                        break
                if family_explored:
                    self.explore(family)
                    continue
                self.verify_family(family)
                self.check_result(family)
                if family.analysis_result.constraints_result.sat is False:
                    self.explore(family)
                    continue
                if family.analysis_result.constraints_result.sat is True:
                    self.explore(family)
                    implementable, tree = self.check_implementability(family)

                    # scheduler_csv = self.family_to_permissive_csv(family)
                    # dtcontrol_tree_helper = paynt.utils.dtnest_helper.run_dtcontrol(scheduler_csv, "csv", metadata=self.dtcontrol_metadata, preset="maxfreq")
                    # dtcontrol_tree = self.mdp_quotient.build_tree_helper_tree(dtcontrol_tree_helper)
                    # print(dtcontrol_tree.get_depth(), len(dtcontrol_tree.collect_nonterminals()))

                    # unfixed_states = stormpy.storage.BitVector(self.mdp_quotient.quotient_mdp.nr_states, False)
                    # selected_choices = self.mdp_quotient.get_selected_choices_from_tree_helper(unfixed_states, dtcontrol_tree)
                    # submdp = self.mdp_quotient.build_from_choice_mask(selected_choices)
                    # result = submdp.check_specification(self.quotient.specification)

                    # assert result.constraints_result.sat is True

                    if implementable:
                        print("sat implementable", tree)
                        return
                    else:
                        continue
                        
                # result = family.analysis_result.undecided_result()
                # if not result.primary_reused:
                #     scheduler = result.primary.result.scheduler

                #     new_scheduler = payntbind.synthesis.create_scheduler(self.quotient.quotient_mdp.nr_states)
                #     quotient_mdp_nci = self.quotient.quotient_mdp.nondeterministic_choice_indices.copy()
                #     state_to_choice = self.quotient.scheduler_to_state_to_choice(family.mdp, scheduler)
                #     # print(state_to_choice)
                #     for state in range(self.quotient.quotient_mdp.nr_states):
                #         quotient_choice = state_to_choice[state]
                #         if quotient_choice is None or not self.mdp_quotient.state_is_relevant_bv.get(state):
                #             payntbind.synthesis.set_dont_care_state_for_scheduler(new_scheduler, state, 0, False)
                #             index = 0
                #         else:
                #             index = quotient_choice - quotient_mdp_nci[state]
                #         scheduler_choice = stormpy.storage.SchedulerChoice(index)
                #         new_scheduler.set_choice(scheduler_choice, state)

                #     json_scheduler = json.loads(new_scheduler.to_json_str(self.quotient.quotient_mdp, skip_dont_care_states=True))
                #     json_str = json.dumps(json_scheduler, indent=4)

                #     dtcontrol_tree_helper = paynt.utils.dtnest_helper.run_dtcontrol(json_str, "storm.json")
                #     dtcontrol_tree = self.mdp_quotient.build_tree_helper_tree(dtcontrol_tree_helper)
                #     print(dtcontrol_tree.get_depth(), len(dtcontrol_tree.collect_nonterminals()), result.primary.value)

                # scheduler_csv = self.family_to_permissive_csv(family)
                # dtcontrol_tree_helper = paynt.utils.dtnest_helper.run_dtcontrol(scheduler_csv, "csv", metadata=self.dtcontrol_metadata, preset="maxfreq")
                # dtcontrol_tree = self.mdp_quotient.build_tree_helper_tree(dtcontrol_tree_helper)
                # unfixed_states = stormpy.storage.BitVector(self.mdp_quotient.quotient_mdp.nr_states, False)
                # selected_choices = self.mdp_quotient.get_selected_choices_from_tree_helper(unfixed_states, dtcontrol_tree)
                # submdp = self.mdp_quotient.build_from_choice_mask(selected_choices)
                # result = submdp.check_specification(self.quotient.specification)

                # print(family.analysis_result.undecided_result().secondary.value)
                # print(dtcontrol_tree.get_depth(), len(dtcontrol_tree.collect_nonterminals()), result.constraints_result.sat, result.constraints_result.results[0].value)

                # undecided, check implementability
                implementable, tree = self.check_implementability(family)
                
                if not implementable:
                    self.unimplementable_families.append(family)
                    continue
                elif tree is not None:
                    unfixed_states = stormpy.storage.BitVector(self.mdp_quotient.quotient_mdp.nr_states, False)
                    selected_choices = self.mdp_quotient.get_selected_choices_from_tree_helper(unfixed_states, tree)
                    submdp = self.mdp_quotient.build_from_choice_mask(selected_choices)
                    result = submdp.check_specification(self.quotient.specification)
                    if result.constraints_result.sat:
                        print("undecided implementable SAT", tree)
                        return

                # subfamilies = self.split_dt(family)
                subfamilies = self.split(family)
                families = families + subfamilies
                self.tree_scheduler_hole_selection = None

            current_depth += 1
            print(f"Increasing tree depth to {current_depth}")
            self.construct_tree_coloring(current_depth)

            for sat_family in self.permissive_policies:
                implementable, tree = self.check_implementability(sat_family)
                if implementable:
                    print("sat check implementable", tree)
                    return
                
            families = list(self.unimplementable_families)
            self.unimplementable_families = []


class DecisionTreeParetoFront(PermissiveTreeSynthesizer):

    optimal_result = None
    optimality_specification = None
    bounded_specification = None

    def __init__(self, quotient, mdp_quotient, eps_threshold=None, mc_reuse=True, cache_sat=False, cache_unsat=False):
        PermissiveTreeSynthesizer.INITIAL_TREE_DEPTH = 0
        super().__init__(quotient, mdp_quotient, eps_threshold, mc_reuse, cache_sat, cache_unsat)
        
        self.pareto_front = {}
        self.depth_colorings = {}
        self.depth_specifications = {}

        self.dtcontrol_metadata = self.create_dtcontrol_metadata()

        self.optimization_direction = "max" if not self.quotient.specification.constraints[0].minimizing else "min"


    def update_specification(self, quotient, spec_type, bound=None):
        if spec_type == "optimality":
            quotient.specification = self.optimality_specification.copy()
        elif spec_type == "bounded":
            quotient.specification = self.bounded_specification.copy()
            quotient.specification.constraints[0].threshold = bound
            quotient.specification.constraints[0].property.raw_formula.set_bound(quotient.specification.constraints[0].formula.comparison_type, stormpy.ExpressionManager().create_rational(stormpy.Rational(bound)))

    def compare_value(self, value, bound):
        if self.optimization_direction == "max":
            return value >= bound
        else:
            return value <= bound

    def initial_check(self):

        self.quotient.build(self.full_family)

        self.update_specification(self.mdp_quotient, "optimality")

        dtpaynt = paynt.synthesizer.decision_tree.SynthesizerDecisionTree(self.mdp_quotient)
        dtpaynt.synthesize_tree(0)
        self.pareto_front[0] = {"lb": dtpaynt.best_tree_value, "ub": dtpaynt.best_tree_value, "tree": dtpaynt.best_tree}

        scheduler = self.create_quotient_scheduler(self.full_family, self.optimal_result.result.scheduler)

        json_scheduler = json.loads(scheduler.to_json_str(self.quotient.quotient_mdp, skip_dont_care_states=True))
        json_str = json.dumps(json_scheduler, indent=4)

        dtcontrol_tree_helper = paynt.utils.dtnest_helper.run_dtcontrol(json_str, "storm.json")
        dtcontrol_tree = self.mdp_quotient.build_tree_helper_tree(dtcontrol_tree_helper)

        optimal_scheduler_depth = dtcontrol_tree.get_depth()

        for i in range(1, optimal_scheduler_depth):
            self.pareto_front[i] = {"lb": self.pareto_front[0]["lb"], "ub": self.optimal_result.value, "tree": dtpaynt.best_tree}
            # TODO we initialize all of the colorings here, but it might be inefficient
            self.mdp_quotient.reset_tree(i, False)
            self.depth_colorings[i] = {"coloring": self.mdp_quotient.coloring, "family": self.mdp_quotient.family.copy(), "dt": self.mdp_quotient.decision_tree.copy()}
        self.pareto_front[optimal_scheduler_depth] = {"lb": self.optimal_result.value, "ub": self.optimal_result.value, "tree": dtcontrol_tree}


        print(self.pareto_front)
        # for x in self.depth_colorings.values():
        #     print(x[0].getFamilyInfo())
        # exit()

    def tree_from_hole_selection(self, hole_selection):
        self.last_tree_assignment = self.mdp_quotient.family.assume_options_copy(hole_selection)
        tree = None
        dtmc = self.mdp_quotient.build_assignment(self.last_tree_assignment)
        res = dtmc.check_specification(self.quotient.specification)
        sat = res.constraints_result.sat
        if sat:
            tree = self.mdp_quotient.decision_tree
            tree.root.associate_assignment(self.last_tree_assignment)
        return tree, res

    def check_implementability_iterative(self, family):
        for depth in range(1, len(self.pareto_front)-1):
            if not self.compare_value(family.analysis_result.constraints_result.results[0].secondary.value, self.pareto_front[depth]["lb"]):
                break
            choices = self.quotient.coloring.selectCompatibleChoices(family.family)
            self.mdp_quotient.coloring = self.depth_colorings[depth]["coloring"]
            self.mdp_quotient.family = self.depth_colorings[depth]["family"]
            self.mdp_quotient.decision_tree = self.depth_colorings[depth]["dt"]
            self.mdp_quotient.coloring.selectCompatibleChoices(self.mdp_quotient.family.family)
            consistent,hole_selection = self.mdp_quotient.coloring.areChoicesConsistentPermissive(choices, self.mdp_quotient.family.family)

            # if implementable, check the returned tree
            if consistent:
                tree, res = self.tree_from_hole_selection(hole_selection)

                # maybe get rid of this?
                if tree is None:
                    continue

                return res.constraints_result.results[0].value, tree

        return None, None


    def synthesize_one(self, family):

        self.full_family = family
        families = [family]
        sat_not_implementable = []

        self.initial_check()

        current_depth = 1

        iter = 0

        while current_depth < len(self.pareto_front)-1 and self.resource_limit_reached() is False:

            self.update_specification(self.quotient, "bounded", self.pareto_front[current_depth]["lb"])

            while families:
                if self.resource_limit_reached():
                    break
                iter += 1
                if iter % 1000 == 0:
                    for key, value in self.pareto_front.items():
                        print(f"{key}: {round(value['lb'], 3)}\t{round(value['ub'], 3)}")
                family = families.pop(0)
                # family_explored = False
                # for explored_family in self.permissive_policies if self.cache_sat else [] + self.discarded_families if self.cache_unsat else []:
                #     if family.family.isSubsetOf(explored_family.family):
                #         family_explored = True
                #         break
                # if family_explored:
                #     self.explore(family)
                #     continue
                self.verify_family(family)
                self.check_result(family)

                family_result = family.analysis_result.constraints_result
                if family_result.sat is False:
                    self.explore(family)
                    continue

                if family_result.sat is True:
                    # This makes the method incomplete in theory
                    split_family = abs(family_result.results[0].primary.value - family_result.results[0].secondary.value) > 1e-4

                    # SMT lower bound update
                    value, tree = self.check_implementability_iterative(family)
                    if tree is not None:
                        tree_depth = tree.get_depth() if tree is not None else None
                        for d in range(tree_depth, len(self.pareto_front)-1):
                            if self.compare_value(value, self.pareto_front[d]["lb"]):
                                self.pareto_front[d]["lb"] = value
                                self.pareto_front[d]["tree"] = tree
                            else:
                                break
                        if tree_depth > current_depth:
                            sat_not_implementable.append(family)
                            split_family = False
                        elif split_family:
                            family_result.sat = None
                            family_result.results[0].sat = None
                            family_result.undecided_constraints = [0]
                            self.update_specification(self.quotient, "bounded", value)
                    else:
                        sat_not_implementable.append(family)
                        split_family = False

                    # dtControl lower bound update

                    if not family_result.results[0].primary_reused:
                        pass
                        # SMT scheduler map


                        # dtControl scheduler map
                        # scheduler = self.create_quotient_scheduler(family, family_result.results[0].primary.result.scheduler)
                        # json_scheduler = json.loads(scheduler.to_json_str(self.quotient.quotient_mdp, skip_dont_care_states=True))
                        # json_str = json.dumps(json_scheduler, indent=4)
                        # dtcontrol_tree_helper = paynt.utils.dtnest_helper.run_dtcontrol(json_str, "storm.json")
                        # dtcontrol_tree = self.mdp_quotient.build_tree_helper_tree(dtcontrol_tree_helper)
                        # tree_depth = dtcontrol_tree.get_depth()
                        # print(tree_depth, family_result.results[0].primary.value)
                        # for d in range(tree_depth, len(self.pareto_front)-1):
                        #     if self.compare_value(family_result.results[0].primary.value, self.pareto_front[d]["lb"]):
                        #         self.pareto_front[d]["lb"] = family_result.results[0].primary.value
                        #         self.pareto_front[d]["tree"] = dtcontrol_tree
                        #     else:
                        #         break

                    if not split_family:
                        continue
                
                # undecided
                subfamilies = self.split(family)
                families = families + subfamilies

            current_depth += 1
            families = sat_not_implementable
            sat_not_implementable = []
            print(f"Increasing tree depth to {current_depth}")
        
def print_profiler_stats(profiler):
    stats = pstats.Stats(profiler)
    NUM_LINES = 10

    print("cProfiler info:")
    stats.sort_stats('tottime').print_stats(NUM_LINES)

    print("percentage breakdown:")
    entries = [ (key,data[2]) for key,data in stats.stats.items()]
    entries = sorted(entries, key=lambda x : x[1], reverse=True)
    entries = entries[:NUM_LINES]
    for key,data in entries:
        module,line,method = key
        if module == "~":
            callee = method
        else:
            callee = f"{module}:{line}({method})"
        percentage = round(data / stats.total_tt * 100,1)
        percentage = str(percentage).ljust(4)
        print(f"{percentage} %  {callee}")



@click.command()
@click.argument('project', type=click.Path(exists=True))
@click.option("--sketch", default="sketch.templ", show_default=True,
    help="name of the sketch file in the project")
@click.option("--props", default="sketch.props", show_default=True,
    help="name of the properties file in the project")
@click.option("--pomdp-as-mdp", is_flag=True, default=False, help="treat POMDP as MDP by considering its underlying MDP")
@click.option("--eps-threshold", type=float, default=None, show_default=True, help="epsilon upperbound on the threshold")
@click.option("--relative-eps", type=float, default=None, show_default=True, help="relative epsilon threhshold computed from random policy")
@click.option("--mc-dont-reuse", is_flag=True, default=False, help="don't reuse model checking in subfamilies")
@click.option("--cache-sat", is_flag=True, default=False, help="cache SAT results")
@click.option("--cache-unsat", is_flag=True, default=False, help="cache UNSAT results")
@click.option("--dt", is_flag=True, default=False, help="synthesize DT")
@click.option("--dt-init-depth", type=int, default=0, show_default=True, help="initial depth for permissive DT synthesis")
@click.option("--timeout", default=300, show_default=True, help="timeout for the synthesis process")
@click.option("--pareto", is_flag=True, default=False, help="synthesize DT pareto front")
@click.option("--profiling", is_flag=True, default=False, help="run profiling")
def main(project, sketch, props, pomdp_as_mdp, eps_threshold, relative_eps, mc_dont_reuse, cache_sat, cache_unsat, dt, dt_init_depth, timeout, pareto, profiling):

    if profiling:
        profiler = cProfile.Profile()
        profiler.enable()

    assert eps_threshold is None or relative_eps is None, "only one of --eps-threshold and --relative-eps can be set"

    model_file = os.path.join(project, sketch)
    props_file = os.path.join(project, props)
    placeholder_quotient = paynt.parser.sketch.Sketch.load_sketch(model_file, props_file)

    explicit_quotient = placeholder_quotient.quotient_mdp
    specification = placeholder_quotient.specification

    family = paynt.family.family.Family()
    choice_to_hole_options = []

    if type(placeholder_quotient) == paynt.quotient.quotient.Quotient:

        quotient = placeholder_quotient
        family = quotient.family

    else:

        if isinstance(placeholder_quotient, paynt.quotient.mdp.MdpQuotient):

            vars, state_valuations = placeholder_quotient.get_state_valuations(explicit_quotient)
            for state in range(explicit_quotient.nr_states):
                nci = explicit_quotient.nondeterministic_choice_indices.copy()
                if explicit_quotient.get_nr_available_actions(state) > 1:
                    state_val = f"{[var+"="+str(state_valuations[state][i]) for i, var in enumerate(vars)]}"
                    family.add_hole(f"{state_val}", [explicit_quotient.choice_labeling.get_labels_of_choice(x) for x in range(nci[state], nci[state + 1])])
                    for action in range(explicit_quotient.get_nr_available_actions(state)):
                        choice_to_hole_options.append([(family.num_holes-1, action)])
                else:
                    choice_to_hole_options.append([])

        elif isinstance(placeholder_quotient, paynt.quotient.pomdp.PomdpQuotient) and not pomdp_as_mdp:

            family, choice_to_hole_options = placeholder_quotient.create_coloring()

        else:

            for state in range(explicit_quotient.nr_states):
                if explicit_quotient.get_nr_available_actions(state) > 1:
                    state_val = f"state_{state}"
                    family.add_hole(f"{state_val}", [str(x) for x in range(explicit_quotient.get_nr_available_actions(state))])
                    for action in range(explicit_quotient.get_nr_available_actions(state)):
                        choice_to_hole_options.append([(family.num_holes-1, action)])
                else:
                    choice_to_hole_options.append([])

        coloring = payntbind.synthesis.Coloring(family.family, explicit_quotient.nondeterministic_choice_indices, choice_to_hole_options)

        if placeholder_quotient.DONT_CARE_ACTION_LABEL in placeholder_quotient.action_labels:

            random_choices = placeholder_quotient.get_random_choices()
            submdp_random = placeholder_quotient.build_from_choice_mask(random_choices)
            mc_result_random = submdp_random.model_check_property(placeholder_quotient.get_property())
            random_result_value = mc_result_random.value

            all_choices = stormpy.storage.BitVector(explicit_quotient.nr_choices, True)
            full_mdp = placeholder_quotient.build_from_choice_mask(all_choices)
            full_mc_result = full_mdp.model_check_property(placeholder_quotient.get_property())
            opt_result_value = full_mc_result.value

            if relative_eps is not None:

                opt_random_diff = opt_result_value - random_result_value
                eps_optimum_threshold = opt_result_value - relative_eps * opt_random_diff

                specification.constraints[0].threshold = eps_optimum_threshold
                specification.constraints[0].property.raw_formula.set_bound(specification.constraints[0].formula.comparison_type, stormpy.ExpressionManager().create_rational(stormpy.Rational(eps_optimum_threshold)))

            elif pareto:

                DecisionTreeParetoFront.optimal_result = full_mc_result

                specification.constraints[0].threshold = random_result_value
                specification.constraints[0].property.raw_formula.set_bound(specification.constraints[0].formula.comparison_type, stormpy.ExpressionManager().create_rational(stormpy.Rational(random_result_value)))
                opt_property = stormpy.Property("", specification.constraints[0].formula.clone())

                paynt_opt_property = paynt.verification.property.construct_property(opt_property, 0, False)
                properties = [paynt_opt_property]

                DecisionTreeParetoFront.optimality_specification = paynt.verification.property.Specification(properties)
                DecisionTreeParetoFront.bounded_specification = specification.copy()


        quotient = paynt.quotient.quotient.Quotient(explicit_quotient, family, coloring, specification)
    
    
    print(f"number of schedulers: {family.size_or_order}")
    # print(f"epsilon optimum threshold: {eps_optimum_threshold}")

    if pareto:
        permissive_synthesizer = DecisionTreeParetoFront(quotient, placeholder_quotient, eps_threshold=eps_threshold, mc_reuse=not mc_dont_reuse, cache_sat=cache_sat, cache_unsat=cache_unsat)
    elif dt:
        PermissiveTreeSynthesizer.INITIAL_TREE_DEPTH = dt_init_depth
        permissive_synthesizer = PermissiveTreeSynthesizer(quotient, placeholder_quotient, eps_threshold=eps_threshold, mc_reuse=not mc_dont_reuse, cache_sat=cache_sat, cache_unsat=cache_unsat)
    else:
        permissive_synthesizer = PermissiveSynthesizer(quotient, eps_threshold=eps_threshold, mc_reuse=not mc_dont_reuse, cache_sat=cache_sat, cache_unsat=cache_unsat)

    permissive_synthesizer.run()

    print(len(permissive_synthesizer.permissive_policies), "permissive policies found")

    # print the safe subfamilies
    # permissive_synthesizer.print_schedulers()

    # print(f"Safe schedulers: {sum(f.size for f in permissive_synthesizer.permissive_policies)}/{family.size} ({round(sum(f.size for f in permissive_synthesizer.permissive_policies) / family.size * 100, 1)}%)")

    if profiling:
        profiler.disable()
        print_profiler_stats(profiler)


if __name__ == "__main__":
    main()