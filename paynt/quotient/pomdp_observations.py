import stormpy
import payntbind

import logging
logger = logging.getLogger(__name__)


class PomdpObservationClass:

    def __init__(self, pomdp):
        self.pomdp_observations = payntbind.synthesis.PomdpObservations(pomdp)
        self.pomdp = pomdp
        logger.info("Observations test")

    def test(self):
        print(self.pomdp)
        print(self.pomdp_observations.underlying_mdp)
        print(self.pomdp.observations)

        # build POMDP from underlying mdp + observation classes
        # test finite belief MDP test
        # create some practice POMDPs