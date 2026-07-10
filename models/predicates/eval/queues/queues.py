import itertools

import stormvogel
import stormvogel.bird
import stormpy
from pathlib import Path


def current_script_directory():
    return str(Path(__file__).resolve().parent)


# 4 queues of size 5, goal is to serve 50 customers
# state variables: queue1, queue2, queue3, queue4, served_customers, customer_waiting

SERVE_PROB = 0.05
MAX_QUEUE_SIZE = 5
GOAL_SERVE_COUNT = 20

serving_outcomes_cache = {}

def available_actions(state):
    if state == "init":
        return ["init"]
    
    queue1, queue2, queue3, queue4, served_customers, customer_waiting = state

    if served_customers >= GOAL_SERVE_COUNT:
        return ["done"]  # No more actions possible
    
    if not customer_waiting:
        return ["wait"]  # Only wait action is available when no customer is waiting
    
    actions = []
    if queue1 < MAX_QUEUE_SIZE:
        actions.append("place1")
    if queue2 < MAX_QUEUE_SIZE:
        actions.append("place2")
    if queue3 < MAX_QUEUE_SIZE:
        actions.append("place3")
    if queue4 < MAX_QUEUE_SIZE:
        actions.append("place4")

    return actions if len(actions) > 0 else ["wait"]  # If all queues are full, only wait action is available
    
    


def serving_customers(state):

    queue1, queue2, queue3, queue4, served_customers, customer_waiting = state

    if (queue1>0, queue2>0, queue3>0, queue4>0) in serving_outcomes_cache:
        return serving_outcomes_cache[(queue1>0, queue2>0, queue3>0, queue4>0)]

    serving_outcomes = {}
    
    for serve1 in [0, 1] if queue1 > 0 else [0]:
        for serve2 in [0, 1] if queue2 > 0 else [0]:
            for serve3 in [0, 1] if queue3 > 0 else [0]:
                for serve4 in [0, 1] if queue4 > 0 else [0]:
                    new_queue1 = serve1
                    new_queue2 = serve2
                    new_queue3 = serve3
                    new_queue4 = serve4
                    new_served_customers = (serve1 + serve2 + serve3 + serve4)

                    prob = (
                        (SERVE_PROB ** (serve1 + serve2 + serve3 + serve4))
                        * ((1 - SERVE_PROB) ** ((queue1 > 0) - serve1))
                        * ((1 - SERVE_PROB) ** ((queue2 > 0) - serve2))
                        * ((1 - SERVE_PROB) ** ((queue3 > 0) - serve3))
                        * ((1 - SERVE_PROB) ** ((queue4 > 0) - serve4))
                    )

                    if (new_queue1, new_queue2, new_queue3, new_queue4, new_served_customers) in serving_outcomes:
                        serving_outcomes[(new_queue1, new_queue2, new_queue3, new_queue4, new_served_customers)] += prob
                    else:
                        serving_outcomes[(new_queue1, new_queue2, new_queue3, new_queue4, new_served_customers)] = prob

    serving_outcomes_cache[(queue1>0, queue2>0, queue3>0, queue4>0)] = serving_outcomes
    return serving_outcomes
        
def customer_arrival(served_customers):
    # Probability peaks at GOAL_SERVE_COUNT/2 customers (0.8), starts at 0.3, ends at 0.1
    if served_customers <= GOAL_SERVE_COUNT / 2:
        # Linear increase from 0.3 to 0.8 over 0-GOAL_SERVE_COUNT/2 customers
        return 0.3 + (served_customers / (GOAL_SERVE_COUNT / 2)) * 0.5
    else:
        # Linear decrease from 0.8 to 0.1 over GOAL_SERVE_COUNT/2-GOAL_SERVE_COUNT customers
        return 0.8 - ((served_customers - GOAL_SERVE_COUNT / 2) / (GOAL_SERVE_COUNT / 2)) * 0.7




