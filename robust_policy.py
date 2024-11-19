import paynt.synthesizer.statistic
import stormpy
import payntbind

import paynt.family.family
import paynt.synthesizer.synthesizer
import paynt.synthesizer.synthesizer_ar

import paynt.quotient.quotient
import paynt.verification.property_result
from paynt.verification.property import Property
import paynt.utils.timer

import paynt.family.smt
import paynt.synthesizer.conflict_generator.dtmc
import paynt.synthesizer.conflict_generator.mdp
import paynt.parser.sketch
import paynt.quotient.mdp_family

import os
import sys


class RobustPolicySynthesizer(paynt.synthesizer.synthesizer.Synthesizer):

    def __init__(self, quotient):
        self.quotient = quotient
        self.prop = self.quotient.specification.constraints[0]
        self.create_policy_coloring()

    def create_policy_coloring(self):
        quotient_mdp = self.quotient.quotient_mdp
        family = paynt.family.family.Family()
        choice_to_hole_options = [[] for choice in range(quotient_mdp.nr_choices)]

        for state in range(quotient_mdp.nr_states):
            state_actions = self.quotient.state_to_actions[state]
            if len(state_actions) < 2:
                continue

            hole = family.num_holes
            name = f'state_{state}'
            option_labels = [self.quotient.action_labels[action] for action in state_actions]
            family.add_hole(name, option_labels)

            for action_index, action in enumerate(state_actions):
                for choice in self.quotient.state_action_choices[state][action]:
                    choice_to_hole_options[choice].append((hole,action_index))

        coloring = payntbind.synthesis.Coloring(family.family, quotient_mdp.nondeterministic_choice_indices, choice_to_hole_options)
        self.policy_family = family
        self.policy_coloring = coloring

    def build_model_from_families(self, mdp_family, policy_family):
        choices_mdp = self.quotient.coloring.selectCompatibleChoices(mdp_family.family)
        choices_policy = self.policy_coloring.selectCompatibleChoices(policy_family.family)
        choices = choices_mdp.__and__(choices_policy)
        return self.quotient.build_from_choice_mask(choices)
    
    def scheduler_selection_for_coloring(self, mdp, scheduler, coloring):
        assert scheduler.memoryless and scheduler.deterministic
        state_to_choice = self.quotient.scheduler_to_state_to_choice(mdp, scheduler)
        choices = self.quotient.state_to_choice_to_choices(state_to_choice)
        hole_selection = coloring.collectHoleOptions(choices)
        return hole_selection


    def robust_cegis_policies_ar_mdps(self, mdp_family):
        policy_family = self.policy_family.copy()
        smt_solver = paynt.family.smt.SmtSolver(policy_family)

        policy_singleton_family = smt_solver.pick_assignment(policy_family)

        iter = 0

        # CEG over policies
        while policy_singleton_family is not None:
            # AR over MDPs for given policy
            policy_model = self.build_model_from_families(mdp_family, policy_singleton_family)
            mdp_assignment = self.quotient.coloring.getChoiceToAssignment()
            choice_to_hole_options = []
            for choice in range(policy_model.model.nr_choices):
                quotient_choice = policy_model.quotient_choice_map[choice]
                choice_to_hole_options.append(mdp_assignment[quotient_choice])

            coloring = payntbind.synthesis.Coloring(mdp_family.family, policy_model.model.nondeterministic_choice_indices, choice_to_hole_options)
            quotient_container = paynt.quotient.quotient.Quotient(policy_model.model, mdp_family, coloring, self.quotient.specification.negate())

            synthesizer = paynt.synthesizer.synthesizer_ar.SynthesizerAR(quotient_container)

            unsat_mdp_assignment = synthesizer.synthesize(print_stats=False)

            if unsat_mdp_assignment is None:
                print("robust policy found")
                return
            
            # unsat MDP was found
            unsat_mdp = self.quotient.build_assignment(unsat_mdp_assignment)
            policy_assignment = self.policy_coloring.getChoiceToAssignment()
            choice_to_hole_options = []
            for choice in range(unsat_mdp.model.nr_choices):
                quotient_choice = unsat_mdp.quotient_choice_map[choice]
                choice_to_hole_options.append(policy_assignment[quotient_choice])

            coloring = payntbind.synthesis.Coloring(policy_family.family, unsat_mdp.model.nondeterministic_choice_indices, choice_to_hole_options)
            quotient_container = paynt.quotient.quotient.Quotient(unsat_mdp.model, policy_family, coloring, self.quotient.specification)

            conflict_generator = paynt.synthesizer.conflict_generator.dtmc.ConflictGeneratorDtmc(quotient_container)
            conflict_generator.initialize()
            requests = [(0, self.prop, None)]

            quotient_container.build(policy_family)
            model = quotient_container.build_assignment(policy_singleton_family)

            conflicts = conflict_generator.construct_conflicts(policy_family, policy_singleton_family, model, requests)
            pruned = smt_solver.exclude_conflicts(policy_family, policy_singleton_family, conflicts)

            self.explored += pruned
            
            # construct next assignment
            policy_singleton_family = smt_solver.pick_assignment(policy_family)
            iter += 1

            if iter % 2 == 0:
                print(f"iter {iter}, progress {self.explored/self.policy_family.size}")

        print("no robust policy found")




    def robust_cegis_policies_1by1_mdps(self, mdp_family):
        policy_family = self.policy_family.copy()
        smt_solver = paynt.family.smt.SmtSolver(policy_family)

        policy_singleton_family = smt_solver.pick_assignment(policy_family)

        # CEG over policies
        while policy_singleton_family is not None:
            # 1by1 checking of MDPs for given policy
            for mdp_hole_assignments in mdp_family.all_combinations():
                combination = list(mdp_hole_assignments)
                mdp_singleton_suboptions = [[option] for option in combination]
                mdp_singleton_family = mdp_family.assume_options_copy(mdp_singleton_suboptions)
                model = self.build_model_from_families(mdp_singleton_family, policy_singleton_family)
                assert model.is_deterministic, "expected DTMC"

                model.model = self.quotient.mdp_to_dtmc(model.model)
                dtmc_result = model.model_check_property(self.prop)
                self.stat.iteration(model)

                if not dtmc_result.sat:
                    break
            else:
                print("robust policy found")
                return
            
            # unsat MDP was found
            self.quotient.build(mdp_singleton_family)
            policy_assignment = self.policy_coloring.getChoiceToAssignment()
            choice_to_hole_options = []
            for choice in range(mdp_singleton_family.mdp.model.nr_choices):
                quotient_choice = mdp_singleton_family.mdp.quotient_choice_map[choice]
                choice_to_hole_options.append(policy_assignment[quotient_choice])

            coloring = payntbind.synthesis.Coloring(policy_family.family, mdp_singleton_family.mdp.model.nondeterministic_choice_indices, choice_to_hole_options)
            quotient_container = paynt.quotient.quotient.Quotient(mdp_singleton_family.mdp.model, policy_family, coloring, self.quotient.specification)

            conflict_generator = paynt.synthesizer.conflict_generator.dtmc.ConflictGeneratorDtmc(quotient_container)
            conflict_generator.initialize()
            requests = [(0, self.prop, None)]

            quotient_container.build(policy_family)
            model = quotient_container.build_assignment(policy_singleton_family)

            conflicts = conflict_generator.construct_conflicts(policy_family, policy_singleton_family, model, requests)
            pruned = smt_solver.exclude_conflicts(policy_family, policy_singleton_family, conflicts)

            self.explored += pruned
            
            # construct next assignment
            policy_singleton_family = smt_solver.pick_assignment(policy_family)

        print("no robust policy found")
                    


    def robust_ar_policies_1by1_mdps(self, mdp_family):
        policy_family = self.policy_family.copy()
        policy_family_stack = [policy_family]

        # AR over policies
        while policy_family_stack:
            current_policy_family = policy_family_stack.pop(-1)

            score_lists = {hole:[] for hole in range(current_policy_family.num_holes) if current_policy_family.hole_num_options(hole) > 1}

            # 1by1 checking of MDPs
            for mdp_hole_assignments in mdp_family.all_combinations():
                combination = list(mdp_hole_assignments)
                mdp_singleton_suboptions = [[option] for option in combination]
                mdp_singleton_family = mdp_family.assume_options_copy(mdp_singleton_suboptions)
                model = self.build_model_from_families(mdp_singleton_family, current_policy_family)

                primary_result = model.model_check_property(self.prop)
                self.stat.iteration(model)

                # we found unsat MDP for the current policy family
                if primary_result.sat == False:
                    splitter = None
                    break

                scheduler_selection = self.scheduler_selection_for_coloring(model, primary_result.result.scheduler, self.policy_coloring)

                for hole, score in score_lists.items():
                    for choice in scheduler_selection[hole]:
                        if choice not in score:
                            score.append(choice)

                scores = {hole:len(score_list) for hole, score_list in score_lists.items()}

                splitters = self.quotient.holes_with_max_score(scores)
                splitter = splitters[0]

                # refinement as soon as the first inconsistency is found
                if scores[splitter] > 1:
                    break
            else:
                # all MDPs share the same satisfying policy (i.e. robust policy was found)
                print("robust policy found")
                return

            # unsat MDP was found
            if splitter is None:
                # print(f"explored family of size {current_policy_family.size/self.policy_family.size}")
                self.explore(current_policy_family)
                continue

            used_options = score_lists[splitter]
            core_suboptions = [[option] for option in used_options]
            other_suboptions = [option for option in current_policy_family.hole_options(splitter) if option not in used_options]
            new_family = current_policy_family.copy()
            if len(other_suboptions) == 0:
                suboptions = core_suboptions
            else:
                suboptions = [other_suboptions] + core_suboptions  # DFS solves core first


            subfamilies = []
            current_policy_family.splitter = splitter
            # parent_info = current_policy_family.collect_parent_info(self.quotient.specification)
            for suboption in suboptions:
                subfamily = new_family.subholes(splitter, suboption)
                # subfamily.add_parent_info(parent_info)
                subfamily.hole_set_options(splitter, suboption)
                subfamilies.append(subfamily)

            policy_family_stack = policy_family_stack + subfamilies

        print("no robust policy found")

        
    def average_union_pomdp(self, mdp_family):
        pass

    def run_robust(self):
        self.synthesis_timer = paynt.utils.timer.Timer()
        self.synthesis_timer.start()
        self.stat = paynt.synthesizer.statistic.Statistic(self)
        self.explored = 0
        self.stat.start(self.policy_family)

        robust_policy_synthesizer.robust_cegis_policies_ar_mdps(self.quotient.family)
        # robust_policy_synthesizer.robust_cegis_policies_1by1_mdps(self.quotient.family)
        # robust_policy_synthesizer.robust_ar_policies_1by1_mdps(self.quotient.family)
        # robust_policy_synthesizer.average_union_pomdp(self.quotient.family)


atva_folder = "models/archive/atva24-policy-trees/"
if len(sys.argv) < 2:
    model_folder = os.path.join(atva_folder, 'obstacles-demo/')
else:
    model_folder = os.path.join(atva_folder, sys.argv[1])
model_file = os.path.join(model_folder, 'sketch.templ')
props_file = os.path.join(model_folder, 'sketch.props')
quotient = paynt.parser.sketch.Sketch.load_sketch(model_file, props_file)
assert isinstance(quotient, paynt.quotient.mdp_family.MdpFamilyQuotient)

robust_policy_synthesizer = RobustPolicySynthesizer(quotient)

robust_policy_synthesizer.run_robust()
