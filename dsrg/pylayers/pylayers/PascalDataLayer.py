from __future__ import print_function
from __future__ import division

import json
import time
import pickle
from scipy.ndimage import zoom
import cv2
# import caffe
import math
from ipdb import set_trace

import numpy as np
import os.path as osp

from random import shuffle
import random

# class PascalDataLayer(caffe.Layer):
#     """
#     This is a simple data layer for training a weakly segmentation network with seed
#     """
#
#     def setup(self, bottom, top):
#         self._top_names = ["data", "seed"]
#
#         #============== Read input parameters ==============#
#         # params is a python dictionary with layer parameters
#         params = eval(self.param_str)
#
#         MyTransformer.check_params(params)
#
#         self.batch_size = params["batch_size"]
#         self.input_shape = params["crop_size"]
#
#         # create a batch loader to load the images
#         self.batch_loader = BatchLoader(params)
#
#         #============ Reshape tops ===================#
#         top[0].reshape(self.batch_size, 3, self.input_shape[0], self.input_shape[1])
#         top[1].reshape(self.batch_size, 21, 41, 41)
#
#         print_info("PascalDataLayer", params)
#
#     def forward(self, bottom, top):
#         """
#         Load data
#         """
#         for itt in range(self.batch_size):
#             # use the batch loader to load the next image.
#             im, cues = self.batch_loader.load_next_image()
#
#             # add directly to the caffe data layer
#             top[0].data[itt, ...] = im
#             top[1].data[itt, ...] = cues
#
#     def reshape(self, bottom, top):
#         pass
#
#     def backward(self, top, propagate_down, bottom):
#         pass


class BatchLoader(object):

    def __init__(self, params):
        self.batch_size = params["batch_size"]
        self.root_folder = params["root_folder"] # VOC2012 folder
        self.cues_name = params["cue_name"]
        self.source = params["source"]
        np.random.seed(0)

        # get list of image indexes
        self.indexlist = [line.strip().split(' ') for line in open(self.source, "r")]
        self._cur = 0

        self.transformer = MyTransformer(params)

        self.loc_cues = pickle.load(open(self.cues_name, "rb"))

        print("BatchLoader initialized with {} images".format(len(self.indexlist)))

    def load_next_image(self):
        """
        Load the next image in a batch
        """
        # Did we finish an epoch?
        if self._cur == len(self.indexlist):
            self._cur = 0
            print("-----------------------reshuffling----------------------")
            shuffle(self.indexlist)

        # set_trace()

        # Load an image
        index, cue_ind = self.indexlist[self._cur]
        image_file_path = osp.join(self.root_folder, "JPEGImages", str(index))
        image = cv2.imread(image_file_path, cv2.IMREAD_COLOR)

        cue = self.loc_cues[str(cue_ind) + "_cues"] # cue format: (class, row, col, value)
        # cue = self.loc_cues[str(index).split('.')[0] + "_cues"]
        seed = np.zeros(shape=(41, 41, 21), dtype=np.float32)
        seed[cue[1], cue[2], cue[0]] = 1.0 # 1.0

        self._cur += 1
        return self.transformer.preprocess(image, seed)

