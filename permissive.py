
import paynt
import payntbind
import stormpy

import paynt.parser.sketch
import paynt.synthesizer.synthesizer

import os

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

            # print(f"secondary: {result.secondary.value}")
            if mdp.is_deterministic and abs(result.primary.value - result.secondary.value) > 1e-4:
                logger.warning(f"WARNING: model is deterministic but min < max: {result.primary.value} {result.secondary.value}")
            if result.secondary.sat:
                # only count permissive schedulers that are not overly conservative as SAT
                if self.overapp_threshold is None or result.primary.value >= self.overapp_threshold:
                    result.sat = True
                    continue

            # discard overly conservative schedulers
            if self.overapp_threshold is not None and result.secondary.value < self.overapp_threshold:
                result.sat = False
                break

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
            if family.analysis_result.constraints_result.sat is False or family.analysis_result.constraints_result.sat is True:
                self.explore(family)
                continue
            # undecided
            subfamilies = self.quotient.split(family)
            families = families + subfamilies


    def print_schedulers(self):
        for i, family in enumerate(self.permissive_policies):
            print(f"Permissive scheduler {i}: {family}")


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
@click.option("--timeout", default=300, show_default=True, help="timeout for the synthesis process")
@click.option("--profiling", is_flag=True, default=False, help="run profiling")
def main(project, sketch, props, pomdp_as_mdp, eps_threshold, relative_eps, mc_dont_reuse, cache_sat, cache_unsat, timeout, profiling):

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

        if placeholder_quotient.DONT_CARE_ACTION_LABEL in placeholder_quotient.action_labels and relative_eps is not None:
            random_choices = placeholder_quotient.get_random_choices()
            submdp_random = placeholder_quotient.build_from_choice_mask(random_choices)
            mc_result_random = submdp_random.model_check_property(placeholder_quotient.get_property())
            random_result_value = mc_result_random.value

            all_choices = stormpy.storage.BitVector(explicit_quotient.nr_choices, True)
            full_mdp = placeholder_quotient.build_from_choice_mask(all_choices)
            full_mc_result = full_mdp.model_check_property(placeholder_quotient.get_property())
            opt_result_value = full_mc_result.value

            opt_random_diff = opt_result_value - random_result_value
            eps_optimum_threshold = opt_result_value - relative_eps * opt_random_diff

            specification.constraints[0].threshold = eps_optimum_threshold
            specification.constraints[0].property.raw_formula.set_bound(specification.constraints[0].formula.comparison_type, stormpy.ExpressionManager().create_rational(stormpy.Rational(eps_optimum_threshold)))

        quotient = paynt.quotient.quotient.Quotient(explicit_quotient, family, coloring, specification)
    
    
    print(f"number of schedulers: {family.size_or_order}")

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