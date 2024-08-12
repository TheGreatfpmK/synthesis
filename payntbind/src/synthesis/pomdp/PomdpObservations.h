#pragma once

#include <storm/adapters/RationalNumberAdapter.h>
#include <storm/models/sparse/Mdp.h>
#include <storm/models/sparse/Pomdp.h>

namespace synthesis {

    template<typename ValueType>
    class PomdpObservations {

    public:

        PomdpObservations(storm::models::sparse::Pomdp<ValueType> const& pomdp);

        // underlying mdp
        std::shared_ptr<storm::models::sparse::Mdp<ValueType>> underlyingMdp;
        
    };
}