def ApplyDistort(im, distort_param):

    def random_brightness(im, prob, delta):
        """Do random brightness distortion"""
        assert 0 <= prob <= 1
        assert delta > 0
        rng = random.random()
        if rng < prob:
            rng_delta = random.uniform(-1 * delta, 1 * delta)
            out_im = cv2.convertScaleAbs(im, alpha=1, beta=rng_delta)
            return out_im
        else:
            return im

    def random_contrast(im, prob, lower, upper):
        """Do random contrast distortion"""
        assert 0 <= prob <= 1
        assert upper > lower
        assert lower > 0

        rng = random.random()
        if rng < prob:
            rng_delta = random.uniform(lower, upper)
            out_im = cv2.convertScaleAbs(im, alpha=rng_delta, beta=0)
            return out_im
        else:
            return im

    def random_saturation(im, prob, lower, upper):
        """ Do random saturation distortion"""
        assert 0 <= prob <= 1
        assert upper > lower
        assert lower > 0

        rng = random.random()
        if rng < prob:
            rng_delta = random.uniform(lower, upper)
            if math.fabs(rng_delta - 1.0) != 0.001:
                hsv_im = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
                hsv_im[:, :, 1] = cv2.convertScaleAbs(hsv_im[:, :, 1], alpha=rng_delta, beta=0)
                out_im = cv2.cvtColor(hsv_im, cv2.COLOR_HSV2BGR)
                return out_im
            else:
                return im
        else:
            return im

    def random_hue(im, prob, delta):
        """ Do random hue distortion"""
        assert delta > 0
        rng = random.random()
        if rng < prob:
            rng_delta = random.uniform(-1 * delta, delta)
            hsv_im = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
            hsv_im[:, :, 0] = cv2.convertScaleAbs(hsv_im[:, :, 0], alpha=1, beta=rng_delta)
            out_im = cv2.cvtColor(hsv_im, cv2.COLOR_HSV2BGR)
            return out_im
        else:
            return im

    im = random_brightness(im, distort_param["bright_prob"], distort_param["bright_delta"])
    im = random_contrast(im, distort_param["contrast_prob"], distort_param["contrast_lower"], distort_param["contrast_upper"])
    im = random_saturation(im, distort_param["saturate_prob"], distort_param["saturate_lower"], distort_param["saturate_upper"])
    im = random_hue(im, distort_param["hue_prob"], distort_param["hue_delta"])

    return im

class MyTransformer(object):

    def __init__(self, params):
        MyTransformer.check_params(params)
        self.mean = params["mean"]
        self.is_mirror = params["mirror"]
        self.crop_h, self.crop_w = params["crop_size"]
        self.new_h, self.new_w = params["new_size"]
        self.distort_param = dict()
        self.distort_param["bright_prob"] = params["bright_prob"]
        self.distort_param["bright_delta"] = params["bright_delta"]
        self.distort_param["contrast_prob"] = params["contrast_prob"]
        self.distort_param["contrast_lower"] = params["contrast_lower"]
        self.distort_param["contrast_upper"] = params["contrast_upper"]
        self.distort_param["saturate_prob"] = params["saturate_prob"]
        self.distort_param["saturate_lower"] = params["saturate_lower"]
        self.distort_param["saturate_upper"] = params["saturate_upper"]
        self.distort_param["hue_prob"] = params["hue_prob"]
        self.distort_param["hue_delta"] = params["hue_delta"]

    def set_mean(self, mean):
        self.mean = mean

    def preprocess(self, image, seed):
        image = np.asarray(image, np.uint8)

        # apply random distortion
        image = ApplyDistort(image, self.distort_param)

        image = image.astype(np.float32)
        image -= self.mean

        img_h, img_w = image.shape[:2]
        seed_h, seed_w = seed.shape[:2]
        # for binarized cue, use order=0, for float cue, use order=1
        resized_img = zoom(image, (self.new_h / img_h, self.new_w / img_w, 1.0), order=1)
        resized_seed = zoom(seed, (self.new_h / seed_h, self.new_w / seed_w, 1.0), order=0)

        # random crop
        h_off = random.randint(0, self.new_h - self.crop_h)
        w_off = random.randint(0, self.new_w - self.crop_w)

        crop_img = np.asarray(resized_img[h_off : h_off + self.crop_h, w_off : w_off + self.crop_w], np.float32)
        crop_seed = np.asarray(resized_seed[h_off : h_off + self.crop_h, w_off : w_off + self.crop_w], np.float32)

        # resize seed back to 41x41
        new_seed = zoom(crop_seed, (41.0 / crop_seed.shape[0], 41.0 / crop_seed.shape[1], 1.0), order=0)

        # HWC -> CHW
        crop_img = crop_img.transpose((2, 0, 1))
        new_seed = new_seed.transpose((2, 0, 1))

        if self.is_mirror:
            flip = np.random.choice(2) * 2 - 1
            crop_img = crop_img[:, :, ::flip]
            new_seed = new_seed[:, :, ::flip]

        return crop_img, new_seed

    @classmethod
    def check_params(cls, params):
        if "crop_size" not in params:
            params["crop_size"] = (321, 321)
        if "new_size" not in params:
            params["new_size"] = (353, 353)
        if "mean" not in params:
            params["mean"] = (104.008,116.669,122.675)
        if "mirror" not in params:
            params["mirror"] = True
        if "source" not in params:
            params["source"] = 'input_list.txt'
        if "cue_name" not in params:
            params['cue_name'] = 'localization_cues-sal.pickle'

        if "bright_prob" not in params:
            params["bright_prob"] = 0.5
        if "bright_delta" not in params:
            params["bright_delta"] = 32

        if "contrast_prob" not in params:
            params["contrast_prob"] = 0.5
        if "contrast_lower" not in params:
            params["contrast_lower"] = 0.5
        if "contrast_upper" not in params:
            params["contrast_upper"] = 1.5

        if "saturate_prob" not in params:
            params["saturate_prob"] = 0.5
        if "saturate_lower" not in params:
            params["saturate_lower"] = 0.5
        if "saturate_upper" not in params:
            params["saturate_upper"] = 1.5

        if "hue_prob" not in params:
            params["hue_prob"] = 0.5
        if "hue_delta" not in params:
            params["hue_delta"] = 18

        assert params["new_size"][0] >= params["crop_size"][0]
        assert params["new_size"][1] >= params["crop_size"][1]
        assert osp.exists(params["cue_name"])
        assert osp.exists(params["root_folder"])
        assert osp.exists(params["source"])

