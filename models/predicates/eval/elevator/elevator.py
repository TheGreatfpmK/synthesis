import stormvogel
import stormvogel.bird
import stormpy


# state variables: elevator_pos, door, pasX_pos, pasX_target, pasX_init, pasX_elevator

NUMBER_OF_FLOORS = 6
# 2 passengers
PASSENGER_INIT_PROB = 0.1


def available_actions(state):
    if state == "init":
        return ["init"]
    
    elevator_pos, door, pas1_pos, pas1_target, pas1_init, pas1_elevator, pas2_pos, pas2_target, pas2_init, pas2_elevator = state

    actions = []
    if elevator_pos < NUMBER_OF_FLOORS - 1 and not door:
        actions.append("up")
    if elevator_pos > 0 and not door:
        actions.append("down")
    actions.append("doors")
    actions.append("wait")
    
    return actions


def passenger_init():
    passenger_outcomes = {}
    passenger_outcomes[(0, 0, False, False)] = 1-PASSENGER_INIT_PROB
    for pas1_pos in range(NUMBER_OF_FLOORS):
        for pas1_target in range(NUMBER_OF_FLOORS):
            if pas1_pos != pas1_target:
                passenger_outcomes[(pas1_pos, pas1_target, True, False)] = PASSENGER_INIT_PROB / (NUMBER_OF_FLOORS * (NUMBER_OF_FLOORS - 1))
                
    return passenger_outcomes


