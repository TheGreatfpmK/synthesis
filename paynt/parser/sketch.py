import stormpy
import payntbind

from paynt.parser.prism_parser import PrismParser
from paynt.parser.pomdp_parser import PomdpParser

import paynt.quotient.models

import paynt.quotient.quotient
import paynt.quotient.pomdp
import paynt.quotient.decpomdp
import paynt.quotient.mdp_family
import paynt.quotient.pomdp_family
import paynt.verification.property

import logging
logger = logging.getLogger(__name__)

import os


def substitute_suffix(string, delimiter, replacer):
    '''Subsitute the suffix behind the last delimiter.'''
    output_string = string.split(delimiter)
    output_string[-1] = str(replacer)
    output_string = delimiter.join(output_string)
    return output_string

def make_rewards_action_based(model):
    tm = model.transition_matrix
    for name,reward_model in model.reward_models.items():
        assert not reward_model.has_transition_rewards, "Paynt does not support transition rewards"
        if not reward_model.has_state_rewards:
            continue
        logger.info("converting state rewards '{}' to state-action rewards".format(name))
        if reward_model.has_state_action_rewards:
            logger.info("state rewards will be added to existing state-action rewards".format(name))
            action_reward = reward_model.state_action_rewards.copy()
        else:
            action_reward = [0] * model.nr_choices

        for state in range(model.nr_states):
            state_reward = reward_model.get_state_reward(state)
            for action in range(tm.get_row_group_start(state),tm.get_row_group_end(state)):
                action_reward[action] += state_reward

        model.remove_reward_model(name)
        new_reward_model = stormpy.storage.SparseRewardModel(optional_state_action_reward_vector=action_reward)
        model.add_reward_model(name, new_reward_model)



