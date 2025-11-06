# pragma once

#include <storm/adapters/RationalNumberAdapter.h>
#include <storm/models/sparse/Pomdp.h>
#include <storm/models/sparse/Mdp.h>
#include <storm/models/sparse/Model.h>
#include <storm/storage/BitVector.h>

namespace synthesis {

template<typename ValueType>
class BeliefSupportUnfolder {

    public:
        BeliefSupportUnfolder(storm::models::sparse::Pomdp<ValueType> const& pomdp);

        void unfoldBeliefSupportMdp();

        storm::models::sparse::Mdp<ValueType> getUnfoldedMdp() const;

        std::set<uint64_t> const& getBeliefSupportOfState(uint64_t state) const {
            return belief_supports[state];
        }

    private:
        storm::models::sparse::Pomdp<ValueType> const& pomdp;
        std::shared_ptr<storm::models::sparse::Mdp<ValueType>> mdp = nullptr;
        std::vector<std::set<uint64_t>> belief_supports;
};

}