def delta(state, action):
    if state == "init":
        outcomes = {}
        for floor in range(NUMBER_OF_FLOORS):
            outcomes[(floor, False, 0, 0, False, False, 0, 0, False, False)] = 1/NUMBER_OF_FLOORS
        return [(prob, state) for state, prob in outcomes.items()]
    
    elevator_pos, door, pas1_pos, pas1_target, pas1_init, pas1_elevator, pas2_pos, pas2_target, pas2_init, pas2_elevator = state

    if (pas1_init and pas1_pos == pas1_target and not pas1_elevator) and (pas2_init and pas2_pos == pas2_target and not pas2_elevator):
        return [(1.0, state)]  # No further transitions if all passengers are at their targets
    
    pas1_outcomes = None
    pas2_outcomes = None

    if not pas1_init:
        pas1_outcomes = passenger_init()

    if not pas2_init:
        pas2_outcomes = passenger_init()
    
    if action == "up":
        assert door == False, "Cannot move up while door is open"
        new_elevator_pos = min(elevator_pos + 1, NUMBER_OF_FLOORS-1)
        outcomes = {}
        if pas1_outcomes is None:
            new_pas1_pos = new_elevator_pos if pas1_elevator else pas1_pos
            new_pas1_target = pas1_target
            new_pas1_init = pas1_init
            new_pas1_elevator = pas1_elevator
        if pas2_outcomes is None:
            new_pas2_pos = new_elevator_pos if pas2_elevator else pas2_pos
            new_pas2_target = pas2_target
            new_pas2_init = pas2_init
            new_pas2_elevator = pas2_elevator
        for pas1_state, pas1_prob in (pas1_outcomes.items() if pas1_outcomes is not None else [((new_pas1_pos, new_pas1_target, new_pas1_init, new_pas1_elevator), 1.0)]):
            for pas2_state, pas2_prob in (pas2_outcomes.items() if pas2_outcomes is not None else [((new_pas2_pos, new_pas2_target, new_pas2_init, new_pas2_elevator), 1.0)]):
                combined_prob = pas1_prob * pas2_prob
                combined_state = (new_elevator_pos, door, pas1_state[0], pas1_state[1], pas1_state[2], pas1_state[3], pas2_state[0], pas2_state[1], pas2_state[2], pas2_state[3])
                outcomes[combined_state] = outcomes.get(combined_state, 0) + combined_prob
        assert sum(outcomes.values()) == 1.0, "Probabilities do not sum to 1"
        return [(prob, state) for state, prob in outcomes.items()]
    
    elif action == "down":
        assert door == False, "Cannot move down while door is open"
        new_elevator_pos = max(elevator_pos - 1, 0)
        outcomes = {}
        if pas1_outcomes is None:
            new_pas1_pos = new_elevator_pos if pas1_elevator else pas1_pos
            new_pas1_target = pas1_target
            new_pas1_init = pas1_init
            new_pas1_elevator = pas1_elevator
        if pas2_outcomes is None:
            new_pas2_pos = new_elevator_pos if pas2_elevator else pas2_pos
            new_pas2_target = pas2_target
            new_pas2_init = pas2_init
            new_pas2_elevator = pas2_elevator
        for pas1_state, pas1_prob in (pas1_outcomes.items() if pas1_outcomes is not None else [((new_pas1_pos, new_pas1_target, new_pas1_init, new_pas1_elevator), 1.0)]):
            for pas2_state, pas2_prob in (pas2_outcomes.items() if pas2_outcomes is not None else [((new_pas2_pos, new_pas2_target, new_pas2_init, new_pas2_elevator), 1.0)]):
                combined_prob = pas1_prob * pas2_prob
                combined_state = (new_elevator_pos, door, pas1_state[0], pas1_state[1], pas1_state[2], pas1_state[3], pas2_state[0], pas2_state[1], pas2_state[2], pas2_state[3])
                outcomes[combined_state] = outcomes.get(combined_state, 0) + combined_prob
        assert sum(outcomes.values()) == 1.0, "Probabilities do not sum to 1"
        return [(prob, state) for state, prob in outcomes.items()]
    
    elif action == "doors":
        new_door = not door
        outcomes = {}
        if pas1_outcomes is None:
            new_pas1_pos = pas1_pos
            new_pas1_target = pas1_target
            new_pas1_init = pas1_init
            if new_door:  # Doors are opened
                if pas1_pos == pas1_target and pas1_elevator:
                    new_pas1_elevator = False  # Passenger 1 leaves the elevator at their target floor
                elif (pas1_pos == elevator_pos) and (pas1_pos != pas1_target) and not pas1_elevator:
                    new_pas1_elevator = True  # Passenger 1 enters the elevator if not at their target floor
                else:
                    new_pas1_elevator = pas1_elevator  # No change
            else:
                new_pas1_elevator = pas1_elevator  # No change if doors are closed
        if pas2_outcomes is None:
            new_pas2_pos = pas2_pos
            new_pas2_target = pas2_target
            new_pas2_init = pas2_init
            if new_door:  # Doors are opened
                if pas2_pos == pas2_target and pas2_elevator:
                    new_pas2_elevator = False  # Passenger 2 leaves the elevator at their target floor
                elif (pas2_pos == elevator_pos) and (pas2_pos != pas2_target) and not pas2_elevator:
                    new_pas2_elevator = True  # Passenger 2 enters the elevator if not at their target floor
                else:
                    new_pas2_elevator = pas2_elevator  # No change
            else:
                new_pas2_elevator = pas2_elevator  # No change if doors are closed
        for pas1_state, pas1_prob in (pas1_outcomes.items() if pas1_outcomes is not None else [((new_pas1_pos, new_pas1_target, new_pas1_init, new_pas1_elevator), 1.0)]):
            for pas2_state, pas2_prob in (pas2_outcomes.items() if pas2_outcomes is not None else [((new_pas2_pos, new_pas2_target, new_pas2_init, new_pas2_elevator), 1.0)]):
                combined_prob = pas1_prob * pas2_prob
                combined_state = (elevator_pos, new_door, pas1_state[0], pas1_state[1], pas1_state[2], pas1_state[3], pas2_state[0], pas2_state[1], pas2_state[2], pas2_state[3])
                outcomes[combined_state] = outcomes.get(combined_state, 0) + combined_prob
        assert sum(outcomes.values()) == 1.0, "Probabilities do not sum to 1"
        return [(prob, state) for state, prob in outcomes.items()]
    
    elif action == "wait":
        outcomes = {}
        if pas1_outcomes is None:
            new_pas1_pos = pas1_pos
            new_pas1_target = pas1_target
            new_pas1_init = pas1_init
            if door:  # Doors are open
                if pas1_pos == pas1_target and pas1_elevator:
                    new_pas1_elevator = False  # Passenger 1 leaves the elevator at their target floor
                elif (pas1_pos == elevator_pos) and (pas1_pos != pas1_target) and not pas1_elevator:
                    new_pas1_elevator = True  # Passenger 1 enters the elevator if not at their target floor
                else:
                    new_pas1_elevator = pas1_elevator  # No change
            else:
                new_pas1_elevator = pas1_elevator  # No change if doors are closed
        if pas2_outcomes is None:
            new_pas2_pos = pas2_pos
            new_pas2_target = pas2_target
            new_pas2_init = pas2_init
            if door:  # Doors are open
                if pas2_pos == pas2_target and pas2_elevator:
                    new_pas2_elevator = False  # Passenger 2 leaves the elevator at their target floor
                elif (pas2_pos == elevator_pos) and (pas2_pos != pas2_target) and not pas2_elevator:
                    new_pas2_elevator = True  # Passenger 2 enters the elevator if not at their target floor
                else:
                    new_pas2_elevator = pas2_elevator  # No change
            else:
                new_pas2_elevator = pas2_elevator  # No change if doors are closed
        for pas1_state, pas1_prob in (pas1_outcomes.items() if pas1_outcomes is not None else [((new_pas1_pos, new_pas1_target, new_pas1_init, new_pas1_elevator), 1.0)]):
            for pas2_state, pas2_prob in (pas2_outcomes.items() if pas2_outcomes is not None else [((new_pas2_pos, new_pas2_target, new_pas2_init, new_pas2_elevator), 1.0)]):
                combined_prob = pas1_prob * pas2_prob
                combined_state = (elevator_pos, door, pas1_state[0], pas1_state[1], pas1_state[2], pas1_state[3], pas2_state[0], pas2_state[1], pas2_state[2], pas2_state[3])
                outcomes[combined_state] = outcomes.get(combined_state, 0) + combined_prob
        assert sum(outcomes.values()) == 1.0, "Probabilities do not sum to 1"
        return [(prob, state) for state, prob in outcomes.items()]
    
    assert False, f"Invalid action: {action} at state: {state}"