def print_info(name, params):
    print("{} initialized with params:\n batch size: {}\n mean: {}\n "
          "root folder: {}\n source: {}\n mirror: {}\n crop size: {}\n "
          "new size: {}\n".format(name, params["batch_size"], params["mean"],
                                  params["root_folder"], params["source"], params["mirror"],
                                  params["crop_size"], params["new_size"]))


if __name__ == '__main__':
    params = {"batch_size": 1,
              "mean": np.array([0.0, 0.0, 0.0]),
              "root_folder": "/data1/yaoqi/Dataset/VOCdevkit/VOC2012/",
              "source":"/data1/yaoqi/segmentation/weakly/DSRG-master/training/experiment/seed_mc/list/train_aug_id.txt",
              "mirror": True,
              "crop_size": (321, 321),
              "new_size": (353, 353),
              "cue_name": "/data1/yaoqi/segmentation/weakly/DSRG-master/training/localization_cues/localization_cues-sal.pickle"}
    t = MyTransformer(params)

    # cue_name = "/data1/yaoqi/segmentation/weakly/DSRG-master/training/localization_cues/generate_seed/my_localization_cues.pkl"

    cue_id = "6154" #"479"
    im_name = "2007_000032"#"2007_000039"
    cues = pickle.load(open(params["cue_name"], "rb"))
    # cue = cues["2007_000039_cues"]
    cue = cues[cue_id + "_cues"]
    seed = np.zeros(shape=(41, 41, 21), dtype=np.float32)
    seed[cue[1], cue[2], cue[0]] = 1.0
    image = cv2.imread(osp.join(params["root_folder"], "JPEGImages", im_name + ".jpg"))

    for _ in range(100):
        crop_im, new_seed = t.preprocess(image, seed)
        crop_im = crop_im.transpose((1, 2, 0)).astype(np.uint8)
        new_seed = new_seed.transpose((1, 2, 0))

        loc = np.where(new_seed == 1)
        mask = np.ones(shape=(41, 41)) * 21
        mask[loc[0], loc[1]] = loc[2]

        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        f1 = plt.figure(facecolor="white")
        rows, cols = 1, 2
        ax = f1.add_subplot(rows, cols, 1)
        ax.imshow(crop_im[:, :, ::-1])
        ax.axis("off")

        ax = f1.add_subplot(rows, cols, 2)
        ax.matshow(mask)
        ax.axis("off")

        # ax = f1.add_subplot(rows, cols, 3)
        # ax.imshow(new_sal[:, :, 0], cmap=cm.Greys_r)
        # ax.axis("off")
        plt.show()

        set_trace()









