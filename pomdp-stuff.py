import paynt
import payntbind
import stormpy

import paynt.parser.sketch
from paynt.quotient.pomdp import PomdpQuotient

import os
import json
import sys

import click
import cProfile
import pstats

import logging
import time
logger = logging.getLogger(__name__)

def setup_logger(log_path = None):
    ''' Setup routine for logging. '''

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # root.setLevel(logging.INFO)

    # formatter = logging.Formatter('%(asctime)s %(threadName)s - %(name)s - %(levelname)s - %(message)s')
    formatter = logging.Formatter('%(asctime)s - %(filename)s:%(lineno)d - %(message)s')

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
@click.argument('project', type=click.Path(exists=True))
@click.option("--sketch", default="sketch.templ", show_default=True,
    help="name of the sketch file in the project")
@click.option("--props", default="sketch.props", show_default=True,
    help="name of the properties file in the project")
def main(project, sketch, props):

    model_file = os.path.join(project, sketch)
    props_file = os.path.join(project, props)
    quotient = paynt.parser.sketch.Sketch.load_sketch(model_file, props_file)

    assert quotient.pomdp is not None, "POMDP on the input expected"

    pomdp = quotient.pomdp

    print(f"Input POMDP has {pomdp.nr_states} states, {pomdp.nr_observations} observations, {pomdp.nr_choices} choices and {pomdp.nr_transitions} transitions.")

    belief_support_unfolder = payntbind.synthesis.BeliefSupportUnfolder(pomdp)
    belief_support_unfolder.unfold_belief_support_mdp()
    unfolded_mdp = belief_support_unfolder.belief_support_mdp()

    print(unfolded_mdp)


if __name__ == "__main__":
    # setup_logger()
    main()