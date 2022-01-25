#include "storm-synthesis/pomdp/ExplicitPomdpMemoryUnfolder.h"

#include <limits>
#include "storm/storage/sparse/ModelComponents.h"
#include "storm/utility/graph.h"

#include "storm/exceptions/NotSupportedException.h"

namespace storm {
    namespace synthesis {

            
            template<typename ValueType>
            ExplicitPomdpMemoryUnfolder<ValueType>::ExplicitPomdpMemoryUnfolder(storm::models::sparse::Pomdp<ValueType> const& pomdp, storm::storage::PomdpMemory const& memory, bool addMemoryLabels, bool keepStateValuations)
            : pomdp(pomdp), memory(memory), addMemoryLabels(addMemoryLabels), keepStateValuations(keepStateValuations) {
                // intentionally left empty
            }


            template<typename ValueType>
            std::vector<uint64_t> ExplicitPomdpMemoryUnfolder<ValueType>::state_to_state() {
                return this->product_to_pomdp_state;
            }

            template<typename ValueType>
            std::vector<uint64_t> ExplicitPomdpMemoryUnfolder<ValueType>::state_to_memory() {
                return this->product_to_pomdp_memory;
            }

            // template<typename ValueType>
            // std::vector<uint64_t> ExplicitPomdpMemoryUnfolder<ValueType>::action_map() {
            //     return this->choice_action;
            // }

            // template<typename ValueType>
            // std::vector<uint64_t> ExplicitPomdpMemoryUnfolder<ValueType>::memory_map() {
            //     return this->choice_memory;
            // }

            
            template<typename ValueType>
            std::shared_ptr<storm::models::sparse::Mdp<ValueType>> ExplicitPomdpMemoryUnfolder<ValueType>::transform() {
                // For simplicity we first build the 'full' product of pomdp and memory (with pomdp.numStates * memory.numStates states).
                STORM_LOG_THROW(pomdp.isCanonic() , storm::exceptions::InvalidArgumentException, "POMDP must be canonical to unfold memory into it");
                storm::storage::sparse::ModelComponents<ValueType> components;
                components.transitionMatrix = transformTransitions();
                components.stateLabeling = transformStateLabeling();
                
                // Now delete unreachable states.
                storm::storage::BitVector allStates(components.transitionMatrix.getRowGroupCount(), true);
                auto reachableStates = storm::utility::graph::getReachableStates(components.transitionMatrix, components.stateLabeling.getStates("init"), allStates, ~allStates);
                components.transitionMatrix = components.transitionMatrix.getSubmatrix(true, reachableStates, reachableStates);
                components.stateLabeling = components.stateLabeling.getSubLabeling(reachableStates);
                if (keepStateValuations && pomdp.hasStateValuations()) {
                    std::vector<uint64_t> newToOldStates(pomdp.getNumberOfStates() * memory.getNumberOfStates(), 0);
                    for (uint64_t newState = 0; newState < newToOldStates.size(); newState++) {
                        newToOldStates[newState] = getModelState(newState);
                    }
                    components.stateValuations = pomdp.getStateValuations().blowup(newToOldStates).selectStates(reachableStates);
                }

                // build the remaining components
                /*components.observabilityClasses = transformObservabilityClasses(reachableStates);*/
                for (auto const& rewModel : pomdp.getRewardModels()) {
                    components.rewardModels.emplace(rewModel.first, transformRewardModel(rewModel.second, reachableStates));
                }

                //+
                this->product_to_pomdp_state.reserve(components.transitionMatrix.getRowGroupCount());
                this->product_to_pomdp_memory.reserve(components.transitionMatrix.getRowGroupCount());
                // this->choice_action.reserve(components.transitionMatrix.getRowCount());
                // this->choice_memory.reserve(components.transitionMatrix.getRowCount());
                storm::storage::SparseMatrix<ValueType> const& origTransitions = pomdp.getTransitionMatrix();
                for (uint64_t modelState = 0; modelState < pomdp.getNumberOfStates(); ++modelState) {
                    for (uint64_t memState = 0; memState < memory.getNumberOfStates(); ++memState) {
                        if (!reachableStates.get(getUnfoldingState(modelState, memState))) {
                            continue;
                        }
                        this->product_to_pomdp_state.push_back(modelState);
                        this->product_to_pomdp_memory.push_back(memState);
                        /*for (uint64_t origRow = origTransitions.getRowGroupIndices()[modelState]; origRow < origTransitions.getRowGroupIndices()[modelState + 1]; ++origRow) {
                            for (auto const& memStatePrime : memory.getTransitions(memState)) {
                                this->choice_action.push_back(origRow);
                                this->choice_memory.push_back(memStatePrime);
                            }
                        }*/
                    }
                }

                // return std::make_shared<storm::models::sparse::Pomdp<ValueType>>(std::move(components), true);
                return std::make_shared<storm::models::sparse::Mdp<ValueType>>(std::move(components));
            }
        
