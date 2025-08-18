
import paynt
import payntbind
import stormpy

import paynt.parser.sketch
import paynt.synthesizer

import os

import click
import cProfile
import pstats



# class PermissiveSynthesizer:










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

    # permissive_synthesizer = PermissiveSynthesizer(quotient)

    # print(f"{sys.argv[1]}, {quotient.quotient_mdp.nr_states}, {len(quotient.action_labels)}, {quotient.family.size}, {robust_policy_synthesizer.policy_family.size}, {quotient.specification.constraints[0].threshold}, , {robust_policy_synthesizer.game_abs_val}")

    # permissive_synthesizer.run(synthesizer, timeout)

    if profiling:
        profiler.disable()
        print_profiler_stats(profiler)


if __name__ == "__main__":
    main()