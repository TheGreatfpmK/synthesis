#pragma once

#include "src/synthesis/translation/ItemKeyTranslator.h"

#include <storm/adapters/RationalNumberAdapter.h>
#include <storm/models/sparse/Model.h>
#include <storm/models/sparse/Mdp.h>
#include <storm/logic/ConditionalFormula.h>
#include <storm/logic/EventuallyFormula.h>
#include <storm/logic/AtomicLabelFormula.h>
#include <storm/storage/BitVector.h>
#include <storm/storage/Scheduler.h>
#include <storm/utility/graph.h>


namespace synthesis {

    template<typename ValueType>
    class ConditionalUnfolder {
    public:

        ConditionalUnfolder(storm::models::sparse::Mdp<ValueType> const& mdp, storm::logic::ConditionalFormula const& formula);

        std::shared_ptr<storm::models::sparse::Mdp<ValueType>> constructUnfoldedModel();

        storm::storage::BitVector getConditionalStatesForOriginalModel() const;
        storm::storage::BitVector getTargetStatesForOriginalModel() const;

        std::string getConditionalLabel() const;
        std::string getTargetLabel() const;

        bool isConditionReachable() const;

        // unfolded MDP
        std::shared_ptr<storm::models::sparse::Mdp<ValueType>> unfoldedMdp;

        // maps new choices to original choices
        std::vector<uint64_t> choiceMap;

        // for each state contains its prototype state
        std::vector<uint64_t> statePrototype;
        // for each state contains its memory index, 0 - original state, 1 - conditional was reached, 2 - target but not conditional was reached
        std::vector<uint64_t> stateMemory;

        std::vector<std::vector<uint64_t>> prototypeDuplicates;

        storm::storage::Scheduler<ValueType> map_scheduler_to_quotient(
            storm::storage::SparseMatrix<ValueType> const& modelMatrix,
            std::vector<uint64_t> const& quotient_state_map,
            std::vector<uint64_t> const& quotient_choice_map,
            storm::storage::Scheduler<ValueType> const& scheduler,
            std::vector<uint64_t> const& reachTargetChoices,
            std::vector<uint64_t> const& reachConditionChoices) const;

    private:

        // original MDP
        storm::models::sparse::Mdp<ValueType> const& mdp;

        storm::logic::ConditionalFormula const& formula;

    };


}