            template<typename ValueType>
            storm::storage::SparseMatrix<ValueType> ExplicitPomdpMemoryUnfolder<ValueType>::transformTransitions() {
                storm::storage::SparseMatrix<ValueType> const& origTransitions = pomdp.getTransitionMatrix();
                uint64_t numRows = 0;
                uint64_t numEntries = 0;
                for (uint64_t modelState = 0; modelState < pomdp.getNumberOfStates(); ++modelState) {
                    for (uint64_t memState = 0; memState < memory.getNumberOfStates(); ++memState) {
                        numRows += origTransitions.getRowGroupSize(modelState) * memory.getNumberOfOutgoingTransitions(memState);
                        numEntries += origTransitions.getRowGroup(modelState).getNumberOfEntries() * memory.getNumberOfOutgoingTransitions(memState);
                    }
                }
                storm::storage::SparseMatrixBuilder<ValueType> builder(numRows,
                                                                        pomdp.getNumberOfStates() * memory.getNumberOfStates(),
                                                                        numEntries,
                                                                        true,
                                                                        true,
                                                                        pomdp.getNumberOfStates() * memory.getNumberOfStates());
                
                uint64_t row = 0;
                for (uint64_t modelState = 0; modelState < pomdp.getNumberOfStates(); ++modelState) {
                    for (uint64_t memState = 0; memState < memory.getNumberOfStates(); ++memState) {
                        builder.newRowGroup(row);
                        for (uint64_t origRow = origTransitions.getRowGroupIndices()[modelState]; origRow < origTransitions.getRowGroupIndices()[modelState + 1]; ++origRow) {
                            for (auto const& memStatePrime : memory.getTransitions(memState)) {
                                for (auto const& entry : origTransitions.getRow(origRow)) {
                                    builder.addNextValue(row, getUnfoldingState(entry.getColumn(), memStatePrime), entry.getValue());
                                }
                                ++row;
                            }
                        }
                    }
                }
                return builder.build();
            }
        
            template<typename ValueType>
            storm::models::sparse::StateLabeling ExplicitPomdpMemoryUnfolder<ValueType>::transformStateLabeling() const {
                storm::models::sparse::StateLabeling labeling(pomdp.getNumberOfStates() * memory.getNumberOfStates());
                for (auto const& labelName : pomdp.getStateLabeling().getLabels()) {
                    storm::storage::BitVector newStates(pomdp.getNumberOfStates() * memory.getNumberOfStates(), false);
                    
                    // The init label is only assigned to unfolding states with the initial memory state
                    if (labelName == "init") {
                        for (auto const& modelState : pomdp.getStateLabeling().getStates(labelName)) {
                            newStates.set(getUnfoldingState(modelState, memory.getInitialState()));
                        }
                    } else {
                        for (auto const& modelState : pomdp.getStateLabeling().getStates(labelName)) {
                            for (uint64_t memState = 0; memState < memory.getNumberOfStates(); ++memState) {
                                newStates.set(getUnfoldingState(modelState, memState));
                            }
                        }
                    }
                    labeling.addLabel(labelName, std::move(newStates));
                }
                if (addMemoryLabels) {
                    for (uint64_t memState = 0; memState < memory.getNumberOfStates(); ++memState) {
                        storm::storage::BitVector newStates(pomdp.getNumberOfStates() * memory.getNumberOfStates(), false);
                        for (uint64_t modelState = 0; modelState < pomdp.getNumberOfStates(); ++modelState) {
                            newStates.set(getUnfoldingState(modelState, memState));
                        }
                        labeling.addLabel("memstate_"+std::to_string(memState), newStates);
                    }
                }
                return labeling;
            }
        
