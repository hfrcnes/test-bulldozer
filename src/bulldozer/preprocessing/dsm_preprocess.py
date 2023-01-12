#!/usr/bin/env python
# coding: utf8
#
# Copyright (c) 2022 Centre National d'Etudes Spatiales (CNES).
#
# This file is part of Bulldozer
# (see https://github.com/CNES/bulldozer).
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
    This module is used to preprocess the DSM in order to improve the DTM computation.
"""

import sys
import rasterio
import os
import concurrent.futures
import numpy as np
import logging
import scipy.ndimage as ndimage
from rasterio.windows import Window
from rasterio.fill import fillnodata
import bulldozer.bordernodata as bn
import bulldozer.disturbedareas as da
from bulldozer.utils.helper import write_dataset
from tqdm import tqdm
from os import remove
from bulldozer.utils.logging_helper import BulldozerLogger
from bulldozer.scale.tools import computeTiles, scaleRun, scaleRunDebug
from bulldozer.utils.helper import Runtime

# No data value constant used in bulldozer
NO_DATA_VALUE = -32768

def generate_output_profile_for_mask(input_profile: rasterio.DatasetReader.profile) -> dict:
    output_profile = input_profile
    output_profile['dtype'] = np.ubyte
    return output_profile

def border_nodata_computer( inputBuffers: list,
                            params: dict) -> np.ndarray:
    """ 
    This method computes the border nodata mask in a given window of the input DSM.

    Args:
        inputBuffers: contain just one DSM buffer.
        params:  dictionnary containing:
            nodata value: DSM potentially custom nodata 
            doTranspose: boolean flag to computer either horizontally or vertically the border no data.
    Returns:
        mask flagging the border nodata areas
    """
    dsm = inputBuffers[0]
    nodata = params['nodata']

    if np.isnan(nodata):
        dsm = np.nan_to_num(dsm, False, nan=NO_DATA_VALUE)
        nodata = NO_DATA_VALUE
    
    # We're using our C++ implementation to perform this computation
    border_nodata = bn.PyBorderNodata()

    if params["doTranspose"]:
        return border_nodata.build_border_nodata_mask(dsm, nodata).astype(np.ubyte)
    else:
        # Vertical border nodata detection case (axis = 1)
        border_nodata_mask = border_nodata.build_border_nodata_mask(dsm.T, nodata).astype(np.ubyte)
        return border_nodata_mask.T
    
@Runtime
def build_border_nodata_mask(dsm_path : str, 
                             nb_max_workers : int, 
                             nodata : float = None) -> np.ndarray:
    """
    This method builds a mask corresponding to the border nodata values.
    Those areas correpond to the nodata points on the edges if the DSM is skewed.

    Args:
        dsm_path: path to the input DSM.
        nb_max_workers: number of availables workers (multiprocessing).
        nodata: nodata value of the input DSM. If None, retrieve this value from the input DSM metadata.

    Returns:
        border nodata boolean masks.
    """

    borderNoDataParams: dict = {
        'doTranspose': False,
        'nodata': nodata,
        'desc': "Build Border NoData Mask"
    }

    horizontal_border_nodata = scaleRun(inputImagePaths = [dsm_path], 
                                        outputImagePath = None, 
                                        algoComputer = border_nodata_computer, 
                                        algoParams = borderNoDataParams, 
                                        generateOutputProfileComputer = generate_output_profile_for_mask, 
                                        nbWorkers = nb_max_workers, 
                                        stableMargin = 0, 
                                        inMemory=True)
    
    borderNoDataParams['doTranspose'] = True
    vertical_border_nodata = scaleRun(inputImagePaths = [dsm_path], 
                                        outputImagePath = None, 
                                        algoComputer = border_nodata_computer, 
                                        algoParams = borderNoDataParams, 
                                        generateOutputProfileComputer = generate_output_profile_for_mask, 
                                        nbWorkers = nb_max_workers, 
                                        stableMargin = 0, 
                                        inMemory=True)     
    
    # Merges the two masks
    return np.logical_and(horizontal_border_nodata, vertical_border_nodata)


def disturbedAreasComputer(inputBuffers: list, params: dict) -> np.ndarray:
    """
        This method computes the disturbance in a DSM window through the horizontal axis.
        It returns the corresping disturbance mask.

        Args:
            inputBuffers: contain just one DSM buffer.
            params:  dictionnary containing:
                nodata value: DSM potentially custom nodata 
                slope_treshold: if the slope is greater than this threshold then we consider it as disturbed variation.
                is_four_connexity: number of evaluated axis.
        Returns:
            mask flagging the disturbed areas. 
    """

    nodata = params["nodata"]

    if np.isnan(nodata):
        dsm = np.nan_to_num(dsm, False, nan=NO_DATA_VALUE)
        nodata = NO_DATA_VALUE

    disturbed_areas = da.PyDisturbedAreas(params["is_four_connexity"])
    disturbance_mask = disturbed_areas.build_disturbance_mask(inputBuffers[0], 
                                                              params["slope_threshold"],
                                                              params["nodata"]).astype(np.ubyte)
    return disturbance_mask


def build_disturbance_mask(dsm_path: str,
                           nb_max_workers : int,
                           slope_threshold: float = 2.0,
                           is_four_connexity : bool = True,
                           nodata: float = NO_DATA_VALUE) -> np.array:
    """
    This method builds a mask corresponding to the disturbed areas in a given DSM.
    Most of those areas correspond to water or correlation issues during the DSM generation (obstruction, etc.).

    Args:
        dsm_path: path to the input DSM.
        nb_max_workers: number of availables workers (multiprocessing).
        slope_treshold: if the slope is greater than this threshold then we consider it as disturbed variation.
        is_four_connexity: number of evaluated axis. 
                        Vertical and horizontal if true else vertical, horizontal and diagonals.

    Returns:
        masks containing the disturbed areas.
    """

    disturbanceParams = {
        "is_four_connexity": is_four_connexity,
        "slope_threshold": slope_threshold,
        "nodata": nodata,
        "desc": "Build Disturbance Mask"
    }

    disturbance_mask = scaleRun(inputImagePaths = [dsm_path], 
                                outputImagePath = None,
                                algoComputer= disturbedAreasComputer, 
                                algoParams = disturbanceParams, 
                                generateOutputProfileComputer = generate_output_profile_for_mask, 
                                nbWorkers = nb_max_workers, 
                                stableMargin = 1,
                                inMemory=True)
    return disturbance_mask != 0
    
def write_quality_mask(border_nodata_mask: np.ndarray,
                       inner_nodata_mask : np.ndarray, 
                       disturbed_area_mask : np.ndarray,
                       quality_mask_path: str,
                       profile : rasterio.profiles.Profile) -> None:
    """
    This method merges the nodata masks generated during the DSM preprocessing into a single quality mask.
    There is a priority order: inner_nodata > disturbance
    (e.g. if a pixel is tagged as disturbed and inner_nodata, the output value will correspond to inner_nodata).

    Args:
        inner_nodata_mask: nodata areas in the input DSM.
        disturbed_area_mask: areas flagged as nodata due to their aspect (mainly correlation issue).
        output_dir: bulldozer output directory. The quality mask will be written in this folder.
        profile: DSM profile (TIF metadata).
    """     
    quality_mask = np.zeros(np.shape(inner_nodata_mask), dtype=np.uint8)

    # Metadata update
    profile['dtype'] = np.uint8
    profile['count'] = 1
    # We don't except nodata value in this mask
    profile['nodata'] = None
    quality_mask[disturbed_area_mask] = 2
    quality_mask[inner_nodata_mask] = 1
    quality_mask[border_nodata_mask] = 3
    write_dataset(quality_mask_path, quality_mask, profile)



def preprocess_pipeline(dsm_path : str, 
                        output_dir : str,
                        nb_max_workers : int,
                        nodata : float = None,
                        slope_threshold : float = 2.0, 
                        is_four_connexity : bool = True,
                        minValidHeight: float = None) -> None:
    """
    This method merges the nodata masks generated during the DSM preprocessing into a single quality mask.
    There is a priority order: inner_nodata > disturbance
    (e.g. if a pixel is tagged as disturbed and inner_nodata, the output value will correspond to inner_nodata).

    Args:
        dsm_path: path to the input DSM.
        output_dir: bulldozer output directory. The quality mask will be written in this folder.
        nb_max_workers: number of availables workers (for multiprocessing purpose).
        nodata: nodata value of the input DSM. If None, retrieve this value from the input DSM metadata.
        slope_treshold: if the slope is greater than this threshold then we consider it as disturbed variation.
        is_four_connexity: number of evaluated axis. 
                        Vertical and horizontal if true else vertical, horizontal and diagonals.
    """ 

    BulldozerLogger.log("Starting preprocess", logging.DEBUG)

    # The value is already retrieved before calling the preprocess method
    # If it is none, it is set automatically to -32768
    if nodata is None:
        BulldozerLogger.log("No data value is set to " + str(NO_DATA_VALUE), logging.INFO)
        nodata = NO_DATA_VALUE

    with rasterio.open(dsm_path) as dsm_dataset:
        
        # Read the buffer in memory
        dsm = dsm_dataset.read(1)
        
        # handle the case where there are dynamic nodata values (MicMac DSM for example)
        if minValidHeight:
            BulldozerLogger.log("Min valid height set by the user" + str(minValidHeight), logging.INFO)
            dsm = np.where( dsm < minValidHeight, nodata, dsm)

        preprocessedDsmProfile = dsm_dataset.profile
        preprocessedDsmProfile['nodata'] = nodata
        
        # Generates inner nodata mask
        BulldozerLogger.log("Starting inner_nodata_mask and border_nodata_mask building", logging.DEBUG)
        border_nodata_mask = build_border_nodata_mask(dsm_path, nb_max_workers, nodata)
        inner_nodata_mask = np.logical_and(np.logical_not(border_nodata_mask), dsm == nodata)
        BulldozerLogger.log("inner_nodata_mask and border_nodata_mask generation: Done", logging.INFO)
                
        # Retrieves the disturbed area mask (mainly correlation issues: occlusion, water, etc.)
        BulldozerLogger.log("Compute disturbance mask", logging.DEBUG)
        disturbed_area_mask = build_disturbance_mask(dsm_path, nb_max_workers, slope_threshold, is_four_connexity, nodata)
        BulldozerLogger.log("disturbance mask: Done", logging.INFO)
        
        # Merges and writes the quality mask
        quality_mask_path = os.path.join(output_dir, "quality_mask.tif")
        write_quality_mask(border_nodata_mask, inner_nodata_mask, disturbed_area_mask, quality_mask_path, dsm_dataset.profile)
        
        dsm[disturbed_area_mask] = nodata

        # Creates the preprocessed DSM. This DSM is only intended for bulldozer DTM extraction function.
        BulldozerLogger.log("Write preprocessed dsm", logging.DEBUG)
        preprocessed_dsm_path = os.path.join(output_dir, 'preprocessed_DSM.tif')
        write_dataset(preprocessed_dsm_path, dsm, preprocessedDsmProfile)

        dsm_dataset.close()
        BulldozerLogger.log("Preprocess done", logging.INFO)

        return preprocessed_dsm_path, quality_mask_path