def delta(state, action):

    if state == "init":
        outcomes = {(0,0,0,0,0,True): 1.0}
        return [(prob, state) for state, prob in outcomes.items()]
    
    queue1, queue2, queue3, queue4, served_customers, customer_waiting = state

    if served_customers >= GOAL_SERVE_COUNT:
        return [(1.0, state)]  # No more actions possible, stay in the same state
    

    if not customer_waiting:
        serving_outcomes = serving_customers(state)
        customer_arrival_prob = customer_arrival(served_customers)

        outcomes = {}

        for (new_queue1, new_queue2, new_queue3, new_queue4, new_served_customers), serve_prob in serving_outcomes.items():
            for customer_arrives in [True, False]:
                if customer_arrives:
                    new_customer_waiting = True
                    arrival_prob = customer_arrival_prob
                else:
                    new_customer_waiting = False
                    arrival_prob = 1 - customer_arrival_prob

                new_state = (queue1 - new_queue1, queue2 - new_queue2, queue3 - new_queue3, queue4 - new_queue4, served_customers + new_served_customers, new_customer_waiting)
                total_prob = serve_prob * arrival_prob

                if new_state in outcomes:
                    outcomes[new_state] += total_prob
                else:
                    outcomes[new_state] = total_prob

        # assert sum(outcomes.values()) == 1.0, f"Probabilities do not sum to 1: {sum(outcomes.values())} at state: {state} with action: {action}"

        return [(prob, state) for state, prob in outcomes.items()]
    
    else:

        outcomes = {}
        serving_outcomes = serving_customers(state)

        if action == "place1":

            for (new_queue1, new_queue2, new_queue3, new_queue4, new_served_customers), serve_prob in serving_outcomes.items():
                new_state = (min(queue1+1-new_queue1, MAX_QUEUE_SIZE), queue2 - new_queue2, queue3 - new_queue3, queue4 - new_queue4, served_customers + new_served_customers, False)
                total_prob = serve_prob

                if new_state in outcomes:
                    outcomes[new_state] += total_prob
                else:
                    outcomes[new_state] = total_prob

        elif action == "place2":

            for (new_queue1, new_queue2, new_queue3, new_queue4, new_served_customers), serve_prob in serving_outcomes.items():
                new_state = (queue1 - new_queue1, min(queue2+1-new_queue2, MAX_QUEUE_SIZE), queue3 - new_queue3, queue4 - new_queue4, served_customers + new_served_customers, False)
                total_prob = serve_prob

                if new_state in outcomes:
                    outcomes[new_state] += total_prob
                else:
                    outcomes[new_state] = total_prob

        elif action == "place3":

            for (new_queue1, new_queue2, new_queue3, new_queue4, new_served_customers), serve_prob in serving_outcomes.items():
                new_state = (queue1 - new_queue1, queue2 - new_queue2, min(queue3+1-new_queue3, MAX_QUEUE_SIZE), queue4 - new_queue4, served_customers + new_served_customers, False)
                total_prob = serve_prob

                if new_state in outcomes:
                    outcomes[new_state] += total_prob
                else:
                    outcomes[new_state] = total_prob

        elif action == "place4":
            
            for (new_queue1, new_queue2, new_queue3, new_queue4, new_served_customers), serve_prob in serving_outcomes.items():
                new_state = (queue1 - new_queue1, queue2 - new_queue2, queue3 - new_queue3, min(queue4+1-new_queue4, MAX_QUEUE_SIZE), served_customers + new_served_customers, False)
                total_prob = serve_prob

                if new_state in outcomes:
                    outcomes[new_state] += total_prob
                else:
                    outcomes[new_state] = total_prob

        elif action == "wait":
            for (new_queue1, new_queue2, new_queue3, new_queue4, new_served_customers), serve_prob in serving_outcomes.items():
                new_state = (queue1 - new_queue1, queue2 - new_queue2, queue3 - new_queue3, queue4 - new_queue4, served_customers + new_served_customers, True)
                total_prob = serve_prob

                if new_state in outcomes:
                    outcomes[new_state] += total_prob
                else:
                    outcomes[new_state] = total_prob

        else:
            assert False, f"Invalid action: {action} at state: {state}"

        # assert sum(outcomes.values()) == 1.0, f"Probabilities do not sum to 1: {sum(outcomes.values())} at state: {state} with action: {action}"
        return [(prob, state) for state, prob in outcomes.items()]

    
    
    assert False, f"Invalid action: {action} at state: {state}"


def labels(state):

    if state == "init":
        return ["init"]
    
    queue1, queue2, queue3, queue4, served_customers, customer_waiting = state

    if served_customers >= GOAL_SERVE_COUNT:
        return ["goal"]
    
    return str(state)
    # return "running"
    


def rewards(state, action):
    
    if state == "init" or labels(state) == "goal":
        return {"rew": 0}
    
    queue1, queue2, queue3, queue4, served_customers, customer_waiting = state

    min_max_diff = max(queue1, queue2, queue3, queue4) - min(queue1, queue2, queue3, queue4)
    queues_full = queue1 == MAX_QUEUE_SIZE and queue2 == MAX_QUEUE_SIZE and queue3 == MAX_QUEUE_SIZE and queue4 == MAX_QUEUE_SIZE

    reward = queue1 + queue2 + queue3 + queue4 + min_max_diff + (10 if customer_waiting and queues_full else 0)

    return {"rew": reward}
    



def queues():
    queues = stormvogel.bird.build_bird(
        delta=delta,
        init="init",
        available_actions=available_actions,
        labels=labels,
        modeltype=stormvogel.ModelType.MDP,
        rewards=rewards,
        max_size=1000000
    )

    vmax = stormvogel.model_checking(queues, "Pmax=? [ F \"goal\" ]").values
    print(f"Maximum probability of reaching the goal: {list(vmax.values())[0]}")

    rmin = stormvogel.model_checking(queues, "Rmin=? [ F \"goal\" ]").values
    print(f"Minimum expected reward to reach the goal: {list(rmin.values())[0]}")

    print(queues)

    model = stormvogel.stormpy_utils.stormvogel_to_stormpy(queues)

    # print(model)

    exit()

    stormpy.export_to_drn(model, current_script_directory() + "/sketch.templ")

    state_valuations_json = []

    for state in queues.states:
        label = next(state.labels).replace('(', '').replace(')', '').split(', ')

        if len(label) == 1:
            if label[0] == "init":
                state_valuations_json.append([["queue1", 0], ["queue2", 0], ["queue3", 0], ["queue4", 0], ["served_customers", 0], ["customer_waiting", False]])
            if label[0] == "goal":
                state_valuations_json.append([["queue1", 0], ["queue2", 0], ["queue3", 0], ["queue4", 0], ["served_customers", GOAL_SERVE_COUNT], ["customer_waiting", False]])
        else:
            state_valuations_json.append([["queue1", int(label[0])], ["queue2", int(label[1])], ["queue3", int(label[2])], ["queue4", int(label[3])], ["served_customers", int(label[4])], ["customer_waiting", label[5] == "True"]])

    import json
    with open(current_script_directory() + "/state-valuations.json", "w") as f:
        json.dump(state_valuations_json, f, indent=4)


if __name__ == "__main__":
    queues()