def labels(state):
    if state == "init":
        return "init"
    
    elevator_pos, door, pas1_pos, pas1_target, pas1_init, pas1_elevator, pas2_pos, pas2_target, pas2_init, pas2_elevator = state

    if (pas1_init and pas1_pos == pas1_target and not pas1_elevator) and (pas2_init and pas2_pos == pas2_target and not pas2_elevator):
        return "goal"
    
    return str(state)
    # return "running"


def rewards(state, action):
    if state == "init" or labels(state) == "goal":
        return {"rew": 0}
    else:
        return {"rew": 1}
    
    



def elevator():
    elevator = stormvogel.bird.build_bird(
        delta=delta,
        init="init",
        available_actions=available_actions,
        labels=labels,
        modeltype=stormvogel.ModelType.MDP,
        rewards=rewards,
        max_size=1000000
    )

    # vmax = stormvogel.model_checking(elevator, "Pmax=? [ F \"goal\" ]").values
    # print(f"Maximum probability of reaching the goal: {list(vmax.values())[0]}")

    # rmin = stormvogel.model_checking(elevator, "Rmin=? [ F \"goal\" ]").values
    # print(f"Minimum expected reward to reach the goal: {list(rmin.values())[0]}")

    model = stormvogel.stormpy_utils.stormvogel_to_stormpy(elevator)

    # print(model)

    stormpy.export_to_drn(model, "elevator.drn")

    state_valuations_json = []

    for state in elevator.states:
        label = next(state.labels).replace('(', '').replace(')', '').split(', ')


        if len(label) == 1:
            if label[0] == "init":
                state_valuations_json.append([["elevator_pos", 0], ["door", False], ["pas1_pos", 0], ["pas1_target", 0], ["pas1_init", False], ["pas1_elevator", False], ["pas2_pos", 0], ["pas2_target", 0], ["pas2_init", False], ["pas2_elevator", False]])
            elif label[0] == "goal":
                state_valuations_json.append([["elevator_pos", 0], ["door", False], ["pas1_pos", 0], ["pas1_target", 0], ["pas1_init", True], ["pas1_elevator", False], ["pas2_pos", 0], ["pas2_target", 0], ["pas2_init", True], ["pas2_elevator", False]])
        else:
            state_valuations_json.append([["elevator_pos", int(label[0])], ["door", label[1] == "True"], ["pas1_pos", int(label[2])], ["pas1_target", int(label[3])], ["pas1_init", label[4] == "True"], ["pas1_elevator", label[5] == "True"], ["pas2_pos", int(label[6])], ["pas2_target", int(label[7])], ["pas2_init", label[8] == "True"], ["pas2_elevator", label[9] == "True"]])

    import json
    with open("state-valuations.json", "w") as f:
        json.dump(state_valuations_json, f, indent=4)


if __name__ == "__main__":
    elevator()