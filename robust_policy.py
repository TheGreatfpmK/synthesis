import paynt.models
import paynt.models.models
import paynt.quotient.pomdp
import paynt.synthesizer.statistic
import stormpy
import payntbind

import paynt.family.family
import paynt.synthesizer.synthesizer
import paynt.synthesizer.synthesizer_ar
import paynt.quotient.storm_pomdp_control

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

import cProfile, pstats


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

        # iter = 0
        self.stat.iterations_mdp = 0

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

            self.stat.iterations_mdp += synthesizer.stat.iterations_mdp

            if unsat_mdp_assignment is None:
                print("robust policy found")
                self.stat.synthesized_assignment = True
                return
            
            # unsat MDP was found
            unsat_mdp = self.quotient.build_assignment(unsat_mdp_assignment)
            policy_assignment = self.policy_coloring.getChoiceToAssignment()
            choice_to_hole_options = []
            for choice in range(unsat_mdp.model.nr_choices):
                quotient_choice = unsat_mdp.quotient_choice_map[choice]
                choice_to_hole_options.append(policy_assignment[quotient_choice])

            coloring = payntbind.synthesis.Coloring(policy_family.family, unsat_mdp.model.nondeterministic_choice_indices, choice_to_hole_options)
            quotient_container = paynt.quotient.quotient.Quotient(unsat_mdp.model, policy_family, coloring, self.quotient.specification) # negate here or no?

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
            # iter += 1

            # if iter % 10 == 0:
                # print(f"iter {iter}, progress {self.explored/self.policy_family.size}")

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
                self.stat.synthesized_assignment = True
                return
            
            # unsat MDP was found
            self.quotient.build(mdp_singleton_family)
            policy_assignment = self.policy_coloring.getChoiceToAssignment()
            choice_to_hole_options = []
            for choice in range(mdp_singleton_family.mdp.model.nr_choices):
                quotient_choice = mdp_singleton_family.mdp.quotient_choice_map[choice]
                choice_to_hole_options.append(policy_assignment[quotient_choice])

            coloring = payntbind.synthesis.Coloring(policy_family.family, mdp_singleton_family.mdp.model.nondeterministic_choice_indices, choice_to_hole_options)
            # quotient_container = paynt.quotient.quotient.Quotient(mdp_singleton_family.mdp.model, policy_family, coloring, self.quotient.specification.negate()) # negate here or no?
            quotient_container = paynt.quotient.quotient.Quotient(mdp_singleton_family.mdp.model, policy_family, coloring, self.quotient.specification) # negate here or no?

            conflict_generator = paynt.synthesizer.conflict_generator.dtmc.ConflictGeneratorDtmc(quotient_container)
            conflict_generator.initialize()
            requests = [(0, self.prop, None)]

            quotient_container.build(policy_family)
            model = quotient_container.build_assignment(policy_singleton_family)

            conflicts = conflict_generator.construct_conflicts(policy_family, policy_singleton_family, model, requests)
            pruned = smt_solver.exclude_conflicts(policy_family, policy_singleton_family, conflicts)

            # print(f"pruned {pruned} options ({pruned/policy_family.size}%)")
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
                # print(current_policy_family)
                # print(score_lists)
                # print(self.stat.iterations_mdp)
                self.stat.synthesized_assignment = True
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


    def robust_posmg(self, mdp_family):
        assignments = []
        # print(self.quotient.quotient_mdp)
        for mdp_hole_assignments in mdp_family.all_combinations():
            combination = list(mdp_hole_assignments)
            mdp_singleton_suboptions = [[option] for option in combination]
            mdp_singleton_family = mdp_family.assume_options_copy(mdp_singleton_suboptions)
            assignments.append(mdp_singleton_family)
        pomdps = [self.assignment_to_pomdp(assignment) for assignment in assignments]
        print(f"created {len(pomdps)} POMDPs")

        posmg_with_decision = payntbind.synthesis.createModelWithInitialDecision(pomdps)
        print(f"constructed union POSMG with {posmg_with_decision.nr_states} states and {posmg_with_decision.nr_choices} actions")

        posmg_specification = self.create_game_optimality_specification()
        # posmg_specification = self.create_game_feasibility_specification()
        posmg_quotient = paynt.quotient.posmg.PosmgQuotient(posmg_with_decision, posmg_specification)
        synthesizer = paynt.synthesizer.synthesizer.Synthesizer.choose_synthesizer(posmg_quotient, "ar", False)
        result = synthesizer.run()

        print(result)


    def assignment_to_mdp(self, assignment):
        mdp = self.quotient.build_assignment(assignment)
        goal_label = self.quotient.specification.constraints[0].get_target_label()
        new_state_labeling = mdp.model.labeling
        if "goal" != goal_label:
            new_state_labeling.add_label("goal")
            for state in range(mdp.model.nr_states):
                state_labels = new_state_labeling.get_labels_of_state(state)
                if goal_label in state_labels:
                    new_state_labeling.add_label_to_state("goal", state)
        components = stormpy.SparseModelComponents(transition_matrix=mdp.model.transition_matrix, state_labeling=new_state_labeling,
                                                   reward_models=mdp.model.reward_models)
        components.state_valuations = mdp.model.state_valuations
        components.choice_labeling = mdp.model.choice_labeling
        
        return stormpy.storage.SparseMdp(components)
    
    def create_game_optimality_specification(self, relative_error=0):
        optimality_formula_str = "<<0>> Pmax=? [ F \"goal\" ]"
        optimality_formula = stormpy.parse_properties_without_context(optimality_formula_str)[0]
        prop = paynt.verification.property.construct_property(optimality_formula, relative_error)
        properties = [prop]
        specification = paynt.verification.property.Specification(properties)
        return specification
    
    def create_game_feasibility_specification(self, relative_error=0):
        optimality_formula_str = "<<0>> P>=1 [ F \"goal\" ]"
        optimality_formula = stormpy.parse_properties_without_context(optimality_formula_str)[0]
        prop = paynt.verification.property.construct_property(optimality_formula, relative_error)
        properties = [prop]
        specification = paynt.verification.property.Specification(properties)
        return specification

    def get_worst_mdp(self, mdp_family):
        assignments = []
        # print(self.quotient.quotient_mdp)
        for mdp_hole_assignments in mdp_family.all_combinations():
            combination = list(mdp_hole_assignments)
            mdp_singleton_suboptions = [[option] for option in combination]
            mdp_singleton_family = mdp_family.assume_options_copy(mdp_singleton_suboptions)
            assignments.append(mdp_singleton_family)
        mdps = [self.assignment_to_mdp(assignment) for assignment in assignments]
        print(f"created {len(mdps)} MDPs")

        game_with_decision = payntbind.synthesis.createModelWithInitialDecision(mdps)
        print(f"constructed an SMG with {game_with_decision.nr_states} states and {game_with_decision.nr_choices} actions")

        optimality_specification = self.create_game_optimality_specification()
        smg = paynt.models.models.Smg(game_with_decision)
        result = smg.model_check_property(optimality_specification.optimality)
        print(result)


    def assignment_to_pomdp(self, assignment):
        mdp = self.quotient.build_assignment(assignment)
        goal_label = self.quotient.specification.constraints[0].get_target_label()
        new_state_labeling = mdp.model.labeling
        if "goal" != goal_label:
            new_state_labeling.add_label("goal")
            for state in range(mdp.model.nr_states):
                state_labels = new_state_labeling.get_labels_of_state(state)
                if goal_label in state_labels:
                    new_state_labeling.add_label_to_state("goal", state)
        components = stormpy.SparseModelComponents(transition_matrix=mdp.model.transition_matrix, state_labeling=new_state_labeling,
                                                   reward_models=mdp.model.reward_models)
        components.state_valuations = mdp.model.state_valuations
        components.choice_labeling = mdp.model.choice_labeling
        components.observability_classes = [mdp.quotient_state_map[state] for state in range(mdp.model.nr_states)]
        
        return stormpy.storage.SparsePomdp(components)
    

    def create_optimality_specification(self, relative_error=0):
        optimality_formula_str = "Pmax=? [ F \"goal\" ]"
        optimality_formula = stormpy.parse_properties_without_context(optimality_formula_str)[0]
        prop = paynt.verification.property.construct_property(optimality_formula, relative_error)
        properties = [prop]
        specification = paynt.verification.property.Specification(properties)
        return specification

        
    def average_union_pomdp(self, mdp_family, storm=False):
        assignments = []
        # print(self.quotient.quotient_mdp)
        for mdp_hole_assignments in mdp_family.all_combinations():
            combination = list(mdp_hole_assignments)
            mdp_singleton_suboptions = [[option] for option in combination]
            mdp_singleton_family = mdp_family.assume_options_copy(mdp_singleton_suboptions)
            assignments.append(mdp_singleton_family)
        pomdps = [self.assignment_to_pomdp(assignment) for assignment in assignments]
        print(f"created {len(pomdps)} POMDPs")

        union_pomdp = payntbind.synthesis.createModelUnion(pomdps)
        print(f"constructed union POMDP with {union_pomdp.nr_states} states and {union_pomdp.nr_choices} actions")

        pomdp_specification = self.create_optimality_specification()
        # paynt.quotient.pomdp.PomdpQuotient.initial_memory_size = 4
        union_pomdp_quotient = paynt.quotient.pomdp.PomdpQuotient(union_pomdp, pomdp_specification)

        storm_control = None
        if storm:
            storm_control = paynt.quotient.storm_pomdp_control.StormPOMDPControl()
            storm_control.set_options(get_storm_result=0)
        synthesizer = paynt.synthesizer.synthesizer.Synthesizer.choose_synthesizer(union_pomdp_quotient, "ar", True, storm_control)
        synthesizer.run()

    def get_iterations(self):
        iterations = 0
        if self.stat.iterations_mdp is not None:
            iterations += self.stat.iterations_mdp
        if self.stat.iterations_dtmc is not None:
            iterations += self.stat.iterations_dtmc
        if self.stat.iterations_game is not None:
            iterations += self.stat.iterations_game
        return iterations

    def run_robust(self, family=None):
        if family is None:
            family = self.quotient.family
        self.synthesis_timer = paynt.utils.timer.Timer()
        self.synthesis_timer.start()
        self.stat = paynt.synthesizer.statistic.Statistic(self)
        self.explored = 0
        self.stat.start(self.policy_family)

        if True:
            self.robust_cegis_policies_ar_mdps(family)
            # self.robust_cegis_policies_1by1_mdps(family)
            # self.robust_ar_policies_1by1_mdps(family)

            self.stat.job_type = "synthesis"
            self.stat.synthesis_timer.stop()
            self.stat.print()
            print(f"{self.stat.synthesized_assignment}, {round(self.stat.synthesis_timer.time, 2)}, {self.get_iterations()}, {int((self.explored / self.stat.family_size) * 100)}")
        else:
            pass
            # self.robust_posmg(family)


    def run_game_abstraction_heuristic(self, family):
        self.quotient.build(family)
        prop = self.quotient.specification.constraints[0]
        game_solver = self.quotient.build_game_abstraction_solver(prop)
        game_solver.solve_smg(family.selected_choices)
        game_value = game_solver.solution_value
        game_sat = prop.satisfies_threshold_within_precision(game_value)
        return game_value, game_sat


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


