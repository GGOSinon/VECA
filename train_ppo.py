import tensorflow as tf
import numpy as np
import os
from baselines.ppo.layer import *
from baselines.ppo.mtl_model_PPO import Model as MTLModel
from baselines.ppo.replaybuffer import MultiTaskReplayBuffer
from baselines.ppo.utils import AdaptiveLR, Saver
import veca.gym
import random
import time
from baselines.ppo.dataloader import MultiTaskDataLoader


if __name__ == "__main__":
    tag = "PPO_COGNIANav"
    PORT = 10000

    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    os.environ["CUDA_VISIBLE_DEVICES"] = "3"

    num_envs = 1
    TRAIN_STEP = 2000000
    SAVE_STEP = 100_000
    REC_STEP = 100000
    NUM_CHUNKS = 4
    NUM_UPDATE = 1
    TRAIN_LOOP = 4
    TIME_STEP = 128
    BUFFER_LENGTH = 2500
    HORIZON = 1280
    GAMMA = 0.99
    LAMBDA = 0.95
    NUM_CHUNKS = 4
    TIME_STEP = 128

    config = tf.ConfigProto()
    config.gpu_options.allow_growth = True
    sess = tf.Session()

    envs = [veca.gym.make(
                task = "cognianav",                                 # VECA task name
                num_envs = num_envs,                                # Number of parallel environment instances to execute
                args = ["--train"],                   # VECA task additional arguments. Append "--help" to list valid arguments.
                seeds = random.sample(range(0, 2000),num_envs ),    # seeds per env instances
                remote_env = False                                  # Whether to use the Environment Orchestrator process at a remote server.
            )]

    class TensorboardLogger:
        def __init__(self, sess, summary_mt, summarys, logdir):
            self.sess = sess
            self.merge = tf.summary.merge(summary_mt) #self.summary())
            self.merge_models = [tf.summary.merge(summary) for summary in summarys]
            self.writer = tf.summary.FileWriter(logdir, self.sess.graph)
        def log(self, feed_dict_mt, feed_dicts, global_step):
            summary = self.sess.run(self.merge, feed_dict = feed_dict_mt) #{)
            self.writer.add_summary(summary, global_step)
            for summary_dict, merge in zip(feed_dicts,self.merge_models):
                summary = self.sess.run(merge, feed_dict = summary_dict)
                self.writer.add_summary(summary, global_step)


    dl = MultiTaskDataLoader(envs)
    buffers = MultiTaskReplayBuffer(len(envs), buffer_length=BUFFER_LENGTH, timestep=TIME_STEP)

    dl.reset(buffers)

    obs_sample = buffers.sample_batch()

    model = MTLModel(envs, sess, obs_sample, tag)

    result_dir = os.path.join("work_dir", tag)

    logger = TensorboardLogger(sess, model.summary(), [submodel.summary() for submodel in model.models], logdir=result_dir)
    lr_scheduler = AdaptiveLR(schedule = True)
    frac = 1.
    entropy_coeff = 0.01 * frac

    saver = Saver(sess)
    saver.load_if_exists(ckpt_dir = result_dir)
    
    obs, reward, done, infos = dl.sample(buffers)

    for step in range(TRAIN_STEP):
        actions = model.get_action(obs)
        obs, reward, done, infos = dl.step(actions,buffers)

        if (step+1) % TIME_STEP == 0:
            start = time.time()
            batches = buffers.sample_batch()
            print("ElapsedC:", time.time() - start, "ms")

            start = time.time()
            summarys = model.feed_batch(batches)
            print("ElapsedD:", time.time() - start, "ms")
            start = time.time()
            loss, loss_agent, loss_critic, ratio, pg_loss, grad = model.forward(ent_coef = entropy_coeff)
            print("ElapsedE:", time.time() - start, "ms")
            
            start = time.time()
            for idx in range(TRAIN_LOOP):
                approxkl = model.optimize_step(lr = lr_scheduler.lrA / (TRAIN_LOOP), ent_coef = entropy_coeff)
                if approxkl > 0.01: break
            print("ElapsedF:", time.time() - start, "ms")
            
            start = time.time()
            lossP, _, _, _, _, _ = model.forward(ent_coef = entropy_coeff)
            print("ElapsedG:", time.time() - start, "ms")

            start = time.time()
            lr_scheduler.step(model.backup, approxkl, loss, lossP)
            print("ElapsedH:", time.time() - start, "ms")

            buffers.clear()

            start = time.time()
            logger.log({model.summary_dict["lr"]:lr_scheduler.lrA, model.summary_dict["ent_coeff"]:entropy_coeff}, summarys,step)
            #model.log(summarys, lr_scheduler.lrA, entropy_coeff, step)
            if approxkl <= 0.01: print("KLD {:.3f}, updated full gradient step.".format(approxkl))
            else: print("KLD {:.3f}, early stopping.".format(approxkl))
            print("STEP", step, "Loss {:.5f} Aloss {:.5f} Closs {:.5f} Maximum ratio {:.5f} pg_loss {:.5f} grad {:.5f}".format(
                loss, loss_agent, loss_critic, ratio, pg_loss, grad))
            print("ElapsedI:", time.time() - start, "ms")

        if (step+1) % HORIZON == 0:
            dl.reset(buffers)
        if step % SAVE_STEP == 0:
            saver.save(ckpt_dir = result_dir, global_step = step )


