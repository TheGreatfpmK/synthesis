#include "ConditionalUnfolder.h"

#include "src/synthesis/translation/componentTranslations.h"
#include "storm/exceptions/NotSupportedException.h"
#include <queue>

namespace synthesis {

    template<typename ValueType>
    ConditionalUnfolder<ValueType>::ConditionalUnfolder(
        storm::models::sparse::Mdp<ValueType> const& mdp,
        storm::logic::ConditionalFormula const& formula
    ) : mdp(mdp), formula(formula) {}


    template<typename ValueType>
    storm::storage::BitVector ConditionalUnfolder<ValueType>::getConditionalStatesForOriginalModel() const {
        // NOTE THIS ONLY WORKS FOR CONDITIONAL FORMULAS OF THE FORM ( F label | F label )
        return this->mdp.getStates(this->getConditionalLabel());
    }

    template<typename ValueType>
    storm::storage::BitVector ConditionalUnfolder<ValueType>::getTargetStatesForOriginalModel() const {
        return this->mdp.getStates(this->getTargetLabel());
    }

    template<typename ValueType>
    std::string ConditionalUnfolder<ValueType>::getConditionalLabel() const {
        return this->formula.getConditionFormula().asEventuallyFormula().getSubformula().asAtomicLabelFormula().getLabel();
    }

    template<typename ValueType>
    std::string ConditionalUnfolder<ValueType>::getTargetLabel() const {
        return this->formula.getSubformula().asEventuallyFormula().getSubformula().asAtomicLabelFormula().getLabel();
    }

    template<typename ValueType>
    storm::storage::Scheduler<ValueType> ConditionalUnfolder<ValueType>::map_scheduler_to_quotient(
        storm::storage::SparseMatrix<ValueType> const& modelMatrix,
        std::vector<uint64_t> const& quotient_state_map,
        std::vector<uint64_t> const& quotient_choice_map,
        storm::storage::Scheduler<ValueType> const& scheduler,
        std::vector<uint64_t> const& reachTargetChoices,
        std::vector<uint64_t> const& reachConditionChoices
    ) const {

        storm::storage::BitVector targetStates = this->getTargetStatesForOriginalModel();
        storm::storage::BitVector conditionStates = this->getConditionalStatesForOriginalModel();

        auto const& transitionMatrix = this->mdp.getTransitionMatrix();

        // create scheduler with memory structure
        storm::storage::MemoryStructure::TransitionMatrix memoryTransitions(3, std::vector<boost::optional<storm::storage::BitVector>>(3, boost::none));
        storm::models::sparse::StateLabeling memoryStateLabeling(3);
        memoryStateLabeling.addLabel("init_memory");
        memoryStateLabeling.addLabel("condition_reached");
        memoryStateLabeling.addLabel("target_reached");
        memoryStateLabeling.addLabelToState("init_memory", 0);
        memoryStateLabeling.addLabelToState("condition_reached", 1);
        memoryStateLabeling.addLabelToState("target_reached", 2);

        storm::storage::BitVector allTransitions(transitionMatrix.getEntryCount(), true);
        storm::storage::BitVector conditionExitTransitions(transitionMatrix.getEntryCount(), false);
        storm::storage::BitVector targetExitTransitions(transitionMatrix.getEntryCount(), false);

        for (auto state : conditionStates) {
            for (auto choice : transitionMatrix.getRowGroupIndices(state)) {
                for (auto entryIt = transitionMatrix.getRow(choice).begin(); entryIt < transitionMatrix.getRow(choice).end(); ++entryIt) {
                    conditionExitTransitions.set(entryIt - transitionMatrix.begin(), true);
                }
            }
        }
        for (auto state : targetStates) {
            for (auto choice : transitionMatrix.getRowGroupIndices(state)) {
                for (auto entryIt = transitionMatrix.getRow(choice).begin(); entryIt < transitionMatrix.getRow(choice).end(); ++entryIt) {
                    targetExitTransitions.set(entryIt - transitionMatrix.begin(), true);
                }
            }
        }

        memoryTransitions[0][0] = allTransitions & ~conditionExitTransitions & ~targetExitTransitions; // if neither condition nor target reached, stay in init_memory
        memoryTransitions[0][1] = conditionExitTransitions;
        memoryTransitions[0][2] = targetExitTransitions & ~conditionExitTransitions;
        memoryTransitions[1][1] = allTransitions;  // once condition reached, stay in that memory state
        memoryTransitions[2][2] = allTransitions;  // once target reached, stay in that memory state

        // this assumes there is a single initial state
        auto memoryStructure = storm::storage::MemoryStructure(memoryTransitions, memoryStateLabeling, std::vector<uint64_t>(1, 0), true);

        auto finalScheduler = storm::storage::Scheduler<ValueType>(transitionMatrix.getRowGroupCount(), std::move(memoryStructure));

        auto const& modelRowGroupIndices = modelMatrix.getRowGroupIndices();
        auto const& quotientRowGroupIndices = transitionMatrix.getRowGroupIndices();

        uint64_t original_state = 0;
        for (uint64_t quotient_state : quotient_state_map) {
            if (scheduler.isChoiceSelected(original_state, 0)) {
                if (!targetStates.get(quotient_state) && !conditionStates.get(quotient_state)) {
                    auto model_choice = modelRowGroupIndices[original_state] + scheduler.getChoice(original_state, 0).getDeterministicChoice();
                    auto quotient_choice = quotient_choice_map[model_choice];
                    finalScheduler.setChoice(quotient_choice - quotientRowGroupIndices[quotient_state], quotient_state, 0);
                }
            }
        }

        for (uint64_t state = 0; state < transitionMatrix.getRowGroupCount(); ++state) {
            for (uint64_t memory = 0; memory < 3; ++memory) {
                if (!finalScheduler.isChoiceSelected(state, memory)) {
                    if (memory == 1) {
                        finalScheduler.setChoice(reachTargetChoices[state], state, memory);
                    } else if (memory == 2) {
                        finalScheduler.setChoice(reachConditionChoices[state], state, memory);
                    } else {
                        if (targetStates.get(state)) {
                            finalScheduler.setChoice(reachConditionChoices[state], state, memory);
                        } else if (conditionStates.get(state)) {
                            finalScheduler.setChoice(reachTargetChoices[state], state, memory);
                        } else {
                            finalScheduler.setChoice(0, state, memory);
                        }
                    }
                }
            }
        }

        return finalScheduler;
    }

