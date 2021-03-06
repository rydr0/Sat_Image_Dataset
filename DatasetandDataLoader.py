import torch
import torchvision
from torch.utils.data import Dataset, DataLoader
import matplotlib.pyplot as plt
from PIL import Image

import geopandas as gpd
from osgeo import gdal
import numpy as np
import math
import os


def random_crop_image(image, crp_h=33, crp_w=50):
    '''Return a randomly cropped image with dimensions
    [channels x crp_h x crp_w] given an image with dimensions
    [channels x h x w] where h > crp_h and w > crp_w.
    Arguments:
        image (tensor): image to be cropped
        crp_h (int): height of cropped image
        crp_w (int): widgth of cropped image
    '''
    shape = image.shape
    img_h, img_w = shape[1], shape[2]

    diff_h = img_h - crp_h
    diff_w = img_w - crp_w

    if diff_h > 0:
        rand_pixel_h = np.random.randint(0, diff_h)
    else:
        rand_pixel_h = 0

    if diff_w > 0:
        rand_pixel_w = np.random.randint(0, diff_w)
    else:
        rand_pixel_w = 0

    cropped_image = image[:, rand_pixel_h:crp_h +
                          rand_pixel_h, rand_pixel_w:crp_w + rand_pixel_w]

    return cropped_image


def horizontal_flip(image):
    '''Flips an image horizontally'''
    image = torch.flip(image, [1])
    return image


def vertical_flip(image):
    '''Flips an image vertically'''
    image = torch.flip(image, [2])
    return image


def classify(label, classes=6):
    '''Create class labels from population labels
    Arguments:
        label - label to create a class for
        classes - int, either 16 or 6 classes
        16: bounds are 2**0, 2**1, 2**2, 2**3, 2**4, 2**5, 2**6, 2**7, 2**8, 2**9, 2**10, 2**11, 2**12, 2**13, 2**14
        6: bounds are 1, 10, 100, 1000, 10000
    Returns:
        label with added dimension with class label
    '''
    if classes == 16:
        bounds = [
            2**0, 2**1, 2**2, 2**3, 2**4, 2**5, 2**6, 2**7, 2**8, 2**9, 2**10,
            2**11, 2**12, 2**13, 2**14
        ]
    if classes == 6:
        bounds = [1, 10, 100, 1000, 10000]
    if label[1] > bounds[-1]:
        label = torch.cat((label, torch.tensor([[len(bounds)]])), dim=0)
    else:
        for c, bound in enumerate(bounds):
            if label[1] < bound:
                label = torch.cat((label, torch.tensor([[c]])), dim=0)
                break
    return label


def load_images_and_labels(test=False, colab=False, classes=16):
    '''Function for loading TIF images and corresponding shapefiles with population labels.
    Arguments:
        test - True for loading test set, False for loading training set
        colab - True if loading from google colab storage
        classes - 16 or 6 depending on desired classification bounds
    Returns:
        (image_list , label_list, geo_list)
        
    '''

    if test == False:
        # File Formats and Prefixes
        if colab == False:
            sat_image_folder = 'C:/Users/rdroz/Documents/Dissertation Data Files/Train/Images'
            labels_folder = 'C:/Users/rdroz/Documents/Dissertation Data Files/Train/Labels'
        else:
            sat_image_folder = '/content/Sat_Image_Dataset/Train/Images'
            labels_folder = '/content/Sat_Image_Dataset/Train/Labels'
        image_prefix = 'Train Set clipped_Index_'

    else:
        if colab == False:
            sat_image_folder = 'C:/Users/rdroz/Documents/Dissertation Data Files/Test/Images'
            labels_folder = 'C:/Users/rdroz/Documents/Dissertation Data Files/Test/Labels'
        else:
            sat_image_folder = '/content/Sat_Image_Dataset/Test/Images'
            labels_folder = '/content/Sat_Image_Dataset/Test/Labels'
        image_prefix = 'Test Set clipped_Index_'

    shapefile_list = os.listdir(labels_folder)
    image_type = '.tif'
    label_prefix = 'Index_'
    label_type = '.gpkg'

    # Empty lists for storing information
    image_list = []
    label_list = []
    geo_list = []

    # Loop for loading each image and label
    for sf in shapefile_list:

        # get index number from shapefile name
        i = sf.lstrip('Index_').rstrip('.gpkg')

        # Open image, convert to tensor and crop image, append to list
        gdal_data = gdal.Open(sat_image_folder + '/' + image_prefix + i +
                              image_type)
        image = gdal_data.ReadAsArray()
        image = torch.tensor(image)
        image_list.append(image)
        gdal_data = None

        # Open shapefile and get label and geometry, append to lists
        shp = gpd.read_file(labels_folder + '/' + label_prefix + i +
                            label_type)
        label = np.array(shp['Population'])
        index = shp['Index']
        geometry = shp['geometry']
        label = torch.tensor([index, label])
        label = classify(label, classes=classes)
        geometry = [index, geometry]
        label_list.append(label)
        geo_list.append(geometry)
        shp = None

    return image_list, label_list, geo_list


def normalize_fn(x, mean, std):
    '''Normalizes an image using channel means and channel standard deviations.
    Changes are made in place.
    Arguments:
        x - image to be normalized
        mean - calculated image mean by channel
        std - caluclated image standard deviation by channel
    '''

    for i in range(0, len(x)):
        for channel in range(0, x[i].shape[0]):
            x[i][channel] = (x[i][channel] -
                             mean[0][channel]) / std[0][channel]


class SatImageDataset(Dataset):
    
    def __init__(self,
                 test=False,
                 colab=False,
                 normalize=False,
                 mean=None,
                 std=None,
                 flip=False,
                 flip_prob=0.25,
                 classes=16):
        """Creates SatImageDataset
        Arguments:
            test = True for test set, False for training set
            colab = True If running code on Google Colab
            normalize = True if want images to be normalized
            mean = mean for each image channel, optional
            std = standard deviation for each image channel, optional
            flip = True for random horizontal and vertical flips
            flip_prob = Probability of flipping an image
            classes = either 16 or 6 depending on problem"""
        # data loading
        self.x, self.y, self.geo = load_images_and_labels(test=test,
                                                          colab=colab,
                                                          classes=classes)
        if normalize == True:
            normalize_fn(self.x, mean, std)
        self.n_images = len(self.x)
        self.flip = flip
        self.flip_prob = flip_prob

    def __getitem__(self, index):
        if torch.is_tensor(index):
            index = index.tolist()
        im = random_crop_image(self.x[index])

        if self.flip == True:
            if torch.rand(1) < self.flip_prob:
                im = horizontal_flip(im)
            elif torch.rand(1) < self.flip_prob:
                im = vertical_flip(im)

        return im, self.y[index]

    def __len__(self):
        return self.n_images