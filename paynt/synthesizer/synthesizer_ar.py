from .synthesizer import Synthesizer

import paynt

class SynthesizerAR(Synthesizer):

    @property
    def method_name(self):
        return "AR"

    
    def verify_family(self, family):
        self.quotient.build(family)
        self.stat.iteration_mdp(family.mdp.states)
        res = family.mdp.check_specification(
            self.quotient.specification, constraint_indices = family.constraint_indices, short_evaluation = True)
        if res.improving_assignment == "any":
            res.improving_assignment = family
        #print(res)
        #exit()
        family.analysis_result = res
        

    
    def update_optimum(self, family):
        """
        :return (1) family feasibility (True/False/None)
        :return (2) new satisfying assignment (or None)
        """
        ia = family.analysis_result.improving_assignment
        if family.analysis_result.improving_value is not None:
            self.quotient.specification.optimality.update_optimum(family.analysis_result.improving_value)
            if isinstance(self.quotient, paynt.quotient.quotient_pomdp.POMDPQuotientContainer):
                self.stat.new_fsc_found(family.analysis_result.improving_value, ia, self.quotient.policy_size(ia))


    def synthesize_assignment(self, family):
        # return self.synthesize_assignment_experimental(family)
        self.quotient.discarded = 0

        satisfying_assignment = None
        families = [family]

        while families:

            family = families.pop(-1)
            #print(family.size)

            self.verify_family(family)
            self.update_optimum(family)
            
            if self.multi_mdp:
                #print(family.analysis_result.constraints_result)
                if family.analysis_result.constraints_result.sat == False:
                    self.explore(family)
                    continue
                sat = False
                if family.analysis_result.constraints_result.sat:
                    sat = True
                elif len(family.analysis_result.constraints_result.undecided_constraints) == 1:
                    undecided_ind = family.analysis_result.constraints_result.undecided_constraints[0]
                    if self.quotient.specification.constraints[undecided_ind].maximizing:
                        if family.analysis_result.constraints_result.results[undecided_ind].primary.value >= self.quotient.specification.constraints[undecided_ind].threshold:
                            sat = True
                    else:
                        if family.analysis_result.constraints_result.results[undecided_ind].primary.value <= self.quotient.specification.constraints[undecided_ind].threshold:
                            sat = True

                if sat:
                    print("Satisfiable!")
                    controllers = 1
                    for state in range(family.mdp.states):
                        controllers *= family.mdp.model.get_nr_available_actions(state)
                    double_check_res = self.quotient.double_check_assignment_multi(family.pick_any())
                    print(f"Time: {round(self.stat.synthesis_time.read(),3)}s\nFamily size: {controllers}\nAchieved values (one random FSC): {double_check_res.constraints_result if double_check_res else False}\nIterations: {self.stat.iterations_mdp}")
                    self.explore(family)
                    print(family)
                    #continue
                    exit()
                

            if family.analysis_result.improving_assignment is not None:
                satisfying_assignment = family.analysis_result.improving_assignment
            if family.analysis_result.can_improve == False:
                self.explore(family)
                continue

            # undecided
            if self.multi_mdp:
                subfamilies = self.quotient.split_multi_mdp(family, Synthesizer.incomplete_search)
            else:
                subfamilies = self.quotient.split(family, Synthesizer.incomplete_search)
            families = families + subfamilies

        return satisfying_assignment

    def synthesize_families(self, family):
        assert not self.quotient.specification.has_optimality
        self.quotient.discarded = 0

        satisfying_families = []
        families = [family]

        while families:

            family = families.pop(-1)

            self.verify_family(family)
            self.update_optimum(family)
            if family.analysis_result.improving_assignment is not None:
                satisfying_families.append(family)
                # print("found shield of size ", family.size)
            if family.analysis_result.can_improve == False:
                self.explore(family)
                continue

            # undecided
            subfamilies = self.quotient.split(family, Synthesizer.incomplete_search)
            families = families + subfamilies

        return satisfying_families


    def family_value(self, family):
        ur = family.analysis_result.undecided_result()
        value = ur.primary.value
        # we pick family with maximum value
        if ur.minimizing:
            value *= -1
        return value
    
    
    def synthesize_assignment_experimental(self, family):

        self.quotient.discarded = 0

        satisfying_assignment = None
        families = [family]
        while families:

            # analyze all families, keep optimal solution
            for family in families:
                if family.analysis_result is not None:
                    continue
                self.verify_family(family)
                self.update_optimum(family)
                if family.analysis_result.improving_assignment is not None:
                    satisfying_assignment = family.analysis_result.improving_assignment
            
            # analyze families once more and keep undecided ones
            undecided_families = []
            for family in families:
                family.analysis_result.evaluate()
                if family.analysis_result.can_improve == False:
                    self.explore(family)
                else:
                    undecided_families.append(family)
            if not undecided_families:
                break
            
            # sort families
            undecided_families = sorted(undecided_families, key=lambda f: self.family_value(f), reverse=True)
            # print([self.family_value(f) for f in undecided_families])

            # split family with the best value
            family = undecided_families[0]
            subfamilies = self.quotient.split(family, Synthesizer.incomplete_search)
            families = subfamilies + undecided_families[1:]
                

        return satisfying_assignment


