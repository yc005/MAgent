""" battle of two armies """

import magent


def get_config(map_size):
    gw = magent.gridworld
    cfg = gw.Config()

    cfg.set({"map_width": map_size, "map_height": map_size})
    cfg.set({"minimap_mode": True})
    cfg.set({"embedding_size": 10})

    troops = cfg.register_agent_type(
        "troops",
        {'width': 1, 'length': 1, 'hp': 10, 'speed': 2,
         'view_range': gw.CircleRange(6), 'attack_range': gw.CircleRange(1.5),
         'damage': 2, 'step_recover': 0.1,

         'step_reward': -0.005,  'kill_reward': 5, 'dead_penalty': -0.1, 'attack_penalty': -0.1,
         })

    tanks = cfg.register_agent_type(
        "tanks",
        {'width': 2, 'length': 2, 'hp': 20, 'speed': 1,
         'view_range': gw.CircleRange(10), 'attack_range': gw.CircleRange(3),
         'damage': 3, 'step_recover': 0.1,

         'step_reward': -0.005, 'kill_reward': 3, 'dead_penalty': -0.2, 'attack_penalty': -0.05,
         })

    rtroops = cfg.add_group(troops)
    rtanks = cfg.add_group(tanks)
    ltroops = cfg.add_group(troops)
    ltanks = cfg.add_group(tanks)

    r_troops = gw.AgentSymbol(rtroops, index='any')
    r_tanks = gw.AgentSymbol(rtanks, index='any')
    l_troops = gw.AgentSymbol(ltroops, index='any')
    l_tanks = gw.AgentSymbol(ltanks, index='any')

    # reward shaping to encourage attack
    cfg.add_reward_rule(gw.Event(l_troops, 'attack', r_troops), receiver=l_troops, value=0.2)
    cfg.add_reward_rule(gw.Event(r_troops, 'attack', l_troops), receiver=r_troops, value=0.2)
    cfg.add_reward_rule(gw.Event(l_tanks, 'attack', r_tanks), receiver=l_tanks, value=0.2)
    cfg.add_reward_rule(gw.Event(r_tanks, 'attack', l_tanks), receiver=r_tanks, value=0.2)
    cfg.add_reward_rule(gw.Event(l_troops, 'attack', r_tanks), receiver=l_troops, value=0.2)
    cfg.add_reward_rule(gw.Event(r_tanks, 'attack', l_troops), receiver=r_tanks, value=0.2)
    cfg.add_reward_rule(gw.Event(l_tanks, 'attack', r_troops), receiver=l_tanks, value=0.2)
    cfg.add_reward_rule(gw.Event(r_troops, 'attack', l_tanks), receiver=r_troops, value=0.2)

    return cfg
