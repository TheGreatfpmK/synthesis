import logging
import multiprocessing as mp
import os
import stormpy

from .family import Family
from .helpers import safe_division
from ..profiler import Profiler, Timer
from .cegis import CEGISChecker

ONLY_CEGIS = True
ONLY_CEGAR = False
PRINT_STAGE_INFO = False

class CegisParallelismLoop(mp.Process, CEGISChecker):

    _ce_quality = False
    _ce_maxsat = False
    _logger = logging.getLogger(__name__)
    # static member of class (    # shared counter across all processes)
    shared_data = None
    stage_score_limit = 99999

    def __init__(self, iterations_cegis, formulae, family, families, counterexample_generator, relevant_holes,
                 input_has_optimality_property, optimality_setting, optimal_value, sketch):
        super().__init__()
        print("CONSTRUCTOR HAS BEEN CALLED")

        self.iterations_cegis = iterations_cegis
        print("HERE..." + str(formulae))
        # TODO: ERROR TypeError: cannot pickle 'stormpy.logic.logic.RewardOperator' object
        self.formulae = formulae
        self.stage_timer = Timer()
        # CE quality
        self.ce_maxsat, self.ce_zero, self.ce_global, self.ce_local = 0, 0, 0, 0
        self.ce_maxsat_timer, self.ce_zero_timer, self.ce_global_timer, self.ce_local_timer = \
            Timer(), Timer(), Timer(), Timer()
        self.family = family
        self.families = families
        self.counterexample_generator = counterexample_generator
        self.relevant_holes = relevant_holes
        self.input_has_optimality_property = input_has_optimality_property
        self._optimality_setting = optimality_setting
        self._optimal_value = optimal_value
        self.stage_switch_allowed = True
        self.stage_time_cegar, self.stage_pruned_cegar, self.stage_time_cegis, self.stage_pruned_cegis = 0, 0, 0, 0

        self.cegis_allocated_time_factor = 1.0
        # start with CEGAR
        self.stage_cegar = True
        self.cegis_allocated_time = 0
        self.stage_time_allocation_cegis = 0

        self.models_total = family.size
        self.stage_score = 0
        self.stage_start(request_stage_cegar=True)
        self.stage_step(family.size)

        self.sketch = sketch
        print("CONSTRUCTOR EXIT...")

    # def __str__(self) -> str:
    #     return "hello string..."

    # def __repr__(self):
    #     return (f'{self.__class__.__name__}('
    #             f'{self.iterations_cegis!r}, '
    #             # f'{self.formulae!r}, '
    #             # f'{self.stage_timer!r}, '
    #             # f'{self.ce_maxsat!r}, '
    #             # f'{self.ce_zero!r}, '
    #             # f'{self.ce_global!r}, '
    #             # f'{self.ce_local!r}, '
    #             # f'{self.ce_maxsat_timer!r}, '
    #             # f'{self.ce_zero_timer!r},'
    #             # f' {self.ce_global_timer!r}, '
    #             # f'{self.ce_local_timer!r}, '
    #             f'{self.iterations_cegis!r})')

    def run(self, ) -> bool:
        print("RUN METHOD HAS BEEN CALLED")
        print('Process ID: ', os.getpid())

        # process family members
        Profiler.start("is - pick DTMC")
        # TODO: mutex here...
        assignment = self.family.pick_member_with_exclude_all_holes()
        Profiler.stop()

        while assignment is not None:
            self.iterations_cegis += 1
            self._logger.debug(f"CEGIS: iteration {self.iterations_cegis}.")
            self._logger.debug(f"CEGIS: picked family member: {assignment}.")

            # collect indices of violated formulae
            violated_formulae_indices = []
            for formula_index in self.family.formulae_indices:
                # logger.debug(f"CEGIS: model checking DTMC against formula with index {formula_index}.")
                Profiler.start("is - DTMC model checking")
                Family.dtmc_checks_inc()
                sat, _ = self.family.analyze_member(formula_index)

                self._logger.info(f"FAMILY ANALYZE member {sat}")

                Profiler.stop()
                self._logger.debug(f"Formula {formula_index} is {'SAT' if sat else 'UNSAT'}")
                if not sat:
                    violated_formulae_indices.append(formula_index)
            if (not violated_formulae_indices or violated_formulae_indices == [len(self.formulae) - 1]) \
                    and self.input_has_optimality_property:
                self._check_optimal_property(self.family, assignment, self.counterexample_generator)
            elif not violated_formulae_indices:
                Profiler.add_ce_stats(self.counterexample_generator.stats)
                return True

            # some formulae UNSAT: construct counterexamples
            # logger.debug("CEGIS: preprocessing DTMC.")
            Profiler.start("_")
            self.counterexample_generator.prepare_dtmc(self.family.dtmc, self.family.dtmc_state_map)
            Profiler.stop()

            Profiler.start("is - constructing CE")
            conflicts = []
            for formula_index in violated_formulae_indices:
                # logger.debug(f"CEGIS: constructing CE for formula with index {formula_index}.")
                conflict_indices = self.counterexample_generator.construct_conflict(formula_index)
                # conflict = counterexample_generator.construct(formula_index, self.use_nontrivial_bounds)
                conflict_holes = [Family.hole_list[index] for index in conflict_indices]
                generalized_count = len(Family.hole_list) - len(conflict_holes)
                self._logger.debug(
                    f"CEGIS: found conflict involving {conflict_holes} (generalized {generalized_count} holes)."
                )
                conflicts.append(conflict_indices)

                # compare to maxsat, state exploration, naive hole exploration, global vs local bounds
                self.ce_quality_measure(
                    assignment, self.relevant_holes, self.counterexample_generator,
                    self.family.dtmc, self.family.dtmc_state_map, formula_index
                )

            # TODO: mutex here...
            # self.family.exclude_member(conflicts)
            Profiler.stop()

            # pick next member
            Profiler.start("is - pick DTMC")
            # TODO: mutex here...
            assignment = self.family.pick_member_with_exclude_all_holes()
            Profiler.stop()

            # record stage
            if self.stage_step(0) and not ONLY_CEGIS:
                # switch requested
                Profiler.add_ce_stats(self.counterexample_generator.stats)
                return None

        #
        # process family members
        # Profiler.start("is - pick DTMC")
        # # TODO: mutex here...
        # assignment = self.family.pick_member_with_exclude_all_holes()
        # Profiler.stop()
        #
        # while assignment is not None:
        #     self.iterations_cegis += 1
        #     self._logger.debug(f"CEGIS: iteration {self.iterations_cegis}.")
        #     self._logger.debug(f"CEGIS: picked family member: {assignment}.")
        #
        #     # collect indices of violated formulae
        #     violated_formulae_indices = []
        #     for formula_index in self.family.formulae_indices:
        #         # logger.debug(f"CEGIS: model checking DTMC against formula with index {formula_index}.")
        #         Profiler.start("is - DTMC model checking")
        #         Family.dtmc_checks_inc()
        #         sat, _ = self.family.analyze_member(formula_index)
        #         Profiler.stop()
        #         self._logger.debug(f"Formula {formula_index} is {'SAT' if sat else 'UNSAT'}")
        #         if not sat:
        #             violated_formulae_indices.append(formula_index)
        #     if (not violated_formulae_indices or violated_formulae_indices == [len(self.formulae) - 1]) \
        #             and self.input_has_optimality_property():
        #         self._check_optimal_property(self.family, assignment, self.counterexample_generator)
        #     elif not violated_formulae_indices:
        #         Profiler.add_ce_stats(self.counterexample_generator.stats)
        #         return True
        #
        #     # some formulae UNSAT: construct counterexamples
        #     # logger.debug("CEGIS: preprocessing DTMC.")
        #     Profiler.start("_")
        #     self.counterexample_generator.prepare_dtmc(self.family.dtmc, self.family.dtmc_state_map)
        #     Profiler.stop()
        #
        #     Profiler.start("is - constructing CE")
        #     conflicts = []
        #     for formula_index in violated_formulae_indices:
        #         # logger.debug(f"CEGIS: constructing CE for formula with index {formula_index}.")
        #         conflict_indices = self.counterexample_generator.construct_conflict(formula_index)
        #         # conflict = counterexample_generator.construct(formula_index, self.use_nontrivial_bounds)
        #         conflict_holes = [Family.hole_list[index] for index in conflict_indices]
        #         generalized_count = len(Family.hole_list) - len(conflict_holes)
        #         self._logger.debug(
        #             f"CEGIS: found conflict involving {conflict_holes} (generalized {generalized_count} holes)."
        #         )
        #         conflicts.append(conflict_indices)
        #
        #         # compare to maxsat, state exploration, naive hole exploration, global vs local bounds
        #         self.ce_quality_measure(
        #             assignment, self.relevant_holes, self.counterexample_generator,
        #             self.family.dtmc, self.family.dtmc_state_map, formula_index
        #         )
        #
        #     # TODO: mutex here...
        #     self.family.exclude_member(conflicts)
        #     Profiler.stop()
        #
        #     # pick next unique member
        #     Profiler.start("is - pick DTMC")
        #     # TODO: mutex here...
        #     assignment = self.family.pick_member_with_exclude_all_holes()
        #     Profiler.stop()
        #
        #     # record stage
        #     if self.stage_step(0) and not ONLY_CEGIS:
        #         # switch requested
        #         Profiler.add_ce_stats(self.counterexample_generator.stats)
        #         return None

    # TODO: this method is from integrated_checker...
    def _check_optimal_property(self, family_ref, assignment, cex_generator=None, optimal_value=None):

        if optimal_value is None:
            assert family_ref.dtmc is not None
            # Model checking of the optimality property
            result = stormpy.model_checking(family_ref.dtmc, self._optimality_setting.criterion)
            optimal_value = result.at(family_ref.dtmc.initial_states[0])

        # Check whether the improvement was achieved
        if self._optimality_setting.is_improvement(optimal_value, self._optimal_value):
            # Set the new values of the optimal attributes
            self._optimal_value = optimal_value
            self._optimal_assignment = assignment

            # Construct the violation property according newly found optimal value
            self._construct_violation_property(family_ref, cex_generator)

            self._logger.debug(f"Optimal value improved to: {self._optimal_value}")
            return True

    #    TODO: this method is from integrated_checker...
    def _construct_violation_property(self, family_ref, cex_generator=None):
        vp_index = len(self.formulae) - 1  # Compute the index of the violation property

        # Construct new violation property with respect to the currently optimal value
        vp = self._optimality_setting.get_violation_property(
            self._optimal_value,
            lambda x: self.sketch.expression_manager.create_rational(stormpy.Rational(x)),
        )

        # Update the attributes of the family according to the new optimal values
        # For each family we need to update theirs formulae and formulae indices to check
        for family in self.families + [family_ref]:
            # Replace the last violation property by newly one
            family.formulae[vp_index] = vp.raw_formula
            # When the violation property is not checking, we have to add its index
            if vp_index not in family.formulae_indices:
                family.formulae_indices.append(vp_index)
                family.model_check_formula(vp_index)
                family.bounds[vp_index] = Family.quotient_container().latest_result.result

        # Change the value of threshold of the violation formulae within constructed quotient MDP
        Family.set_thresholds(Family.get_thresholds()[:-1] + [vp.raw_formula.threshold])

        # Update counter-example generator for violation property
        if cex_generator is not None:
            cex_generator.replace_formula_threshold(
                vp_index, vp.raw_formula.threshold_expr.evaluate_as_double(), family_ref.bounds[vp_index]
            )
            # Family.global_cex_generator.replace_formula_threshold(
            #     vp_index, vp.raw_formula.threshold_expr.evaluate_as_double(), family_ref.bounds[vp_index]
            # )

    #    TODO: this method is from integrated_checker...
    def ce_quality_measure(
            self, assignments, relevant_holes, counterexample_generator, dtmc, dtmc_state_map, formula_idx
    ):
        if not self._ce_quality:
            return
        self.statistic.timer.stop()
        self.stage_timer.stop()

        # maxsat
        self.ce_maxsat_timer.start()
        instance = self.build_instance(assignments)
        if self._ce_maxsat:
            _, conflict_maxsat = self._verifier.naive_check(instance, all_conflicts=True)
            conflict_maxsat = conflict_maxsat.pop() if conflict_maxsat else []
            conflict_maxsat = [hole for hole in conflict_maxsat if hole in relevant_holes]
            self.ce_maxsat += safe_division(len(conflict_maxsat), len(relevant_holes))
        self.ce_maxsat_timer.stop()

        # zero
        self.ce_zero_timer.start()
        counterexample_generator.prepare_dtmc(dtmc, dtmc_state_map)
        conflict_zero = counterexample_generator.construct_conflict(formula_idx, use_bounds=False)
        self.ce_zero += safe_division(len(conflict_zero), len(relevant_holes))
        self.ce_zero_timer.stop()

        # global
        # self.ce_global_timer.start()
        # Family.global_cex_generator.prepare_dtmc(dtmc, dtmc_state_map)
        # conflict_global = Family.global_cex_generator.construct_conflict(formula_idx, use_bounds=True)
        # self.ce_global += safe_division(len(conflict_global), len(relevant_holes))
        # self.ce_global_timer.stop()

        # local
        self.ce_local_timer.start()
        counterexample_generator.prepare_dtmc(dtmc, dtmc_state_map)
        conflict_local = counterexample_generator.construct_conflict(formula_idx, use_bounds=True)
        self.ce_local += safe_division(len(conflict_local), len(relevant_holes))
        self.ce_local_timer.stop()

        # resume timers
        self.stage_timer.start()
        self.statistic.timer.start()

    def stage_start(self, request_stage_cegar):
        self.stage_cegar = request_stage_cegar
        if ONLY_CEGAR:
            # disallow return to CEGIS
            self.stage_switch_allowed = False
        self.stage_timer.reset()
        self.stage_timer.start()

    def stage_step(self, models_pruned):
        """Performs a stage step, returns True if the method switch took place"""

        # if the method switch is prohibited, we do not care about stats
        if not self.stage_switch_allowed:
            return False

        # record pruned models
        self.stage_pruned_cegar += models_pruned / self.models_total if self.stage_cegar else 0
        self.stage_pruned_cegis += models_pruned / self.models_total if not self.stage_cegar else 0

        # allow cegis another stage step if some time remains
        if not self.stage_cegar and self.stage_timer.read() < self.cegis_allocated_time:
            return False

        # stage is finished: record time
        self.stage_timer.stop()
        current_time = self.stage_timer.read()
        if self.stage_cegar:
            # cegar stage over: allocate time for cegis and switch
            self.stage_time_cegar += current_time
            self.cegis_allocated_time = current_time * self.cegis_allocated_time_factor
            self.stage_start(request_stage_cegar=False)
            return True

        # cegis stage over
        self.stage_time_cegis += current_time

        self._logger.error(str(self.stage_time_cegar))
        self._logger.error(str(self.stage_time_cegis))

        # calculate average success rate, update stage score
        success_rate_cegar = self.stage_pruned_cegar / self.stage_time_cegar
        success_rate_cegis = self.stage_pruned_cegis / self.stage_time_cegis
        if success_rate_cegar > success_rate_cegis:
            # cegar wins the stage
            self.stage_score += 1
            if self.stage_score >= self.stage_score_limit:
                # cegar wins the synthesis
                # print("> only cegar")
                self.stage_switch_allowed = False
                # switch back to cegar
                self.stage_start(request_stage_cegar=True)
                return True
        elif success_rate_cegar < success_rate_cegis:
            # cegis wins the stage
            self.stage_score -= 1
            if self.stage_score <= -self.stage_score_limit:
                # cegar wins the synthesis
                # print("> only cegis")
                self.stage_switch_allowed = False
                # no need to switch
                return False

        # neither method prevails: adjust cegis time allocation factor
        if self.stage_pruned_cegar == 0 or self.stage_pruned_cegis == 0:
            cegar_dominance = 1
        else:
            cegar_dominance = success_rate_cegar / success_rate_cegis
        cegis_dominance = 1 / cegar_dominance
        self.stage_time_allocation_cegis = cegis_dominance

        # stage log
        if PRINT_STAGE_INFO:
            print("> ", end="")
            print(
                f"{success_rate_cegar:.2e} \\\\ {success_rate_cegis:.2e} = {cegis_dominance:.1e} ({self.stage_score})"
            )

        # switch back to cegar
        self.stage_start(request_stage_cegar=True)
        return True

    # ----- CE quality ----- #

    # def construct_global_cex_generator(self, family):
    #     self.statistic.timer.stop()
    #     self.stage_timer.stop()

    #     if self.ce_quality_compute:
    #         Family.global_cex_generator = stormpy.synthesis.SynthesisCounterexample(
    #             family.mdp, len(Family.hole_list), family.state_to_hole_indices, self.formulae, family.bounds
    #         )

    #     self.stage_timer.start()
    #     self.statistic.timer.start()