            template<typename ValueType>
            std::vector<uint32_t> ExplicitPomdpMemoryUnfolder<ValueType>::transformObservabilityClasses(storm::storage::BitVector const& reachableStates) const {
                std::vector<uint32_t> observations;
                observations.reserve(pomdp.getNumberOfStates() * memory.getNumberOfStates());
                for (uint64_t modelState = 0; modelState < pomdp.getNumberOfStates(); ++modelState) {
                    for (uint64_t memState = 0; memState < memory.getNumberOfStates(); ++memState) {
                        if (reachableStates.get(getUnfoldingState(modelState, memState))) {
                            observations.push_back(getUnfoldingObersvation(pomdp.getObservation(modelState), memState));
                        }
                    }
                }
                
                // Eliminate observations that are not in use (as they are not reachable).
                std::set<uint32_t> occuringObservations(observations.begin(), observations.end());
                uint32_t highestObservation = *occuringObservations.rbegin();
                std::vector<uint32_t> oldToNewObservationMapping(highestObservation + 1, std::numeric_limits<uint32_t>::max());
                uint32_t newObs = 0;
                for (auto const& oldObs : occuringObservations) {
                    oldToNewObservationMapping[oldObs] = newObs;
                    ++newObs;
                }
                for (auto& obs : observations) {
                    obs = oldToNewObservationMapping[obs];
                }
                
                return observations;
            }
        
            template<typename ValueType>
            storm::models::sparse::StandardRewardModel<ValueType> ExplicitPomdpMemoryUnfolder<ValueType>::transformRewardModel(storm::models::sparse::StandardRewardModel<ValueType> const& rewardModel, storm::storage::BitVector const& reachableStates) const {
                boost::optional<std::vector<ValueType>> stateRewards, actionRewards;
                if (rewardModel.hasStateRewards()) {
                    stateRewards = std::vector<ValueType>();
                    stateRewards->reserve(pomdp.getNumberOfStates() * memory.getNumberOfStates());
                    for (uint64_t modelState = 0; modelState < pomdp.getNumberOfStates(); ++modelState) {
                        for (uint64_t memState = 0; memState < memory.getNumberOfStates(); ++memState) {
                            if (reachableStates.get(getUnfoldingState(modelState, memState))) {
                                stateRewards->push_back(rewardModel.getStateReward(modelState));
                            }
                        }
                    }
                }
                if (rewardModel.hasStateActionRewards()) {
                    actionRewards = std::vector<ValueType>();
                    for (uint64_t modelState = 0; modelState < pomdp.getNumberOfStates(); ++modelState) {
                        for (uint64_t memState = 0; memState < memory.getNumberOfStates(); ++memState) {
                            if (reachableStates.get(getUnfoldingState(modelState, memState))) {
                                for (uint64_t origRow = pomdp.getTransitionMatrix().getRowGroupIndices()[modelState]; origRow < pomdp.getTransitionMatrix().getRowGroupIndices()[modelState + 1]; ++origRow) {
                                    ValueType const& actionReward = rewardModel.getStateActionReward(origRow);
                                    actionRewards->insert(actionRewards->end(), memory.getNumberOfOutgoingTransitions(memState), actionReward);
                                }
                            }
                        }
                    }
                }
                STORM_LOG_THROW(!rewardModel.hasTransitionRewards(), storm::exceptions::NotSupportedException, "Transition rewards are currently not supported.");
                return storm::models::sparse::StandardRewardModel<ValueType>(std::move(stateRewards), std::move(actionRewards));
            }

            template<typename ValueType>
            uint64_t ExplicitPomdpMemoryUnfolder<ValueType>::getUnfoldingState(uint64_t modelState, uint64_t memoryState) const {
                return modelState * memory.getNumberOfStates() + memoryState;
            }
            
            template<typename ValueType>
            uint64_t ExplicitPomdpMemoryUnfolder<ValueType>::getModelState(uint64_t unfoldingState) const {
                return unfoldingState / memory.getNumberOfStates();
            }
            
            template<typename ValueType>
            uint64_t ExplicitPomdpMemoryUnfolder<ValueType>::getMemoryState(uint64_t unfoldingState) const {
                return unfoldingState % memory.getNumberOfStates();
            }
            
            template<typename ValueType>
            uint32_t ExplicitPomdpMemoryUnfolder<ValueType>::getUnfoldingObersvation(uint32_t modelObservation, uint64_t memoryState) const {
                return modelObservation * memory.getNumberOfStates() + memoryState;
            }
            
            template<typename ValueType>
            uint32_t ExplicitPomdpMemoryUnfolder<ValueType>::getModelObersvation(uint32_t unfoldingObservation) const {
                return unfoldingObservation / memory.getNumberOfStates();
            }
            
            template<typename ValueType>
            uint64_t ExplicitPomdpMemoryUnfolder<ValueType>::getMemoryStateFromObservation(uint32_t unfoldingObservation) const {
                return unfoldingObservation % memory.getNumberOfStates();
            }

            template class ExplicitPomdpMemoryUnfolder<double>;
            template class ExplicitPomdpMemoryUnfolder<storm::RationalNumber>;
            template class ExplicitPomdpMemoryUnfolder<storm::RationalFunction>;

    }
}