def family_selection(quotient):
    if False:
        pass
    else:
        return quotient.family


profiling = False

if profiling:
    profiler = cProfile.Profile()
    profiler.enable()

# robust_folder = "models/archive/atva24-policy-trees/"
robust_folder = "models/robust-mdps/"
if len(sys.argv) < 2:
    model_folder = os.path.join(robust_folder, 'obstacles-demo/')
else:
    model_folder = os.path.join(robust_folder, sys.argv[1])
model_file = os.path.join(model_folder, 'sketch.templ')
props_file = os.path.join(model_folder, 'sketch.props')
quotient = paynt.parser.sketch.Sketch.load_sketch(model_file, props_file)
assert isinstance(quotient, paynt.quotient.mdp_family.MdpFamilyQuotient)

family = family_selection(quotient)

robust_policy_synthesizer = RobustPolicySynthesizer(quotient)
game_abs_val, game_abs_sat = robust_policy_synthesizer.run_game_abstraction_heuristic(quotient.family)

print(f"{sys.argv[1]}, {quotient.quotient_mdp.nr_states}, {len(quotient.action_labels)}, {quotient.family.size}, {robust_policy_synthesizer.policy_family.size}, {quotient.specification.constraints[0].threshold}, , {game_abs_val}")

robust_policy_synthesizer.run_robust()
# robust_policy_synthesizer.average_union_pomdp(quotient.family)
# robust_policy_synthesizer.average_union_pomdp(quotient.family, storm=True)

if profiling:
    profiler.disable()
    print_profiler_stats(profiler)


