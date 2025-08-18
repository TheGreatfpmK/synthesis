
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
    
    def __init__(self, quotient):
        super().__init__(quotient)
        
        self.permissive_policies = []

    def check_specification(self, family):
        ''' Check specification for mdp or smg based on self.quotient '''
        mdp = family.mdp

        if isinstance(self.quotient, paynt.quotient.posmg.PosmgQuotient):
            model = self.quotient.create_smg_from_mdp(mdp)
        else:
            model = mdp

        # check constraints
        admissible_assignment = None
        spec = self.quotient.specification
        if family.constraint_indices is None:
            family.constraint_indices = spec.all_constraint_indices()
        results = [None for _ in spec.constraints]
        for index in family.constraint_indices:
            constraint = spec.constraints[index]
            result = paynt.verification.property_result.MdpPropertyResult(constraint)
            results[index] = result

            # check primary direction
            result.primary = model.model_check_property(constraint)
            # print(f"primary: {result.primary.value}")
            if result.primary.sat is False:
                result.sat = False
                break

            result.primary_selection,_ = self.quotient.scheduler_is_consistent(mdp, constraint, result.primary.result)

            # primary direction is SAT: check secondary direction to see whether all SAT
            result.secondary = model.model_check_property(constraint, alt=True)
            # print(f"secondary: {result.secondary.value}, {result.secondary.sat}")
            if mdp.is_deterministic and result.primary.value != result.secondary.value:
                logger.warning("WARNING: model is deterministic but min<max")
            if result.secondary.sat:
                result.sat = True
                continue

            primary_selection,_ = self.quotient.scheduler_is_consistent(mdp, constraint, result.primary.result)
            secondary_selection,_ = self.quotient.scheduler_is_consistent(mdp, constraint, result.secondary.result)

            assert len(primary_selection) == len(secondary_selection)
            selection = [[] for _ in range(len(primary_selection))]
            for i in range(len(primary_selection)):
                selection[i] = primary_selection[i]
                for x in secondary_selection[i]:
                    if x not in selection[i]:
                        selection[i].append(x)
            result.primary_selection = selection

        spec_result = paynt.verification.property_result.MdpSpecificationResult()
        spec_result.constraints_result = paynt.verification.property_result.ConstraintsResult(results)

        family.analysis_result = spec_result

    def verify_family(self, family):
        self.quotient.build(family)

        # TODO include iteration_game in iteration? is it necessary?
        if isinstance(self.quotient, paynt.quotient.posmg.PosmgQuotient):
            self.stat.iteration_game(family.mdp.states)
        else:
            self.stat.iteration(family.mdp)

        self.check_specification(family)

    def check_result(self, family):
        result = family.analysis_result
        if result is None:
            return
        elif result.constraints_result.sat is False:
            return
        elif result.constraints_result.sat is True:
            print(f"permissive scheduler found: {family.size}")
            self.permissive_policies.append(family)

    def synthesize_one(self, family):
        families = [family]
        while families:
            if self.resource_limit_reached():
                break
            family = families.pop(-1)
            self.verify_family(family)
            self.check_result(family)
            if family.analysis_result.constraints_result.sat is False or family.analysis_result.constraints_result.sat is True:
                self.explore(family)
                continue
            # undecided
            subfamilies = self.quotient.split(family)
            families = families + subfamilies


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
@click.option("--timeout", default=300, show_default=True, help="timeout for the synthesis process")
@click.option("--profiling", is_flag=True, default=False, help="run profiling")
def main(project, sketch, props, timeout, profiling):

    if profiling:
        profiler = cProfile.Profile()
        profiler.enable()

    model_file = os.path.join(project, sketch)
    props_file = os.path.join(project, props)
    placeholder_quotient = paynt.parser.sketch.Sketch.load_sketch(model_file, props_file)

    explicit_quotient = placeholder_quotient.quotient_mdp
    specification = placeholder_quotient.specification

    family = paynt.family.family.Family()
    choice_to_hole_options = []
    for state in range(explicit_quotient.nr_states):
        family.add_hole(f"state_{state}", [x for x in range(explicit_quotient.get_nr_available_actions(state))])
        for action in range(explicit_quotient.get_nr_available_actions(state)):
            choice_to_hole_options.append([(state, action)])

    coloring = payntbind.synthesis.Coloring(family.family, explicit_quotient.nondeterministic_choice_indices, choice_to_hole_options)

    quotient = paynt.quotient.quotient.Quotient(explicit_quotient, family, coloring, specification)

    permissive_synthesizer = PermissiveSynthesizer(quotient)

    permissive_synthesizer.run()

    if profiling:
        profiler.disable()
        print_profiler_stats(profiler)


if __name__ == "__main__":
    main()