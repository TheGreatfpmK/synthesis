import stormpy

from paynt.verification.property import *
from paynt.verification.property_result import *

import logging
logger = logging.getLogger(__name__)

class MarkovChain:

    # options for the construction of chains
    builder_options = None
    # model checking environment (method & precision)
    environment = None

    @classmethod
    def initialize(cls, specification):
        # builder options
        formulae = specification.stormpy_formulae()
        cls.builder_options = stormpy.BuilderOptions(formulae)
        cls.builder_options.set_build_with_choice_origins(True)
        cls.builder_options.set_build_state_valuations(True)
        cls.builder_options.set_add_overlapping_guards_label()
        cls.builder_options.set_build_observation_valuations(True)
    
        # model checking environment
        cls.environment = stormpy.Environment()
        se = cls.environment.solver_environment
        
        stormpy.synthesis.set_precision_native(se.native_solver_environment, Property.mc_precision)
        stormpy.synthesis.set_precision_minmax(se.minmax_solver_environment, Property.mc_precision)

        se.set_linear_equation_solver_type(stormpy.EquationSolverType.native)
        # se.set_linear_equation_solver_type(stormpy.EquationSolverType.gmmxx)
        # se.set_linear_equation_solver_type(stormpy.EquationSolverType.eigen)

        # se.minmax_solver_environment.method = stormpy.MinMaxMethod.policy_iteration
        se.minmax_solver_environment.method = stormpy.MinMaxMethod.value_iteration
        # se.minmax_solver_environment.method = stormpy.MinMaxMethod.sound_value_iteration
        # se.minmax_solver_environment.method = stormpy.MinMaxMethod.interval_iteration
        # se.minmax_solver_environment.method = stormpy.MinMaxMethod.optimistic_value_iteration
        # se.minmax_solver_environment.method = stormpy.MinMaxMethod.topological

    @classmethod
    def assert_no_overlapping_guards(cls, model):
        if model.labeling.contains_label("overlap_guards"):
            assert model.labeling.get_states("overlap_guards").number_of_set_bits() == 0
    
    @classmethod
    def from_prism(cls, prism):
        
        assert prism.model_type in [stormpy.storage.PrismModelType.MDP, stormpy.storage.PrismModelType.POMDP]
        # TODO why do we disable choice labels here?
        MarkovChain.builder_options.set_build_choice_labels(True)
        model = stormpy.build_sparse_model_with_options(prism, MarkovChain.builder_options)
        MarkovChain.builder_options.set_build_choice_labels(False)
        MarkovChain.assert_no_overlapping_guards(model)
        return model

    
    def __init__(self, model, quotient_container, quotient_state_map, quotient_choice_map):
        MarkovChain.assert_no_overlapping_guards(model)
        if len(model.initial_states) > 1:
            logger.warning("WARNING: obtained model with multiple initial states")
        
        self.model = model
        self.quotient_container = quotient_container
        self.quotient_choice_map = quotient_choice_map
        self.quotient_state_map = quotient_state_map

        # identify simple holes
        design_space = quotient_container.design_space
        hole_to_states = [0 for hole in design_space]
        for state in range(self.states):
            for hole in quotient_container.coloring.state_to_holes[self.quotient_state_map[state]]:
                hole_to_states[hole] += 1
        self.hole_simple = [hole_to_states[hole] <= 1 for hole in design_space.hole_indices]

        self.analysis_hints = None
    
    @property
    def states(self):
        return self.model.nr_states

    @property
    def choices(self):
        return self.model.nr_choices

    @property
    def is_dtmc(self):
        return self.model.nr_choices == self.model.nr_states

    @property
    def initial_state(self):
        return self.model.initial_states[0]

    def model_check_formula(self, formula):
        if not self.is_dtmc:
            return stormpy.synthesis.verify_mdp(self.environment,self.model,formula,True)
        return stormpy.model_checking(
            self.model, formula, only_initial_states=False,
            extract_scheduler=(not self.is_dtmc),
            environment=self.environment
        )

    def model_check_formula_hint(self, formula, hint):
        raise RuntimeError("model checking with hints is not fully supported")
        stormpy.synthesis.set_loglevel_off()
        task = stormpy.core.CheckTask(formula, only_initial_states=False)
        task.set_produce_schedulers(produce_schedulers=True)
        result = stormpy.synthesis.model_check_with_hint(self.model, task, self.environment, hint)
        return result

    def model_check_property(self, prop, alt = False):
        direction = "prim" if not alt else "seco"
        # get hint
        hint = None
        if self.analysis_hints is not None:
            hint_prim,hint_seco = self.analysis_hints[prop]
            hint = hint_prim if not alt else hint_seco
            # hint = self.analysis_hints[prop]

        formula = prop.formula if not alt else prop.formula_alt
        if hint is None:
            result = self.model_check_formula(formula)
        else:
            result = self.model_check_formula_hint(formula, hint)
        
        value = result.at(self.initial_state)

        return PropertyResult(prop, result, value)

    
    def check_constraint(self, constraint):
        ''' to be overridden '''
        return None

    def check_optimality(self, optimality):
        ''' to be overridden '''
        return None

    def check_constraints(self, constraints, constraint_indices, short_evaluation):
        results = [None for constraint in constraints]
        for index in constraint_indices:
            constraint = constraints[index]
            result = self.check_constraint(constraint)
            results[index] = result
            if short_evaluation and result.sat == False:
                break
        return ConstraintsResult(results)

    def check_specification(self, specification, constraint_indices = None, short_evaluation = False):
        '''
        Check specification.
        :param specification containing constraints and optimality
        :param constraint_indices a selection of property indices to investigate (default: all)
        :param short_evaluation if set to True, then evaluation terminates as soon as one constraint violated
        '''
        if constraint_indices is None:
            constraint_indices = specification.all_constraint_indices()
        constraints_result = self.check_constraints(specification.constraints, constraint_indices, short_evaluation)
        optimality_result = None
        if specification.has_optimality and not (short_evaluation and constraints_result.sat == False):
            optimality_result = self.check_optimality(specification.optimality)
        return constraints_result, optimality_result


