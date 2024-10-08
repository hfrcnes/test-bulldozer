import numpy as np
import rasterio
import bulldozer.eoscale.manager as eom
import bulldozer.eoscale.eo_executors as eoexe
import bulldozer.preprocessing.regular as reg
from bulldozer.utils.bulldozer_logger import Runtime

def regular_mask_profile(input_profiles: list,
                         params: dict) -> dict:
    
    input_profiles[0]['dtype'] = np.uint8
    input_profiles[0]['nodata'] = None
    return input_profiles[0]


def regular_mask_filter(input_buffers: list,
                        input_profiles: list, 
                        filter_parameters: dict) -> np.ndarray:

    reg_filter = reg.PyRegularAreas()
    reg_mask = reg_filter.buildRegularMask(input_buffers[0][0, :, :],
                                           slope_threshold=filter_parameters["regular_slope"],
                                           no_data_value=filter_parameters["nodata"])
    return reg_mask     

@Runtime
def run(dsm_key: str,
        eomanager: eom.EOContextManager,
        regular_slope: float):
    """ """

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
