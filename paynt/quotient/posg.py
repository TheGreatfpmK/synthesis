import stormpy
import payntbind

import paynt.quotient.quotient
import paynt.quotient.pomdp
import paynt.verification.property

import logging
logger = logging.getLogger(__name__)


class PosgQuotient(paynt.quotient.quotient.Quotient):

    # label associated with states of Player 1
    PLAYER_1_STATE_LABEL = "__player_1_state__"

    
    def __init__(self, quotient_mdp, specification):
        super().__init__(quotient_mdp = quotient_mdp, specification = specification)

        # TODO Antonin
        self.coloring = None
        self.family = None
        self.design_space = None

        pomdp = self.quotient_mdp


        game_manager = payntbind.synthesis.StochasticGame(pomdp)
        my_game = game_manager.build_game()

        # print(my_game.get_state_player_indications())
        # for state in range(my_game.nr_states):
        #     print(my_game.labels_state(state))

        formula_str = "<<1>> Pmax=? [ F \"goal\" ]"
        formulas = stormpy.parse_properties(formula_str)

        result = stormpy.model_checking(my_game, formulas[0], extract_scheduler=True, environment=paynt.verification.property.Property.environment)

        print(result)

        game_manager.check_game(my_game)

        # print(type(pomdp), dir(pomdp))
        # print(dir(pomdp.labeling))
        # print(pomdp.labeling.get_states("__player_1_state__"))

        exit()