class DTMC(MarkovChain):

    def check_constraint(self, constraint):
        return self.model_check_property(constraint)

    def check_optimality(self, optimality):
        return self.model_check_property(optimality)

    def check_specification(self, specification, constraint_indices = None, short_evaluation = False):
        constraints_result, optimality_result = super().check_specification(specification,constraint_indices,short_evaluation)
        return SpecificationResult(constraints_result, optimality_result)


class MDP(MarkovChain):

    # whether the secondary direction will be explored if primary is not enough
    compute_secondary_direction = False

    def __init__(self, model, quotient_container, quotient_state_map, quotient_choice_map, design_space):
        super().__init__(model, quotient_container, quotient_state_map, quotient_choice_map)

        self.design_space = design_space
        self.analysis_hints = None
        self.quotient_to_restricted_action_map = None


    def check_constraint(self, prop):

        result = MdpPropertyResult(prop)

        # check primary direction
        result.primary = self.model_check_property(prop, alt = False)
        
        # no need to check secondary direction if primary direction yields UNSAT
        if not result.primary.sat:
            result.sat = False
            return result

        # primary direction is SAT
        # check if the primary scheduler is consistent
        result.primary_selection,result.primary_choice_values,result.primary_expected_visits,result.primay_scores,consistent = \
            self.quotient_container.scheduler_consistent(self, prop, result.primary.result)

        # regardless of whether it is consistent or not, we compute secondary direction to show that all SAT
        result.secondary = self.model_check_property(prop, alt = True)
        if self.is_dtmc and result.primary.value != result.secondary.value:
            logger.warning("WARNING: model is deterministic but min<max")

        if result.secondary.sat:
            result.sat = True
        return result


    def check_optimality(self, prop):
        # check primary direction
        primary = self.model_check_property(prop, alt = False)

        if not primary.improves_optimum:
            # OPT <= LB
            return MdpOptimalityResult(prop, primary, None, None, None, False, None, None, None, None)

        # LB < OPT
        # check if LB is tight
        selection,choice_values,expected_visits,scores,consistent = self.quotient_container.scheduler_consistent(self, prop, primary.result)
        if consistent:
            # LB is tight and LB < OPT
            scheduler_assignment = self.design_space.copy()
            scheduler_assignment.assume_options(selection)
            improving_assignment, improving_value = self.quotient_container.double_check_assignment(scheduler_assignment)
            return MdpOptimalityResult(prop, primary, None, improving_assignment, improving_value, False, selection, choice_values, expected_visits, scores)

        if not MDP.compute_secondary_direction:
            return MdpOptimalityResult(prop, primary, None, None, None, True, selection, choice_values, expected_visits, scores)

        # UB might improve the optimum
        secondary = self.model_check_property(prop, alt = True)

        if not secondary.improves_optimum:
            # LB < OPT < UB :  T < LB < OPT < UB (can improve) or LB < T < OPT < UB (cannot improve)
            can_improve = primary.sat
            return MdpOptimalityResult(prop, primary, secondary, None, None, can_improve, selection, choice_values, expected_visits, scores)

        # LB < UB < OPT
        # this family definitely improves the optimum
        assignment = self.design_space.pick_any()
        improving_assignment, improving_value = self.quotient_container.double_check_assignment(assignment)
        # either LB < T, LB < UB < OPT (can improve) or T < LB < UB < OPT (cannot improve)
        can_improve = primary.sat
        return MdpOptimalityResult(prop, primary, secondary, improving_assignment, improving_value, can_improve, selection, choice_values, expected_visits, scores)

    def check_specification(self, specification, constraint_indices = None, short_evaluation = False):
        constraints_result, optimality_result = super().check_specification(specification,constraint_indices,short_evaluation)
        return MdpSpecificationResult(constraints_result, optimality_result)
