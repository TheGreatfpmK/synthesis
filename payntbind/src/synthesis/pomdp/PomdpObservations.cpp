#include "PomdpObservations.h"


namespace synthesis {

    template <typename ValueType>
    PomdpObservations<ValueType>::PomdpObservations(storm::models::sparse::Pomdp<ValueType> const& pomdp) {
        storm::storage::sparse::ModelComponents<ValueType> components;
        components.transitionMatrix = pomdp.getTransitionMatrix();
        components.stateLabeling = pomdp.getStateLabeling();
        components.choiceLabeling = pomdp.getChoiceLabeling();
        for (auto const& reward_model : pomdp.getRewardModels()) {
            components.rewardModels.emplace(reward_model.first, reward_model.second);
        }
        this->underlyingMdp = std::make_shared<storm::models::sparse::Mdp<ValueType>>(std::move(components));
    }

    

    template class PomdpObservations<double>;
}