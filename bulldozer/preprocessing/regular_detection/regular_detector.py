#!/usr/bin/env python
# coding: utf8
#
# Copyright (c) 2022-2025 Centre National d'Etudes Spatiales (CNES).
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
This module is used to extract the regular areas in the provided DSM.
"""
import numpy as np
import rasterio
import bulldozer.eoscale.manager as eom
import bulldozer.eoscale.eo_executors as eoexe
import bulldozer.preprocessing.regular as reg
from bulldozer.utils.bulldozer_logger import Runtime

def regular_mask_profile(input_profiles: list,
                         params: dict) -> dict:
    """
        This method is used in the main `detect_regular_areas` 
        method to provide the output mask profile (binary profile).

        Args:
            input_profiles: input profile.
            params: extra parameters.
        
        Returns:
            updated profile.
    """
    input_profiles[0]['dtype'] = np.uint8
    input_profiles[0]['nodata'] = None
    return input_profiles[0]


def regular_mask_filter(input_buffers: list,
                        input_profiles: list, 
                        filter_parameters: dict) -> np.ndarray:
    """
        This method is used in the main `detect_regular_areas`.
        It calls the Cython method to extract regular areas.

        Args:
            input_buffers: input DSM.
            input_profiles: DSM profile.
            filter_parameters: filter parameters.
        
        Returns:
            regular areas mask.
    """
    reg_filter = reg.PyRegularAreas()
    # the input_buffers[0] corresponds to the input DSM raster
    reg_mask = reg_filter.buildRegularMask(input_buffers[0][0, :, :],
                                           slope_threshold=filter_parameters["regular_slope"],
                                           nodata_value=filter_parameters["nodata"])
    return reg_mask     

@Runtime
def detect_regular_areas(dsm_key: str,
                          eomanager: eom.EOContextManager,
                          regular_slope: float) -> dict:
    """
        This method returns the binary mask of the regular areas location in the provided DSM.

        Args:
            dsm_key: input DSM.
            eomanager: eoscale context manager.
            regular_slope: maximum slope of a regular area.

        Returns:
            the regular areas mask.
    """
    regular_parameters: dict = {
        "regular_slope": regular_slope,
        "nodata": eomanager.get_profile(key=dsm_key)["nodata"] 
    }

    [regular_mask_key] = eoexe.n_images_to_m_images_filter(inputs=[dsm_key],
                                                           image_filter=regular_mask_filter,
                                                           filter_parameters=regular_parameters,
                                                           generate_output_profiles=regular_mask_profile,
                                                           context_manager=eomanager,
                                                           stable_margin=1,
                                                           filter_desc="Regular mask processing...")
    
    return {
        "regular_mask": regular_mask_key
    }
