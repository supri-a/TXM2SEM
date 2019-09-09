"""Dataset class template

This module provides a template for users to implement custom datasets.
You can specify '--dataset_mode template' to use this dataset.
The class name should be consistent with both the filename and its dataset_mode option.
The filename should be <dataset_mode>_dataset.py
The class name should be <Dataset_mode>Dataset.py
You need to implement the following functions:
    -- <modify_commandline_options>:　Add dataset-specific options and rewrite default values for existing options.
    -- <__init__>: Initialize this dataset class.
    -- <__getitem__>: Return a data point and its metadata information.
    -- <__len__>: Return the number of images.
"""
from data.base_dataset import BaseDataset, get_transform
# from data.image_folder import make_dataset
from PIL import Image
import numpy as np
import glob
import re
import os
import random
from util import util
import torch


class ImageRepairDataset(BaseDataset):
    """A template dataset class for you to implement custom datasets."""
    @staticmethod
    def modify_commandline_options(parser, is_train):
        """Add new dataset-specific options, and rewrite default values for existing options.

        Parameters:
            parser          -- original option parser
            is_train (bool) -- whether training phase or test phase. You can use this flag to add training-specific or test-specific options.

        Returns:
            the modified parser.
        """
        parser.add_argument('--aligned', type=eval, default=True, help='optionally use aligned or unaligned image patches')
        parser.add_argument('--eval_mode', type=eval, default=False, help='determines whether dataset has fixed or random indices')
        parser.add_argument('--patch_size', type=int, default=256, help='image patch size when performing subsampling')
        parser.add_argument('--txm_dir', type=str, default='txm/', help='directory containing TXM images')
        parser.add_argument('--sem_dir', type=str, default='sem/', help='directory containing SEM images')
        parser.add_argument('--charge_dir', type=str, default='charge/', help='directory containing TXM images')
        parser.add_argument('--num_train', type=int, default=10000, help='number of image patches to sample for training set')
        parser.add_argument('--num_test', type=int, default=1000, help='number of image patches to sample for test set')

        parser.set_defaults(max_dataset_size=10000, new_dataset_option=2.0)  # specify dataset-specific default values
        
        return parser

    def __init__(self, opt):
        """Initialize this dataset class.

        Parameters:
            opt (Option class) -- stores all the experiment flags; needs to be a subclass of BaseOptions

        A few things can be done here.
        - save the options (have been done in BaseDataset)
        - get image paths and meta information of the dataset.
        - define the image transformation.
        """
        # save the option and dataset root
        BaseDataset.__init__(self, opt)

        self.patch_size = opt.patch_size
        self.aligned = opt.aligned
        self.eval_mode = opt.eval_mode
        
        # get images for dataset;
        img_nums = []
        TXM = []
        SEM = []
        charges = []
        
        if opt.isTrain:
            base_img_dir = './images/train/'
        else:
            base_img_dir = './images/test/'

        txm_dir = base_img_dir + opt.txm_dir
        sem_dir = base_img_dir + opt.sem_dir
        charge_dir = base_img_dir + opt.charge_dir

        for f in glob.glob(txm_dir+'*.tif'):
            img_nums.append(max(map(int, re.findall('\d+', f))))
            imnum = str(img_nums[-1]).zfill(3)
            TXM.append(np.asarray(Image.open(txm_dir+imnum+'_TXM.tif').convert('L')))
            SEM.append(np.asarray(Image.open(sem_dir+imnum+'_SEM.tif').convert('L')))
            charges.append(np.asarray(Image.open(charge_dir+imnum+'_SEM_mask.tif')))
        
        # Sort according to slice number
        sort_inds = np.argsort(img_nums)
        self.txm = [TXM[i] for i in sort_inds]
        self.sem = [SEM[i] for i in sort_inds]
        self.charges = [charges[i] for i in sort_inds]


        # Define the default transform function from base transform funtion. 
        if opt.model in ['feedforward']:
            self.transform = get_transform(opt, convert=False)
        else:
            self.transform = get_transform(opt)


        # Get patch indices and save subset of patches
        self.txm_save_dir = os.path.join(opt.checkpoints_dir, opt.name, 'sample_imgs', opt.txm_dir)
        self.sem_save_dir = os.path.join(opt.checkpoints_dir, opt.name, 'sample_imgs', opt.sem_dir)
        self.sem_masked_save_dir = os.path.join(opt.checkpoints_dir, opt.name, 'sample_imgs', 'sample_masked_imgs')
        self.sem_fake_save_dir = os.path.join(opt.checkpoints_dir, opt.name, 'sample_imgs','sem_fake')
        util.mkdirs([self.txm_save_dir, self.sem_save_dir, self.sem_fake_save_dir, self.sem_masked_save_dir])

        if opt.isTrain:
            self.length = opt.num_train
        else:
            self.length = opt.num_test

        # Sample fixed patch indices if set to evaluation mode
        if self.eval_mode:
            np.random.seed(999)
            random.seed(999)
            self.indices = []

            for i in range(self.length):
                inds_temp = self.get_aligned_patch_inds()
                self.indices.append(inds_temp)

                txm_patch, sem_masked_patch, sem_patch = self.get_patch(i)
                txm_patch = util.tensor2im(torch.unsqueeze(txm_patch,0))
                sem_masked_patch = util.tensor2im(torch.unsqueeze(sem_masked_patch,0))
                sem_patch = util.tensor2im(torch.unsqueeze(sem_patch,0))

                txm_path = self.txm_save_dir + str(i).zfill(3) + '.png'
                sem_path = self.sem_save_dir + str(i).zfill(3) + '.png'
                sem_masked_path = self.sem_masked_save_dir + str(i).zfill(3) + '.png'
                
                util.save_image(txm_patch, txm_path)
                util.save_image(sem_patch, sem_path)
                util.save_image(sem_masked_patch, sem_masked_path)
        

    def __getitem__(self, index):
        """Return a data point and its metadata information.

        Parameters:
            index -- a random integer for data indexing

        Returns:
            a dictionary of data with their names. It usually contains the data itself and its metadata information.

        Step 1: get a random image path: e.g., path = self.image_paths[index]
        Step 2: load your data from the disk: e.g., image = Image.open(path).convert('RGB').
        Step 3: convert your data to a PyTorch tensor. You can use helpder functions such as self.transform. e.g., data = self.transform(image)
        Step 4: return a data point as a dictionary.
        """

        data_A1, data_A2, data_B = self.get_patch(index)
        data_A = torch.cat((data_A1, data_A2)) # concatenate TXM and masked SEM slices

        A_paths = self.sem_masked_save_dir + str(index).zfill(3) + '.png' 
        B_paths = self.sem_fake_save_dir + str(index).zfill(3) + '.png'

        # Data transformation needs to convert to tensor
        return {'A': data_A, 'B': data_B, 'A_paths': A_paths, 'B_paths': B_paths}


    def __len__(self):
        """Return the total number of images."""
        return self.length


    def get_patch(self, index):
        '''
        Randomly sample patch from image stack
        ''' 
        
        if self.eval_mode:
            imgcoords, maskcoords = self.indices[index] # Unpack indices
            xcoord, ycoord, zcoord = imgcoords
            xcoord2, ycoord2, zcoord2 = maskcoords
        else:
            imgcoords, maskcoords = self.get_aligned_patch_inds()
            xcoord, ycoord, zcoord = imgcoords
            xcoord2, ycoord2, zcoord2 = maskcoords
        
        # fix for performing same transform taken from: https://github.com/pytorch/vision/issues/9 
        seed = np.random.randint(2147483647) # make a seed with numpy generator 
        
        random.seed(seed) # apply this seed to img transforms
        sem_temp_patch = self.sem[zcoord][xcoord:xcoord+self.patch_size, ycoord:ycoord+self.patch_size]
        sem_patch = self.transform(Image.fromarray(sem_temp_patch))
        
        random.seed(seed)
        txm_patch = self.transform(Image.fromarray(self.txm[zcoord][xcoord:xcoord+self.patch_size, ycoord:ycoord+self.patch_size]))
        
        random.seed(seed)
        charge_patch = self.charges[zcoord2][xcoord2:xcoord2+self.patch_size, ycoord2:ycoord2+self.patch_size]
        sem_masked_patch = self.transform(Image.fromarray(charge_patch*sem_temp_patch))
        
        return txm_patch, sem_masked_patch, sem_patch


    def get_aligned_patch_inds(self):
        
        W, H = self.txm[0].shape
        good_patch = False
        good_mask = False
        
        while not good_patch:
            # Sample random coordinate
            xcoord = np.random.randint(0, high = W-self.patch_size)
            ycoord = np.random.randint(0, high = H-self.patch_size)
            zcoord = np.random.randint(0, high = len(self.txm))
            
            # Extract image patches from random coordinate
            sem_patch = self.sem[zcoord][xcoord:xcoord+self.patch_size, ycoord:ycoord+self.patch_size]
            txm_patch = self.txm[zcoord][xcoord:xcoord+self.patch_size, ycoord:ycoord+self.patch_size]
            charge_patch = self.charges[zcoord][xcoord:xcoord+self.patch_size, ycoord:ycoord+self.patch_size]  
            
            # Calculate mask of all black pixels across all three images
            mask = np.greater(charge_patch*sem_patch*txm_patch, 0)

            # Calculate number of pixels that are zero and are uncharged
            mask_prop =  np.sum(mask) / sem_patch.size
            uncharge_prop =  np.sum(charge_patch) / sem_patch.size
            
            # Check if patch is acceptable, if not resample
            if uncharge_prop > 0.99 and mask_prop > 0.75:
                good_patch = True


        while not good_mask:
            # Sample random coordinate
            xcoord2 = np.random.randint(0, high = W-self.patch_size)
            ycoord2 = np.random.randint(0, high = H-self.patch_size)
            zcoord2 = np.random.randint(0, high = len(self.txm))

            charge_patch = self.charges[zcoord2][xcoord2:xcoord2+self.patch_size, ycoord2:ycoord2+self.patch_size] 

            uncharge_prop =  np.sum(charge_patch) / charge_patch.size

            # Check if charge mask is acceptable, if not resample
            if uncharge_prop > 0.25 and uncharge_prop < 0.75:
                good_mask = True


        return (xcoord, ycoord, zcoord), (xcoord2, ycoord2, zcoord2)


    