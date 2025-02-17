# v1.5.2
# A2C vs COMA
# right is COMA, left is A2C

"""
Train battle, two models in two processes
"""

import argparse
import time
import logging as log
import math
import os
# os.environ["TF_CPP_MIN_LOG_LEVEL"] = '2'
# # 只显示 warning 和 Error
os.environ["TF_CPP_MIN_LOG_LEVEL"] = '3'
# 只显示 Error

import numpy as np

import magent

from magent.builtin.tf_model import AdvantageActorCritic
from magent.builtin.tf_model import Random
from magent.builtin.tf_model import DeepQNetwork


def load_config(map_size):
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

         'step_reward': -0.005,  'kill_reward': 0, 'dead_penalty': -0.4, 'attack_penalty': -0.05,
         })

    tanks = cfg.register_agent_type(
        "tanks",
        {'width': 2, 'length': 2, 'hp': 40, 'speed': 1.5,
         'view_range': gw.CircleRange(6), 'attack_range': gw.CircleRange(3),
         'damage': 7, 'step_recover': 0.1,

         'step_reward': -0.005, 'kill_reward': 0, 'dead_penalty': -1.6, 'attack_penalty': -0.1,
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
    attack_reward = 1
    cfg.add_reward_rule(gw.Event(l_troops, 'attack', r_troops), receiver=l_troops, value=attack_reward)
    cfg.add_reward_rule(gw.Event(r_troops, 'attack', l_troops), receiver=r_troops, value=attack_reward)
    cfg.add_reward_rule(gw.Event(l_tanks, 'attack', r_tanks), receiver=l_tanks, value=attack_reward)
    cfg.add_reward_rule(gw.Event(r_tanks, 'attack', l_tanks), receiver=r_tanks, value=attack_reward)
    cfg.add_reward_rule(gw.Event(l_troops, 'attack', r_tanks), receiver=l_troops, value=attack_reward)
    cfg.add_reward_rule(gw.Event(r_tanks, 'attack', l_troops), receiver=r_tanks, value=attack_reward)
    cfg.add_reward_rule(gw.Event(l_tanks, 'attack', r_troops), receiver=l_tanks, value=attack_reward)
    cfg.add_reward_rule(gw.Event(r_troops, 'attack', l_tanks), receiver=r_troops, value=attack_reward)

    cfg.add_reward_rule(gw.Event(l_troops, 'attack', l_tanks), receiver=l_troops, value=-10)
    cfg.add_reward_rule(gw.Event(l_tanks, 'attack', l_troops), receiver=l_tanks, value=-10)
    cfg.add_reward_rule(gw.Event(r_tanks, 'attack', r_troops), receiver=r_tanks, value=-10)
    cfg.add_reward_rule(gw.Event(r_troops, 'attack', r_tanks), receiver=r_troops, value=-10)

    return cfg


r_troopsID = 0
r_tanksID = 1
l_troopsID = 2
l_tanksID = 3


def generate_map(env, map_size, handles):
    """ generate a map, which consists of two squares of agents"""
    width = height = map_size
    init_num = map_size * map_size * 0.02
    gap = 3

    # right
    n = init_num
    side = int(math.sqrt(n)) * 2
    pos_troops = []
    pos_tanks = []
    pos_flag = 0
    for x in range(width//2 + gap, width//2 + gap + side, 2):
        for y in range((height - side)//2, (height - side)//2 + side, 2):
            if pos_flag % 6 != 0:
                pos_troops.append([x, y, 0])
            else:
                pos_tanks.append([x, y, 0])
            pos_flag += 1
    env.add_agents(handles[r_troopsID], method="custom", pos=pos_troops)
    env.add_agents(handles[r_tanksID], method="custom", pos=pos_tanks)

    # left
    n = init_num
    side = int(math.sqrt(n)) * 2
    pos_troops = []
    pos_tanks = []
    pos_flag = 0
    for x in range(width//2 - gap - side, width//2 - gap - side + side, 2):
        for y in range((height - side)//2, (height - side)//2 + side, 2):
            if pos_flag % 6 != 0:
                pos_troops.append([x, y, 0])
            else:
                pos_tanks.append([x, y, 0])
            pos_flag += 1
    env.add_agents(handles[l_troopsID], method="custom", pos=pos_troops)
    env.add_agents(handles[l_tanksID], method="custom", pos=pos_tanks)


def play_a_round(env, map_size, handles, models, rlmodels, print_every, train=True, render=False, eps=None):
    """play a ground and train"""
    env.reset()
    generate_map(env, map_size, handles)

    step_ct = 0
    done = False

    n = len(handles)
    obs  = [[] for _ in range(n)]
    ids  = [[] for _ in range(n)]
    acts = [[] for _ in range(n)]
    nums = [env.get_num(handle) for handle in handles]
    total_reward = [0 for _ in range(n)]

    print("===== sample =====")
    print("eps %.2f number %s" % (eps, nums))
    start_time = time.time()
    while not done:
        # take actions for every model
        for i in range(n):
            obs[i] = env.get_observation(handles[i])
            ids[i] = env.get_agent_id(handles[i])
            # print("the ", i, "id th id is, ", ids[i], type(ids), type(ids[i]), type(ids[i][0]))
            # let models infer action in parallel (non-blocking)
            models[i].infer_action(obs[i], ids[i], 'e_greedy', eps, block=False)

        for i in range(n):
            acts[i] = models[i].fetch_action()  # fetch actions (blocking)
            env.set_action(handles[i], acts[i])

        # simulate one step
        done = env.step()

        # sample
        step_reward = []
        for i in range(n):
            rewards = env.get_reward(handles[i])
            if train:
                alives = env.get_alive(handles[i])
                # store samples in replay buffer (non-blocking)
                models[i].sample_step(rewards, alives, block=False)
            s = sum(rewards)
            step_reward.append(s)
            total_reward[i] += s

        # render
        if render:
            env.render()

        # stat info
        nums = [env.get_num(handle) for handle in handles]

        # clear dead agents
        env.clear_dead()

        # check return message of previous called non-blocking function sample_step()
        if args.train:
            for model in models:
                model.check_done()

        if step_ct % print_every == 0:
            print("step %3d,  nums: %s reward: %s,  total_reward: %s " %
                  (step_ct, nums, np.around(step_reward, 2), np.around(total_reward, 2)))

        step_ct += 1
        if step_ct > 550:
            break

    sample_time = time.time() - start_time
    print("steps: %d,  total time: %.2f,  step average %.2f" % (step_ct, sample_time, sample_time / step_ct))

    # train
    # total_loss, value = [0 for _ in range(n)], [0 for _ in range(n)]
    # if train:
    #     print("===== train =====")
    #     start_time = time.time()
    #
    #     # train models in parallel
    #     for i in range(n):
    #         models[i].train(print_every=1000, block=False)
    #     for i in range(n):
    #         total_loss[i], value[i] = models[i].fetch_train()
    #
    #     train_time = time.time() - start_time
    #     print("train_time %.2f" % train_time)

    total_loss, value = [0 for _ in range(n)], [0 for _ in range(n)]
    if train:
        print("===== train =====")
        start_time = time.time()

        # train first half (right) models in parallel
        # for i in range(round(n / 2), n):
        #     models[i].train(print_every=1000, block=False)
        # for i in range(round(n / 2), n):
        #     total_loss[i], value[i] = models[i].fetch_train()

        # train models in parallel
        for i in range(n):
            if rlmodels[i] == DeepQNetwork:
                models[i].train(print_every=1000, block=False)
            if rlmodels[i] == Random:
                pass
            else:
                total_loss_list, value[i] = models[i].train(1000)
                total_loss[i] = total_loss_list[1]
        for i in range(n):
            if rlmodels[i] == DeepQNetwork:
                total_loss[i], value[i] = models[i].fetch_train()

        train_time = time.time() - start_time
        print("train_time %.2f" % train_time)

    def round_list(l): return [round(x, 2) for x in l]
    return round_list(total_loss), nums, round_list(total_reward), round_list(value)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--save_every", type=int, default=5)
    parser.add_argument("--render_every", type=int, default=10)
    parser.add_argument("--n_round", type=int, default=2000)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--load_from", type=int)
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--map_size", type=int, default=125)
    parser.add_argument("--greedy", action="store_true")
    parser.add_argument("--name", type=str, default="battle")
    parser.add_argument("--eval", action="store_true")
    parser.add_argument('--alg', default='dqn', choices=['dqn', 'drqn', 'a2c'])
    args = parser.parse_args()

    # set logger
    magent.utility.init_logger(args.name)

    # init the game
    env = magent.GridWorld(load_config(args.map_size))
    env.set_render_dir("build/render")

    # two groups of agents
    handles = env.get_handles()

    # sample eval observation set
    eval_obs = [None for _ in range(len(handles))]
    if args.eval:
        print("sample eval set...")
        env.reset()
        generate_map(env, args.map_size, handles)
        for i in range(len(handles)):
            eval_obs[i] = magent.utility.sample_observation(env, handles, 2048, 500)

    # load models
    batch_size = 256
    unroll_step = 8
    target_update = 1200
    train_freq = 5

    # if args.alg == 'dqn':
    #     from magent.builtin.tf_model import DeepQNetwork
    #     RLModel = DeepQNetwork
    #     # RLModels.append(RLModel)
    #     base_args = {'batch_size': batch_size,
    #                  'memory_size': 2 ** 20, 'learning_rate': 1e-4,
    #                  'target_update': target_update, 'train_freq': train_freq}
    # elif args.alg == 'drqn':
    #     from magent.builtin.tf_model import DeepRecurrentQNetwork
    #     RLModel = DeepRecurrentQNetwork
    #     # RLModels.append(RLModel)
    #     base_args = {'batch_size': batch_size / unroll_step, 'unroll_step': unroll_step,
    #                  'memory_size': 8 * 625, 'learning_rate': 1e-4,
    #                  'target_update': target_update, 'train_freq': train_freq}
    # elif args.alg == 'a2c':
    #     # see train_against.py to know how to use a2c
    #     from magent.builtin.tf_model import AdvantageActorCritic
    #     RLModel = AdvantageActorCritic
    #     # RLModels.append(RLModel)
    #     step_batch_size = 10 * args.map_size * args.map_size * 0.04
    #     base_args = {'learning_rate': 1e-4}
    #
    # RLModels = [AdvantageActorCritic, AdvantageActorCritic, AdvantageActorCritic, AdvantageActorCritic]

    # init models
    names = [args.name + "-r0", args.name + "-r1", args.name + "-l0", args.name + "-l1"]
    models = []
    RLModels = []

    for i in range(len(names)):
        model_args = {'eval_obs': eval_obs[i]}
        if i < len(names) / 2:
            # from magent.builtin.tf_model import AdvantageActorCritic
            #
            # RLModel = AdvantageActorCritic
            from magent.builtin.tf_model import COMA

            RLModel = COMA
            step_batch_size = 10 * args.map_size * args.map_size * 0.04
            base_args = {'learning_rate': 1e-4}
            RLModels.append(RLModel)
            model_args.update(base_args)
            models.append(magent.ProcessingModel(env, handles[i], names[i], 20000+i, 1000, RLModel, **model_args))
        else:
            from magent.builtin.tf_model import AdvantageActorCritic

            RLModel = AdvantageActorCritic
            step_batch_size = 10 * args.map_size * args.map_size * 0.04
            base_args = {'learning_rate': 1e-4}
            RLModels.append(RLModel)
            model_args.update(base_args)
            models.append(magent.ProcessingModel(env, handles[i], names[i], 20000+i, 1000, RLModel, **model_args))


    # load if
    savedir = 'save_model'
    if args.load_from is not None:
        start_from = args.load_from
        print("load ... %d" % start_from)
        for idx, model in enumerate(models):
            if RLModels[idx] != Random:
                model.load(savedir, start_from)
    else:
        start_from = 0

    # print state info
    print(args)
    print("view_space", env.get_view_space(handles[0]))
    print("feature_space", env.get_feature_space(handles[0]))

    # play
    start = time.time()
    for k in range(start_from, start_from + args.n_round):
        tic = time.time()
        eps = magent.utility.piecewise_decay(k, [0, 700, 1400], [1, 0.2, 0.05]) if not args.greedy else 0
        loss, num, reward, value = play_a_round(env, args.map_size, handles, models, RLModels,
                                                train=args.train, print_every=50,
                                                render=args.render or (k+1) % args.render_every == 0,
                                                eps=eps)  # for e-greedy

        log.info("round %d\t loss: %s\t num: %s\t reward: %s\t value: %s" % (k, loss, num, reward, value))
        print("round time %.2f  total time %.2f\n" % (time.time() - tic, time.time() - start))

        # save models
        if (k + 1) % args.save_every == 0 and args.train:
            print("save model... ")
            for idx, model in enumerate(models):
                if RLModels[idx] != Random:
                    model.save(savedir, k)

    # send quit command
    for model in models:
        model.quit()