    template<typename ValueType>
    bool ConditionalUnfolder<ValueType>::isConditionReachable() const {
        storm::storage::BitVector cond_states = this->getConditionalStatesForOriginalModel();
        storm::storage::BitVector all_states(this->mdp.getNumberOfStates(), true);
        uint64_t initial_state = *(this->mdp.getInitialStates().begin());
        
        auto reachable_states = storm::utility::graph::performProbGreater0E(this->mdp.getBackwardTransitions(), all_states, cond_states);

        return reachable_states.get(initial_state);
    }

    template<typename ValueType>
    std::shared_ptr<storm::models::sparse::Mdp<ValueType>> ConditionalUnfolder<ValueType>::constructUnfoldedModel() {
        
        // TODO make this more robust, only supports conditional formulas that use labels currently
        const std::string& main_subformula_label = this->formula.getSubformula().asEventuallyFormula().getSubformula().asAtomicLabelFormula().getLabel();
        const std::string& cond_subformula_label = this->formula.getConditionFormula().asEventuallyFormula().getSubformula().asAtomicLabelFormula().getLabel();

        STORM_LOG_THROW(mdp.hasLabel(main_subformula_label), storm::exceptions::NotSupportedException,
                        "The MDP does not have the label '" << main_subformula_label << "' required by the main subformula of the conditional formula.");
        STORM_LOG_THROW(mdp.hasLabel(cond_subformula_label), storm::exceptions::NotSupportedException,
                        "The MDP does not have the label '" << cond_subformula_label << "' required by the condition subformula of the conditional formula.");

        storm::storage::BitVector target_states = this->mdp.getStates(main_subformula_label);
        storm::storage::BitVector cond_states = this->mdp.getStates(cond_subformula_label);
        storm::storage::BitVector target_non_cond_states = target_states & (~cond_states);

        // bfs from cond states
        std::queue<uint64_t> bfs_queue;
        for (auto state : cond_states) {
            bfs_queue.push(state);
        }
        storm::storage::BitVector reachable_from_cond_states(this->mdp.getNumberOfStates(), false);
        uint64_t reachable_from_cond_states_rows = 0;
        auto transition_matrix = this->mdp.getTransitionMatrix();
        while (!bfs_queue.empty()) {
            uint64_t current_state = bfs_queue.front();
            bfs_queue.pop();

            for (auto rowIndex : transition_matrix.getRowGroupIndices(current_state)) {
                for (auto const& entry : transition_matrix.getRow(rowIndex)) {
                    uint64_t successor = entry.getColumn();
                    if (!reachable_from_cond_states.get(successor)) {
                        reachable_from_cond_states.set(successor, true);
                        reachable_from_cond_states_rows += transition_matrix.getRowGroupSize(successor);
                        bfs_queue.push(successor);
                    }
                }
            }
        }

        // bfs from target states that are not cond states
        for (auto state : target_non_cond_states) {
            bfs_queue.push(state);
        }
        storm::storage::BitVector reachable_from_target_non_cond_states(this->mdp.getNumberOfStates(), false);
        uint64_t reachable_from_target_non_cond_states_rows = 0;
        while (!bfs_queue.empty()) {
            uint64_t current_state = bfs_queue.front();
            bfs_queue.pop();

            for (auto rowIndex : transition_matrix.getRowGroupIndices(current_state)) {
                for (auto const& entry : transition_matrix.getRow(rowIndex)) {
                    uint64_t successor = entry.getColumn();
                    if (!reachable_from_target_non_cond_states.get(successor)) {
                        reachable_from_target_non_cond_states.set(successor, true);
                        reachable_from_target_non_cond_states_rows += transition_matrix.getRowGroupSize(successor);
                        bfs_queue.push(successor);
                    }
                }
            }
        }

        this->prototypeDuplicates.resize(3);
        this->prototypeDuplicates[0].resize(this->mdp.getNumberOfStates());
        this->prototypeDuplicates[1].resize(reachable_from_cond_states.getNumberOfSetBits());
        this->prototypeDuplicates[2].resize(reachable_from_target_non_cond_states.getNumberOfSetBits());

        uint64_t new_state_index = 0;
        for (uint64_t state = 0; state < this->mdp.getNumberOfStates(); state++) {
            this->statePrototype.push_back(state);
            this->stateMemory.push_back(0); // original state
            this->prototypeDuplicates[0][state] = new_state_index;
            new_state_index++;
        }
        for (auto state : reachable_from_cond_states) {
            this->statePrototype.push_back(state);
            this->stateMemory.push_back(1); // conditional was reached
            this->prototypeDuplicates[1][state] = new_state_index;
            new_state_index++;
        }
        for (auto state : reachable_from_target_non_cond_states) {
            this->statePrototype.push_back(state);
            this->stateMemory.push_back(2); // target but not conditional was reached
            this->prototypeDuplicates[2][state] = new_state_index;
            new_state_index++;
        }

        uint64_t num_new_states = this->mdp.getNumberOfStates() + reachable_from_cond_states.getNumberOfSetBits() + reachable_from_target_non_cond_states.getNumberOfSetBits();
        uint64_t num_new_rows = this->mdp.getNumberOfChoices() + reachable_from_cond_states_rows + reachable_from_target_non_cond_states_rows;

        storm::storage::sparse::ModelComponents<ValueType> components;

        storm::storage::SparseMatrixBuilder<ValueType> matrixBuilder(num_new_rows, num_new_states, 0, true, true, num_new_states);
        uint64_t rows_counter = 0;
        auto const& row_group_indices = this->mdp.getTransitionMatrix().getRowGroupIndices();
        for (uint64_t state = 0; state < num_new_states; ++state) {
            matrixBuilder.newRowGroup(rows_counter);
            auto prototype_state = this->statePrototype[state];
            auto memory = this->stateMemory[state];
            for (
                uint64_t prototype_row = row_group_indices[prototype_state];
                prototype_row < row_group_indices[prototype_state + 1];
                prototype_row++
            ) {

                if (memory == 0 && (!cond_states.get(prototype_state) || !target_states.get(prototype_state))) {
                    for (auto const& entry : this->mdp.getTransitionMatrix().getRow(prototype_row)) {
                        // original state, no cond reached, no target reached
                        matrixBuilder.addNextValue(
                            rows_counter,
                            entry.getColumn(),
                            entry.getValue()
                        );
                    }
                }

                else if (memory == 0 && cond_states.get(prototype_state)) {
                    for (auto const& entry : this->mdp.getTransitionMatrix().getRow(prototype_row)) {
                        // original state, cond reached
                        uint64_t new_state = this->prototypeDuplicates[1][entry.getColumn()];
                        matrixBuilder.addNextValue(
                            rows_counter,
                            new_state,
                            entry.getValue()
                        );
                    }
                }

                else if (memory == 0 && target_states.get(prototype_state)) {
                    for (auto const& entry : this->mdp.getTransitionMatrix().getRow(prototype_row)) {
                        // original state, target reached but not cond
                        uint64_t new_state = this->prototypeDuplicates[2][entry.getColumn()];
                        matrixBuilder.addNextValue(
                            rows_counter,
                            new_state,
                            entry.getValue()
                        );
                    }
                }

                // mem 1 state and target or mem 2 state and cond
                else if ((memory == 1 && target_states.get(prototype_state)) || (memory == 2 && cond_states.get(prototype_state))) {
                    matrixBuilder.addNextValue(
                        rows_counter,
                        state,
                        1
                    );
                }

                else if (memory == 1 || memory == 2) {
                    for (auto const& entry : this->mdp.getTransitionMatrix().getRow(prototype_row)) {
                        // original state, cond reached
                        uint64_t new_state = this->prototypeDuplicates[memory][entry.getColumn()];
                        matrixBuilder.addNextValue(
                            rows_counter,
                            new_state,
                            entry.getValue()
                        );
                    }
                }

                else {
                    throw storm::exceptions::BaseException("Unexpected state in unfolding.");
                }
                
                this->choiceMap.push_back(prototype_row);
                rows_counter++;
            }
        }

        auto new_transition_matrix = matrixBuilder.build();
        components.transitionMatrix = new_transition_matrix;

        // construct state labeling
        storm::models::sparse::StateLabeling labeling(num_new_states);
        for (auto const& label : this->mdp.getStateLabeling().getLabels()) {
            storm::storage::BitVector label_flags(num_new_states, false);
            
            if (label == "init") {
                // init label is only assigned to states with the initial memory state
                for (auto const& prototype : this->mdp.getStateLabeling().getStates(label)) {
                    for (uint64_t state = 0; state < num_new_states; state++) {
                        if (this->statePrototype[state] == prototype && this->stateMemory[state] == 0) {
                            label_flags.set(state);
                            break; // only one state can have the init label
                        }
                    }
                }
            } else {
                for (auto const& prototype : this->mdp.getStateLabeling().getStates(label)) {
                    for (uint64_t state = 0; state < num_new_states; state++) {
                        if (this->statePrototype[state] == prototype) {
                            label_flags.set(state);
                        }
                    }
                }
            }
            labeling.addLabel(label, std::move(label_flags));
        }
        components.stateLabeling = labeling;

        // create choice labeling
        storm::models::sparse::ChoiceLabeling choice_labeling(rows_counter);
        // add labels first
        if (this->mdp.hasChoiceLabeling()) {
            for (auto const& label : this->mdp.getChoiceLabeling().getLabels()) {
                choice_labeling.addLabel(label, storm::storage::BitVector(rows_counter, false));
            }
            for (uint64_t choice = 0; choice < rows_counter; choice++) {
                auto original_choice = this->choiceMap[choice];
                for (auto const& label : this->mdp.getChoiceLabeling().getLabelsOfChoice(original_choice)) {
                    choice_labeling.addLabelToChoice(label, choice);
                }
            }
            components.choiceLabeling = choice_labeling;
        }


        this->unfoldedMdp = std::make_shared<storm::models::sparse::Mdp<ValueType>>(std::move(components));

        return this->unfoldedMdp;
    }


    template class ConditionalUnfolder<storm::RationalNumber>;
    template class ConditionalUnfolder<double>;

}