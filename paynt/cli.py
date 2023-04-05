from . import version

from .parser.sketch import Sketch
from .quotient.quotient_pomdp import POMDPQuotientContainer

from .synthesizer.synthesizer import Synthesizer
from .synthesizer.synthesizer_onebyone import SynthesizerOneByOne
from .synthesizer.synthesizer_ar import SynthesizerAR
from .synthesizer.synthesizer_cegis import SynthesizerCEGIS
from .synthesizer.synthesizer_hybrid import SynthesizerHybrid
from .synthesizer.synthesizer_pomdp import SynthesizerPOMDP
from .synthesizer.synthesizer_multicore_ar import SynthesizerMultiCoreAR

from .quotient.storm_pomdp_control import StormPOMDPControl

from .utils.alpha_vector_analysis import AlphaVectorAnalyzer

from .utils.storm_parallel import ParallelControl
# TODO remove?
from multiprocessing import Manager
from multiprocessing.managers import BaseManager

import click
import sys
import os
import cProfile, pstats

import logging
logger = logging.getLogger(__name__)


def setup_logger(log_path = None):
    ''' Setup routine for logging. '''
    
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # root.setLevel(logging.INFO)

    # formatter = logging.Formatter('%(asctime)s %(threadName)s - %(name)s - %(levelname)s - %(message)s')
    formatter = logging.Formatter('%(asctime)s - %(filename)s - %(message)s')

    handlers = []
    if log_path is not None:
        fh = logging.FileHandler(log_path)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        handlers.append(fh)
    sh = logging.StreamHandler(sys.stdout)
    handlers.append(sh)
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(formatter)
    for h in handlers:
        root.addHandler(h)
    return handlers


@click.command()
@click.option("--project", required=True, type=click.Path(exists=True),
    help="project path")
@click.option("--sketch", default="sketch.templ", show_default=True,
    help="name of the sketch file in the project")
@click.option("--props", default="sketch.props", show_default=True,
    help="name of the properties file in the project")
@click.option("--constants", default="", help="constant assignment string")
@click.option("--relative-error", type=click.FLOAT, default="0", show_default=True,
    help="relative error for optimal synthesis")

@click.option("--filetype",
    type=click.Choice(['prism', 'drn', 'cassandra']),
    default="prism", show_default=True,
    help="input file format")
@click.option("--export",
    type=click.Choice(['drn', 'pomdp']),
    help="export the model to *.drn/*.pomdp and abort")

@click.option("--method",
    type=click.Choice(['onebyone', 'ar', 'cegis', 'hybrid', 'ar_multicore']),
    default="ar", show_default=True,
    help="synthesis method"
    )

@click.option("--incomplete-search", is_flag=True, default=False,
    help="use incomplete search during synthesis")

@click.option("--fsc-synthesis", is_flag=True, default=False,
    help="enable incremental synthesis of FSCs for a POMDP")
@click.option("--pomdp-memory-size", default=1, show_default=True,
    help="implicit memory size for POMDP FSCs")
@click.option("--posterior-aware", is_flag=True, default=False,
    help="unfold MDP taking posterior observation of into account")
@click.option("--fsc-export-result", is_flag=True, default=False,
    help="export the input POMDP as well as the (labeled) optimal DTMC into a .drn format")

@click.option("--storm-pomdp", is_flag=True, default=False,
    help="enable running storm analysis for POMDPs to enhance FSC synthesis (supports AR only for now!)")
@click.option(
    "--storm-options",
    default="cutoff",
    type=click.Choice(["cutoff", "clip2", "clip4", "small", "refine", "overapp", "2mil", "5mil", "10mil", "20mil", "30mil", "50mil"]),
    show_default=True,
    help="run Storm using pre-defined settings and use the result to enhance PAYNT. Can only be used together with --storm-pomdp flag")
@click.option("--iterative-storm", nargs=3, type=int, show_default=True, default=None,
    help="runs the iterative PAYNT/Storm integration. Arguments timeout, paynt_timeout, storm_timeout. Can only be used together with --storm-pomdp flag")
@click.option("--get-storm-result", default=None, type=int,
    help="runs PAYNT for given amount of seconds and returns Storm result using FSC at cutoff. If time is 0 returns pure Storm result. Can only be used together with --storm-pomdp flag")
@click.option("--prune-storm", is_flag=True, default=False,
    help="only explore the main family suggested by Storm in each iteration. Can only be used together with --storm-pomdp flag. Can only be used together with --storm-pomdp flag")
@click.option("--use-storm-cutoffs", is_flag=True, default=False,
    help="if set the storm randomized scheduler cutoffs are used during the prioritization of families. Can only be used together with --storm-pomdp flag. Can only be used together with --storm-pomdp flag")
