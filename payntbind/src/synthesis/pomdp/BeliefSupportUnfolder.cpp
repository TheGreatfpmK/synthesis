
#include "BeliefSupportUnfolder.h"

#include <queue>

namespace synthesis {

template<typename ValueType>
BeliefSupportUnfolder<ValueType>::BeliefSupportUnfolder(storm::models::sparse::Pomdp<ValueType> const& pomdp)
    : pomdp(pomdp) {}

template<typename ValueType>
void BeliefSupportUnfolder<ValueType>::unfoldBeliefSupportMdp() {
    
    // compute state space
    storm::storage::BitVector initialStates = pomdp.getInitialStates();
    std::set<uint64_t> initial_belief_support{};
    for (auto state : initialStates) {
        initial_belief_support.insert(state);
    }

    uint64_t row_count = 0;

    belief_supports.push_back(initial_belief_support);
    std::map<std::set<uint64_t>, uint64_t> belief_support_to_index;
    belief_support_to_index[initial_belief_support] = 0;

    std::queue<uint64_t> to_explore;
    to_explore.push(0);

    while (!to_explore.empty()) {
        uint64_t current_belief_support_index = to_explore.front();
        to_explore.pop();
        std::set<uint64_t> const& current_belief_support = belief_supports[current_belief_support_index];

        auto it = current_belief_support.begin();
        uint64_t first_state = *it;
        row_count += pomdp.getNondeterministicChoiceIndices()[first_state + 1] - pomdp.getNondeterministicChoiceIndices()[first_state];

        // compute successors for all actions
        std::map<std::tuple<uint64_t, uint32_t>, std::set<uint64_t>> action_observation_to_successor_belief_support;
        for (uint64_t state : current_belief_support) {
            uint64_t nci_start = pomdp.getNondeterministicChoiceIndices()[state];
            uint64_t nci_end = pomdp.getNondeterministicChoiceIndices()[state + 1];
            for (uint64_t choice = nci_start; choice < nci_end; ++choice) {
                uint64_t action = choice - nci_start;
                auto const& transitions = pomdp.getTransitionMatrix().getRow(choice);
                for (auto const& entry : transitions) {
                    uint32_t observation = pomdp.getObservation(entry.getColumn());
                    action_observation_to_successor_belief_support[std::make_tuple(action, observation)].insert(entry.getColumn());
                }
            }
        }

        // add new belief supports
        for (auto const& [action_observation, successor_belief_support] : action_observation_to_successor_belief_support) {
            if (belief_support_to_index.find(successor_belief_support) == belief_support_to_index.end()) {
                uint64_t new_index = belief_supports.size();
                belief_supports.push_back(successor_belief_support);
                belief_support_to_index[successor_belief_support] = new_index;
                to_explore.push(new_index);
            }
        }
    }

    std::cout << "Unfolded belief-support MDP has " << belief_supports.size() << " states." << std::endl;
    // for (uint64_t i = 0; i < belief_supports.size(); ++i) {
    //     std::cout << "  Belief support " << i << " contains { ";
    //     for (auto state : belief_supports[i]) {
    //         std::cout << state << " ";
    //     }
    //     std::cout << "}" << std::endl;
    // }

    //compute transition matrix
    storm::storage::SparseMatrixBuilder<ValueType> builder(
        row_count, belief_supports.size(), 0, true, true, belief_supports.size()
    );

    uint64_t num_rows = 0;
    std::vector<uint64_t> choiceMap;
    for (uint64_t state = 0; state < belief_supports.size(); ++state) {
        builder.newRowGroup(num_rows);
        std::set<uint64_t> const& current_belief_support = belief_supports[state];

        // compute successors for all actions
        std::map<std::tuple<uint64_t, uint32_t>, ValueType> action_observation_to_successor_belief_support_value_sum;
        std::map<std::tuple<uint64_t, uint32_t>, std::set<uint64_t>> action_observation_to_successor_belief_support;
        std::map<uint64_t, std::set<uint32_t>> action_to_observations;
        for (uint64_t pomdp_state : current_belief_support) {
            uint64_t nci_start = pomdp.getNondeterministicChoiceIndices()[pomdp_state];
            uint64_t nci_end = pomdp.getNondeterministicChoiceIndices()[pomdp_state + 1];
            for (uint64_t choice = nci_start; choice < nci_end; ++choice) {
                uint64_t action = choice - nci_start;
                auto const& transitions = pomdp.getTransitionMatrix().getRow(choice);
                for (auto const& entry : transitions) {
                    uint32_t observation = pomdp.getObservation(entry.getColumn());
                    action_to_observations[action].insert(observation);
                    if (action_observation_to_successor_belief_support_value_sum.find(std::make_tuple(action, observation)) == action_observation_to_successor_belief_support_value_sum.end()) {
                        action_observation_to_successor_belief_support_value_sum[std::make_tuple(action, observation)] = ValueType(0);
                    }
                    action_observation_to_successor_belief_support_value_sum[std::make_tuple(action, observation)] += entry.getValue();
                    action_observation_to_successor_belief_support[std::make_tuple(action, observation)].insert(entry.getColumn());
                }
            }
        }

        // add transitions
        for (uint64_t action = 0; action < action_to_observations.size(); ++action) {
            // Get the first element of the set
            auto it = current_belief_support.begin();
            uint64_t first_state = *it;
            choiceMap.push_back(pomdp.getNondeterministicChoiceIndices()[first_state] + action);
            std::vector<uint64_t> successor_indices;
            std::map<uint64_t, uint32_t> successor_to_observation;
            for (auto observation : action_to_observations[action]) {
                uint64_t successor_index = belief_support_to_index[action_observation_to_successor_belief_support[std::make_tuple(action, observation)]];
                successor_indices.push_back(successor_index);
                successor_to_observation[successor_index] = observation;
            }

            for (auto successor_index : successor_indices) {
                uint32_t observation = successor_to_observation[successor_index];
                ValueType action_observation_value = action_observation_to_successor_belief_support_value_sum[std::make_tuple(action, observation)];
                ValueType action_total_sum = ValueType(0);
                for (auto obs : action_to_observations[action]) {
                    action_total_sum += action_observation_to_successor_belief_support_value_sum[std::make_tuple(action, obs)];
                }
                ValueType transition_probability = action_observation_value / action_total_sum;
                builder.addNextValue(num_rows, successor_index, transition_probability);
            }
            num_rows++;
        }
    }
    auto transition_matrix = builder.build();

    storm::storage::sparse::ModelComponents<ValueType> components;
    components.transitionMatrix = transition_matrix;

    // construct state labeling
    storm::models::sparse::StateLabeling labeling(belief_supports.size());
    storm::storage::BitVector init_flag(belief_supports.size(), false);
    init_flag.set(0);
    labeling.addLabel("init", std::move(init_flag));
    components.stateLabeling = labeling;

    // create choice labeling
    storm::models::sparse::ChoiceLabeling choiceLabeling(num_rows);
    // add labels first
    for (auto const& label : pomdp.getChoiceLabeling().getLabels()) {
        choiceLabeling.addLabel(label, storm::storage::BitVector(num_rows, false));
    }

    for (uint64_t choice = 0; choice < num_rows; choice++) {
        auto original_choice = choiceMap[choice];
        for (auto const& label : pomdp.getChoiceLabeling().getLabelsOfChoice(original_choice)) {
            choiceLabeling.addLabelToChoice(label, choice);
        }
    }
    components.choiceLabeling = choiceLabeling;

    mdp = std::make_shared<storm::models::sparse::Mdp<ValueType>>(components);
}

template<typename ValueType>
storm::models::sparse::Mdp<ValueType> BeliefSupportUnfolder<ValueType>::getUnfoldedMdp() const {
    return *mdp;
}

template class BeliefSupportUnfolder<double>;
template class BeliefSupportUnfolder<storm::RationalNumber>;

} // namespace synthesis