class Sketch:


    @classmethod
    def load_sketch(cls, sketch_path, properties_path,
        export=None, relative_error=0, discount_factor=1):

        assert discount_factor>0 and discount_factor<=1, "discount factor must be in the interval (0,1]"

        prism = None
        explicit_quotient = None
        specification = None
        family = None
        coloring = None
        jani_unfolder = None
        decpomdp_manager = None
        obs_evaluator = None

        # check path
        if not os.path.isfile(sketch_path):
            raise ValueError(f"the sketch file {sketch_path} does not exist")
        logger.info(f"loading sketch from {sketch_path} ...")

        filetype = None
        try:
            logger.info(f"assuming sketch in PRISM format...")
            prism, explicit_quotient, specification, family, coloring, jani_unfolder, obs_evaluator = PrismParser.read_prism(
                        sketch_path, properties_path, relative_error, discount_factor)
            filetype = "prism"
        except SyntaxError:
            pass
        if filetype is None:
            try:
                logger.info(f"assuming sketch in DRN format...")
                explicit_quotient = PomdpParser.read_pomdp_drn(sketch_path)
                specification = PrismParser.parse_specification(properties_path, relative_error, discount_factor)
                filetype = "drn"
            except:
                pass
        if filetype is None:
            try:
                logger.info(f"assuming sketch in Cassandra format...")
                decpomdp_manager = payntbind.synthesis.parse_decpomdp(sketch_path)
                if decpomdp_manager is None:
                    raise SyntaxError
                print("paynt.quotient.pomdp.PomdpQuotient.dont_use_discount_transformation",paynt.quotient.pomdp.PomdpQuotient.dont_use_discount_transformation)
                if paynt.quotient.pomdp.PomdpQuotient.dont_use_discount_transformation:
                    explicit_quotient = decpomdp_manager.construct_pomdp()
                    optimality = paynt.verification.property.construct_reward_property(
                        decpomdp_manager.reward_model_name,
                        decpomdp_manager.reward_minimizing,
                        decpomdp_manager.target_label)
                    specification = paynt.verification.property.Specification([optimality])
                else:
                    logger.info("applying discount factor transformation...")
                    decpomdp_manager.apply_discount_factor_transformation()
                    explicit_quotient = decpomdp_manager.construct_pomdp()
                    optimality = paynt.verification.property.construct_reward_property(
                        decpomdp_manager.reward_model_name,
                        decpomdp_manager.reward_minimizing,
                        decpomdp_manager.discount_sink_label)
                    specification = paynt.verification.property.Specification([optimality])
                    

                filetype = "cassandra"
            except SyntaxError:
                pass

        assert filetype is not None, "unknow format of input file"
        logger.info("sketch parsing OK")

        if filetype=="prism" or filetype =="drn":
            assert specification is not None
            if discount_factor < 1:
                logger.info("applying discount factor transformation")
                assert specification.is_single_property and specification.all_properties()[0].reward, \
                    "non-trivial discount factor can only be used in combination with a single reward property"
                assert explicit_quotient.is_partially_observable, \
                    "non-trivial discount factor can only be used for POMDPs (for now...)"
                prop = specification.all_properties()[0]
                reward_name = prop.formula.reward_name
                target_label = str(prop.formula.subformula.subformula)
                subpomdp_builder = payntbind.synthesis.SubPomdpBuilder(explicit_quotient, reward_name, target_label)
                subpomdp_builder.set_discount_factor(discount_factor)
                initial_distribution = {explicit_quotient.initial_states[0] : 1}
                relevant_observations = stormpy.storage.BitVector(explicit_quotient.nr_observations,True)
                subpomdp_builder.set_relevant_observations(relevant_observations, initial_distribution)
                explicit_quotient = subpomdp_builder.restrict_pomdp(initial_distribution)
                logger.debug('WARNING: discount factor transformation has not been properly tested')
             
        paynt.quotient.models.MarkovChain.initialize(specification)
        paynt.verification.property.Property.initialize()
        
        make_rewards_action_based(explicit_quotient)
        logger.debug("constructed explicit quotient having {} states and {} actions".format(
            explicit_quotient.nr_states, explicit_quotient.nr_choices))

        specification.check()
        if specification.contains_until_properties() and filetype != "prism":
            logger.info("WARNING: using until formulae with non-PRISM inputs might lead to unexpected behaviour")
        specification.transform_until_to_eventually()
        logger.info(f"found the following specification {specification}")

        if export is not None:
            Sketch.export(export, sketch_path, jani_unfolder, explicit_quotient)
            logger.info("export OK, aborting...")
            exit(0)

        return Sketch.build_quotient_container(prism, jani_unfolder, explicit_quotient, family, coloring, specification, obs_evaluator, decpomdp_manager)

    
    @classmethod
    def export(cls, export, sketch_path, jani_unfolder, explicit_quotient):
        if export == "jani":
            assert jani_unfolder is not None, "jani unfolder was not used"
            output_path = substitute_suffix(sketch_path, '.', 'jani')
            jani_unfolder.write_jani(output_path)
        if export == "drn":
            output_path = substitute_suffix(sketch_path, '.', 'drn')
            stormpy.export_to_drn(explicit_quotient, output_path)
        if export == "pomdp":
            assert explicit_quotient.is_nondeterministic_model and explicit_quotient.is_partially_observable, \
                "cannot '--export pomdp' with non-POMDP sketches"
            output_path = substitute_suffix(sketch_path, '.', 'pomdp')
            property_path = substitute_suffix(sketch_path, '/', 'props.pomdp')
            PomdpParser.write_model_in_pomdp_solve_format(explicit_quotient, output_path, property_path)


    @classmethod
    def build_quotient_container(cls, prism, jani_unfolder, explicit_quotient, family, coloring, specification, obs_evaluator, decpomdp_manager):
        if jani_unfolder is not None:
            if prism.model_type == stormpy.storage.PrismModelType.DTMC:
                quotient_container = paynt.quotient.quotient.DtmcFamilyQuotient(explicit_quotient, family, coloring, specification)
            elif prism.model_type == stormpy.storage.PrismModelType.MDP:
                quotient_container = paynt.quotient.mdp_family.MdpFamilyQuotient(explicit_quotient, family, coloring, specification)
            elif prism.model_type == stormpy.storage.PrismModelType.POMDP:
                quotient_container = paynt.quotient.pomdp_family.PomdpFamilyQuotient(explicit_quotient, family, coloring, specification, obs_evaluator)
        else:
            assert explicit_quotient.is_nondeterministic_model
            if decpomdp_manager is not None and decpomdp_manager.num_agents > 1:
                quotient_container = paynt.quotient.decpomdp.DecPomdpQuotient(decpomdp_manager, specification)
            else:
                quotient_container = paynt.quotient.pomdp.PomdpQuotient(explicit_quotient, specification, decpomdp_manager)
        return quotient_container