@click.option(
    "--unfold-strategy-storm",
    default="storm",
    type=click.Choice(["storm", "paynt", "cutoff"]),
    show_default=True,
    help="specify memory unfold strategy. Can only be used together with --storm-pomdp flag")

#@click.option("--storm-parallel", is_flag=True, default=False,
#    help="run storm analysis in parallel (can only be used together with --storm-pomdp-analysis flag)")

@click.option(
    "--ce-generator",
    default="storm",
    type=click.Choice(["storm", "switss", "mdp"]),
    show_default=True,
    help="counterexample generator",
)
@click.option("--pomcp", is_flag=True, default=False,
    help="run POMCP")
@click.option("--profiling", is_flag=True, default=False,
    help="run profiling")

@click.option("--alpha-vector-export", type=click.Path(), default=None,
    help="path to file where alpha vectors should be exported to")
@click.option("--alpha-vector-analysis", type=click.Path(), default=None,
    help="computes the value of the strategy encoded as a set of alpha vectors")

def paynt(
        project, sketch, props, constants, relative_error,
        filetype, export,
        method,
        incomplete_search,
        fsc_synthesis, pomdp_memory_size, posterior_aware,
        fsc_export_result,
        storm_pomdp, iterative_storm, get_storm_result, storm_options, prune_storm,
        use_storm_cutoffs, unfold_strategy_storm,
        ce_generator,
        pomcp,
        profiling,
        alpha_vector_export, alpha_vector_analysis
):
    logger.info("This is Paynt version {}.".format(version()))

    # set CLI parameters
    Synthesizer.incomplete_search = incomplete_search
    SynthesizerCEGIS.conflict_generator_type = ce_generator
    POMDPQuotientContainer.initial_memory_size = pomdp_memory_size
    POMDPQuotientContainer.export_optimal_result = fsc_export_result
    POMDPQuotientContainer.posterior_aware = posterior_aware
    POMDPQuotientContainer.alpha_vector_export = alpha_vector_export

    # check paths of input files
    sketch_path = os.path.join(project, sketch)
    properties_path = os.path.join(project, props)
    if not os.path.isfile(sketch_path):
        raise ValueError(f"the sketch file {sketch_path} does not exist")
    if not filetype=="cassandra" and not os.path.isfile(properties_path):
        raise ValueError(f"the properties file {properties_path} does not exist")

    quotient = Sketch.load_sketch(sketch_path, filetype, export,
        properties_path, constants, relative_error)

    if storm_pomdp:
        storm_control = StormPOMDPControl()
        storm_control.storm_options = storm_options
        if get_storm_result is not None:
            storm_control.get_result = get_storm_result
        if iterative_storm is not None:
            storm_control.iteration_timeout, storm_control.paynt_timeout, storm_control.storm_timeout = iterative_storm
        storm_control.use_cutoffs = use_storm_cutoffs
        storm_control.unfold_strategy_storm = unfold_strategy_storm
    else:
        storm_control = None

    if pomcp:
        from paynt.simulation.pomcp import POMCP
        if not profiling:
            POMCP(quotient).run()
        else:
            with cProfile.Profile() as pr:
                POMCP(quotient).run()
            stats = pr.create_stats()
            print(stats)
            pstats.Stats(pr).sort_stats('tottime').print_stats(10)
        exit()
        
    # choose the synthesis method and run the corresponding synthesizer
    if isinstance(quotient, POMDPQuotientContainer) and fsc_synthesis:
        synthesizer = SynthesizerPOMDP(quotient, method, storm_control)
    elif method == "onebyone":
        synthesizer = SynthesizerOneByOne(quotient)
    elif method == "ar":
        synthesizer = SynthesizerAR(quotient)
    elif method == "cegis":
        synthesizer = SynthesizerCEGIS(quotient)
    elif method == "hybrid":
        synthesizer = SynthesizerHybrid(quotient)
    elif method == "ar_multicore":
        synthesizer = SynthesizerMultiCoreAR(quotient)
    else:
        pass

    if storm_pomdp:
        if prune_storm:
            synthesizer.incomplete_exploration = True
        if unfold_strategy_storm == "paynt":
            synthesizer.unfold_storm = False
        elif unfold_strategy_storm == "cutoff":
            synthesizer.unfold_cutoff = True

    if alpha_vector_analysis:
        analyzer = AlphaVectorAnalyzer(synthesizer, alpha_vector_analysis)
        analyzer.analyse()
        return

    if not profiling:
        synthesizer.run()
    else:
        with cProfile.Profile() as pr:
            synthesizer.run()
        stats = pr.create_stats()
        print(stats)
        pstats.Stats(pr).sort_stats('tottime').print_stats(10)


def main():
    setup_logger()
    paynt()


if __name__ == "__main__":
    main()
